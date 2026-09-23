#!/usr/bin/env python3
"""Create a working copy of the public starter workspace."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "examples" / "starter"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    target = args.target.resolve()
    if target.exists():
        print(f"error: target already exists: {target}", file=sys.stderr)
        return 1
    shutil.copytree(STARTER, target)
    for name in ("drafts", "receipts"):
        (target / name).mkdir(exist_ok=True)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

