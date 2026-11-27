#!/usr/bin/env python3
"""M2 function-boundary review (stdlib only, deterministic).

Reconciles the canonical function starts (build/cache/analysis.json "funcs",
from tools/analysis/funcmap.py) with the second finder
(extracted/analysis/split_candidates.json "function_starts", from splits.py)
and with the PC-relative references that cross starts
(build/section_merges.txt).  Every canonical start that is suspicious, every
start only one finder has, and every merge is decided from evidence decoded
straight out of extracted/text.bin.

Evidence collected per address
  refs    BL callers, .rodata/.data words equal to the address ("dptr"),
          vtable slots (split_candidates vtables), literal-pool values
          ("litptr"), init_array, crt0 entry.
  ext_br  B/Bcc into the address from code owned by a different
          strongly-referenced function (a real tail call).
  in_br   B/Bcc into the address from the preceding region (the region that
          starts at the last kept start).
  prev    what the word before the address is: fall-through code, a
          terminator (ret, B, LDM ..pc, BX), a BL to a no-return function,
          a literal-pool word, or padding/unreached.
  backbr  the address's own code branches into the interior of the
          preceding region (functions never jump into another function).
  pool    a PC-relative load/ADR crosses the address (D-005 merges): the
          preceding region uses a literal at/after it, or its own code uses a
          literal inside the preceding region.
  frame   its code pops the stack (LDMFD sp!/LDR pc,[sp],#4/ADD sp/VPOP)
          before pushing anything: it runs in the caller's frame.

Decision: see the "Rules" section of docs/analysis/M2_boundaries.md (it is
generated from write_report below).  In short, certain starts (BL / pointer /
vtable / init_array / tail call from another function / armlink branch-NOP
tail call) are kept; any other start that the previous kept function's own
control flow reaches is removed (high for fall-through, back-branch, loop,
foreign frame, pool+branch, dead filler; medium for a lone forward branch after
a terminator; low when it starts with a prologue).  Additions are code
addresses after an armlink branch-NOP (`MOV r0,r0` replacing `B next`) that
the previous function does not otherwise flow into.

Outputs
  config/naming/boundaries.csv         action,addr,confidence,reason
  docs/analysis/M2_boundaries.md       short report
  build/m2_boundaries/decisions.csv    every reviewed address (scratch)
Usage: python tools/m2/boundaries.py
"""
import sys as _sys  # noqa: E402
if "--awakening-pass" not in _sys.argv:  # Fates: names come from the shipped symbol map
    _sys.exit("tools/m2/boundaries.py is the Awakening RTTI/heuristic naming pass and still holds "
              "Awakening addresses; it would write wrong rows for Fates. Fates names come "
              "from the shipped symbol map: python tools/fates/symbols.py (docs/SYMBOLS.md).")
import bisect
import csv
import json
import os
import struct
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "analysis"))
import funcmap  # noqa: E402  (decoder only; importing runs nothing)
from funcmap import (decode_arm, K_B, K_BL, K_BLX_IMM, K_BX, K_RET, K_LDRLIT,  # noqa: E402
                     K_ADR, K_JT_ADD, K_JT_LDR, K_PCWRITE, K_VENEER, K_PUSH,
                     K_POP, K_TRAP, K_INVALID)

TEXT_VA, TEXT_SIZE = 0x00100000, 0x359B88
TEXT_END = TEXT_VA + TEXT_SIZE
RO_VA, RO_OFF, RO_SZ = 0x0045A000, 0x35A000, 0x5BA88
DA_VA, DA_OFF, DA_SZ = 0x004B6000, 0x3B6000, 0x314E8

P_CACHE = os.path.join(ROOT, "build", "cache", "analysis.json")
P_SPLIT = os.path.join(ROOT, "extracted", "analysis", "split_candidates.json")
P_FUNCS = os.path.join(ROOT, "extracted", "analysis", "functions.csv")
P_MERGE = os.path.join(ROOT, "build", "section_merges.txt")
P_CODE = os.path.join(ROOT, "extracted", "code.bin")
OUT_CSV = os.path.join(ROOT, "config", "naming", "boundaries.csv")
OUT_MD = os.path.join(ROOT, "docs", "analysis", "M2_boundaries.md")
SCRATCH = os.path.join(ROOT, "build", "m2_boundaries")

TERM_KINDS = (K_RET, K_B, K_BX, K_PCWRITE, K_VENEER, K_JT_ADD, K_JT_LDR, K_TRAP)
NOPS = (0xE320F000, 0xE1A00000)


def hx(a):
    return "0x%08X" % a


def is_prologue(w):
    return ((w & 0xFFFF4000) == 0xE92D4000 or w == 0xE52DE004
            or (w & 0xFFFF0000) == 0xE92D0000
            or (w & 0x0FBF0E00) == 0x0D2D0A00 or (w & 0xFFFFF000) == 0xE24DD000)


