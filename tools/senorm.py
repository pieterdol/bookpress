#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Normalise pandoc's Markdown from a Standard Ebooks EPUB into something
novel.tex can typeset.

Standard Ebooks marks up far more structure than a printed page needs, and
pandoc faithfully carries all of it across: section anchors, semantic spans,
`<hgroup>` wrappers, epub:type divs. None of it survives contact with LaTeX
usefully, and hand-deleting 31 anchors and 29 hgroups is not a good use of an
evening.

The two structural jobs:

  hgroup collapse   SE puts the chapter ordinal in the heading and the chapter
                    title in a paragraph beneath it, inside an <hgroup>. We
                    want one heading carrying the title, and memoir supplies
                    "Chapter 7" itself, so the ordinal is dropped.

  level promotion   Books arrive as h2 and chapters as h3, because SE reserves
                    h1 for the whole work. Promoting both by one gives
                    part=#, chapter=##, which is what --top-level-division=part
                    expects.

Idempotent: running it twice changes nothing the second time.

    ./tools/senorm.py source/book.md            # in place, with a .orig backup
    ./tools/senorm.py source/book.md -o out.md
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


def collapse_hgroups(text: str) -> tuple[str, int]:
    """<hgroup> + heading + title paragraph -> one heading, promoted a level."""
    pat = re.compile(
        r"<hgroup[^>]*>\s*\n+"
        r"(?P<hashes>\#{2,6})[ \t]+(?P<ordinal>[^\n]*?)[ \t]*\n"
        r"(?P<rest>.*?)"
        r"</hgroup>",
        re.S,
    )

    def sub(m: re.Match) -> str:
        level = max(1, len(m.group("hashes")) - 1)
        body = [ln.strip() for ln in m.group("rest").split("\n") if ln.strip()]
        title = body[0] if body else m.group("ordinal").strip()
        return f"{'#' * level} {title}\n"

    return pat.subn(sub, text)


def md_to_tex(s: str) -> str:
    """Inline Markdown -> LaTeX, for text going into a raw LaTeX block.

    Pandoc does not look inside a raw block, so *emphasis* written there would
    reach the page as literal asterisks. Only the few inline forms that turn up
    in a dedication or an epigraph are handled.
    """
    s = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", s)
    s = re.sub(r"\*([^*]+)\*", r"\\emph{\1}", s)
    s = re.sub(r"_([^_]+)_", r"\\emph{\1}", s)
    return s


def convert_divs(text: str) -> str:
    """Dedication and epigraph become LaTeX; every other div is unwrapped.

    These two are real frontmatter pages in a printed book, not sections, so
    they need their own placement rather than a heading in the flow.
    """
    pat = re.compile(r"^::: *\{(?P<attrs>[^}]*)\}\n(?P<body>.*?)^:::[ \t]*$", re.M | re.S)

    def sub(m: re.Match) -> str:
        attrs, body = m.group("attrs"), m.group("body").strip()
        if "dedication" in attrs:
            lines = [ln.strip().rstrip("\\") for ln in body.split("\n") if ln.strip()]
            return "```{=latex}\n\\bpdedication{%s}\n```\n" % md_to_tex(
                r" \\ ".join(lines)
            )
        if "epigraph" in attrs:
            quote = [
                ln.lstrip("> ").strip()
                for ln in body.split("\n")
                if ln.strip().startswith(">")
            ]
            quote = [q for q in quote if q]
            cite = ""
            if quote and ("Kepler" in quote[-1] or "," in quote[-1] and len(quote) > 1):
                cite = quote.pop()
            return "```{=latex}\n\\bpepigraph{%s}{%s}\n```\n" % (
                md_to_tex(" ".join(quote).strip()),
                md_to_tex(cite.strip()),
            )
        return body + "\n"

    return pat.sub(sub, text)


def clean(text: str) -> tuple[str, dict[str, int]]:
    stats: dict[str, int] = {}

    # The EPUB's own cover. We make our own.
    text, n = re.subn(r"^!\[[^\]]*\]\([^)]*\)[ \t]*\n", "", text, flags=re.M)
    stats["cover images removed"] = n

    # SE brackets its ellipses with U+FEFF; there is no glyph for it and
    # LuaTeX passes it through as a missing character.
    text, n = re.subn("\ufeff", "", text)
    stats["zero-width spaces removed"] = n

    text = convert_divs(text)

    text, n = collapse_hgroups(text)
    stats["hgroups collapsed"] = n

    # Raw HTML pandoc could not map. <cite> is the only one here, and italics
    # is what a printed attribution wants anyway.
    text, n = re.subn(r"`</?cite>`\{=html\}", "", text)
    stats["raw html stripped"] = n

    # Semantic spans: [Mr.]{.abbr}, [I]{.z3998:roman}, and the empty []{#anchor}
    # section markers, which are the same shape with no text.
    text, n = re.subn(r"\[([^\[\]]*)\]\{[^{}]*\}", r"\1", text)
    stats["spans unwrapped"] = n

    # Leftover attribute blocks on headings, e.g. "## Title {#id}".
    text, n = re.subn(r"[ \t]*\{#[^}]*\}[ \t]*$", "", text, flags=re.M)
    stats["heading ids removed"] = n

    text, n = re.subn(r"\n{3,}", "\n\n", text)
    stats["blank runs collapsed"] = n

    return text.strip() + "\n", stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("markdown")
    ap.add_argument("-o", "--out", help="default: rewrite in place, keeping a .orig")
    args = ap.parse_args()

    src = Path(args.markdown)
    if not src.is_file():
        raise SystemExit(f"no such file: {src}")
    text = src.read_text()

    out_text, stats = clean(text)

    dst = Path(args.out) if args.out else src
    if not args.out:
        backup = src.with_suffix(src.suffix + ".orig")
        if not backup.exists():
            shutil.copy2(src, backup)
            print(f"kept the original at {backup}")
    dst.write_text(out_text)

    print(f"wrote {dst}")
    for k, v in stats.items():
        print(f"  {k:24s} {v}")

    parts = len(re.findall(r"^# [^#]", out_text, re.M))
    chapters = len(re.findall(r"^## [^#]", out_text, re.M))
    print(f"  {'parts (#)':24s} {parts}")
    print(f"  {'chapters (##)':24s} {chapters}")
    # {=latex} is ours — the raw blocks holding the dedication and epigraph.
    leftovers = [
        s for s in re.findall(r"<[a-z/][^>]*>|\{[.=#][^}]*\}", out_text)
        if s != "{=latex}"
    ]
    if leftovers:
        seen = sorted(set(leftovers))[:6]
        print(f"  warning: {len(leftovers)} markup leftovers, e.g. {seen}")


if __name__ == "__main__":
    main()
