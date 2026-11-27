#!/usr/bin/env python3
"""Control-flow reach inside one function window (used by symbols.py to keep named
function bodies intact).

reach(code, text_va, start, limit, thumb) follows the code from `start` the way the CPU
can: fall-through, conditional and unconditional local branches, ARMCC jump tables
("CMP rX,#N ; ADDLS pc,pc,rX,LSL #2 ; B default ; B case0 ...", and
"LDRLS pc,[pc,rX,LSL #2]" address tables). Calls (BL/BLX) return, so they fall through;
returns, unconditional branches out of the window, BX and other PC writes end a path.
PC-relative loads mark their literal words as data so they are never decoded.

It answers one question: "can execution that enters at `start` reach address X before
`limit`?" A start that funcmap proposes inside a named function is a separate function
only when the answer is no (symbols.py), and the end of the reached code shows where a
named function really stops (for an unnamed function that follows it in the same window).

Instruction classification comes from tools/analysis/funcmap.py (decode_arm/decode_thumb).
Standard library only.
"""
from __future__ import annotations

import bisect
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import funcmap as FM  # noqa: E402

AL = 14


@dataclass
class Reach:
    insns: dict = field(default_factory=dict)     # pc -> instruction length
    literals: set = field(default_factory=set)    # byte addresses read as data
    adr: set = field(default_factory=set)         # ADR targets in the window (inline data)
    incomplete: bool = False                      # an untracked computed jump was seen
    invalid: bool = False                         # a reached word did not decode
    calls: list = field(default_factory=list)     # (target, target_is_thumb) of BL/BLX imm
    thumb_at: set = field(default_factory=set)    # reached instruction starts decoded as Thumb
    strings: list = field(default_factory=list)   # (start, end) of ADR'd text strings
    _starts: list | None = None

    def covers(self, a: int, known: list | None = None) -> bool:
        """True when `a` is a reached instruction start, inside one, literal data, or in
        inline data that an ADR points at (armcc puts string constants between code
        blocks). An ADR'd hole runs from the ADR target to the next reached instruction;
        when `known` (sorted list of known function starts) is given, a hole that starts
        at a known start is code (a callback address), not data, and a hole never runs
        past the next known start."""
        if a in self.insns or a in self.literals:
            return True
        if self.insns.get(a - 2, 0) > 2:            # 2nd half of an ARM word or Thumb BL pair
            return True
        for t, e in self.strings:
            if t <= a < e:
                return True
        if self.adr:
            if self._starts is None:
                self._starts = sorted(self.insns)
            for t in self.adr:
                if t > a:
                    continue
                i = bisect.bisect_right(self._starts, t)
                nxt = self._starts[i] if i < len(self._starts) else None
                if nxt is None or a >= nxt:
                    continue
                if known is not None:
                    j = bisect.bisect_left(known, t)
                    if j < len(known) and known[j] < a:    # a known start in [t, a): code, not data
                        continue
                return True
        return False

    def end(self) -> int:
        """First byte after the last reached instruction or literal (0 if nothing)."""
        e = max((p + n for p, n in self.insns.items()), default=0)
        if self.literals:
            e = max(e, max(self.literals) + 1)
        for _, se in self.strings:
            e = max(e, se)
        return e


def _u32(code: bytes, text_va: int, a: int) -> int | None:
    o = a - text_va
    if o < 0 or o + 4 > len(code):
        return None
    return int.from_bytes(code[o:o + 4], "little")


def _u16(code: bytes, text_va: int, a: int) -> int | None:
    o = a - text_va
    if o < 0 or o + 2 > len(code):
        return None
    return int.from_bytes(code[o:o + 2], "little")


def _cmp_bound(code: bytes, text_va: int, pc: int, reg: int) -> int | None:
    """N from the 'CMP reg,#N' just before a jump-table dispatch (cases 0..N)."""
    w = _u32(code, text_va, pc - 4)
    if w is None:
        return None
    if (w & 0x0FF0F000) == 0x03500000 and ((w >> 16) & 0xF) == reg:
        return FM.ror_imm(w)
    return None