def is_sp_release(w, k, c, b):
    """Instruction that releases a stack frame it did not set up."""
    if k == K_RET and b == 1:            # LDMFD sp!,{..pc} / LDR pc,[sp],#4
        return True
    if k == K_POP:                       # LDMFD sp!,{..} / VPOP
        return True
    if (w & 0x0FFFF000) == 0x028DD000:   # ADD sp,sp,#imm
        return True
    return False


def is_sp_setup(w, k):
    return k == K_PUSH or (w & 0x0FFFF000) == 0x024DD000  # push / SUB sp,sp,#


class Bin:
    def __init__(self):
        with open(P_CODE, "rb") as f:
            self.d = f.read()
        self.text = self.d[:TEXT_SIZE]

    def u32(self, a):
        if TEXT_VA <= a <= TEXT_END - 4:
            return struct.unpack_from("<I", self.text, a - TEXT_VA)[0]
        return None


def load():
    cache = json.load(open(P_CACHE))
    split = json.load(open(P_SPLIT))
    rows = {}
    with open(P_FUNCS, newline="") as f:
        for r in csv.DictReader(f):
            rows[int(r["start"], 16)] = r
    merges = []
    with open(P_MERGE) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            p = line.split()
            # "SRC -> TGT  joins func_A .. func_B"
            merges.append((int(p[0], 16), int(p[2], 16),
                           int(p[4][5:], 16), int(p[6][5:], 16)))
    return cache, split, rows, merges


