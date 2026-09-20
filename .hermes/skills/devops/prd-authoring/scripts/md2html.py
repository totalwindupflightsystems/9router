#!/usr/bin/env python3
"""Render markdown PRDs/reports as self-contained, phone-friendly dark HTML.

Usage: python3 md2html.py <file.md | directory> [...]
Writes <name>.html next to each markdown file.
Stdlib only: headings, paragraphs, bullet/ordered lists, pipe tables, fenced
code, inline code/bold/italic, horizontal rules.
"""
import html
import re
import sys
from pathlib import Path

TPL = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#0f1115;--fg:#d7dae0;--mut:#8b93a1;--acc:#5eb0ef;--card:#161a22}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);
font:17px/1.65 -apple-system,'Segoe UI',Roboto,sans-serif;padding:1.1rem;max-width:46rem;margin-inline:auto}}
h1{{font-size:1.45rem;line-height:1.3;color:#fff;margin:.2rem 0 .6rem}}
h2{{font-size:1.15rem;color:var(--acc);border-bottom:1px solid #2a3140;padding-bottom:.3rem;margin:1.6rem 0 .5rem}}
h3{{font-size:1.02rem;color:#fff;margin:1.2rem 0 .3rem}}
p{{margin:.55rem 0}} code{{background:var(--card);border:1px solid #2a3140;border-radius:5px;
padding:.08em .35em;font-size:.86em;font-family:ui-monospace,Menlo,monospace;color:#9ecbff}}
pre{{background:var(--card);border:1px solid #2a3140;border-radius:8px;padding:.8rem;overflow-x:auto}}
pre code{{border:none;background:none;padding:0;color:#c9e2a8}}
table{{border-collapse:collapse;width:100%;font-size:.92rem;margin:.6rem 0}}
th,td{{text-align:left;padding:.45rem;border-bottom:1px solid #2a3140;vertical-align:top}}
th{{color:var(--mut)}} a{{color:var(--acc)}}
ul,ol{{margin:.4rem 0 .8rem;padding-left:1.3rem}} li{{margin:.3rem 0}}
hr{{border:none;border-top:1px solid #2a3140;margin:1.4rem 0}}
strong{{color:#fff}} .tag{{color:var(--mut);font-size:.85rem}}
</style></head><body>
{body}
</body></html>"""


def inline(text):
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def convert(md):
    out, in_code, list_open, in_table = [], False, None, False

    def close_list():
        nonlocal list_open
        if list_open:
            out.append("</%s>" % list_open)
            list_open = None

    def close_table():
        nonlocal in_table
        if in_table:
            out.append("</table>")
            in_table = False

    for line in md.splitlines():
        if line.strip().startswith("```"):
            close_list(); close_table()
            out.append("<pre><code>" if not in_code else "</code></pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        s = line.strip()
        if not s:
            close_list(); close_table(); continue
        if re.match(r"^---+$", s):
            close_list(); close_table(); out.append("<hr>"); continue
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if not in_table:
                close_list(); out.append("<table>"); in_table = True
            tag = "th" if "<tr>" not in out[-1:] else "td"
            out.append("<tr>" + "".join("<%s>%s</%s>" % (tag, inline(c), tag) for c in cells) + "</tr>")
            continue
        close_table()
        if s.startswith("### "):
            close_list(); out.append("<h3>%s</h3>" % inline(s[4:]))
        elif s.startswith("## "):
            close_list(); out.append("<h2>%s</h2>" % inline(s[3:]))
        elif s.startswith("# "):
            close_list(); out.append("<h1>%s</h1>" % inline(s[2:]))
        elif re.match(r"^\d+\. ", s):
            if list_open != "ol":
                close_list(); out.append("<ol>"); list_open = "ol"
            out.append("<li>%s</li>" % inline(re.sub(r"^\d+\. ", "", s)))
        elif s.startswith(("- ", "* ")):
            if list_open != "ul":
                close_list(); out.append("<ul>"); list_open = "ul"
            out.append("<li>%s</li>" % inline(s[2:]))
        else:
            close_list(); out.append("<p>%s</p>" % inline(s))
    close_list(); close_table()
    return "\n".join(out)


def render(path):
    title = path.stem.replace("-", " ").title()
    out = path.with_suffix(".html")
    out.write_text(TPL.format(title=title, body=convert(path.read_text())))
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    targets = []
    for arg in argv:
        p = Path(arg)
        targets.extend(sorted(p.glob("*.md")) if p.is_dir() else [p])
    for t in targets:
        if t.is_file():
            o = render(t)
            print("%s -> %s (%d bytes)" % (t, o, o.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
