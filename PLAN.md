# bookpress — plan

Printing and hand-binding public-domain novels at home. First as glued
paperbacks, later as sewn signatures. *The War of the Worlds* is the pilot.

Everything here is built around one hard constraint: **the spine width depends
on the final page count**, so the cover cannot be designed until the interior
is finished. Get that ordering wrong and you re-do the cover every time you
fix a typo.

---

## The two tracks

```
  EPUB (Standard Ebooks)
        │
        │  pandoc
        ▼
  source/book.md ──────── hand-cleaned once, kept in git
        │
        │  interior/build.sh   (pandoc → LuaLaTeX, memoir class)
        ▼
  out/interior.pdf  ····· 129 × 194 mm trimmed pages, even page count
        │                          │
        │  tools/impose.py         │  page count
        ▼                          ▼
  out/imposed-*.pdf         tools/cover.py ──► out/cover.pdf
  A4 sheets, duplex          back │ spine │ front, folds computed
        │                          │
        ▼                          ▼
     print, cut/fold, glue or sew, trim, case in
```

The two tracks are independent except for that one arrow: the page count.

---

## Layout

| Path | What |
|---|---|
| `book.toml` | Every measurement for one book. The only file you edit to change geometry. |
| `interior/novel.tex` | pandoc template: memoir class, mirrored margins, running heads, chapter style. |
| `interior/build.sh` | EPUB → Markdown, then Markdown → trimmed PDF. Re-enters the container itself. |
| `tools/epubtrim.py` | Drop the ebook's own front/back matter by editing the spine. |
| `tools/senorm.py` | Normalise Standard Ebooks markup into headings novel.tex can use. |
| `tools/bookspec.py` | Shared geometry. Spine width, creep, sanity checks. |
| `tools/regmark.py` | Duplex registration + printable-area test sheet. |
| `tools/impose.py` | Cut-and-stack 2-up, or folded signatures with creep. |
| `tools/coverart.py` | Cover artwork via local ComfyUI, sized from the spec at 300 dpi. |
| `tools/cover.py` | Cover wrap with computed spine and folds. |
| `source/`, `out/`, `art/` | Input text, generated PDFs, cover artwork. |

Python tools are `uv` scripts with inline dependencies — run them directly,
nothing to install. LaTeX lives in the `bookpress` distrobox (already created)
because the host is ostree-immutable.

---

## Quick start

```bash
# 0. Calibrate the printer — do this ONCE, before anything else
./tools/regmark.py                        # print duplex, read the sheet,
                                          # write flip + unprintable into book.toml

# 1. Text — trims the ebook's own front/back matter and normalises the markup
./interior/build.sh extract source/wotw.epub
$EDITOR source/book.md              # scene breaks and anything else it left
./interior/build.sh                 # → out/interior.pdf + page count + spine

#    --keep-boilerplate  keeps titlepage/imprint/colophon/uncopyright
#    --raw               skips the Standard Ebooks normaliser entirely

# 2. Sheets
./tools/impose.py --dry-run               # check the sheet map first
./tools/impose.py                         # → out/imposed-perfect.pdf

# 3. Artwork — three concepts, correctly sized and 300 dpi at print size
bash ~/start-all.sh                       # if ComfyUI is not already up
./tools/coverart.py --panel front --n 3 --name wotw "a huge dull metal cylinder ..."

# 4. Cover — only once the interior is final
./tools/cover.py --art art/wotw-a.png --guides --sheet 297x210   # proof
./tools/cover.py --art art/wotw-a.png --sheet 297x210            # print
```

---

## Order of operations

This is the critical path. Steps 1–2 are one-time; 3–8 repeat per title.

1. **Calibrate the printer.** `regmark.py`, printed duplex on the real stock.
   Gives three numbers that go straight into `book.toml`: the duplex flip
   (`imposition.flip`), the dead border (`paper.unprintable`), and the
   registration error — which is what tells you whether `interior.gutter` of
   7 mm is generous or barely adequate.
2. **Measure the paper.** 100 sheets, calipers, divide by 100 →
   `paper.caliper`. Every spine calculation downstream rests on this one
   number. Do not take it from the gsm rating.
3. **Get clean source text.** Standard Ebooks, not raw Gutenberg.
4. **Clean the Markdown once.** Strip boilerplate, fix chapter headings to
   `# Title`, convert scene breaks to `\scenebreak`.
5. **Typeset and read a proof.** Print a dozen pages 1-up at 100 % and look at
   them on paper — the measure, the leading and the gutter cannot be judged on
   a screen.
6. **Impose and print the block.** `--dry-run` first. Print two sheets, fold or
   cut them, confirm the page order by hand, *then* commit the ream.
7. **Cut, glue or sew, trim.** Page count is now frozen.
8. **Build the cover** against the frozen page count and print it.

---

## Phases

### Phase 0 — calibration *(blocked on hardware)*
Buy the printer. Run `regmark.py`. Fill in `flip`, `unprintable`, `caliper`.
Print one 16-page test signature and one 16-page cut-and-stack set on cheap
paper and bind both badly on purpose — the goal is to find out what goes wrong
before a 300-page job is on the line.

### Phase 1 — first paperback
*The War of the Worlds*, ~320 pages, B-format-ish, double-fan PVA binding,
cover printed on A4 landscape and trimmed flush. Success is a book that opens
without cracking and does not shed pages. It will not look professional and
that is fine.

### Phase 2 — sewn
Same text, `method = "sewn"`, 16-page signatures. Needs a sewing frame or a
jig, linen thread, an awl and a punching cradle. Creep compensation is already
in the imposition, so the only new variables are physical.

### Phase 3 — refinements
Drop caps (`EBGaramond-Initials.otf` is installed and unused), tipped-in
illustration plates on pigment inkjet, printed endpapers, a proper case
binding with boards, CMYK conversion if covers ever go to a commercial press.

---

## Decisions still open

- **Printer.** See `RECOMMENDATIONS.md`. Nothing here is testable until one
  exists.
- **Trim size.** 129 × 194 mm is set as the default and justified in
  `book.toml`, but it is a compromise driven by A4 and crop-mark room. Worth
  revisiting once you have held a proof.
- **Spine text direction.** Currently `down` (UK/US and every print-on-demand
  template). Dutch and German binding traditionally runs `up`. Pick one and
  keep it — a shelf of mixed directions looks like an accident.
  `cover.py --spine-direction up` switches it.
- **Cover stock and where it gets printed.** Desktop lasers largely refuse
  250 gsm; a copy shop is likely cheaper and better than a second printer.
- **Short-grain paper supplier.** Needed before the first real book, not
  before the first test.

---

## State

Built and verified:

- Interior template compiles; page size confirmed 129 × 194 mm; running heads
  correct on verso and recto; chapter openings on recto; even page count
  guaranteed; french spacing; widow/orphan/broken-word penalties set.
- Imposition maps verified against hand-worked examples for both schemes.
  Cut-and-stack collates by stacking the right pile under the left. Sewn
  signatures nest correctly, creep is applied toward the fold, and the fold
  edge carries no crop marks.
- Cover geometry verified: 320 pages → 18.14 mm spine, 282.1 × 200 mm wrap,
  which fits A4 landscape. Art bleeds on the three outer edges only.
- Crop marks fit themselves to the printable band and warn when the trim size
  leaves no room.

Not yet verified — needs hardware:

- Nothing has been physically printed. Duplex flip, registration and the dead
  border are all currently *assumed* in `book.toml`.
- `paper.caliper = 0.104` is a nominal 80 gsm figure, not a measurement.
