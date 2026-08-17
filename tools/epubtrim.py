#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Drop sections from an EPUB before it reaches pandoc.

A Standard Ebooks edition carries material that belongs to the ebook rather
than to the book: a title page, the Standard Ebooks imprint, a colophon about
the digital edition, and the CC0 uncopyright notice. Printed, they are wrong —
novel.tex sets its own title page and colophon — so they have to come out.

Doing that in the Markdown afterwards means finding section boundaries in a
20,000-line file by eye. Doing it here means editing the spine, which is a list
of about thirty entries and unambiguous.

Sections are matched by filename stem *or* by epub:type, so `--drop colophon`
works whatever the file happens to be called.

    ./tools/epubtrim.py book.epub --list
    ./tools/epubtrim.py book.epub --drop-boilerplate -o trimmed.epub
    ./tools/epubtrim.py book.epub --drop colophon,epigraph -o trimmed.epub
"""

from __future__ import annotations

import argparse
import re
import shutil
import zipfile
from pathlib import Path

# Non-authorial matter in a Standard Ebooks edition. Dedication and epigraph
# are deliberately NOT here: those are the author's, and belong in the book.
BOILERPLATE = ["titlepage", "imprint", "halftitlepage", "colophon", "uncopyright"]


def opf_path(z: zipfile.ZipFile) -> str:
    container = z.read("META-INF/container.xml").decode()
    m = re.search(r'full-path="([^"]+)"', container)
    if not m:
        raise SystemExit("cannot find the OPF: no full-path in container.xml")
    return m.group(1)


def manifest(opf_xml: str) -> dict[str, str]:
    """id -> href, tolerant of attribute order."""
    out: dict[str, str] = {}
    for tag in re.findall(r"<item\b[^>]*/?>", opf_xml):
        i = re.search(r'\bid="([^"]+)"', tag)
        h = re.search(r'\bhref="([^"]+)"', tag)
        if i and h:
            out[i.group(1)] = h.group(1)
    return out


def epub_types(z: zipfile.ZipFile, path: str) -> set[str]:
    try:
        s = z.read(path).decode("utf-8", "replace")
    except KeyError:
        return set()
    toks: set[str] = set()
    for v in re.findall(r'epub:type="([^"]+)"', s[:4000]):
        toks.update(v.split())
    return {t.split(":")[-1] for t in toks}


def spine_entries(z: zipfile.ZipFile):
    opf = opf_path(z)
    base = str(Path(opf).parent)
    xml = z.read(opf).decode()
    man = manifest(xml)
    ids = re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', xml)
    rows = []
    for idref in ids:
        href = man.get(idref, "")
        full = f"{base}/{href}" if base not in ("", ".") else href
        rows.append({
            "idref": idref,
            "href": href,
            "full": full,
            "stem": Path(href).stem,
            "types": epub_types(z, full),
        })
    return opf, xml, rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("epub")
    ap.add_argument("--list", action="store_true", help="show the spine and exit")
    ap.add_argument("--drop", default="", help="comma-separated stems or epub:types")
    ap.add_argument("--drop-boilerplate", action="store_true",
                    help=f"drop {', '.join(BOILERPLATE)}")
    ap.add_argument("-o", "--out", help="output EPUB (default: <name>-trimmed.epub)")
    args = ap.parse_args()

    src = Path(args.epub).expanduser()
    if not src.is_file():
        raise SystemExit(f"no such file: {src}")

    with zipfile.ZipFile(src) as z:
        opf, xml, rows = spine_entries(z)

    if args.list:
        print(f"{len(rows)} spine entries in {src.name}\n")
        print(f"{'#':>3}  {'stem':24s} {'epub:type'}")
        for n, r in enumerate(rows, 1):
            mark = "  <- boilerplate" if (
                r["stem"] in BOILERPLATE or r["types"] & set(BOILERPLATE)
            ) else ""
            print(f"{n:3d}  {r['stem']:24s} {','.join(sorted(r['types'])) or '-'}{mark}")
        return

    wanted = {s.strip() for s in args.drop.split(",") if s.strip()}
    if args.drop_boilerplate:
        wanted |= set(BOILERPLATE)
    if not wanted:
        raise SystemExit("nothing to drop — pass --drop or --drop-boilerplate (or --list)")

    dropped = [r for r in rows if r["stem"] in wanted or r["types"] & wanted]
    if not dropped:
        raise SystemExit(f"no spine entry matched {sorted(wanted)} — try --list")

    drop_ids = {r["idref"] for r in dropped}
    drop_files = {r["full"] for r in dropped}

    # Remove the itemrefs. Pandoc walks the spine, so a section that is not in
    # it is not read — but the files go too, so the result is not quietly
    # carrying content that nothing references.
    new_xml = xml
    for idref in drop_ids:
        new_xml = re.sub(
            rf'\s*<itemref\b[^>]*\bidref="{re.escape(idref)}"[^>]*/?>', "", new_xml
        )
        new_xml = re.sub(
            rf'\s*<item\b[^>]*\bid="{re.escape(idref)}"[^>]*/?>', "", new_xml
        )

    out = Path(args.out) if args.out else src.with_name(f"{src.stem}-trimmed.epub")
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
        out, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        # mimetype must be first and uncompressed, or readers reject the file.
        if "mimetype" in zin.namelist():
            zout.writestr(
                zipfile.ZipInfo("mimetype"), zin.read("mimetype"),
                compress_type=zipfile.ZIP_STORED,
            )
        for item in zin.infolist():
            if item.filename in ("mimetype",) or item.filename in drop_files:
                continue
            zout.writestr(item, new_xml.encode() if item.filename == opf
                          else zin.read(item.filename))

    print(f"wrote {out}")
    print(f"  dropped {len(dropped)}: {', '.join(r['stem'] for r in dropped)}")
    print(f"  kept    {len(rows) - len(dropped)} sections")


if __name__ == "__main__":
    main()
