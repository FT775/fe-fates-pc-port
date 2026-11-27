#!/usr/bin/env python3
"""M2 pointer review: decide which in-range words are really addresses.

Inputs (read-only): extracted/code.bin + layout.json, build/cache/analysis.json,
build/ptr_unresolved.txt (words gen_asm.py kept raw) and an objdump listing of
.text (cached under build/m2_ptrs/).

Output: config/naming/pointer_overrides.csv
    word_addr,value,action,confidence,evidence,source,target
  action  symbolize  word is an absolute address; emit it as a label (+addend)
          raw        generator symbolized it, but it is an integer/text; emit 0x...
          pcrel      word is a PC-relative delta (ADD rX, pc, rY / LDR [pc, rY]):
                     neither raw nor an absolute label; must become
                     (target - (anchor + 8)). target column = "TTTTTTTT@AAAAAAAA"
                     (absolute target @ anchor instruction).
  source  unresolved:<reason> (from ptr_unresolved.txt) | symbolized (generator
          emitted a label) | unlisted (generator kept it raw silently: value out of
          the symbolizable range)
Scratch/diagnostics: build/m2_ptrs/.

Method (all evidence is from the code itself):
  1. Every LDR-literal in decoded code is traced forward (same function, <=24
     instructions, through MOV copies and ADD/SUB #imm) and each use of the loaded
     register is classified: base of a load/store/LDM/STM/VLDR (address), BX/BLX/
     MOV pc (code address), ADD with pc (pc-relative delta), shifted/logical/
     multiplicative/compare/index use (integer).
  2. If an address-literal's base use is a word LDR at a known offset into
     .rodata/.data, the loaded data word is traced the same way (second level), so
     data words get direct usage evidence too.
  3. Words with no decisive usage are judged by table context: same-stride
     neighbours that the generator symbolized to the same kind of target (and, for
     code targets, the target must look like a function entry: after a return, after
     string/padding data, or after the MOV r0,r0 left where a tail branch into the
     next function was removed).
  3b. A code target proven by 1-3 is accepted wherever else it is loaded and only
     stored/passed; other entry-like targets that are only stored/passed: medium.
  4. Opposite error: symbolized words with only integer usage, words inside
     UTF-16 / ASCII / Shift-JIS NUL-terminated text runs, and (medium) words inside
     high-entropy (random-looking) tables. PC-relative deltas are reported as pcrel
     whatever the generator did with them.
Deterministic; Python stdlib only.
"""
from __future__ import annotations
import sys as _sys  # noqa: E402
if "--awakening-pass" not in _sys.argv:  # Fates: names come from the shipped symbol map
    _sys.exit("tools/m2/pointer_review.py is the Awakening RTTI/heuristic naming pass and still holds "
              "Awakening addresses; it would write wrong rows for Fates. Fates names come "
              "from the shipped symbol map: python tools/fates/symbols.py (docs/SYMBOLS.md).")

import bisect
import collections
import csv
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "extracted"
BUILD = ROOT / "build"
SCRATCH = BUILD / "m2_ptrs"
OUT = ROOT / "config" / "naming" / "pointer_overrides.csv"
MAX_STEPS = 24

REGN = {"sb": 9, "sl": 10, "fp": 11, "ip": 12, "sp": 13, "lr": 14, "pc": 15}
for _i in range(16):
    REGN[f"r{_i}"] = _i
REG_RE = re.compile(r"\b(r1[0-5]|r[0-9]|sb|sl|fp|ip|sp|lr|pc)\b")
CONDS = ("eq", "ne", "cs", "cc", "mi", "pl", "vs", "vc", "hi", "ls", "ge", "lt", "gt", "le", "al", "hs", "lo")

MEM1 = ["ldrsb", "ldrsh", "ldrexd", "ldrexb", "ldrexh", "ldrex", "ldrbt", "ldrht", "ldrt", "ldrb", "ldrh",
        "ldrd", "ldr", "strexd", "strexb", "strexh", "strex", "strbt", "strht", "strt", "strb", "strh",
        "strd", "str", "pld"]
MEMM = ["ldm", "stm", "push", "pop"]
VMEM = ["vldr", "vstr", "vldm", "vstm", "vpush", "vpop"]
DP3 = ["and", "eor", "sub", "rsb", "add", "adc", "sbc", "rsc", "orr", "bic"]
CMP = ["tst", "teq", "cmp", "cmn"]
MOV = ["mov", "mvn"]
SHIFT = ["lsl", "lsr", "asr", "ror", "rrx"]
MUL = ["mul", "mla", "mls", "umull", "umlal", "smull", "smlal", "umaal", "smul", "smla", "smlsl", "smlal",
       "smuad", "smusd", "smmul", "smmla", "smmls", "usad8", "usada8"]