def reach(code: bytes, text_va: int, start: int, limit: int, thumb: bool,
          max_table: int = 1024) -> Reach:
    r = Reach()
    work = [(start, thumb)]
    while work:
        pc, th = work.pop()
        adr_reg = None                                # (rd, target) of the last ADR on this path
        while start <= pc < limit and pc not in r.insns and pc not in r.literals:
            if th:
                h = _u16(code, text_va, pc)
                if h is None:
                    break
                h2 = _u16(code, text_va, pc + 2) if pc + 4 <= limit else None
                k, cond, a, b, ln = FM.decode_thumb(h, h2, pc)
                rd = (h >> 8) & 7 if k == FM.K_ADR else None
            else:
                if pc & 3:
                    r.invalid = True
                    break
                w = _u32(code, text_va, pc)
                if w is None:
                    break
                k, cond, a, b = FM.decode_arm(w, pc)
                rd = (w >> 12) & 0xF if k == FM.K_ADR else None
                ln = 4
            if k == FM.K_INVALID:
                r.invalid = True
                break
            r.insns[pc] = ln
            if th:
                r.thumb_at.add(pc)
            nxt = pc + ln
            if k == FM.K_BL:
                r.calls.append((a, th))
            elif k == FM.K_BLX_IMM:
                r.calls.append((a, not th))
            elif k == FM.K_ADR:
                adr_reg = (rd, a)
                if start <= a < limit:
                    r.adr.add(a & ~1)
            elif k == FM.K_LDRLIT:
                r.literals.update(range(a, a + b))
            elif k == FM.K_VENEER:                        # ldr pc,[pc,#imm]
                r.literals.update(range(a, a + 4))
                if cond == AL:
                    break
            elif k == FM.K_B:
                if start <= a < limit:
                    work.append((a, th))
                if cond == AL:
                    break
            elif k == FM.K_BX and adr_reg and adr_reg[0] == a:
                # interworking stub: 'add ip,pc,#1 ; bx ip' (ARM -> Thumb) or 'adr r; bx r'
                t = adr_reg[1]
                r.adr.discard(t & ~1)
                work.append((t & ~1, bool(t & 1)))
                if cond == AL:
                    break
            elif k in (FM.K_RET, FM.K_BX, FM.K_PCWRITE, FM.K_TRAP):
                if cond == AL:
                    break
            elif k == FM.K_JT_ADD:
                if th:
                    r.incomplete = True
                    break
                n = _cmp_bound(code, text_va, pc, a)
                cnt = (n + 1) if n is not None else max_table
                for i in range(cnt):                      # table of B instructions at pc+8
                    t = pc + 8 + 4 * i
                    wt = _u32(code, text_va, t)
                    if t >= limit or wt is None:
                        break
                    kt, ct, _, _ = FM.decode_arm(wt, t)
                    if n is None and not (kt == FM.K_B and ct == AL):
                        break
                    work.append((t, False))
                if cond == AL:
                    break
            elif k == FM.K_JT_LDR:
                n = _cmp_bound(code, text_va, pc, a)
                if n is None:
                    r.incomplete = True
                else:
                    for i in range(n + 1):                # table of addresses at pc+8
                        t = pc + 8 + 4 * i
                        r.literals.update(range(t, t + 4))
                        v = _u32(code, text_va, t)
                        if v is not None and start <= (v & ~1) < limit:
                            work.append((v & ~1, bool(v & 1)))
                if cond == AL:
                    break
            pc = nxt
    for t in sorted(r.adr):                               # ADR'd C strings (text, NUL, pad to 4)
        if t in r.insns:
            continue
        o = t - text_va
        j = o
        while j < len(code) and j - o < 512 and code[j] != 0 and (code[j] >= 0x80 or 0x20 <= code[j] < 0x7F):
            j += 1
        if j - o >= 2 and j < len(code) and code[j] == 0:
            e = text_va + j + 1
            e += (-e) % 4
            r.strings.append((t, min(e, limit)))
    return r


