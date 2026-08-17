# Recommendations

Hardware, materials and the reasoning behind the software choices already
implemented in this repo. Prices are rough EU figures and drift; treat them as
ratios, not quotes.

---

## 1. Printer

### Laser, not inkjet

For a text block this is not a close call.

- **Toner is dry and fused.** No cockling, no drying time before you stack 150
  sheets, and no bleeding when PVA moisture reaches the spine. Inkjet on
  80 gsm cockles enough that a glued block ends up visibly wavy.
- **Cost per page.** ~€0.01–0.02 with compatible toner. A 320-page novel is
  about €2 of toner. Inkjet is 5–10× that, and slow.
- **Sharpness at 11 pt.** Laser edges are crisper than dye inkjet on uncoated
  stock, where ink wicks into the fibre.

Keep an inkjet only for illustration plates — *War of the Worlds* has the
Corrêa and Goble sets. Print those on pigment inkjet and **tip them in** by
hand. Better than laser halftones, and it sidesteps the whole problem.

### What actually matters

Most printer reviews measure things irrelevant here.

1. **Duplex registration** — how precisely the back of a sheet lines up with
   the front. Cheap units drift 1–2 mm, which reads as a wandering gutter
   through the whole book. Nobody publishes this number; `tools/regmark.py`
   measures it in one sheet.
2. **Media weight range.** Text stock at 80–100 gsm is fine anywhere. Cover
   stock at 250–300 gsm is where desktop lasers give up — most cap around
   160–200 gsm even from the manual tray.
3. **Straight-through paper path.** A rear exit that avoids bending the sheet
   around the fuser. Essential for card, rare on cheap machines.
4. **CUPS support.** Driverless IPP Everywhere is the sane path now. Brother
   and Kyocera both do it well. Avoid recent HP — the cartridge
   authentication firmware is a running hostility.

### Options

**Entry — Brother HL-L2400D / L2445DW line, ~€150–200.** Auto duplex,
`brlaser` works out of the box, cheap and widely available toner. Registration
is okay-not-great. This is the correct *first* printer: twenty badly bound
books will teach you more than any amount of further research.

**The one I would buy — Kyocera ECOSYS P-series (e.g. P3155dn), ~€300–400.**
Kyocera's design centre is long-life drum plus cheap toner, aimed at
high-volume offices, which is exactly this usage pattern. Noticeably better
paper handling and registration than the Brother consumer line; per-page cost
drops to around a cent.

**Covers — a separate machine, or don't.** Reliably feeding 250–300 gsm
through a desktop laser is genuinely annoying. Either an **OKI LED printer**
(C500/C800 lines have a real straight path and eat card stock) or send the
cover PDF to a local copy shop for a couple of euros. For one or two books at
a time the copy shop wins on cost *and* quality, and they will laminate.

`cover.py --sheet 297x210` already emits the wrap centred on A4 landscape with
trim marks, because a B-format wrap is 282 × 200 mm and fits — just.

---

## 2. Paper

### Grain direction — the part nobody mentions

**Grain must run parallel to the spine.** Cross-grain, the book fights you
when it opens, folds crack instead of creasing, and pages wave with humidity.

Standard A4 office paper is **long grain**: fibres run along the 297 mm side.
Fold it in half and the fold runs along the 210 mm direction — perpendicular
to the grain. Wrong way round.

So for anything folded you want **short-grain A4**, sold by bookbinding and
printing suppliers rather than office shops. Test a ream you already have:
tear a sheet both ways. It tears straight and clean *with* the grain, ragged
*against* it. Or wet a strip and watch which way it curls.

This matters less for the glued cut-and-stack scheme (single leaves, no folds)
than for sewn signatures — but it still affects how the finished block opens,
so buy short grain once you are past the test phase.

### Weight and shade

80 gsm office white duplexes with visible show-through and reads cold. Better:
an uncoated book wove around 80–90 gsm in cream or ivory — **Munken Print
Cream** is the reference, and bulky book papers give a thicker block at the
same weight. Higher opacity is the specific property to look for.

Whatever you buy, **measure its caliper** and put it in `book.toml`. 100
sheets, calipers, divide by 100. Every spine calculation depends on it, and
the gsm rating will not tell you — bulky papers can be half again as thick as
office stock at the same weight.

---

## 3. Binding materials

- **Flexible bookbinding PVA.** Not wood glue, not padding compound. It stays
  flexible when cured, which is the entire requirement for a spine.
- **Mull / gauze** for a spine lining. Turns a glued block into one that
  survives being opened.
