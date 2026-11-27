#!/usr/bin/env python3
"""Explains tier 2's shadow-pass read count of unit_item_stat_bonus (0x0033A790 GetEnhanceHave).

    python src/readable/battle2/tests/shadow_count.py

3dsrecomp verify (engine/3dsrecomp/src/verify.rs, read, not copied) runs each function on a made-up
memory that it builds the same way every time: the game's text, rodata and data(+bss) images, a
0x40000-byte heap at 0x08000000 filled by a fixed xorshift (regions(), seed 0x9E3779B97F4A7C15), a
zeroed stack below 0x10000000 and r0..r12 from the same xorshift seeded with 0x5DEECE66D0000000 ^ the
function's address. This script rebuilds that state from the owner's extracted/ files (test tool only,
nothing copied anywhere), runs the game's own GetEnhanceHave in arm_mini.py twice on the same memory
(the guard routine __cxa_guard_acquire answered as the game's does: a 0 guard word becomes 1 and the
call returns 1), and counts the unmapped byte accesses of each call to Unit::IsItemEnhanceHave and
unit::Item::ToData.

From those counts it predicts both of tier 2's numbers:
  A (the interpreter)       = the first run
  B (the shadow pass)       = the original (A) + the readable code of every ToData call it makes
                              (ToData is an override, item_to_data: in shadow mode its original AND its
                              readable code run) + this override's readable code, which runs after the
                              original on the same memory, so IsItemEnhanceHave's one-time caches are
                              warm (the second run) + again the readable code of its ToData calls.
Exit 0 when the prediction equals build/readable/verify_battle2/0033A790.shadow.txt's "A faults
against B" (or, without that file, prints the prediction). docs/BATTLE2.md section 8.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "battle", "tests"))
import arm_mini as A  # noqa: E402

FUNC = 0x0033A790
ENHANCE, TO_DATA = 0x0052FB98, 0x003D0EA4
WATCH = {ENHANCE: "Unit::IsItemEnhanceHave", TO_DATA: "unit::Item::ToData"}
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
RETURN = 0xFFFFFFF0
M64 = (1 << 64) - 1
HEAP, HEAP_SIZE, STACK_TOP, STACK_SIZE, TLS = 0x08000000, 0x40000, 0x10000000, 0x40000, 0x1FF82000


class Rnd:
    """verify.rs's Random: xorshift64, the high 32 of the low 48 bits."""

    def __init__(self, seed: int):
        self.s = seed & M64

    def next(self) -> int:
        x = self.s
        x ^= (x << 13) & M64
        x ^= x >> 7
        x ^= (x << 17) & M64
        self.s = x
        return (x >> 16) & 0xFFFFFFFF

    def heap_pointer(self) -> int:
        return (HEAP + self.next() % (HEAP_SIZE - 0x1000)) & ~3


def pad(b: bytes) -> bytes:
    return b + bytes((-len(b)) % 4096)


def made_up_memory(ext: str) -> A.Memory:
    lay = json.load(open(os.path.join(ext, "layout.json")))
    mem = A.Memory(open(os.path.join(ext, "text.bin"), "rb").read())
    mem.map(lay["rodata"]["addr"], pad(open(os.path.join(ext, "rodata.bin"), "rb").read()))
    mem.map(lay["data"]["addr"], pad(open(os.path.join(ext, "data.bin"), "rb").read() + bytes(lay["bss_size"])))
    r = Rnd(0x9E3779B97F4A7C15)
    heap = bytearray(HEAP_SIZE)
    for i in range(0, HEAP_SIZE, 4):
        v = r.heap_pointer() if r.next() % 4 == 0 else r.next()
        heap[i:i + 4] = v.to_bytes(4, "little")
    mem.map(HEAP, heap)
    mem.map(STACK_TOP - STACK_SIZE, bytes(STACK_SIZE))
    mem.map(TLS, bytes(4096))
    mem.map(0x0B000000, pad((0xE3A00000).to_bytes(4, "little") + (0xE12FFF1E).to_bytes(4, "little")))
    return mem