EXTEND = ["uxtb16", "uxtab16", "sxtb16", "sxtab16", "uxtab", "uxtah", "sxtab", "sxtah", "uxtb", "uxth", "sxtb",
          "sxth", "clz", "rev16", "revsh", "rev", "ssat16", "usat16", "ssat", "usat", "pkhbt", "pkhtb", "sel",
          "qadd", "qsub", "qdadd", "qdsub", "uqadd", "uqsub", "uhadd", "uhsub", "uadd", "usub", "sadd", "ssub",
          "shadd", "shsub", "qasx", "qsax", "uasx", "usax", "sasx", "ssax"]


def hx(v: int) -> str:
    return f"0x{v:08X}"


# ------------------------------------------------------------------ inputs
class Image:
    def __init__(self):
        self.code = (EXT / "code.bin").read_bytes()
        lay = json.loads((EXT / "layout.json").read_text())
        self.seg = {}
        for k in ("text", "rodata", "data"):
            s = lay[k]
            self.seg[k] = (s["addr"], s["addr"] + s["size"], s["file_offset"])
        d0, d1, _ = self.seg["data"]
        self.seg["bss"] = (d1, d1 + lay["bss_size"], None)
        self.t0, self.t1, _ = self.seg["text"]
        an = json.loads((BUILD / "cache" / "analysis.json").read_text())
        self.funcs = sorted(f for f in an["funcs"] if self.t0 <= f < self.t1)
        if self.funcs[0] != self.t0:
            self.funcs.insert(0, self.t0)
        self.funcset = set(self.funcs)
        self.code_ranges = sorted(tuple(r) for r in an["code_ranges"])
        self.is_code = set()
        for a, b in self.code_ranges:
            self.is_code.update(range(a, b, 4))
        self.pool = set()
        for a, s in an["lits"]:
            for w in range(a & ~3, a + s, 4):
                self.pool.add(w)
        self.jt = set(an["jt_lits"])
        self.range_starts = {a for a, _ in self.code_ranges}

    def word(self, va: int) -> int | None:
        for k in ("text", "rodata", "data"):
            s0, s1, off = self.seg[k]
            if s0 <= va < s1 and va + 4 <= s1:
                return struct.unpack_from("<I", self.code, off + va - s0)[0]
        return None

    def half(self, va: int) -> int | None:
        for k in ("text", "rodata", "data"):
            s0, s1, off = self.seg[k]
            if s0 <= va < s1 - 1:
                return struct.unpack_from("<H", self.code, off + va - s0)[0]
        return None

    def segof(self, v: int) -> str | None:
        if self.t0 <= v <= self.t1:
            return "text"
        for k in ("rodata", "data", "bss"):
            s0, s1, _ = self.seg[k]
            if s0 <= v <= s1:
                return k
        return None

    def in_data(self, v: int) -> bool:
        return self.segof(v) in ("rodata", "data", "bss")

    def gen_decision(self, v: int) -> str:
        """Mirror of gen_asm.ptr_expr (non jump-table): 'sym', 'raw-out' or reject reason."""
        in_text = self.t0 <= v <= self.t1
        if not in_text and not self.in_data(v):
            return "raw-out"
        if in_text and v in self.funcset:
            return "sym"
        if 0x20 <= (v & 0xFFFF) <= 0x7E:
            return "utf16"
        if in_text:
            if (v & 0xFFFFF) == 0:
                return "round"
            if (v & ~3) in self.is_code:
                return "midcode"
        return "sym"

    def func_end(self, a: int) -> int:
        i = bisect.bisect_right(self.funcs, a)
        return self.funcs[i] if i < len(self.funcs) else self.t1


def disassemble(img: Image) -> dict[int, tuple[str, str]]:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    t0, t1, off = img.seg["text"]
    text = img.code[off: off + (t1 - t0)]
    sha = hashlib.sha1(text).hexdigest()
    dis = SCRATCH / "text.dis"
    stamp = SCRATCH / "text.dis.sha1"
    if not (dis.is_file() and stamp.is_file() and stamp.read_text().strip() == sha):
        cfg = json.loads((ROOT / "tools" / "config.local.json").read_text())
        exe = Path(cfg["binutils_dir"]) / ("arm-none-eabi-objdump.exe" if os.name == "nt" else "arm-none-eabi-objdump")
        binp = SCRATCH / "text.bin"
        binp.write_bytes(text)
        with open(dis, "w") as fh:
            subprocess.run([str(exe), "-D", "-b", "binary", "-marm", f"--adjust-vma=0x{t0:X}", str(binp)],
                           stdout=fh, check=True)
        stamp.write_text(sha + "\n")
    ins = {}
    for line in dis.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or not parts[0].strip().endswith(":"):
            continue
        try:
            a = int(parts[0].strip()[:-1], 16)
        except ValueError:
            continue
        mn = parts[2].strip()
        ops = parts[3].strip() if len(parts) > 3 else ""
        ins[a] = (mn, ops)
    return ins


