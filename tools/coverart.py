#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=5.0"]
# ///
"""Generate cover artwork sized from book.toml, via the local ComfyUI.

The point of this over calling generate.py by hand is that the panel geometry
comes out of the same spec everything else uses. Ask for a front panel and it
works out the aspect ratio, picks the nearest latent the model will actually
draw well, and sets the upscale factor that clears 300 dpi at the real printed
size — rather than you guessing and finding out at the guillotine.

Two deliberate differences from the generic image path:

  * upscaler defaults to nickelback, not ultrasharp. UltraSharp adds fine
    detail and crunch, which is right for photographs and wrong for painterly
    illustration — it turns soft brushwork gritty.
  * no text is ever requested in the prompt. Cover type is set in cover.py or
    Scribus, where it stays vector and sharp.

Usage:
    ./tools/coverart.py --panel front --name wotw-a "a colossal machine ..."
    ./tools/coverart.py --panel wrap  --name wotw-w "..."      # full wraparound
    ./tools/coverart.py --panel front --n 3 --name wotw        # three concepts
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/Code/comfy-agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bookspec  # noqa: E402

TARGET_DPI = 300

# The three latent sizes these models are trained to draw. Asking for a bigger
# latent to get a bigger picture makes SDXL draw two subjects; enlargement
# happens after the decode instead.
LATENTS = [(1024, 1024), (832, 1216), (1216, 832)]

# Anything that tends to arrive as a caption, a logo, or a border.
NEG = ("text, title, lettering, watermark, signature, logo, frame, border, "
       "book cover mockup, ui, caption, letterboxing")


def panel_mm(spec, panel: str, pages: int) -> tuple[float, float]:
    """Printed size of the target area in mm, bleed included."""
    b = spec.bleed
    if panel == "front" or panel == "back":
        return spec.trim_w + b, spec.trim_h + 2 * b
    spine = spec.spine_width(pages)
    return 2 * spec.trim_w + spine + 2 * b, spec.trim_h + 2 * b


def pick(w_mm: float, h_mm: float) -> tuple[tuple[int, int], int, float]:
    """Choose latent size and upscale factor for the printed panel.

    Returns (latent, upscale, effective_dpi). The upscale factor is the
    smallest of 1/2/4 that clears TARGET_DPI on both axes — there is no point
    paying for 4x when 2x already prints.
    """
    target = w_mm / h_mm
    latent = min(LATENTS, key=lambda s: abs(s[0] / s[1] - target))
    need_w = w_mm / 25.4 * TARGET_DPI
    need_h = h_mm / 25.4 * TARGET_DPI
    for up in (1, 2, 4):
        px_w, px_h = latent[0] * up, latent[1] * up
        # The image is centre-cropped to the panel, so the binding constraint
        # is whichever axis has the least slack after cropping to aspect.
        scale = max(need_w / px_w, need_h / px_h)
        if scale <= 1.0:
            dpi = min(px_w / (w_mm / 25.4), px_h / (h_mm / 25.4))
            return latent, up, dpi
    px_w, px_h = latent[0] * 4, latent[1] * 4
    return latent, 4, min(px_w / (w_mm / 25.4), px_h / (h_mm / 25.4))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("prompt")
    ap.add_argument("--spec")
    ap.add_argument("--panel", choices=("front", "back", "wrap"), default="front")
    # zimage has a genuinely painterly, oil-on-canvas register that suits a
    # nineteenth-century novel far better than klein's cleaner digital look.
    # It costs ~85 s against klein's ~28 s, so use --model klein while you are
    # still hunting for a composition, then re-run the winner on zimage.
    ap.add_argument("--model", default="zimage")
    ap.add_argument("--upscaler", default="nickelback", choices=("nickelback", "ultrasharp"))
    ap.add_argument("--name", default="cover")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--pages", type=int, default=None,
                    help="page count for --panel wrap; default reads out/interior.pdf")
    ap.add_argument("--out", default=None)
    ap.add_argument("--neg", default="")
    ap.add_argument("--init", help="restyle this image instead of starting from noise")
    ap.add_argument("--denoise", type=float, default=0.5,
                    help="with --init: 0.35 shifts palette, 0.55 repaints surfaces, "
                         "0.75+ keeps only the arrangement of masses (default 0.5)")
    ap.add_argument("--controlnet", nargs="?", const="controlnet-union-sdxl-promax.safetensors",
                    help="lock composition to --init using a ControlNet; needs an "
                         "SDXL ckpt model such as cyberillustrious")
    ap.add_argument("--cn-strength", type=float, default=0.75)
    ap.add_argument("--cn-mode", default="canny", choices=("canny", "tile"),
                    help="canny conditions on extracted edges — strong on architecture, "
                         "but a dark low-contrast source yields almost no edges and the "
                         "model fills the gaps with invention. tile conditions on the "
                         "image itself, so it holds composition regardless of contrast")
    ap.add_argument("--cn-low", type=float, default=0.4, help="canny low threshold")
    ap.add_argument("--cn-high", type=float, default=0.8, help="canny high threshold")
    ap.add_argument("--cn-end", type=float, default=0.85,
                    help="release the control before the end so the model settles "
                         "its own texture (default 0.85)")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    spec = bookspec.load(args.spec)
    out_dir = Path(args.out) if args.out else spec.path.parent / "art"
    out_dir.mkdir(parents=True, exist_ok=True)

    # A wrap's width includes the spine, so it depends on the real page count.
    # Defaulting to a guess here would silently produce art of the wrong aspect
    # ratio, which only shows up as a crop at the very end.
    pages = args.pages
    if pages is None and args.panel == "wrap":
        pdf = spec.path.parent / "out" / "interior.pdf"
        if not pdf.is_file():
            raise SystemExit(
                "--panel wrap needs the page count: build the interior first, "
                "or pass --pages"
            )
        from pypdf import PdfReader

        pages = len(PdfReader(str(pdf)).pages)
        print(f"read {pages} pages from {pdf.name}")

    w_mm, h_mm = panel_mm(spec, args.panel, pages or 0)
    (lw, lh), up, dpi = pick(w_mm, h_mm)

    import agent  # noqa: E402  (needs the sys.path insert above)

    # The registry splits models by prompt dialect, and feeding one the other's
    # gets a quietly worse picture rather than an error. Booru models want
    # comma-separated Danbooru tags; a sentence reads to them as a bag of
    # loosely related words.
    style = agent.MODELS.get(args.model, {}).get("style", "")
    booru = "booru" in style
    prose = args.prompt.count(",") < 6 or len(max(args.prompt.split(","), key=len)) > 60
    if booru and prose:
        print(f"note: {args.model} wants comma-separated Danbooru tags, and this "
              f"prompt reads as prose — expect weaker adherence")
    elif not booru and not prose and args.prompt.count(",") > 14:
        print(f"note: {args.model} wants natural language, not tags")

    # LoadImage resolves bare names against ComfyUI's own input directory, so
    # the source has to be copied in rather than referenced where it lies.
    init_name = None
    if args.init:
        src = Path(args.init).expanduser()
        if not src.is_file():
            raise SystemExit(f"no such image: {src}")
        init_dir = Path(agent.INPUT_DIR)
        init_dir.mkdir(parents=True, exist_ok=True)
        init_name = f"bookpress-init{src.suffix}"
        shutil.copy2(src, init_dir / init_name)
        print(f"restyling {src.name} at denoise {args.denoise}")

    print(f"panel {args.panel}: {w_mm:.1f} x {h_mm:.1f} mm printed")
    print(f"  latent {lw}x{lh}, upscale {up}x -> {lw*up}x{lh*up} px = {dpi:.0f} dpi")
    print(f"  model {args.model}, upscaler {args.upscaler}")

    made = []
    for i in range(args.n):
        label = args.name if args.n == 1 else f"{args.name}-{chr(ord('a') + i)}"
        spec_d = {
            "model": args.model,
            "prompt": args.prompt,
            "negative_prompt": ", ".join(x for x in (NEG, args.neg) if x),
            "width": lw, "height": lh,
            "upscale": up, "upscaler": args.upscaler,
        }
        if init_name:
            if args.controlnet:
                # ControlNet reads structure from the source and repaints
                # everything else, so the sampler starts from noise as usual.
                # Passing init_image as well would blend the source back in and
                # confuse which mechanism is doing the work.
                spec_d["cn_image"] = init_name
                spec_d["controlnet"] = args.controlnet
                spec_d["cn_strength"] = args.cn_strength
                spec_d["cn_end"] = args.cn_end
                if args.cn_mode == "tile":
                    spec_d["cn_type"] = "tile"
                    spec_d["cn_preprocess"] = "none"
                else:
                    spec_d["cn_low"] = args.cn_low
                    spec_d["cn_high"] = args.cn_high
            else:
                spec_d["init_image"] = init_name
                spec_d["denoise"] = args.denoise
        print(f"→ {label} …", flush=True)
        try:
            files, secs = agent.generate(spec_d, timeout_s=args.timeout)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {e.__class__.__name__}: {e}", flush=True)
            continue
        # Move each result out immediately: SaveImage numbers by what is already
        # in the output folder, so a name chosen there is not stable.
        for f in files:
            src = Path(agent.OUTPUT_DIR) / f
            if not src.exists():
                hits = list(Path(agent.OUTPUT_DIR).rglob(f))
                if not hits:
                    continue
                src = hits[0]
            dst = out_dir / f"{label}.png"
            shutil.move(str(src), dst)
            made.append(dst)
            print(f"  ✓ {dst}  ({secs:.0f}s)", flush=True)

    if made:
        print(f"\nUse it:  ./tools/cover.py --art {made[0]} --guides --sheet 297x210")


if __name__ == "__main__":
    main()
