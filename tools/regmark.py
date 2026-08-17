#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["reportlab>=4.0"]
# ///
"""Duplex registration and printable-area test sheet.

Print this two-page PDF duplex on the paper you intend to use, then hold the
sheet up to a window. It answers the three questions you need answered before
imposing anything:

  1. How far out is the back side from the front? (registration error)
  2. Which way does this printer flip the sheet? (long or short edge)
  3. How close to the paper edge can it actually print? (unprintable border)

Every measuring feature is drawn at four stations arranged symmetrically
around the page centre, so a ladder and a pointer meet up no matter which way
the sheet flips. That is the whole trick: you cannot know the flip in advance,
so the pattern must not depend on it.

Usage:
    ./tools/regmark.py                  # uses book.toml for the sheet size
    ./tools/regmark.py -o /tmp/reg.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.pdfgen import canvas

import bookspec
from bookspec import mm

HAIR = 0.3
GAUGE_SPAN = 6.0  # mm each side of zero on a ladder
PROBE_INSETS = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0]

# Gauge stations, as (dx, dy) from the page centre in mm.
#
# Each group is closed under both x -> -x and y -> -y, which is what makes the
# sheet readable without knowing the duplex flip beforehand: whichever way the
# back lands, every pointer still finds a ladder. Within a group all stations
# measure the same axis, because a flip maps one station of the group onto
# another and the two must agree about what they are measuring.
#
# They sit off the centre lines on purpose — a pointer drawn along a centre
# line is invisible against it.
STATIONS_X = [(dx, dy) for dx in (-20.0, 20.0) for dy in (-45.0, 45.0)]
STATIONS_Y = [(dx, dy) for dx in (-45.0, 45.0) for dy in (-20.0, 20.0)]


def ladder(c: canvas.Canvas, cx: float, cy: float, horizontal: bool) -> None:
    """A vernier scale in 0.5 mm steps, centred on (cx, cy) in mm."""
    c.setLineWidth(HAIR)
    c.setFont("Helvetica", 3.6)
    k = 0
    step = 0.5
    n = int(GAUGE_SPAN / step)
    for i in range(-n, n + 1):
        off = i * step
        whole = abs(off - round(off)) < 1e-9
        if i == 0:
            length, width = 5.0, 0.6
        elif whole:
            length, width = 3.4, HAIR
        else:
            length, width = 2.0, HAIR
        c.setLineWidth(width)
        if horizontal:
            x = cx + off
            c.line(mm(x), mm(cy), mm(x), mm(cy + length))
            if whole and int(round(off)) % 2 == 0 and off != 0:
                c.drawCentredString(mm(x), mm(cy + length + 1.2), f"{int(round(off))}")
        else:
            y = cy + off
            c.line(mm(cx), mm(y), mm(cx + length), mm(y))
            if whole and int(round(off)) % 2 == 0 and off != 0:
                c.drawString(mm(cx + length + 0.8), mm(y - 0.6), f"{int(round(off))}")
        k += 1


def pointer(c: canvas.Canvas, cx: float, cy: float, horizontal: bool) -> None:
    """The mark that reads against a ladder on the other side of the sheet."""
    c.setLineWidth(0.6)
    if horizontal:
        c.line(mm(cx), mm(cy - 1.5), mm(cx), mm(cy + 6.5))
        p = c.beginPath()
        p.moveTo(mm(cx), mm(cy + 3.0))
        p.lineTo(mm(cx - 1.1), mm(cy + 5.2))
        p.lineTo(mm(cx + 1.1), mm(cy + 5.2))
        p.close()
    else:
        c.line(mm(cx - 1.5), mm(cy), mm(cx + 6.5), mm(cy))
        p = c.beginPath()
        p.moveTo(mm(cx + 3.0), mm(cy))
        p.lineTo(mm(cx + 5.2), mm(cy - 1.1))
        p.lineTo(mm(cx + 5.2), mm(cy + 1.1))
        p.close()
    c.drawPath(p, fill=1, stroke=0)


def common(c: canvas.Canvas, w: float, h: float) -> None:
    """Geometry identical on both sides: centre cross and corner brackets.

    All of it is symmetric about both axes, so it overlays itself under any
    duplex flip. Coarse misalignment shows up here at a glance.
    """
    cx, cy = w / 2, h / 2
    c.setLineWidth(HAIR)
    c.line(mm(cx), mm(12), mm(cx), mm(h - 12))
    c.line(mm(12), mm(cy), mm(w - 12), mm(cy))

    inset, arm = 15.0, 9.0
    for sx, x in ((1, inset), (-1, w - inset)):
        for sy, y in ((1, inset), (-1, h - inset)):
            c.line(mm(x), mm(y), mm(x + sx * arm), mm(y))
            c.line(mm(x), mm(y), mm(x), mm(y + sy * arm))


def margin_probe(c: canvas.Canvas, w: float, h: float) -> None:
    """Nested frames at known insets. The outermost frame that prints complete
    on all four sides gives this printer's unprintable border — put one step
    larger into paper.unprintable.

    Each label sits just inside its own frame and is staggered horizontally, so
    a missing number is as informative as a missing line.
    """
    c.setLineWidth(HAIR)
    c.setFont("Helvetica", 3.8)
    for i, inset in enumerate(PROBE_INSETS):
        c.rect(mm(inset), mm(inset), mm(w - 2 * inset), mm(h - 2 * inset))
        x = w / 2 - 21 + i * 7
        c.drawCentredString(mm(x), mm(h - inset - 3.2), f"{inset:g}")
        c.drawCentredString(mm(x), mm(inset + 1.4), f"{inset:g}")


def side(c: canvas.Canvas, spec, w: float, h: float, front: bool) -> None:
    cx, cy = w / 2, h / 2
    common(c, w, h)

    if front:
        margin_probe(c, w, h)

    # Eight stations: four reading left/right error, four reading up/down.
    # The redundancy is not waste — if the four readings on one axis disagree,
    # the sheet is going through skewed rather than merely offset, which is a
    # feed problem and no amount of gutter will hide it.
    for group, horiz in ((STATIONS_X, True), (STATIONS_Y, False)):
        for dx, dy in group:
            draw = ladder if front else pointer
            draw(c, cx + dx, cy + dy, horiz)

    # Flip indicator: a disc on the front, a square on the back, both drawn at
    # the same coordinates in their own page's space. Where the square lands
    # relative to the disc names the flip.
    fx, fy = cx - 30.0, cy + 68.0
    if front:
        c.circle(mm(fx), mm(fy), mm(3.0), fill=1, stroke=0)
    else:
        c.rect(mm(fx - 3.0), mm(fy - 3.0), mm(6.0), mm(6.0), fill=1, stroke=0)

    # Legend.
    c.setFont("Helvetica-Bold", 8)
    label = "FRONT  (side 1)" if front else "BACK  (side 2)"
    c.drawCentredString(mm(cx), mm(cy - 62), label)

    c.setFont("Helvetica", 6.2)
    if front:
        lines = [
            "Print duplex on your real stock, then hold the sheet up to a window.",
            "",
            "1. REGISTRATION - at each gauge, read where the pointer sits against",
            "   the ladder. That offset in mm is your duplex error. Under ~0.5 mm",
            "   is good; over 1.5 mm, widen interior.gutter to hide it.",
            "   If the four gauges on one axis disagree, the sheet is feeding",
            "   skewed rather than offset - a paper-path fault, not a margin one.",
            "",
            "2. FLIP - find the solid square (back) relative to the disc (front):",
            "     square lands on the disc ........ no mirroring   -> flip = short",
            "     square mirrored left/right ...... long-edge flip -> flip = long",
            "     square mirrored top/bottom ...... short-edge flip -> flip = short",
            "     square diagonally opposite ...... 180 deg        -> flip = long",
            "   Write the answer into imposition.flip in book.toml.",
            "",
            "3. PRINTABLE AREA - the frames run 2 mm to 7 mm from the paper edge.",
            "   The smallest number that prints complete on all four sides is the",
            "   closest this printer gets to the edge. Put it in paper.unprintable.",
        ]
        y = cy - 70
        for ln in lines:
            c.drawCentredString(mm(cx), mm(y), ln)
            y -= 2.9
    else:
        c.drawCentredString(mm(cx), mm(cy - 70), "Nothing to read on this side alone.")
        c.drawCentredString(mm(cx), mm(cy - 74), "Hold the sheet to the light and read the front.")

    c.setFont("Helvetica", 5)
    c.drawCentredString(
        mm(cx), mm(cy + 78),
        f"bookpress registration sheet  -  {w:g} x {h:g} mm  -  print at 100%, scaling OFF",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", help="path to book.toml")
    ap.add_argument("-o", "--out", default=None, help="output PDF")
    args = ap.parse_args()

    spec = bookspec.load(args.spec)
    w, h = spec.sheet_w, spec.sheet_h

    out = Path(args.out) if args.out else spec.path.parent / "out" / "regmark.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out), pagesize=(mm(w), mm(h)))
    c.setTitle("bookpress duplex registration sheet")
    for front in (True, False):
        side(c, spec, w, h, front)
        c.showPage()
    c.save()

    print(f"wrote {out}")
    print("Print it duplex at 100% scale — 'fit to page' will silently ruin the test.")


if __name__ == "__main__":
    main()