# ------------------------------------------------------------------ decoding helpers
def split_mn(mn: str, table: list[str]) -> str | None:
    """Return base mnemonic if mn = base + optional cond/s/suffix."""
    for b in sorted(table, key=len, reverse=True):
        if mn.startswith(b):
            rest = mn[len(b):]
            rest = rest.split(".")[0]
            for c in CONDS + ("",):
                for s in ("", "s", "ia", "ib", "da", "db", "fd", "fa", "ed", "ea"):
                    if rest in (s + c, c + s):
                        return b
    return None


def cond_of(mn: str) -> bool:
    """True if the instruction is conditional (approximate)."""
    m = mn.split(".")[0]
    return any(m.endswith(c) and len(m) > len(c) + 1 for c in CONDS if c != "al")


def regs(s: str) -> list[int]:
    return [REGN[x] for x in REG_RE.findall(s)]


def parse_mem(ops: str):
    """'rX, [rN, ...]' -> (data_regs, base, index, imm, writeback)."""
    i = ops.find("[")
    if i < 0:
        return None
    j = ops.find("]", i)
    pre, inner, post = ops[:i], ops[i + 1:j], ops[j + 1:]
    inr = regs(inner)
    base = inr[0] if inr else None
    index = inr[1:] if len(inr) > 1 else []
    if not index and post:
        pr = regs(post)
        index = pr
    imm = 0
    m = re.search(r"#(-?)(0x[0-9a-f]+|\d+)", inner)
    if m:
        imm = int(m.group(2), 0) * (-1 if m.group(1) else 1)
    wb = "!" in post or (post.strip().startswith(",") and True)
    return regs(pre), base, index, imm, wb


class Ev:
    __slots__ = ("kind", "at", "detail")

    def __init__(self, kind, at, detail=""):
        self.kind, self.at, self.detail = kind, at, detail


