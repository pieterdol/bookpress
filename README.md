# bookpress

Print and hand-bind public-domain novels at home: a typeset interior, sheets
imposed for your own duplex printer, and a cover wrap with the spine width
computed from the real page count.

Built for glued paperbacks first, sewn signatures second. *The War of the
Worlds* is the pilot title.

```
EPUB ──pandoc──► Markdown ──LuaLaTeX──► interior.pdf ──┬──► imposed sheets
                                                       └──► cover wrap
```

The one thing that ties the halves together is the page count: spine width
falls out of it, so **the cover cannot be built until the text is final**.

## Start here

- **[PLAN.md](PLAN.md)** — pipeline, quick start, order of operations, phases.
- **[RECOMMENDATIONS.md](RECOMMENDATIONS.md)** — which printer, why laser, paper
  grain direction, glue, the guillotine problem, generating cover art locally.
- **[book.toml](book.toml)** — every measurement for one book, in one file.
  Commented with the reasoning, not just the numbers.

## Quick start

```bash
./tools/regmark.py                              # calibrate the printer FIRST
./interior/build.sh extract source/book.epub    # EPUB -> Markdown
./interior/build.sh                             # -> out/interior.pdf
./tools/impose.py --dry-run                     # check the sheet map
./tools/impose.py                               # -> printable A4 sheets
./tools/cover.py --art art/front.png --sheet 297x210
```

Python tools are [uv](https://docs.astral.sh/uv/) scripts with inline
dependencies — run them directly, there is nothing to install. LaTeX is
expected in a container; see PLAN.md.

## What works, and what has not been tested

The interior template, both imposition schemes and the cover geometry are
built and verified against real output. Page maps were checked by hand.

**Nothing here has met a printer yet.** The duplex flip, the dead border and
the paper caliper in `book.toml` are placeholders. `tools/regmark.py` exists to
replace the first two with measurements, and the third wants a caliper and a
stack of 100 sheets. Every spine calculation depends on that number.

## Licensing, and what it does and does not cover

The **code and documentation** are MIT — see [LICENSE](LICENSE).

The **cover artwork** in `art/chosen/` was generated locally with ComfyUI —
Krea 2 Turbo, Z-Image Turbo, FLUX.2 klein and CyberIllustrious, one model per
image.

Whether anyone holds copyright in a purely AI-generated image is unsettled, and
the answer differs by jurisdiction. EU law requires a work to be the author's
own intellectual creation, and Dutch law asks for an *eigen oorspronkelijk
karakter en persoonlijk stempel van de maker* — tests that output produced from
a prompt alone looks unlikely to meet, though it has not been litigated. The US
Copyright Office has said as much explicitly. The UK is the outlier: s.9(3) of
the CDPA does protect computer-generated works, attributing them to whoever made
the arrangements for their creation.

The practical upshot, wherever you are: treat these files as free to use, and do
not rely on owning them. None of this is legal advice.

Each PNG carries its full workflow, prompt and seed in a `tEXt` chunk, so which
model made a given image is recorded in the file itself, along with everything
needed to reproduce it.

The **book text** is not distributed here, and `source/` is gitignored: you
supply the EPUB, and `source/book.md` is generated from it. *The War of the
Worlds* is public domain (Wells died in 1946), and
[Standard Ebooks](https://standardebooks.org) dedicate their editions to the
public domain — but check the status of any title before you commit its text
to a public repository.
