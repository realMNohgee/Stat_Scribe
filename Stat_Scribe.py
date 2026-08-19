from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

# Explicit description constant. (The __future__ import occupies line 1, so a
# module docstring placed after it would NOT be the first statement and the
# module __doc__ would be None. We therefore never rely on __doc__.)
_DESCRIPTION = """\
Stat_Scribe — zero-dependency descriptive statistics for the command line.

Compute descriptive statistics (describe) or render an ASCII histogram (hist)
from a comma-separated list of numbers, a file containing numbers, or stdin.

Domains: data analysis · statistics · quality assurance · finance · agent tools.
"""

_PROG = "Stat_Scribe"

# Matches an integer token (optional sign + digits) so we can preserve exact
# integer arithmetic for whole-number inputs instead of forcing everything to float.
_INT_RE = re.compile(r"^[+-]?\d+$")

# Maps a --delimiter keyword to its split character. None means "auto" (split
# on runs of commas and/or whitespace), which handles commas, tabs, and spaces.
_DELIMITERS = {
    "auto": None,
    "any": None,
    "whitespace": None,
    "comma": ",",
    "tab": "\t",
    "space": " ",
    ",": ",",
    "\t": "\t",
    " ": " ",
}

# Ordered (key, human label) pairs that drive the text rendering of describe.
_LABELS = [
    ("n", "n"),
    ("sum", "sum"),
    ("min", "min"),
    ("max", "max"),
    ("range", "range"),
    ("mean", "mean"),
    ("median", "median"),
    ("mode", "mode"),
    ("sample_variance", "sample variance"),
    ("sample_std_dev", "sample std dev"),
    ("q1", "Q1"),
    ("q3", "Q3"),
    ("iqr", "IQR"),
    ("skewness", "skewness (g1)"),
    ("excess_kurtosis", "excess kurtosis (g2)"),
]


class StatError(Exception):
    """User-facing error; caught in main() and printed to stderr with exit 1."""


def _fail(msg):
    """Raise a StatError carrying the user-facing message."""
    raise StatError(msg)


def _to_number(token):
    """Convert a token to int (if integer-shaped) or float; reject non-finite."""
    # Preserve ints so sums/min/max/range stay exact for whole-number data.
    if _INT_RE.match(token):
        return int(token)
    value = float(token)
    # Reject inf/nan — they would poison every downstream statistic.
    if not math.isfinite(value):
        raise ValueError(token)
    return value


def _tokenize(text, delimiter):
    """Split raw text into non-empty tokens per the requested delimiter."""
    # Validate the delimiter keyword up front so bad values fail with a clear message.
    if delimiter not in _DELIMITERS:
        _fail(f"unknown delimiter {delimiter!r} (use comma, tab, space, or auto)")
    sep = _DELIMITERS[delimiter]
    if sep is None:
        # auto: split on runs of commas and/or any whitespace (incl. newlines).
        return [t for t in re.split(r"[,\s]+", text) if t]
    # Explicit separator: split line-by-line first so multi-line files work
    # even when the user forces a single-character delimiter.
    tokens = []
    for line in text.splitlines():
        for piece in line.split(sep):
            piece = piece.strip()
            if piece:
                tokens.append(piece)
    return tokens


def _parse_numbers(tokens, source_desc):
    """Convert tokens to numbers, skipping (with a stderr warning) non-numeric ones."""
    numbers = []
    skipped = 0
    for tok in tokens:
        try:
            numbers.append(_to_number(tok))
        except ValueError:
            skipped += 1
            print(f"warning: skipping non-numeric token {tok!r} (in {source_desc})",
                  file=sys.stderr)
    return numbers, skipped


def _looks_like_path(text):
    """Heuristic: does a string look like a file path rather than a literal list?"""
    if text.startswith(("~", ".", "/", "\\")):
        return True
    if "/" in text or "\\" in text:
        return True
    # Common data-file extensions signal "this is a file, not a number list".
    if re.search(r"\.(txt|csv|tsv|dat|data|numbers|log)$", text, re.IGNORECASE):
        return True
    return False