def trace(img: Image, ins, start: int, reg: int, value: int, level: int, out_nested):
    """Follow `reg` (holding `value`) forward from the instruction after `start`.

    Returns list of Ev. out_nested receives (data_word_addr, load_insn, dest_reg) for
    second-level traces."""
    evs = []
    tracked = {reg: 0}        # reg -> offset from value (None = mixed with another reg)
    end = img.func_end(start)
    a = start + 4
    steps = 0
    while a < end and steps < MAX_STEPS and tracked:
        if a not in img.is_code or a not in ins:
            break
        steps += 1
        mn, ops = ins[a]
        cond = cond_of(mn)
        r_all = regs(ops)
        hit = [r for r in r_all if r in tracked]

        b = split_mn(mn, MEM1)
        if b and "[" in ops:
            pm = parse_mem(ops)
            dregs, base, index, imm, wb = pm
            is_load = b.startswith("ldr") or b == "pld"
            if base in tracked:
                off = tracked[base]
                if base == 15:
                    pass
                else:
                    tgt = None if off is None else value + off + imm
                    if index:
                        evs.append(Ev("BASE_IDX", a, b))
                    else:
                        if (not is_load) and tgt is not None and img.segof(tgt) in ("text", "rodata"):
                            evs.append(Ev("STORE_RO", a, b))
                        elif off is None:
                            evs.append(Ev("BASE_MIX", a, b))
                        else:
                            evs.append(Ev("BASE", a, b))
                            if (level == 0 and b == "ldr" and is_load and tgt is not None and tgt % 4 == 0
                                    and img.segof(tgt) in ("rodata", "data") and dregs):
                                out_nested.append((tgt, a, dregs[0]))
            for r in index:
                if r in tracked:
                    if base == 15:
                        evs.append(Ev("PCREL_LDR", a, b))
                    else:
                        evs.append(Ev("REGOFF", a, b))   # [rA, rB]: base or index, ambiguous
            if not is_load:
                for r in dregs:
                    if r in tracked and b != "pld":
                        evs.append(Ev("STORED", a, b))
            else:
                for r in dregs:
                    tracked.pop(r, None)
            if base == 15 and is_load:
                for r in dregs:
                    tracked.pop(r, None)
            if dregs and 15 in dregs and is_load and not cond:
                break
            a += 4
            continue

        b = split_mn(mn, VMEM)
        if b:
            if b in ("vldr", "vstr"):
                pm = parse_mem(ops)
                if pm and pm[1] in tracked:
                    evs.append(Ev("BASE", a, b))
            elif b in ("vldm", "vstm"):
                r = regs(ops.split("{")[0])
                if r and r[0] in tracked:
                    evs.append(Ev("BASE", a, b))
            a += 4
            continue

        b = split_mn(mn, MEMM)
        if b:
            head, _, lst = ops.partition("{")
            lr = regs(lst)
            if b in ("ldm", "stm"):
                hb = regs(head)
                if hb and hb[0] in tracked:
                    evs.append(Ev("BASE", a, b))
            if b in ("ldm", "pop"):
                for r in lr:
                    tracked.pop(r, None)
                if 15 in lr and not cond:
                    break
            else:
                pass  # stm/push of a tracked reg: neutral
            a += 4
            continue

        m0 = mn.split(".")[0]
        if m0 in ("b",) or (m0.startswith("b") and m0[1:] in CONDS and m0 not in ("bl",)):
            if m0 == "b" or m0 == "bal":
                break
            a += 4
            continue
        if m0.startswith("bl") and not m0.startswith("blx") and (m0 == "bl" or m0[2:] in CONDS):
            if any(r in tracked for r in (0, 1, 2, 3)):
                evs.append(Ev("ARG", a, "bl"))
            for r in (0, 1, 2, 3, 12, 14):
                tracked.pop(r, None)
            a += 4
            continue
        if m0.startswith("bx") or m0.startswith("blx"):
            if hit:
                evs.append(Ev("CODEPTR", a, m0[:3]))
            if m0.startswith("blx"):
                if any(r in tracked for r in (0, 1, 2, 3)) and not hit:
                    evs.append(Ev("ARG", a, "blx"))
                for r in (0, 1, 2, 3, 12, 14):
                    tracked.pop(r, None)
                a += 4
                continue
            if not cond:
                break
            a += 4
            continue

        if not r_all:
            a += 4
            continue
        dst = r_all[0]
        srcs_txt = ops.split(",", 1)[1] if "," in ops else ""

        b = split_mn(mn, CMP)
        if b:
            if hit:
                evs.append(Ev("CMP" if b in ("cmp", "cmn") else "INT", a, b))
            a += 4
            continue
        b = split_mn(mn, MOV)
        if b:
            src = regs(srcs_txt)
            shifted = bool(re.search(r"(lsl|lsr|asr|ror|rrx)", srcs_txt))
            if dst == 15 and src and src[0] in tracked:
                evs.append(Ev("CODEPTR", a, "mov pc"))
                break
            if src and any(r in tracked for r in src):
                if b == "mov" and not shifted and len(src) == 1:
                    tracked[dst] = tracked[src[0]]
                    a += 4
                    continue
                evs.append(Ev("INT", a, b + ("-shift" if shifted else "")))
            tracked.pop(dst, None)
            if dst == 15:
                break
            a += 4
            continue
        b = split_mn(mn, SHIFT)
        if b:
            if any(r in tracked for r in r_all[1:]):
                evs.append(Ev("INT", a, b))
            tracked.pop(dst, None)
            a += 4
            continue
        b = split_mn(mn, DP3)
        if b:
            src = regs(srcs_txt)
            shifted = bool(re.search(r"(lsl|lsr|asr|ror|rrx)", srcs_txt))
            m_imm = re.search(r"#(-?)(0x[0-9a-f]+|\d+)", srcs_txt)
            imm = (int(m_imm.group(2), 0) * (-1 if m_imm.group(1) else 1)) if m_imm else None
            tsrc = [r for r in src if r in tracked]
            newoff = "kill"
            if tsrc:
                if b in ("add", "sub") and 15 in src and len(src) == 2 and not shifted and b == "add":
                    evs.append(Ev("PCREL", a, "add pc"))
                elif b in ("add", "sub") and len(src) == 1 and imm is not None:
                    o = tracked[src[0]]
                    newoff = None if o is None else o + (imm if b == "add" else -imm)
                    evs.append(Ev("DERIVE", a, b))
                elif b == "add" and len(src) == 2 and not shifted:
                    evs.append(Ev("ADDREG", a, b))
                    newoff = None
                elif b == "add" and len(src) == 2 and shifted and src[0] in tracked and src[1] not in tracked:
                    evs.append(Ev("ADDREG", a, "add-scaled-index"))   # value + idx<<k: base of a table
                    newoff = None
                elif b == "sub" and len(src) == 2 and not shifted:
                    evs.append(Ev("SUBREG", a, b))
                else:
                    evs.append(Ev("INT", a, b + ("-shift" if shifted else "")))
            if newoff == "kill":
                tracked.pop(dst, None)
            else:
                tracked[dst] = newoff
            a += 4
            continue
        b = split_mn(mn, MUL) or split_mn(mn, EXTEND)
        if b or m0.startswith(("mul", "mla", "umull", "smull", "smla", "smul", "umla", "uxt", "sxt", "uq", "uh",
                               "ua", "us", "sa", "ss", "sh", "qa", "qs", "sel", "clz", "rev", "pkh")):
            nd = 2 if m0.startswith(("umull", "umlal", "smull", "smlal", "umaal", "smlald", "smlsld")) else 1
            if any(r in tracked for r in r_all[nd:]):
                evs.append(Ev("INT", a, m0))
            for r in r_all[:nd]:
                tracked.pop(r, None)
            a += 4
            continue
        if m0.startswith("vmov") or m0.startswith("vcvt") or m0.startswith("vdup"):
            if any(r in tracked for r in r_all):
                # vmov rX, sY defines rX; vmov sY, rX uses it as float/int bits
                first = ops.split(",")[0].strip()
                if first in REGN and REGN[first] in tracked:
                    tracked.pop(REGN[first], None)
                else:
                    evs.append(Ev("INT", a, "vmov"))
            a += 4
            continue
        if m0.startswith("mcr") or m0.startswith("mrc") or m0.startswith("svc") or m0.startswith("vmrs"):
            if m0.startswith("svc"):
                if any(r in tracked for r in (0, 1, 2, 3)):
                    evs.append(Ev("ARG", a, "svc"))
                for r in (0, 1, 2, 3):
                    tracked.pop(r, None)
            elif m0.startswith("mcr") and hit:
                evs.append(Ev("ARG", a, "mcr"))
            else:
                for r in r_all:
                    tracked.pop(r, None)
            a += 4
            continue
        # unknown / undecodable instruction: stop to stay safe
        break
    return evs