def selftest() -> int:
    import struct
    fails = 0

    def check(what, got, want):
        nonlocal fails
        if got != want:
            fails += 1
            print(f"FAIL {what}: got {got!r} want {want!r}")

    base = 0x100000
    # f: ldr r0,[pc,#8] ; push {r4,lr} ; bl +0 ; pop {r4,pc} ; .word lit ; g: push {r4,lr} ; pop {r4,pc}
    words = [0xE59F0008, 0xE92D4010, 0xEBFFFFFE, 0xE8BD8010, 0x12345678, 0xE92D4010, 0xE8BD8010]
    code = struct.pack(f"<{len(words)}I", *words)
    r = reach(code, base, base, base + len(code), False)
    check("ldr-then-push body reaches the push", base + 4 in r.insns, True)
    check("literal is data", r.covers(base + 0x10), True)
    check("next function not reached", r.covers(base + 0x14), False)
    check("end", r.end(), base + 0x14)
    # conditional branch over a return: movne ; bxeq lr ; b skip ; nop ; skip: bx lr
    words = [0x13A00002, 0x012FFF1E, 0xEA000000, 0xE1A00000, 0xE12FFF1E]
    code = struct.pack(f"<{len(words)}I", *words)
    r = reach(code, base, base, base + len(code), False)
    check("branch target reached", base + 0x10 in r.insns, True)
    check("skipped word not reached", base + 0xC in r.insns, False)
    check("mid-instruction halfword covered", r.covers(base + 6), True)
    # jump table: cmp r0,#1 ; addls pc,pc,r0,lsl#2 ; b dflt ; b c0 ; b c1 ; c0: bx lr ; c1: bx lr ; dflt: bx lr
    words = [0xE3500001, 0x908FF100, 0xEA000003, 0xEA000000, 0xEA000000,
             0xE12FFF1E, 0xE12FFF1E, 0xE12FFF1E]
    code = struct.pack(f"<{len(words)}I", *words)
    r = reach(code, base, base, base + len(code), False)
    check("jump table cases reached", all(base + o in r.insns for o in (0x14, 0x18, 0x1C)), True)
    # Thumb: bl ; bx lr ; push {r3-r7,lr}
    hw = [0xF7FF, 0xFFFE, 0x4770, 0xB5F8, 0xBDF8]
    code = struct.pack(f"<{len(hw)}H", *hw)
    r = reach(code, base, base, base + len(code), True)
    check("thumb stops at bx lr", r.end(), base + 6)
    check("thumb next start free", r.covers(base + 6), False)
    # ARM -> Thumb interworking stub: nop ; add ip,pc,#1 ; bx ip ; thumb: bx lr
    code = struct.pack("<3IH", 0xE1A00000, 0xE28FC001, 0xE12FFF1C, 0x4770)
    r = reach(code, base, base, base + len(code), False)
    check("stub continues in Thumb", base + 0xC in r.thumb_at, True)
    # ADR'd inline string between code blocks: adr r1,str ; b over ; str: "ab" + 2 NUL ; over: bx lr
    words = [0xE28F1000, 0xEA000000, 0x00006261, 0xE12FFF1E]
    code = struct.pack("<4I", *words)
    r = reach(code, base, base, base + len(code), False)
    check("inline ADR data covered", r.covers(base + 8), True)
    check("code after inline data reached", base + 0xC in r.insns, True)
    # ADR'd string at the end of a function: adr r0,str ; b far ; "MKID_X" NUL pad ; next: bx lr
    code = struct.pack("<2I", 0xE28F0000, 0xEAFFFFFE) + b"MKID_X" + bytes(2) + struct.pack("<I", 0xE12FFF1E)
    r = reach(code, base, base, base + len(code), False)
    check("trailing ADR string covered", r.covers(base + 0xC), True)
    check("trailing ADR string ends before next code", r.end(), base + 0x10)
    print(f"flow selftest: {fails} failures")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(selftest())
