"""Shared `rando.py make` runs for a test class (round 67, release part A, goal 2).

A class lists the (seed, flags) make each test needs; setUpClass starts the makes the running suite will use, side by
side (tools/release/makes.py: fresh makes, rando cache OFF, no window, below-normal priority), and each test then reads
its own make. Every test still asserts exactly what it asserted before; only the waiting is shared.

Which tests will run is read from the suite that is calling setUpClass (plain discover, a -k filter, a single test
name, or tools/release/run_tests.py --core with tests/heavy.txt left out). If that cannot be read, every listed make is
started.
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "release"))
import makes as MK  # noqa: E402


def selected_methods(cls) -> set[str] | None:
    """names of cls's test methods in the suite now running setUpClass (from the call stack), or None"""
    f = sys._getframe(1)
    while f is not None:
        s = f.f_locals.get("self")
        if isinstance(s, unittest.TestSuite):
            names: set[str] = set()

            def walk(t):
                if isinstance(t, unittest.TestSuite):
                    for x in list(t._tests):
                        walk(x)
                elif isinstance(t, cls):
                    names.add(t._testMethodName)

            walk(s)
            if names:
                return names
        f = f.f_back
    return None


def start(cls, wanted: dict[str, tuple[str, list]], work_top: str, jobs: int | None = None) -> dict:
    """wanted = {test method name: (seed, flags)}; makes each distinct (seed, flags) the running tests need once,
    side by side, into <work_top>/<seed>; returns {(seed, tuple(flags)): makes.Made}"""
    sel = selected_methods(cls)
    need: dict[tuple, str] = {}
    for name, (seed, flags) in wanted.items():
        if sel is None or name in sel:
            need[(seed, tuple(flags))] = seed
    seeds = list(need.values())
    if len(set(seeds)) != len(seeds):
        raise ValueError(f"one folder per seed: a seed is listed with two flag sets ({sorted(seeds)})")
    specs = [(key, ["--seed", seed, *key[1]], os.path.join(work_top, seed)) for key, seed in need.items()]
    got = MK.make_many(specs, jobs or MK.default_jobs())
    return {key: got[key] for key in need}