# ------------------------------------------------------------------ evidence
POINTER_KINDS = {"BASE", "BASE_IDX", "CODEPTR"}
INT_KINDS = {"INT", "STORE_RO"}


def collect_code_evidence(img: Image, ins):
    """word_addr -> list[Ev]; word_addr -> loaders."""
    ev = collections.defaultdict(list)
    loaders = collections.defaultdict(list)
    nested = []
    ldr_lit = re.compile(r"^(r1[0-5]|r[0-9]|sb|sl|fp|ip|sp|lr), \[pc(?:, #(-?\d+))?\]")
    for a in sorted(img.is_code):
        t = ins.get(a)
        if not t:
            continue
        mn, ops = t
        b = split_mn(mn, MEM1)
        if b and ops.startswith(tuple(REGN)) and "[pc" in ops:
            m = ldr_lit.match(ops)
            if not m:
                continue
            imm = int(m.group(2) or 0)
            w = a + 8 + imm
            if b == "ldr":
                v = img.word(w)
                if v is None:
                    continue
                loaders[w].append(a)
                nst = []
                evs = trace(img, ins, a, REGN[m.group(1)], v, 0, nst)
                ev[w].extend(evs)
                for (dw, la, dr) in nst:
                    nested.append((dw, la, dr))
            elif b == "ldrd":
                loaders[w].append(a)
                ev[w].append(Ev("INT", a, "ldrd-literal"))
                ev[w + 4].append(Ev("INT", a, "ldrd-literal"))
            else:
                loaders[w].append(a)
                ev[w].append(Ev("INT", a, b + "-literal"))
        elif mn.split(".")[0].startswith("vldr") and "[pc" in ops:
            m = re.search(r"\[pc, #(-?\d+)\]", ops)
            if m:
                w = a + 8 + int(m.group(1))
                ev[w].append(Ev("FLOAT", a, "vldr"))
                if ops.startswith("d"):
                    ev[w + 4].append(Ev("FLOAT", a, "vldr"))
    # second level: data words loaded through an address literal
    dev = collections.defaultdict(list)
    for dw, la, dr in sorted(set(nested)):
        v = img.word(dw)
        if v is None:
            continue
        evs = trace(img, ins, la, dr, v, 1, [])
        dev[dw].extend(evs)
    return ev, loaders, dev


def verdict(evs: list[Ev]) -> tuple[str | None, str, str]:
    """(action or None, confidence, evidence tag) from usage events."""
    kinds = collections.Counter(e.kind for e in evs)
    ptr = sum(kinds[k] for k in POINTER_KINDS)
    intn = sum(kinds[k] for k in INT_KINDS) + kinds["FLOAT"]
    pcrel = kinds["PCREL"] + kinds["PCREL_LDR"]
    if pcrel and not ptr and not intn:
        return "pcrel", "high", "ldr_then_add_pc"
    if kinds["CODEPTR"] and not intn and not pcrel:
        return "symbolize", "high", "ldr_then_bx_blx"
    if ptr and not intn and not pcrel:
        if kinds["BASE"]:
            return "symbolize", "high", "ldr_then_base_of_ldst"
        return "symbolize", "medium", "ldr_then_indexed_base"
    if intn and not ptr and not pcrel:
        tags = []
        for k in ("FLOAT", "STORE_RO", "INT"):
            if kinds[k]:
                tags.append({"FLOAT": "vfp_literal", "STORE_RO": "store_into_ro", "INT": "integer_op"}[k])
        neutral = kinds["ARG"] + kinds["STORED"] + kinds["ADDREG"] + kinds["BASE_MIX"] + kinds["REGOFF"]             + kinds["SUBREG"]
        return "raw", ("high" if not neutral else "medium"), "ldr_then_" + tags[0]
    if kinds["CMP"] and not ptr and not pcrel and not kinds["ARG"] and not kinds["STORED"] \
            and not kinds["ADDREG"] and not kinds["BASE_MIX"]:
        return "raw", "medium", "ldr_then_compare_only"
    return None, "", ""


