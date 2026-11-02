"""Render MAJI_Final_Report.md to print-ready HTML."""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).with_name("MAJI_Final_Report.md")
OUT = Path(__file__).with_name("MAJI_Final_Report.html")

CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
html, body { margin: 0; }
body {
  font-family: "Palatino Linotype", Palatino, "Times New Roman", serif;
  font-size: 10.6pt;
  line-height: 1.36;
  color: #111;
}
h1 { font-size: 18pt; line-height: 1.2; margin: 0 0 8pt; }
h2 { font-size: 13.5pt; margin: 16pt 0 6pt; page-break-after: avoid; }
h3 { font-size: 12pt; margin: 12pt 0 4pt; page-break-after: avoid; }
p, li { margin: 0 0 6pt; }
ul, ol { margin: 0 0 8pt; padding-left: 18pt; }
strong { font-weight: 700; }
em { font-style: italic; }
hr { border: 0; border-top: 1px solid #bbb; margin: 12pt 0; }
code, pre { font-family: Consolas, "Courier New", monospace; font-size: 9pt; }
pre {
  background: #f4f4f4;
  border: 1px solid #ddd;
  padding: 8pt;
  white-space: pre-wrap;
  page-break-inside: avoid;
}
table {
  border-collapse: collapse;
  width: 100%;
  font-size: 9.5pt;
  margin: 0 0 10pt;
  page-break-inside: avoid;
}
th, td { border: 1px solid #ccc; padding: 3pt 5pt; text-align: left; vertical-align: top; }
th { background: #f0f0f0; }
img {
  max-width: 100%;
  max-height: 92mm;
  display: block;
  margin: 4pt auto 2pt;
  page-break-inside: avoid;
}
.fig { font-size: 10pt; color: #333; margin: 0 0 10pt; }
.cover p { margin: 2pt 0; }
"""


def inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


def convert(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    in_code = False
    code: list[str] = []
    table: list[str] = []
    list_kind = None

    def flush_list():
        nonlocal list_kind
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    def flush_table():
        nonlocal table
        if not table:
            return
        rows = [r.strip().strip("|") for r in table if not re.match(r"^\s*\|?\s*[:\-]+", r)]
        html_rows = []
        for n, row in enumerate(rows):
            cells = [inline(c.strip()) for c in row.split("|")]
            tag = "th" if n == 0 else "td"
            html_rows.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
        out.append("<table>" + "".join(html_rows) + "</table>")
        table = []

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush_list()
            flush_table()
            if in_code:
                out.append("<pre>" + html.escape("\n".join(code)) + "</pre>")
                code = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code.append(line)
            i += 1
            continue
        if line.startswith("|"):
            flush_list()
            table.append(line)
            i += 1
            continue
        flush_table()
        if re.match(r"^!\[[^\]]*\]\(([^)]+)\)", line):
            flush_list()
            m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)", line)
            src = m.group(2)
            if src.startswith("../"):
                src = (ROOT / src[3:]).as_uri()
            out.append(f'<img src="{src}" alt="{html.escape(m.group(1))}">')
            i += 1
            continue
        if line.startswith("# "):
            flush_list()
            out.append(f'<div class="cover"><h1>{inline(line[2:])}</h1>')
            i += 1
            continue
        if line.startswith("## "):
            flush_list()
            if out and out[-1].startswith('<div class="cover">'):
                out.append("</div>")
            out.append(f"<h2>{inline(line[3:])}</h2>")
            i += 1
            continue
        if line.startswith("### "):
            flush_list()
            out.append(f"<h3>{inline(line[4:])}</h3>")
            i += 1
            continue
        if line.strip() == "---":
            flush_list()
            out.append("<hr>")
            i += 1
            continue
        if re.match(r"^\d+\.\s+", line):
            if list_kind != "ol":
                flush_list()
                out.append("<ol>")
                list_kind = "ol"
            out.append(f"<li>{inline(re.sub(r'^\d+\.\s+', '', line))}</li>")
            i += 1
            continue
        if re.match(r"^[-*]\s+", line):
            if list_kind != "ul":
                flush_list()
                out.append("<ul>")
                list_kind = "ul"
            out.append(f"<li>{inline(re.sub(r'^[-*]\s+', '', line))}</li>")
            i += 1
            continue
        flush_list()
        if line.strip() == "":
            i += 1
            continue
        cls = ' class="fig"' if line.startswith("**Figure") else ""
        out.append(f"<p{cls}>{inline(line)}</p>")
        i += 1
    flush_list()
    flush_table()
    if in_code:
        out.append("<pre>" + html.escape("\n".join(code)) + "</pre>")
    return "\n".join(out)


def main() -> None:
    body = convert(SRC.read_text(encoding="utf-8"))
    OUT.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>M.A.J.I Final Report</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>",
        encoding="utf-8",
    )
    print("wrote", OUT)


if __name__ == "__main__":
    main()