- **Double-fan binding** is the technique. Rough or notch the spine, fan the
  block one way and glue, fan the other way and glue again, then line with
  mull. It is dramatically stronger than the padding-glue approach POD uses,
  and it is the one DIY method that reliably does not shed pages.
- **One warning:** PVA does not bond to fused toner. Keep the inner margin
  clear of print near the spine edge, and never glue endpapers onto a
  toner-covered area.

For Phase 2: linen thread, a curved needle or a straight one with a cradle, an
awl, and either a sewing frame or a simple jig.

---

## 4. Tools

**The bottleneck is the guillotine, not the printer.** A 300-page block needs
a stack cutter that takes 15–20 mm in one clean bite. A rotary trimmer wanders
and leaves a bevelled, ugly fore-edge.

- A Dahle 550/560-class stack cutter is the usual hobbyist answer, and it is a
  real chunk of money.
- Perfectly reasonable alternative: bind at home, pay a copy shop a few euros
  to trim the three edges on a programmable guillotine. Takes them a minute.
- Cheap and necessary regardless: a bone folder, a metal straightedge, a
  cutting mat, and two boards plus clamps as an improvised press.

Spend on: the guillotine (or outsource it), the paper, the glue.
Do not spend on: a fancy printer before you have bound anything.

---

## 5. Cover artwork from ComfyUI

`tools/coverart.py` wraps the local setup and takes its geometry from
`book.toml`, so the aspect ratio and the upscale factor are derived rather than
guessed:

```bash
./tools/coverart.py --panel front --n 3 --name wotw "…"
# panel front: 132.0 x 200.0 mm printed
#   latent 832x1216, upscale 2x -> 1664x2432 px = 309 dpi
```

~35 s per image on the RX 6900 XT with a light model resident; ~76-87 s for
`zimage`, which has to evict the LLM first.

### Settings that matter here

- **Upscaler: `nickelback`, not the default `ultrasharp`.** UltraSharp adds
  fine detail and contrast, which suits photographs and actively harms
  painterly illustration — it turns soft brushwork gritty. Nickelback keeps
  flat colour and soft edges smooth. `generate.py` had no flag for this until
  we added one; `build_workflow` reads an `upscaler` key, which
  `coverart.py` passes.
- **Never generate at a bigger latent to get a bigger picture.** Enlargement
  happens after the decode, where it cannot invent a second subject.
- **`coverart.py` warns on dialect mismatch.** Prose sent to a tag model, or
  tag soup sent to a natural-language one, produces a quietly worse picture
  rather than an error.

### The models

Six of the nine in `~/Code/comfy-agent/agent.py` were tested for cover work.
The column that predicts most about how one behaves is **cfg**: at 1.0
classifier-free guidance is inert, so the negative prompt does nothing at all
and the positive is your only lever.

| model | prompt dialect | steps / cfg | negatives? | VRAM | observed speed |
|---|---|---|---|---|---|
| `krea` | natural language | 8 / 1.0 | **no** | heavy, evicts the LLM | ~90 s |
| `zimage` | natural language | 8 / 1.0 | **no** | heavy, evicts the LLM | ~76–87 s |
| `klein` | natural language | 4 / 1.0 | **no** | heavy, evicts the LLM | ~28 s |
| `cyberillustrious` | Danbooru tags | 30 / 5.0 | yes | light, co-resident | ~32–42 s |
| `illustrious` | Danbooru tags | 28 / 5.5 | yes | light, co-resident | ~35 s |
| `animagine` | Danbooru tags | 28 / 6.0 | yes | light, co-resident | ~35 s |

The natural-language three are marked `direct` in the registry and unload Qwen
before they run, which is most of why they are slower per image. The tag models
sit alongside it.

**`krea` is the best of them for this book**, which was not the expectation —
its registry style says "photorealistic / cinematic", but asked for a
nineteenth-century oil illustration it delivers one, with a genuine painted
surface rather than a rendered one. It is also the only model that both knows
St Paul's *and* renders it well, and the only one that followed a compositional
instruction ("dome on the right, empty mist on the left") consistently across
five generations.

**`illustrious` and `animagine` are not usable here.** Two attempts each at all
three subjects produced no cylinder, no machines, and red *light* rather than
red vegetation — lurid fantasy ruins in a loose digital-painting style. Whatever
CyberIllustrious gains from being the semi-realistic derivative, it is not
present in the base models.

### Which model for which subject

Tested on three subjects from this book, wraparound and front panel.

