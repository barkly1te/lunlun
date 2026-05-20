#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import requests
from PIL import Image

from web_figure_capture import (
    USER_AGENT,
    build_integration_note,
    build_latex_snippet,
    infer_integration_mode,
    sanitize_stem,
)


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".bmp", ".tif", ".tiff"}
PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx"}
DOC_SUFFIXES = {".doc"}


@dataclass
class AssetCandidate:
    path: str
    score: int
    note: str
    page: int | None = None


def normalize_text(text: str) -> str:
    return re.sub(r"[\s\u3000]+", "", (text or "").lower())


def summarize_subprocess_error(stderr: str, stdout: str) -> str:
    combined = [line.strip() for line in (stderr or stdout or "").splitlines() if line.strip()]
    if not combined:
        return "No diagnostic output was returned by the delegated capture script."
    for line in reversed(combined):
        if line.startswith("RuntimeError:"):
            return line.removeprefix("RuntimeError:").strip()
    return combined[-1]


def parse_crop_spec(spec: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) != 4:
        raise ValueError("Crop spec must contain exactly four comma-separated numbers: x1,y1,x2,y2")
    try:
        x1, y1, x2, y2 = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError("Crop spec values must be numeric.") from exc
    if x1 >= x2 or y1 >= y2:
        raise ValueError("Crop spec must satisfy x1 < x2 and y1 < y2.")
    return x1, y1, x2, y2


def parse_page_number_from_path(path: Path) -> int | None:
    match = re.search(r"pdf_page-(\d+)", path.stem)
    return int(match.group(1)) if match else None


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def download_file(url: str, output_dir: Path, stem: str | None, timeout: int) -> tuple[Path, str | None]:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, stream=True)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type")
    suffix = Path(urlparse(url).path).suffix.lower()
    if not suffix:
        guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
        suffix = ".bin" if not guessed else (".jpg" if guessed == ".jpe" else guessed)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_stem = stem or sanitize_stem(Path(urlparse(url).path).stem or "downloaded-source")
    target = output_dir / f"{file_stem}{suffix}"
    with target.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                handle.write(chunk)
    return target, content_type


def classify_source(path_or_url: str, content_type: str | None = None) -> str:
    parsed_path = Path(urlparse(path_or_url).path if is_url(path_or_url) else path_or_url)
    suffix = parsed_path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in PDF_SUFFIXES:
        return "pdf"
    if suffix in DOCX_SUFFIXES:
        return "docx"
    if suffix in DOC_SUFFIXES:
        return "doc"
    if is_url(path_or_url):
        ctype = (content_type or "").lower()
        if "pdf" in ctype:
            return "pdf"
        if "word" in ctype or "officedocument.wordprocessingml" in ctype:
            return "docx"
        if ctype.startswith("image/"):
            return "image"
        return "webpage"
    return "unknown"


def copy_local_image(source_path: Path, output_dir: Path, stem: str | None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{(stem or sanitize_stem(source_path.stem))}{source_path.suffix.lower()}"
    shutil.copy2(source_path, target)
    return target


def extract_pdf_images(pdf_path: Path, output_dir: Path, page: int | None = None) -> list[Path]:
    if shutil.which("pdfimages") is None:
        raise RuntimeError("pdfimages is not available on this system")
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / "pdf_image"
    cmd = ["pdfimages", "-all"]
    if page is not None:
        cmd.extend(["-f", str(page), "-l", str(page)])
    cmd.extend([str(pdf_path), str(prefix)])
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
    )
    extracted = [p for p in output_dir.iterdir() if p.is_file() and p.name.startswith("pdf_image")]
    return sorted(extracted, key=lambda p: p.stat().st_size, reverse=True)


