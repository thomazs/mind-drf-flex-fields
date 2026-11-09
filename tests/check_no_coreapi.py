#!/usr/bin/env python
"""
Fails if any CoreAPI reference creeps back into the package.

Removing CoreAPI is the reason this fork exists, so it is worth a check that
runs on every environment - including Windows, where the `grep` one-liner the
CI pipelines used would not work.
"""

import sys
from pathlib import Path

FORBIDDEN = ("coreapi", "coreschema")
PACKAGE = Path(__file__).resolve().parent.parent / "mind_flex_fields"


def main() -> int:
    offenders = []

    for path in sorted(PACKAGE.rglob("*.py")):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for word in FORBIDDEN:
                if word in line:
                    offenders.append((path, lineno, word, line.strip()))

    if offenders:
        print("CoreAPI references found - this fork must not depend on it:")
        for path, lineno, word, line in offenders:
            rel = path.relative_to(PACKAGE.parent)
            print(f"  {rel}:{lineno}: {word!r} in {line!r}")
        return 1

    count = len(list(PACKAGE.rglob("*.py")))
    print(f"OK: no CoreAPI references in {count} file(s) under {PACKAGE.name}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
