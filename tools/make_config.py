#!/usr/bin/env python3
"""M2: build config/functions.csv, the single function registry every tool reads.

Fire Emblem Fates ships its own symbol map (romfs/debug/name.StackTrace +
addr.StackTrace, build rev 27274), so the registry comes from that map instead of the
RTTI / vtable / sort-order inference the Awakening port needed. This entry point keeps
the old name (tools/build.py calls it) and runs tools/fates/symbols.py:

    python tools/make_config.py            == python tools/fates/symbols.py
    python tools/make_config.py --check    exit 1 if config/functions.csv is stale

Inputs:  the symbol map, extracted/analysis/functions.csv (tools/analysis/funcmap.py,
         re-run automatically when code.bin is newer), config/names.csv (hand names).
Outputs: config/functions.csv (columns in docs/SYMBOLS.md), build/symbols/symbols_report.txt.

config/data_symbols.csv is not produced yet: Fates data symbols (vtables, typeinfo,
tables) need their own pass. Tools that read it treat a missing file as "no names".
See docs/SYMBOLS.md.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    cmd = [sys.executable, str(ROOT / "tools" / "fates" / "symbols.py")] + sys.argv[1:]
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
