"""Turn a ``slides.md`` plus its ``figures/`` into one self-contained HTML deck.

    python scripts/build_deck.py slides/exp004_real_data_transfer

Images are inlined as base64 so the file opens anywhere with no server and no
adjacent directory. That is why decks are git-ignored: they are multi-MB and
fully derived.

Until now they were not derived -- ``slides/exp003_.../deck.html`` was authored by
hand alongside ``slides.md``, so the two could drift and ``.gitignore``'s claim
that decks regenerate from the figure script was simply false. One source, one
build step, and a changed figure cannot leave a stale deck behind.

**The Markdown subset is deliberately small and strict.** These slides are written
in this repository for this tool, so the converter supports exactly what they use
and **raises** on anything else. Silently dropping an unrecognised construct is
the same failure as the stale deck: content that exists in the source and not in
the artefact, with nothing to say so. No Markdown dependency -- the subset is
small enough that a library would be the larger commitment (CLAUDE.md section 4).
"""

from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
import sys
from pathlib import Path

CSS = """
:root{
  --paper:#eef2f3; --slide:#ffffff; --sunken:#e9eff0; --ink:#101a1f; --slate:#55676e;
  --faint:#81949a; --rule:#d3dedf; --firm:#b6c6c8;
  --cyan:#0d6e7d; --cyan-soft:#d8ecef; --verm:#b03f2a; --verm-soft:#f7ddd6; --amber:#a8712f;
  --shadow:0 1px 2px rgba(16,26,31,.07),0 14px 40px -18px rgba(16,26,31,.28);
  --serif:Georgia,"Iowan Old Style","Palatino Linotype",Palatino,serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#0a1114; --slide:#131e22; --sunken:#0f191d; --ink:#e6eeef; --slate:#9cb0b6;
  --faint:#718589; --rule:#26363b; --firm:#3a4e54;
  --cyan:#5ec4d4; --cyan-soft:#12333a; --verm:#e8836a; --verm-soft:#3a201a; --amber:#d9a457;
  --shadow:0 1px 2px rgba(0,0,0,.5),0 14px 40px -18px rgba(0,0,0,.7);
}}
:root[data-theme="dark"]{
  --paper:#0a1114; --slide:#131e22; --sunken:#0f191d; --ink:#e6eeef; --slate:#9cb0b6;
  --faint:#718589; --rule:#26363b; --firm:#3a4e54;
  --cyan:#5ec4d4; --cyan-soft:#12333a; --verm:#e8836a; --verm-soft:#3a201a; --amber:#d9a457;
  --shadow:0 1px 2px rgba(0,0,0,.5),0 14px 40px -18px rgba(0,0,0,.7);
}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);margin:0;
  padding:2rem 1.25rem 5rem;line-height:1.55;-webkit-font-smoothing:antialiased}
.deck{max-width:1180px;margin:0 auto;display:flex;flex-direction:column;gap:2rem}
.deckhead{display:flex;flex-direction:column;gap:.6rem;padding:1rem .25rem 0}
.deckhead h1{font-family:var(--serif);font-weight:400;font-size:clamp(1.6rem,4vw,2.3rem);
  margin:0;letter-spacing:-.015em;text-wrap:balance}
.deckhead p{margin:0;color:var(--slate);max-width:70ch;font-size:.95rem}
.slide{background:var(--slide);border:1px solid var(--rule);border-radius:4px;
  box-shadow:var(--shadow);padding:2rem 2.2rem 2.4rem;display:flex;
  flex-direction:column;gap:1.1rem}
.slide-num{font-family:var(--mono);font-size:.7rem;letter-spacing:.16em;
  text-transform:uppercase;color:var(--cyan);display:flex;gap:1rem;align-items:baseline}
.slide-num .of{color:var(--faint)}
h2{font-family:var(--serif);font-weight:400;font-size:clamp(1.35rem,3vw,1.95rem);
  line-height:1.2;letter-spacing:-.012em;margin:0;text-wrap:balance}
h3{font-family:var(--sans);font-size:.78rem;font-weight:700;letter-spacing:.11em;
  text-transform:uppercase;color:var(--slate);margin:.6rem 0 -.4rem}
p{margin:0;max-width:78ch}
ul,ol{margin:0;padding-left:1.15rem;display:flex;flex-direction:column;gap:.35rem;max-width:78ch}
strong{font-weight:650}
code{font-family:var(--mono);font-size:.86em;background:var(--sunken);
  padding:.1em .32em;border-radius:3px}
pre{margin:0;background:var(--sunken);border:1px solid var(--rule);border-radius:4px;
  padding:.9rem 1.1rem;overflow-x:auto}
pre code{background:none;padding:0;font-size:.8rem;line-height:1.5}
a{color:var(--cyan);text-decoration:none;border-bottom:1px solid var(--firm)}
blockquote{margin:0;padding:.85rem 1.1rem;background:var(--cyan-soft);
  border-left:3px solid var(--cyan);border-radius:0 4px 4px 0;max-width:78ch}
blockquote p{font-size:1.02rem}
hr{border:0;border-top:1px solid var(--rule);margin:.4rem 0;width:100%}
.scroll{overflow-x:auto;max-width:100%}
table{border-collapse:collapse;font-size:.88rem;font-variant-numeric:tabular-nums;
  min-width:100%}
th{text-align:left;font-weight:650;font-size:.72rem;letter-spacing:.08em;
  text-transform:uppercase;color:var(--slate);border-bottom:1px solid var(--firm);
  padding:.45rem .8rem .45rem 0;white-space:nowrap}
td{padding:.4rem .8rem .4rem 0;border-bottom:1px solid var(--rule);vertical-align:top}
tr:last-child td{border-bottom:0}
figure{margin:0;display:flex;flex-direction:column;gap:.5rem}
figure img{width:100%;height:auto;display:block;border:1px solid var(--rule);
  border-radius:3px;background:#fff}
figcaption{font-size:.78rem;color:var(--faint);font-family:var(--mono)}
:focus-visible{outline:2px solid var(--cyan);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

INLINE = re.compile(
    r"(?P<code>`[^`]+`)"
    r"|(?P<img>!\[(?P<alt>[^\]]*)\]\((?P<isrc>[^)]+)\))"
    r"|(?P<link>\[(?P<text>[^\]]+)\]\((?P<href>[^)]+)\))"
    r"|(?P<bold>\*\*(?P<btext>[^*]+)\*\*)"
    r"|(?P<em>\*(?P<etext>[^*]+)\*)"
)


class DeckError(SystemExit):
    """A slide source this converter refuses to guess at."""


def inline(text: str, assets: dict[str, str]) -> str:
    """Render the inline subset: code, images, links, bold, italic."""
    out, pos = [], 0
    for m in INLINE.finditer(text):
        out.append(html.escape(text[pos : m.start()]))
        if m.group("code"):
            out.append(f"<code>{html.escape(m.group('code')[1:-1])}</code>")
        elif m.group("img"):
            src = assets.get(m.group("isrc"), m.group("isrc"))
            out.append(f'<img src="{src}" alt="{html.escape(m.group("alt"))}">')
        elif m.group("link"):
            href = html.escape(m.group("href"), quote=True)
            out.append(f'<a href="{href}">{html.escape(m.group("text"))}</a>')
        elif m.group("bold"):
            out.append(f"<strong>{html.escape(m.group('btext'))}</strong>")
        else:
            out.append(f"<em>{html.escape(m.group('etext'))}</em>")
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def _table(rows: list[str], assets: dict[str, str]) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, body = cells[0], cells[2:]  # cells[1] is the alignment rule
    thead = "".join(f"<th>{inline(c, assets)}</th>" for c in head)
    trs = "".join(
        "<tr>" + "".join(f"<td>{inline(c, assets)}</td>" for c in row) + "</tr>" for row in body
    )
    return (
        f'<div class="scroll"><table><thead><tr>{thead}</tr></thead>'
        f"<tbody>{trs}</tbody></table></div>"
    )


def blocks(lines: list[str], assets: dict[str, str], where: str) -> str:
    """Convert a slide body. Raises on any construct outside the subset."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
        elif stripped.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            if j >= len(lines):
                raise DeckError(f"{where}: unterminated code fence at line {i + 1}")
            body = html.escape("\n".join(lines[i + 1 : j]))
            out.append(f"<pre><code>{body}</code></pre>")
            i = j + 1
        elif stripped.startswith("### "):
            out.append(f"<h3>{inline(stripped[4:], assets)}</h3>")
            i += 1
        elif stripped in ("---", "***", "___"):
            out.append("<hr>")
            i += 1
        elif stripped.startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            if j - i < 2:
                raise DeckError(f"{where}: table at line {i + 1} has no alignment row")
            out.append(_table(lines[i:j], assets))
            i = j
        elif stripped.startswith(("- ", "* ")):
            items, j = [], i
            while j < len(lines) and lines[j].strip().startswith(("- ", "* ")):
                item = [lines[j].strip()[2:]]
                j += 1
                while j < len(lines) and lines[j].startswith(("  ", "\t")) and lines[j].strip():
                    item.append(lines[j].strip())
                    j += 1
                items.append(" ".join(item))
            body = "".join(f"<li>{inline(t, assets)}</li>" for t in items)
            out.append(f"<ul>{body}</ul>")
            i = j
        elif re.match(r"^\d+\. ", stripped):
            items, j = [], i
            while j < len(lines) and re.match(r"^\d+\. ", lines[j].strip()):
                item = [re.sub(r"^\d+\. ", "", lines[j].strip())]
                j += 1
                while j < len(lines) and lines[j].startswith(("  ", "\t")) and lines[j].strip():
                    item.append(lines[j].strip())
                    j += 1
                items.append(" ".join(item))
            body = "".join(f"<li>{inline(t, assets)}</li>" for t in items)
            out.append(f"<ol>{body}</ol>")
            i = j
        elif stripped.startswith("> "):
            quoted, j = [], i
            while j < len(lines) and lines[j].strip().startswith(">"):
                quoted.append(lines[j].strip().lstrip(">").strip())
                j += 1
            text = " ".join(x for x in quoted if x)
            out.append(f"<blockquote><p>{inline(text, assets)}</p></blockquote>")
            i = j
        elif stripped.startswith("#"):
            raise DeckError(
                f"{where}: unexpected heading at line {i + 1}: {stripped!r}\n"
                "Slides are delimited by '## Slide N', and '###' is a section label. "
                "A deeper heading has no rendering here, and guessing one would put "
                "content on the page in a shape nobody chose."
            )
        else:
            para, j = [], i
            while j < len(lines) and lines[j].strip() and not _starts_block(lines[j]):
                para.append(lines[j].strip())
                j += 1
            text = " ".join(para)
            # A paragraph that is only an image becomes a figure, so the caption
            # (the alt text) renders under it rather than being invisible.
            solo = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", text)
            if solo:
                src = assets.get(solo.group(2), solo.group(2))
                cap = html.escape(solo.group(1))
                out.append(
                    f'<figure><img src="{src}" alt="{cap}">'
                    + (f"<figcaption>{cap}</figcaption>" if cap else "")
                    + "</figure>"
                )
            else:
                out.append(f"<p>{inline(text, assets)}</p>")
            i = j
    return "\n".join(out)


