#!/usr/bin/env python3
"""Map functions of a reference port (the Awakening port) onto this game's code by masked
byte matching: the method of scout/code-mapping.txt, recomputed and reproducible.

    python tools/readable/xmap.py                 map the reference port's readable registry
                                                  (its config/readable/functions.csv) and write
                                                  config/readable/xmap_reference.csv
    python tools/readable/xmap.py --all-ref       map every reference function (its
                                                  config/functions.csv); report only, written to
                                                  build/codetools/xmap_all.csv
    python tools/readable/xmap.py --ref DIR       reference repo (default: "reference_port" in
                                                  tools/config.local.json, else the sibling
                                                  "FE AWAKENING pc port" folder)
    python tools/readable/xmap.py --selftest      matcher on made-up code

The reference repo is only READ (code.bin, layout.json, config/functions.csv,
config/readable/functions.csv). Only addresses, names and match levels are written.

Levels (ARM code only; a function is the words from its start to the next start):
  exact   every word equal after wildcarding branch/BLX offsets (w & 0xFF000000) and
          literal-pool words (any word a PC-relative load inside the function reads)
  imm     also wildcard load/store offsets (LDR/STR 0xFFF, LDRH/LDRSB/... 0xF0F, VLDR 0xFF)
          and data-processing immediates (0xFFF): same code shape, shifted struct fields
          or constants (e.g. Unit x/y 0x90/0x91 in Awakening -> 0xF4/0xF5 in Fates)
A match is `unique` when exactly one function of this game has that masked sequence.
Tiny functions (fewer than --min-words words, default 3) are reported but never unique:
`bx lr` stubs match hundreds of places.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "readable"))
OUT = ROOT / "config" / "readable" / "xmap_reference.csv"
SCRATCH = ROOT / "build" / "codetools"
FIELDS = ["ref_address", "ref_name", "ref_kind", "ref_source", "words", "level", "unique",
          "candidates", "confidence", "address", "symbol"]


# ----------------------------------------------------------------------------- image
class Image:
    def __init__(self, code: bytes, layout: dict):
        self.code = code
        self.segs = [(layout[k]["addr"], layout[k]["addr"] + layout[k]["size"], layout[k]["file_offset"])
                     for k in ("text", "rodata", "data")]
        self.t0, self.t1, _ = self.segs[0]

    @classmethod
    def load(cls, repo: Path) -> "Image":
        return cls((repo / "extracted" / "code.bin").read_bytes(),
                   json.loads((repo / "extracted" / "layout.json").read_text()))

    def word(self, a: int) -> int:
        return struct.unpack_from("<I", self.code, a - self.t0)[0]

    def words(self, a: int, b: int) -> list[int]:
        n = (b - a) // 4
        return list(struct.unpack_from(f"<{n}I", self.code, a - self.t0)) if n > 0 else []


def pc_load_target(w: int, a: int) -> int | None:
    """Address read by a PC-relative LDR/LDRB/LDRH/LDRD/VLDR at a (ARM), else None."""
    if (w >> 28) == 0xF or ((w >> 16) & 0xF) != 15:
        return None
    up = (w >> 23) & 1
    if (w >> 26) & 3 == 1 and not (w >> 25) & 1 and (w >> 20) & 1:          # LDR(B) imm
        off = w & 0xFFF
    elif (w >> 25) & 7 == 0 and (w >> 22) & 1 and (w >> 7) & 1 and (w >> 4) & 1 and (w >> 5) & 3:
        off = ((w >> 4) & 0xF0) | (w & 0xF)                                  # LDRH/LDRSB/LDRSH/LDRD
    elif (w >> 24) & 0xF == 0xD and (w >> 8) & 0xE == 0xA and (w >> 20) & 1:  # VLDR
        off = (w & 0xFF) * 4
    else:
        return None
    return a + 8 + off if up else a + 8 - off


def mask_word(w: int, level: str) -> int:
    cond = w >> 28
    if (w >> 25) & 7 == 5:                       # B/BL, or BLX imm when cond == 0xF
        return w & (0xFE000000 if cond == 0xF else 0xFF000000)
    if level == "imm" and cond != 0xF:
        if (w >> 26) & 3 == 1 and not (w >> 25) & 1:
            return w & ~0xFFF                    # LDR/STR(B) immediate offset
        if (w >> 25) & 7 == 0 and (w >> 22) & 1 and (w >> 7) & 1 and (w >> 4) & 1 and (w >> 5) & 3:
            return w & ~0xF0F                    # halfword/signed/doubleword immediate
        if (w >> 25) & 7 == 1:
            return w & ~0xFFF                    # data processing immediate (incl. MOVW/MOVT low part)
        if (w >> 24) & 0xF == 0xD and (w >> 8) & 0xE == 0xA:
            return w & ~0xFF                     # VLDR/VSTR offset
    return w


def masked(img: Image, a: int, b: int, level: str) -> tuple:
    ws = img.words(a, b)
    pool = set()
    for i, w in enumerate(ws):
        t = pc_load_target(w, a + 4 * i)
        if t is not None and a <= t < b:
            pool.add((t - a) // 4)
            if t & 3 == 0 and (t - a) // 4 + 1 < len(ws) and (w >> 25) & 7 == 0 and (w >> 5) & 3 == 2 \
                    and not (w >> 20) & 1:
                pool.add((t - a) // 4 + 1)       # LDRD reads two words
    return tuple(None if i in pool else mask_word(w, level) for i, w in enumerate(ws))


# ----------------------------------------------------------------------------- functions
def spans_from_starts(starts: list[int], t1: int) -> dict[int, int]:
    s = sorted(set(starts))
    return {a: (s[i + 1] if i + 1 < len(s) else t1) for i, a in enumerate(s)}


def this_game_functions(img: Image) -> tuple[dict[int, int], dict[int, str]]:
    """ARM function spans of this game: config/functions.csv when present, else the
    analysis cache (build/cache/analysis.json, written by gen_asm.py) and the symbol map.
    Returns (start -> end, start -> symbol name)."""
    import symmap
    names = symmap.by_addr() if symmap.available() else {}
    fcsv = ROOT / "config" / "functions.csv"
    starts: set[int] = set()
    if fcsv.is_file():
        with fcsv.open(newline="", encoding="utf-8") as f:
            starts = {int(r["addr"], 16) for r in csv.DictReader(f)}
    cache = ROOT / "build" / "cache" / "analysis.json"
    code = None
    if cache.is_file():
        c = json.loads(cache.read_text())
        starts |= set(c["funcs"])
        code = c["code_ranges"]
    starts |= set(names)
    starts = {a for a in starts if not a & 3 and img.t0 <= a < img.t1}
    if code:                                     # ARM code only (Thumb starts are not in "A" ranges)
        lo = [r[0] for r in code]
        def is_arm(a):
            i = bisect.bisect_right(lo, a) - 1
            return i >= 0 and a < code[i][1]
        starts = {a for a in starts if is_arm(a)}
    return spans_from_starts(sorted(starts), img.t1), names


def read_ref_functions(repo: Path) -> dict[int, tuple[int, str]]:
    with (repo / "config" / "functions.csv").open(newline="", encoding="utf-8") as f:
        return {int(r["addr"], 16): (int(r["end"], 16), r["name"]) for r in csv.DictReader(f)}


def build_index(img: Image, spans: dict[int, int], level: str) -> dict[tuple, list[int]]:
    idx: dict[tuple, list[int]] = defaultdict(list)
    for a, b in spans.items():
        idx[masked(img, a, b, level)].append(a)
    return idx


def match(ref: Image, rspan: tuple[int, int], idx: dict[str, dict], min_words: int) -> tuple[str, list[int]]:
    a, b = rspan
    for level in ("exact", "imm"):
        hits = idx[level].get(masked(ref, a, b, level), [])
        if hits:
            return level, sorted(hits)
    return "none", []


def default_ref() -> Path:
    cfg = ROOT / "tools" / "config.local.json"
    if cfg.is_file():
        p = json.loads(cfg.read_text()).get("reference_port")
        if p:
            return Path(p)
    return ROOT.parent / "FE AWAKENING pc port"


def run(ref_repo: Path, all_ref: bool, min_words: int) -> int:
    ref = Image.load(ref_repo)
    me = Image.load(ROOT)
    spans, names = this_game_functions(me)
    print(f"this game: {len(spans)} ARM functions, {len(names)} symbol names")
    idx = {lv: build_index(me, spans, lv) for lv in ("exact", "imm")}
    rfuncs = read_ref_functions(ref_repo)
    if all_ref:
        rows_in = [{"address": f"0x{a:08X}", "name": n, "kind": "", "source": ""} for a, (_e, n) in sorted(rfuncs.items())]
    else:
        with (ref_repo / "config" / "readable" / "functions.csv").open(newline="", encoding="utf-8") as f:
            rows_in = [r for r in csv.DictReader(f) if (r.get("address") or "").strip()]
    out, counts = [], defaultdict(int)
    for r in rows_in:
        a = int(r["address"], 16)
        if a not in rfuncs:
            counts["ref_not_a_function"] += 1
            continue
        end = rfuncs[a][0]
        n = (end - a) // 4
        level, hits = match(ref, (a, end), idx, min_words)
        uniq = level != "none" and len(hits) == 1 and n >= min_words
        counts[f"{level}_{'unique' if uniq else ('ambiguous' if hits else 'none')}"] += 1
        h = hits[0] if len(hits) == 1 else None
        out.append({"ref_address": r["address"], "ref_name": r["name"], "ref_kind": r.get("kind", ""),
                    "ref_source": r.get("source", ""), "words": n, "level": level,
                    "unique": "yes" if uniq else "no", "candidates": len(hits),
                    "address": f"0x{h:08X}" if h is not None else "",
                    "symbol": names.get(h, "") if h is not None else ""})
    # confidence: high = exact + unique + >= 5 words; medium = imm + unique + >= 8 words;
    # low = any other unique hit. Two reference rows landing on one address are both low
    # (e.g. two 11-word option getters that differ only in a field offset).
    per_addr = defaultdict(int)
    for o in out:
        if o["unique"] == "yes":
            per_addr[o["address"]] += 1
    for o in out:
        if o["unique"] != "yes":
            o["confidence"] = ""
        elif per_addr[o["address"]] > 1:
            o["confidence"] = "low"
        elif o["level"] == "exact" and o["words"] >= 5:
            o["confidence"] = "high"
        elif o["level"] == "imm" and o["words"] >= 8:
            o["confidence"] = "medium"
        else:
            o["confidence"] = "low"
        counts[f"confidence_{o['confidence'] or 'none'}"] += 1
    dst = SCRATCH / "xmap_all.csv" if all_ref else OUT
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} reference functions: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"wrote {dst.relative_to(ROOT)}")
    return 0


# ----------------------------------------------------------------------------- selftest
def selftest() -> int:
    fails = 0

    def check(c, what):
        nonlocal fails
        fails += not c
        print(f"  {'ok  ' if c else 'FAIL'} {what}")

    def img(words: list[int]) -> Image:
        code = struct.pack(f"<{len(words)}I", *words)
        lay = {"text": {"addr": 0x100000, "size": len(code), "file_offset": 0},
               "rodata": {"addr": 0x200000, "size": 0, "file_offset": len(code)},
               "data": {"addr": 0x300000, "size": 0, "file_offset": len(code)}}
        return Image(code, lay)

    # f: ldr r0,[pc,#4] ; ldrsb r1,[r0,#0x90] ; bl X ; bx lr ; pool
    f_ref = [0xE59F0008, 0xE1D019D0, 0xEB000010, 0xE12FFF1E, 0x00401234]
    # same, other pool value and branch offset -> exact
    f_same = [0xE59F0008, 0xE1D019D0, 0xEB0000F0, 0xE12FFF1E, 0x00699999]
    # field moved 0x90 -> 0xF4 -> imm only
    f_shift = [0xE59F0008, 0xE1D01FD4, 0xEB000020, 0xE12FFF1E, 0x00401234]
    other = [0xE3A00000, 0xE12FFF1E]
    ref = img(f_ref)
    me = img(f_same + f_shift + other)
    spans = {0x100000: 0x100014, 0x100014: 0x100028, 0x100028: 0x100030}
    idx = {lv: build_index(me, spans, lv) for lv in ("exact", "imm")}
    lv, hits = match(ref, (0x100000, 0x100014), idx, 3)
    check(lv == "exact" and hits == [0x100000], f"pool + branch offset wildcarded ({lv}, {hits})")
    check(masked(ref, 0x100000, 0x100014, "exact")[4] is None, "pool word is a wildcard")
    ref2 = img(f_shift)
    lv2, hits2 = match(ref2, (0x100000, 0x100014), idx, 3)
    check(lv2 == "exact" and hits2 == [0x100014], "shifted copy matches itself exactly")
    idx_noexact = {"exact": {}, "imm": idx["imm"]}
    lv3, hits3 = match(ref, (0x100000, 0x100014), idx_noexact, 3)
    check(lv3 == "imm" and hits3 == [0x100000, 0x100014], f"imm level sees both shapes ({hits3})")
    check(mask_word(0xFA000001, "exact") == 0xFA000000 and mask_word(0xFB000001, "exact") == 0xFA000000,
          "BLX imm H bit wildcarded")
    check(pc_load_target(0xE59F0004, 0x100000) == 0x10000C, "pc load target")
    check(pc_load_target(0xE58F0004, 0x100000) is None, "pc store is not a pool read")
    check(spans_from_starts([0x10, 0x4, 0x10], 0x20) == {0x4: 0x10, 0x10: 0x20}, "spans")
    print(f"xmap selftest: {'OK' if not fails else f'{fails} failure(s)'}")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", type=Path)
    ap.add_argument("--all-ref", action="store_true")
    ap.add_argument("--min-words", type=int, default=3)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    return run(a.ref or default_ref(), a.all_ref, a.min_words)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
