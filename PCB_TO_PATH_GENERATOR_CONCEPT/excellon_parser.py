"""
Excellon (.drl) PCB drill-file coordinate extractor.

Reads a PTH (plated through-hole) Excellon drill file exported by
KiCad / Eagle / Altium / Fusion360 and extracts a clean list of holes:

    { "tool": "T01", "diameter_mm": 0.7, "x_mm": 12.5, "y_mm": 7.5 }

Handles the common real-world variations between EDA-tool exports:
  - units: METRIC or INCH (declared in header, or inferred from tool sizes)
  - zero suppression: leading-zero suppressed (LZ) vs trailing-zero
    suppressed (TZ) vs explicit decimal points
  - integer coordinate format (e.g. 3.3 / 2.4 digit format), read from
    header comments when present, else a sane default is used
  - explicit decimal points in coordinates (most modern exporters like
    KiCad emit these -- if present, they always win over any assumed
    format, since they're unambiguous)

Usage:
    python excellon_parser.py input.drl -o holes.csv
    python excellon_parser.py input.drl -o holes.json --format json
"""

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, asdict


@dataclass
class Hole:
    tool: str
    diameter_mm: float
    x_mm: float
    y_mm: float


class ExcellonParseError(Exception):
    pass


class ExcellonParser:
    def __init__(self):
        self.units = "metric"          # "metric" or "inch"
        self.zero_suppression = "leading"  # "leading" or "trailing"
        # integer.decimal digit counts, used only when a coordinate has
        # no explicit decimal point in it
        self.int_digits = 3
        self.dec_digits = 3
        self.tools = {}                # {"T01": diameter_mm}
        self.holes = []

    # ------------------------------------------------------------------
    # Header parsing
    # ------------------------------------------------------------------
    def _parse_header_line(self, line: str):
        upper = line.upper()

        if "METRIC" in upper:
            self.units = "metric"
            self._parse_zero_and_format(upper)
        elif "INCH" in upper:
            self.units = "inch"
            self._parse_zero_and_format(upper)

        # Tool definitions, e.g. "T1C0.700" or "T01C0.7000"
        m = re.match(r"^(T\d+)C([0-9.]+)", line, re.IGNORECASE)
        if m:
            tool_id = self._normalize_tool(m.group(1))
            diameter = float(m.group(2))
            if self.units == "inch":
                diameter *= 25.4
            self.tools[tool_id] = diameter

    def _parse_zero_and_format(self, upper_line: str):
        if "LZ" in upper_line:
            self.zero_suppression = "leading"
        elif "TZ" in upper_line:
            self.zero_suppression = "trailing"
        # Some tools declare explicit digit format like ",3.3" or ",2.4"
        m = re.search(r"(\d)\.(\d)", upper_line)
        if m:
            self.int_digits = int(m.group(1))
            self.dec_digits = int(m.group(2))

    @staticmethod
    def _normalize_tool(tool_str: str) -> str:
        """T1 -> T01, T12 -> T12 (always 2+ digit, zero-padded)."""
        digits = re.sub(r"\D", "", tool_str)
        return f"T{int(digits):02d}"

    # ------------------------------------------------------------------
    # Coordinate parsing
    # ------------------------------------------------------------------
    def _coord_to_mm(self, raw: str) -> float:
        """Convert a raw X or Y token (without the X/Y letter) to mm."""
        negative = raw.startswith("-")
        raw = raw.lstrip("+-")

        if "." in raw:
            # Explicit decimal point present -- unambiguous, always trust it.
            value = float(raw)
        else:
            # Implied decimal: pad according to declared int.dec format.
            total_digits = self.int_digits + self.dec_digits
            if self.zero_suppression == "leading":
                raw = raw.rjust(total_digits, "0")
            else:  # trailing zero suppression
                raw = raw.ljust(total_digits, "0")
            int_part = raw[: self.int_digits]
            dec_part = raw[self.int_digits:]
            value = float(f"{int_part}.{dec_part}")

        if self.units == "inch":
            value *= 25.4

        return -value if negative else value

    # ------------------------------------------------------------------
    # Main parse
    # ------------------------------------------------------------------
    def parse(self, filepath: str):
        with open(filepath, "r", errors="ignore") as f:
            lines = [ln.strip() for ln in f.readlines()]

        in_header = True
        current_tool = None
        coord_re = re.compile(
            r"X(-?[0-9.]+)?Y(-?[0-9.]+)?", re.IGNORECASE
        )

        for line in lines:
            if not line or line.startswith(";"):
                continue

            if line == "%" or line.upper() == "M95":
                in_header = False
                continue

            if line.upper() == "M48":
                in_header = True
                continue

            if in_header:
                self._parse_header_line(line)
                continue

            # Tool selection, e.g. "T01" on its own line
            m = re.match(r"^(T\d+)\s*$", line, re.IGNORECASE)
            if m:
                current_tool = self._normalize_tool(m.group(1))
                continue

            # Some files select the tool on the same logical block without
            # a header re-declare (rare) -- also catch inline "T01" prefix
            m = re.match(r"^(T\d+)(X.*)", line, re.IGNORECASE)
            if m:
                current_tool = self._normalize_tool(m.group(1))
                line = m.group(2)

            # End of program
            if line.upper().startswith("M30"):
                break

            # Coordinate line
            m = coord_re.match(line)
            if m and (m.group(1) is not None or m.group(2) is not None):
                if current_tool is None:
                    raise ExcellonParseError(
                        f"Coordinate found before any tool was selected: '{line}'"
                    )
                x_raw, y_raw = m.group(1), m.group(2)
                x_mm = self._coord_to_mm(x_raw) if x_raw is not None else 0.0
                y_mm = self._coord_to_mm(y_raw) if y_raw is not None else 0.0
                diameter = self.tools.get(current_tool)
                if diameter is None:
                    raise ExcellonParseError(
                        f"Tool {current_tool} used but never defined in header"
                    )
                self.holes.append(
                    Hole(tool=current_tool, diameter_mm=round(diameter, 4),
                         x_mm=round(x_mm, 4), y_mm=round(y_mm, 4))
                )

        if not self.holes:
            raise ExcellonParseError(
                "No holes were extracted -- check that this is a valid "
                "Excellon PTH drill file."
            )

        return self.holes


def write_csv(holes, out_path):
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["tool", "diameter_mm", "x_mm", "y_mm"])
        writer.writeheader()
        for h in holes:
            writer.writerow(asdict(h))


def write_json(holes, out_path):
    with open(out_path, "w") as f:
        json.dump([asdict(h) for h in holes], f, indent=2)


def main():
    ap = argparse.ArgumentParser(description="Extract hole coordinates from an Excellon .drl file")
    ap.add_argument("input", help="Path to the .drl (PTH) drill file")
    ap.add_argument("-o", "--output", required=True, help="Output file path")
    ap.add_argument("--format", choices=["csv", "json"], default="csv")
    args = ap.parse_args()

    parser = ExcellonParser()
    try:
        holes = parser.parse(args.input)
    except ExcellonParseError as e:
        print(f"Error parsing {args.input}: {e}", file=sys.stderr)
        sys.exit(1)

    if args.format == "csv":
        write_csv(holes, args.output)
    else:
        write_json(holes, args.output)

    print(f"Detected units: {parser.units}, zero suppression: {parser.zero_suppression}")
    print(f"Tools found: {parser.tools}")
    print(f"Extracted {len(holes)} holes -> {args.output}")


if __name__ == "__main__":
    main()
