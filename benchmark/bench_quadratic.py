"""Reproduce the quadratic scan-loop behavior.

``LinkifyIt.match()`` exhibits quadratic slowdown on text containing many fuzzy
email candidates. The scan loop in ``linkify_it/main.py`` repeatedly slices the
remaining tail and runs an unanchored ``re.search`` over it on each iteration.

Two upstream JavaScript fixes were never ported to this package:

* linkify-it 5.0.1 -- GHSA-22p9-wv53-3rq4 / CVE-2026-48801
  "Quadratic algorithmic complexity in LinkifyIt#match scan loop"
* linkify-it 5.0.2 -- GHSA-v245-v573-v5vm / CVE-2026-59887
  "Quadratic-complexity DoS via the ``mailto:`` validator scan-loop"

This benchmark covers both cases, along with controls that isolate linkify as
the source of the slowdown. Run it before and after porting the upstream fixes:
the ``ratio`` column should fall from roughly 4x per input doubling (quadratic)
to roughly 2x (linear).

Usage::

    python benchmark/bench_quadratic.py
    python benchmark/bench_quadratic.py --max-kb 64    # full advisory table
    python benchmark/bench_quadratic.py --suite render
"""

import argparse
import platform
import time
from collections.abc import Callable, Iterator

import linkify_it
from linkify_it import LinkifyIt

try:
    import markdown_it
    from markdown_it import MarkdownIt
except ImportError:  # pragma: no cover - markdown-it-py is an extra
    markdown_it = None  # type: ignore[assignment]
    MarkdownIt = None  # type: ignore[assignment, misc]

# Signature shared by everything we time: LinkifyIt.match and
# MarkdownIt.render both take the payload and return a value we discard.
TimedCall = Callable[[str], object]

KB = 1024

# Timing the first call would fold in one-off ``re`` compilation, which is
# large enough at 4 KB to hide the growth curve. Warm up on a small payload.
WARMUP_KB = 1

# "a@b.com " repeated. Fuzzy email candidates drive the match() scan loop.
EMAIL_UNIT = "a@b.com "

# "mailto:" repeated. The ":" is a valid email-name char, so "mailto:mailto:..."
# chains into O(n) schema hits, each running the validator to the end of the tail.
MAILTO_UNIT = "mailto:"

# Consumed by an inline rule first, so this payload should stay linear.
HTTP_UNIT = "http://a.com "

# Timings published in GHSA-8m2q-wq3r-6hq8, measured by the reporter through
# MarkdownIt("gfm-like").render() against linkify-it-py 2.1.0.
REPORTED_RENDER_SECONDS: dict[int, float] = {8: 1.07, 16: 3.90, 32: 15.5, 64: 62.0}

# Same advisory: the commonmark preset, with linkify off, on a 32 KB payload.
REPORTED_CONTROL_SECONDS = 0.013


def print_environment() -> None:
    print(f"python        : {platform.python_version()} ({platform.machine()})")
    print(f"linkify-it-py : {linkify_it.__version__}")
    print(f"              : {linkify_it.__file__}")
    if markdown_it is not None:
        print(f"markdown-it-py: {markdown_it.__version__}")
    print()