# ------------------------------------------------------------------ data heuristics
TEXTCH = lambda h: (0x20 <= h <= 0x7E) or h in (0x0A, 0x0D, 0x09) or 0x3000 <= h <= 0x30FF or \
    0x4E00 <= h <= 0x9FFF or 0xFF01 <= h <= 0xFF9F or 0x2000 <= h <= 0x206F or 0xA0 <= h <= 0xFF


ASCII = lambda c: 0x20 <= c <= 0x7E or c in (0x09, 0x0A, 0x0D)
SJIS_LEAD = lambda c: 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC
SJIS_TRAIL = lambda c: 0x40 <= c <= 0xFC and c != 0x7F


def text8_end(by: bytes, i: int) -> tuple[int, int]:
    """Scan an 8-bit ASCII/Shift-JIS run from i; return (end, n_double_byte_chars)."""
    n, dbl = len(by), 0
    while i < n:
        c = by[i]
        if ASCII(c) or 0xA1 <= c <= 0xDF:
            i += 1
        elif SJIS_LEAD(c) and i + 1 < n and SJIS_TRAIL(by[i + 1]):
            i += 2
            dbl += 1
        else:
            break
    return i, dbl


def mark_run(inside: set, first: int, last: int) -> None:
    """Add every aligned word lying entirely inside [first, last)."""
    w = (first + 3) & ~3
    while w + 4 <= last:
        inside.add(w)
        w += 4


def text_runs(img: Image) -> tuple[set[int], set[int]]:
    """Aligned words entirely inside a NUL-terminated text run.

    UTF-16: >= 4 ASCII code units then a 0x0000 unit.  8-bit: >= 6 printable ASCII bytes,
    starting after a NUL byte (or segment start), then a NUL byte; the 6-byte minimum and
    the NUL-before rule keep a {float, pointer} pair from looking like a string.
    Words in these runs are text, never addresses."""
    u16, a8, sj = set(), set(), set()
    for k in ("rodata", "data", "text"):
        s0, s1, off = img.seg[k]
        n = (s1 - s0) // 2
        hw = struct.unpack_from(f"<{n}H", img.code, off)
        i = 0
        while i < n:
            if ASCII(hw[i]):
                j = i
                while j < n and ASCII(hw[j]):
                    j += 1
                if j - i >= 4 and j < n and hw[j] == 0:
                    mark_run(u16, s0 + 2 * i, s0 + 2 * (j + 1))
                i = j + 1
            else:
                i += 1
        by = img.code[off: off + (s1 - s0)]
        i, n = 0, len(by)
        while i < n:
            if (ASCII(by[i]) or SJIS_LEAD(by[i])) and (i == 0 or by[i - 1] == 0):
                j, dbl = text8_end(by, i)
                if j - i >= 6 and j < n and by[j] == 0 and (dbl == 0 or dbl >= 2):
                    mark_run(sj if dbl else a8, s0 + i, s0 + j + 1)
                i = max(j, i + 1)
            else:
                i += 1
    return u16, a8, sj


def entropy_window(img: Image, a: int, n: int = 8) -> bool:
    """True if the words around a look like random bits (hash/crc/crypto tables, packed data)."""
    vals = []
    for d in range(-n, n + 1):
        if d == 0:
            continue
        v = img.word(a + 4 * d)
        if v is None:
            return False
        vals.append(v)
    hi = [v >> 24 for v in vals]
    small = sum(1 for h in hi if h in (0x00, 0xFF))
    distinct = len(set(hi))
    return small <= 1 and distinct >= 12


def classify_word(img: Image, v: int) -> str:
    d = img.gen_decision(v)
    if d == "sym":
        if img.t0 <= v <= img.t1:
            return "F" if v in img.funcset else "T"
        return "D"
    if d == "raw-out":
        return "N" if v else "0"
    return "R"


def is_return(mn: str, ops: str) -> bool:
    m0 = mn.split(".")[0]
    return m0 in ("b", "bx") or (m0 == "pop" and "pc" in ops) or (m0.startswith("ldm") and "pc" in ops)         or (m0 == "mov" and ops.startswith("pc"))