def _starts_block(line: str) -> bool:
    s = line.strip()
    return bool(
        s.startswith(("|", "- ", "* ", "> ", "#", "```"))
        or s in ("---", "***", "___")
        or re.match(r"^\d+\. ", s)
    )


def embed(figures: Path) -> dict[str, str]:
    """Map every relative image path used in slides.md to a data: URI."""
    assets: dict[str, str] = {}
    if not figures.is_dir():
        return assets
    for path in sorted(figures.iterdir()):
        mime, _ = mimetypes.guess_type(path.name)
        if not mime or not mime.startswith("image/"):
            continue
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
        uri = f"data:{mime};base64,{payload}"
        assets[f"figures/{path.name}"] = uri
        assets[f"./figures/{path.name}"] = uri
    return assets


def build(directory: Path) -> Path:
    source = directory / "slides.md"
    if not source.exists():
        raise DeckError(f"missing {source}")
    assets = embed(directory / "figures")
    text = source.read_text()

    # Everything before the first '## ' is the deck header; each '## ' starts a slide.
    parts = re.split(r"^## ", text, flags=re.M)
    header_lines = parts[0].strip().splitlines()
    title = header_lines[0].lstrip("# ").strip() if header_lines else directory.name
    preamble = blocks(header_lines[1:], assets, f"{source}:header")

    # A section headed "Slide N — Title" is a numbered slide; anything else is an
    # unnumbered section (appendices, caveats, sources). Taking the number from
    # the source rather than from position means the deck cannot disagree with the
    # Markdown about which slide is which, and an appendix does not silently
    # become "slide 5 of 5".
    chunks = []
    for chunk in parts[1:]:
        chunk_lines = chunk.rstrip().splitlines()
        heading = chunk_lines[0].strip()
        # Dashes by escape: ruff RUF001 flags en/em dash literals as ambiguous.
        m = re.match("Slide\\s+(\\d+)\\s*[-\u2013\u2014:]\\s*(.*)", heading)
        chunks.append(
            (m.group(1) if m else None, m.group(2) if m else heading, chunk_lines[1:])
        )

    total = sum(1 for number, _, _ in chunks if number)
    slides = []
    for number, title, body_lines in chunks:
        label = f"slide {number}" if number else title
        body = blocks(body_lines, assets, f"{source}:{label}")
        num = (
            f'<div class="slide-num"><span class="n">Slide {number}</span>'
            f'<span class="of">of {total}</span></div>'
            if number
            else ""
        )
        slides.append(
            f'<section class="slide">{num}<h2>{inline(title, assets)}</h2>{body}</section>'
        )
    if not slides:
        raise DeckError(f"{source} has no '## ' slide headings")

    used = {m.group(1) for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text)}
    missing = sorted(u for u in used if u not in assets and not u.startswith(("http", "data:")))
    if missing:
        raise DeckError(
            f"{source} references images that are not in {directory / 'figures'}: {missing}\n"
            "Run the figure script for this deck first."
        )

    doc = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        f'<main class="deck">\n<header class="deckhead"><h1>{html.escape(title)}</h1>'
        f"{preamble}</header>\n" + "\n".join(slides) + "\n</main>\n</body>\n</html>\n"
    )
    out = directory / "deck.html"
    out.write_text(doc)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("directories", nargs="+", type=Path, help="a slides/<deck>/ directory")
    args = ap.parse_args(argv)
    for directory in args.directories:
        out = build(directory)
        print(f"wrote {out}  ({out.stat().st_size >> 10} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
