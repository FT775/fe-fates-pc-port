#!/usr/bin/env python3
"""M2: library tagging per function.

Writes
  config/naming/library.csv          func_addr,library,confidence,evidence  (one row per
                                     function start in build/cache/analysis.json)
  config/naming/library_summary.csv  library,functions,bytes,high,medium,low
Scratch (debug, not tracked): build/m2_libs/

Libraries: crt0 rvct_clib cxx_runtime ctr_sdk nw4c nex pia molive zlib pead game unknown

Method (all evidence is computed from extracted/code.bin + build/cache/analysis.json,
plus the typeinfo list in extracted/analysis/rtti_classes.csv):
  1. Per-function features from a linear decode of the function's code words:
     BL/B edges, literal-pool (LDR pc) and ADR targets, SVC, TLS reads (mrc p15 c13),
     pre-branch NOPs, MOV pc,lr returns, VFP ops.
  2. Direct anchors (evidence tags str_*, svc, tls_read, rtti_*, clib_style, ...):
     - strings referenced through a literal or ADR, and pointer tables of such strings
       (*_table: e.g. the DMP GL uniform table, service-name lists, z_errmsg);
     - SVC / TLS reads -> ctr_sdk (good, not decisive: they also appear inlined);
     - RTTI: slots of vtables whose typeinfo is a game class, and functions that load
       such a vtable's address point (ctors/dtors) -> game; __cxxabiv1/std -> cxx_runtime;
     - code style: MOV pc,lr returns, no BX LR, no NOP -> rvct_clib, unless the function
       has the packed-pixel motion-compensation signature (video_mc_asm -> molive);
     - crt0 by layout (entry point, .bss clear, exit SVC stub).
     clib_style anchors only inside the C-library block 0x100114-0x129280; MOV pc,lr
     leaves elsewhere are a last-resort fallback (clib_style_weak).
  3. NOP-free runs (>= 40 functions without a NOP: separately built code): the span
     between the first and last video-MC function (no BX LR), grown only through
     functions with codec traits, is the codec (codec_asm_span); other run members take
     the nearest runtime/middleware anchor on their side of the span
     (nopfree_run_nearest) if the layering allows; callers of the codec -> calls_codec.
  3b. Static initializers (the 356 init-array targets) are excluded from the code-style,
     video-MC, NOP-free and contiguity stages; without a direct anchor they take the
     library of the functions sharing their .data/.bss objects, of their callees or of
     the vtables they install (static_init+sinit_*), else game/low.
  4. Call-graph propagation from labels of at least medium confidence, respecting the
     layering game -> middleware -> SDK -> runtime (cg_*). Never overrides an anchor;
     never puts game/SDK/NEX/Pia into NOP-free windows; capped at low where few BLs are
     NOP-led (*_lownop).
  5. Contiguity: unlabeled runs between two functions of one library join it
     (run_between; lexically sorted sections keep a namespace together), limited in
     mixed regions; library boundaries split by call-graph votes (run_edge_cg).
  6. A weak call-graph pass where labels of any confidence vote (cg_weak), the MOV pc,lr
     fallback, weak region priors (STRATEGY.md 2.6) and a last weak run fill; all low.
Run with --features to dump per-function features to build/m2_libs/features.csv only.
Deterministic; Python 3 stdlib only.
"""
import sys as _sys  # noqa: E402
if "--awakening-pass" not in _sys.argv:  # Fates: names come from the shipped symbol map
    _sys.exit("tools/m2/library_tags.py is the Awakening RTTI/heuristic naming pass and still holds "
              "Awakening addresses; it would write wrong rows for Fates. Fates names come "
              "from the shipped symbol map: python tools/fates/symbols.py (docs/SYMBOLS.md).")
import bisect
import collections
import csv
import json
import os
import re
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CODE_BIN = os.path.join(ROOT, "extracted", "code.bin")
ANALYSIS = os.path.join(ROOT, "build", "cache", "analysis.json")
RTTI_CSV = os.path.join(ROOT, "extracted", "analysis", "rtti_classes.csv")
OUT_DIR = os.path.join(ROOT, "config", "naming")
SCRATCH = os.path.join(ROOT, "build", "m2_libs")

TEXT_VA, TEXT_SZ = 0x00100000, 0x359B88
RO_VA, RO_SZ, RO_OFF = 0x0045A000, 0x5BA88, 0x35A000
DATA_VA, DATA_SZ, DATA_OFF = 0x004B6000, 0x314E8, 0x3B6000
TEXT_END = TEXT_VA + TEXT_SZ
INIT_ARRAY = 0x004595F8          # self-relative static-init list up to TEXT_END

LIBS = ["crt0", "rvct_clib", "cxx_runtime", "ctr_sdk", "nw4c", "nex", "pia", "molive",
        "zlib", "pead", "game", "unknown"]
RUNTIME = {"crt0", "rvct_clib", "cxx_runtime"}
# Layering: a library may call only its own level or lower ones (lower number).
LEVEL = {"rvct_clib": 0, "cxx_runtime": 0, "crt0": 0, "zlib": 1, "ctr_sdk": 1,
         "nw4c": 2, "nex": 2, "pia": 2, "molive": 2, "pead": 3, "game": 4}

# ----------------------------------------------------------------------------
# image
# ----------------------------------------------------------------------------
CODE = open(CODE_BIN, "rb").read()
SEGS = [(TEXT_VA, TEXT_SZ, 0), (RO_VA, RO_SZ, RO_OFF), (DATA_VA, DATA_SZ, DATA_OFF)]


def va2off(va):
    for a, s, o in SEGS:
        if a <= va < a + s:
            return o + va - a
    return None


def u32(va):
    o = va2off(va)
    if o is None or o + 4 > len(CODE):
        return None
    return struct.unpack_from("<I", CODE, o)[0]


def in_text(v):
    return TEXT_VA <= v < TEXT_END


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


