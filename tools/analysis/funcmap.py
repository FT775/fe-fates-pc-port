#!/usr/bin/env python3
"""First-pass function map of the game's .text (constants from config/game.json).

Standard library only.  Implements just enough ARMv6K ARM + Thumb-1 decoding
to do recursive-descent disassembly:

  * branches (B/BL/BLX imm, BX/BLX reg), returns (BX LR, LDM sp!{..pc},
    LDR pc,[sp],#4, MOV pc,lr, Thumb POP {..pc})
  * PC-relative loads (LDR/LDRB/LDRH/LDRD/VLDR literal, Thumb LDR literal)
    -> literal pool words
  * ADR (ADD/SUB rd, pc, #imm)
  * jump tables: ARMCC "CMP rX,#N ; ADDLS pc,pc,rX,LSL #2 ; B default ; B..."
    and "LDRcc pc,[pc,rX,LSL #2]" address tables
  * prologues (STMFD sp!,{..lr}, VPUSH, Thumb PUSH {..lr})
  * a coarse validity check (cond=0xF space, non-VFP/CP15 coprocessor ops,
    UDF, Thumb 0xDE.., lone BL halves) used to reject data decoded as code.

It is NOT a full disassembler: operands of ordinary data-processing / media /
VFP instructions are not decoded, only classified.

Discovery order: crt0 entry closure over BL/BLX/tail targets -> C++
init_array (self-relative, found from the crt0 runner) -> literal values
pointing into .text (excluding jump-table words and "ADD rX,pc,rX" PC-relative
offsets) -> .rodata/.data words pointing into .text (vtables etc.) -> gap scan
(STMFD sp!,{..lr} prologues, then the first cond=AL word of each gap).  Weak
candidates (pointers, gaps) must pass plausibility checks (see descend()) and
are pruned afterwards if ordinary code falls through into them.  Final
ownership treats any branch leaving [start, next_start) as a tail call.

Known limits (see funcmap_summary.txt for the measured effect):
  * Thumb: Thumb-1 + BL/BLX pairs only (ARMv6K has no Thumb-2).  No Thumb code
    was found by a reliable route, so the Thumb gap scan is off by default.
  * Jump tables: only the ARMCC "CMP rX,#N ; LDRcc pc,[pc,rX,LSL#2]" and
    "ADDcc pc,pc,rX,LSL#2 ; B ..." forms.  Computed "ADD pc, rA, rB" tables in
    hand-written library code are not followed (counted as add_pc_reg).
  * Function ends are "last reached instruction or owned literal, clipped to
    the next start"; inline ADR data inside a function counts toward its size.
  * "tail_range" starts (targets of branches leaving a function's range) and
    "gap" starts are heuristics: low confidence.
  * Validity check is coarse; data whose words decode as plausible cond=AL
    ARM instructions can still be accepted as code.
  * No dataflow: register-indirect calls (BLX rX, 5.9k sites) and vtable
    dispatch are not resolved; such targets are only found via data pointers.

Usage:  python tools/analysis/funcmap.py [--selftest]
Outputs (under extracted/analysis/):
  functions.csv              start,end_guess,mode,callers,size,+extras
  funcmap_summary.txt        human readable summary
  funcmap_summary.json       machine readable metrics
  funcmap_literal_pools.csv  contiguous literal-pool runs
  funcmap_jumptables.csv     detected jump tables
"""
import csv
import json
import os
import struct
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CODE_BIN = os.path.join(ROOT, "extracted", "code.bin")
OUT_DIR = os.path.join(ROOT, "extracted", "analysis")

# Segment constants come from config/game.json (tools/gamecfg.py). code.bin is the
# page-aligned image starting at .text, so a segment's file offset is vaddr - TEXT_VA.
sys.path.insert(0, os.path.join(ROOT, "tools"))
from gamecfg import GAME  # noqa: E402

TEXT_VA = GAME.seg("text").vaddr
TEXT_SIZE = GAME.seg("text").size
RODATA_VA, RODATA_SIZE = GAME.seg("rodata").vaddr, GAME.seg("rodata").size
DATA_VA, DATA_SIZE = GAME.seg("data").vaddr, GAME.seg("data").size
RODATA_OFF, DATA_OFF = RODATA_VA - TEXT_VA, DATA_VA - TEXT_VA
BSS_SIZE = int(GAME.raw["segments"]["bss_size"], 16)
TEXT_END = TEXT_VA + TEXT_SIZE
GAME_LABEL = "%s %s" % (GAME.game, GAME.product_code)

# ---------------------------------------------------------------- kinds
K_OTHER, K_B, K_BL, K_BLX_IMM, K_BX, K_BLX_REG, K_RET, K_LDRLIT, K_ADR, \
    K_JT_ADD, K_JT_LDR, K_PCWRITE, K_INVALID, K_PUSH, K_POP, K_SVC, \
    K_VENEER, K_BL_HI, K_TRAP = range(19)
KNAMES = ["other", "b", "bl", "blx_imm", "bx", "blx_reg", "ret", "ldr_lit",
          "adr", "jt_add", "jt_ldr", "pc_write", "INVALID", "push", "pop",
          "svc", "veneer", "bl_hi", "trap_udf"]
COND = ["eq", "ne", "cs", "cc", "mi", "pl", "vs", "vc", "hi", "ls", "ge",
        "lt", "gt", "le", "", "nv"]


def sext(v, bits):
    m = 1 << (bits - 1)
    return (v ^ m) - m


def ror_imm(w):
    imm = w & 0xFF
    rot = ((w >> 8) & 0xF) * 2
    return ((imm >> rot) | (imm << (32 - rot))) & 0xFFFFFFFF if rot else imm


# Decoded instruction: (kind, cond, a, b)
#   b/bl/blx_imm : a = target
#   bx/blx_reg   : a = register
#   ldr_lit      : a = literal address, b = size in bytes
#   adr          : a = computed address
#   jt_add/jt_ldr: a = index register
#   push/pop     : a = register list, b = 1 if lr/pc included
#   veneer       : a = literal address holding target