def main():
    img = Bin()
    cache, split, rows, merges = load()
    F = sorted(cache["funcs"])
    Fset = set(F)
    S = sorted(split["function_starts"])
    Sset = set(S)

    LITW = {}                                   # word addr -> lit start
    for a, s in cache["lits"]:
        for o in range(0, max(s, 1), 4):
            LITW[(a + o) & ~3] = a
        LITW.setdefault(a & ~3, a)
    JT = set(cache["jt_lits"])
    CODE = set()
    for a, b in cache["code_ranges"]:
        for x in range(a, b, 4):
            if x not in LITW:
                CODE.add(x)

    # ------------------------------------------------------------ decode
    dec = {}
    for a in CODE:
        dec[a] = decode_arm(img.u32(a), a)
    bl_from = defaultdict(list)
    br_from = defaultdict(list)          # target -> [(src, cond)]
    pcrel = []                           # (src, target)
    for a in sorted(CODE):
        k, c, t, b = dec[a]
        if k in (K_BL, K_BLX_IMM):
            bl_from[t].append(a)
        elif k == K_B:
            br_from[t].append((a, c))
        elif k in (K_LDRLIT, K_ADR, K_VENEER):
            if TEXT_VA <= t < TEXT_END:
                pcrel.append((a, t))

    # pointer references
    dptr = Counter()
    for va, off, sz in ((RO_VA, RO_OFF, RO_SZ), (DA_VA, DA_OFF, DA_SZ)):
        for i in range(0, sz - 3, 4):
            v = struct.unpack_from("<I", img.d, off + i)[0]
            if TEXT_VA <= v < TEXT_END and not v & 3:
                dptr[v] += 1
    litptr = Counter()
    for a, s in cache["lits"]:
        if s == 4 and a not in JT and not a & 3:
            v = img.u32(a)
            if v is not None and TEXT_VA <= v < TEXT_END and not v & 3:
                litptr[v] += 1
    vt = Counter()
    for v in split["vtables"]:
        for f in v["funcs"]:
            if not f & 1:
                vt[f] += 1
    init = {s for s, r in rows.items() if "init_array" in r["sources"]}

    def hard_refs(a):
        return (len(bl_from.get(a, ())) + dptr[a] + vt[a] + litptr[a]
                + (a in init) + (a == TEXT_VA))

    # --------------------------------------------------- no-return callees
    memo = {}

    def noreturn(t, depth=0):
        if t in memo:
            return memo[t]
        if depth > 6 or t not in CODE:
            return False
        memo[t] = False
        seen = set()
        work = [t]
        returns = False
        while work and not returns and len(seen) < 4000:
            pc = work.pop()
            while pc in CODE and pc not in seen:
                seen.add(pc)
                k, c, x, b = dec[pc]
                if k == K_INVALID:
                    returns = True
                    break
                if k in (K_RET, K_BX, K_PCWRITE, K_VENEER, K_JT_ADD, K_JT_LDR):
                    if c == 14 or k in (K_JT_ADD, K_JT_LDR):
                        returns = True
                        break
                if k == K_B:
                    if x in Fset and x != t:
                        if not noreturn(x, depth + 1):
                            returns = True
                            break
                        if c == 14:
                            break
                    elif c == 14:
                        pc = x
                        continue
                    else:
                        work.append(x)
                if k == K_BL and c == 14 and noreturn(x, depth + 1):
                    break
                pc += 4
            if pc not in CODE and pc not in seen and not returns:
                pass
        memo[t] = not returns
        return memo[t]

    def is_call_pc_write(a):
        """BX rX / MOV pc,rX preceded by MOV lr,pc or ADR lr: an old-style call."""
        if img.u32(a - 4) == 0xE1A0E00F:          # MOV lr, pc
            return True
        for j in range(1, 33):
            w = img.u32(a - 4 * j)
            if w is None:
                return False
            if (w & 0xFFFFF000) == 0xE28FE000 and a - 4 * j + 8 + funcmap.ror_imm(w) == a + 4:
                return True                     # ADR lr, a+4
            kk = dec.get(a - 4 * j, (0, 0))
            if j > 1 and ((kk[0] in (K_B, K_RET, K_BX, K_PCWRITE) and kk[1] == 14)
                          or kk[0] in (K_BL, K_BLX_IMM)):
                return False
        return False

    def is_teardown(w, k, c, b):
        """Epilogue that restores LR without returning (pop {..lr},
        LDR lr,[sp],#4, VPOP, ADD sp,sp,#n): what precedes a tail call."""
        if c != 14:
            return False
        if (w & 0xFFFF4000) == 0xE8BD4000 and not w & 0x8000:
            return True
        return w == 0xE49DE004

    def prev_kind(a):
        p = a - 4
        if p in CODE and img.u32(p) == 0xE1A00000:
            # armlink --branchnop: a tail call "B next" to the section placed
            # right after was replaced by MOV r0,r0.  After a frame teardown
            # it can only have been a tail call, so a starts a function.
            # A NOP that follows a pool / terminator is itself a one-word
            # function (a former "B next" thunk).
            q = p - 4
            if q in LITW or q not in CODE:
                return "bnop_tail"
            k, c, t, b = dec[q]
            if is_teardown(img.u32(q), k, c, b):
                return "bnop_tail"
            if c == 14 and k in TERM_KINDS and not (k in (K_BX, K_PCWRITE) and is_call_pc_write(q)):
                return "bnop_tail"
            if is_prologue(img.u32(a)):
                return "bnop_prologue"
            # "B next" inside a function, or after argument set-up in a
            # thunk: undecided.
            return "bnop_other"
        if p in LITW:
            return "pool"
        if p not in CODE:
            return "gap"
        k, c, t, b = dec[p]
        if c == 14 and k in TERM_KINDS and not (k in (K_BX, K_PCWRITE) and is_call_pc_write(p)):
            return "term"
        if c == 14 and k == K_BL and noreturn(t):
            return "noret"
        return "fall"

    # ------------------------------------------------ strong-owner mapping
    strong = sorted(s for s in F if hard_refs(s))
    strong_set = set(strong)

    def strong_owner(a):
        i = bisect.bisect_right(strong, a) - 1
        return strong[i] if i >= 0 else TEXT_VA

    def ext_branches(a):
        """Branches into a from code owned by a different referenced
        function, plus an unconditional 'B a' sitting right before a (a
        compiler never branches to the next instruction inside one function;
        a tail call across a section boundary does)."""
        own = strong_owner(a - 4)
        n = 0
        for src, c in br_from.get(a, ()):
            if strong_owner(src) != own and strong_owner(src) != strong_owner(a):
                n += 1
            elif src == a - 4 and c == 14:
                n += 1
        return n

    # pc-relative crossings indexed by address
    pcrel.sort()

    def walk_local(s, lim):
        """Instructions reached from s without leaving [s, lim)."""
        local = []
        seen = set()
        work = [s]
        while work:
            pc = work.pop()
            while s <= pc < lim and pc in CODE and pc not in seen:
                seen.add(pc)
                local.append(pc)
                k, c, t, b = dec[pc]
                if k == K_B:
                    if s <= t < lim:
                        if c == 14:
                            pc = t
                            continue
                        work.append(t)
                    elif c == 14:
                        break
                elif k in (K_RET, K_BX, K_PCWRITE, K_VENEER, K_JT_ADD, K_JT_LDR, K_TRAP):
                    if c == 14:
                        if k == K_JT_ADD:
                            work.extend(pc + 8 + 4 * i for i in range(1, 300)
                                        if pc + 8 + 4 * i < lim and dec.get(pc + 8 + 4 * i, (0,))[0] == K_B
                                        and False)
                        if not (k in (K_BX, K_PCWRITE) and is_call_pc_write(pc)):
                            break
                elif k == K_BL and c == 14 and noreturn(t):
                    break
                pc += 4
        return sorted(local)

    def frame_less_pop(s, lim):
        """Linear path from s: stack released before it is set up."""
        pc = s
        n = 0
        while s <= pc < lim and pc in CODE and n < 64:
            w = img.u32(pc)
            k, c, t, b = dec[pc]
            if is_sp_setup(w, k):
                return False
            if is_sp_release(w, k, c, b):
                return True
            if k == K_B and c == 14:
                if s <= t < lim and t > pc:
                    pc = t
                    n += 1
                    continue
                return False
            if k in TERM_KINDS and c == 14:
                return False
            pc += 4
            n += 1
        return False

    # ----------------------------------------------- review canonical starts
    merge_starts = set()
    merge_info = []
    for src, tgt, fa, fb in merges:
        lo, hi = min(src, tgt), max(src, tgt)
        i = bisect.bisect_right(F, lo)
        j = bisect.bisect_right(F, hi)
        crossed = F[i:j]
        merge_info.append((src, tgt, crossed))
        merge_starts.update(crossed)

    # starts that are certainly real: referenced, tail-called from another
    # function, or entered through a branch-NOP'd tail call
    hard = sorted(s for s in F if hard_refs(s) or ext_branches(s) or prev_kind(s) == "bnop_tail")
    hard_set = set(hard)

    def next_hard(a):
        i = bisect.bisect_right(hard, a)
        return hard[i] if i < len(hard) else TEXT_END

    def closure(h, hi):
        """Intra-procedural flow from h, not entering other certain starts
        and not leaving [h, hi)."""
        seen = set()
        work = [h]
        while work:
            pc = work.pop()
            while h <= pc < hi and pc in CODE and pc not in seen:
                if pc != h and pc in hard_set:
                    break
                seen.add(pc)
                if img.u32(pc) == 0xE1A00000 and prev_kind(pc + 4) == "bnop_prologue":
                    break       # former tail call into the next function
                k, c, t, b = dec[pc]
                if k == K_B:
                    if h <= t < hi and t not in hard_set:
                        if c == 14:
                            pc = t
                            continue
                        work.append(t)
                    elif c == 14:
                        break
                elif k == K_JT_ADD:
                    j = pc + 8
                    while j < hi and j in CODE and dec[j][0] == K_B:
                        work.append(j)
                        j += 4
                    work.append(pc + 4)
                    break
                elif k == K_JT_LDR:
                    j = pc + 8
                    while j in JT:
                        work.append(img.u32(j))
                        j += 4
                    work.append(pc + 4)
                    break
                elif k in (K_RET, K_BX, K_PCWRITE, K_VENEER, K_TRAP) and c == 14:
                    if not (k in (K_BX, K_PCWRITE) and is_call_pc_write(pc)):
                        break
                elif k == K_BL and c == 14 and noreturn(t):
                    break
                pc += 4
        return seen

    decisions = {}       # addr -> dict
    moved = {}           # missed real entry -> (false start, old owner)
    kept = [F[0]]
    removed = set()
    C = closure(F[0], next_hard(F[0]))
    nF = len(F)
    for idx in range(1, nF):
        s = F[idx]
        lim = F[idx + 1] if idx + 1 < nF else TEXT_END
        if s in hard_set:
            C = set()
        P = kept[-1]
        refs = hard_refs(s)
        ext = ext_branches(s)
        pk = prev_kind(s)
        in_C = s in C and s not in hard_set
        loop = sum(1 for src, c in br_from.get(s, ()) if src > s and src in C)
        fall_C = pk in ("fall", "bnop_other") and (s - 4) in C
        # branches into s from the preceding region [P, s)
        in_br = [src for src, c in br_from.get(s, ()) if P <= src < s]
        in_br_c = sum(1 for src, c in br_from.get(s, ()) if P <= src < s and c != 14)
        local = walk_local(s, lim)
        # also count branches from the preceding region into s's body
        body = set(local)
        in_body = 0
        for x in local:
            for src, c in br_from.get(x, ()):
                if P <= src < s:
                    in_body += 1
        backbr = 0
        for x in local:
            k, c, t, b = dec[x]
            if k == K_B and P < t < s and t not in Fset:
                backbr += 1
            elif k == K_B and P < t < s and t in removed:
                backbr += 1
        # pc-relative crossings
        pool_fwd = 0
        lo_i = bisect.bisect_left(pcrel, (P, 0))
        for q in range(lo_i, len(pcrel)):
            a, t = pcrel[q]
            if a >= s:
                break
            if t >= s:
                pool_fwd += 1
        pool_back = 0
        for x in local:
            k, c, t, b = dec[x]
            if k in (K_LDRLIT, K_ADR, K_VENEER) and P <= t < s:
                pool_back += 1
        pool = pool_fwd + pool_back
        frame = frame_less_pop(s, lim)
        prol = is_prologue(img.u32(s))
        reached = pk in ("fall", "bnop_other") or in_br or in_body or pool
        verdict, conf, why = "keep", "", ""
        if in_C and not refs and not ext:
            # reached by the previous function's own control flow
            if fall_C:
                verdict, conf, why = "remove", "high", "fallthru"
            elif backbr:
                verdict, conf, why = "remove", "high", "backbr"
            elif loop:
                verdict, conf, why = "remove", "high", "loop"
            elif frame:
                verdict, conf, why = "remove", "high", "frame"
            elif pool and not prol:
                verdict, conf, why = "remove", "high", "pool+br"
            elif prol:
                verdict, conf, why = "remove", "low", "br_only_prologue"
            elif pk == "term":
                verdict, conf, why = "remove", "medium", "br_only"
            else:
                verdict, conf, why = "remove", "low", "br_only_after_pool"
        elif (not refs and not ext and s not in hard_set
              and closure(s, next_hard(s)) & C):
            # its own flow runs into the previous function's body (dead
            # filler or a block whose entry branch was not resolved)
            verdict, conf, why = "remove", "high", "joins_prev"
        elif pk == "bnop_tail" and not refs and not ext:
            why = "branchnop_tail" if (in_br or in_body or pool or backbr) else ""
        elif refs or ext:
            if pk == "fall" or backbr:
                why = "multi_entry"
                if not refs and pk == "fall":
                    # only reached by branches from elsewhere plus fall-through:
                    # an internal label of hand-written code.  For humans.
                    verdict, conf, why = "remove", "low", "multi_entry_branch_only"
            elif pool:
                why = "shared_pool"
        elif reached:
            if pk == "fall":
                verdict, conf, why = "remove", "high", "fallthru"
                # real entry a few instructions earlier (scheduled before
                # the prologue, varargs push, ...) that nobody marked?
                b = s - 4
                n = 0
                while b - 4 > P and b - 4 in CODE and prev_kind(b) == "fall" and n < 8:
                    b -= 4
                    n += 1
                if (b > P and b not in Fset and b in CODE
                        and prev_kind(b) in ("term", "pool", "gap", "noret", "bnop_tail", "bnop_prologue")
                        and not any(P <= src < b for x in range(b, s + 4, 4)
                                    for src, c in br_from.get(x, ()))):
                    moved[b] = (s, P)
                    P = b
                    kept.append(b)
                    why = "fallthru"
            elif backbr:
                verdict, conf, why = "remove", "high", "backbr"
            elif pk == "bnop_other" and frame:
                verdict, conf, why = "remove", "high", "frame"
            elif pk == "bnop_other":
                verdict, conf, why = "remove", "low", "fallthru_after_nop"
            elif frame and (in_br or in_body):
                verdict, conf, why = "remove", "high", "frame"
            elif pool and (in_br or in_body) and not prol:
                verdict, conf, why = "remove", "high", "pool+br"
            elif pool and (in_br or in_body):
                verdict, conf, why = "remove", "low", "pool+br_prologue"
            elif pool:
                # nothing flows in: a separate function in a section that
                # shares one literal pool (library built without
                # per-function sections).  Keep.
                why = "shared_pool_unref"
            elif prol:
                verdict, conf, why = "remove", "low", "br_only_prologue"
            elif pk == "term":
                verdict, conf, why = "remove", "medium", "br_only"
            else:
                verdict, conf, why = "remove", "low", "br_only_after_pool"
        if verdict == "remove" and conf in ("high", "medium"):
            removed.add(s)
        else:
            kept.append(s)      # low removes stay starts for chaining
            C |= closure(s, next_hard(s))
        decisions[s] = dict(addr=s, side="canon", in_split=s in Sset,
                            in_merge=s in merge_starts, src=rows[s]["sources"],
                            fconf=rows[s]["confidence"], refs=refs, ext=ext,
                            prev=pk, in_br=len(in_br), in_br_cond=in_br_c,
                            in_body=in_body, backbr=backbr, pool=pool,
                            frame=int(frame), prologue=int(prol),
                            verdict=verdict, conf=conf, why=why, owner=P,
                            inC=int(in_C), loop=loop)

    for b, (s_, P_) in sorted(moved.items()):
        decisions[b] = dict(addr=b, side="add", in_split=b in Sset, in_merge=False,
                            src="", fconf="", refs=hard_refs(b), ext=0,
                            prev=prev_kind(b), in_br=0, in_br_cond=0, in_body=0,
                            backbr=0, pool=0, frame=0,
                            prologue=int(is_prologue(img.u32(b))), verdict="add",
                            conf="high" if is_prologue(img.u32(s_)) else "medium",
                            why="entry_before_%s" % hx(s_), owner=0)

    # low removes must not make later starts chain onto them as removed
    removed_applied = {a for a, d in decisions.items()
                       if d["verdict"] == "remove" and d["conf"] in ("high", "medium")}

    # ----------------------------------------------------------- additions
    def canon_owner(a):
        i = bisect.bisect_right(F, a) - 1
        while i > 0 and F[i] in removed_applied:
            i -= 1
        return F[i] if i >= 0 else TEXT_VA

    add_cands = set(a for a in S if a not in Fset and a not in moved)
    for a in list(dptr) + list(litptr) + list(vt):
        if a in CODE and a not in Fset and a not in moved:
            add_cands.add(a)
    for p in CODE:
        if img.u32(p) == 0xE1A00000 and p + 4 in CODE and p + 4 not in Fset                 and p + 4 not in moved:
            if prev_kind(p + 4) in ("bnop_tail", "bnop_prologue"):
                add_cands.add(p + 4)
    for a in sorted(add_cands):
        d = dict(addr=a, side="add", in_split=a in Sset, in_merge=False,
                 src="", fconf="", refs=0, ext=0, prev="", in_br=0,
                 in_br_cond=0, in_body=0, backbr=0, pool=0, frame=0,
                 prologue=0, verdict="keep", conf="", why="", owner=0)
        decisions[a] = d
        if a not in CODE or a & 3:
            d["why"] = "not_code"
            continue
        P = canon_owner(a)
        d["owner"] = P
        pk = prev_kind(a)
        bl = len(bl_from.get(a, ()))
        ptr = dptr[a] + litptr[a] + vt[a]
        d["refs"] = bl + ptr
        d["prev"] = pk
        prol = is_prologue(img.u32(a))
        d["prologue"] = int(prol)
        in_br = [src for src, c in br_from.get(a, ()) if P <= src < a]
        d["in_br"] = len(in_br)
        # does the owner's code continue past a (fall-through, or branch to
        # an address >= a from before a)?
        jumps_over = 0
        for src0 in range(P, a, 4):
            if src0 in CODE:
                k, c, t, b = dec[src0]
                if k == K_B and t > a and (bisect.bisect_right(F, t) - 1 == bisect.bisect_right(F, a) - 1):
                    jumps_over += 1
        d["in_body"] = jumps_over
        frame = frame_less_pop(a, TEXT_END)
        d["frame"] = int(frame)
        if pk in ("fall", "bnop_other"):
            d["why"] = "fall_into"
            continue
        if jumps_over:
            d["why"] = "owner_flows_over"
            continue
        if pk == "bnop_tail" and not frame:
            d.update(verdict="add", conf="high", why="branchnop_tail")
            continue
        if in_br:
            d["why"] = "owner_flows_in"
            continue
        if frame:
            d["why"] = "uses_owner_frame"
            continue
        if vt[a] and pk in ("term", "pool", "noret", "gap"):
            d.update(verdict="add", conf="high", why="vtable+boundary")
        elif ptr and prol and pk in ("term", "pool", "noret", "gap"):
            d.update(verdict="add", conf="high", why="ptr+prologue+boundary")
        elif ptr and pk in ("pool", "noret") or (ptr and pk == "term" and dptr[a] + vt[a]):
            d.update(verdict="add", conf="medium", why="ptr+boundary")
        elif prol and pk == "noret":
            d.update(verdict="add", conf="medium", why="prologue_after_noreturn")
        elif pk == "bnop_prologue":
            d.update(verdict="add", conf="medium", why="branchnop_prologue")
        elif ptr or prol:
            d.update(verdict="add", conf="low", why="weak_boundary")
        else:
            d["why"] = "no_evidence"

    # -------------------------------------------------------------- outputs
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    os.makedirs(SCRATCH, exist_ok=True)
    cols = ["addr", "side", "verdict", "conf", "why", "owner", "in_split",
            "in_merge", "src", "fconf", "refs", "ext", "prev", "in_br",
            "in_br_cond", "in_body", "backbr", "pool", "frame", "prologue",
            "inC", "loop"]
    adds_sorted = sorted(a for a, d in decisions.items() if d["verdict"] == "add"
                         and d["conf"] in ("high", "medium"))
    for a, d in decisions.items():
        d.setdefault("inC", "")
        d.setdefault("loop", "")
        if d["verdict"] == "remove":
            i = bisect.bisect_left(adds_sorted, a) - 1
            if i >= 0 and adds_sorted[i] > d["owner"]:
                d["owner"] = adds_sorted[i]
    review = [d for a, d in sorted(decisions.items())
              if d["side"] == "add" or not d["in_split"] or d["in_merge"]
              or d["verdict"] != "keep" or d["why"]]
    with open(os.path.join(SCRATCH, "decisions.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for d in review:
            w.writerow([hx(d[c]) if c in ("addr", "owner") else
                        (int(d[c]) if isinstance(d[c], bool) else d[c]) for c in cols])
    out = []
    for d in review:
        if d["verdict"] in ("add", "remove"):
            tag = d["why"]
            if d["verdict"] == "remove":
                tag += ";into %s" % hx(d["owner"])
            out.append((d["addr"], d["verdict"], d["conf"], tag))
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["action", "addr", "confidence", "reason"])
        for a, act, conf, tag in out:
            w.writerow([act, hx(a), conf, tag])

    stats = summarize(decisions, merge_info, removed_applied, F, S, Fset, Sset)
    write_report(stats)
    print(json.dumps(stats["counts"], indent=1, sort_keys=True))
    return 0


def summarize(decisions, merge_info, removed_applied, F, S, Fset, Sset):
    c = Counter()
    for d in decisions.values():
        key = "%s:%s:%s:%s" % (d["side"], d["verdict"], d["conf"] or "-", d["why"] or "-")
        c[key] += 1
    only_f = [a for a in F if a not in Sset]
    only_s = [a for a in S if a not in Fset]
    only_f_v = Counter("%s/%s" % (decisions[a]["verdict"], decisions[a]["conf"] or "-") for a in only_f)
    only_s_v = Counter("%s/%s" % (decisions[a]["verdict"], decisions[a]["conf"] or "-") for a in only_s)
    # merges: resolved if every crossed start is removed (high/medium) or
    # the crossing is explained as a kept shared pool / multi-entry routine
    m_res = Counter()
    m_examples = defaultdict(list)
    for src, tgt, crossed in merge_info:
        low = [a for a in crossed if decisions[a]["verdict"] == "remove"
               and a not in removed_applied]
        if not crossed:
            k = "no_start_crossed"
        elif all(a in removed_applied for a in crossed):
            k = "false_split_all_removed"
        elif low:
            k = "needs_review_low_rows"
        elif any(a in removed_applied for a in crossed):
            k = "false_split_plus_real_shared_pool"
        else:
            k = "real_shared_pool"
        m_res[k] += 1
        if len(m_examples[k]) < 6:
            m_examples[k].append((src, tgt, crossed))
    ex = defaultdict(list)
    for a, d in sorted(decisions.items()):
        key = (d["side"], d["verdict"], d["conf"], d["why"])
        if len(ex[key]) < 5:
            ex[key].append(a)
    rows_out = Counter()
    for d in decisions.values():
        if d["verdict"] in ("add", "remove"):
            rows_out["%s/%s" % (d["verdict"], d["conf"])] += 1
    new_n = len(F) - len(removed_applied) + rows_out["add/high"] + rows_out["add/medium"]
    return dict(counts=dict(c), only_f=len(only_f), only_s=len(only_s),
                only_f_v=dict(only_f_v), only_s_v=dict(only_s_v),
                merges=len(merge_info), m_res=dict(m_res), m_examples=m_examples,
                ex=ex, rows_out=dict(rows_out), nF=len(F), nS=len(S), new_n=new_n,
                decisions=decisions)


def write_report(st):
    L = []
    A = L.append
    A("# M2 function-boundary review")
    A("")
    A("Generated by `tools/m2/boundaries.py` (re-runnable, stdlib only). Output:")
    A("`config/naming/boundaries.csv` (`action,addr,confidence,reason`). Only `high` and")
    A("`medium` rows are meant to be applied; `low` rows are for human review.")
    A("Per-address evidence for every reviewed start: `build/m2_boundaries/decisions.csv`.")
    A("")
    A("## Inputs")
    A("")
    A("| Input | Starts / rows |")
    A("|---|---|")
    A("| funcmap.py (canonical, `build/cache/analysis.json`) | %d |" % st["nF"])
    A("| splits.py (`split_candidates.json`) | %d |" % st["nS"])
    A("| only funcmap / only splits | %d / %d |" % (st["only_f"], st["only_s"]))
    A("| PC-relative merges (`build/section_merges.txt`) | %d |" % st["merges"])
    A("")
    A("## Rows written")
    A("")
    A("| Action / confidence | Rows |")
    A("|---|---|")
    for k in sorted(st["rows_out"]):
        A("| %s | %d |" % (k, st["rows_out"][k]))
    A("")
    A("Applying high+medium rows takes the function count from %d to %d." % (st["nF"], st["new_n"]))
    A("")
    A("## Rules (evidence tags in the `reason` column)")
    A("")
    A("**Certain starts** are never removed: a BL caller, a .rodata/.data pointer, a vtable")
    A("slot, a literal-pool pointer, an init_array entry, a branch from another referenced")
    A("function, or a branch-NOP tail call (below). Every other start is checked against the")
    A("control flow of the previous kept function (walked from its start, following")
    A("branches, jump tables and ADR-lr/MOV-lr calls, never entering a certain start). A start")
    A("that this flow reaches is removed, i.e. merged into the start named after `into`:")
    A("")
    A("| Tag | Evidence | Confidence |")
    A("|---|---|---|")
    A("| `fallthru` | the word before is reached code that falls through into it | high |")
    A("| `backbr` | its own code branches back into the previous function's interior | high |")
    A("| `loop` | reached by a backward branch from later code of the previous function | high |")
    A("| `frame` | pops a stack frame it never pushed (runs in the caller's frame) | high |")
    A("| `pool+br` | reached by a branch, and a PC-relative load crosses it; no prologue | high |")
    A("| `joins_prev` | not reached, but its own flow runs into the previous function (dead filler) | high |")
    A("| `br_only` | only reached by a forward branch, word before is a terminator, no prologue | medium |")
    A("| `br_only_prologue` | as above but it starts with a prologue: could be a static function reached by a conditional tail call | low |")
    A("| `br_only_after_pool` | only reached by a forward branch, after a literal pool | low |")
    A("| `multi_entry_branch_only` | falls through from the previous function but is also branched to from another function: an internal label of hand-written code | low |")
    A("")
    A("**armlink branch-NOP.** `MOV r0,r0` (0xE1A00000) is what armlink leaves when a branch")
    A("resolves to the next instruction. Directly after an epilogue that restores LR without")
    A("returning (`pop {..,lr}`, `ldr lr,[sp],#4`), or as the only word after a terminator or")
    A("literal pool (a one-word thunk), it was a tail call `B next`, so the next word starts a")
    A("function: `branchnop_tail` (high). Before a prologue with anything else in front:")
    A("`branchnop_prologue` (medium). Elsewhere it is an in-function `B next` and proves nothing.")
    A("An addition is refused when the previous function falls into it by ordinary code,")
    A("branches into it or past it, or when it pops a frame it never pushed.")
    A("")
    A("Kept but reported: `shared_pool` (certain start whose pool is shared with its")
    A("neighbour), `shared_pool_unref` (unreferenced, nothing flows in, but a pool is shared:")
    A("a separate function in a section built without per-function pools), `multi_entry`")
    A("(certain start that the previous function also falls or branches into).")
    A("")
    A("## Disagreements between the two finders")
    A("")
    A("| Set | Verdict | Count |")
    A("|---|---|---|")
    for k in sorted(st["only_f_v"]):
        A("| only funcmap | %s | %d |" % (k, st["only_f_v"][k]))
    for k in sorted(st["only_s_v"]):
        A("| only splits | %s | %d |" % (k, st["only_s_v"][k]))
    A("")
    A("Most funcmap-only starts are real: splits.py is a linear scan that only knows BL")
    A("targets, literal values, RTTI vtable slots and prologues after a terminator, so it")
    A("misses callbacks in non-RTTI data tables, init_array entries, tail-call-only targets")
    A("and leaf functions without a prologue. The funcmap-only starts that are false are")
    A("almost all `tail_range`/`gap`/`prologue` starts inside hand-written or library code")
    A("(loop heads, shrink-wrapped pushes after an early `BXcc lr`, varargs `push {r0-r3}`")
    A("followed by the real push, a load scheduled before the push).")
    A("")
    A("Splits-only starts: the accepted ones are functions entered through a branch-NOP")
    A("tail call that funcmap glued to the thunk before them. The refused ones are literal")
    A("values that point into the middle of a function (PC-relative offsets or constants),")
    A("a few coincidental data words, prologues inside a function that the function itself")
    A("branches to, and addresses outside reached code.")
    A("")
    A("## Merges (D-005)")
    A("")
    A("| Outcome | References |")
    A("|---|---|")
    for k in sorted(st["m_res"]):
        A("| %s | %d |" % (k, st["m_res"][k]))
    A("")
    for k in sorted(st["m_examples"]):
        exs = st["m_examples"][k][:3]
        A("- %s: %s" % (k, "; ".join("%s->%s crosses %s" % (
            "0x%08X" % s, "0x%08X" % t, ",".join("0x%08X" % c for c in cr[:3]) + ("..." if len(cr) > 3 else ""))
            for s, t, cr in exs)))
    A("")
    A("## Examples by category")
    A("")
    A("| Side | Verdict | Conf | Tag | Count | Examples |")
    A("|---|---|---|---|---|---|")
    cnt = Counter((d["side"], d["verdict"], d["conf"], d["why"]) for d in st["decisions"].values())
    for key in sorted(st["ex"], key=lambda k: (k[0], k[1], k[2], k[3])):
        if key[1] == "keep" and not key[3]:
            continue
        A("| %s | %s | %s | %s | %d | %s |" % (key[0], key[1], key[2] or "-", key[3] or "-",
                                             cnt[key], ", ".join("0x%08X" % a for a in st["ex"][key])))
    A("")
    A("## Open questions")
    A("")
    A("- **Genuinely shared pools are common in library code.** Separate functions that share")
    A("  one literal pool (e.g. 0x00126D58/0x00126EA4, 0x00126F3C/0x00126FAC, 0x001261F4/0x001264CC)")
    A("  mean those objects were built without per-function sections. D-005 keeps them in one")
    A("  section, which is right; the split config needs a way to say \"one section, several")
    A("  global functions\".")
    A("- **Branch-NOP is a linker fingerprint.** armlink rewrote `B next` to `MOV r0,r0`, so")
    A("  the original objects had a tail-call branch there. A matching link must either")
    A("  reproduce that (our own linker, D-004) or emit the NOP from asm. funcmap.py should")
    A("  learn the rule so it stops gluing thunks to the function that follows them.")
    A("- `multi_entry_branch_only` (low) rows sit in hand-written blitter-like code around")
    A("  0x00135F90-0x00147xxx where other routines branch into the middle of a loop. Whether")
    A("  these are separate asm entry points or one routine needs a human look.")
    A("- `br_only_prologue` / `br_only_after_pool` (low): a static function reached only by a")
    A("  conditional tail call looks the same as a cold block. Needs a human or the compiler (S1).")
    A("- Data-pointer evidence is taken at face value; a coincidental .data word that equals a")
    A("  code address keeps a false start alive (and blocks its removal).")
    A("- After applying the rows, re-run funcmap and regenerate `section_merges.txt`; anything")
    A("  still crossing a start should be a `shared_pool` case.")
    A("")
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
