"use client";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sanitizeUrl(url: string) {
  const trimmed = url.trim();
  if (/^(https?:|mailto:)/i.test(trimmed)) {
    return trimmed;
  }
  return "#";
}

function renderInline(markdown: string) {
  const escaped = escapeHtml(markdown);
  const codePlaceholders: string[] = [];

  let html = escaped.replace(/`([^`\n]+)`/g, (_, code: string) => {
    const placeholder = `@@CODE_${codePlaceholders.length}@@`;
    codePlaceholders.push(`<code>${code}</code>`);
    return placeholder;
  });

  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_, label: string, url: string) =>
      `<a href="${escapeHtml(sanitizeUrl(url))}" target="_blank" rel="noreferrer">${label}</a>`,
  );

  html = html.replace(/(^|[\s(])(https?:\/\/[^\s<]+)/g, (_, prefix: string, url: string) => {
    const safeUrl = sanitizeUrl(url);
    return `${prefix}<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noreferrer">${url}</a>`;
  });

  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  html = html.replace(/~~([^~]+)~~/g, "<del>$1</del>");
  html = html.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  html = html.replace(/(^|[^_])_([^_\n]+)_(?!_)/g, "$1<em>$2</em>");

  for (const [index, value] of codePlaceholders.entries()) {
    html = html.replace(`@@CODE_${index}@@`, value);
  }

  return html.replace(/\n/g, "<br />");
}

function renderTable(lines: string[]) {
  if (lines.length < 2) {
    return `<p>${renderInline(lines.join("\n"))}</p>`;
  }

  const cellsFromLine = (line: string) =>
    line
      .trim()
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((cell) => cell.trim());

  const header = cellsFromLine(lines[0]);
  const rows = lines.slice(2).map(cellsFromLine);

  const headerHtml = header.map((cell) => `<th>${renderInline(cell)}</th>`).join("");
  const rowsHtml = rows
    .map(
      (row) =>
        `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join("")}</tr>`,
    )
    .join("");

  return `<div class="markdown-table-wrap"><table><thead><tr>${headerHtml}</tr></thead><tbody>${rowsHtml}</tbody></table></div>`;
}

function renderBlocks(markdown: string) {
  const normalized = markdown.replace(/\r\n?/g, "\n");
  const lines = normalized.split("\n");
  const html: string[] = [];
  let index = 0;

  const isTableSeparator = (line: string) =>
    /^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$/.test(line);

  while (index < lines.length) {
    const line = lines[index];

    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fenceMatch = line.match(/^```([\w-]+)?\s*$/);
    if (fenceMatch) {
      const language = fenceMatch[1] ? ` language-${fenceMatch[1]}` : "";
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      html.push(
        `<pre><code class="${language.trim()}">${escapeHtml(codeLines.join("\n"))}</code></pre>`,
      );
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      html.push(`<h${level}>${renderInline(headingMatch[2])}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      html.push(`<blockquote>${renderBlocks(quoteLines.join("\n"))}</blockquote>`);
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const tableLines = [line, lines[index + 1]];
      index += 2;
      while (index < lines.length && lines[index].includes("|")) {
        tableLines.push(lines[index]);
        index += 1;
      }
      html.push(renderTable(tableLines));
      continue;
    }

    const unorderedMatch = line.match(/^[-*+]\s+(.*)$/);
    if (unorderedMatch) {
      const items: string[] = [];
      while (index < lines.length) {
        const current = lines[index];
        const itemMatch = current.match(/^[-*+]\s+(.*)$/);
        if (!itemMatch) {
          break;
        }
        items.push(itemMatch[1]);
        index += 1;
      }
      html.push(`<ul>${items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ul>`);
      continue;
    }

    const orderedMatch = line.match(/^\d+\.\s+(.*)$/);
    if (orderedMatch) {
      const items: string[] = [];
      while (index < lines.length) {
        const current = lines[index];
        const itemMatch = current.match(/^\d+\.\s+(.*)$/);
        if (!itemMatch) {
          break;
        }
        items.push(itemMatch[1]);
        index += 1;
      }
      html.push(`<ol>${items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ol>`);
      continue;
    }

    const paragraphLines: string[] = [line];
    index += 1;
    while (index < lines.length) {
      const current = lines[index];
      if (!current.trim()) {
        index += 1;
        break;
      }
      if (
        /^```/.test(current) ||
        /^(#{1,6})\s+/.test(current) ||
        /^>\s?/.test(current) ||
        /^[-*+]\s+/.test(current) ||
        /^\d+\.\s+/.test(current) ||
        (current.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1]))
      ) {
        break;
      }
      paragraphLines.push(current);
      index += 1;
    }
    html.push(`<p>${renderInline(paragraphLines.join("\n"))}</p>`);
  }

  return html.join("");
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  const html = renderBlocks(content || "");
  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}