def repeat_to(unit: str, kb: int) -> str:
    """Build a payload of about ``kb`` kibibytes by repeating ``unit``."""
    return unit * (kb * KB // len(unit))


def measure(fn: TimedCall, text: str) -> float:
    """Return the wall-clock seconds ``fn(text)`` takes."""
    start = time.perf_counter()
    fn(text)
    return time.perf_counter() - start


def warm_up(fn: TimedCall, unit: str) -> None:
    """Prime ``re`` caches so the first timed size is not an outlier."""
    fn(repeat_to(unit, WARMUP_KB))


def doubling_sizes(max_kb: int, start_kb: int = 4) -> Iterator[int]:
    """Yield 4, 8, 16, ... kibibytes up to and including ``max_kb``."""
    kb = start_kb
    while kb <= max_kb:
        yield kb
        kb *= 2


def eval(ratios: list[float]) -> str:
    """Classify growth from the per-doubling time ratios."""
    if not ratios:
        return "not enough data points"

    average = sum(ratios) / len(ratios)
    if average >= 3.0:
        return f"QUADRATIC: {average:.2f}x per doubling (quadratic is ~4x)"
    if average <= 2.5:
        return f"linear: {average:.2f}x per doubling (linear is ~2x)"
    return f"inconclusive: {average:.2f}x per doubling"


def run_scaling(
    title: str,
    unit: str,
    fn: TimedCall,
    max_kb: int,
    reported: dict[int, float] | None = None,
) -> None:
    """Time ``fn`` over doubling payload sizes and print a scaling table."""
    print(f"=== {title} ===")
    print(f'payload: "{unit}" repeated')
    print()

    header = f"{'size':>7} {'n (bytes)':>11} {'time':>12} {'t/n^2':>14} {'ratio':>8}"
    if reported:
        header += f" {'reported':>11}"
    print(header)

    warm_up(fn, unit)

    previous: float | None = None
    ratios: list[float] = []
    for kb in doubling_sizes(max_kb):
        text = repeat_to(unit, kb)
        elapsed = measure(fn, text)
        n = len(text)

        if previous is None:
            ratio = "--"
        else:
            ratios.append(elapsed / previous)
            ratio = f"{ratios[-1]:.2f}x"
        previous = elapsed

        row = (
            f"{kb:>4} KB {n:>11} {elapsed:>10.3f} s "
            f"{elapsed / n**2 * 1e9:>11.3f}e-9 {ratio:>8}"
        )
        if reported:
            expected = reported.get(kb)
            row += f" {expected:>9.2f} s" if expected else f" {'-':>11}"
        print(row, flush=True)

    print(f"-> {eval(ratios)}")
    print()


def require_markdown_it() -> bool:
    """Return ``True`` if markdown-it-py is importable, else explain and skip."""
    if MarkdownIt is not None:
        return True
    print("(skipped: markdown-it-py is not installed -- pip install markdown-it-py)")
    print()
    return False


def suite_email(max_kb: int) -> None:
    linkify = LinkifyIt()
    run_scaling(
        "fuzzy email scan loop, LinkifyIt.match() -- CVE-2026-48801",
        EMAIL_UNIT,
        linkify.match,
        max_kb,
    )


def suite_mailto(max_kb: int) -> None:
    linkify = LinkifyIt()
    run_scaling(
        "mailto: validator scan loop, LinkifyIt.match() -- CVE-2026-59887",
        MAILTO_UNIT,
        linkify.match,
        max_kb,
    )


def suite_render(max_kb: int) -> None:
    """Reproduce the advisory's own configuration, end to end."""
    if not require_markdown_it():
        return

    md = MarkdownIt("gfm-like")
    run_scaling(
        "MarkdownIt('gfm-like').render(), linkify on -- advisory configuration",
        EMAIL_UNIT,
        md.render,
        max_kb,
        reported=REPORTED_RENDER_SECONDS,
    )


def suite_controls(max_kb: int) -> None:
    """Show that linkify, not the gfm-like preset, is the trigger."""
    if not require_markdown_it():
        return

    print("=== controls ===")
    print()

    text = repeat_to(EMAIL_UNIT, max_kb)

    commonmark = MarkdownIt("commonmark")
    warm_up(commonmark.render, EMAIL_UNIT)
    baseline = measure(commonmark.render, text)
    print(
        f"{max_kb} KB email payload, commonmark (linkify off) : "
        f"{baseline:>9.4f} s   (reported {REPORTED_CONTROL_SECONDS:.3f} s"
        f" at 32 KB)"
    )

    gfm_off = MarkdownIt("gfm-like")
    gfm_off.options["linkify"] = False
    warm_up(gfm_off.render, EMAIL_UNIT)
    print(
        f"{max_kb} KB email payload, gfm-like, linkify=False  : "
        f"{measure(gfm_off.render, text):>9.4f} s"
    )

    gfm_on = MarkdownIt("gfm-like")
    warm_up(gfm_on.render, EMAIL_UNIT)
    on = measure(gfm_on.render, text)
    print(
        f"{max_kb} KB email payload, gfm-like, linkify=True   : "
        f"{on:>9.4f} s   ({on / baseline:.0f}x slower)"
    )
    print()

    run_scaling(
        "http:// payload -- consumed by an inline rule, expected to stay linear",
        HTTP_UNIT,
        gfm_on.render,
        max_kb,
    )


SUITES: dict[str, Callable[[int], None]] = {
    "email": suite_email,
    "mailto": suite_mailto,
    "render": suite_render,
    "controls": suite_controls,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--max-kb",
        type=int,
        default=32,
        help="largest payload size in KiB (default: 32; use 64 for the"
        " full advisory table, which takes about a minute)",
    )
    parser.add_argument(
        "--suite",
        choices=["all", *SUITES],
        default="all",
        help="which measurement to run (default: all)",
    )
    args = parser.parse_args()

    print_environment()

    names = list(SUITES) if args.suite == "all" else [args.suite]
    for name in names:
        SUITES[name](args.max_kb)


if __name__ == "__main__":
    main()
