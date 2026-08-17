#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=5.0", "reportlab>=4.0"]
# ///
"""Impose a trimmed interior PDF onto printable sheets.

Two schemes, matching the two ways you said you want to bind:

  perfect  cut-and-stack, two pages up on a landscape sheet. Print the whole
           job duplex, guillotine the stack once down the gap, drop the
           right-hand pile under the left-hand pile, and you have the book in
           order as single leaves ready to glue.

  sewn     booklet imposition into folded signatures, with creep
           compensation. Print, fold each sheet, nest them into signatures,
           sew through the folds.

Both need to know which way your printer turns the sheet over. Run
tools/regmark.py first and set imposition.flip; guessing costs you a whole
job's worth of paper.

Usage:
    ./tools/impose.py                      # scheme from book.toml
    ./tools/impose.py --scheme sewn
    ./tools/impose.py --dry-run            # print the sheet map, write nothing
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas

import bookspec
from bookspec import mm

HAIR = 0.25
MARK_LEN = 4.0  # mm, nominal crop-mark arm
MARK_GAP = 1.0  # mm, clear space between trim edge and the start of the arm


# --------------------------------------------------------------- page maps --


def perfect_map(pages: int) -> list[tuple[int, int, int, int]]:
    """Cut-and-stack 2-up. Returns (front_L, front_R, back_L, back_R) per sheet.

    Page numbers are 1-based; 0 means a blank.

    The book is split down the middle and the two halves ride side by side
    through the printer. After the cut, the left pile is pages 1..h in order
    and the right pile is h+1..n in order, so the whole job collates by
    stacking one pile on the other — no interleaving, no page-by-page sorting.

    Back-side slots are swapped relative to the front because turning the
    sheet over exchanges left and right. That swap is the imposition; the
    printer's flip setting only decides whether the sheet also comes out
    upside down, which is handled later by rotating the page.
    """
    n = pages + (-pages % 4)  # pad to a multiple of 4
    half = n // 2
    sheets = []
    for s in range(half // 2):
        fl = 2 * s + 1
        fr = half + 2 * s + 1
        bl = half + 2 * s + 2
        br = 2 * s + 2
        sheets.append(
            tuple(0 if p > pages else p for p in (fl, fr, bl, br))  # type: ignore[misc]
        )
    return sheets


def sewn_map(pages: int, per_sig: int) -> list[tuple[int, int, int, int, int, int]]:
    """Booklet imposition. Returns (fL, fR, bL, bR, sheet_in_sig, sig) per sheet.

    Within a signature of S sheets (4S pages), sheet i counted from the
    outside carries pages 4S-2i and 2i+1 on the front, 2i+2 and 4S-2i-1 on the
    back. The outermost sheet therefore holds the first and last pages of the
    signature, which is the property that makes a folded stack read in order.
    """
    per_sig_pages = 4 * per_sig
    n = pages + (-pages % per_sig_pages)
    sheets = []
    for sig in range(n // per_sig_pages):
        base = sig * per_sig_pages
        for i in range(per_sig):
            fl = base + per_sig_pages - 2 * i
            fr = base + 2 * i + 1
            bl = base + 2 * i + 2
            br = base + per_sig_pages - 2 * i - 1
            quad = tuple(0 if p > pages else p for p in (fl, fr, bl, br))
            sheets.append((*quad, i, sig))  # type: ignore[misc]
    return sheets


# ------------------------------------------------------------------- marks --


def _arm(c: canvas.Canvas, x: float, y: float, dx: float, dy: float, room: float) -> float:
    """Draw one crop-mark arm outward from (x, y), fitted to the room available.

    Returns the length actually drawn. The gap between the trim corner and the
    start of the arm shrinks along with the arm rather than staying fixed —
    a fixed 1 mm gap eats most of the space when there are only 3 mm to work
    with, which is exactly the case on the head and tail of an A4 sheet.
    """
    if room <= 0.6:
        return 0.0
    gap = min(MARK_GAP, room * 0.25)
    length = min(MARK_LEN, room - gap)
    if length < 0.5:
        return 0.0
    c.line(
        mm(x + dx * gap), mm(y + dy * gap),
        mm(x + dx * (gap + length)), mm(y + dy * (gap + length)),
    )
    return length


def crop_marks(c: canvas.Canvas, boxes, spec, sheet_w, sheet_h, mark_inner: bool):
    """Corner crop marks around each trim box, fitted to what actually prints.

    An arm inside the printer's dead border does not exist, so every arm is
    measured against the room between the trim edge and the printable
    boundary. In sewn mode the inner edges are the fold, not a cut, and get no
    marks at all — drawing them there would put ink across the facing page.
    """
    warn: list[str] = []
    u = spec.unprintable
    c.setLineWidth(HAIR)
    c.setStrokeColorRGB(0, 0, 0)

    shortest_v = 99.0
    centre = sheet_w / 2

    for x0, y0, w, h in boxes:
        x1, y1 = x0 + w, y0 + h
        for x, sx in ((x0, -1.0), (x1, 1.0)):
            # Is this the edge that faces the sheet centre?
            inner = (sx > 0 and x <= centre + 0.01) or (sx < 0 and x >= centre - 0.01)
            if inner and not mark_inner:
                continue
            room_x = (x - u) if sx < 0 else (sheet_w - u - x)
            if inner:
                # Never let an arm cross the waste strip into the facing page.
                room_x = min(room_x, spec.column_gap / 2)
            for y, sy in ((y0, -1.0), (y1, 1.0)):
                _arm(c, x, y, sx, 0.0, room_x)
                room_y = (y - u) if sy < 0 else (sheet_h - u - y)
                shortest_v = min(shortest_v, _arm(c, x, y, 0.0, sy, room_y))

    if shortest_v < 2.0:
        # Solve (sheet_h - th)/2 - u >= MARK_GAP + 2.5 for th.
        suggest = sheet_h - 2 * (u + MARK_GAP + 2.5)
        warn.append(
            f"head/tail crop marks come out {shortest_v:.1f} mm long — the "
            f"{u} mm dead border leaves little room. Set trim.height to "
            f"{suggest:.0f} mm or less for a mark you can aim a blade at, or "
            f"cut head and tail against a measured guillotine stop instead."
        )
    return warn


def sheet_marks(
    c: canvas.Canvas, spec, boxes, sheet_w, sheet_h, label: str, cut_x: float | None,
    fold_x: float | None,
) -> list[str]:
    warn = crop_marks(c, boxes, spec, sheet_w, sheet_h, mark_inner=cut_x is not None)

    # The cut line down the waste strip, and the fold line for signatures.
    if cut_x is not None:
        c.setDash(2, 2)
        c.setLineWidth(HAIR)
        c.setStrokeColorRGB(0.6, 0.6, 0.6)
        c.line(mm(cut_x), mm(spec.unprintable), mm(cut_x), mm(sheet_h - spec.unprintable))
        c.setDash()
    if fold_x is not None:
        c.setDash(6, 3)
        c.setLineWidth(HAIR)
        c.setStrokeColorRGB(0.6, 0.6, 0.6)
        c.line(mm(fold_x), mm(spec.unprintable), mm(fold_x), mm(sheet_h - spec.unprintable))
        c.setDash()

    # Sheet identity, small, in the dead strip nobody keeps. A dropped stack
    # is unrecoverable without this.
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.setFont("Helvetica", 4.5)
    c.drawCentredString(mm(sheet_w / 2), mm(spec.unprintable + 0.8), label)
    c.setFillColorRGB(0, 0, 0)
    return warn


# --------------------------------------------------------------- placement --


def place(out_page, src, box_x, box_y, trim_w, trim_h, src_page) -> None:
    """Drop one source page into a trim box at its natural size.

    No scaling: the interior was typeset at exactly the trim size, and
    scaling a text block to fit is how a book ends up with the wrong measure
    and the wrong optical weight.
    """
    if src_page == 0:
        return
    p = src.pages[src_page - 1]
    tx = mm(box_x) - float(p.mediabox.left)
    ty = mm(box_y) - float(p.mediabox.bottom)
    out_page.merge_transformed_page(p, Transformation().translate(tx, ty))


# ------------------------------------------------------------------- build --


def build(spec, src_path: Path, out_path: Path, scheme: str, dry: bool) -> None:
    src = PdfReader(str(src_path))
    pages = len(src.pages)

    pw = float(src.pages[0].mediabox.width) / (72.0 / 25.4)
    ph = float(src.pages[0].mediabox.height) / (72.0 / 25.4)
    if abs(pw - spec.trim_w) > 0.5 or abs(ph - spec.trim_h) > 0.5:
        print(
            f"warning: interior is {pw:.1f} x {ph:.1f} mm but book.toml says "
            f"{spec.trim_w} x {spec.trim_h} mm. Rebuild the interior, or fix the spec.",
            file=sys.stderr,
        )

    W, H = spec.imposed_w, spec.imposed_h  # landscape sheet
    tw, th = spec.trim_w, spec.trim_h
    y0 = (H - th) / 2

    warnings: list[str] = []

    if scheme == "perfect":
        gap = spec.column_gap
        x_left = (W - 2 * tw - gap) / 2
        x_right = x_left + tw + gap
        cut_x = x_left + tw + gap / 2
        fold_x = None
        sheets = perfect_map(pages)
        plan = [(f, b, 0, 0) for f, b in ((s[:2], s[2:]) for s in sheets)]
    else:
        # Folded: the spine of each page sits on the fold at the sheet centre.
        x_left = W / 2 - tw
        x_right = W / 2
        cut_x = None
        fold_x = W / 2
        raw = sewn_map(pages, spec.sheets_per_sig)
        plan = [(s[:2], s[2:4], s[4], s[5]) for s in raw]

    if dry:
        print(f"{scheme}: {pages} pages -> {len(plan)} sheets ({len(plan)*2} sides)")
        print(f"sheet  {'front L/R':>14}  {'back L/R':>14}   creep")
        for n, (front, back, idx, sig) in enumerate(plan, 1):
            cr = spec.creep(idx, spec.sheets_per_sig) if scheme == "sewn" else 0.0
            tag = f"  sig{sig+1} s{idx+1}" if scheme == "sewn" else ""
            print(
                f"{n:5d}  {front[0]:6d} {front[1]:6d}  {back[0]:6d} {back[1]:6d}"
                f"  {cr:5.2f}{tag}"
            )
        return

    writer = PdfWriter()

    for n, (front, back, idx, sig) in enumerate(plan, 1):
        creep = spec.creep(idx, spec.sheets_per_sig) if scheme == "sewn" else 0.0

        for is_front, slots in ((True, front), (False, back)):
            page = PageObject.create_blank_page(width=mm(W), height=mm(H))

            # Creep pulls each page toward the fold; the left page moves right
            # and the right page moves left, so both keep their margins after
            # the fore-edge is trimmed off.
            lx = x_left + creep
            rx = x_right - creep

            place(page, src, lx, y0, tw, th, slots[0])
            place(page, src, rx, y0, tw, th, slots[1])

            boxes = [(lx, y0, tw, th), (rx, y0, tw, th)]
            side = "front" if is_front else "back"
            if scheme == "sewn":
                label = f"{spec.book['title']}  ·  sig {sig+1}  sheet {idx+1}  {side}"
            else:
                label = f"{spec.book['title']}  ·  sheet {n} of {len(plan)}  {side}"

            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(mm(W), mm(H)))
            w = sheet_marks(c, spec, boxes, W, H, label, cut_x, fold_x)
            c.save()
            buf.seek(0)
            page.merge_page(PdfReader(buf).pages[0])
            if n == 1 and is_front:
                warnings.extend(w)

            # A short-edge flip turns the back over the other way, which is a
            # long-edge flip plus a half turn. Undo the half turn here so the
            # same imposition serves both kinds of printer.
            if not is_front and spec.flip == "short":
                page.add_transformation(
                    Transformation().rotate(180).translate(mm(W), mm(H))
                )

            writer.add_page(page)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as fh:
        writer.write(fh)

    print(f"wrote {out_path}")
    print(f"  {pages} pages -> {len(plan)} sheets, {len(plan) * 2} sides, {scheme}")
    if scheme == "sewn":
        nsig = plan[-1][3] + 1
        print(f"  {nsig} signatures of {spec.sheets_per_sig} sheets")
        print(f"  creep across a signature: {spec.creep(spec.sheets_per_sig - 1, spec.sheets_per_sig):.2f} mm")
    else:
        print(f"  cut once at {(W - 2 * spec.trim_w - spec.column_gap) / 2 + spec.trim_w + spec.column_gap / 2:.1f} mm from the left sheet edge")
        print("  then put the right-hand pile UNDER the left-hand pile")
    print(f"  duplex flip: {spec.flip}  (from book.toml — verify with regmark.py)")
    for w in warnings:
        print(f"  warning: {w}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", help="path to book.toml")
    ap.add_argument("-i", "--input", help="interior PDF (default out/interior.pdf)")
    ap.add_argument("-o", "--out", help="output PDF")
    ap.add_argument("--scheme", choices=("perfect", "sewn"), help="override book.toml")
    ap.add_argument("--dry-run", action="store_true", help="print the sheet map only")
    args = ap.parse_args()

    spec = bookspec.load(args.spec)
    root = spec.path.parent
    scheme = args.scheme or spec.method

    for w in spec.check():
        print(f"warning: {w}", file=sys.stderr)

    src = Path(args.input) if args.input else root / "out" / "interior.pdf"
    if not src.is_file():
        raise SystemExit(f"no interior at {src} — run interior/build.sh first")

    out = Path(args.out) if args.out else root / "out" / f"imposed-{scheme}.pdf"
    build(spec, src, out, scheme, args.dry_run)


if __name__ == "__main__":
    main()
