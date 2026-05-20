#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
from dataclasses import dataclass, asdict, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from PIL import ImageFile


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

IMG_ATTRS = ("src", "data-src", "data-original", "data-lazy-src", "data-actualsrc")
META_IMAGE_KEYS = {
    ("property", "og:image"),
    ("property", "og:image:url"),
    ("name", "twitter:image"),
    ("name", "twitter:image:src"),
    ("itemprop", "image"),
}
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
INTEGRATION_MODES = {
    "structure-introduction",
    "workflow-bridge",
    "design-justification",
    "result-interpretation",
}
LOW_CONFIDENCE_THRESHOLD = 10
NEGATIVE_TOKENS = {
    "logo",
    "icon",
    "avatar",
    "sprite",
    "badge",
    "favicon",
    "brand",
    "masthead",
    "header",
    "nav",
    "footer",
    "share",
    "social",
    "twitter",
    "opengraph",
    "hero",
    "banner",
    "cover",
    "thumbnail",
    "thumb",
    "poster",
    "promo",
    "profile",
    "site",
    "brandmark",
    "favicon",
    "appicon",
    "marketing",
    "ad",
    "ads",
    "sponsor",
    "sponsored",
    "card",
}
POSITIVE_TOKENS = {
    "figure",
    "diagram",
    "chart",
    "graph",
    "workflow",
    "pipeline",
    "architecture",
    "system",
    "result",
    "analysis",
    "report",
    "article",
    "content",
    "entry",
    "post",
    "illustration",
    "summary",
    "figurecaption",
    "正文",
    "内容",
    "模块",
    "流程",
}
PROMOTED_TAGS = {"figure", "main", "article", "section"}
DEMOTED_TAGS = {"header", "nav", "footer", "aside"}


@dataclass
class Candidate:
    image_url: str
    source: str
    alt: str = ""
    title: str = ""
    score: int = 0
    width: int | None = None
    height: int | None = None
    classes: str = ""
    element_id: str = ""
    context: str = ""
    content_type: str | None = None
    content_length: int | None = None
    notes: list[str] = field(default_factory=list)


def tokenize_text(*parts: str) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", (part or "").lower()):
            if token:
                tokens.add(token)
    return tokens


def parse_dimension(value: str) -> int | None:
    match = re.search(r"(\d+)", value or "")
    return int(match.group(1)) if match else None


class ImageHTMLParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.page_title = ""
        self.candidates: list[Candidate] = []
        self._inside_title = False
        self._stack: list[dict[str, str]] = []

    def _push_context(self, tag: str, attr_map: dict[str, str]) -> None:
        self._stack.append(
            {
                "tag": tag,
                "class": attr_map.get("class", ""),
                "id": attr_map.get("id", ""),
            }
        )

    def _pop_context(self, tag: str) -> None:
        lowered = tag.lower()
        for idx in range(len(self._stack) - 1, -1, -1):
            if self._stack[idx]["tag"] == lowered:
                del self._stack[idx:]
                return

    def _context_string(self) -> str:
        parts = []
        for item in self._stack[-5:]:
            bit = item["tag"]
            if item["id"]:
                bit += f"#{item['id']}"
            if item["class"]:
                bit += "." + ".".join(token for token in item["class"].split() if token)
            parts.append(bit)
        return " > ".join(parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attr_map = {k.lower(): (v or "").strip() for k, v in attrs}
        if lowered == "title":
            self._inside_title = True
            return
        if lowered == "meta":
            for key_name, key_value in META_IMAGE_KEYS:
                if attr_map.get(key_name, "").lower() == key_value:
                    content = attr_map.get("content", "")
                    if content:
                        self.candidates.append(
                            Candidate(
                                image_url=urljoin(self.base_url, content),
                                source=f"meta:{key_value}",
                                title=self.page_title,
                                score=15,
                                context="meta-social-card",
                            )
                        )
                    return
        if lowered != "img":
            self._push_context(lowered, attr_map)
            return

        alt = attr_map.get("alt", "")
        title = attr_map.get("title", "")
        classes = attr_map.get("class", "")
        element_id = attr_map.get("id", "")
        width = parse_dimension(attr_map.get("width", ""))
        height = parse_dimension(attr_map.get("height", ""))
        context = self._context_string()
        found = []
        for attr_name in IMG_ATTRS:
            value = attr_map.get(attr_name, "")
            if value:
                found.append(value)
        srcset = attr_map.get("srcset", "")
        if srcset:
            first_src = srcset.split(",")[0].strip().split(" ")[0].strip()
            if first_src:
                found.append(first_src)
        for raw in found:
            self.candidates.append(
                Candidate(
                    image_url=urljoin(self.base_url, raw),
                    source="img",
                    alt=alt,
                    title=title,
                    score=35,
                    width=width,
                    height=height,
                    classes=classes,
                    element_id=element_id,
                    context=context,
                )
            )

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._inside_title = False
            return
        self._pop_context(lowered)

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.page_title += data.strip()


def sanitize_stem(text: str) -> str:
    text = re.sub(r"\s+", "-", text.strip().lower())
    text = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "web-figure"


def infer_suffix(url: str, content_type: str | None) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in ALLOWED_SUFFIXES:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return ".jpg" if guessed == ".jpe" else guessed
    return ".png"


def probe_image_metadata(image_url: str, timeout: int) -> tuple[int | None, int | None, str | None, int | None]:
    response = requests.get(image_url, headers={"User-Agent": USER_AGENT}, timeout=timeout, stream=True)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type")
    content_length = response.headers.get("Content-Length")
    parser = ImageFile.Parser()
    width = None
    height = None
    bytes_read = 0
    try:
        for chunk in response.iter_content(chunk_size=32768):
            if not chunk:
                continue
            bytes_read += len(chunk)
            parser.feed(chunk)
            if getattr(parser, "image", None) is not None:
                width, height = parser.image.size
                break
            if bytes_read >= 524288:
                break
    finally:
        response.close()
    parsed_length = int(content_length) if content_length and content_length.isdigit() else None
    return width, height, content_type, parsed_length


def apply_dimension_adjustments(item: Candidate, notes: list[str]) -> int:
    score = 0
    if item.width and item.height:
        area = item.width * item.height
        aspect_ratio = item.width / max(1, item.height)
        reverse_ratio = item.height / max(1, item.width)
        if min(item.width, item.height) < 120 or area < 30_000:
            score -= 60
            notes.append("tiny-image")
        elif min(item.width, item.height) < 180 or area < 80_000:
            score -= 25
            notes.append("small-image")
        elif item.width >= 480 and item.height >= 240:
            score += 16
            notes.append("substantial-dimensions")
        if aspect_ratio > 3.6 or reverse_ratio > 3.6:
            score -= 22
            notes.append("extreme-aspect-ratio")
        if abs(item.width - item.height) <= 24 and max(item.width, item.height) <= 256:
            score -= 18
            notes.append("square-icon-like")
        if aspect_ratio > 3.2 and item.height < 500:
            score -= 24
            notes.append("banner-like")
    elif item.source.startswith("meta:"):
        score -= 10
        notes.append("unknown-meta-dimensions")
    return score


def select_candidates(candidates: Iterable[Candidate], page_host: str, pattern: str | None, timeout: int) -> list[Candidate]:
    result: list[Candidate] = []
    seen = set()
    regex = re.compile(pattern, re.I) if pattern else None
    for item in candidates:
        if item.image_url in seen:
            continue
        seen.add(item.image_url)
        parsed = urlparse(item.image_url)
        score = item.score
        notes: list[str] = []
        path_lower = parsed.path.lower()
        tokens = tokenize_text(
            path_lower,
            parsed.query.lower(),
            item.alt,
            item.title,
            item.classes,
            item.element_id,
            item.context,
            item.source,
        )
        if parsed.netloc == page_host:
            score += 20
            notes.append("same-host")
        if item.source.startswith("meta:"):
            score -= 45
            notes.append("demote-social-card-meta")

        neg_hits = sorted(tokens & NEGATIVE_TOKENS)
        if neg_hits:
            strong_hits = {"logo", "icon", "avatar", "sprite", "badge", "favicon"} & set(neg_hits)
            score -= 65 if strong_hits else 35
            notes.append(f"negative-context:{','.join(neg_hits[:4])}")

        context_tokens = tokenize_text(item.context)
        if PROMOTED_TAGS & context_tokens:
            score += 12
            notes.append("inside-content-structure")
        if DEMOTED_TAGS & context_tokens:
            score -= 25
            notes.append("inside-nav-header-footer")

        pos_hits = sorted(tokens & POSITIVE_TOKENS)
        if pos_hits:
            score += min(24, 8 * len(pos_hits))
            notes.append(f"positive-context:{','.join(pos_hits[:3])}")

        descriptive_text = " ".join(part for part in (item.alt, item.title) if part).strip()
        if descriptive_text:
            if len(descriptive_text) >= 12:
                score += 12
                notes.append("descriptive-alt-or-title")
            else:
                score += 4
                notes.append("has-alt-or-title")
        else:
            score -= 8
            notes.append("no-alt-or-title")

        score += apply_dimension_adjustments(item, notes)

        if regex:
            haystack = " ".join((item.image_url, item.alt, item.title, item.context, item.classes, item.element_id))
            if regex.search(haystack):
                score += 30
                notes.append("pattern-match")
            else:
                score -= 30
                notes.append("pattern-miss")

        result.append(
            Candidate(
                item.image_url,
                item.source,
                item.alt,
                item.title,
                score,
                width=item.width,
                height=item.height,
                classes=item.classes,
                element_id=item.element_id,
                context=item.context,
                content_type=item.content_type,
                content_length=item.content_length,
                notes=notes,
            )
        )
    probe_cache: dict[str, tuple[int | None, int | None, str | None, int | None]] = {}
    for item in result[: min(12, len(result))]:
        had_dimensions = bool(item.width and item.height)
        if had_dimensions and item.content_type:
            continue
        try:
            probe_cache[item.image_url] = probe_cache.get(item.image_url) or probe_image_metadata(item.image_url, timeout)
        except Exception:
            continue
        width, height, content_type, content_length = probe_cache[item.image_url]
        item.width = item.width or width
        item.height = item.height or height
        item.content_type = content_type
        item.content_length = content_length
        if not had_dimensions and item.width and item.height:
            item.score += apply_dimension_adjustments(item, item.notes)
        if content_type and not content_type.startswith("image/"):
            item.score -= 60
            item.notes.append("non-image-content-type")
        if content_length is not None and content_length < 8_000:
            item.score -= 25
            item.notes.append("tiny-file")
        elif content_length is not None and content_length > 150_000:
            item.score += 8
            item.notes.append("substantial-file")
    result.sort(
        key=lambda x: (
            x.score,
            (x.width or 0) * (x.height or 0),
            0 if x.source.startswith("meta:") else 1,
        ),
        reverse=True,
    )
    return result


def fetch_html(url: str, timeout: int, render: bool) -> str:
    if render:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError("Playwright is not available for rendered capture") from exc
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            html = page.content()
            browser.close()
            return html

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    return response.text


def download_image(image_url: str, output_dir: Path, suggested_name: str, timeout: int) -> tuple[Path, str | None]:
    response = requests.get(image_url, headers={"User-Agent": USER_AGENT}, timeout=timeout, stream=True)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type")
    suffix = infer_suffix(image_url, content_type)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{suggested_name}{suffix}"
    with output_path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                handle.write(chunk)
    return output_path, content_type


def build_latex_snippet(asset_relpath: str, caption: str, label: str) -> str:
    return "\n".join(
        [
            r"\begin{figure}[htbp]",
            r"  \centering",
            f"  \\includegraphics[width=0.8\\textwidth]{{{asset_relpath}}}",
            f"  \\caption{{{caption}}}",
            f"  \\label{{{label}}}",
            r"\end{figure}",
        ]
    )


def infer_integration_mode(section_context: str | None, caption: str) -> str:
    haystack = f"{section_context or ''} {caption}".lower()
    if any(token in haystack for token in ("结果", "分析", "性能", "对比", "趋势", "测试结果", "result", "analysis")):
        return "result-interpretation"
    if any(token in haystack for token in ("方法", "流程", "平台", "测试流程", "数据流", "workflow", "pipeline", "method")):
        return "workflow-bridge"
    if any(token in haystack for token in ("设计", "实现", "参数", "接口", "约束", "design", "implementation")):
        return "design-justification"
    return "structure-introduction"


def build_integration_note(mode: str, caption: str, section_context: str | None) -> str:
    ctx = section_context or "本节"
    if mode == "workflow-bridge":
        return f"在{ctx}中，{caption}可作为流程承接节点来组织输入、关键处理环节与输出关系，正文应围绕这一链路展开说明。"
    if mode == "design-justification":
        return f"在{ctx}中，{caption}宜用于解释当前结构安排如何回应接口、约束或参数分配要求，从而支撑后续设计选择。"
    if mode == "result-interpretation":
        return f"在{ctx}中，{caption}应结合对应结果或现象进行解读，重点说明可支持的趋势、对比关系及其边界。"
    return f"在{ctx}中，{caption}主要用于交代相关对象的组成关系与层次分工，为后文的结构说明提供参照。"


def classify_selection_confidence(score: int) -> str:
    if score >= 60:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a citable image from a real webpage for thesis insertion.")
    parser.add_argument("--url", required=True, help="Source page URL.")
    parser.add_argument("--output-dir", required=True, help="Directory for the downloaded asset and sidecar metadata.")
    parser.add_argument("--pattern", help="Optional regex to bias candidate image selection.")
    parser.add_argument("--index", type=int, default=0, help="Candidate index after ranking, default 0.")
    parser.add_argument("--candidate", type=int, help="Alias for --index.")
    parser.add_argument("--list-only", action="store_true", help="List ranked candidates without downloading an asset.")
    parser.add_argument("--render", action="store_true", help="Render the page with Playwright before extraction.")
    parser.add_argument("--caption", default="网页来源图片", help="Suggested Chinese figure caption.")
    parser.add_argument("--label", default="fig:web-captured", help="Suggested LaTeX figure label.")
    parser.add_argument("--name", help="Optional stem for the downloaded asset filename.")
    parser.add_argument("--timeout", type=int, default=20, help="Request timeout in seconds.")
    parser.add_argument("--integration-mode", choices=sorted(INTEGRATION_MODES), help="Preferred figure-text integration mode.")
    parser.add_argument("--section-context", help="Optional Chinese section context used to draft the integration note.")
    args = parser.parse_args()

    page_url = args.url
    html = fetch_html(page_url, args.timeout, args.render)
    parser_obj = ImageHTMLParser(page_url)
    parser_obj.feed(html)

    ranked = select_candidates(parser_obj.candidates, urlparse(page_url).netloc, args.pattern, args.timeout)
    if not ranked:
        raise RuntimeError("No candidate images were found on the provided page.")
    candidate_index = args.candidate if args.candidate is not None else args.index
    if args.list_only:
        payload = {
            "source_page_url": page_url,
            "page_title": parser_obj.page_title,
            "candidate_count": len(ranked),
            "candidate_preview": [asdict(item) for item in ranked[:10]],
            "selection_required": True,
            "selection_confidence": classify_selection_confidence(ranked[0].score),
            "recommended_next_step": "Review the candidate list first when confidence is low, then refine with --pattern / --render or choose --candidate explicitly.",
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    if candidate_index < 0 or candidate_index >= len(ranked):
        raise RuntimeError(f"Candidate index {candidate_index} is out of range for {len(ranked)} candidates.")

    chosen = ranked[candidate_index]
    explicit_selection = args.candidate is not None or args.index != 0
    confidence = classify_selection_confidence(chosen.score)
    if not explicit_selection and confidence == "low":
        raise RuntimeError(
            "Only low-confidence webpage images were found. Run with --list-only to inspect candidates, "
            "use --pattern to bias selection, or choose a candidate explicitly with --candidate."
        )
    stem = args.name or sanitize_stem(parser_obj.page_title or Path(urlparse(page_url).path).stem or "web-figure")
    output_dir = Path(args.output_dir).resolve()
    output_path, content_type = download_image(chosen.image_url, output_dir, stem, args.timeout)
    integration_mode = args.integration_mode or infer_integration_mode(args.section_context, args.caption)
    integration_note = build_integration_note(integration_mode, args.caption, args.section_context)

    meta = {
        "source_page_url": page_url,
        "captured_image_url": chosen.image_url,
        "selection_source": chosen.source,
        "selection_score": chosen.score,
        "selection_confidence": confidence,
        "page_title": parser_obj.page_title,
        "image_alt": chosen.alt,
        "image_title": chosen.title,
        "downloaded_asset_path": str(output_path),
        "downloaded_asset_name": output_path.name,
        "content_type": content_type,
        "figure_caption_zh": args.caption,
        "figure_label": args.label,
        "asset_relpath_hint": output_path.name,
        "integration_mode": integration_mode,
        "integration_note_zh": integration_note,
        "integration_note_status": "draft-needs-local-adaptation",
        "latex_snippet": build_latex_snippet(output_path.name, args.caption, args.label),
        "citation_note_zh": "请在正文或图注中标明网页来源，并在参考文献中补入真实网页条目。",
        "candidate_preview": [asdict(item) for item in ranked[:5]],
    }

    metadata_path = output_dir / f"{output_path.stem}.metadata.json"
    metadata_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    json.dump(meta, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