def _resolve_input(source):
    """Resolve INPUT into raw text + a source label, handling '-', files, and literals."""
    # '-' means read stdin.
    if source == "-":
        data = sys.stdin.read()
        if not data.strip():
            _fail("no input provided on stdin")
        return data, "<stdin>"
    # An existing path is read as a file.
    if os.path.isfile(source):
        try:
            with open(source, "r", encoding="utf-8") as fh:
                data = fh.read()
        except OSError as exc:
            _fail(f"cannot read file {source!r}: {exc}")
        if not data.strip():
            _fail(f"file {source!r} is empty")
        return data, source
    # A path-like string that does not exist is a missing file (nonzero exit).
    if _looks_like_path(source):
        _fail(f"file not found: {source}")
    # Otherwise treat INPUT as a literal list of numbers.
    return source, "<literal list>"


def _collect_numbers(source, delimiter):
    """Resolve INPUT and return the list of numeric values plus a source label."""
    text, source_desc = _resolve_input(source)
    tokens = _tokenize(text, delimiter)
    numbers, _skipped = _parse_numbers(tokens, source_desc)
    if not numbers:
        _fail(f"no valid numeric values found in {source_desc}")
    return numbers, source_desc


def _median(sorted_data):
    """Return the median of an already-sorted list (None if empty)."""
    n = len(sorted_data)
    if n == 0:
        return None
    mid = n // 2
    if n % 2 == 1:
        return sorted_data[mid]
    return (sorted_data[mid - 1] + sorted_data[mid]) / 2.0


def _quartiles(sorted_data):
    """Return (q1, q3) via the median-of-halves method (median excluded from halves).

    The median splits the sorted data into a lower half and an upper half; Q1 is
    the median of the lower half and Q3 the median of the upper half. When n is
    odd the middle (median) value is excluded from both halves.
    """
    n = len(sorted_data)
    if n == 1:
        # Single value: every quartile collapses onto that value.
        return sorted_data[0], sorted_data[0]
    mid = n // 2
    if n % 2 == 1:
        lower = sorted_data[:mid]
        upper = sorted_data[mid + 1:]
    else:
        lower = sorted_data[:mid]
        upper = sorted_data[mid:]
    return _median(lower), _median(upper)


def _modes(sorted_data):
    """Return the list of modes (values sharing the max frequency), [] if none."""
    counts = {}
    for v in sorted_data:
        counts[v] = counts.get(v, 0) + 1
    max_count = max(counts.values())
    if max_count <= 1:
        return []  # every value is unique -> no mode
    return sorted(v for v, c in counts.items() if c == max_count)


def _sample_variance(data, mean):
    """Sample variance using the (n - 1) denominator; None when n < 2."""
    n = len(data)
    if n < 2:
        return None
    return sum((x - mean) ** 2 for x in data) / (n - 1)


def _skewness(data, mean, std):
    """Adjusted Fisher-Pearson coefficient of skewness g1 (None when n < 3 or flat)."""
    n = len(data)
    if n < 3 or std is None or std == 0:
        return None
    m3 = sum((x - mean) ** 3 for x in data)
    return (n / ((n - 1) * (n - 2))) * m3 / (std ** 3)


def _excess_kurtosis(data, mean, std):
    """Unbiased excess kurtosis g2 (None when n < 4 or flat)."""
    n = len(data)
    if n < 4 or std is None or std == 0:
        return None
    m4 = sum((x - mean) ** 4 for x in data)
    term = (n * (n + 1)) / ((n - 1) * (n - 2) * (n - 3)) * m4 / (std ** 4)
    correction = (3 * (n - 1) ** 2) / ((n - 2) * (n - 3))
    return term - correction