def render_pdf_pages(
    pdf_path: Path,
    output_dir: Path,
    page: int | None = None,
    pages: list[int] | None = None,
    max_pages: int = 3,
) -> list[Path]:
    if shutil.which("pdftoppm") is None:
        raise RuntimeError("pdftoppm is not available on this system")
    output_dir.mkdir(parents=True, exist_ok=True)
    if pages:
        rendered: list[Path] = []
        for selected_page in pages:
            prefix = output_dir / f"pdf_page-{selected_page:02d}"
            subprocess.run(
                [
                    "pdftoppm",
                    "-png",
                    "-singlefile",
                    "-f",
                    str(selected_page),
                    "-l",
                    str(selected_page),
                    str(pdf_path),
                    str(prefix),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            candidate = prefix.with_suffix(".png")
            if candidate.exists():
                rendered.append(candidate)
    else:
        prefix = output_dir / "pdf_page"
        first_page = page or 1
        last_page = page or max_pages
        subprocess.run(
            ["pdftoppm", "-png", "-f", str(first_page), "-l", str(last_page), str(pdf_path), str(prefix)],
            check=True,
            capture_output=True,
            text=True,
        )
        rendered = [p for p in output_dir.iterdir() if p.is_file() and p.name.startswith("pdf_page")]
    return sorted(rendered, key=lambda p: p.name)


def extract_docx_images(docx_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(docx_path) as archive:
        for name in archive.namelist():
            if not name.startswith("word/media/"):
                continue
            suffix = Path(name).suffix.lower()
            if suffix not in IMAGE_SUFFIXES:
                continue
            target = output_dir / Path(name).name
            with archive.open(name) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)
    return sorted(extracted, key=lambda p: p.stat().st_size, reverse=True)


def get_pdf_page_count(pdf_path: Path) -> int:
    if shutil.which("pdfinfo") is None:
        raise RuntimeError("pdfinfo is not available on this system")
    result = subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    match = re.search(r"Pages:\s+(\d+)", result.stdout)
    if not match:
        raise RuntimeError("Could not determine PDF page count from pdfinfo output.")
    return int(match.group(1))


def extract_pdf_page_text(pdf_path: Path, page: int) -> str:
    if shutil.which("pdftotext") is None:
        raise RuntimeError("pdftotext is not available on this system")
    result = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def build_figure_queries(figure_number: str) -> list[str]:
    raw = figure_number.strip()
    variants = {raw}
    match = re.search(r"\d+(?:[.\-]\d+)?", raw)
    if match:
        digits = match.group(0)
        variants.update(
            {
                f"图{digits}",
                f"图 {digits}",
                f"figure {digits}",
                f"figure{digits}",
                f"fig. {digits}",
                f"fig {digits}",
                f"fig{digits}",
            }
        )
    return sorted(variants)


def rank_pdf_pages_by_hint(
    pdf_path: Path,
    page_count: int,
    figure_number: str | None = None,
    caption_pattern: str | None = None,
) -> list[dict[str, object]]:
    if not figure_number and not caption_pattern:
        return []
    figure_queries = build_figure_queries(figure_number) if figure_number else []
    regex = re.compile(caption_pattern, re.I) if caption_pattern else None
    ranked: list[dict[str, object]] = []
    for page_number in range(1, page_count + 1):
        text = extract_pdf_page_text(pdf_path, page_number)
        normalized = normalize_text(text)
        score = 0
        reasons: list[str] = []
        if figure_queries:
            hits = [query for query in figure_queries if normalize_text(query) in normalized]
            if hits:
                score += 100 + 10 * len(hits)
                reasons.append(f"figure-number-match:{hits[0]}")
        if regex:
            matched = regex.search(text)
            if matched:
                score += 80
                reasons.append(f"caption-pattern-match:{matched.group(0)}")
        if score > 0:
            ranked.append(
                {
                    "page": page_number,
                    "score": score,
                    "reasons": reasons,
                }
            )
    ranked.sort(key=lambda item: (int(item["score"]), -int(item["page"])), reverse=True)
    return ranked


def crop_image_asset(asset_path: Path, crop_spec: str, output_dir: Path, stem: str | None = None) -> tuple[Path, dict[str, object]]:
    x1, y1, x2, y2 = parse_crop_spec(crop_spec)
    with Image.open(asset_path) as image:
        width, height = image.size
        values = (x1, y1, x2, y2)
        if all(0 <= value <= 1 for value in values):
            left = int(round(x1 * width))
            top = int(round(y1 * height))
            right = int(round(x2 * width))
            bottom = int(round(y2 * height))
            crop_mode = "normalized"
        else:
            left, top, right, bottom = (int(round(value)) for value in values)
            crop_mode = "pixel"
        left = max(0, min(left, width - 1))
        top = max(0, min(top, height - 1))
        right = max(left + 1, min(right, width))
        bottom = max(top + 1, min(bottom, height))
        cropped = image.crop((left, top, right, bottom))
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"{stem or sanitize_stem(asset_path.stem)}-crop{asset_path.suffix.lower()}"
        cropped.save(target)
    return target, {
        "crop_mode": crop_mode,
        "crop_box_pixels": [left, top, right, bottom],
        "original_size_pixels": [width, height],
        "crop_spec_input": crop_spec,
    }


def build_candidate_preview(
    paths: Iterable[Path],
    note_prefix: str,
    page_hint_map: dict[int, dict[str, object]] | None = None,
) -> list[AssetCandidate]:
    preview = []
    for idx, path in enumerate(paths):
        page_number = parse_page_number_from_path(path)
        hint_note = ""
        hint_score = 0
        if page_number is not None and page_hint_map and page_number in page_hint_map:
            hint_score = int(page_hint_map[page_number]["score"])
            reason_text = ", ".join(page_hint_map[page_number]["reasons"])
            hint_note = f"; page_hint_score={hint_score}; page_hint_reasons={reason_text}"
        preview.append(
            AssetCandidate(
                path=str(path),
                score=max(1, 100 - idx + hint_score),
                note=f"{note_prefix}; size={path.stat().st_size} bytes{hint_note}",
                page=page_number,
            )
        )
    return preview


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect thesis figure assets from webpage, PDF, DOCX, or direct image sources.")
    parser.add_argument("--source", required=True, help="Local path or open URL to a webpage, PDF, DOCX, or image.")
    parser.add_argument("--output-dir", required=True, help="Directory for downloaded or extracted assets and metadata.")
    parser.add_argument("--caption", default="外部来源图片", help="Suggested Chinese figure caption.")
    parser.add_argument("--label", default="fig:external-source", help="Suggested LaTeX figure label.")
    parser.add_argument("--index", type=int, default=0, help="Candidate index after ranking, default 0.")
    parser.add_argument("--candidate", type=int, help="Alias for --index.")
    parser.add_argument("--name", help="Optional output asset stem.")
    parser.add_argument("--timeout", type=int, default=20, help="Network timeout in seconds.")
    parser.add_argument("--pattern", help="Optional regex to bias candidate selection for webpage sources.")
    parser.add_argument("--render", action="store_true", help="Render webpage sources with Playwright before extraction.")
    parser.add_argument("--page", type=int, help="Optional 1-based PDF page to limit extraction or rendering.")
    parser.add_argument("--max-pages", type=int, default=3, help="Maximum PDF pages to rasterize when fallback rendering is needed.")
    parser.add_argument("--crop", help="Optional crop region as x1,y1,x2,y2; values can be normalized 0-1 or absolute pixels.")
    parser.add_argument("--figure-number", help="Optional figure-number hint, such as '图3' or 'Figure 3', used to narrow PDF pages.")
    parser.add_argument("--caption-pattern", help="Optional regex used to search PDF page text for a target caption.")
    parser.add_argument("--list-only", action="store_true", help="List candidates without copying a selected asset.")
    parser.add_argument("--integration-mode", choices=[
        "structure-introduction",
        "workflow-bridge",
        "design-justification",
        "result-interpretation",
    ], help="Preferred figure-text integration mode.")
    parser.add_argument("--section-context", help="Optional Chinese section context used to draft the integration note.")
    args = parser.parse_args()

    source = args.source
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_index = args.candidate if args.candidate is not None else args.index

    downloaded_path: Path | None = None
    content_type: str | None = None

    if is_url(source):
        source_type = classify_source(source)
        if source_type in {"pdf", "docx", "image"}:
            downloaded_path, content_type = download_file(source, output_dir, args.name, args.timeout)
            source_type = classify_source(str(downloaded_path), content_type)
        else:
            temp_script = Path(__file__).with_name("web_figure_capture.py")
            cmd = [
                "python3",
                str(temp_script),
                "--url",
                source,
                "--output-dir",
                str(output_dir),
                "--caption",
                args.caption,
                "--label",
                args.label,
                "--timeout",
                str(args.timeout),
            ]
            if args.candidate is not None or args.index != 0:
                cmd.extend(["--index", str(candidate_index)])
            if args.name:
                cmd.extend(["--name", args.name])
            if args.pattern:
                cmd.extend(["--pattern", args.pattern])
            if args.render:
                cmd.append("--render")
            if args.list_only:
                cmd.append("--list-only")
            if args.integration_mode:
                cmd.extend(["--integration-mode", args.integration_mode])
            if args.section_context:
                cmd.extend(["--section-context", args.section_context])
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                detail = summarize_subprocess_error(result.stderr, result.stdout)
                raise RuntimeError(
                    "Webpage capture failed inside source intake. "
                    + detail
                )
            print(result.stdout.strip())
            return 0
    else:
        local_path = Path(source).expanduser().resolve()
        if not local_path.exists():
            raise FileNotFoundError(f"Source not found: {local_path}")
        source_type = classify_source(str(local_path))
        downloaded_path = local_path

    candidates: list[Path] = []
    note = ""
    page_hint_rankings: list[dict[str, object]] = []
    page_hint_map: dict[int, dict[str, object]] = {}
    crop_meta: dict[str, object] | None = None
    hint_requested = bool(args.figure_number or args.caption_pattern)

    if source_type == "image":
        assert downloaded_path is not None
        asset_path = downloaded_path if is_url(source) else copy_local_image(downloaded_path, output_dir, args.name)
        candidates = [asset_path]
        note = "Direct image source"
    elif source_type == "pdf":
        assert downloaded_path is not None
        page_count = get_pdf_page_count(downloaded_path)
        if args.page is not None and (args.page < 1 or args.page > page_count):
            raise RuntimeError(f"Requested --page {args.page} is outside the PDF page range 1-{page_count}.")
        if hint_requested:
            page_hint_rankings = rank_pdf_pages_by_hint(
                downloaded_path,
                page_count,
                figure_number=args.figure_number,
                caption_pattern=args.caption_pattern,
            )
            page_hint_map = {int(item["page"]): item for item in page_hint_rankings}
        if args.crop and not args.page and not page_hint_rankings:
            raise RuntimeError(
                "Precise PDF cropping requires either --page or a matching --figure-number / --caption-pattern hint."
            )
        if hint_requested and not args.page and not page_hint_rankings:
            if args.list_only:
                integration_mode = args.integration_mode or infer_integration_mode(args.section_context, args.caption)
                integration_note = build_integration_note(integration_mode, args.caption, args.section_context)
                payload = {
                    "source_input": source,
                    "source_type": source_type,
                    "source_file_path": str(downloaded_path),
                    "downloaded_content_type": content_type,
                    "candidate_count": 0,
                    "candidate_preview": [],
                    "selection_required": True,
                    "pdf_page_hints": [],
                    "requested_page": args.page,
                    "requested_crop": args.crop,
                    "requested_figure_number": args.figure_number,
                    "requested_caption_pattern": args.caption_pattern,
                    "hint_match_found": False,
                    "recommended_next_step": "Broaden --caption-pattern, provide --page, or inspect the PDF manually before retrying.",
                    "integration_mode": integration_mode,
                    "integration_note_zh": integration_note,
                    "integration_note_status": "draft-needs-local-adaptation",
                }
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0
            raise RuntimeError(
                "No PDF page matched the provided --figure-number / --caption-pattern hint. "
                "Re-run with --list-only, broaden the hint, or provide --page explicitly."
            )
        if args.crop or page_hint_rankings:
            render_dir = output_dir / "rendered_pdf_pages"
            if args.page:
                target_pages = [args.page]
                note = "Rasterized selected PDF page for precise region-based extraction"
            elif page_hint_rankings:
                target_pages = [int(item["page"]) for item in page_hint_rankings[: min(5, len(page_hint_rankings))]]
                note = "Rasterized PDF pages narrowed by figure-number or caption-text hints"
            else:
                target_pages = list(range(1, min(page_count, args.max_pages) + 1))
                note = "Rasterized PDF pages for region-based extraction"
            candidates = render_pdf_pages(downloaded_path, render_dir, pages=target_pages, max_pages=args.max_pages)
        else:
            extract_dir = output_dir / "extracted_from_pdf"
            candidates = extract_pdf_images(downloaded_path, extract_dir, page=args.page)
            note = "Extracted from PDF via pdfimages"
            if not candidates:
                render_dir = output_dir / "rendered_pdf_pages"
                candidates = render_pdf_pages(downloaded_path, render_dir, page=args.page, max_pages=args.max_pages)
                note = "Rasterized PDF page fallback via pdftoppm"
    elif source_type == "docx":
        assert downloaded_path is not None
        extract_dir = output_dir / "extracted_from_docx"
        candidates = extract_docx_images(downloaded_path, extract_dir)
        note = "Extracted from DOCX media bundle"
    elif source_type == "doc":
        raise RuntimeError("Legacy .doc is not supported directly. Convert it to .docx or PDF first.")
    else:
        raise RuntimeError(f"Unsupported source type: {source_type}")

    if not candidates:
        raise RuntimeError(f"No usable image assets found for source type: {source_type}")
    integration_mode = args.integration_mode or infer_integration_mode(args.section_context, args.caption)
    integration_note = build_integration_note(integration_mode, args.caption, args.section_context)
    preview = [asdict(item) for item in build_candidate_preview(candidates[:10], note, page_hint_map=page_hint_map)]
    if args.list_only:
        payload = {
            "source_input": source,
            "source_type": source_type,
            "source_file_path": str(downloaded_path) if downloaded_path else None,
            "downloaded_content_type": content_type,
            "candidate_count": len(candidates),
            "candidate_preview": preview,
            "selection_required": True,
            "pdf_page_hints": page_hint_rankings[:10],
            "requested_page": args.page,
            "requested_crop": args.crop,
            "requested_figure_number": args.figure_number,
            "requested_caption_pattern": args.caption_pattern,
            "integration_mode": integration_mode,
            "integration_note_zh": integration_note,
            "integration_note_status": "draft-needs-local-adaptation",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if candidate_index < 0 or candidate_index >= len(candidates):
        raise RuntimeError(f"Candidate index {candidate_index} is out of range for {len(candidates)} candidates.")

    chosen = candidates[candidate_index]
    final_asset = chosen
    if chosen.parent != output_dir:
        suffix = chosen.suffix.lower()
        target_name = f"{args.name or sanitize_stem(chosen.stem)}{suffix}"
        copied = output_dir / target_name
        shutil.copy2(chosen, copied)
        final_asset = copied
    if args.crop:
        final_asset, crop_meta = crop_image_asset(
            final_asset,
            args.crop,
            output_dir,
            stem=args.name or sanitize_stem(final_asset.stem),
        )

    meta = {
        "source_input": source,
        "source_type": source_type,
        "source_file_path": str(downloaded_path) if downloaded_path else None,
        "downloaded_content_type": content_type,
        "selected_asset_path": str(final_asset),
        "selected_asset_name": final_asset.name,
        "figure_caption_zh": args.caption,
        "figure_label": args.label,
        "asset_relpath_hint": final_asset.name,
        "requested_page": args.page,
        "requested_crop": args.crop,
        "requested_figure_number": args.figure_number,
        "requested_caption_pattern": args.caption_pattern,
        "selected_page_hint": parse_page_number_from_path(chosen),
        "pdf_page_hints": page_hint_rankings[:10],
        "crop_metadata": crop_meta,
        "integration_mode": integration_mode,
        "integration_note_zh": integration_note,
        "integration_note_status": "draft-needs-local-adaptation",
        "latex_snippet": build_latex_snippet(final_asset.name, args.caption, args.label),
        "citation_note_zh": "请在正文或图注中保留真实来源，并在参考文献中补入对应网页、论文或文档条目。",
        "candidate_preview": preview[:5],
    }

    metadata_path = output_dir / f"{final_asset.stem}.metadata.json"
    metadata_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