TW = struct.unpack_from("<%dI" % (TEXT_SZ // 4), CODE, 0)

A = json.load(open(ANALYSIS))
FUNCS = sorted(set(A["funcs"]))
FSET = set(FUNCS)
NF = len(FUNCS)
FEND = FUNCS[1:] + [INIT_ARRAY if FUNCS[-1] < INIT_ARRAY else TEXT_END]
IS_CODE = bytearray(TEXT_SZ // 4)
for a, b in A["code_ranges"]:
    for i in range((a - TEXT_VA) >> 2, (b - TEXT_VA) >> 2):
        IS_CODE[i] = 1
for a, s in A["lits"]:
    for k in range(0, s, 4):
        i = (a + k - TEXT_VA) >> 2
        if 0 <= i < len(IS_CODE):
            IS_CODE[i] = 0
for a in A["jt_lits"]:
    i = (a - TEXT_VA) >> 2
    if 0 <= i < len(IS_CODE):
        IS_CODE[i] = 0


def fidx(a):
    return bisect.bisect_right(FUNCS, a) - 1


# Per-TU static initializers: targets of the self-relative init array (STRATEGY.md 2.4).
# They are ordinary compiled code (data-table setup, ctor calls); the code-style, video-MC
# and NOP-free-run heuristics do not apply to them and contiguity among them is
# meaningless (they are grouped together at the end of .text). SINIT_ORDER keeps the
# init-array (object) order.
SINIT_ORDER = []
for _p in range(INIT_ARRAY, TEXT_END, 4):
    _w = struct.unpack_from("<I", CODE, _p - TEXT_VA)[0]
    _t = (_p + _w) & 0xFFFFFFFF
    if _t in FSET:
        SINIT_ORDER.append(bisect.bisect_left(FUNCS, _t))
SINIT = set(SINIT_ORDER)
BSS_END = 0x004E74E8 + 0x3BD24
# The prebuilt C-library area at the start of .text (before the codec assembly). MOV pc,lr
# leaves elsewhere (static initializers, wide-string helpers) are not reliable C-library
# evidence, so clib_style only anchors inside this block.
CLIB_BLOCK = (0x00100114, 0x00129280)


# ----------------------------------------------------------------------------
# strings
# ----------------------------------------------------------------------------
ASCII_RE = re.compile(rb"[\x20-\x7e\t\n\r]{3,}\x00")


def get_string(va):
    """('a', text) for 8-bit ASCII, ('w', text) for UTF-16LE ASCII, else None."""
    o = va2off(va)
    if o is None:
        return None
    # a target in the middle of a longer printable run is a constant that happens to point
    # into a string, not a string reference
    m = ASCII_RE.match(CODE, o, o + 400)
    if m and not (o > 0 and 0x20 <= CODE[o - 1] < 0x7F):
        s = m.group()[:-1]
        nal = sum(1 for c in s if 65 <= c <= 90 or 97 <= c <= 122)
        if (nal >= 3 and len(s) >= 4) or (len(s) == 3 and nal == 3):
            return ("a", s.decode("latin-1"))
    if not (o & 1) and not (o > 1 and CODE[o - 1] == 0 and 0x20 <= CODE[o - 2] < 0x7F):
        out = []
        p = o
        while p + 1 < len(CODE) and len(out) < 300:
            c = CODE[p] | (CODE[p + 1] << 8)
            if c == 0:
                break
            if not (0x20 <= c < 0x7F or c in (9, 10, 13)):
                out = None
                break
            out.append(chr(c))
            p += 2
        if out and len(out) >= 3 and sum(ch.isalpha() for ch in out) >= 2:
            return ("w", "".join(out))
    return None


# (library, strength, tag, kind, regex). kind: a=ASCII only, w=UTF-16 only, *=both.
# strength 3 = decisive anchor, 2 = good, 1 = weak hint.
NEX_RMC = (r"^(AddDuplicaLocation|DeleteDuplica|RemoveFromCachedDuplicationSet|ElectNewMaster|"
           r"ConfirmElection|DeclinePromotion|SynchronizeTermination|RequestIDRangeFromMaster|"
           r"SignalAsFaulty|RetrieveURLs|LeaveSession|SyncRequest|SyncResponse|AdjustTime|"
           r"SetSyncCount|ResetSyncCount|SetAnswer)$")
ZLIB_MSG = (r"^(need dictionary|stream end|file error|stream error|data error|insufficient memory|"
            r"buffer error|incompatible version)$|incorrect (header|data|length) check|"
            r"invalid (block type|window size|distance|stored block|code lengths|bit length|"
            r"literal|code -- missing)|unknown compression method|unknown header flags set|"
            r"header crc mismatch|too many length or distance symbols|invalid distances set|"
            r"invalid literal/lengths set|oversubscribed|incomplete (dynamic )?(bit|literal)")
SVC_NAME = (r"^(?:[a-z][a-z0-9]{1,5}:[A-Za-z]{1,5}|[a-z]{2,5}::[A-Za-z]{2,5}|APT:[AUS]|srv:|"
            r"srv:pm|\$hio\w*|\$hostio\d)$")
STRING_RULES = [
    # NEX built inside the game project (absolute game paths) -- still NEX code
    ("nex", 3, "str_nex_gamebuild", "*", re.compile(r"Projects\\quartz\\SDK\\CTR_NEX|Sources\\Link\\NEX")),
    ("pia", 3, "str_pia", "*", re.compile(r"\\Pia\\|pia (local|common) heap|^Uds[A-Z]\w*::|\bUds(Node|Message|MigrationManager)")),
    ("nex", 3, "str_nex_assert", "w", re.compile(r"\.(cpp|h)$|ObjDup|Quazal|Net-Z|prudps?:|CallContext|DOCore|"
                                                 r"InstanceTable|InstantiationContext|Transport|StationManager|Scheduler")),
    ("nex", 3, "str_nex_rmc", "a", re.compile(NEX_RMC)),
    ("nex", 2, "str_nex_wide", "w", re.compile(
        r"::|Thread|Station|Session|Job|Protocol|extension|Compression|CheckExpiredCalls|Bandwidth|"
        r"ConnectionEncoding|WellKnown|DupSpace|ConnectionManager|RemainingJobs|Packet|Queue|Build %d|"
        r"^Release$|^Unicode$|POINT2POINT|LOOPBACK|BROADCAST|^localhost$|XLSPID|RVCID|probeinit|NodeId|"
        r"TimedSignal|^Match$|Authentication info|^Send$|System Components|^Core$|processing|UserDOs|"
        r"empty location set|^address$|^port$|NEX_Quartz|Version 20\d\d|^%ls%ls|^stream$|^type$|"
        r"Unregister|JobProcessing|CheckPeriodicMatch|PreventRegularBlockCall|GetState|IsConnecting|"
        r"IsDisconnecting|TestState|GetRefCount|m_b[A-Z]|GetTotalNumberOf|%08x")),
    ("molive", 3, "str_molive", "a", re.compile(r"MoLive::|^ReadEp: |Ep goes beyond|Mobiclip|moflex demux", re.I)),
    ("zlib", 3, "str_zlib", "a", re.compile(ZLIB_MSG)),
    ("cxx_runtime", 3, "str_cxxrt", "a", re.compile(
        r"bad_alloc|unexpected exception|unknown exception|^Exception: |^exception$|bad_cast|bad_typeid|"
        r"pure virtual|__cxa_|std::")),
    ("rvct_clib", 3, "str_clib_fp", "a", re.compile(r"^(INFINITY|INF|NAN|nan|inf|infinity)$")),
    ("pead", 3, "str_pead", "a", re.compile(r"\bpead::|^pead")),
    ("ctr_sdk", 3, "str_sdk_service", "a", re.compile(SVC_NAME)),
    ("ctr_sdk", 2, "str_sdk_dmp", "a", re.compile(r"^dmp_\w")),
    ("ctr_sdk", 2, "str_sdk_ngword", "*", re.compile(r"^ngword:")),
    ("ctr_sdk", 2, "str_sdk_ec", "a", re.compile(
        r"ContentInfoArchive|MetaDataContentHeader|PricingSelection|^PURCHASABLE$|^RELEASED$|"
        r"/icons/%u\.icn|^Prices$|^Ratings$")),
    ("nw4c", 2, "str_nw4c", "a", re.compile(r"\bnw::|NW4C|nw4c")),
    # game-side strings: asset paths, game IDs, game class names, mount points
    ("game", 3, "str_game_asset", "*", re.compile(
        r"\.(lz|ctpk|tga|bcres|arc|bcsar|moflex|cmb|bccam|shbin|bcsdr|icn|bin|txt)\b|"
        r"^(rom|data|aoc|sdmc):|^(MID|SE|STRM|PID|IID|JID|MPID|MCID|FID|FSID|CID|MEC|EFF|TMTID|"
        r"NA|MEID|AI|GM|WSD|PLAYER|DUAL|CUTIN|GROUP)_")),
    ("game", 2, "str_game_name", "a", re.compile(
        r"^Proc[A-Z]|Menu|Seq|Dialog|Window|Drawer|Controller|Battle|Unit|Sortie|Chapter|Dual|^ev::|"
        r"^bev::|Talk|Shop|Event|Effect|Viewer|Action[A-Z]|%s|Volume|msec")),
]

# ----------------------------------------------------------------------------
# instruction scan
# ----------------------------------------------------------------------------
NOP = 0xE320F000
BX_LR = 0xE12FFF1E
MOV_PC_LR = 0xE1A0F00E


class F:
    __slots__ = ("i", "addr", "end", "calls", "tails", "fptrs", "strs", "svc", "tls", "nop",
                 "nop_bl", "bl", "movpc", "bxlr", "vfp", "ninsn", "vt_loads", "anch")

    def __init__(self, i):
        self.i = i
        self.addr = FUNCS[i]
        self.end = FEND[i]
        self.calls = set()
        self.tails = set()
        self.fptrs = set()
        self.strs = []
        self.svc = self.tls = self.nop = self.nop_bl = self.bl = 0
        self.movpc = self.bxlr = self.vfp = self.ninsn = 0
        self.vt_loads = []
        self.anch = collections.Counter()


FS = [F(i) for i in range(NF)]
LIT_TARGETS = collections.defaultdict(set)   # value loaded by LDR literal -> func indices

for f in FS:
    i0 = (f.addr - TEXT_VA) >> 2
    i1 = (min(f.end, TEXT_END) - TEXT_VA) >> 2
    prev = 0
    for i in range(i0, i1):
        if not IS_CODE[i]:
            prev = 0
            # words outside the decoded code ranges (unreached handlers) still count for
            # string references made with ADR, never for calls or code style
            w = TW[i]
            if (w >> 28) == 0xE and (w & 0x0FFF0000) == 0x028F0000:
                rot = ((w >> 8) & 0xF) * 2
                imm = w & 0xFF
                imm = ((imm >> rot) | (imm << (32 - rot))) & 0xFFFFFFFF if rot else imm
                s = get_string(TEXT_VA + 4 * i + 8 + imm)
                if s:
                    f.strs.append(s)
            continue
        w = TW[i]
        pc = TEXT_VA + 4 * i
        f.ninsn += 1
        cond = w >> 28
        top = w & 0x0F000000
        if cond != 0xF and top == 0x0B000000:                 # BL
            t = (pc + 8 + (s32((w & 0xFFFFFF) << 8) >> 6)) & 0xFFFFFFFF
            f.bl += 1
            if prev == NOP:
                f.nop_bl += 1
            if in_text(t):
                j = fidx(t)
                if j >= 0 and j != f.i:
                    f.calls.add(j)
        elif cond != 0xF and top == 0x0A000000:               # B
            t = (pc + 8 + (s32((w & 0xFFFFFF) << 8) >> 6)) & 0xFFFFFFFF
            if in_text(t) and not (f.addr <= t < f.end):
                j = fidx(t)
                if j >= 0 and j != f.i:
                    f.tails.add(j)
        elif cond != 0xF and top == 0x0F000000:               # SVC
            f.svc += 1
        elif (w & 0x0FFF0FFF) == 0x0E1D0F70:                  # mrc p15,0,rX,c13,c0,3
            f.tls += 1
        elif w == NOP:
            f.nop += 1
        elif w == MOV_PC_LR:
            f.movpc += 1
        elif w == BX_LR:
            f.bxlr += 1
        if cond != 0xF and (w & 0x0E000E00) in (0x0C000A00, 0x0E000A00) and (w & 0x0F000010) != 0x0E000010:
            f.vfp += 1
        tgt = None
        if cond != 0xF and (w & 0x0F7F0000) == 0x051F0000:   # LDR rX,[pc,#imm]
            imm = w & 0xFFF
            la = pc + 8 + imm if (w & 0x00800000) else pc + 8 - imm
            v = u32(la)
            if v is not None:
                tgt = v
                LIT_TARGETS[v].add(f.i)
                if in_text(v & ~1) and (v & ~1) in FSET:
                    f.fptrs.add(fidx(v & ~1))
        elif cond != 0xF and (w & 0x0FFF0000) in (0x028F0000, 0x024F0000):   # ADR
            rot = ((w >> 8) & 0xF) * 2
            imm = w & 0xFF
            imm = ((imm >> rot) | (imm << (32 - rot))) & 0xFFFFFFFF if rot else imm
            tgt = (pc + 8 + imm) if (w & 0x0FFF0000) == 0x028F0000 else (pc + 8 - imm)
        if tgt is not None and va2off(tgt) is not None:
            s = get_string(tgt)
            if s:
                f.strs.append(s)
        prev = w

CALLERS = [set() for _ in range(NF)]
for f in FS:
    for j in f.calls | f.tails:
        CALLERS[j].add(f.i)

# ----------------------------------------------------------------------------
# RTTI and vtables
# ----------------------------------------------------------------------------
WORDS_RD = {}
for base, size, off in ((RO_VA, RO_SZ, RO_OFF), (DATA_VA, DATA_SZ, DATA_OFF)):
    ws = struct.unpack_from("<%dI" % (size // 4), CODE, off)
    for k, w in enumerate(ws):
        WORDS_RD[base + 4 * k] = w
WIDX = collections.defaultdict(list)
for a, w in WORDS_RD.items():
    WIDX[w].append(a)

TYPEINFO = {}
with open(RTTI_CSV, newline="") as fh:
    for r in csv.DictReader(fh):
        TYPEINFO[int(r["typeinfo"], 16)] = r["name"]
RUNTIME_TI = {a for a, n in TYPEINFO.items() if n.startswith("__cxxabiv1::") or n.startswith("std::")}


def read_slots(p):
    out = []
    while len(out) < 512:
        w = WORDS_RD.get(p)
        if w is None or not in_text(w & ~1) or (w & ~1) not in FSET:
            break
        out.append(fidx(w & ~1))
        p += 4
    return out


VTABLES = []          # (addr_point, typeinfo or 0, [func idx])
for ti in sorted(TYPEINFO):
    for ref in WIDX.get(ti, []):
        ot = WORDS_RD.get(ref - 4)
        if ot is None or not (-0x10000 < s32(ot) <= 0):
            continue
        slots = read_slots(ref + 4)
        if slots:
            VTABLES.append((ref + 4, ti, slots))
# vtables built without RTTI: [0][0][fptr][fptr]..., address point referenced from code
for a in sorted(WORDS_RD):
    if WORDS_RD[a] != 0 or WORDS_RD.get(a + 4) != 0:
        continue
    ap = a + 8
    if ap not in LIT_TARGETS:
        continue
    slots = read_slots(ap)
    if len(slots) >= 2:
        VTABLES.append((ap, 0, slots))
VT_BY_AP = {ap: (ti, sl) for ap, ti, sl in VTABLES}

# slot usage count per function, by typeinfo kind
slot_game = collections.Counter()
slot_rt = collections.Counter()
slot_noti = collections.Counter()
for ap, ti, slots in VTABLES:
    for j in set(slots):
        if ti == 0:
            slot_noti[j] += 1
        elif ti in RUNTIME_TI:
            slot_rt[j] += 1
        else:
            slot_game[j] += 1
# ----------------------------------------------------------------------------
# code style
# ----------------------------------------------------------------------------
# "clib": returns with MOV pc,lr, no BX LR and no pre-branch NOP. Game/SDK/NEX code is
# built for interworking (BX LR) and carries pre-branch NOPs; the prebuilt RVCT library
# and hand-written codec assembly do not.
# STYLE "clib" only inside CLIB_BLOCK; the same shape elsewhere is "movpc" (a weak,
# fallback-only hint that never blocks other labels).
STYLE_PRE = [None] * NF
for f in FS:
    if f.movpc and not f.nop and not f.bxlr and f.i not in SINIT:
        STYLE_PRE[f.i] = "clib" if CLIB_BLOCK[0] <= f.addr < CLIB_BLOCK[1] else "movpc"
    elif f.nop:
        STYLE_PRE[f.i] = "nop"


def simd_count(f):
    """ARMv6 parallel add/sub (uadd8/usub8/uhadd8/uqsub8/...): codec SIMD."""
    i0 = (f.addr - TEXT_VA) >> 2
    i1 = (min(f.end, TEXT_END) - TEXT_VA) >> 2
    n = 0
    for i in range(i0, i1):
        w = TW[i]
        if IS_CODE[i] and (w & 0x0F800F10) == 0x06000F10 and (w >> 20) & 7:
            n += 1
    return n


def video_mc(f):
    """Packed-pixel motion-compensation loops (Mobiclip-style decoder asm): row strides of
    0x100..0x800 added to pointers, and AND rd, ip, rm, LSR #1 pixel averaging.
    Never true for static initializers (their struct-stride ADDs look the same)."""
    if f.i in SINIT:
        return False
    i0 = (f.addr - TEXT_VA) >> 2
    i1 = (min(f.end, TEXT_END) - TEXT_VA) >> 2
    stride = avg = 0
    for i in range(i0, i1):
        if not IS_CODE[i]:
            continue
        w = TW[i]
        if ((w & 0x0FE00000) == 0x02800000 and ((w >> 16) & 0xF) == ((w >> 12) & 0xF)
                and (w & 0xFFF) in (0xC01, 0xC02, 0xB01, 0xB02, 0xA01, 0xA02)):
            stride += 1
        if (w & 0x0FFF0FF0) == 0x000C00A0:
            avg += 1
    return stride >= 2 or avg >= 2


# ----------------------------------------------------------------------------
# direct anchors
# ----------------------------------------------------------------------------
EVID = [collections.defaultdict(list) for _ in range(NF)]   # lib -> [(strength, tag)]


def add(j, lib, strength, tag):
    EVID[j][lib].append((strength, tag))


def classify(kind, s):
    for lib, strength, tag, k, rx in STRING_RULES:
        if k != "*" and k != kind:
            continue
        if rx.search(s):
            return lib, strength, tag
    return None


# Pointer tables of strings in .rodata/.data (e.g. the DMP GL uniform table, RMC method
# tables, game ID tables): a function that loads an address inside such a table gets
# that table's library as a (weaker) string anchor.
_str_cache = {}
TABLE_HITS = []          # (word addr, lib, tag)
for a in sorted(WORDS_RD):
    w = WORDS_RD[a]
    if va2off(w) is None:
        continue
    if w not in _str_cache:
        st = get_string(w)
        _str_cache[w] = classify(*st) if st else None
    c = _str_cache[w]
    if c:
        TABLE_HITS.append((a, c[0], c[2]))
STR_TABLES = []          # (lo, hi, lib, tag)
_i = 0
while _i < len(TABLE_HITS):
    _k = _i
    while _k + 1 < len(TABLE_HITS) and TABLE_HITS[_k + 1][0] - TABLE_HITS[_k][0] <= 64:
        _k += 1
    grp = TABLE_HITS[_i:_k + 1]
    cnt = collections.Counter(g[1] for g in grp)
    lib, n = cnt.most_common(1)[0]
    if n >= 3 and n * 4 >= len(grp) * 3:
        tag = collections.Counter(g[2] for g in grp if g[1] == lib).most_common(1)[0][0]
        # Window = the table's own entries only. A +16 tail used to swallow whatever data
        # follows the table (a float-constant block after the SDK service table, a no-RTTI
        # slot table after z_errmsg) and mislabeled ~276 functions (M2 verifier finding).
        STR_TABLES.append((grp[0][0] - 8, grp[-1][0] + 3, lib, tag + "_table"))
    _i = _k + 1
_tab_lo = [t[0] for t in STR_TABLES]


def table_of(v):
    i = bisect.bisect_right(_tab_lo, v) - 1
    if i >= 0 and STR_TABLES[i][0] <= v <= STR_TABLES[i][1]:
        return STR_TABLES[i]
    return None


TABLE_USERS = collections.defaultdict(set)
for v in sorted(LIT_TARGETS):
    t = table_of(v)
    if t:
        for j in LIT_TARGETS[v]:
            TABLE_USERS[j].add((t[2], t[3]))

for f in FS:
    for kind, s in f.strs:
        c = classify(kind, s)
        if c:
            add(f.i, *c)
    for lib, tag in sorted(TABLE_USERS.get(f.i, ())):
        add(f.i, lib, 2, tag)
    # SVCs and TLS reads also appear inlined (nn::os/IPC helpers) in game and NEX code,
    # so they are good but not decisive alone; together they are.
    if f.svc:
        add(f.i, "ctr_sdk", 2, "svc")
    if f.tls:
        add(f.i, "ctr_sdk", 2, "tls_read")
    if STYLE_PRE[f.i] in ("clib", "movpc") and video_mc(f):
        add(f.i, "molive", 2, "video_mc_asm")
    elif STYLE_PRE[f.i] == "clib":
        add(f.i, "rvct_clib", 2, "clib_style")

for j, n in slot_game.items():
    add(j, "game", 4, "rtti_vslot")
for j, n in slot_rt.items():
    add(j, "cxx_runtime", 4, "cxxabi_vslot")
for ap, (ti, slots) in VT_BY_AP.items():
    for j in LIT_TARGETS.get(ap, ()):
        if ti == 0:
            continue
        if ti in RUNTIME_TI:
            add(j, "cxx_runtime", 3, "cxxabi_vtable_load")
        else:
            add(j, "game", 4, "rtti_vtable_load")

# crt0 by layout: entry stub, the .bss clear it calls first, and the exit SVC stub
add(0, "crt0", 5, "entry")
for f in FS:
    if f.addr < 0x00100114 and f.i != 0:
        if f.addr == 0x00100024 or (f.svc and f.ninsn <= 3):
            add(f.i, "crt0", 5, "entry_stub")

# static-init runner and the self-relative init list -> runtime
if FUNCS[-1] < INIT_ARRAY:
    add(NF - 1, "cxx_runtime", 2, "init_array_runner")


def direct_label(j):
    ev = EVID[j]
    if not ev:
        return None
    score = {lib: sum(s for s, _ in v) + 0.5 * max(s for s, _ in v) for lib, v in ev.items()}
    best = sorted(score.items(), key=lambda kv: (-kv[1], LIBS.index(kv[0])))
    lib, sc = best[0]
    second = best[1][1] if len(best) > 1 else 0
    top = max(s for s, _ in ev[lib])
    if lib == "game" and len(best) > 1:
        # a game string next to a library assert is usually an inlined library helper;
        # strong library anchors win unless RTTI says game
        tags = {t for _, t in ev["game"]}
        if not tags & {"rtti_vslot", "rtti_vtable_load"}:
            for olib, osc in best[1:]:
                if olib != "game" and max(s for s, _ in ev[olib]) >= 3:
                    lib, sc, top = olib, osc, 3
                    break
    tags = sorted({t for s, t in ev[lib]}, key=lambda t: (-max(s for s, tt in ev[lib] if tt == t), t))
    if (top >= 3 or sc >= 5) and sc >= 2 * second:
        conf = "high"
    elif top >= 2:
        conf = "medium"
    else:
        conf = "low"
    return lib, conf, "+".join(tags[:3])


LABEL = [None] * NF      # (lib, conf, evidence, stage)
for j in range(NF):
    d = direct_label(j)
    if d:
        LABEL[j] = (d[0], d[1], d[2], "direct")

STYLE = STYLE_PRE


def dump_features(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("addr,size,ninsn,bl,nop,nop_bl,movpc,bxlr,svc,tls,vfp,ncallers,ncallees,style,label,conf,evid,stage\n")
        for f in FS:
            L = LABEL[f.i] or ("", "", "", "")
            fh.write("0x%08X,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%s,%s,%s,%s,%s\n" % (
                f.addr, f.end - f.addr, f.ninsn, f.bl, f.nop, f.nop_bl, f.movpc, f.bxlr, f.svc, f.tls,
                f.vfp, len(CALLERS[f.i]), len(f.calls | f.tails), STYLE[f.i] or "", L[0], L[1], L[2], L[3]))


if __name__ == "__main__" and "--features" in sys.argv:
    os.makedirs(SCRATCH, exist_ok=True)
    dump_features(os.path.join(SCRATCH, "features.csv"))
    print("vtables", len(VTABLES), "with ti", sum(1 for v in VTABLES if v[1]),
          "noti", sum(1 for v in VTABLES if not v[1]))
    c = collections.Counter(L[0] for L in LABEL if L)
    print("direct", sum(c.values()), c.most_common())
    sys.exit(0)

# ----------------------------------------------------------------------------
# NOP-free windows
# ----------------------------------------------------------------------------
# Game, CTR-SDK, NEX and Pia code all carry pre-branch NOPs (about 1 in 10 BLs). Long
# stretches with none are separately built code (RVCT C library, codec assembly, and a
# few unidentified blocks). Propagation never puts NOP-family labels into such windows.
NOP_FAMILY = {"game", "ctr_sdk", "nex", "pia", "pead", "nw4c"}
NOPFREE = [False] * NF
LOWNOP = [False] * NF
_bl = [f.bl for f in FS]
_nop = [f.nop for f in FS]
_nb = [f.nop_bl for f in FS]
for j in range(NF):
    lo = hi = j
    bl = _bl[j]
    while bl < 80 and (lo > 0 or hi < NF - 1):
        if lo > 0:
            lo -= 1
            bl += _bl[lo]
        if hi < NF - 1:
            hi += 1
            bl += _bl[hi]
    nops = sum(_nop[lo:hi + 1])
    NOPFREE[j] = bl >= 60 and nops <= max(1, bl // 80)
    LOWNOP[j] = bl >= 60 and sum(_nb[lo:hi + 1]) * 100 < bl * 3   # <3% of BLs NOP-led


def allowed(j, lib):
    """May an inferred (non-direct) label put function j into lib?"""
    if lib in NOP_FAMILY:
        if STYLE[j] == "clib":
            return False
        f = FS[j]
        # a leaf has no branch to put a NOP before; a BX LR return is interworking
        # (compiled) style, so a NOP-free window says nothing about it
        if NOPFREE[j] and not f.nop and not (f.bxlr and not f.bl):
            return False
    return True


# ----------------------------------------------------------------------------
# propagation and contiguity
# ----------------------------------------------------------------------------
CONF_RANK = {"high": 3, "medium": 2, "low": 1}
NOPROP = {"crt0"}          # crt0 calls into everything; its label never propagates


def free(j):
    """Unlabeled and open to propagation/contiguity/priors. Static initializers are only
    labeled by their own anchors and stage, and act as barriers for runs."""
    return not LABEL[j] and j not in SINIT


def lab(k):
    """Label usable as propagation evidence: not crt0, and at least medium confidence
    (low-confidence guesses never seed further guesses). Runtime labels obtained only by
    contiguity never seed (a run between two leaves is too weak to grow a C-library
    chain)."""
    L = LABEL[k]
    if not L or L[0] in NOPROP or CONF_RANK[L[1]] < 2:
        return None
    if L[0] in RUNTIME and L[3] == "contiguity":
        return None
    return L[0]


def neighbours(j):
    """(labels of labeled callers, labels of labeled callees, n callers)."""
    cl = [x for x in (lab(k) for k in sorted(CALLERS[j])) if x]
    ce = [x for x in (lab(k) for k in sorted(FS[j].calls | FS[j].tails)) if x]
    return cl, ce, len(CALLERS[j])


def strong_game(k):
    L = LABEL[k]
    return bool(L) and L[0] == "game" and L[3] == "direct" and CONF_RANK[L[1]] >= 2


def lower_lib(j, libs):
    """Lowest layer below a set of distinct caller libraries."""
    nongame = sorted({x for x in libs if x != "game"}, key=lambda x: (LEVEL.get(x, 9), x))
    if not nongame:
        return None
    if "game" in libs and len(nongame) == 1 and nongame[0] not in RUNTIME:
        return nongame[0]               # the game calls a middleware API
    lvl = LEVEL.get(nongame[0], 9)
    if lvl <= 0:
        return nongame[0] if len(nongame) == 1 else None
    f = FS[j]
    if STYLE[j] == "clib" or (NOPFREE[j] and not f.nop):
        return "rvct_clib"
    if not f.nop and not f.svc and not f.tls and not f.calls and len(libs) >= 3:
        # leaf helper shared by three or more libraries (memset/division/new-style)
        return "rvct_clib"
    if nongame[0] == "zlib":
        return "rvct_clib"
    return "ctr_sdk"


def propagate_once():
    new = {}
    for j in range(NF):
        if not free(j):
            continue
        cl, ce, ncl = neighbours(j)
        ce_nr = [x for x in ce if x not in RUNTIME]
        callees = FS[j].calls | FS[j].tails
        cand = None
        # libraries never BL into game code
        ng = sum(1 for k in callees if strong_game(k))
        if ng:
            cand = ("game", "medium" if ng >= 2 or set(ce_nr) <= {"game"} else "low", "cg_calls_game")
        else:
            scl = set(cl)
            enough = ncl < 4 or len(cl) * 2 >= ncl
            if len(scl) == 1 and enough:
                L = cl[0]
                if L in RUNTIME:
                    if not ce_nr:
                        cand = (L, "medium" if len(cl) >= 2 else "low", "cg_runtime_only")
                elif set(ce_nr) <= {L}:
                    n = len(cl) + len(ce_nr)
                    cand = (L, "medium" if n >= 2 else "low", "cg_only_" + ("game" if L == "game" else "lib"))
                elif L != "game" and all(LEVEL.get(x, 9) <= LEVEL[L] for x in ce_nr):
                    cand = (L, "low", "cg_called_by_lib")
            elif len(scl) >= 2 and len(cl) >= 3:
                L = lower_lib(j, scl)
                if L and all(LEVEL.get(x, 9) <= LEVEL.get(L, 9) for x in ce_nr):
                    cand = (L, "low", "cg_shared_lower")
            elif (not cl and len(ce_nr) >= 2 and len(set(ce_nr)) == 1 and len(ce) == len(callees)
                  and ce_nr[0] not in ("game", "ctr_sdk")):
                # uncalled (virtual/callback) function whose every callee is one middleware;
                # not used for ctr_sdk: game virtuals calling SDK APIs look the same
                cand = (ce_nr[0], "low", "cg_callees_lib")
        if cand and allowed(j, cand[0]):
            if LOWNOP[j] and cand[0] in NOP_FAMILY and not FS[j].nop_bl:
                # thin NOP density: possibly separately built code; never more than low
                cand = (cand[0], "low", cand[2] + "_lownop")
            new[j] = cand
    for j, (lib, conf, ev) in new.items():
        LABEL[j] = (lib, conf, ev, "callgraph")
    return len(new)


def mixed_at(j, w=12):
    """Three or more libraries each with two or more direct anchors within +-w functions
    (e.g. the C-name tail of a sorted group, where namespaces no longer keep runs)."""
    libs = collections.Counter()
    for k in range(max(0, j - w), min(NF, j + w + 1)):
        L = LABEL[k]
        if L and L[3] == "direct" and L[0] not in NOPROP:
            libs[L[0]] += 1
    return sum(1 for n in libs.values() if n >= 2) >= 3


def fill_runs():
    """Unlabeled runs between two functions of one library join it (lexically sorted
    sections keep a namespace together)."""
    changed = 0
    j = 0
    while j < NF:
        if not free(j):
            j += 1
            continue
        k = j
        while k < NF and free(k):
            k += 1
        left = LABEL[j - 1] if j > 0 else None
        right = LABEL[k] if k < NF else None
        run = list(range(j, k))
        span = (FUNCS[k] if k < NF else TEXT_END) - FUNCS[j]
        ok_bounds = bool(left and right and CONF_RANK[left[1]] >= 2 and CONF_RANK[right[1]] >= 2
                         and left[0] not in NOPROP and right[0] not in NOPROP)
        if ok_bounds and left[0] == right[0]:
            lib = left[0]
            mixed = mixed_at(j) or mixed_at(k - 1)
            limit = 2 if mixed else 64
            if len(run) <= limit and all(allowed(x, lib) for x in run):
                tight = len(run) <= 6 or span <= 0x1000
                both_direct = left[3] == "direct" and right[3] == "direct"
                conf = "medium" if tight and both_direct and not mixed else "low"
                for x in run:
                    LABEL[x] = (lib, conf, "run_between", "contiguity")
                changed += len(run)
        elif ok_bounds:
            for x in run:
                cl, ce, _ = neighbours(x)
                votes = {v for v in cl + ce if v in (left[0], right[0])}
                if len(votes) == 1:
                    lib = votes.pop()
                    if allowed(x, lib):
                        LABEL[x] = (lib, "low", "run_edge_cg", "contiguity")
                        changed += 1
        j = k
    return changed


def converge():
    total = 0
    for _ in range(60):
        n = propagate_once()
        total += n
        if not n:
            break
    return total


# ----------------------------------------------------------------------------
# NOP-free runs: codec assembly span and C-library zone
# ----------------------------------------------------------------------------
# Inside a long run of functions without any NOP (separately built code), the span from
# the first to the last video-MC anchor (no BX LR) is the codec (MoLive/Mobiclip decoder
# asm, including the routines without the MC signature). The span grows past its end
# anchors only through functions with codec traits (MOV pc,lr returns or ARMv6 SIMD, and
# no BX LR); compiled glue after it (BX LR, init stubs, texture-header accessors) is not
# swept in. Outside a codec span, run members take the nearest runtime/middleware anchor
# of their own side of the span, unless the layering forbids it (a C-library function
# never calls into the codec or a middleware).
# Static initializers break runs: they are never part of a NOP-free block.
NF_RUNS = []
_j = 0
while _j < NF:
    if FS[_j].nop or _j in SINIT:
        _j += 1
        continue
    _k = _j
    while _k < NF and not FS[_k].nop and _k not in SINIT:
        _k += 1
    if _k - _j >= 40:
        NF_RUNS.append((_j, _k))
    _j = _k
BLOCK_LIBS = ("rvct_clib", "cxx_runtime", "zlib", "molive")
CODEC = set()


def codec_trait(x):
    f = FS[x]
    return not f.bxlr and (STYLE[x] in ("clib", "movpc") or simd_count(f) > 0)


n_block = 0
CODEC_SPANS = []
for lo, hi in NF_RUNS:
    mc = [x for x in range(lo, hi) if video_mc(FS[x]) and not FS[x].bxlr]
    if len(mc) < 3:
        continue
    a, b = mc[0], mc[-1]
    while a - 1 >= lo and codec_trait(a - 1):
        a -= 1
    while b + 1 < hi and codec_trait(b + 1):
        b += 1
    CODEC_SPANS.append((a, b))
    for x in range(a, b + 1):
        CODEC.add(x)
        L = LABEL[x]
        if L is None or L[2] == "clib_style":
            LABEL[x] = ("molive", "medium", "codec_asm_span", "block")
            n_block += 1

for lo, hi in NF_RUNS:
    cuts = [lo]
    for a, b in CODEC_SPANS:
        if lo <= a < hi:
            cuts += [a, b + 1]
    cuts.append(hi)
    for s0, s1 in zip(cuts[0::2], cuts[1::2]):        # segments outside codec spans
        anchors = [x for x in range(s0, s1) if LABEL[x] and LABEL[x][0] in BLOCK_LIBS
                   and (LABEL[x][3] == "block" or CONF_RANK[LABEL[x][1]] >= 2)]
        for x in range(s0, s1):
            if not free(x):
                continue
            callees = FS[x].calls | FS[x].tails
            if callees & CODEC:
                LABEL[x] = ("molive", "low", "calls_codec", "block")
                n_block += 1
                continue
            if not anchors:
                continue
            near = min(anchors, key=lambda y: (abs(y - x), y))
            lib = LABEL[near][0]
            if abs(near - x) > 48:
                continue
            ce = [lab(k) for k in sorted(callees)]
            if any(c and LEVEL.get(c, 9) > LEVEL[lib] for c in ce):
                continue
            LABEL[x] = (lib, "low", "nopfree_run_nearest", "block")
            n_block += 1

n_cg1 = converge()
n_fill = 0
for _ in range(12):
    a = fill_runs()
    b = converge()
    n_fill += a + b
    if not a and not b:
        break

# ----------------------------------------------------------------------------
# static initializers (init-array targets)
# ----------------------------------------------------------------------------
# A static initializer without a direct anchor takes the library of its translation unit,
# seen through (1) the functions that use the same .data/.bss objects it initializes
# (literal-pool addresses shared with it), (2) its callees (constructors), and (3) the
# slots of library vtables it installs. Votes come from labels of at least medium
# confidence. The init array is in object (link) order and the voted labels form
# contiguous library groups in it, so an unvoted initializer takes the library of its
# nearest voted init-array neighbours when they agree (or only one side exists);
# between two different libraries it stays unknown (static_init_unresolved).
SINIT_VOTE = {}


def sinit_votes(j):
    f = FS[j]
    users = set()
    i0 = (f.addr - TEXT_VA) >> 2
    i1 = (min(f.end, TEXT_END) - TEXT_VA) >> 2
    for i in range(i0, i1):
        w = TW[i]
        if IS_CODE[i] and (w >> 28) != 0xF and (w & 0x0F7F0000) == 0x051F0000:
            pc = TEXT_VA + 4 * i
            imm = w & 0xFFF
            v = u32(pc + 8 + imm if (w & 0x00800000) else pc + 8 - imm)
            if v is None:
                continue
            if DATA_VA <= v < BSS_END:
                us = LIT_TARGETS.get(v, set()) - SINIT
                if len(us) <= 40:                    # shared registries say nothing
                    users |= us
            if v in VT_BY_AP and VT_BY_AP[v][0] == 0:
                users |= set(VT_BY_AP[v][1])
    votes = collections.Counter()
    for k in sorted(users):
        x = lab(k)
        if x and x not in RUNTIME:
            votes[(x, "sinit_data_users")] += 1
    for k in sorted(f.calls | f.tails):
        x = lab(k)
        if x and x not in RUNTIME and k not in SINIT:
            votes[(x, "sinit_callees")] += 1
    return votes


n_sinit = 0
for j in SINIT_ORDER:
    if LABEL[j]:
        continue
    v = sinit_votes(j)
    per_lib = collections.Counter()
    for (lib, tag), n in v.items():
        per_lib[lib] += n
    if per_lib:
        lib, n = sorted(per_lib.items(), key=lambda kv: (-kv[1], LIBS.index(kv[0])))[0]
        total = sum(per_lib.values())
        if n * 3 >= total * 2:
            tags = [t for (l2, t), _ in sorted(v.items(), key=lambda kv: (-kv[1], kv[0])) if l2 == lib]
            conf = "medium" if n >= 3 and n == total else "low"
            SINIT_VOTE[j] = lib
            LABEL[j] = (lib, conf, "+".join(["static_init"] + tags[:2]), "sinit")
            n_sinit += 1
for pos, j in enumerate(SINIT_ORDER):
    if LABEL[j]:
        continue
    prev_l = next((SINIT_VOTE[k] for k in reversed(SINIT_ORDER[:pos]) if k in SINIT_VOTE), None)
    next_l = next((SINIT_VOTE[k] for k in SINIT_ORDER[pos + 1:] if k in SINIT_VOTE), None)
    if (prev_l or next_l) and (prev_l == next_l or not prev_l or not next_l):
        LABEL[j] = (prev_l or next_l, "low", "static_init+sinit_order_neighbours", "sinit")
        n_sinit += 1
    # else: between two different libraries in object order -> left unknown
    # (evidence static_init_unresolved)
n_cg2 = converge()


# Weak call-graph pass (one pass, no chaining): labels of any confidence count, but at
# least one voter must be a direct anchor or of medium+ confidence; still never
# overriding anything, still respecting NOP windows. A function whose labeled callers and
# callees (two or more) all agree on one library gets it at low confidence, before
# region priors.
def propagate_weak():
    new = {}
    for j in range(NF):
        if not free(j):
            continue
        votes = []
        strong = False
        for k in sorted(CALLERS[j]) + sorted(FS[j].calls | FS[j].tails):
            L = LABEL[k]
            if L and L[0] not in NOPROP and L[0] not in RUNTIME:
                votes.append(L[0])
                strong = strong or L[3] == "direct" or CONF_RANK[L[1]] >= 2
        if len(votes) < 2 or len(set(votes)) != 1 or not strong:
            continue
        lib = votes[0]
        if allowed(j, lib):
            new[j] = (lib, "low", "cg_weak", "callgraph_weak")
    for j, v in new.items():
        LABEL[j] = v
    return len(new)


n_weak_cg = propagate_weak()

# MOV pc,lr leaves outside the C-library block: C-library style, but only as a fallback
n_movpc = 0
for j in range(NF):
    if free(j) and STYLE[j] == "movpc":
        LABEL[j] = ("rvct_clib", "low", "clib_style_weak", "fallback")
        n_movpc += 1

# ----------------------------------------------------------------------------
# weak priors for what is left (STRATEGY.md 2.6 regions), always low confidence
# ----------------------------------------------------------------------------
REGION_PRIORS = [
    (0x00100000, 0x00120000, "ctr_sdk"),
    (0x00150000, 0x00220000, "game"),
    (0x0022E000, 0x00260000, "nex"),
    (0x002B0000, 0x00300000, "game"),
    (0x00380000, 0x00420000, "game"),
]


def apply_priors():
    n = 0
    for j in range(NF):
        if not free(j):
            continue
        a = FUNCS[j]
        for lo, hi, lib in REGION_PRIORS:
            if lo <= a < hi and allowed(j, lib) and not mixed_at(j):
                LABEL[j] = (lib, "low", "region_prior", "prior")
                n += 1
                break
    return n


n_prior = apply_priors()


def fill_runs_weak():
    """Last pass: an unlabeled run whose nearest labeled neighbours (any confidence) agree
    joins that library at low confidence."""
    n = 0
    j = 0
    while j < NF:
        if not free(j):
            j += 1
            continue
        k = j
        while k < NF and free(k):
            k += 1
        left = LABEL[j - 1] if j > 0 else None
        right = LABEL[k] if k < NF else None
        if (left and right and left[0] == right[0] and left[0] not in NOPROP and k - j <= 64
                and left[3] != "fallback" and right[3] != "fallback"
                and all(allowed(x, left[0]) for x in range(j, k))):
            for x in range(j, k):
                LABEL[x] = (left[0], "low", "run_between_weak", "contiguity")
            n += k - j
        j = k
    return n


n_weak = fill_runs_weak()


def finish():
    rows = []
    for j in range(NF):
        L = LABEL[j]
        if not L:
            cl, ce, _ = neighbours(j)
            if j in SINIT:
                ev = "static_init_unresolved"
            elif NOPFREE[j] and not FS[j].nop:
                ev = "nopfree_block"
                if cl and set(cl) == {"game"}:
                    ev = "nopfree_block_called_by_game"
            elif mixed_at(j):
                ev = "mixed_region"
            else:
                ev = "no_evidence"
            rows.append((FUNCS[j], "unknown", "low", ev))
        else:
            rows.append((FUNCS[j], L[0], L[1], L[2]))
    return rows


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(SCRATCH, exist_ok=True)
    rows = finish()
    with open(os.path.join(OUT_DIR, "library.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["func_addr", "library", "confidence", "evidence"])
        for a, lib, conf, ev in rows:
            w.writerow(["0x%08X" % a, lib, conf, ev])
    summ = {lib: [0, 0, 0, 0, 0] for lib in LIBS}
    for j, (a, lib, conf, ev) in enumerate(rows):
        s = summ[lib]
        s[0] += 1
        s[1] += FEND[j] - a
        s[2 + ["high", "medium", "low"].index(conf)] += 1
    with open(os.path.join(OUT_DIR, "library_summary.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["library", "functions", "bytes", "high", "medium", "low"])
        for lib in LIBS:
            w.writerow([lib] + summ[lib])
    dump_features(os.path.join(SCRATCH, "features.csv"))
    total = sum(s[1] for s in summ.values())
    print("functions %d  bytes 0x%X" % (len(rows), total))
    print("stages: direct %d, block %d, callgraph(first pass) %d, contiguity+cg %d, static inits %d "
          "(+cg %d), weak cg %d, movpc fallback %d, priors %d, weak runs %d" % (
              sum(1 for L in LABEL if L and L[3] == "direct"), n_block, n_cg1, n_fill, n_sinit, n_cg2,
              n_weak_cg, n_movpc, n_prior, n_weak))
    print("init-array targets %d, codec spans %s" % (
        len(SINIT), ", ".join("0x%08X-0x%08X" % (FUNCS[a], FEND[b]) for a, b in CODEC_SPANS)))
    for lib in LIBS:
        s = summ[lib]
        print("  %-12s %6d funcs %8d bytes (%5.1f%%)  h=%d m=%d l=%d" % (
            lib, s[0], s[1], 100.0 * s[1] / total, s[2], s[3], s[4]))
    g = summ["game"]
    gb = {c: sum(FEND[j] - rows[j][0] for j in range(NF) if rows[j][1] == "game" and rows[j][2] in c)
          for c in (("high",), ("high", "medium"), ("high", "medium", "low"))}
    unk = summ["unknown"][1]
    thin = sum(FEND[j] - rows[j][0] for j in range(NF)
               if rows[j][1] == "game" and rows[j][2] == "low" and LOWNOP[j])
    print("game share range: %.1f%% (game minus low labels in thin-NOP windows) .. %.1f%% (game + unknown)" % (
        100.0 * (g[1] - thin) / total, 100.0 * (g[1] + unk) / total))
    print("game share of .text bytes: high %.1f%%, high+med %.1f%%, all %.1f%%, all+unknown %.1f%%" % (
        100.0 * gb[("high",)] / total, 100.0 * gb[("high", "medium")] / total,
        100.0 * gb[("high", "medium", "low")] / total, 100.0 * (g[1] + unk) / total))


if __name__ == "__main__":
    main()
