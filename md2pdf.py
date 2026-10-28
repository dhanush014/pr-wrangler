"""Render a Markdown file to a styled PDF via headless Chrome.

    uv run --with markdown python md2pdf.py INPUT.md OUTPUT.pdf
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 10.5pt;
       line-height: 1.5; color: #1f2328; }
h1 { font-size: 22pt; margin: 0 0 6pt; padding-bottom: 6pt; border-bottom: 2px solid #d0d7de; }
h2 { font-size: 15pt; margin: 22pt 0 8pt; padding-bottom: 4pt; border-bottom: 1px solid #d0d7de;
     break-after: avoid; }
h3 { font-size: 12pt; margin: 14pt 0 6pt; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
a { color: #0969da; text-decoration: none; }
code { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 8.8pt; background: #eff1f3;
       padding: 1px 4px; border-radius: 4px; }
pre { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 9px 11px;
      font-size: 8.4pt; line-height: 1.4; white-space: pre-wrap; word-break: break-word;
      break-inside: avoid; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0 12pt; font-size: 9.2pt;
        break-inside: auto; }
th, td { border: 1px solid #d0d7de; padding: 5px 7px; vertical-align: top; text-align: left; }
th { background: #f6f8fa; font-weight: 600; }
tr { break-inside: avoid; }
hr { border: none; border-top: 1px solid #d0d7de; margin: 16pt 0; }
img { max-width: 100%; border-radius: 8px; margin: 6pt 0; }
blockquote { margin: 0; padding: 0 12px; color: #57606a; border-left: 3px solid #d0d7de; }
"""


LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+\.)\s")


def normalize_lists(text: str) -> str:
    """GitHub-style lists -> Python-Markdown: blank line before a list, 4-space nesting."""
    out, in_code = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        if not in_code:
            m = LIST_ITEM.match(line)
            if m:
                indent = len(m.group(1))
                if indent:
                    line = " " * (4 * ((indent + 1) // 2)) + line.lstrip()
                prev = out[-1] if out else ""
                if prev.strip() and not LIST_ITEM.match(prev) and not prev.startswith(" "):
                    out.append("")
        out.append(line)
    return "\n".join(out)


def main(src: str, out: str):
    text = normalize_lists(Path(src).read_text())
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    base = Path(src).resolve().parent.as_uri() + "/"  # so relative image paths resolve next to the .md
    html = f"<!doctype html><html><head><meta charset='utf-8'><base href='{base}'><style>{CSS}</style></head><body>{body}</body></html>"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "doc.html"
        page.write_text(html)
        subprocess.run([
            CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={Path(out).resolve()}", page.as_uri(),
        ], check=True, capture_output=True)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