| subject | best model | what happened |
|---|---|---|
| red weed over a dead London street | `krea` | correct St Paul's dome, Thames on the left, weed on the buildings — and the composition brief followed in all five |
| the cylinder in its crater | `krea`, then `zimage` | krea darker and more restrained, zimage more illustrative; both correct first try |
| two walking machines at different distances | `krea` | best rendering by a distance: brass dome, jointed legs, cable stays, distant second machine every time |
| anything with a recognisable landmark | `krea` or `klein` | the only two that know what St Paul's looks like |

**Nothing counts legs.** Asked repeatedly for a three-legged machine: klein drew
four, krea drew four every time, zimage varied between three and four,
cyberillustrious drew a humanoid. "tripod" is unusable (see below) and "three
legs" does not constrain the count. If three legs matter, the options are to
pick a lucky variant, hide the legs in smoke, or lock the geometry with
ControlNet from a source that happens to have three.

**The boundary worth knowing: `cyberillustrious` cannot draw an unfamiliar
machine.** It failed the cylinder and the walking machines three times each,
and not for want of prompting. It is Illustrious-lineage, so its priors are
figures and environments:

- asked for one large cylinder, it produced *nine* — and raising the weight to
  `(cylinder:1.7)` made that worse, because **over-weighting multiplies a
  subject rather than emphasising it**. Second attempt: a field of concrete
  pillars.
- asked for a three-legged machine, it produced a giant nude humanoid, holding
  to that even against `--neg "humanoid robot, biped, arms, hands"`. Negatives
  that work are still no match for a strong prior.

Conversely, give `cyberillustrious` an environment and it is the best of the
three — and it was the only one that produced **no anachronisms**, where zimage
put yellow road markings and modern vehicles into a Victorian street.

So the working split: **`zimage` for machines and objects, `cyberillustrious`
for places, `klein` when a real landmark has to be recognisable.**

### Restyling: keeping a composition, changing the look

The models are good at different things, so the useful move is to compose with
one and repaint with another. Two mechanisms, and they are not interchangeable.

**img2img** (`--init X --denoise N`) starts the sampler from the source instead
of from noise. Structure loosens as denoise rises, so you are always trading
fidelity against how much the style may change: ~0.35 shifts palette and
brushwork, ~0.55 repaints surfaces, past ~0.75 little survives but the
arrangement of masses.

**ControlNet** (`--init X --controlnet`) conditions on extracted structure
instead, so geometry holds even at full denoise and the style is free to change
completely. It needs an SDXL ckpt model as the restyler — `cyberillustrious` is
the obvious one, being the best renderer of environments and the only tested
model whose negatives work. It will not load against krea, zimage or klein,
which are other architectures; `agent.py` says so rather than failing obscurely.

The model is `controlnet-union-sdxl-promax.safetensors` (2.3 GB, xinsir), which
carries canny, depth, tile and more in one file. ComfyUI has `ControlNetLoader`,
`ControlNetApplyAdvanced`, `SetUnionControlNetType` and a `Canny` node built in,
so no custom node pack is needed.

**Use `--cn-mode tile`, not the canny default, for night scenes.** Canny
conditions on extracted edges, which is excellent for architecture but useless
where there are none: a dark crater under an empty night sky yields almost no
edge map, and the first attempt had CyberIllustrious invent an archway and a
town square in the blank space. Tile conditions on the image itself, so it holds
composition regardless of contrast — the same source came back with the crater,
the cylinder's position and angle, and every lantern-bearing figure exactly in
place, repainted.

`--cn-end` defaults to 0.85, releasing the control before the last steps so the
model settles its own texture; holding to 1.0 tends to leave edges looking
traced.

### Vocabulary traps

Both of these cost a generation before they were obvious.

- **"tripod" means *camera tripod*.** On a Danbooru-trained model it is a
  photography term, and the result was literal camera tripods and telescopes
  standing in front of a bonfire. Describe the machine; never name it.
- **"hood" reads as biological.** It is Wells's own word for the machines'
  upper body, but to a diffusion model a hood is a cowl and a cowl belongs to a
  creature — the result was an H.R. Giger xenomorph head. *"A smooth domed
  canopy of riveted brass like an upturned cauldron lid, entirely mechanical,
  no head and no face"* routes around it, and is also Wells's phrasing.

The general lesson: a word that is evocative in prose may be a well-populated
category label in a training set. When a subject keeps coming out wrong, suspect
the noun before you suspect the prompt.

### What actually went wrong, and the fixes

- **The model cannot count legs.** "A colossal three-legged walking machine"
  came back as a four-limbed humanoid mech, twice. Diffusion models do not
  count. Two reliable workarounds: obscure the limbs (silhouette, fog, smoke,
  a low angle that crops them), or **choose a subject with nothing to count** —
  the cylinder in the pit, the red weed, the deserted city. The cylinder
  concept worked first time for exactly this reason.