def _fmt_num(v):
    """Compact human formatting for a number (integer-valued floats shown as ints)."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 1e16:
            return str(int(v))
        return f"{v:.10g}"
    return str(v)


def _round_sig(v, sig=12):
    """Round a float to `sig` significant digits (ints pass through) for clean JSON."""
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v == 0 or not math.isfinite(v):
            return v
        return float(f"{v:.{sig}g}")
    return v


def _jsonify(obj):
    """Recursively round floats to 12 significant digits for clean JSON output."""
    if isinstance(obj, float):
        return _round_sig(obj)
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    return obj


def _render_value(key, value):
    """Format a single describe result value for text output."""
    if value is None:
        return "n/a"
    if key == "mode":
        if not value:
            return "none (no repeated values)"
        return ", ".join(_fmt_num(m) for m in value)
    if isinstance(value, list):
        return ", ".join(_fmt_num(v) for v in value)
    return _fmt_num(value)


def _emit_text(result):
    """Print the describe result dict as a human-readable key/value block."""
    for key, label in _LABELS:
        print(f"{label}: {_render_value(key, result[key])}")


def cmd_describe(args):
    """Compute and emit descriptive statistics for INPUT."""
    numbers, _ = _collect_numbers(args.input, args.delimiter)
    data = sorted(numbers)
    n = len(data)

    total = sum(data)
    mn = data[0]
    mx = data[-1]
    rng = mx - mn
    mean = total / n
    median = _median(data)
    modes = _modes(data)
    var = _sample_variance(data, mean)
    std = math.sqrt(var) if var is not None else None
    q1, q3 = _quartiles(data)
    iqr = q3 - q1
    g1 = _skewness(data, mean, std)
    g2 = _excess_kurtosis(data, mean, std)

    result = {
        "n": n,
        "sum": total,
        "min": mn,
        "max": mx,
        "range": rng,
        "mean": mean,
        "median": median,
        "mode": modes,
        "sample_variance": var,
        "sample_std_dev": std,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "skewness": g1,
        "excess_kurtosis": g2,
    }

    if args.format == "json":
        print(json.dumps(_jsonify(result), indent=2))
    else:
        _emit_text(result)
    return 0


def _build_histogram(data, n_bins):
    """Return (bins, counts, note) for a sorted dataset split into n_bins bins.

    bins is a list of (low, high) tuples and counts the aligned counts. The last
    bin's upper edge is inclusive of the maximum so no value is lost.
    """
    mn = data[0]
    mx = data[-1]
    # Degenerate case: every value is identical -> single bin, no usable width.
    if mn == mx:
        return [(mn, mn)], [len(data)], "note: all values are equal (min == max); single bin shown"

    span = mx - mn
    bin_width = span / n_bins
    # Build edges, then force the top edge to exactly mx to dodge float drift.
    edges = [mn + i * bin_width for i in range(n_bins + 1)]
    edges[-1] = mx
    counts = [0] * n_bins
    for v in data:
        idx = int((v - mn) / bin_width)
        if idx >= n_bins:
            idx = n_bins - 1  # clamp the max value into the final (inclusive) bin
        counts[idx] += 1
    bins = [(edges[i], edges[i + 1]) for i in range(n_bins)]
    return bins, counts, None


def _render_hist_text(bins, counts, width, note):
    """Render the histogram as ASCII text (auto-scaled '#' bars to the max bin)."""
    max_count = max(counts) if counts else 0
    # Format edge labels first so we can right-align every line consistently.
    lo_labels = [_fmt_num(lo) for lo, _ in bins]
    hi_labels = [_fmt_num(hi) for _, hi in bins]
    lo_w = max(len(s) for s in lo_labels) if lo_labels else 1
    hi_w = max(len(s) for s in hi_labels) if hi_labels else 1

    lines = ["histogram (auto-scaled: '#' length is proportional to bin count)"]
    if note:
        lines.append(note)
    for i, ((_lo, _hi), c) in enumerate(zip(bins, counts)):
        close = "]" if i == len(bins) - 1 else ")"  # last bin inclusive of max
        lo_s = lo_labels[i].rjust(lo_w)
        hi_s = hi_labels[i].rjust(hi_w)
        bar_len = int(round(c / max_count * width)) if max_count else 0
        bar = "#" * bar_len
        lines.append(f"[{lo_s}, {hi_s}{close} | {bar:<{width}} {c}")
    return "\n".join(lines)


def cmd_hist(args):
    """Render an ASCII histogram of INPUT."""
    # Validate cheap numeric flags before doing any file I/O.
    if args.bins < 1:
        _fail("--bins must be a positive integer")
    if args.width < 1:
        _fail("--width must be a positive integer")

    numbers, _ = _collect_numbers(args.input, args.delimiter)
    data = sorted(numbers)
    bins, counts, note = _build_histogram(data, args.bins)

    if args.format == "json":
        result = {
            "n": len(data),
            "bins": len(bins),
            "width": args.width,
            "min": data[0],
            "max": data[-1],
            "note": note,
            "histogram": [
                {"bin": i, "low": _round_sig(lo), "high": _round_sig(hi), "count": c}
                for i, ((lo, hi), c) in enumerate(zip(bins, counts))
            ],
        }
        print(json.dumps(_jsonify(result), indent=2))
    else:
        print(_render_hist_text(bins, counts, args.width, note))
    return 0


def build_parser():
    """Build the argparse parser with a shared --format parent (before AND after)."""
    # Shared parent: --format works both before and after the subcommand. Using
    # default=SUPPRESS means the flag only sets the attribute when actually
    # passed, so the top-level and subparser copies never stomp each other.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--format", choices=["text", "json"],
                        default=argparse.SUPPRESS,
                        help="Output format: text or json (default: text)")

    parser = argparse.ArgumentParser(
        prog=_PROG,
        description=_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[common],
    )
    sub = parser.add_subparsers(dest="cmd", required=True,
                                metavar="{describe,hist}")

    # describe: full descriptive-statistics report.
    sp_describe = sub.add_parser(
        "describe", parents=[common],
        help="Compute descriptive statistics for a list or file of numbers.",
        description="Compute n, sum, min, max, range, mean, median, mode(s), "
                    "sample variance, sample std dev, Q1/median/Q3, IQR, "
                    "skewness (g1), and excess kurtosis (g2).",
    )
    sp_describe.add_argument("input",
                             help="Comma-separated list of numbers, a file path, "
                                  "or '-' for stdin.")
    sp_describe.add_argument("--delimiter", default="auto",
                             help="Token separator: comma, tab, space, or auto "
                                  "(default: auto = commas + whitespace).")
    sp_describe.set_defaults(func=cmd_describe)

    # hist: ASCII histogram.
    sp_hist = sub.add_parser(
        "hist", parents=[common],
        help="Render an ASCII histogram of a list or file of numbers.",
        description="Render an ASCII histogram with a configurable bin count and "
                    "bar width, auto-scaled to the largest bin.",
    )
    sp_hist.add_argument("input",
                         help="Comma-separated list of numbers, a file path, "
                              "or '-' for stdin.")
    sp_hist.add_argument("--bins", type=int, default=10,
                         help="Number of bins (default: 10).")
    sp_hist.add_argument("--width", type=int, default=50,
                         help="Max bar width in characters (default: 50).")
    sp_hist.add_argument("--delimiter", default="auto",
                         help="Token separator: comma, tab, space, or auto "
                              "(default: auto).")
    sp_hist.set_defaults(func=cmd_hist)

    return parser


def main(argv=None):
    """Parse args, resolve the --format fallback, dispatch, and handle errors."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        # Fallback: --format uses SUPPRESS, so an unset attribute means "text".
        args.format = getattr(args, "format", None) or "text"
        return args.func(args)
    except StatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
