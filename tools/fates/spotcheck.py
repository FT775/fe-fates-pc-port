#!/usr/bin/env python3
"""Check the symbol-map names in config/functions.csv against the code they label.

The map is for build rev 27274; the cart's code could in principle be a different build,
so names are checked against what the ARM code actually does:

  1. svc        every `.nn.svc.<Name>` wrapper must contain `svc #N` with the 3DS SVC
                number of <Name> (numbers from the public 3dbrew SVC table).
  2. starts     the first word of every symbol-map ARM start decodes as a valid ARM
                instruction (tools/analysis/funcmap.py decoder), and the word before it
                ends the previous function (return / branch / literal / padding).
  3. accessors  tiny `Get*`/`Is*`/`Has*` functions (2 instructions) must load into r0 or
                set r0, then return; tiny `Set*` functions must store r1 (or s0).
  4. vtables    a constructor `X::X` that loads a vtable whose slots are text addresses:
                at least one slot is named `X::...` (or a thunk of X); compared with a
                shuffled baseline (constructor names rotated).
  5. random     20 random named game functions (fixed seed) disassembled with objdump,
                calls resolved to names, written to build/symbols/spotcheck20.txt for
                review by eye (the verdicts are recorded in docs/SYMBOLS.md).

Usage:
    python tools/fates/spotcheck.py [--seed N] [--count 20]
Exit status 1 if check 1 or 2 finds a mismatch, or 3/4 fall under their thresholds.
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "analysis"))
from gamecfg import GAME  # noqa: E402
import funcmap as FM  # noqa: E402
sys.path.insert(0, str(ROOT / "tools" / "fates"))
import symbols as S  # noqa: E402

OUT = ROOT / "build" / "symbols"
CODE = (ROOT / "extracted" / "code.bin")

# 3DS kernel SVC numbers (3dbrew "SVC" page: public documentation, facts only).
SVC = {"ControlMemory": 0x01, "QueryMemory": 0x02, "ExitProcess": 0x03, "CreateThread": 0x08,
       "ExitThread": 0x09, "SleepThread": 0x0A, "GetThreadPriority": 0x0B, "SetThreadPriority": 0x0C,
       "CreateMutex": 0x13, "ReleaseMutex": 0x14, "CreateSemaphore": 0x15, "ReleaseSemaphore": 0x16,
       "CreateEvent": 0x17, "SignalEvent": 0x18, "ClearEvent": 0x19, "CreateTimer": 0x1A,
       "SetTimer": 0x1B, "CancelTimer": 0x1C, "ClearTimer": 0x1D, "CreateMemoryBlock": 0x1E,
       "MapMemoryBlock": 0x1F, "UnmapMemoryBlock": 0x20, "CreateAddressArbiter": 0x21,
       "ArbitrateAddress": 0x22, "CloseHandle": 0x23, "WaitSynchronization1": 0x24,
       "WaitSynchronizationN": 0x25, "SignalAndWait": 0x26, "DuplicateHandle": 0x27,
       "GetSystemTick": 0x28, "GetHandleInfo": 0x29, "GetSystemInfo": 0x2A, "GetProcessInfo": 0x2B,
       "GetThreadInfo": 0x2C, "ConnectToPort": 0x2D, "SendSyncRequest": 0x32, "OpenProcess": 0x33,
       "OpenThread": 0x34, "GetProcessId": 0x35, "GetProcessIdOfThread": 0x36, "GetThreadId": 0x37,
       "GetResourceLimit": 0x38, "GetResourceLimitLimitValues": 0x39,
       "GetResourceLimitCurrentValues": 0x3A, "GetThreadContext": 0x3B, "Break": 0x3C,
       "OutputDebugString": 0x3D}


class Code:
    def __init__(self):
        self.d = CODE.read_bytes()
        t = GAME.seg("text")
        self.t0, self.t1 = t.vaddr, t.end
        self.segs = [(GAME.seg(n).vaddr, GAME.seg(n).end) for n in ("text", "rodata", "data")]

    def u32(self, a: int) -> int | None:
        for lo, hi in self.segs:
            if lo <= a and a + 4 <= hi:
                o = a - self.t0
                return int.from_bytes(self.d[o:o + 4], "little")
        return None

    def in_data(self, a: int) -> bool:
        return any(lo <= a < hi for lo, hi in self.segs[1:])


def load_rows() -> list[dict]:
    with (ROOT / "config" / "functions.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["a"] = int(r["addr"], 16)
        r["e"] = int(r["end"], 16)
    return rows


def base_name(sig: str) -> tuple[str, str]:
    _, qual, _ = S.split_signature(sig)
    return S.split_scope(qual)


# ------------------------------------------------------------------ 1. svc numbers
def check_svc(rows, code) -> tuple[int, int, list[str]]:
    ok = bad = 0
    lines = []
    for r in rows:
        m = re.match(r"^\.nn\.svc\.(\w+)$", r["signature"])
        if not m:
            continue
        want = SVC.get(m.group(1))
        got = []
        for pc in range(r["a"], min(r["e"], r["a"] + 0x40), 4):
            w = code.u32(pc)
            if w is not None and (w & 0x0F000000) == 0x0F000000 and (w >> 28) == 0xE:
                got.append(w & 0xFFFFFF)
        good = want is not None and want in got
        ok += good
        bad += not good
        lines.append(f"  {'ok  ' if good else 'BAD '} {m.group(1):28} want {want if want is None else hex(want)} "
                     f"found {[hex(g) for g in got]}")
    return ok, bad, lines


# ------------------------------------------------------------------ 2. start validity
def check_starts(rows, code) -> tuple[int, int, Counter, list[str]]:
    """First word valid? And what precedes the start: 'end' (unconditional return/branch/
    pc write), 'call' (BL to a no-return callee), 'zero' (padding), 'thumb' (previous
    function is Thumb), or 'other' (usually a literal-pool word, which can decode as
    anything; informational only)."""
    valid = invalid = 0
    prev = Counter()
    bad = []
    ends = {FM.K_RET, FM.K_B, FM.K_BX, FM.K_PCWRITE, FM.K_VENEER, FM.K_JT_LDR, FM.K_JT_ADD, FM.K_TRAP}
    for i, r in enumerate(rows):
        if r["source"] not in ("symbol_map", "symbol_map+hand") or r["mode"] != "ARM":
            continue
        k = FM.decode_arm(code.u32(r["a"]), r["a"])[0]
        if k == FM.K_INVALID:
            invalid += 1
            bad.append(f"  invalid first word at {r['addr']} {r['signature'][:80]}")
            continue
        valid += 1
        pw = code.u32(r["a"] - 4) if r["a"] > code.t0 else None
        if pw is None:
            prev["first"] += 1
            continue
        pk, cond, _, _ = FM.decode_arm(pw, r["a"] - 4)
        if i and rows[i - 1]["mode"] == "THUMB":
            prev["thumb"] += 1
        elif pw == 0:
            prev["zero"] += 1
        elif cond == 14 and (pk in ends or (pk == FM.K_POP and pw & (1 << 15))):
            prev["end"] += 1
        elif cond == 14 and pk == FM.K_BL:
            prev["call"] += 1
        else:
            prev["other"] += 1
    return valid, invalid, prev, bad


# ------------------------------------------------------------------ 3. accessors
COND_ALWAYS = 0xE


def arm_load_store(w: int) -> tuple[str, int, int, bool] | None:
    """('ld'|'st', rd, rn, is_imm) for single data transfers (word/byte/halfword)."""
    if (w >> 28) != COND_ALWAYS:
        return None
    if (w & 0x0C000000) == 0x04000000:                      # LDR/STR/LDRB/STRB
        return ("ld" if w & (1 << 20) else "st", (w >> 12) & 15, (w >> 16) & 15, not (w & (1 << 25)))
    if (w & 0x0E000090) == 0x00000090 and (w & 0x60):       # LDRH/STRH/LDRSB/LDRSH/LDRD/STRD
        L = bool(w & (1 << 20))
        sh = (w >> 5) & 3
        if not L and sh != 1:                               # LDRD/STRD encodings
            return ("ld" if sh == 2 else "st", (w >> 12) & 15, (w >> 16) & 15, bool(w & (1 << 22)))
        return ("ld" if L else "st", (w >> 12) & 15, (w >> 16) & 15, bool(w & (1 << 22)))
    if (w & 0x0E100F00) in (0x0C100A00, 0x0C100B00) and (w & 0x0F000000) == 0x0D000000:   # VLDR
        return ("ld", 0, (w >> 16) & 15, True)
    if (w & 0x0E100F00) in (0x0C000A00, 0x0C000B00) and (w & 0x0F000000) == 0x0D000000:   # VSTR
        return ("st", 1, (w >> 16) & 15, True)
    return None


def is_mov_r0(w: int) -> bool:
    """MOV/MVN r0, ... or ADD/SUB r0, rN, ... (address of a member or of a pc-relative
    string: `GetName` returning `this + 0x3C` is a getter too)."""
    if (w >> 28) != COND_ALWAYS or (w & 0x0C00F000) != 0x00000000:
        return False
    op = (w >> 21) & 15
    return op in (0xD, 0xF, 0x4, 0x2)


def check_accessors(rows, code) -> tuple[dict, list[str]]:
    stats = Counter()
    odd = []
    for r in rows:
        if not r["signature"] or r["mode"] != "ARM" or r["kind"] not in ("func", "operator"):
            continue
        scope, base = base_name(r["signature"])
        m = re.match(r"^(Get|Is|Has|Set)[A-Z0-9_]", base)
        if not m:
            continue
        w0, w1 = code.u32(r["a"]), code.u32(r["a"] + 4)
        if w1 != 0xE12FFF1E:          # exactly "<insn>; bx lr"
            continue
        kind = "set" if m.group(1) == "Set" else "get"
        ls = arm_load_store(w0)
        if kind == "get":
            good = (ls is not None and ls[0] == "ld" and ls[1] == 0) or is_mov_r0(w0)
        else:
            good = ls is not None and ls[0] == "st" and ls[2] == 0 and ls[1] in (1, 2)
        stats[f"{kind}_total"] += 1
        stats[f"{kind}_ok"] += good
        if not good and len(odd) < 15:
            odd.append(f"  {kind} {r['addr']} {w0:08X} {r['signature'][:80]}")
    return dict(stats), odd


# ------------------------------------------------------------------ 4. vtables
def ctor_vtable_classes(rows, code) -> list[tuple[str, list[str]]]:
    by_addr = {r["a"]: r for r in rows}
    out = []
    for r in rows:
        if r["kind"] != "ctor" or r["mode"] != "ARM" or not r["class"]:
            continue
        slots_classes: list[str] = []
        for pc in range(r["a"], min(r["e"], r["a"] + 0x200), 4):
            w = code.u32(pc)
            k, c, t, sz = FM.decode_arm(w, pc)
            if k != FM.K_LDRLIT or sz != 4:
                continue
            v = code.u32(t)
            if v is None or not code.in_data(v):
                continue
            # an ARM-ABI vtable pointer points at slot 0; take up to 8 slots
            for s in range(8):
                f = code.u32(v + 4 * s)
                if f is None or f not in by_addr:
                    break
                fr = by_addr[f]
                slots_classes.append(fr["class"].replace("virtual ", ""))
        if slots_classes:
            out.append((r["class"], slots_classes))
    return out


def check_vtables(rows, code) -> dict:
    pairs = ctor_vtable_classes(rows, code)

    def hit_rate(ps):
        return sum(1 for cls, sl in ps if cls in sl) / max(1, len(ps))

    real = hit_rate(pairs)
    rot = [(pairs[(i + 1) % len(pairs)][0], pairs[i][1]) for i in range(len(pairs))]
    return {"ctors_with_vtable": len(pairs), "own_class_in_slots": round(real, 3),
            "baseline_rotated": round(hit_rate(rot), 3)}


# ------------------------------------------------------------------ 5. random sample
def objdump_path() -> Path | None:
    import toolchain
    d = toolchain.find({})
    return d / f"arm-none-eabi-objdump{toolchain.EXE}" if d else None


def disasm(objdump: Path, a: int, e: int, thumb: bool) -> list[str]:
    t0 = GAME.seg("text").vaddr
    cmd = [str(objdump), "-D", "-b", "binary", "-marm", f"--adjust-vma={t0:#x}",
           f"--start-address={a:#x}", f"--stop-address={e:#x}"]
    if thumb:
        cmd.append("-Mforce-thumb")
    cmd.append(str(CODE))
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    return [ln for ln in out.splitlines() if re.match(r"^\s+[0-9a-f]+:", ln)]


def random_sample(rows, code, seed: int, count: int) -> list[str]:
    objdump = objdump_path()
    by_addr = {r["a"]: r for r in rows}
    pool = [r for r in rows if r["library"] == "game" and r["signature"] and r["kind"] in ("func", "ctor", "dtor")
            and 8 <= r["e"] - r["a"] <= 0x180]
    rnd = random.Random(seed)
    picks = sorted(rnd.sample(pool, count), key=lambda r: r["a"])
    lines = [f"seed {seed}; pool {len(pool)} named game functions of 8..384 bytes", ""]
    for r in picks:
        lines.append(f"=== {r['addr']} size {r['e'] - r['a']} {r['mode']}  {r['signature']}")
        if not objdump:
            lines.append("  (objdump not found: python tools/toolchain.py)")
            continue
        for ln in disasm(objdump, r["a"], r["e"], r["mode"] == "THUMB")[:60]:
            m = re.search(r"\b(bl|blx|b)\s+(?:0x)?([0-9a-f]+)", ln)
            note = ""
            if m:
                t = int(m.group(2), 16)
                if t in by_addr and by_addr[t]["signature"]:
                    note = f"   ; -> {by_addr[t]['signature'][:90]}"
            lit = re.search(r"\[pc, #(-?\d+)\]", ln)
            if lit:
                pc = int(ln.split(":")[0], 16)
                la = pc + 8 + int(lit.group(1))
                v = code.u32(la)
                if v is not None:
                    tgt = by_addr.get(v)
                    note = f"   ; ={v:#010x}" + (f" {tgt['signature'][:70]}" if tgt and tgt["signature"] else "")
            lines.append(ln.rstrip() + note)
        lines.append("")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=27274)
    ap.add_argument("--count", type=int, default=20)
    a = ap.parse_args()
    rows = load_rows()
    code = Code()
    OUT.mkdir(parents=True, exist_ok=True)
    rep = []
    fails = 0

    ok, bad, svc_lines = check_svc(rows, code)
    rep.append(f"1. svc wrappers: {ok} match the 3dbrew SVC number, {bad} do not")
    rep += svc_lines
    fails += bad > 0 or ok == 0

    valid, invalid, prev, bad_starts = check_starts(rows, code)
    rep.append(f"2. symbol-map ARM starts: {valid} decode as valid ARM, {invalid} do not; "
               f"word before the start: {dict(prev.most_common())}")
    rep += bad_starts[:20]
    fails += invalid > 0

    st, odd = check_accessors(rows, code)
    g = st.get("get_ok", 0) / max(1, st.get("get_total", 0))
    s_ = st.get("set_ok", 0) / max(1, st.get("set_total", 0))
    rep.append(f"3. two-instruction accessors: Get/Is/Has {st.get('get_ok', 0)}/{st.get('get_total', 0)} "
               f"load or set r0 ({g:.1%}); Set {st.get('set_ok', 0)}/{st.get('set_total', 0)} store r1/r2 "
               f"into [r0] ({s_:.1%})")
    rep += odd
    fails += g < 0.9 or s_ < 0.9

    vt = check_vtables(rows, code)
    rep.append(f"4. constructors loading a vtable: {vt['ctors_with_vtable']}; own class among the slot "
               f"names: {vt['own_class_in_slots']:.1%} (rotated-name baseline {vt['baseline_rotated']:.1%})")
    fails += vt["own_class_in_slots"] < 0.5 or vt["own_class_in_slots"] < 5 * vt["baseline_rotated"]

    sample = random_sample(rows, code, a.seed, a.count)
    (OUT / "spotcheck20.txt").write_text("\n".join(sample) + "\n", encoding="utf-8")
    rep.append(f"5. random sample: {a.count} functions written to build/symbols/spotcheck20.txt")
    (OUT / "spotcheck_report.txt").write_text("\n".join(rep) + "\n", encoding="utf-8")
    print("\n".join(rep))
    print("spotcheck:", "FAIL" if fails else "ok")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