def decode_arm(w, pc):
    cond = w >> 28
    if cond == 0xF:
        if (w & 0x0E000000) == 0x0A000000:  # BLX imm
            off = (sext(w & 0xFFFFFF, 24) << 2) | (((w >> 24) & 1) << 1)
            return (K_BLX_IMM, 14, (pc + 8 + off) & 0xFFFFFFFF, 0)
        if (w & 0x0D70F000) == 0x0550F000:  # PLD
            return (K_OTHER, 14, 0, 0)
        if w == 0xF57FF01F or (w & 0xFFF1FE20) == 0xF1000000 \
                or (w & 0xFFFFFDFF) == 0xF1010000 \
                or (w & 0xFE5FFFE0) == 0xF84D0500 \
                or (w & 0xFE50FFFF) == 0xF8100A00 \
                or (w & 0xFFFFFFF0) in (0xF57FF040, 0xF57FF050, 0xF57FF060):
            return (K_OTHER, 14, 0, 0)
        return (K_INVALID, cond, 0, 0)
    op = (w >> 25) & 7
    if op == 5:
        tgt = (pc + 8 + (sext(w & 0xFFFFFF, 24) << 2)) & 0xFFFFFFFF
        return ((K_BL if w & 0x01000000 else K_B), cond, tgt, 0)
    if (w & 0x0FFFFFF0) == 0x012FFF10:
        rm = w & 0xF
        return ((K_RET if rm == 14 else K_BX), cond, rm, 0)
    if (w & 0x0FFFFFF0) == 0x012FFF30:
        return (K_BLX_REG, cond, w & 0xF, 0)
    if op == 4:  # LDM/STM
        L = (w >> 20) & 1
        rn = (w >> 16) & 0xF
        rl = w & 0xFFFF
        wb = (w >> 21) & 1
        if L:
            if rl & 0x8000:
                if rn == 13:
                    return (K_RET, cond, rl, 1)
                return (K_PCWRITE, cond, rn, 0)
            if rn == 13 and wb:
                return (K_POP, cond, rl, 0)
        else:
            if rn == 13 and wb and not (w >> 23) & 1 and (w >> 24) & 1:
                return (K_PUSH, cond, rl, 1 if rl & 0x4000 else 0)
        return (K_OTHER, cond, 0, 0)
    if op == 2 or (op == 3 and not (w & 0x10)):  # LDR/STR single
        L = (w >> 20) & 1
        rn = (w >> 16) & 0xF
        rd = (w >> 12) & 0xF
        P = (w >> 24) & 1
        U = (w >> 23) & 1
        B = (w >> 22) & 1
        W = (w >> 21) & 1
        reg = op == 3
        if L and rd == 15:
            if rn == 13 and not P and not reg:
                return (K_RET, cond, 0, 1)
            if rn == 15 and reg and P:
                return (K_JT_LDR, cond, w & 0xF, (w >> 4) & 0xFF)
            if rn == 15 and not reg and P and not W:
                imm = w & 0xFFF
                return (K_VENEER, cond, pc + 8 + (imm if U else -imm), 0)
            return (K_PCWRITE, cond, rn, 0)
        if L and rn == 15 and not reg and P and not W:
            imm = w & 0xFFF
            return (K_LDRLIT, cond, pc + 8 + (imm if U else -imm), 1 if B else 4)
        if not L and rn == 13 and P and W and not U and not reg and (w & 0xFFF) == 4:
            return (K_PUSH, cond, 1 << rd, 1 if rd == 14 else 0)
        return (K_OTHER, cond, 0, 0)
    if op == 3:  # media
        if (w & 0x0FF000F0) == 0x07F000F0:
            # permanently-undefined (UDF): used deliberately as a trap
            return (K_TRAP if cond == 14 else K_INVALID, cond, 0, 0)
        return (K_OTHER, cond, 0, 0)
    if op == 7:
        if w & 0x01000000:
            return (K_SVC, cond, w & 0xFFFFFF, 0)
        cp = (w >> 8) & 0xF
        return (K_OTHER if cp in (10, 11, 14, 15) else K_INVALID, cond, 0, 0)
    if op == 6:
        cp = (w >> 8) & 0xF
        if cp not in (10, 11, 14, 15):
            return (K_INVALID, cond, 0, 0)
        if (w & 0x0F300E00) == 0x0D100A00 and ((w >> 16) & 0xF) == 15:  # VLDR lit
            imm = (w & 0xFF) * 4
            base = (pc + 8) & ~3
            return (K_LDRLIT, cond, base + (imm if (w >> 23) & 1 else -imm),
                    8 if w & 0x100 else 4)
        if (w & 0x0FBF0E00) == 0x0D2D0A00:
            return (K_PUSH, cond, 0, 0)  # VPUSH
        if (w & 0x0FBF0E00) == 0x0CBD0A00:
            return (K_POP, cond, 0, 0)   # VPOP
        return (K_OTHER, cond, 0, 0)
    # op 0/1: data processing, multiplies, extra load/store, misc
    if op == 0 and (w & 0x90) == 0x90:
        sh = (w >> 5) & 3
        if sh == 0:
            return (K_OTHER, cond, 0, 0)  # multiply / swap / ldrex
        L = (w >> 20) & 1
        rn = (w >> 16) & 0xF
        P = (w >> 24) & 1
        W = (w >> 21) & 1
        I = (w >> 22) & 1
        if rn == 15 and P and not W and I:
            imm = ((w >> 4) & 0xF0) | (w & 0xF)
            a = pc + 8 + (imm if (w >> 23) & 1 else -imm)
            if L:
                size = {1: 2, 2: 1, 3: 2}[sh]
                return (K_LDRLIT, cond, a, size)
            if sh == 2:
                return (K_LDRLIT, cond, a, 8)  # LDRD
        if L and ((w >> 12) & 0xF) == 15:
            return (K_PCWRITE, cond, rn, 0)
        return (K_OTHER, cond, 0, 0)
    opc = (w >> 21) & 0xF
    S = (w >> 20) & 1
    rn = (w >> 16) & 0xF
    rd = (w >> 12) & 0xF
    I = (w >> 25) & 1
    if 8 <= opc <= 11 and not S:
        return (K_OTHER, cond, 0, 0)  # MRS/MSR/CLZ/etc.
    if rd == 15 and not (8 <= opc <= 11):
        if opc == 13 and not I and (w & 0xFFF) == 14:
            return (K_RET, cond, 14, 0)
        if opc == 4 and rn == 15 and not I and (w & 0xFF0) == 0x100:
            return (K_JT_ADD, cond, w & 0xF, 0)
        return (K_PCWRITE, cond, rn, 0)
    if I and rn == 15 and opc in (2, 4):
        imm = ror_imm(w)
        return (K_ADR, cond, (pc + 8 + (imm if opc == 4 else -imm)) & 0xFFFFFFFF, 0)
    return (K_OTHER, cond, 0, 0)


def decode_thumb(h, h2, pc):
    """Returns (kind, cond, a, b, length)."""
    top5 = h >> 11
    if top5 == 0x1E:  # BL/BLX prefix
        if h2 is not None and (h2 >> 11) in (0x1F, 0x1D):
            off = (sext(h & 0x7FF, 11) << 12) | ((h2 & 0x7FF) << 1)
            tgt = (pc + 4 + off) & 0xFFFFFFFF
            if (h2 >> 11) == 0x1F:
                return (K_BL, 14, tgt, 0, 4)
            if h2 & 1:
                return (K_INVALID, 14, 0, 0, 2)
            return (K_BLX_IMM, 14, tgt & ~3, 0, 4)
        return (K_INVALID, 14, 0, 0, 2)
    if top5 in (0x1F, 0x1D):
        return (K_INVALID, 14, 0, 0, 2)
    if (h & 0xFF00) == 0xB500 or (h & 0xFF00) == 0xB400:
        return (K_PUSH, 14, h & 0x1FF, 1 if h & 0x100 else 0, 2)
    if (h & 0xFF00) == 0xBD00:
        return (K_RET, 14, h & 0xFF, 1, 2)
    if (h & 0xFF00) == 0xBC00:
        return (K_POP, 14, h & 0xFF, 0, 2)
    if (h & 0xFF87) == 0x4700:
        rm = (h >> 3) & 0xF
        return ((K_RET if rm == 14 else K_BX), 14, rm, 0, 2)
    if (h & 0xFF87) == 0x4780:
        return (K_BLX_REG, 14, (h >> 3) & 0xF, 0, 2)
    if (h & 0xFF87) == 0x4687:  # MOV pc, rm
        rm = (h >> 3) & 0xF
        return ((K_RET if rm == 14 else K_PCWRITE), 14, rm, 0, 2)
    if (h & 0xFF87) == 0x4487:  # ADD pc, rm
        return (K_JT_ADD, 14, (h >> 3) & 0xF, 0, 2)
    if (h & 0xF000) == 0xD000:
        c = (h >> 8) & 0xF
        if c == 0xE:
            return (K_INVALID, 14, 0, 0, 2)
        if c == 0xF:
            return (K_SVC, 14, h & 0xFF, 0, 2)
        return (K_B, c, (pc + 4 + (sext(h & 0xFF, 8) << 1)) & 0xFFFFFFFF, 0, 2)
    if (h & 0xF800) == 0xE000:
        return (K_B, 14, (pc + 4 + (sext(h & 0x7FF, 11) << 1)) & 0xFFFFFFFF, 0, 2)
    if (h & 0xF800) == 0x4800:
        return (K_LDRLIT, 14, ((pc + 4) & ~3) + (h & 0xFF) * 4, 4, 2)
    if (h & 0xF800) == 0xA000:
        return (K_ADR, 14, ((pc + 4) & ~3) + (h & 0xFF) * 4, 0, 2)
    if (h & 0xFF00) == 0xBE00:  # BKPT
        return (K_INVALID, 14, 0, 0, 2)
    return (K_OTHER, 14, 0, 0, 2)


# ---------------------------------------------------------------- tiny formatter
def fmt_arm(w, pc):
    k, c, a, b = decode_arm(w, pc)
    cs = COND[c] if c < 16 else ""
    if (w & 0x0FFFFF00) == 0x0320F000:
        return ["nop", "yield", "wfe", "wfi", "sev"][w & 0xFF] + cs if (w & 0xFF) < 5 else "hint"
    if w == 0xE49DF004:
        return "pop {pc}  (ldr pc,[sp],#4)"
    if (w & 0x0FFFFFFF) == 0x01A0F00E:
        return "mov%s pc, lr" % cs
    if k in (K_B, K_BL):
        return "%s%s 0x%X" % (KNAMES[k], cs, a)
    if k == K_BLX_IMM:
        return "blx 0x%X (thumb)" % a
    if k == K_BX:
        return "bx%s r%d" % (cs, a)
    if k == K_BLX_REG:
        return "blx%s r%d" % (cs, a)
    if k == K_LDRLIT:
        return "ldr%s r%d, [pc] ; lit@0x%X size %d" % (cs, (w >> 12) & 15, a, b)
    if k == K_ADR:
        return "adr%s r%d, 0x%X" % (cs, (w >> 12) & 15, a)
    if k in (K_PUSH, K_POP, K_RET):
        regs = [("r%d" % i).replace("r13", "sp").replace("r14", "lr").replace("r15", "pc")
                for i in range(16) if a & (1 << i)] if (w & 0x0E000000) == 0x08000000 else []
        nm = {K_PUSH: "push", K_POP: "pop", K_RET: "pop"}[k]
        if w == 0xE12FFF1E or (k == K_RET and (w & 0x0FFFFFF0) == 0x012FFF10):
            return "bx%s lr" % cs
        return "%s%s {%s}" % (nm, cs, ", ".join(regs))
    if k == K_JT_ADD:
        return "add%s pc, pc, r%d, lsl #2  ; jump table" % (cs, a)
    if k == K_JT_LDR:
        return "ldr%s pc, [pc, r%d, lsl #2] ; jump table" % (cs, a)
    op = (w >> 25) & 7
    if op in (0, 1) and not ((w & 0x0E000090) == 0x00000090):
        opc = (w >> 21) & 0xF
        names = ["and", "eor", "sub", "rsb", "add", "adc", "sbc", "rsc", "tst",
                 "teq", "cmp", "cmn", "orr", "mov", "bic", "mvn"]
        rd, rn = (w >> 12) & 0xF, (w >> 16) & 0xF
        src = ("#0x%X" % ror_imm(w)) if w & 0x02000000 else ("r%d%s" % (
            w & 0xF, "" if (w & 0xFF0) == 0 else " <shift 0x%X>" % ((w >> 4) & 0xFF)))
        s = "s" if (w >> 20) & 1 and not 8 <= opc <= 11 else ""
        if 8 <= opc <= 11:
            return "%s%s r%d, %s" % (names[opc], cs, rn, src)
        if opc in (13, 15):
            return "%s%s%s r%d, %s" % (names[opc], s, cs, rd, src)
        return "%s%s%s r%d, r%d, %s" % (names[opc], s, cs, rd, rn, src)
    if op in (2, 3):
        L = "ldr" if (w >> 20) & 1 else "str"
        B = "b" if (w >> 22) & 1 else ""
        return "%s%s%s r%d, [r%d ...] (P%d U%d W%d)" % (
            L, B, cs, (w >> 12) & 15, (w >> 16) & 15, (w >> 24) & 1, (w >> 23) & 1, (w >> 21) & 1)
    return "%s%s (0x%08X)" % (KNAMES[k], cs, w)