- **Match the art's luminance to where the type goes.** `cover.py` sets the
  title in white at 72 % of the panel height. Two of three concepts had pale,
  washed-out skies there, so white type vanished; the night-sky one took it
  perfectly. Decide the type colour and the composition together — ask for
  "vast empty *dark* sky filling the upper third" and you get somewhere to put
  a title.
- **Do not let the model draw the title.** `coverart.py` negatives text,
  lettering, watermarks, logos and frames on every generation. Type is set in
  `cover.py` or Scribus, where it stays vector and sharp.
- **Generate three to five concepts.** The hit rate on a first prompt is low,
  and `--n 5` makes a batch cheap enough to be the default approach.

### Wrapping around the spine

`--panel wrap` sizes a single image across back, spine and front, reading the
page count from the built interior so the spine allowance is right. At 234
pages that is 277.7 × 200 mm, which needs a 1216×832 latent at 4× to clear
300 dpi — it comes out at 423 dpi and takes about the same 85 s.

Compose for it. The front cover is the **right-hand** third, so the subject
belongs right of centre and the left third wants to stay quiet enough to carry
the blurb. Saying so explicitly in the prompt works: "the dome on the right
side of the frame, the left opening out into pale empty mist" produced exactly
that.

Two problems only appear once the art is actually placed:

- **The spine is where wraparounds fail.** The art runs straight through it,
  so the lettering ends up on open picture with nothing behind it — and on a
  13.7 mm spine there is no room to lose. `--spine-band` lays a solid band
  across it. Its hard edges are not a blemish, because they fall exactly on the
  folds: an edge *on* a fold reads as design, an edge *near* one reads as a
  mistake.
- **Body copy needs much more contrast than a display line.** A title can sit
  on a light scrim; a blurb cannot. `--scrim` gives the back panel an extra
  wash, faded out horizontally towards the spine so it meets the front at
  nothing rather than at a visible step.

The alternative is `--panel front` plus a back sampled from the art — less
striking, but it never fails, and `cover.py` takes `--art`, `--back-art` and
`--wrap` so all three are one flag apart.

### White type on pale art

The single commonest way a good cover fails, and it is invisible in a terminal.
`cover.py` measures the mean luminance of the two bands the type lands in and
warns:

    warning: the art under the title averages 61% luminance — white type will
    not read there. Add --scrim 0.6, or pick art with a dark band.

`--scrim 0.6` to `0.7` fixes it, and on foggy or overcast art the darkening
tends to read as weather rather than as an overlay.

### Colour

ComfyUI gives sRGB; presses are CMYK, and saturated blues and greens dull
noticeably. Only relevant if a cover goes to a commercial press — convert
last, with a real profile (FOGRA39 for Europe) via Scribus's PDF/X-3 export or
`magick -profile`. For home laser output, ignore this entirely.

The one case that bites regardless of where it is printed: the reds
`cyberillustrious` produces are extremely saturated, and a desktop laser will
render them muddier than the screen suggests. Proof any red-dominant cover on
the actual printer before committing to it.

---

## 6. Why the software is what it is

| Choice | Why not the alternative |
|---|---|
| **pandoc + LuaLaTeX (memoir)** | Calibre's `ebook-convert` produces a PDF of an ebook: no mirrored margins, no gutter, weak hyphenation. A novel is pure flowing text, which is exactly what TeX is best at. |
| **Standard Ebooks as source** | Same public-domain text as Gutenberg, re-proofed, semantic XHTML, real em-dashes. Removes most of the cleanup. |
| **distrobox for TeX** | Host is ostree-immutable. TeX Live is ~2 GB and does not belong layered into the base image. |
| **`uv` inline-dependency scripts** | No venv to manage, no system packages, works on an immutable host. |
| **Custom imposition rather than `pdfbook2`** | `pdfbook2` does signatures but not cut-and-stack, not creep compensation, and not crop marks fitted to a specific printer's dead border. All three matter here. |
| **Scribus, if you want it** | Still the right tool for hand-tuning a cover. `cover.py --no-text --guides` gives you a correctly-sized wrap with fold and safe-area guides to import. |

---

## 7. If you would rather not print it yourself

Worth keeping in view as a comparison point: **Lulu** prints in the EU, has no
obligation to sell, and publishes exact templates. A one-off B-format
paperback runs roughly €5–8 plus shipping — considerably less than the
per-book cost of getting good at this, and the binding will be better than
anything hand-glued for the first several attempts.

That is not an argument against doing it yourself. It is an argument for being
clear that the point is the making, not the book.
