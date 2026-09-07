from __future__ import annotations

from typing import Optional, Sequence

from trafriend_api.scripts.calculate_mtd_rankings import main as calculate_mtd_main


def main(argv: Optional[Sequence[str]] = None) -> int:
    forwarded = ["--period", "2026-09"]
    if argv:
        forwarded.extend(argv)
    return calculate_mtd_main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