def looks_like_entry(img: Image, ins, t: int) -> str | None:
    """Why t looks like a function entry, or None.

    'after_return': previous instruction is a return / unconditional branch / not code.
    'after_tail_nop': previous word is MOV r0,r0 closing a function that falls through
    into t (POP {..,lr} without pc, or pool/non-code, within 3 instructions before it);
    armlink leaves this shape where a tail branch to the next function was removed."""
    if t % 4 or t not in img.is_code:
        return None
    p = t - 4
    if p not in img.is_code or t in img.range_starts:
        return "after_return"
    mn, ops = ins.get(p, ("", ""))
    m0 = mn.split(".")[0]
    if is_return(mn, ops):
        return "after_return"
    if img.word(p) < 0x10000:
        # 'andeq/muleq r0, ...' never comes out of the compiler: this is string/padding data
        # that the function finder decoded as code
        return "after_data"
    if img.word(p) == 0xE1A00000:
        for q in (p - 4, p - 8, p - 12):
            if q not in img.is_code or q in img.funcset or img.word(q) < 0x10000:
                return "after_tail_nop"
            qm, qo = ins.get(q, ("", ""))
            if is_return(qm, qo):
                return "after_return"
            if qm == "pop" and "lr" in qo and "pc" not in qo:
                return "after_tail_nop"
            if qm.startswith("ldm") and qo.startswith("sp!") and "lr" in qo and "pc" not in qo:
                return "after_tail_nop"
            if qm.split(".")[0] in ("b", "bx", "bl", "blx") or "pc" in qo:
                return None
    return None


def table_context(img: Image, cls: dict, a: int, v: int):
    """Same-stride neighbours symbolized to the same kind of target -> (n_match, stride)."""
    want = {"text": ("F", "T"), "rodata": ("D",), "data": ("D",), "bss": ("D",)}[img.segof(v)]
    best = (0, 0)
    for s in (4, 8, 12, 16, 20, 24, 28, 32):
        left = right = 0
        k = 1
        while k <= 4 and cls.get(a - k * s) in want:
            left += 1
            k += 1
        k = 1
        while k <= 4 and cls.get(a + k * s) in want:
            right += 1
            k += 1
        n = left + right
        if left and right:
            n += 2      # both sides: strongly table-like
        if n > best[0]:
            best = (n, s)
    return best


