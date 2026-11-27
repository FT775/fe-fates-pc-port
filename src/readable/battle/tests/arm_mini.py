"""A small ARM (A32, ARMv6K) interpreter for host differential tests of readable code.

Written for src/readable/battle/tests/stance_diff.py, because neither tools/readable nor
tools/harness has an ARM interpreter and Unicorn is not installed. Standard library only.
It runs the game's own code bytes from the owner's extracted/text.bin (never copied
anywhere) on a made-up memory, so a readable C function and the original can be compared
on the same inputs.

What it implements: condition codes; every data-processing instruction (immediate,
immediate shift and register shift operands, carry out of the shifter, S forms);
MUL/MLA/UMULL/UMLAL/SMULL/SMLAL; LDR/STR/LDRB/STRB (immediate and register offset,
pre/post-index, writeback); LDRH/STRH/LDRSB/LDRSH/LDRD/STRD; LDM/STM (all four modes, PC
in the list); B/BL/BX/BLX (register, and immediate as a call only); SXTB/SXTH/UXTB/UXTH
(and the add forms); CLZ; the hint NOPs. Anything else raises Unsupported, so a test
cannot silently pass over an instruction it does not model. No Thumb, VFP, coprocessor
or exclusive access: none occurs in the functions it is used on.

Calls: a BL/BLX to an address in `stubs` does not run the callee; the stub function gets
(cpu, args r0..r3) and its return value goes to r0 (r1-r3, r12 are left as they were,
which AAPCS allows). A BLX to a Thumb address without a stub raises ColdGuard when it is
the C++ one-time guard routine (the test treats that as "cache not filled") and
Unsupported otherwise.

Memory: 4 KiB pages created by map(); reads of unmapped bytes give 0 and count a fault,
writes there are dropped and counted, like 3dsrecomp's verify host. The code segment is
readable (literal pools) but writes to it raise.
"""
from __future__ import annotations

MASK = 0xFFFFFFFF
RETURN_SENTINEL = 0xFFFFFFE0  # the readable layer's FE_GUEST_RETURN: never code


class Unsupported(Exception):
    pass


class ColdGuard(Exception):
    pass


class Memory:
    def __init__(self, text: bytes, text_base: int = 0x00100000):
        self.text, self.text_base = text, text_base
        self.pages: dict[int, bytearray] = {}
        self.faults = 0
        self.writes: list[tuple[int, int, int]] = []  # (address, size, value) in order

    def map(self, addr: int, data: bytes) -> None:
        for i, b in enumerate(data):
            a = (addr + i) & MASK
            page = self.pages.get(a >> 12)
            if page is None:
                page = self.pages[a >> 12] = bytearray(4096)
            page[a & 0xFFF] = b

    def read8(self, a: int) -> int:
        a &= MASK
        page = self.pages.get(a >> 12)
        if page is not None:
            return page[a & 0xFFF]
        off = a - self.text_base
        if 0 <= off < len(self.text):
            return self.text[off]
        self.faults += 1
        return 0

    def read(self, a: int, n: int) -> int:
        v = 0
        for i in range(n):
            v |= self.read8(a + i) << (8 * i)
        return v

    def write(self, a: int, n: int, v: int) -> None:
        a &= MASK
        self.writes.append((a, n, v & ((1 << (8 * n)) - 1)))
        for i in range(n):
            b = (a + i) & MASK
            page = self.pages.get(b >> 12)
            if page is None:
                if 0 <= b - self.text_base < len(self.text):
                    raise Unsupported(f"write to code at {b:08X}")
                self.faults += 1
                continue
            page[b & 0xFFF] = (v >> (8 * i)) & 0xFF


