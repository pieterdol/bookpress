#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["reportlab>=4.0", "pillow>=10.0", "pypdf>=5.0"]
# ///
"""Build a paperback cover wrap: back cover, spine and front as one flat sheet.

The spine width comes from the real page count of the built interior, so this
cannot be run meaningfully until the text block is final — one page added or
removed moves both folds and shifts every panel.

    +--------------------------------------------------+
    |  bleed                                            |
    |    +-------------+---+-------------+              |
    |    | BACK COVER  | S | FRONT COVER |   trim height |
    |    +-------------+---+-------------+              |
    |                                                   |
    +--------------------------------------------------+
       trim width    spine   trim width

Usage:
    ./tools/cover.py                          # geometry + plain wrap
    ./tools/cover.py --art art/front.png      # art fills the front panel
    ./tools/cover.py --wrap art/full.png      # one image across the whole wrap
    ./tools/cover.py --guides                 # overlay folds and safe areas
    ./tools/cover.py --sheet 297x210          # centre it on A4 landscape
    ./tools/cover.py --pages 320              # model a spine before the text is done
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import bookspec
from bookspec import mm

MIN_SPINE_TEXT = 6.0  # mm; below this the spine is too narrow to letter
GROUND = (0.09, 0.09, 0.11)  # panel colour where no art covers
TARGET_DPI = 300


# -------------------------------------------------------------------- fonts --


def resolve_font(name: str) -> str:
    """Register a system font by family name, falling back to a built-in.

    fc-match never fails — ask it for a font nobody has installed and it
    cheerfully hands back the default sans. So the family it reports has to be
    checked against the family that was asked for, or a cover meant to be set
    in Garamond quietly comes out in DejaVu Sans.

    reportlab also only reads TrueType outlines, so an OTF with CFF glyphs —
    which is what most of the good book faces ship as, EB Garamond included —
    will not load here at all. That is survivable for the half-dozen words on
    a cover, and it is part of why the interior is set in LaTeX instead.
    """
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{family}\t%{file}", name],
            capture_output=True, text=True, timeout=5,
        )
        family, _, path_s = out.stdout.strip().partition("\t")
        path = Path(path_s)
        wanted = name.lower().replace(" ", "")
        got = family.lower().replace(" ", "")
        if wanted not in got and got not in wanted:
            return "Times-Roman"
        if path.suffix.lower() == ".ttf" and path.is_file():
            pdfmetrics.registerFont(TTFont(name, str(path)))
            return name
    except Exception:
        pass
    return "Times-Roman"


# ---------------------------------------------------------------- geometry --


class Wrap:
    def __init__(self, spec, pages: int):
        self.spec = spec
        self.pages = pages
        self.spine = spec.spine_width(pages)
        self.bleed = spec.bleed
        self.tw, self.th = spec.trim_w, spec.trim_h

        self.width = 2 * self.tw + self.spine + 2 * self.bleed
        self.height = self.th + 2 * self.bleed

        # Panel left edges, measured from the wrap's own bottom-left corner.
        self.back_x = self.bleed
        self.spine_x = self.bleed + self.tw
        self.front_x = self.bleed + self.tw + self.spine
        self.panel_y = self.bleed

    def report(self) -> str:
        s = self.spec
        return "\n".join([
            f"  page count        {self.pages}  ({self.pages / 2:.0f} leaves)",
            f"  caliper           {s.caliper} mm per sheet",
            f"  spine             {self.pages / 2:.0f} x {s.caliper} + {s.glue_allowance}"
            f" glue = {self.spine:.2f} mm",
            f"  wrap              {self.width:.1f} x {self.height:.1f} mm"
            f"  (bleed {self.bleed} mm)",
            f"  fold 1 at         {self.spine_x:.1f} mm from the left wrap edge",
            f"  fold 2 at         {self.front_x:.1f} mm from the left wrap edge",
            f"  spine lettering   {'yes' if self.spine >= MIN_SPINE_TEXT else 'NO - spine too narrow'}",
        ])


# ------------------------------------------------------------------ drawing --


def fill_panel(c, img_path: Path, x, y, w, h, warn: list[str], quality: int = 92) -> None:
    """Draw an image cropped to cover the panel exactly, centred.

    Cover, not fit: a cover with white slivers down one edge looks like a
    mistake, and stretching to fit looks worse.
    """
    img = Image.open(img_path)
    iw, ih = img.size
    eff_dpi = min(iw / (w / 25.4), ih / (h / 25.4))
    if eff_dpi < TARGET_DPI:
        warn.append(
            f"{img_path.name} lands at {eff_dpi:.0f} dpi over "
            f"{w:.0f} x {h:.0f} mm; {TARGET_DPI} dpi wants "
            f"{int(w / 25.4 * TARGET_DPI)} x {int(h / 25.4 * TARGET_DPI)} px. "
            f"Upscale it before this goes near a press."
        )

    target = w / h
    if iw / ih > target:  # too wide: trim the sides
        new_w = int(ih * target)
        box = ((iw - new_w) // 2, 0, (iw + new_w) // 2, ih)
    else:  # too tall: trim top and bottom
        new_h = int(iw / target)
        box = (0, (ih - new_h) // 2, iw, (ih + new_h) // 2)
    img = img.crop(box).convert("RGB")

    if quality:
        # reportlab embeds a PIL image losslessly, which for a 4864 x 3328
        # wraparound means a 39 MB PDF — awkward to hand to a print shop and
        # pointless on paper. Re-encoding as JPEG hands reportlab a DCTDecode
        # stream instead and costs nothing visible at this quality; presses
        # have taken JPEG for decades.
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, subsampling=0, optimize=True)
        buf.seek(0)
        c.drawImage(ImageReader(buf), mm(x), mm(y), mm(w), mm(h))
    else:
        c.drawImage(ImageReader(img), mm(x), mm(y), mm(w), mm(h))


def band_luminance(img_path: Path, frac_lo: float, frac_hi: float) -> float:
    """Mean perceived luminance (0-1) of a horizontal band of the art.

    frac_lo/frac_hi are measured from the BOTTOM of the image, matching the
    PDF coordinate system the type is placed in.
    """
    img = Image.open(img_path).convert("L")
    w, h = img.size
    top = int(h * (1.0 - frac_hi))
    bot = int(h * (1.0 - frac_lo))
    band = img.crop((0, max(0, top), w, min(h, max(bot, top + 1))))
    px = list(band.resize((64, 16)).getdata())
    return sum(px) / len(px) / 255.0


def scrim(c, x, y, w, h, strength: float, from_top: bool, fade: str | None = None) -> None:
    """Lay a fading dark wash over part of the wrap so type can sit on it.

    A cover with busy or pale art has nowhere for white type to live. Every
    trade paperback solves this the same way — a gradient scrim — and it stays
    invisible as long as it fades out before the art gets interesting.

    `fade` adds a horizontal fade to nothing at the named edge. On a
    wraparound that is not decoration: a wash that simply stops at the fold
    leaves a hard vertical step down the cover, and the eye finds it
    instantly because nothing else on a printed page has an edge like that.
    """
    wsteps, hsteps = (64 if fade else 1), 256
    layer = Image.new("RGBA", (wsteps, hsteps), (0, 0, 0, 255))
    alpha = Image.new("L", (wsteps, hsteps))
    for j in range(hsteps):
        t = j / (hsteps - 1)              # 0 at the top of the strip
        v = (1.0 - t) if from_top else t  # fade away from the edge
        # An exponent below 1 holds the wash open across the middle of its
        # span rather than collapsing near the edge. A steeper curve looks
        # tidier in isolation and leaves nothing under the type, which is the
        # only place the wash exists to serve.
        v = v ** 0.75
        for i in range(wsteps):
            u = i / (wsteps - 1) if wsteps > 1 else 0.0
            if fade == "right":
                hmul = (1.0 - u) ** 0.9
            elif fade == "left":
                hmul = u ** 0.9
            else:
                hmul = 1.0
            alpha.putpixel((i, j), int(255 * min(1.0, strength) * v * hmul))
    layer.putalpha(alpha)
    c.drawImage(ImageReader(layer), mm(x), mm(y), mm(w), mm(h), mask="auto")


def guides(c, wr: Wrap) -> None:
    """Fold lines, trim box and safe areas. Proofing only — never print these."""
    s = wr.spec
    c.saveState()
    c.setFont("Helvetica", 5)

    # Trim box.
    c.setStrokeColorRGB(0, 0.6, 0.9)
    c.setLineWidth(0.4)
    c.setDash(3, 2)
    c.rect(mm(wr.bleed), mm(wr.bleed), mm(wr.width - 2 * wr.bleed), mm(wr.th))

    # Folds.
    c.setStrokeColorRGB(0.9, 0.2, 0.2)
    for x, tag in ((wr.spine_x, "fold"), (wr.front_x, "fold")):
        c.line(mm(x), mm(0), mm(x), mm(wr.height))
        c.setFillColorRGB(0.9, 0.2, 0.2)
        c.drawString(mm(x + 0.8), mm(1.5), f"{tag} @ {x:.1f}")

    # Safe areas: inset from every trim edge and from both folds.
    c.setStrokeColorRGB(0.2, 0.7, 0.2)
    c.setDash(1.5, 1.5)
    for px, pw in (
        (wr.back_x, wr.tw), (wr.spine_x, wr.spine), (wr.front_x, wr.tw)
    ):
        if pw <= 2 * s.safe:
            continue
        c.rect(
            mm(px + s.safe), mm(wr.panel_y + s.safe),
            mm(pw - 2 * s.safe), mm(wr.th - 2 * s.safe),
        )
    c.setDash()
    c.restoreState()


def spine_text(c, wr: Wrap, font: str, direction: str) -> None:
    s = wr.spec
    if wr.spine < MIN_SPINE_TEXT:
        return
    title = s.book.get("spine_title") or s.book["title"]
    author = s.book["author"]

    # Fit to the spine height, leaving the safe inset at each end. The type
    # is sized off the spine width, not the page: the constraint that matters
    # is the 1.5-2 mm of clearance you need to each fold, because a spine
    # line that drifts onto the front cover is the classic hand-binding tell.
    avail = wr.th - 2 * s.safe
    size = min(wr.spine * 0.60, 16.0)
    while size > 4 and pdfmetrics.stringWidth(f"{title}   {author}", font, size) > mm(avail):
        size -= 0.25

    cx = wr.spine_x + wr.spine / 2
    cy = wr.panel_y + wr.th / 2

    c.saveState()
    c.translate(mm(cx), mm(cy))
    # "down": reads top-to-bottom with the book lying face up — UK/US and
    # every print-on-demand template. "up" is the traditional Dutch and
    # German direction. Both are correct; a shelf of mixed ones is not.
    c.rotate(-90 if direction == "down" else 90)
    c.setFont(font, size)
    c.setFillColorRGB(1, 1, 1)
    c.drawCentredString(0, -size * 0.35, f"{title}   {author}")
    c.restoreState()


def back_text(c, wr: Wrap, font: str, blurb: Path) -> None:
    """Set the back-cover copy, wrapped inside the safe area."""
    s = wr.spec
    x = wr.back_x + s.safe
    w = wr.tw - 2 * s.safe
    size, lead = 9.5, 13.5

    # Blank lines in the source separate paragraphs; a lone newline is just
    # how the file happens to be wrapped and carries no meaning.
    lines: list[str | None] = []
    for para in blurb.read_text().split("\n\n"):
        if not para.strip():
            continue
        if lines:
            lines.append(None)  # paragraph space
        cur = ""
        for word in para.split():
            trial = f"{cur} {word}".strip()
            if pdfmetrics.stringWidth(trial, font, size) > mm(w) and cur:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            lines.append(cur)

    c.setFont(font, size)
    c.setFillColorRGB(0.92, 0.92, 0.92)
    step = lead / (72.0 / 25.4)
    y = wr.panel_y + wr.th * 0.78
    for line in lines:
        if line is None:
            y -= step * 0.6
            continue
        c.drawString(mm(x), mm(y), line)
        y -= step


def cover_text(c, wr: Wrap, font: str) -> None:
    s = wr.spec
    fx = wr.front_x + s.safe
    fw = wr.tw - 2 * s.safe
    c.setFillColorRGB(1, 1, 1)

    size = 26.0
    title = s.book["title"]
    while size > 10 and pdfmetrics.stringWidth(title, font, size) > mm(fw):
        size -= 0.5
    c.setFont(font, size)
    c.drawCentredString(mm(fx + fw / 2), mm(wr.panel_y + wr.th * 0.72), title)

    c.setFont(font, size * 0.5)
    c.drawCentredString(mm(fx + fw / 2), mm(wr.panel_y + wr.th * 0.14), s.book["author"])


# --------------------------------------------------------------------- main --


def page_count(spec, override: int | None) -> int:
    if override:
        return override
    if spec.raw["cover"].get("page_count"):
        return int(spec.raw["cover"]["page_count"])
    pdf = spec.path.parent / "out" / "interior.pdf"
    if not pdf.is_file():
        raise SystemExit(
            "no out/interior.pdf to measure — build the interior first, or pass --pages"
        )
    return len(PdfReader(str(pdf)).pages)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec")
    ap.add_argument("-o", "--out")
    ap.add_argument("--art", help="image for the front panel")
    ap.add_argument("--back-art", help="image for the back panel")
    ap.add_argument("--wrap", help="one image spanning the whole wrap")
    ap.add_argument("--blurb", help="text file of back-cover copy")
    ap.add_argument("--pages", type=int, help="override the measured page count")
    ap.add_argument("--guides", action="store_true", help="overlay folds and safe areas")
    ap.add_argument("--no-text", action="store_true", help="art only, set type elsewhere")
    ap.add_argument("--font", default="EB Garamond")
    ap.add_argument("--spine-direction", choices=("down", "up"), default="down")
    ap.add_argument("--jpeg-quality", type=int, default=92, metavar="Q",
                    help="JPEG quality for placed art (default 92)")
    ap.add_argument("--lossless", action="store_true",
                    help="embed art losslessly; much larger files")
    ap.add_argument("--spine-band", action="store_true",
                    help="solid band across the spine, for wraparound art that "
                         "would otherwise leave the lettering on open picture")
    ap.add_argument("--scrim", type=float, default=0.0, metavar="STRENGTH",
                    help="0-1 dark gradient over the top and bottom of the front "
                         "panel so white type reads over pale or busy art (try 0.6)")
    ap.add_argument("--sheet", help="centre the wrap on a sheet, e.g. 297x210")
    args = ap.parse_args()

    spec = bookspec.load(args.spec)
    wr = Wrap(spec, page_count(spec, args.pages))
    warn: list[str] = []

    page_w, page_h = wr.width, wr.height
    ox = oy = 0.0
    if args.sheet:
        sw, sh = (float(v) for v in args.sheet.lower().split("x"))
        if wr.width > sw or wr.height > sh:
            raise SystemExit(
                f"wrap is {wr.width:.1f} x {wr.height:.1f} mm and will not fit a "
                f"{sw:g} x {sh:g} mm sheet"
            )
        page_w, page_h = sw, sh
        ox, oy = (sw - wr.width) / 2, (sh - wr.height) / 2

    out = Path(args.out) if args.out else spec.path.parent / "out" / "cover.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    font = resolve_font(args.font)
    c = canvas.Canvas(str(out), pagesize=(mm(page_w), mm(page_h)))
    c.setTitle(f"{spec.book['title']} — cover wrap")
    c.translate(mm(ox), mm(oy))

    # Ground colour, so an untouched panel is not white paper by accident.
    c.setFillColorRGB(*GROUND)
    c.rect(0, 0, mm(wr.width), mm(wr.height), fill=1, stroke=0)

    # Panel art runs out into the bleed on the three edges that face the
    # outside of the book. Stopping it at the trim line guarantees a white
    # sliver the moment the guillotine wanders half a millimetre.
    b = wr.bleed
    q = 0 if args.lossless else args.jpeg_quality
    if args.wrap:
        fill_panel(c, Path(args.wrap), 0, 0, wr.width, wr.height, warn, q)
    if args.back_art:
        fill_panel(c, Path(args.back_art), 0, 0, wr.tw + b, wr.height, warn, q)
    if args.art:
        fill_panel(c, Path(args.art), wr.front_x, 0, wr.tw + b, wr.height, warn, q)

    # White type on a pale sky is the commonest way an otherwise good cover
    # fails, and it is obvious on the page and invisible in the terminal. Check
    # the two bands the type actually lands in and say so.
    front_art = args.art or args.wrap
    if front_art and not args.no_text and args.scrim <= 0:
        for label, lo, hi in (("title", 0.68, 0.80), ("author", 0.09, 0.19)):
            lum = band_luminance(Path(front_art), lo, hi)
            if lum > 0.55:
                warn.append(
                    f"the art under the {label} averages {lum:.0%} luminance — "
                    f"white type will not read there. Add --scrim 0.6, or pick "
                    f"art with a dark band where the type goes."
                )

    # Scrims go over the art but under the type.
    if args.scrim > 0:
        # Each wash has to reach past the type it serves, not stop at it: the
        # title sits at 72% of the panel and the author at 14%.
        top_h = wr.height * 0.52
        bot_h = wr.height * 0.34
        spans_all = bool(args.wrap)

        # On a wraparound the top and bottom washes run the whole width, so
        # there is no density change at either fold to give them away. With
        # art on the front only, the back is flat ground and needs nothing.
        x0 = 0.0 if spans_all else wr.front_x
        w0 = wr.width if spans_all else wr.tw + b
        scrim(c, x0, wr.height - top_h, w0, top_h, args.scrim, True)
        scrim(c, x0, 0, w0, bot_h, args.scrim, False)

        # Body copy needs far more contrast than a display line, so the back
        # takes an extra wash — faded out horizontally towards the spine so it
        # meets the front panel at nothing rather than at an edge.
        if args.wrap or args.back_art:
            back_h = wr.height * 0.86
            scrim(c, 0, wr.height - back_h, wr.spine_x, back_h,
                  args.scrim * 0.75, True, fade="right")

    # A wraparound runs the art straight through the spine, which is where the
    # lettering has to go and where there is least room to lose. A solid band
    # is what publishers do here, and its hard edges are not a blemish: they
    # land exactly on the folds, where the cover physically creases. An edge ON
    # a fold reads as design; an edge NEAR one reads as a mistake.
    if args.spine_band and wr.spine >= MIN_SPINE_TEXT:
        c.setFillColorRGB(*GROUND)
        c.rect(mm(wr.spine_x), 0, mm(wr.spine), mm(wr.height), fill=1, stroke=0)

    if not args.no_text:
        cover_text(c, wr, font)
        spine_text(c, wr, font, args.spine_direction)
        if args.blurb:
            back_text(c, wr, font, Path(args.blurb))

    if args.guides:
        guides(c, wr)

    if args.sheet:
        # Trim marks outside the wrap, on the sheet.
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.25)
        for x in (0, wr.width):
            for y in (0, wr.height):
                c.line(mm(x), mm(y - 5 if y == 0 else y + 5), mm(x), mm(y))
                c.line(mm(x - 5 if x == 0 else x + 5), mm(y), mm(x), mm(y))

    c.showPage()
    c.save()

    print(f"wrote {out}")
    print(wr.report())
    if args.sheet:
        print(f"  centred on        {page_w:g} x {page_h:g} mm sheet")
    if font == "Times-Roman" and args.font != "Times-Roman":
        warn.append(
            f"'{args.font}' is not available as TrueType; fell back to Times-Roman. "
            f"Use --no-text and set the cover type in Scribus for the real thing."
        )
    for w in warn:
        print(f"  warning: {w}")


if __name__ == "__main__":
    main()