# ------------------------------------------------------------------ main
def main():
    img = Image()
    ins = disassemble(img)
    unresolved = {}
    for line in (BUILD / "ptr_unresolved.txt").read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        wa, val, why = line.split()
        unresolved[int(wa, 16)] = (int(val, 16), why)

    ev, loaders, dev = collect_code_evidence(img, ins)
    u16, a8, sj = text_runs(img)
    txt = u16 | a8 | sj

    # classes of every data word (and text pool words) as the generator would emit them
    cls = {}
    for k in ("rodata", "data"):
        s0, s1, _ = img.seg[k]
        for a in range(s0, s1, 4):
            cls[a] = classify_word(img, img.word(a))
    for a in img.pool:
        w = img.word(a)
        if w is not None:
            cls[a] = classify_word(img, w)

    rows = {}
    diag = []

    def put(a, v, action, conf, evid, source, target=""):
        rows[a] = (a, v, action, conf, evid, source, target)

    def pcrel_target(a, v, evs):
        anch = sorted({e.at for e in evs if e.kind in ("PCREL", "PCREL_LDR")})
        if len(anch) != 1:
            return None
        t = (anch[0] + 8 + v) & 0xFFFFFFFF
        return f"{t:08X}@{anch[0]:08X}" if img.segof(t) else None

    # ---- 1. unresolved words
    per_reason = collections.Counter()
    decided = collections.Counter()
    for a in sorted(unresolved):
        v, why = unresolved[a]
        per_reason[why] += 1
        in_text_word = img.t0 <= a < img.t1
        evs = ev.get(a, []) if in_text_word else dev.get(a, [])
        act, conf, tag = verdict(evs) if evs else (None, "", "")
        seg_v = img.segof(v)
        if act == "pcrel":
            t = pcrel_target(a, v, evs)
            if t:
                put(a, v, "pcrel", "high", tag, f"unresolved:{why}", t)
                decided[(why, "pcrel")] += 1
            continue
        if act == "symbolize":
            ok = True
            if seg_v == "text" and v % 4:
                ok = False            # pure ARM: code addresses are word aligned
            if any(e.kind == "CODEPTR" for e in evs) and not (seg_v == "text" and v in img.is_code):
                ok = False
            if ok and a in txt:
                ok = False
            if ok:
                if seg_v == "text" and v in img.is_code and not any(e.kind == "CODEPTR" for e in evs):
                    # base of a data access pointing into instructions: suspicious
                    conf = "low"
                    tag += "_into_code"
                if conf != "low":
                    put(a, v, "symbolize", conf, tag + ("" if in_text_word else "_l2"), f"unresolved:{why}")
                    decided[(why, "symbolize")] += 1
                diag.append(f"{a:08X} {v:08X} {why} {act} {conf} {tag} " +
                            " ".join(f"{e.kind}@{e.at:08X}" for e in evs))
            continue
        if act == "raw":
            decided[(why, "raw-confirmed")] += 1
            continue
        # no decisive usage: table context for data/pool words
        if a in txt:
            decided[(why, "raw-text-run")] += 1
            continue
        if seg_v == "text" and v % 4:
            decided[(why, "raw-unaligned-code")] += 1
            continue
        if in_text_word and a not in img.pool:
            continue
        n, stride = table_context(img, cls, a, v)
        if n >= 4:
            if seg_v == "text":
                entry = looks_like_entry(img, ins, v)
                if not entry:
                    diag.append(f"{a:08X} {v:08X} {why} table{stride} n={n} target-not-entry")
                    decided[(why, "undecided-table-midfunc")] += 1
                    continue
                c = "high" if n >= 6 else "medium"
                put(a, v, "symbolize", c, f"fptr_table_s{stride}_{entry}", f"unresolved:{why}")
            else:
                c = "high" if n >= 6 else "medium"
                put(a, v, "symbolize", c, f"dptr_table_s{stride}", f"unresolved:{why}")
            decided[(why, "symbolize")] += 1
        else:
            decided[(why, "default-raw")] += 1

    # ---- 1b. code addresses already proven above, reused elsewhere; or entry-like
    #      targets whose only use is being stored / passed (callback registration)
    proven = {r[1] for r in rows.values() if r[2] == "symbolize" and img.segof(r[1]) == "text"}
    for a in sorted(unresolved):
        if a in rows or a in txt:
            continue
        v, why = unresolved[a]
        if img.segof(v) != "text" or v % 4 or v not in img.is_code:
            continue
        in_text_word = img.t0 <= a < img.t1
        if in_text_word and a not in img.pool:
            continue
        evs = ev.get(a, []) if in_text_word else dev.get(a, [])
        kinds = {e.kind for e in evs}
        if kinds & (INT_KINDS | {"FLOAT", "CMP", "PCREL", "PCREL_LDR", "SUBREG"}):
            continue
        if v in proven:
            put(a, v, "symbolize", "high", "same_target_as_proven_codeptr", f"unresolved:{why}")
            decided[(why, "symbolize")] += 1
            decided[(why, "default-raw")] -= 1
            continue
        entry = looks_like_entry(img, ins, v)
        if entry and kinds and kinds <= {"STORED", "ARG"}:
            put(a, v, "symbolize", "medium", f"ldr_then_stored_or_arg_{entry}", f"unresolved:{why}")
            decided[(why, "symbolize")] += 1
            decided[(why, "default-raw")] -= 1

    # ---- 2. opposite error: words the generator symbolized
    opp = collections.Counter()
    for a in sorted(set(ev) | set(dev) | set(cls)):
        if a in unresolved:
            continue
        v = img.word(a)
        if v is None:
            continue
        in_text_word = img.t0 <= a < img.t1
        if in_text_word and a not in img.pool:
            continue
        if in_text_word and a in img.jt:
            continue
        d = img.gen_decision(v)
        evs = ev.get(a, []) if in_text_word else dev.get(a, [])
        act, conf, tag = verdict(evs) if evs else (None, "", "")
        if d == "sym":
            if act == "pcrel":
                t = pcrel_target(a, v, evs)
                if t:
                    put(a, v, "pcrel", "high", tag, "symbolized", t)
                    opp["symbolized->pcrel"] += 1
                continue
            if act == "raw" and conf == "high":
                put(a, v, "raw", conf, tag + ("" if in_text_word else "_l2"), "symbolized")
                opp["symbolized->raw(usage)"] += 1
                continue
            if act is not None:
                continue
            if not in_text_word and a in u16:
                put(a, v, "raw", "high", "inside_utf16_text_run", "symbolized")
                opp["symbolized->raw(utf16)"] += 1
                continue
            if not in_text_word and a in a8:
                put(a, v, "raw", "high", "inside_ascii_text_run", "symbolized")
                opp["symbolized->raw(ascii)"] += 1
                continue
            if not in_text_word and a in sj:
                put(a, v, "raw", "high", "inside_sjis_text_run", "symbolized")
                opp["symbolized->raw(sjis)"] += 1
                continue
            if not in_text_word and entropy_window(img, a):
                put(a, v, "raw", "medium", "inside_high_entropy_table", "symbolized")
                opp["symbolized->raw(entropy)"] += 1
                continue
        elif d == "raw-out" and act == "pcrel":
            t = pcrel_target(a, v, evs)
            if t:
                put(a, v, "pcrel", "high", tag, "unlisted", t)
                opp["unlisted->pcrel"] += 1

    # ---- write
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["word_addr", "value", "action", "confidence", "evidence", "source", "target"])
        for a in sorted(rows):
            r = rows[a]
            w.writerow([hx(r[0]), hx(r[1]), r[2], r[3], r[4], r[5], r[6]])
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "diag.txt").write_text("\n".join(diag) + "\n")
    summ = {
        "unresolved_per_reason": dict(sorted(per_reason.items())),
        "unresolved_decisions": {f"{k[0]}:{k[1]}": n for k, n in sorted(decided.items())},
        "opposite": dict(sorted(opp.items())),
        "rows_by_action": {f"{k[0]}:{k[1]}": n for k, n in
                           sorted(collections.Counter((r[2], r[3]) for r in rows.values()).items())},
        "rows": len(rows),
    }
    (SCRATCH / "summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