def sx(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def ror(v: int, n: int) -> int:
    n &= 31
    return ((v >> n) | (v << (32 - n))) & MASK if n else v


class Cpu:
    def __init__(self, mem: Memory, stubs: dict | None = None, guard: int | None = None):
        self.mem = mem
        self.r = [0] * 16
        self.n = self.z = self.c = self.v = 0
        self.stubs = stubs or {}
        self.guard = guard  # address of the one-time guard routine (Thumb, without bit 0)
        self.steps = 0
        self.calls: list[tuple[int, tuple]] = []  # stubbed calls, in order

    # ---------------------------------------------------------------- helpers
    def cond(self, c: int) -> bool:
        n, z, cf, v = self.n, self.z, self.c, self.v
        return [z, not z, cf, not cf, n, not n, v, not v, cf and not z, not cf or z,
                n == v, n != v, not z and n == v, z or n != v, True, True][c]

    def shift(self, val: int, kind: int, amt: int, carry_in: int, by_reg: bool) -> tuple[int, int]:
        if by_reg:
            amt &= 0xFF
            if amt == 0:
                return val, carry_in
        if kind == 0:  # LSL
            if amt == 0:
                return val, carry_in
            if amt < 32:
                return (val << amt) & MASK, (val >> (32 - amt)) & 1
            if amt == 32:
                return 0, val & 1
            return 0, 0
        if kind == 1:  # LSR (immediate 0 = 32)
            if amt == 0 and not by_reg:
                amt = 32
            if amt < 32:
                return val >> amt, (val >> (amt - 1)) & 1
            if amt == 32:
                return 0, val >> 31
            return 0, 0
        if kind == 2:  # ASR (immediate 0 = 32)
            if amt == 0 and not by_reg:
                amt = 32
            s = sx(val, 32)
            if amt >= 32:
                return (MASK if s < 0 else 0), (1 if s < 0 else 0)
            return (s >> amt) & MASK, (val >> (amt - 1)) & 1
        # ROR / RRX
        if amt == 0 and not by_reg:
            return ((carry_in << 31) | (val >> 1)) & MASK, val & 1
        amt &= 31
        if amt == 0:
            return val, val >> 31
        res = ror(val, amt)
        return res, res >> 31

    def operand2(self, ins: int, pc: int) -> tuple[int, int]:
        if ins & (1 << 25):
            rot = ((ins >> 8) & 0xF) * 2
            v = ror(ins & 0xFF, rot)
            return v, (v >> 31) if rot else self.c
        rm = ins & 0xF
        val = self.reg(rm, pc)
        kind = (ins >> 5) & 3
        if ins & 0x10:
            rs = (ins >> 8) & 0xF
            if rm == 15:
                val = (pc + 12) & MASK
            return self.shift(val, kind, self.r[rs] & 0xFF, self.c, True)
        return self.shift(val, kind, (ins >> 7) & 0x1F, self.c, False)

    def reg(self, n: int, pc: int) -> int:
        return (pc + 8) & MASK if n == 15 else self.r[n]

    # ---------------------------------------------------------------- run
    def call(self, target: int, ret: int) -> bool:
        """A BL/BLX: True when it was stubbed (pc already set to ret)."""
        stub = self.stubs.get(target)
        if stub is None:
            return False
        args = tuple(self.r[:4])
        self.calls.append((target, args))
        self.r[0] = stub(self, args) & MASK
        self.r[15] = ret
        return True

    def run(self, pc: int, stop: set[int] | None = None, limit: int = 200000) -> int:
        """Runs from pc until pc reaches RETURN_SENTINEL or an address in stop; returns that pc."""
        self.r[15] = pc
        stop = stop or set()
        while True:
            pc = self.r[15]
            if pc == RETURN_SENTINEL or pc in stop:
                return pc
            self.steps += 1
            if self.steps > limit:
                raise Unsupported("step limit")
            ins = self.mem.read(pc, 4)
            self.r[15] = (pc + 4) & MASK
            self.step(ins, pc)

    def step(self, ins: int, pc: int) -> None:
        c = ins >> 28
        if c == 0xF:
            if (ins & 0xFE000000) == 0xFA000000:  # BLX immediate (to Thumb)
                off = sx(ins & 0xFFFFFF, 24) << 2
                target = (pc + 8 + off + (((ins >> 24) & 1) << 1)) & MASK
                ret = (pc + 4) & MASK
                self.r[14] = ret
                if self.call(target, ret) or self.call(target | 1, ret):
                    return
                if self.guard is not None and target == self.guard:
                    raise ColdGuard(f"one-time guard reached at {pc:08X}")
                raise Unsupported(f"BLX to Thumb {target:08X} at {pc:08X}")
            raise Unsupported(f"unconditional space {ins:08X} at {pc:08X}")
        if not self.cond(c):
            return
        op = (ins >> 25) & 7
        if (ins & 0x0FFFFFF0) == 0x012FFF10 or (ins & 0x0FFFFFF0) == 0x012FFF30:  # BX / BLX reg
            target = self.r[ins & 0xF]
            if ins & 0x20:
                ret = (pc + 4) & MASK
                self.r[14] = ret
                if self.call(target & ~1 & MASK, ret):
                    return
            if target & 1:
                raise Unsupported(f"switch to Thumb at {pc:08X}")
            self.r[15] = target & ~3 & MASK
            return
        if (ins & 0x0FFFFF00) == 0x0320F000:  # NOP / hints
            return
        if (ins & 0x0FFF0FF0) == 0x016F0F10:  # CLZ
            v = self.r[ins & 0xF]
            self.r[(ins >> 12) & 0xF] = 32 - v.bit_length()
            return
        if op == 0 and (ins & 0x90) == 0x90:
            if (ins & 0x60) == 0:
                return self.multiply(ins)
            return self.extra_load_store(ins, pc)
        if op in (0, 1):
            if (ins & 0x01900000) == 0x01000000:  # MRS/MSR/other misc with S=0 on test ops
                raise Unsupported(f"misc {ins:08X} at {pc:08X}")
            return self.data_processing(ins, pc)
        if op == 3 and (ins & 0x10):
            return self.media(ins, pc)
        if op in (2, 3):
            return self.load_store(ins, pc)
        if op == 4:
            return self.block(ins, pc)
        if op == 5:
            off = sx(ins & 0xFFFFFF, 24) << 2
            target = (pc + 8 + off) & MASK
            if ins & (1 << 24):
                ret = (pc + 4) & MASK
                self.r[14] = ret
                if self.call(target, ret):
                    return
            self.r[15] = target
            return
        raise Unsupported(f"{ins:08X} at {pc:08X}")

    def set_nz(self, v: int) -> None:
        self.n, self.z = v >> 31, int(v == 0)

    def data_processing(self, ins: int, pc: int) -> None:
        opc = (ins >> 21) & 0xF
        s = (ins >> 20) & 1
        rn, rd = (ins >> 16) & 0xF, (ins >> 12) & 0xF
        b, carry = self.operand2(ins, pc)
        a = self.reg(rn, pc)
        if (ins & 0x10) and not (ins & (1 << 25)) and rn == 15:
            a = (pc + 12) & MASK
        cin = self.c
        logic = opc in (0, 1, 8, 9, 12, 13, 14, 15)
        if opc == 0: res = a & b
        elif opc == 1: res = a ^ b
        elif opc in (2, 10): full = a + ((~b) & MASK) + 1
        elif opc == 3: full = b + ((~a) & MASK) + 1
        elif opc in (4, 11): full = a + b
        elif opc == 5: full = a + b + cin
        elif opc == 6: full = a + ((~b) & MASK) + cin
        elif opc == 7: full = b + ((~a) & MASK) + cin
        elif opc == 8: res = a & b
        elif opc == 9: res = a ^ b
        elif opc == 12: res = a | b
        elif opc == 13: res = b
        elif opc == 14: res = a & ~b & MASK
        else: res = (~b) & MASK
        if not logic:
            res = full & MASK
            x, y = (a, b) if opc in (2, 4, 5, 6, 10, 11) else (b, a)
            if opc in (2, 6, 10, 3, 7):
                y_eff = (~y) & MASK
            else:
                y_eff = y
            ovf = ((x ^ res) & (y_eff ^ res)) >> 31
        if opc in (8, 9, 10, 11):  # TST TEQ CMP CMN
            if not s:
                raise Unsupported(f"misc {ins:08X} at {pc:08X}")
            self.set_nz(res)
            if logic:
                self.c = carry
            else:
                self.c, self.v = int(full > MASK), ovf
            return
        if rd == 15:
            if s:
                raise Unsupported(f"S with pc at {pc:08X}")
            self.r[15] = res & ~3 & MASK
            return
        self.r[rd] = res
        if s:
            self.set_nz(res)
            if logic:
                self.c = carry
            else:
                self.c, self.v = int(full > MASK), ovf

    def multiply(self, ins: int) -> None:
        rd, rn, rs, rm = (ins >> 16) & 0xF, (ins >> 12) & 0xF, (ins >> 8) & 0xF, ins & 0xF
        s = (ins >> 20) & 1
        kind = (ins >> 21) & 0xF
        if kind in (0, 1):  # MUL, MLA
            res = (self.r[rm] * self.r[rs] + (self.r[rn] if kind == 1 else 0)) & MASK
            self.r[rd] = res
            if s:
                self.set_nz(res)
            return
        if kind in (4, 5, 6, 7):  # UMULL UMLAL SMULL SMLAL
            signed = kind in (6, 7)
            x, y = self.r[rm], self.r[rs]
            if signed:
                x, y = sx(x, 32), sx(y, 32)
            res = x * y
            if kind in (5, 7):
                res += (self.r[rd] << 32) | self.r[rn]
            res &= (1 << 64) - 1
            self.r[rn], self.r[rd] = res & MASK, res >> 32
            if s:
                self.n, self.z = res >> 63, int(res == 0)
            return
        raise Unsupported(f"multiply {ins:08X}")

    def address(self, ins: int, pc: int, offset: int) -> tuple[int, int, bool]:
        rn = (ins >> 16) & 0xF
        base = self.reg(rn, pc)
        up, pre, wb = (ins >> 23) & 1, (ins >> 24) & 1, (ins >> 21) & 1
        moved = (base + offset if up else base - offset) & MASK
        addr = moved if pre else base
        write = (not pre) or wb
        if write and rn == 15:
            raise Unsupported("writeback to pc")
        return addr, moved, write

    def load_store(self, ins: int, pc: int) -> None:
        if ins & (1 << 25):
            if ins & 0x10:
                raise Unsupported(f"media {ins:08X}")
            off, _ = self.shift(self.r[ins & 0xF], (ins >> 5) & 3, (ins >> 7) & 0x1F, self.c, False)
        else:
            off = ins & 0xFFF
        addr, moved, write = self.address(ins, pc, off)
        rn, rd = (ins >> 16) & 0xF, (ins >> 12) & 0xF
        byte, load = (ins >> 22) & 1, (ins >> 20) & 1
        if not ((ins >> 24) & 1) and ((ins >> 21) & 1):
            raise Unsupported("LDRT/STRT")
        if load:
            v = self.mem.read8(addr) if byte else self.mem.read(addr & ~3 & MASK, 4)
            if not byte and addr & 3:
                v = ror(v, (addr & 3) * 8)
            if write:
                self.r[rn] = moved
            if rd == 15:
                self.r[15] = v & ~3 & MASK
            else:
                self.r[rd] = v
        else:
            v = self.reg(rd, pc) if rd != 15 else (pc + 12) & MASK
            if byte:
                self.mem.write(addr, 1, v)
            else:
                self.mem.write(addr & ~3 & MASK, 4, v)
            if write:
                self.r[rn] = moved

    def extra_load_store(self, ins: int, pc: int) -> None:
        if ins & (1 << 22):
            off = ((ins >> 4) & 0xF0) | (ins & 0xF)
        else:
            off = self.r[ins & 0xF]
        addr, moved, write = self.address(ins, pc, off)
        rn, rd = (ins >> 16) & 0xF, (ins >> 12) & 0xF
        load, sh = (ins >> 20) & 1, (ins >> 5) & 3
        if load:
            if sh == 1:
                v = self.mem.read(addr, 2)
            elif sh == 2:
                v = sx(self.mem.read8(addr), 8) & MASK
            else:
                v = sx(self.mem.read(addr, 2), 16) & MASK
            if write:
                self.r[rn] = moved
            self.r[rd] = v
            return
        if sh == 1:  # STRH
            self.mem.write(addr, 2, self.reg(rd, pc))
        elif sh == 2:  # LDRD
            if rd & 1 or rd == 14:
                raise Unsupported("LDRD odd register")
            lo, hi = self.mem.read(addr, 4), self.mem.read(addr + 4, 4)
            if write:
                self.r[rn] = moved
            self.r[rd], self.r[rd + 1] = lo, hi
            return
        else:  # STRD
            if rd & 1 or rd == 14:
                raise Unsupported("STRD odd register")
            self.mem.write(addr, 4, self.r[rd])
            self.mem.write(addr + 4, 4, self.r[rd + 1])
        if write:
            self.r[rn] = moved

    def block(self, ins: int, pc: int) -> None:
        rn = (ins >> 16) & 0xF
        regs = [i for i in range(16) if ins & (1 << i)]
        if ins & (1 << 22):
            raise Unsupported("LDM/STM user registers")
        up, pre, wb, load = (ins >> 23) & 1, (ins >> 24) & 1, (ins >> 21) & 1, (ins >> 20) & 1
        base = self.r[rn]
        n = len(regs)
        if up:
            start = base + 4 if pre else base
            new = base + 4 * n
        else:
            start = base - 4 * n if pre else base - 4 * n + 4
            new = base - 4 * n
        start &= MASK
        if load:
            vals = [self.mem.read((start + 4 * i) & MASK, 4) for i in range(n)]
            if wb and rn not in regs:
                self.r[rn] = new & MASK
            for reg, v in zip(regs, vals):
                if reg == 15:
                    if v & 1:
                        raise Unsupported("return to Thumb")
                    self.r[15] = v & ~3 & MASK
                else:
                    self.r[reg] = v
        else:
            for i, reg in enumerate(regs):
                v = (pc + 12) & MASK if reg == 15 else self.r[reg]
                self.mem.write((start + 4 * i) & MASK, 4, v)
            if wb:
                self.r[rn] = new & MASK

    def media(self, ins: int, pc: int) -> None:
        # SXTB/SXTH/UXTB/UXTH and the add forms (SXTAB...): cond 0110 1UUU nnnn dddd rr00 0111 mmmm
        if (ins & 0x0F8003F0) == 0x06800070 and ((ins >> 20) & 7) in (2, 3, 6, 7):
            kind = (ins >> 20) & 7
            rn, rd, rm = (ins >> 16) & 0xF, (ins >> 12) & 0xF, ins & 0xF
            v = ror(self.r[rm], ((ins >> 10) & 3) * 8)
            if kind == 2: v = sx(v, 8) & MASK
            elif kind == 3: v = sx(v, 16) & MASK
            elif kind == 6: v &= 0xFF
            else: v &= 0xFFFF
            if rn != 15:
                v = (v + self.r[rn]) & MASK
            self.r[rd] = v
            return
        raise Unsupported(f"media {ins:08X} at {pc:08X}")


def selftest() -> int:
    """Checks the interpreter on hand-assembled words (encodings from the ARM ARM; no game code)."""
    fails = 0

    def run(words: list[int], regs: dict[int, int], mem_init=None) -> Cpu:
        code = b"".join(w.to_bytes(4, "little") for w in words + [0xE12FFF1E])  # ... ; bx lr
        m = Memory(code, 0x1000)
        m.map(0x8000, bytes(0x1000))
        for a, d in (mem_init or []):
            m.map(a, d)
        cpu = Cpu(m)
        for k, v in regs.items():
            cpu.r[k] = v & MASK
        cpu.r[14] = RETURN_SENTINEL
        cpu.r[13] = 0x9000
        cpu.run(0x1000)
        return cpu

    def expect(name, got, want):
        nonlocal fails
        if got != want:
            fails += 1
            print(f"  arm_mini selftest FAIL {name}: {got:#x} != {want:#x}")

    c = run([0xE0800001], {0: 5, 1: 7})                      # add r0, r0, r1
    expect("add", c.r[0], 12)
    c = run([0xE0500001, 0x03A00001, 0x13A00002], {0: 3, 1: 3})  # subs; moveq #1; movne #2
    expect("subs/cond", c.r[0], 1)
    c = run([0xE1A000C0], {0: 0xFFFFFFF6})                   # asr r0, r0, #1
    expect("asr", c.r[0], 0xFFFFFFFB)
    c = run([0xE0C10392], {2: 0x55555556, 3: 0xFFFFFFF1})    # smull r0, r1, r2, r3
    expect("smull hi", c.r[1], 0xFFFFFFFA)  # floor(-15 * 0x55555556 / 2**32) = -6
    c = run([0xE1D000D1], {0: 0x8000}, [(0x8001, b"\x80")])  # ldrsb r0, [r0, #1]
    expect("ldrsb", c.r[0], 0xFFFFFF80)
    c = run([0xE6BF0070], {0: 0x00018001})                   # sxth r0, r0
    expect("sxth", c.r[0], 0xFFFF8001)
    c = run([0xE92D0003, 0xE3A00000, 0xE3A01000, 0xE8BD0003], {0: 11, 1: 22})  # push {r0,r1}; mov; mov; pop
    expect("push/pop", c.r[0] + c.r[1], 33)
    c = run([0xE3530000, 0xC0800001], {0: 1, 1: 2, 3: 0xFFFFFFFF})  # cmp r3,#0; addgt
    expect("signed gt", c.r[0], 1)
    c = run([0xE1B000C2], {2: 3})                             # asrs r0, r2, #1 -> carry 1
    expect("asrs carry", c.c, 1)
    print(f"arm_mini selftest: {9 - fails}/9 checks passed")
    return fails


if __name__ == "__main__":
    raise SystemExit(1 if selftest() else 0)
