#!/usr/bin/env bash
# bookpress — build the interior text block from an EPUB.
#
#   ./interior/build.sh extract source/wotw.epub   # EPUB -> Markdown, once
#   ./interior/build.sh                            # Markdown -> out/interior.pdf
#
# The two steps are separate on purpose. Going straight from EPUB to PDF works
# and is tempting, but you only get one shot at fixing the source: scene
# breaks, chapter titles, the Gutenberg boilerplate, stray <br> runs. Do that
# once in Markdown, keep it in git, and rebuild the PDF as often as you like.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# All the typesetting lives in the container; re-enter if we are on the host.
if [[ ! -e /run/.containerenv && -z "${BOOKPRESS_IN_CONTAINER:-}" ]]; then
  exec distrobox enter bookpress -- env BOOKPRESS_IN_CONTAINER=1 \
    "$ROOT/interior/build.sh" "$@"
fi

SPEC="${BOOKPRESS_SPEC:-$ROOT/book.toml}"
SRC="$ROOT/source/book.md"
OUT="$ROOT/out/interior.pdf"

# ------------------------------------------------------------------ extract --
if [[ "${1:-}" == "extract" ]]; then
  EPUB="${2:?usage: build.sh extract <file.epub>}"
  mkdir -p "$ROOT/source/media"
  pandoc "$EPUB" \
    --to=markdown \
    --wrap=none \
    --extract-media="$ROOT/source/media" \
    --output="$SRC"
  echo "wrote $SRC"
  echo
  echo "Now read it. Things worth fixing before you typeset:"
  echo "  - Project Gutenberg / Standard Ebooks front and back matter"
  echo "  - chapter headings: they must be '# Title' for --top-level-division"
  echo "  - scene breaks: replace bare '---' or '* * *' with \\scenebreak"
  echo "  - hard line breaks left over from the EPUB's own layout"
  exit 0
fi

[[ -f "$SRC" ]] || { echo "no $SRC — run: build.sh extract <file.epub>" >&2; exit 1; }

# ---------------------------------------------------- spec -> pandoc -V flags --
# memoir's class sizes are discrete; leading is not. Resolve both here so the
# template stays free of arithmetic.
mapfile -t V < <(python3 - "$SPEC" <<'PY'
import sys, tomllib

with open(sys.argv[1], "rb") as fh:
    s = tomllib.load(fh)

trim, inter, book = s["trim"], s["interior"], s["book"]

size = inter.get("font_size", "11pt").removesuffix("pt")
lead = float(inter.get("leading", "15pt").removesuffix("pt"))

# Default \baselineskip the standard classes give each size. linespread is a
# multiplier on that, so we need the real value, not 1.2 x size.
BASELINE = {"9": 11.0, "10": 12.0, "11": 13.6, "12": 14.5, "14": 18.0, "17": 22.0}
if size not in BASELINE:
    sys.exit(f"interior.font_size must be one of {sorted(BASELINE, key=float)} pt, got {size}")

print(f"fontsize={size}pt")
print(f"linespread={lead / BASELINE[size]:.4f}")
print(f"trimwidth={trim['width']}mm")
print(f"trimheight={trim['height']}mm")
print(f"innermargin={inter['margin_inner'] + inter['gutter']}mm")
print(f"outermargin={inter['margin_outer']}mm")
print(f"topmargin={inter['margin_top']}mm")
print(f"bottommargin={inter['margin_bottom']}mm")
print(f"booktitle={book['title']}")
print(f"author={book['author']}")
if book.get("subtitle"):
    print(f"subtitle={book['subtitle']}")
if book.get("year"):
    print(f"year={book['year']}")
PY
)

ARGS=()
for kv in "${V[@]}"; do ARGS+=(-V "$kv"); done

mkdir -p "$ROOT/out"
pandoc "$SRC" \
  --from=markdown \
  --template="$ROOT/interior/novel.tex" \
  --pdf-engine=lualatex \
  --top-level-division=chapter \
  "${ARGS[@]}" \
  --output="$OUT"

# pdfinfo, not a regex over the bytes: LuaTeX writes compressed object
# streams, so /Count never appears as plain text in the file.
PAGES=$(pdfinfo "$OUT" | awk '/^Pages:/{print $2}')

echo
echo "wrote $OUT — $PAGES pages"
if [[ $((PAGES % 4)) -ne 0 ]]; then
  echo "note: imposition will pad to $(( (PAGES + 3) / 4 * 4 )) with blanks"
fi
echo "spine at this page count:"
python3 - "$SPEC" "$PAGES" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as fh:
    s = tomllib.load(fh)
pages = int(sys.argv[2])
p = s["paper"]["caliper"]
g = s["binding"].get("glue_allowance", 1.5)
print(f"  {pages/2:.0f} leaves x {p} mm + {g} mm glue = {pages/2*p + g:.1f} mm")
PY
exit 0