def registers(func: int) -> list[int]:
    r = Rnd(0x5DEECE66D0000000 ^ func)
    out = []
    for _ in range(13):
        k = r.next() % 4
        out.append(r.heap_pointer() if k in (0, 1) else (r.next() % 256 if k == 2 else r.next()))
    return out


def guard_acquire(cpu, a) -> int:
    if cpu.mem.read(a[0], 4) == 0:
        cpu.mem.write(a[0], 4, 1)
        return 1
    return 0


class Tracing(A.Cpu):
    """arm_mini's Cpu, noting the unmapped accesses of every call to a WATCH function."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.open: list[tuple] = []
        self.log: list[tuple[int, int, int]] = []  # (depth, function, faults)

    def run(self, pc: int, stop=None, limit: int = 2000000) -> int:
        self.r[15] = pc
        while True:
            pc = self.r[15]
            if self.open and pc == self.open[-1][1] and self.r[13] == self.open[-1][3]:
                f, _ret, f0, _sp = self.open.pop()
                self.log.append((len(self.open), f, self.mem.faults - f0))
            if pc == RETURN:
                return pc
            if pc in WATCH:
                self.open.append((pc, self.r[14], self.mem.faults, self.r[13]))
            self.steps += 1
            if self.steps > limit:
                raise A.Unsupported("step limit")
            ins = self.mem.read(pc, 4)
            self.r[15] = (pc + 4) & A.MASK
            self.step(ins, pc)


def run_once(mem: A.Memory, regs: list[int]) -> tuple[int, int, list]:
    cpu = Tracing(mem, {GUARD: guard_acquire, GUARD | 1: guard_acquire})
    cpu.r[:13] = regs
    cpu.r[13], cpu.r[14] = STACK_TOP - 0x1000, RETURN
    f0 = mem.faults
    cpu.run(FUNC)
    return cpu.r[0], mem.faults - f0, cpu.log


def main() -> int:
    ext = os.path.join(ROOT, "extracted")
    if not os.path.isfile(os.path.join(ext, "text.bin")):
        print("shadow_count: SKIPPED (extracted/ is missing)")
        return 0
    regs = registers(FUNC)
    mem = made_up_memory(ext)
    r0a, cold, log_a = run_once(mem, regs)
    r0b, warm, log_b = run_once(mem, regs)
    print(f"shadow_count: GetEnhanceHave in verify's made-up state, r0 = 0x{regs[0]:08X}, r1 = {regs[1]}")
    for title, total, log in (("first run (caches cold)", cold, log_a), ("second run (caches warm)", warm, log_b)):
        print(f"  {title}: {total} unmapped accesses; per call: "
              + ", ".join(f"{'  ' * d}{WATCH[f].split('::')[-1]} {n}" for d, f, n in log))
    to_data = [n for _d, f, n in log_a if f == TO_DATA]
    to_data_b = [n for _d, f, n in log_b if f == TO_DATA]
    a = cold
    b = cold + sum(to_data) + warm + sum(to_data_b)
    print(f"  predicted: A = {a}; B = {cold} (original) + {sum(to_data)} (item_to_data's readable code in "
          f"its {len(to_data)} calls) + {warm} (readable code, caches warm) + {sum(to_data_b)} (item_to_data "
          f"again) = {b}")
    shadow = os.path.join(ROOT, "build", "readable", "verify_battle2", "0033A790.shadow.txt")
    if not os.path.isfile(shadow):
        print("shadow_count: no tier-2 shadow output to compare with (prediction only)")
        return 0
    m = re.search(r"(\d+) faults against (\d+)", open(shadow, encoding="utf-8", errors="replace").read())
    if not m:
        print("shadow_count: the shadow output has no fault line")
        return 1
    got = (int(m.group(1)), int(m.group(2)))
    ok = got == (a, b) and r0a == r0b
    print(f"shadow_count: {'OK' if ok else 'DIFFERENT'} (tier 2 shadow pass: {got[0]} faults against {got[1]}; "
          f"predicted {a} against {b})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