# ---------------------------------------------------------------- image
class Image:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.d = f.read()
        self.text = self.d[:TEXT_SIZE]

    def in_text(self, a):
        return TEXT_VA <= a < TEXT_END

    def u32(self, a):
        if TEXT_VA <= a and a + 4 <= TEXT_END:
            return struct.unpack_from("<I", self.d, a - TEXT_VA)[0]
        if RODATA_VA <= a and a + 4 <= RODATA_VA + RODATA_SIZE:
            return struct.unpack_from("<I", self.d, a - RODATA_VA + RODATA_OFF)[0]
        if DATA_VA <= a and a + 4 <= DATA_VA + DATA_SIZE:
            return struct.unpack_from("<I", self.d, a - DATA_VA + DATA_OFF)[0]
        return None

    def u16(self, a):
        if TEXT_VA <= a and a + 2 <= TEXT_END:
            return struct.unpack_from("<H", self.d, a - TEXT_VA)[0]
        return None


# ---------------------------------------------------------------- analysis
class Analyzer:
    MAX_INSNS = 60000
    THUMB_GAP_SCAN = False

    def __init__(self, img):
        self.img = img
        self.code = {}            # addr -> 'A'/'T' (visited instruction)
        self.lits = {}            # literal addr -> size
        self.lit_refs = Counter()  # literal addr -> number of loads
        self.calls = defaultdict(list)   # target -> [site]  (BL/BLX imm)
        self.tails = defaultdict(list)   # target -> [site]  (B to known start)
        self.starts = {}          # addr -> mode
        self.src = defaultdict(set)      # addr -> set(source tags)
        self.jts = {}             # dispatch addr -> dict
        self.adr_targets = Counter()
        self.adr_data = Counter()        # ADR (rd != lr) targets: inline data
        self.adr_code = Counter()        # ADR lr targets: code labels
        self.adr_other = Counter()
        self.jt_lits = set()
        self.pcrel_lits = set()
        self.adr_lr_calls = set()
        self.noreturn_memo = {}
        self.noreturn_calls = Counter()  # BL target -> sites followed by a pool  # "ADR lr, next ; MOV pc, rX" indirect calls   # literals used as "ADD rX, pc, rX" offsets
        self.init_array = None
        self.ptr_midcode_rejected = 0
        self.lit_text_ptrs = Counter()   # literal values pointing into text
        self.invalid_hits = []
        self.veneers = {}

    # -- trial / committed descent ------------------------------------
    def descend(self, start, mode, commit=True, weak=False):
        """Recursive descent from start.  Returns (ok, info).
        ok=False if an invalid instruction or a literal collision was hit.
        weak=True (pointer/gap candidates) adds plausibility checks: the
        first ARM instruction must be unconditional, the path must not run
        into ADR-referenced inline data, and at most half of the decoded
        instructions may carry cond=EQ (small integers / UTF-16 text decode
        as cond=0x0 "andeq..."; cond=0xF words are rejected as invalid)."""
        img = self.img
        ncond = 0
        jtlits = set()
        pcrel = set()
        code = self.code
        local = {}
        lits = {}
        calls = []
        jts = []
        adrs = []
        work = [(start, mode)]
        bad = None
        n = 0
        while work:
            pc, m = work.pop()
            prev_bl = None
            while True:
                if not img.in_text(pc):
                    bad = ("out_of_text", pc)
                    break
                if pc in local:
                    break
                if pc in code:
                    if code[pc] != m:
                        bad = ("mode_clash", pc)
                    break
                if pc in self.lits or pc in lits:
                    if prev_bl is not None and pc == prev_bl[0] + 4:
                        # BL followed directly by a literal pool: the callee
                        # does not return (abort/panic style)
                        self.noreturn_calls[prev_bl[1]] += 1
                        break
                    bad = ("lit_collision", pc)
                    break
                if weak and pc in self.adr_data:
                    bad = ("adr_data_collision", pc)
                    break
                n += 1
                if n > self.MAX_INSNS:
                    bad = ("too_long", pc)
                    break
                if m == "A":
                    if pc & 3:
                        bad = ("misaligned", pc)
                        break
                    w = img.u32(pc)
                    k, c, a, b = decode_arm(w, pc)
                    size = 4
                else:
                    h = img.u16(pc)
                    h2 = img.u16(pc + 2)
                    k, c, a, b, size = decode_thumb(h, h2, pc)
                if c == 0:
                    ncond += 1
                if weak and pc == start and m == "A" and c != 14:
                    bad = ("weak_first_cond", pc)
                    break
                local[pc] = m
                if size == 4 and m == "T":
                    local[pc + 2] = m
                if k == K_INVALID or (k == K_TRAP and weak and pc == start):
                    bad = ("invalid", pc)
                    break
                if k == K_TRAP:
                    break
                prev_bl = (pc, a) if k == K_BL and c == 14 else None
                nxt = pc + size
                if k == K_LDRLIT:
                    lits[a] = max(lits.get(a, 0), b)
                    if m == "A" and b == 4 and self._is_pcrel_offset(pc, (img.u32(pc) >> 12) & 0xF):
                        pcrel.add(a)
                elif k == K_ADR:
                    adrs.append((a, (img.u32(pc) >> 12) & 0xF if m == "A" else 0))
                elif k in (K_BL, K_BLX_IMM):
                    tm = m if k == K_BL else ("T" if m == "A" else "A")
                    calls.append((a, tm, pc))
                    if c == 14 or True:
                        pc = nxt
                        continue
                elif k == K_B:
                    if c == 14:
                        if a in self.starts and a != start:
                            calls.append((a, m, -pc))  # tail call (negative site)
                            break
                        pc = a
                        continue
                    work.append((a, m))
                elif k in (K_RET, K_BX, K_PCWRITE):
                    if c == 14 and not (m == "A" and k != K_RET and self._is_adr_lr_call(pc)):
                        break
                    if k != K_RET and m == "A" and self._is_adr_lr_call(pc):
                        self.adr_lr_calls.add(pc)
                elif k == K_VENEER:
                    lits[a] = 4
                    tv = img.u32(a)
                    if tv is not None:
                        calls.append((tv & ~1, "T" if tv & 1 else "A", -pc))
                    if c == 14:
                        break
                elif k == K_JT_ADD and m == "A":
                    n_ent = self._jt_count(local, pc, a, c)
                    jt = {"addr": pc, "kind": "add_pc_b_table", "index": a,
                          "entries": n_ent, "cond": COND[c]}
                    jts.append(jt)
                    if c != 14:
                        work.append((pc + 4, m))  # default branch
                    if n_ent is None:
                        # walk B instructions until a non-branch
                        q = pc + 8
                        cnt = 0
                        while img.in_text(q) and cnt < 1024:
                            kk = decode_arm(img.u32(q), q)
                            if kk[0] != K_B or kk[1] != 14:
                                break
                            q += 4
                            cnt += 1
                        n_ent = cnt
                        jt["entries"] = cnt
                        jt["guessed"] = True
                    for i in range(n_ent):
                        work.append((pc + 8 + 4 * i, m))
                    break
                elif k == K_JT_LDR and m == "A":
                    n_ent = self._jt_count(local, pc, a, c)
                    jt = {"addr": pc, "kind": "ldr_pc_addr_table", "index": a,
                          "entries": n_ent, "cond": COND[c]}
                    jts.append(jt)
                    if n_ent is None:
                        n_ent = self._jt_walk_addrs(pc)
                        jt["entries"] = n_ent
                        jt["guessed"] = True
                    if b == 0x10:  # LSL #2
                        # ARMCC layout: LDRcc pc,[pc,rX,LSL#2] ; B default ;
                        # .word case0 ; .word case1 ...
                        for i in range(n_ent):
                            ea = pc + 8 + 4 * i
                            lits[ea] = 4
                            jtlits.add(ea)
                            tv = img.u32(ea)
                            if tv is not None and img.in_text(tv & ~1):
                                work.append((tv & ~1, "T" if tv & 1 else "A"))
                        if c != 14:
                            work.append((pc + 4, m))  # default branch
                    break
                elif k == K_JT_ADD and m == "T":
                    jts.append({"addr": pc, "kind": "thumb_add_pc", "index": a,
                                "entries": None, "cond": ""})
                    break
                pc = nxt
            if bad:
                break
        # literal/code overlap check inside this descent
        if not bad:
            for la, ls in lits.items():
                for o in range(0, ls, 2 if mode == "T" else 4):
                    if la + o in local or self.code.get(la + o):
                        bad = ("lit_in_code", la)
                        break
                if bad:
                    break
        if not bad and weak and n >= 4 and ncond * 2 > n:
            bad = ("weak_cond_ratio", start)
        ok = bad is None
        info = {"local": local, "lits": lits, "calls": calls, "jts": jts,
                "adrs": adrs, "bad": bad, "n": n, "ncond": ncond}
        if ok and commit:
            self.code.update(local)
            for la, ls in lits.items():
                self.lits[la] = max(self.lits.get(la, 0), ls)
                self.lit_refs[la] += 1
                if la in jtlits:
                    self.jt_lits.add(la)
                elif la in pcrel:
                    self.pcrel_lits.add(la)
                elif ls == 4:
                    v = self.img.u32(la)
                    if v is not None and self.img.in_text(v & ~1):
                        self.lit_text_ptrs[v] += 1
            for jt in jts:
                self.jts[jt["addr"]] = jt
            for a, rd in adrs:
                self.adr_targets[a] += 1
                w = self.img.u32(a) if self.img.in_text(a) else None
                if rd == 14:
                    self.adr_code[a] += 1   # "adr lr, label" = return address
                elif w is not None and (w >> 28) != 0xE:
                    self.adr_data[a] += 1   # inline const data / UTF-16 text
                else:
                    self.adr_other[a] += 1  # cond=AL word: code label or data
        return ok, info

    def _jt_count(self, local, pc, reg, cond=None):
        """Find CMP reg,#N in the preceding 8 instructions.
        ARMCC: CMP rX,#N ; LDRCC/ADDCC pc,... -> N entries (unsigned <N);
        with LS (<=N) -> N+1 entries.  Other conditions: unknown (None)."""
        if cond is None:
            cond = decode_arm(self.img.u32(pc), pc)[1]
        for back in range(1, 9):
            q = pc - 4 * back
            if q not in local and q not in self.code:
                continue
            w = self.img.u32(q)
            if (w & 0x0FF00000) == 0x03500000 and ((w >> 16) & 0xF) == reg:
                n = ror_imm(w)
                if cond == 3:
                    return n
                if cond == 9:
                    return n + 1
                return None
        return None

    def _is_adr_lr_call(self, pc):
        """Old-style indirect call: ADR lr, pc+4 within the 4 previous insns."""
        for j in range(1, 5):
            q = pc - 4 * j
            w = self.img.u32(q)
            if w is None:
                return False
            if (w & 0x0FFFF000) == 0x028FE000 and q + 8 + ror_imm(w) == pc + 4:
                return True
        return False

    def _is_pcrel_offset(self, pc, rd):
        """LDR rd,=off followed within 6 insns by ADD rX, pc, rd (or rd, pc):
        the literal is a PC-relative offset (position-independent code), not
        a pointer, even if its value happens to fall inside .text."""
        for j in range(1, 7):
            q = pc + 4 * j
            w = self.img.u32(q)
            if w is None:
                return False
            if (w & 0x0FE00FF0) == 0x00800000:  # ADD rd, rn, rm (no shift)
                rn, rm = (w >> 16) & 0xF, w & 0xF
                if (rn == 15 and rm == rd) or (rm == 15 and rn == rd):
                    return True
            k = decode_arm(w, q)[0]
            if k in (K_B, K_BL, K_RET, K_BX, K_BLX_REG, K_PCWRITE):
                return False
        return False

    def _jt_walk_addrs(self, pc):
        """Guess an address-table length: consecutive 4-aligned .text words."""
        q = pc + 8
        cnt = 0
        while cnt < 1024:
            v = self.img.u32(q)
            if v is None or not (TEXT_VA <= v < TEXT_END) or v & 3:
                break
            q += 4
            cnt += 1
        return cnt

    # -- driver -----------------------------------------------------------
    def add_start(self, a, m, tag):
        if a not in self.starts:
            self.starts[a] = m
        self.src[a].add(tag)

    def closure(self, queue, tag, validate):
        """Descend from (addr, mode) candidates; follow BL targets."""
        added = 0
        base_validate = validate
        while queue:
            a, m, t = queue.pop()
            # BL/BLX/tail targets found while exploring weak candidates are
            # still strong evidence; only the seed candidates are "weak".
            validate = base_validate and t not in self.STRONG
            if not self.img.in_text(a):
                continue
            if m == "A" and a & 3:
                continue
            if a in self.code:
                if a in self.starts or self.code[a] != m:
                    if a in self.starts:
                        self.src[a].add(t)
                    continue
                # already-visited code reached as a call target -> new start.
                # Pointer/gap candidates must not be reachable by fall-through.
                if validate and not self._no_fallthrough_into(a, m):
                    self.ptr_midcode_rejected += 1
                    continue
                self.add_start(a, m, t)
                continue
            ok, info = self.descend(a, m, commit=True, weak=validate)
            if not ok:
                if validate:
                    continue
                self.invalid_hits.append((a, m, t, info["bad"]))
                # commit partial knowledge anyway for confident starts
                ok2, info = self.descend(a, m, commit=False)
                continue
            self.add_start(a, m, t)
            added += 1
            for (ta, tm, site) in info["calls"]:
                if site >= 0:
                    queue.append((ta, tm, "bl"))
                else:
                    queue.append((ta, tm, "tail"))
        return added

    def _no_fallthrough_into(self, a, m):
        """True if the instruction before a cannot fall through into a."""
        if m != "A":
            return False
        p = a - 4
        if p in self.lits or p not in self.code:
            return True
        k, c, t, b = decode_arm(self.img.u32(p), p)
        if c != 14:
            return False
        return k in (K_RET, K_B, K_BX, K_PCWRITE, K_VENEER, K_JT_ADD, K_JT_LDR)

    def find_init_array(self):
        """crt0 calls an ARMCC C++ static-init runner that walks a table of
        self-relative offsets: LDR rX,=off ; ADD rX,pc,rX (twice: begin/end).
        Returns (begin, end, runner) or None."""
        img = self.img
        for i in range(0, 0x24, 4):
            k, c, t, _ = decode_arm(img.u32(TEXT_VA + i), TEXT_VA + i)
            if k != K_BL:
                continue
            found = []
            regs = {}
            for j in range(32):
                p = t + 4 * j
                w = img.u32(p)
                kk = decode_arm(w, p)
                if kk[0] == K_LDRLIT and kk[3] == 4:
                    regs[(w >> 12) & 0xF] = img.u32(kk[2])
                elif (w & 0x0FFF0FF0) == 0x008F0000 and (w & 0xF) in regs \
                        and ((w >> 12) & 0xF) == (w & 0xF):
                    found.append((p + 8 + regs[w & 0xF]) & 0xFFFFFFFF)
                if kk[0] == K_RET and kk[1] == 14:
                    break
            if len(found) >= 2 and TEXT_VA <= found[0] < found[1] <= TEXT_END:
                return (found[0], found[1], t)
        return None

    def run(self):
        img = self.img
        # Phase 1: entry point and everything reachable by BL.
        self.closure([(TEXT_VA, "A", "entry")], "entry", validate=False)
        # Phase 1b: C++ static initialisers (self-relative init_array)
        ia = self.find_init_array()
        if ia:
            b, e, runner = ia
            q = []
            for ea in range(b, e, 4):
                self.lits[ea] = 4
                tv = (ea + img.u32(ea)) & 0xFFFFFFFF
                q.append((tv & ~1, "T" if tv & 1 else "A", "init_array"))
            self.init_array = {"begin": b, "end": e, "runner": runner,
                               "entries": (e - b) // 4}
            self.closure(q, "init_array", validate=False)
        # Phase 2: literal pool values that point into .text (callbacks).
        rounds = []
        for it in range(8):
            before = len(self.starts)
            q = []
            for v in list(self.lit_text_ptrs):
                q.append((v & ~1, "T" if v & 1 else "A", "litptr"))
            self.closure(q, "litptr", validate=True)
            # Phase 3: pointers in .rodata/.data (vtables, callback tables)
            q = []
            for base, off, size in ((RODATA_VA, RODATA_OFF, RODATA_SIZE),
                                    (DATA_VA, DATA_OFF, DATA_SIZE)):
                for i in range(0, size - 3, 4):
                    v = struct.unpack_from("<I", img.d, off + i)[0]
                    if TEXT_VA <= v < TEXT_END:
                        if v & 1:
                            q.append((v & ~1, "T", "dataptr"))
                        elif not v & 3:
                            q.append((v, "A", "dataptr"))
            self.closure(q, "dataptr", validate=True)
            # Phase 4: gap scan (prologues, then first valid instruction)
            self.gap_fill()
            rounds.append(len(self.starts) - before)
            if len(self.starts) == before:
                break
        self.rounds = rounds
        self.prune_weak_starts()
        self.finalize()

    STRONG = {"entry", "bl", "tail", "init_array"}

    def is_noreturn(self, t, depth=0):
        """Function at t never returns: no return / indirect jump / tail
        branch to another start is reachable (BLs to noreturn callees end a
        path).  Memoised; recursion depth-limited (deep -> assume returns)."""
        memo = self.noreturn_memo
        if t in memo:
            return memo[t]
        if depth > 6 or not self.img.in_text(t) or t & 3:
            return False
        memo[t] = False   # provisional (recursion guard)
        img = self.img
        seen = set()
        work = [t]
        returns = False
        while work and not returns and len(seen) < 4000:
            pc = work.pop()
            while img.in_text(pc) and pc not in seen:
                seen.add(pc)
                k, c, a, b = decode_arm(img.u32(pc), pc)
                if k == K_INVALID:
                    returns = True   # unknown -> be conservative
                    break
                if k in (K_RET, K_BX, K_PCWRITE, K_VENEER, K_JT_ADD, K_JT_LDR):
                    if k in (K_JT_ADD, K_JT_LDR) or c == 14:
                        if k in (K_JT_ADD, K_JT_LDR) or pc not in self.adr_lr_calls:
                            returns = True   # (jump tables: give up)
                            break
                if k == K_B:
                    if a in self.starts and a != t:
                        returns = True
                        break
                    if c == 14:
                        pc = a
                        continue
                    work.append(a)
                if k == K_BL and c == 14 and self.is_noreturn(a, depth + 1):
                    break
                pc += 4
        memo[t] = not returns
        return memo[t]

    def prune_weak_starts(self):
        """Drop pointer/gap-derived starts that ordinary code falls into.
        A coincidental .data value (or literal) that lands mid-function
        passes the descent check if it was tried before the enclosing
        function was discovered.  Rule: drop a weak start s if the word
        before it is reached code whose instruction can fall through (not a
        terminator, not a BL - noreturn calls end functions) and s is not a
        prologue (STMFD sp!,{..lr} / STR lr,[sp,#-4]! / VPUSH / SUB sp)."""
        img = self.img
        dropped = []
        for s in list(self.starts):
            if self.src[s] & self.STRONG or self.starts[s] != "A":
                continue
            p = s - 4
            if p not in self.code or p in self.lits:
                continue
            k, c, t, b = decode_arm(img.u32(p), p)
            if c == 14 and k in (K_RET, K_B, K_BX, K_PCWRITE, K_VENEER,
                                 K_JT_ADD, K_JT_LDR) and p not in self.adr_lr_calls:
                continue
            if c == 14 and k == K_BL and self.is_noreturn(t):
                continue
            w = img.u32(s)
            if (w & 0xFFFF4000) == 0xE92D4000 or w == 0xE52DE004                     or (w & 0x0FBF0E00) == 0x0D2D0A00 or (w & 0xFFFFF000) == 0xE24DD000:
                continue
            dropped.append(s)
        for s in dropped:
            del self.starts[s]
            self.dropped_srcs = getattr(self, "dropped_srcs", Counter())
            for t in self.src[s]:
                self.dropped_srcs[t] += 1
            del self.src[s]
        self.pruned = len(dropped)

    def gaps(self):
        """Yield (start, end) of 4-aligned regions not covered by code/lits."""
        covered = bytearray(TEXT_SIZE // 2 + 1)
        for a in self.code:
            covered[(a - TEXT_VA) >> 1] = 1
            if self.code[a] == "A":
                covered[((a - TEXT_VA) >> 1) + 1] = 1
        for a, s in self.lits.items():
            if img_in(a):
                for o in range(0, s, 2):
                    idx = (a + o - TEXT_VA) >> 1
                    if idx < len(covered):
                        covered[idx] = 1
        res = []
        i = 0
        n = TEXT_SIZE // 2
        while i < n:
            if covered[i]:
                i += 1
                continue
            j = i
            while j < n and not covered[j]:
                j += 1
            res.append((TEXT_VA + 2 * i, TEXT_VA + 2 * j))
            i = j
        return res

    def gap_fill(self):
        img = self.img
        for it in range(6):
            progress = 0
            for gs, ge in self.gaps():
                a = (gs + 3) & ~3
                # prologue scan inside the gap
                q = []
                first = None
                while a + 4 <= ge:
                    w = img.u32(a)
                    if first is None and (w >> 28) == 0xE and a not in self.adr_data:
                        first = a
                    if (w & 0xFFFF4000) == 0xE92D4000 or w == 0xE52DE004:
                        q.append((a, "A", "prologue"))
                    a += 4
                if q:
                    progress += self.closure(q, "prologue", validate=True)
                if first is not None and first not in self.code:
                    progress += self.closure([(first, "A", "gap")], "gap", validate=True)
                # Thumb prologue (PUSH {..,lr}) in gaps where ARM failed
                # Thumb prologue scan disabled by default: no Thumb code was
                # found by any reliable route (0 BLX-imm, 0 Thumb pointers),
                # and PUSH {..lr} halfwords occur inside ARM words (e.g.
                # 0xB551xxxx = LDRBLT), giving false Thumb functions.
                if self.THUMB_GAP_SCAN and not q and first is not None and first not in self.code:
                    b = gs
                    tq = []
                    while b + 2 <= ge:
                        h = img.u16(b)
                        if (h & 0xFF00) == 0xB500:
                            tq.append((b, "T", "thumb_prologue"))
                        b += 2
                    if tq and len(tq) < 64:
                        progress += self.closure(tq, "thumb_prologue", validate=True)
            if not progress:
                break

    # -- final ownership -----------------------------------------------
    def finalize(self):
        img = self.img
        starts = sorted(self.starts)
        self.sorted_starts = starts
        self.funcs = []
        start_set = set(starts)
        # recount callers using only confirmed code
        callers = Counter()
        tails = Counter()
        for a, m in self.code.items():
            if m == "A":
                if a & 3:
                    continue
                k, c, t, _ = decode_arm(img.u32(a), a)
                if k in (K_BL, K_BLX_IMM):
                    callers[t] += 1
                elif k == K_B and c == 14 and t in start_set:
                    tails[t] += 1
            else:
                h = img.u16(a)
                if (h >> 11) == 0x1E:
                    k, c, t, _, _ = decode_thumb(h, img.u16(a + 2), a)
                    if k in (K_BL, K_BLX_IMM):
                        callers[t] += 1
        self.callers = callers
        # ownership: re-descend each start; a branch to another start, or any
        # branch leaving [start, next_start), is a tail call.  Out-of-range
        # targets that are not yet starts become new starts ("tail_range")
        # and the pass repeats until stable.
        import bisect
        self.tail_range_added = 0
        for _iter in range(10):
            new = self._ownership_pass(starts, start_set)
            if not new:
                break
            for a in new:
                self.add_start(a, self.code[a], "tail_range")
            self.tail_range_added += len(new)
            starts = sorted(self.starts)
            start_set = set(starts)
        self.sorted_starts = starts
        tails = self.tails_ct
        self._finish(starts, callers, tails)

    def _ownership_pass(self, starts, start_set):
        import bisect
        img = self.img
        claimed = {}
        lits_owner = {}
        self.funcs = []
        self.tails_ct = Counter()
        new_starts = set()
        for idx, s in enumerate(starts):
            lim = starts[idx + 1] if idx + 1 < len(starts) else TEXT_END
            m = self.starts[s]
            local = {}
            mylits = set()
            work = [s]
            ninsn = 0
            jt_count = 0
            while work:
                pc = work.pop()
                while img.in_text(pc) and pc not in local and pc in self.code:
                    if pc != s and pc in start_set:
                        break
                    if pc in self.lits:
                        break
                    if pc in claimed:
                        break
                    local[pc] = 1
                    ninsn += 1
                    if m == "A":
                        k, c, a, b = decode_arm(img.u32(pc), pc)
                        size = 4
                    else:
                        k, c, a, b, size = decode_thumb(img.u16(pc), img.u16(pc + 2), pc)
                    nxt = pc + size
                    if k == K_LDRLIT:
                        mylits.add(a)
                    elif k == K_VENEER:
                        mylits.add(a)
                        if c == 14:
                            break
                    elif k == K_B:
                        out = a in start_set or a < s or a >= lim
                        if out:
                            self.tails_ct[a] += 1
                            if a not in start_set and a in self.code:
                                new_starts.add(a)
                            if c == 14:
                                break
                        elif c == 14:
                            pc = a
                            continue
                        else:
                            work.append(a)
                    elif k in (K_RET, K_BX, K_PCWRITE) and c == 14                             and pc not in self.adr_lr_calls:
                        break
                    elif k in (K_JT_ADD, K_JT_LDR):
                        jt = self.jts.get(pc)
                        jt_count += 1
                        if jt and jt["entries"]:
                            if k == K_JT_ADD:
                                for i in range(jt["entries"]):
                                    work.append(pc + 8 + 4 * i)
                                if c != 14:
                                    work.append(pc + 4)
                            else:
                                for i in range(jt["entries"]):
                                    ea = pc + 8 + 4 * i
                                    mylits.add(ea)
                                    tv = img.u32(ea)
                                    work.append(tv & ~1)
                                if c != 14:
                                    work.append(pc + 4)
                        break
                    pc = nxt
            for a in local:
                claimed[a] = s
            for la in mylits:
                lits_owner.setdefault(la, s)
            hi = max(local) + (4 if m == "A" else 2) if local else s + 4
            for la in mylits:
                if la > s and la + self.lits.get(la, 4) > hi and la - hi < 0x1000:
                    hi = la + self.lits.get(la, 4)
            codehi = max(local) + (4 if m == "A" else 2) if local else s + 4
            self.funcs.append({"start": s, "mode": m, "extent": hi,
                               "codehi": codehi, "ninsn": ninsn, "jts": jt_count})
        self.claimed = claimed
        self.lits_owner = lits_owner
        return new_starts

    def _finish(self, starts, callers, tails):
        # end_guess: min(extent, next start); size
        for i, f in enumerate(self.funcs):
            nxt = self.funcs[i + 1]["start"] if i + 1 < len(self.funcs) else TEXT_END
            f["next"] = nxt
            end = min(f["extent"], nxt)
            f["overlap"] = f["codehi"] > nxt
            f["lit_past_next"] = f["extent"] > nxt and not f["overlap"]
            # extend over trailing padding / unreached bytes up to next start?
            f["end_guess"] = end
            f["size"] = end - f["start"]
            f["callers"] = callers.get(f["start"], 0) + callers.get(f["start"] | 1, 0) \
                if f["mode"] == "T" else callers.get(f["start"], 0)
            f["tails"] = tails.get(f["start"], 0)
            f["dataptr"] = "dataptr" in self.src[f["start"]]
            f["sources"] = "+".join(sorted(self.src[f["start"]]))


def img_in(a):
    return TEXT_VA <= a < TEXT_END


# ---------------------------------------------------------------- linear stats
def linear_stats(img):
    t = img.text
    n = len(t) // 4
    words = struct.unpack_from("<%dI" % n, t)
    c = Counter()
    bl_tgt_in = 0
    for i, w in enumerate(words):
        pc = TEXT_VA + 4 * i
        if (w & 0x0F000000) == 0x0B000000 and (w >> 28) != 0xF:
            c["arm_bl_all_cond"] += 1
            if (w >> 28) == 0xE:
                c["arm_bl_al"] += 1
                tgt = (pc + 8 + (sext(w & 0xFFFFFF, 24) << 2)) & 0xFFFFFFFF
                if img_in(tgt):
                    bl_tgt_in += 1
        elif (w & 0xFE000000) == 0xFA000000:
            c["arm_blx_imm"] += 1
        if w == 0xE12FFF1E:
            c["arm_bx_lr"] += 1
        if (w & 0x0FFFFFF0) == 0x012FFF30:
            c["arm_blx_reg"] += 1
        if (w & 0x0FFFFFF0) == 0x012FFF10 and (w & 0xF) != 14:
            c["arm_bx_reg_not_lr"] += 1
        if (w & 0xFFFF4000) == 0xE92D4000:
            c["arm_stmfd_sp_lr"] += 1
        if (w & 0xFFFF8000) == 0xE8BD8000:
            c["arm_ldmfd_sp_pc"] += 1
        if (w & 0xFFFF0000) == 0xE92D0000:
            c["arm_stmfd_sp_any"] += 1
        if (w & 0xFFFF0000) == 0xE8BD0000:
            c["arm_ldmfd_sp_any"] += 1
        if (w & 0x0FBF0E00) == 0x0D2D0A00:
            c["arm_vpush"] += 1
        if w == 0x00000000:
            c["zero_words"] += 1
    c["arm_bl_al_target_in_text"] = bl_tgt_in
    # thumb halfword scan (naive; ARM words split into halves add noise)
    hn = len(t) // 2
    hw = struct.unpack_from("<%dH" % hn, t)
    for i, h in enumerate(hw):
        if (h & 0xFF00) == 0xB500:
            c["thumb_push_lr_halfwords"] += 1
        if (h & 0xFF00) == 0xBD00:
            c["thumb_pop_pc_halfwords"] += 1
        if h == 0x4770:
            c["thumb_bx_lr_halfwords"] += 1
        if (h >> 11) == 0x1E and i + 1 < hn and (hw[i + 1] >> 11) == 0x1F:
            c["thumb_bl_pairs_naive"] += 1
    return dict(c)


# ---------------------------------------------------------------- selftest
def selftest(img=None):
    """Hand-checked encodings (ARM ARM / known compiler output)."""
    cases = [
        # (word, pc, expected kind, expected a)
        (0xEB000007, 0x100000, K_BL, 0x100024),    # bl +0x1C (+8)
        (0xEAFFFFFE, 0x200000, K_B, 0x200000),     # b . (self loop)
        (0x3AFFFFFC, 0x100038, K_B, 0x100030),     # bcc back 2 insns
        (0xFA000000, 0x100000, K_BLX_IMM, 0x100008),
        (0xFB000000, 0x100000, K_BLX_IMM, 0x10000A),  # H bit
        (0xE12FFF1E, 0, K_RET, 14),                # bx lr
        (0xE12FFF13, 0, K_BX, 3),                  # bx r3
        (0xE12FFF33, 0, K_BLX_REG, 3),             # blx r3
        (0xE92D4010, 0, K_PUSH, 0x4010),           # push {r4, lr}
        (0xE8BD8010, 0, K_RET, 0x8010),            # pop {r4, pc}
        (0xE8BD0010, 0, K_POP, 0x0010),            # pop {r4}
        (0xE49DF004, 0, K_RET, 0),                 # ldr pc, [sp], #4
        (0xE1A0F00E, 0, K_RET, 14),                # mov pc, lr
        (0xE59F0014, 0x100024, K_LDRLIT, 0x100040),  # ldr r0,[pc,#0x14]
        (0xE51F0004, 0x100000, K_LDRLIT, 0x100004),  # ldr r0,[pc,#-4]
        (0xE51FF004, 0x100000, K_VENEER, 0x100004),  # ldr pc,[pc,#-4]
        (0xE1CF00D8, 0x100000, K_LDRLIT, 0x100010),  # ldrd r0,[pc,#8]
        (0xED9F0A01, 0x100000, K_LDRLIT, 0x10000C),  # vldr s0,[pc,#4]
        (0xED2D8B02, 0, K_PUSH, 0),                # vpush {d8}
        (0xE28F0008, 0x100000, K_ADR, 0x100010),   # adr r0, pc+8+8
        (0x908FF101, 0, K_JT_ADD, 1),              # addls pc,pc,r1,lsl #2
        (0x979FF101, 0, K_JT_LDR, 1),              # ldrls pc,[pc,r1,lsl #2]
        (0xEF000032, 0, K_SVC, 0x32),              # svc 0x32
        (0xE7F000F0, 0, K_TRAP, 0),                # udf #0 (trap)
        (0x07F000F0, 0, K_INVALID, 0),             # conditional udf: data
        (0xF0000000, 0, K_INVALID, 0),             # cond=NV garbage
        (0xEC000100, 0, K_INVALID, 0),             # coproc p1 (not VFP/cp15)
        (0xEE070F9A, 0, K_OTHER, 0),               # mcr p15 (DSB-ish cp15 op)
        (0xE3A02000, 0, K_OTHER, 0),               # mov r2,#0
    ]
    tcases = [
        (0xB510, None, 0, K_PUSH, 0x110),          # push {r4, lr}
        (0xBD10, None, 0, K_RET, 0x10),            # pop {r4, pc}
        (0x4770, None, 0, K_RET, 14),              # bx lr
        (0x4718, None, 0, K_BX, 3),                # bx r3
        (0xF000, 0xF800, 0x1000, K_BL, 0x1004),    # bl +0
        (0xF7FF, 0xFFFE, 0x1000, K_BL, 0x1000),    # bl . (-4)
        (0xF000, 0xE800, 0x1002, K_BLX_IMM, 0x1004),  # blx -> arm, aligned
        (0xE7FE, None, 0x2000, K_B, 0x2000),       # b .
        (0xD0FE, None, 0x2000, K_B, 0x2000),       # beq .
        (0x4801, None, 0x2002, K_LDRLIT, 0x2008),  # ldr r0,[pc,#4] aligned
        (0xDE00, None, 0, K_INVALID, 0),           # udf
        (0xF800, None, 0, K_INVALID, 0),           # lone BL suffix
    ]
    fails = 0
    lines = []
    for w, pc, ek, ea in cases:
        k, c, a, b = decode_arm(w, pc)
        good = k == ek and (a == ea or ek in (K_OTHER, K_INVALID, K_SVC) and (ek != K_SVC or a == ea))
        fails += not good
        lines.append("%s ARM   %08X @%06X -> %-8s a=0x%X   [%s]" % (
            "ok  " if good else "FAIL", w, pc, KNAMES[k], a, fmt_arm(w, pc)))
    for h, h2, pc, ek, ea in tcases:
        k, c, a, b, sz = decode_thumb(h, h2, pc)
        good = k == ek and (a == ea or ek == K_INVALID)
        fails += not good
        lines.append("%s THUMB %04X %s @%06X -> %-8s a=0x%X" % (
            "ok  " if good else "FAIL", h, ("%04X" % h2) if h2 is not None else "    ",
            pc, KNAMES[k], a))
    return fails, lines


# ---------------------------------------------------------------- reporting
def pct(a, b):
    return "%.1f%%" % (100.0 * a / b) if b else "n/a"


def main():
    img = Image(CODE_BIN)
    fails, stlines = selftest(img)
    if "--selftest" in sys.argv:
        print("\n".join(stlines))
        print("selftest failures:", fails)
        return 1 if fails else 0
    os.makedirs(OUT_DIR, exist_ok=True)
    lin = linear_stats(img)
    an = Analyzer(img)
    an.run()
    funcs = an.funcs

    # ---- functions.csv
    with open(os.path.join(OUT_DIR, "functions.csv"), "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["start", "end_guess", "mode", "callers", "size",
                     "tail_callers", "ninsn", "jump_tables", "sources", "overlap_next"])
        for fn in funcs:
            wr.writerow(["0x%08X" % fn["start"], "0x%08X" % fn["end_guess"],
                         "ARM" if fn["mode"] == "A" else "THUMB", fn["callers"],
                         fn["size"], fn["tails"], fn["ninsn"], fn["jts"],
                         fn["sources"], int(fn["overlap"])])

    # ---- literal pools
    lit_addrs = sorted(a for a in an.lits if img_in(a))
    pools = []
    for a in lit_addrs:
        s = an.lits[a]
        if pools and a <= pools[-1][1] + 0:
            pools[-1][1] = max(pools[-1][1], a + s)
            pools[-1][2] += 1
        else:
            pools.append([a, a + s, 1])
    with open(os.path.join(OUT_DIR, "funcmap_literal_pools.csv"), "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["start", "end", "entries", "bytes", "owner_func"])
        for s, e, cnt in pools:
            wr.writerow(["0x%08X" % s, "0x%08X" % e, cnt, e - s,
                         "0x%08X" % an.lits_owner[s] if s in an.lits_owner else ""])
    lit_bytes = sum(e - s for s, e, _ in pools)

    # ---- jump tables
    with open(os.path.join(OUT_DIR, "funcmap_jumptables.csv"), "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["dispatch", "kind", "cond", "index_reg", "entries", "entries_guessed", "owner_func"])
        for a in sorted(an.jts):
            jt = an.jts[a]
            wr.writerow(["0x%08X" % a, jt["kind"], jt["cond"], "r%d" % jt["index"],
                         jt["entries"] if jt["entries"] is not None else "",
                         int(bool(jt.get("guessed"))),
                         "0x%08X" % an.claimed[a] if a in an.claimed else ""])

    # ---- stats
    arm_insn = sum(1 for m in an.code.values() if m == "A")
    th_bytes = sum(1 for m in an.code.values() if m == "T") * 2
    code_bytes = arm_insn * 4 + th_bytes
    gaps = an.gaps()
    gap_bytes = sum(e - s for s, e in gaps)
    zero_gap = 0
    for s, e in gaps:
        if img.text[s - TEXT_VA:e - TEXT_VA].count(0) == e - s:
            zero_gap += e - s
    sizes = sorted(fn["size"] for fn in funcs)
    nf = len(funcs)

    def q(p):
        return sizes[min(nf - 1, int(p * nf))] if nf else 0
    buckets = [(0, 8), (8, 16), (16, 32), (32, 64), (64, 128), (128, 256), (256, 512),
               (512, 1024), (1024, 4096), (4096, 16384), (16384, 1 << 30)]
    hist = []
    for lo, hi in buckets:
        hist.append(("%d-%d" % (lo, hi - 1) if hi < 1 << 30 else ">=%d" % lo,
                     sum(1 for s in sizes if lo <= s < hi)))
    mode_counts = Counter(fn["mode"] for fn in funcs)
    src_counts = Counter()
    for fn in funcs:
        for t in fn["sources"].split("+"):
            src_counts[t] += 1
    only_src = Counter(fn["sources"] for fn in funcs)
    # code-reached kind stats
    kstat = Counter()
    for a, m in an.code.items():
        if m == "A":
            k, c, t, b = decode_arm(img.u32(a), a)
            kstat["A_" + KNAMES[k] + ("" if c == 14 else "_cond")] += 1
            if k == K_PUSH and b:
                kstat["A_push_with_lr"] += 1
        else:
            h = img.u16(a)
            if a - 2 in an.code and an.code[a - 2] == "T" and (img.u16(a - 2) >> 11) == 0x1E:
                continue
            k, c, t, b, sz = decode_thumb(h, img.u16(a + 2), a)
            kstat["T_" + KNAMES[k]] += 1
    largest = sorted(funcs, key=lambda f: -f["size"])[:25]
    most_called = sorted(funcs, key=lambda f: -f["callers"])[:15]
    overlaps = sum(1 for f in funcs if f["overlap"])
    no_callers = sum(1 for f in funcs if f["callers"] == 0 and f["tails"] == 0)
    jt_kinds = Counter(j["kind"] for j in an.jts.values())
    jt_guessed = sum(1 for j in an.jts.values() if j.get("guessed"))
    jt_entries = sum((j["entries"] or 0) for j in an.jts.values())
    thumb_funcs = [f for f in funcs if f["mode"] == "T"]

    # gap classification
    adr_data_set = set(an.adr_data)
    gap_cls = Counter()
    gap_cls_bytes = Counter()
    gap_rows = []
    for gs, ge in gaps:
        blob = img.text[gs - TEXT_VA:ge - TEXT_VA]
        nw = max(1, (ge - gs) // 4)
        words = [img.u32(a) for a in range((gs + 3) & ~3, ge - 3, 4)]
        if blob.count(0) == len(blob):
            cls = "zero_padding"
        elif any(a in adr_data_set for a in range(gs & ~3, ge, 4)):
            cls = "adr_inline_data"
        elif words and sum(1 for w in words if TEXT_VA <= w < DATA_VA + DATA_SIZE + BSS_SIZE) * 2 >= len(words):
            cls = "pointer_or_offset_table"
        elif words and sum(1 for w in words if (w >> 28) == 0xE) * 10 >= 6 * len(words):
            cls = "code_like_unreached"
        else:
            cls = "data_like"
        gap_cls[cls] += 1
        gap_cls_bytes[cls] += ge - gs
        gap_rows.append((gs, ge, cls))
    with open(os.path.join(OUT_DIR, "funcmap_gaps.csv"), "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["start", "end", "bytes", "class"])
        for gs, ge, cls in gap_rows:
            wr.writerow(["0x%08X" % gs, "0x%08X" % ge, ge - gs, cls])

    # indirect pc writes in reached code
    pcw = Counter()
    for a, m in an.code.items():
        if m != "A":
            continue
        w = img.u32(a)
        k, c, t, b = decode_arm(w, a)
        if k == K_BLX_REG:
            pcw["blx_reg (indirect call)"] += 1
        elif k == K_BX:
            pcw["bx_reg_not_lr"] += 1
        elif k == K_PCWRITE:
            if a in an.adr_lr_calls:
                pcw["adr_lr+mov/ldr_pc (old-style indirect call)"] += 1
            elif (w & 0x0C500000) == 0x04100000:
                pcw["ldr_pc_[reg] (indirect jump/tail)"] += 1
            elif (w & 0x0FE00000) == 0x01A00000:
                pcw["mov_pc_reg (indirect jump)"] += 1
            elif (w & 0x0FE00000) == 0x00800000:
                pcw["add_pc_reg (computed jump)"] += 1
            else:
                pcw["other_pc_write"] += 1
        elif k == K_VENEER:
            pcw["ldr_pc_literal (veneer)"] += 1

    # confidence tiers of starts
    def tier(src):
        ss = set(src.split("+"))
        if ss & {"entry", "bl", "init_array"}:
            return "high"
        if ss & {"tail", "dataptr", "litptr", "prologue"}:
            return "medium"
        return "low"    # gap / tail_range / thumb_prologue only
    tiers = Counter(tier(fn["sources"]) for fn in funcs)
    tier_bytes = Counter()
    for fn in funcs:
        tier_bytes[tier(fn["sources"])] += fn["size"]
    for fn in funcs:
        fn["tier"] = tier(fn["sources"])

    odd_ptr_in_arm = 0
    odd_ptr = 0
    for base, off, size in ((RODATA_VA, RODATA_OFF, RODATA_SIZE), (DATA_VA, DATA_OFF, DATA_SIZE)):
        for i in range(0, size - 3, 4):
            v = struct.unpack_from("<I", img.d, off + i)[0]
            if TEXT_VA <= v < TEXT_END and v & 1:
                odd_ptr += 1
                if an.code.get(v & ~3) == "A":
                    odd_ptr_in_arm += 1
    blx_imm_linear_valid = 0
    for i in range(0, TEXT_SIZE, 4):
        w = struct.unpack_from("<I", img.d, i)[0]
        if (w & 0xFE000000) == 0xFA000000:
            k, c, t, _ = decode_arm(w, TEXT_VA + i)
            if img_in(t):
                blx_imm_linear_valid += 1
    pool_sizes = sorted(e - s0 for s0, e, _ in pools)
    owners_with_pool = len(set(an.lits_owner.values()))

    # crt0 hand check: bss clear bounds
    bss_lo, bss_hi = img.u32(0x100040), img.u32(0x100044)
    crt_check = (bss_lo == DATA_VA + DATA_SIZE and bss_hi == DATA_VA + DATA_SIZE + BSS_SIZE)

    # crt0 listing
    crt = []
    for i in range(0, 0x48, 4):
        a = TEXT_VA + i
        w = img.u32(a)
        crt.append("  %08X: %08X  %s" % (a, w, fmt_arm(w, a)))
    crt_targets = []
    for i in range(0, 0x24, 4):
        a = TEXT_VA + i
        k, c, t, _ = decode_arm(img.u32(a), a)
        if k in (K_B, K_BL):
            fn = next((f for f in funcs if f["start"] == t), None)
            crt_targets.append("  %08X %s -> 0x%08X  size=%s callers=%s" % (
                a, KNAMES[k], t, fn["size"] if fn else "?", fn["callers"] if fn else "?"))

    with open(os.path.join(OUT_DIR, "functions.csv"), "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["start", "end_guess", "mode", "callers", "size",
                     "tail_callers", "ninsn", "jump_tables", "sources", "confidence",
                     "overlap_next"])
        for fn in funcs:
            wr.writerow(["0x%08X" % fn["start"], "0x%08X" % fn["end_guess"],
                         "ARM" if fn["mode"] == "A" else "THUMB", fn["callers"],
                         fn["size"], fn["tails"], fn["ninsn"], fn["jts"],
                         fn["sources"], fn["tier"], int(fn["overlap"])])

    summary = {
        "selftest_failures": fails,
        "crt0_bss_clear_bounds_match_layout": crt_check,
        "init_array": an.init_array,
        "confidence_tiers": dict(tiers),
        "confidence_tier_bytes": dict(tier_bytes),
        "gap_classes_count": dict(gap_cls),
        "gap_classes_bytes": dict(gap_cls_bytes),
        "indirect_control_flow": dict(pcw),
        "adr_targets_total": len(an.adr_targets),
        "adr_targets_inline_data": len(an.adr_data),
        "adr_lr_return_labels": len(an.adr_code),
        "adr_lr_indirect_calls": len(an.adr_lr_calls),
        "pcrel_offset_literals": len(an.pcrel_lits),
        "jump_table_entry_words": len(an.jt_lits),
        "weak_starts_pruned": an.pruned,
        "noreturn_callees_by_literal_after_bl": len(an.noreturn_calls),
        "noreturn_call_sites": sum(an.noreturn_calls.values()),
        "tail_range_starts_added": an.tail_range_added,
        "odd_text_pointers_in_data": odd_ptr,
        "odd_text_pointers_landing_in_arm_code": odd_ptr_in_arm,
        "blx_imm_words_with_target_in_text": blx_imm_linear_valid,
        "functions_owning_literals": owners_with_pool,
        "pool_bytes_median": pool_sizes[len(pool_sizes) // 2] if pool_sizes else 0,
        "pool_bytes_max": pool_sizes[-1] if pool_sizes else 0,
        "functions": nf,
        "functions_arm": mode_counts.get("A", 0),
        "functions_thumb": mode_counts.get("T", 0),
        "reached_code_bytes": code_bytes,
        "reached_arm_insns": arm_insn,
        "reached_thumb_bytes": th_bytes,
        "text_bytes": TEXT_SIZE,
        "literal_words_or_items": len(lit_addrs),
        "literal_pools": len(pools),
        "literal_bytes": lit_bytes,
        "unexplained_gap_bytes": gap_bytes,
        "unexplained_gap_bytes_all_zero": zero_gap,
        "gap_regions": len(gaps),
        "jump_tables": len(an.jts),
        "jump_table_kinds": dict(jt_kinds),
        "jump_table_entries_total": jt_entries,
        "jump_tables_entry_count_guessed": jt_guessed,
        "size_min": sizes[0] if sizes else 0,
        "size_median": q(0.5),
        "size_p90": q(0.9),
        "size_p99": q(0.99),
        "size_max": sizes[-1] if sizes else 0,
        "size_mean": round(sum(sizes) / nf, 1) if nf else 0,
        "size_hist": dict(hist),
        "sources_any": dict(src_counts),
        "sources_exact_top": dict(only_src.most_common(12)),
        "funcs_with_zero_direct_callers": no_callers,
        "funcs_overlapping_next_start": overlaps,
        "rejected_confident_starts": len(an.invalid_hits),
        "discovery_rounds_new_starts": an.rounds,
        "linear_scan": lin,
        "reached_kind_counts": dict(sorted(kstat.items())),
        "veneer_like_ldr_pc_lit": kstat.get("A_veneer", 0),
    }
    with open(os.path.join(OUT_DIR, "funcmap_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)

    L = []
    L.append("funcmap.py summary  (%s .text 0x%X-0x%X)" % (GAME_LABEL, TEXT_VA, TEXT_END))
    L.append("")
    L.append("Decoder self-test: %d hand-checked encodings, %d failures" % (len(stlines), fails))
    L.append("")
    L.append("crt0 / entry (first 0x48 bytes):")
    L += crt
    L.append("entry BL/B targets:")
    L += crt_targets
    L.append("")
    L.append("Functions: %d  (ARM %d, Thumb %d)" % (nf, mode_counts.get("A", 0), mode_counts.get("T", 0)))
    L.append("Reached code: %d bytes = %s of .text (ARM insns %d, Thumb bytes %d)" % (
        code_bytes, pct(code_bytes, TEXT_SIZE), arm_insn, th_bytes))
    L.append("Literal pools: %d runs, %d items, %d bytes (%s of .text)" % (
        len(pools), len(lit_addrs), lit_bytes, pct(lit_bytes, TEXT_SIZE)))
    L.append("Unexplained gaps: %d regions, %d bytes (%s), of which all-zero %d bytes" % (
        len(gaps), gap_bytes, pct(gap_bytes, TEXT_SIZE), zero_gap))
    L.append("Jump tables: %d (%s), %d entries total, %d with guessed entry count" % (
        len(an.jts), dict(jt_kinds), jt_entries, jt_guessed))
    L.append("Size (bytes): min %d  median %d  mean %.1f  p90 %d  p99 %d  max %d" % (
        summary["size_min"], summary["size_median"], summary["size_mean"],
        summary["size_p90"], summary["size_p99"], summary["size_max"]))
    L.append("Size histogram: " + ", ".join("%s:%d" % h for h in hist))
    L.append("Start sources (any): %s" % dict(src_counts))
    L.append("Functions with no direct BL/BLX or tail-B callers: %d" % no_callers)
    L.append("Functions whose descent extent runs past next start (clipped): %d" % overlaps)
    L.append("Discovery rounds (new starts per round): %s" % an.rounds)
    L.append("crt0 bss-clear bounds (lits @0x100040/44 = 0x%X..0x%X) match layout data_end..bss_end: %s" % (
        bss_lo, bss_hi, crt_check))
    if an.init_array:
        L.append("C++ init_array (self-relative offsets): 0x%X-0x%X, %d entries, walked by 0x%X" % (
            an.init_array["begin"], an.init_array["end"], an.init_array["entries"], an.init_array["runner"]))
    L.append("Confidence tiers (count): %s ; (bytes): %s" % (dict(tiers), dict(tier_bytes)))
    L.append("  high = BL/BLX target, entry or init_array; medium = tail-B target, .data/.rodata")
    L.append("  pointer, literal pointer or STMFD-lr prologue; low = gap heuristic / tail_range only")
    L.append("Gap classes (count): %s" % dict(gap_cls))
    L.append("Gap classes (bytes): %s" % dict(gap_cls_bytes))
    L.append("ADR targets: %d total, %d inline data (cond!=AL word), %d 'adr lr' return labels; "
             "%d old-style 'adr lr / mov pc' indirect calls" % (
                 len(an.adr_targets), len(an.adr_data), len(an.adr_code), len(an.adr_lr_calls)))
    L.append("Literal words used as PC-relative offsets (ADD rX,pc,rX): %d ; jump-table entry words: %d" % (
        len(an.pcrel_lits), len(an.jt_lits)))
    L.append("Weak starts pruned (fall-through into them): %d ; tail_range starts added: %d" % (
        an.pruned, an.tail_range_added))
    L.append("No-return callees (BL directly followed by a literal pool): %d callees, %d sites; top: %s" % (
        len(an.noreturn_calls), sum(an.noreturn_calls.values()),
        ", ".join("0x%X x%d" % kv for kv in an.noreturn_calls.most_common(5))))
    L.append("Odd (Thumb-looking) .text pointers in .rodata/.data: %d, of which %d land inside ARM code" % (
        odd_ptr, odd_ptr_in_arm))
    L.append("BLX-immediate words in .text whose target is inside .text: %d" % blx_imm_linear_valid)
    L.append("Indirect control flow in reached code: %s" % dict(pcw))
    L.append("Literal pool run size: median %s bytes, max %s; %d functions own >=1 literal" % (
        summary["pool_bytes_median"], summary["pool_bytes_max"], owners_with_pool))
    L.append("")
    L.append("Linear (whole-.text, unfiltered) pattern counts:")
    for k in sorted(lin):
        L.append("  %-28s %d" % (k, lin[k]))
    L.append("")
    L.append("Instruction classes in reached code:")
    for k, v in sorted(kstat.items(), key=lambda x: -x[1]):
        L.append("  %-24s %d" % (k, v))
    L.append("")
    L.append("Largest functions:")
    for fn in largest:
        L.append("  0x%08X-0x%08X %s size %7d callers %4d insns %6d jt %d src %s" % (
            fn["start"], fn["end_guess"], fn["mode"], fn["size"], fn["callers"],
            fn["ninsn"], fn["jts"], fn["sources"]))
    L.append("")
    L.append("Most-called functions:")
    for fn in most_called:
        L.append("  0x%08X %s size %6d callers %5d" % (fn["start"], fn["mode"], fn["size"], fn["callers"]))
    L.append("")
    L.append("Thumb functions (first 30 of %d):" % len(thumb_funcs))
    for fn in thumb_funcs[:30]:
        L.append("  0x%08X size %d callers %d src %s" % (fn["start"], fn["size"], fn["callers"], fn["sources"]))
    L.append("")
    L.append("Largest unexplained gaps:")
    for s, e in sorted(gaps, key=lambda g: g[0] - g[1])[:15]:
        L.append("  0x%08X-0x%08X %d bytes" % (s, e, e - s))
    L.append("")
    L.append("Confident starts rejected by descent (first 20 of %d):" % len(an.invalid_hits))
    for a, m, t, b in an.invalid_hits[:20]:
        L.append("  0x%08X %s via %s: %s" % (a, m, t, b))
    with open(os.path.join(OUT_DIR, "funcmap_summary.txt"), "w") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[:60]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
