"""Shared geometry for the bookpress toolchain.

Everything here is millimetres. Points appear only at the boundary where a
value is handed to a PDF library, via mm(). Keeping the conversion in one
place is the difference between a spine that fits and one that is off by the
72/25.4 you forgot somewhere.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

MM = 72.0 / 25.4


def mm(value: float) -> float:
    """Millimetres to PostScript points."""
    return value * MM


def find_spec(explicit: str | None = None) -> Path:
    """Locate book.toml: an explicit path, else the project root above tools/."""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            raise SystemExit(f"spec not found: {p}")
        return p
    root = Path(__file__).resolve().parent.parent
    p = root / "book.toml"
    if not p.is_file():
        raise SystemExit(f"no book.toml at {p} (pass --spec)")
    return p


@dataclass(frozen=True)
class Spec:
    raw: dict
    path: Path

    # -- passthrough sections ------------------------------------------------

    @property
    def book(self) -> dict:
        return self.raw["book"]

    @property
    def trim_w(self) -> float:
        return self.raw["trim"]["width"]

    @property
    def trim_h(self) -> float:
        return self.raw["trim"]["height"]

    @property
    def caliper(self) -> float:
        return self.raw["paper"]["caliper"]

    @property
    def sheet_w(self) -> float:
        return self.raw["paper"]["sheet_width"]

    @property
    def sheet_h(self) -> float:
        return self.raw["paper"]["sheet_height"]

    @property
    def unprintable(self) -> float:
        return self.raw["paper"].get("unprintable", 4.5)

    @property
    def method(self) -> str:
        return self.raw["binding"]["method"]

    @property
    def sheets_per_sig(self) -> int:
        return int(self.raw["binding"]["sheets_per_signature"])

    @property
    def glue_allowance(self) -> float:
        return self.raw["binding"].get("glue_allowance", 1.5)

    @property
    def column_gap(self) -> float:
        return self.raw["imposition"].get("column_gap", 10.0)

    @property
    def flip(self) -> str:
        return self.raw["imposition"].get("flip", "long")

    @property
    def bleed(self) -> float:
        return self.raw["cover"].get("bleed", 3.0)

    @property
    def safe(self) -> float:
        return self.raw["cover"].get("safe", 8.0)

    # -- derived geometry ----------------------------------------------------

    @property
    def imposed_w(self) -> float:
        """Width of a 2-up sheet, landscape: the long edge of the paper."""
        return max(self.sheet_w, self.sheet_h)

    @property
    def imposed_h(self) -> float:
        return min(self.sheet_w, self.sheet_h)

    def spine_width(self, page_count: int) -> float:
        """Thickness of the finished text block, in mm.

        page_count is *pages* (numbered sides). Two pages make one leaf, and
        it is leaves that have thickness — this /2 is the single most common
        place a spine goes wrong by a factor of two.
        """
        leaves = page_count / 2.0
        return leaves * self.caliper + self.glue_allowance

    def creep(self, sheet_index: int, sheets_in_sig: int) -> float:
        """Fore-edge push-out of one sheet inside a folded signature, in mm.

        sheet_index is 0 for the OUTERMOST sheet and grows inward. When n
        sheets are nested and folded, sheet k must wrap around everything
        inside it; the fold consumes paper proportional to that core's
        thickness, so inner sheets reach further toward the fore edge and
        lose more to the trim. The innermost sheet protrudes by
        (n-1) * caliper relative to the outermost.

        The returned value is how far this sheet's content must shift back
        toward the spine to survive the trim with the same margins as the
        outermost sheet.
        """
        if sheets_in_sig <= 1:
            return 0.0
        return sheet_index * self.caliper

    # -- sanity --------------------------------------------------------------

    def check(self) -> list[str]:
        """Return a list of human-readable warnings. Empty means plausible."""
        warn: list[str] = []

        span = 2 * self.trim_w + self.column_gap
        if span > self.imposed_w:
            warn.append(
                f"2-up does not fit: 2 x {self.trim_w} + {self.column_gap} gap "
                f"= {span:.1f} mm > {self.imposed_w:.1f} mm sheet width. "
                f"Reduce trim.width or imposition.column_gap."
            )
        else:
            side = (self.imposed_w - span) / 2
            if side < self.unprintable:
                warn.append(
                    f"only {side:.1f} mm outboard of the trim edge; crop marks "
                    f"land inside the {self.unprintable} mm unprintable border "
                    f"and will not appear. Use --marks inboard, or narrow the page."
                )

        if self.trim_h > self.imposed_h:
            warn.append(
                f"trim.height {self.trim_h} mm exceeds sheet height "
                f"{self.imposed_h:.1f} mm."
            )
        else:
            band = (self.imposed_h - self.trim_h) / 2
            if band < self.unprintable:
                warn.append(
                    f"only {band:.1f} mm above/below the trim edge; horizontal "
                    f"crop marks fall in the unprintable border. Shorten "
                    f"trim.height to {self.imposed_h - 2 * self.unprintable - 2:.0f} mm "
                    f"or less for visible marks."
                )

        if self.caliper > 0.3:
            warn.append(
                f"caliper {self.caliper} mm is very thick for text stock — did "
                f"you measure one sheet or a stack of ten?"
            )
        if self.method == "sewn" and self.sheets_per_sig * self.caliper > 1.6:
            warn.append(
                f"{self.sheets_per_sig} sheets per signature gives "
                f"{(self.sheets_per_sig - 1) * self.caliper:.2f} mm of creep; "
                f"consider fewer sheets per signature."
            )
        return warn


def load(explicit: str | None = None) -> Spec:
    path = find_spec(explicit)
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    return Spec(raw=raw, path=path)
