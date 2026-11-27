#!/usr/bin/env python3
"""M1 exit tests for the byte-identical asm build (STRATEGY.md section 5, M1).

    python tools/m1_tests.py [clean|mutation|shift|all]

clean     gen twice -> identical asm (determinism); fresh build dir (C++ compiled from
          scratch, nothing cached) -> all hashes OK
mutation  change one instruction / one rodata word in a copy -> compare must FAIL and
          name the containing function; change the size of one .bss unit (no bytes in
          the image) -> the link must stop naming the unit; change one matched C++
          function (a copy of src/) -> compare must FAIL and name that function; change
          the size of the data in a matched C++ data unit -> the build must stop naming
          the unit
shift     insert a NOP before ~250 asm functions spread over .text and before every
          compiled (src_map matched) function, and a zero word at the start of ~100 data
          units spread over .rodata/.data/.bss and of every C++-owned data unit; relink
          and check the new image word-for-word against an exact prediction: branches
          re-aimed, symbolic pointers (pools, .rodata, .data, pc-relative words) moved,
          raw words unchanged. Compiled functions are predicted from their reference
          asm (asm/func/), so their relocations are checked too. Every symbol whose
          original address is known must sit at its predicted address (this is what
          checks .bss, which has no bytes). Also flags PC-relative loads that would
          straddle an insertion point and raw in-range words the prediction would move.
          Thumb (lines tagged `@ ADDR T`): symbolic `bl`/`blx` are predicted at f(target);
          a raw Thumb branch or literal load that would straddle an insertion point fails.

Works on copies under build/test_*; never edits asm/, src/ or the real build/.
"""
from __future__ import annotations

import bisect
import contextlib
import hashlib
import io
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build as B  # noqa: E402

ASM, BUILD, EXT = B.ASM, B.BUILD, B.EXT
NOP = 0xE320F000
LOG: list[str] = []


def log(s: str = "") -> None:
    print(s, flush=True)
    LOG.append(s)


def u32s(b: bytes) -> list[int]:
    return list(struct.unpack(f"<{len(b) // 4}I", b[: len(b) // 4 * 4]))


def fresh(d: Path) -> Path:
    # only ever removes our own scratch dirs under build/
    assert d.parent == BUILD and d.name.startswith("test_"), d
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def asm_digest() -> str:
    h = hashlib.sha1()
    for p in sorted(ASM.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(ASM).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def quiet(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = fn(*a, **k)
    return r, buf.getvalue()


# ----------------------------------------------------------------------- clean
def test_clean() -> bool:
    log("== clean build + determinism")
    B.gen()
    d1 = asm_digest()
    B.gen()
    d2 = asm_digest()
    det = d1 == d2
    log(f"   gen twice -> identical asm: {'PASS' if det else 'FAIL'} ({d1[:12]} / {d2[:12]})")
    out = fresh(BUILD / "test_clean")
    errs = B.build(ASM, out)
    if errs:
        log(f"   FAIL: assembler errors {errs[:3]}")
        return False
    bad, text = quiet(B.compare, True, out)
    for line in text.splitlines():
        log("   " + line)
    ok = det and not bad
    log(f"   clean build: {'PASS' if not bad else 'FAIL'}")
    return ok


# -------------------------------------------------------------------- mutation
def test_mutation() -> bool:
    log("== mutation (the gate must catch a one-instruction / one-word change)")
    work = fresh(BUILD / "test_mutation")
    asm = work / "asm"
    shutil.copytree(ASM, asm)
    files = sorted((asm / "text").glob("*.s"))
    target = files[len(files) // 2]
    lines = target.read_text().splitlines()
    pat = re.compile(r"^\tmov (r\d+), #(\d+) @ ([0-9A-F]{8})$")
    idx = next(i for i in range(len(lines) // 2, len(lines)) if pat.match(lines[i]))
    m = pat.match(lines[idx])
    addr = int(m.group(3), 16)
    # the containing function's label: the last `.type NAME, %function` above the line (labels
    # carry config/functions.csv names, e.g. symbol-map names in Fates, not only func_XXXXXXXX)
    func = next(m2.group(1) for l in reversed(lines[:idx])
                if (m2 := re.match(r"^\.type (\S+), %function$", l)))
    lines[idx] = f"\tmov {m.group(1)}, #{int(m.group(2)) ^ 1} @ {m.group(3)}"
    target.write_text("\n".join(lines) + "\n")
    # one rodata word too
    ros = sorted((asm / "data").glob("rodata_*.s"))
    ro = ros[len(ros) // 2]
    rl = ro.read_text().splitlines()
    ridx = next(i for i, l in enumerate(rl) if re.match(r"^\t\.word 0x[0-9A-F]{8} @", l) and i > len(rl) // 3)
    val = int(re.search(r"0x([0-9A-F]{8})", rl[ridx]).group(1), 16)
    raddr = rl[ridx].split("@")[1].strip()
    rl[ridx] = f"\t.word 0x{val ^ 0x80:08X} @ {raddr}"
    ro.write_text("\n".join(rl) + "\n")

    out = work / "out"
    errs = B.build(asm, out)
    if errs:
        log(f"   FAIL: mutated copy did not assemble: {errs[:2]}")
        return False
    bad, text = quiet(B.compare, True, out)
    named = func in text and f"{addr:08X}" in text
    ro_caught = "rodata  FAIL" in text and raddr in text
    for line in text.splitlines()[:12]:
        log("   " + line)
    ok = bool(bad) and named and ro_caught
    log(f"   text mutation at {addr:08X} in {func}: caught={bool(bad)} named={named}")
    log(f"   rodata mutation at {raddr}: caught={ro_caught}")
    ok = mutate_bss(work) and ok
    ok = mutate_cxx(work) and ok
    ok = mutate_cxx_data(work) and ok
    log(f"   mutation: {'PASS' if ok else 'FAIL'}")
    return ok


def build_expect_stop(*a, **k) -> tuple[bool, str]:
    """Run B.build expecting it to stop (sys.exit); returns (stopped, captured output)."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            errs = B.build(*a, **k)
    except SystemExit as ex:
        return True, buf.getvalue() + f"\n{ex.code}"
    return bool(errs), buf.getvalue() + (f"\n{errs[:2]}" if errs else "")


def mutate_bss(work: Path) -> bool:
    """Grow one .space in the middle of .bss by 4 bytes. .bss has no bytes in the image,
    so the hash gate alone could miss it; the per-unit placement asserts must not."""
    asm = work / "asm_bss"
    shutil.copytree(ASM, asm)
    files = sorted((asm / "data").glob("bss_*.s"))
    p = files[len(files) // 2]
    lines = p.read_text().splitlines()
    idx = next(i for i in range(len(lines) // 2, len(lines)) if lines[i].startswith("\t.space "))
    unit = next(re.match(r"^\.section \.bss\.u_([0-9A-F]{8})", l).group(1)
                for l in reversed(lines[:idx]) if l.startswith(".section .bss.u_"))
    n = int(lines[idx].split()[1], 16)
    lines[idx] = f"\t.space 0x{n + 4:X}"
    p.write_text("\n".join(lines) + "\n")
    stopped, text = build_expect_stop(asm, work / "out_bss")
    nxt = [e["unit"] for e in json.loads((ASM / "link_layout.json").read_text())["data"]
           if e["seg"] == "bss" and int(e["start"], 16) > int(unit, 16)]
    named = bool(nxt) and nxt[0] in text and "moved" in text
    log(f"   bss mutation: unit bss_{unit} grown by 4 bytes: stopped={stopped} "
        f"next unit named={named} ({nxt[0] if nxt else '-'})")
    return stopped and named


def mutate_cxx_data(work: Path) -> bool:
    """Grow the first array of the first matched data_map unit by one element in a copy
    of src/: the build must stop and name the unit (size / label offset check)."""
    lay = json.loads((ASM / "link_layout.json").read_text())
    owned = [e for e in lay["data"] if e.get("status") == "matched"]
    if not owned:
        log("   C++ data mutation: SKIP (no matched data_map rows)")
        return True
    e = owned[0]
    src = work / "src_data"
    shutil.copytree(B.SRC, src)
    p = src / Path(e["source"]).relative_to("src")
    txt = p.read_text(encoding="utf-8")
    tag = txt.find(e["unit"])
    m = re.compile(r"\[(0x[0-9A-Fa-f]+|\d+)\]").search(txt, max(tag, 0))
    if tag < 0 or not m:
        log(f"   C++ data mutation: FAIL (no `[N]` array after the {e['unit']} comment in {e['source']})")
        return False
    n = int(m.group(1), 0)
    p.write_text(txt[:m.start()] + f"[{n + 1}]" + txt[m.end():], encoding="utf-8")
    stopped, text = build_expect_stop(ASM, work / "out_cxx_data", src_root=src)
    named = e["unit"] in text
    for line in [l for l in text.splitlines() if e["unit"] in l][:3]:
        log("   " + line.strip())
    log(f"   C++ data mutation in {e['source']} ({e['unit']}): `[{n}]` -> `[{n + 1}]` "
        f"stopped={stopped} named={named}")
    return stopped and named


def mutate_cxx(work: Path) -> bool:
    """Change the first `return X;` of the lowest-address matched C++ function (a copy of
    src/) to `return (X) + 1;`: the hash gate must fail and name that function."""
    lay = json.loads((ASM / "link_layout.json").read_text())
    matched = [e for e in lay["text"] if e["kind"] == "func" and e["status"] == "matched"]
    if not matched:
        log("   C++ mutation: SKIP (no matched src_map rows)")
        return True
    src = work / "src"
    shutil.copytree(B.SRC, src)
    for e in matched:
        p = src / Path(e["source"]).relative_to("src")
        txt = p.read_text(encoding="utf-8")
        tag = txt.find(e["addr"][2:].upper())          # the address comment above the function
        m = re.compile(r"return ([^;]+);").search(txt, max(tag, 0))
        if tag >= 0 and m:
            p.write_text(txt[:m.start()] + f"return ({m.group(1)}) + 1;" + txt[m.end():], encoding="utf-8")
            break
    else:
        log("   C++ mutation: SKIP (no matched function with a `return X;`)")
        return True
    out = work / "out_cxx"
    errs = B.build(ASM, out, src_root=src)
    if errs:
        log(f"   FAIL: mutated C++ build did not assemble: {errs[:2]}")
        return False
    bad, text = quiet(B.compare, True, out)
    caught = bool(bad)
    named = f"{int(e['addr'], 16):08X}" in text and (e["name"] in text or e["symbol"] in text)
    for line in text.splitlines()[:6]:
        log("   " + line)
    log(f"   C++ mutation in {e['source']} ({e['name']}): `return ({m.group(1)}) + 1;` "
        f"caught={caught} named={named}")
    return caught and named


# ----------------------------------------------------------------------- shift
def sext24(v: int) -> int:
    return v - (1 << 24) if v & (1 << 23) else v


from gen_asm import pcrel_target  # noqa: E402  (same decoder the generator uses)


LINE = re.compile(r"^\t(\S+)\s*(.*?) @ ([0-9A-F]{8})( T)?$")
# .word arguments: raw hex, or a symbol expression (address or pc-relative difference)


def parse_asm_kinds(thumb: dict[int, str] | None = None) -> dict[int, str]:
    """addr -> 'insn' | 'inst' | 'wsym' | 'wraw' from the generated (unshifted) asm.
    Thumb lines (tagged `@ ADDR T`) go to `thumb` instead, halfword address ->
    'call' (symbolic `bl`/`blx SYM`, re-aimed by the linker) | 'raw' (.inst.n/.inst.w/
    .hword, never changes) | 'insn' (position-independent text)."""
    kinds = {}
    # asm/func/ and asm/dunit/ hold src_map functions and data_map units: nonmatching
    # ones are linked as asm, matched ones are reference asm for the compiled code/data
    # that replaces them (same words, same kinds)
    for p in [*(ASM / "text").glob("*.s"), *(ASM / "func").glob("*.s"),
              *(ASM / "data").glob("*.s"), *(ASM / "dunit").glob("*.s")]:
        for line in p.read_text().splitlines():
            m = LINE.match(line)
            if not m:
                continue
            op, args, a = m.group(1), m.group(2), int(m.group(3), 16)
            if m.group(4):
                if thumb is not None:
                    thumb[a] = ("call" if op in ("bl", "blx") else
                                "raw" if op in (".inst.n", ".inst.w", ".hword") else "insn")
                continue
            if op == ".word":
                kinds[a] = "wraw" if re.fullmatch(r"0x[0-9A-F]{8}", args) else "wsym"
            elif op == ".inst":
                kinds[a] = "inst"
            else:
                kinds[a] = "insn"
    return kinds


def predict_thumb(pred_text: list[int], orig: list[int], tkinds: dict[int, str], t0: int, f):
    """Apply the Thumb part of the shift prediction to the predicted .text words.

    Symbolic Thumb `bl`/`blx SYM` are re-aimed at f(target) (BLX keeps its word-aligned
    base). Raw Thumb branches (B, B<cond>, call-shaped .inst pairs) and PC-relative
    literal loads / ADR never change, so each one whose target moves relative to it is
    reported: the shifted image would be wrong there. Returns (words, calls, crossing)."""
    ob = struct.pack(f"<{len(orig)}I", *orig)
    pb = bytearray(struct.pack(f"<{len(pred_text)}I", *pred_text))

    def hw(a: int) -> int:
        return struct.unpack_from("<H", ob, a - t0)[0]

    calls, crossing = 0, []
    for a in sorted(tkinds):
        k = tkinds[a]
        h1 = hw(a)
        h2 = hw(a + 2) if a + 4 <= t0 + len(ob) else 0
        pair = h1 & 0xF800 == 0xF000 and h2 & 0xE800 == 0xE800
        t = why = None
        if pair:
            off = ((h1 & 0x7FF) << 12) | ((h2 & 0x7FF) << 1)
            off -= (1 << 23) if off & (1 << 22) else 0
            blx = h2 & 0xF800 == 0xE800
            t = (((a + 4) & ~3) if blx else a + 4) + off
            if k == "call":
                fa, ft = f(a), f(t)
                assert f(a + 2) == fa + 2, f"insertion point inside the Thumb call at {a:08X}"
                no = ft - (((fa + 4) & ~3) if blx else fa + 4)
                struct.pack_into("<HH", pb, fa - t0, 0xF000 | ((no >> 12) & 0x7FF),
                                 (0xE800 if blx else 0xF800) | ((no >> 1) & 0x7FF))
                calls += 1
                continue
            why = "raw BLX" if blx else "raw BL"
        elif h1 & 0xF800 == 0xE000:                                   # B
            t = a + 4 + (((h1 & 0x7FF) ^ 0x400) - 0x400) * 2
            why = "raw B"
        elif h1 & 0xF000 == 0xD000 and (h1 >> 8) & 0xF < 0xE:         # B<cond>
            t = a + 4 + (((h1 & 0xFF) ^ 0x80) - 0x80) * 2
            why = "raw B<cond>"
        elif h1 & 0xF800 in (0x4800, 0xA000):                         # ldr rX, [pc] / adr
            t = ((a + 4) & ~3) + (h1 & 0xFF) * 4
            why = "pc-relative"
        if t is not None and f(t) - f(a) != t - a:
            crossing.append((a, t, why))
    words = list(struct.unpack(f"<{len(pb) // 4}I", bytes(pb)))
    return words, calls, crossing


def known_symbol_addrs() -> dict[str, int]:
    """Original address of every symbol whose address is known without linking: config
    names (functions.csv, data_symbols.csv) and func_/lab_/D_XXXXXXXX names."""
    import csv
    out = {}
    for path in (ROOT / "config" / "functions.csv", ROOT / "config" / "data_symbols.csv"):
        if path.is_file():
            with path.open(newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    out[r["name"]] = int(r["addr"], 16)
    return out


def elf_section_addrs(elf: Path) -> dict[str, int]:
    import compile as CX
    return {sec.name: sec.addr for sec in CX.Elf(elf).sections}


def even_pick(items: list, n: int) -> list:
    """n items spread evenly over `items` (deterministic)."""
    if n <= 0 or not items:
        return []
    n = min(n, len(items))
    step = len(items) / n
    return [items[int(i * step + step / 2)] for i in range(n)]


def test_shift(n_points: int = 250, n_data: int = 100) -> bool:
    log("== shift (insert NOPs before many functions and zero words at the start of many data "
        "units; predict the new image exactly)")
    lay = B.layout()
    t0 = lay["text"]["addr"]
    t1 = t0 + lay["text"]["size"]
    slack = (lay["rodata"]["addr"] - t1) // 4 - 2
    cache = json.loads((BUILD / "cache" / "analysis.json").read_text())
    # compiled functions: one NOP before each, emitted by the linker script (LONG)
    ll = json.loads((ASM / "link_layout.json").read_text())
    cxx = [e for e in ll["text"] if e["kind"] == "func" and e["status"] == "matched"]
    cxx_points = [int(e["addr"], 16) for e in cxx]
    n_points = min(n_points, slack - len(cxx_points))
    # asm: insert only where the generator starts a section (functions merged into one
    # section because of PC-relative references are not separable, by design)
    secs = [int(x, 16) for x in (ASM / "sections.txt").read_text().split()]
    secs = [s for s in secs if t0 < s < t1]
    step = len(secs) // n_points
    asm_points = sorted(secs[i * step + step // 2] for i in range(n_points))
    names = {f"func_{p:08X}" for p in asm_points}
    points = sorted(asm_points + cxx_points)

    # data: a zero word at the start of ~n_data units, in proportion to the unit count of
    # each segment, plus every C++-owned unit (linker-script LONG / `. += 4`). Segment page
    # starts must not move: .rodata may grow by at most its slack before .data's page;
    # .data growth moves .bss (predicted), .bss growth moves nothing.
    seg = {k: (int(ll["segments"][k], 16), int(ll["segment_ends"][k], 16)) for k in ("rodata", "data", "bss")}
    units = {k: [e for e in ll["data"] if e["seg"] == k] for k in seg}
    cxx_units = [e for e in ll["data"] if e.get("status") == "matched"]
    total = sum(len(v) for v in units.values())
    dpts: dict[str, list[int]] = {}
    asm_unit_pad: set[str] = set()
    for k, us in units.items():
        cand = [e for e in us if e.get("status") != "matched"]
        pick = even_pick(cand, round(n_data * len(us) / total))
        asm_unit_pad |= {e["section"] for e in pick}
        dpts[k] = sorted(int(e["start"], 16) for e in pick + [e for e in cxx_units if e["seg"] == k])
    ro_slack = (seg["data"][0] - seg["rodata"][1]) // 4
    if len(dpts["rodata"]) > ro_slack:
        log(f"   FAIL: {len(dpts['rodata'])} rodata insertions exceed the {ro_slack}-word page slack")
        return False

    work = fresh(BUILD / "test_shift")
    asm = work / "asm"
    shutil.copytree(ASM, asm)
    inserted = 0
    for p in [*(asm / "text").glob("*.s"), *(asm / "func").glob("*.s")]:
        lines = p.read_text().splitlines()
        out, i = [], 0
        while i < len(lines):
            out.append(lines[i])
            m = re.match(r'^\.section \.text\.f_([0-9A-F]{8}),', lines[i])
            if m and f"func_{m.group(1)}" in names:
                out.append(lines[i + 1])            # .balign 4
                out.append("\tnop @ SHIFT")
                inserted += 1
                i += 2
                continue
            i += 1
        p.write_text("\n".join(out) + "\n")
    dinserted = 0
    for p in [*(asm / "data").glob("*.s"), *(asm / "dunit").glob("*.s")]:
        lines = p.read_text().splitlines()
        out, i = [], 0
        while i < len(lines):
            out.append(lines[i])
            m = re.match(r'^\.section (\.(rodata|data|bss)\.u_[0-9A-F]{8}),', lines[i])
            if m and m.group(1) in asm_unit_pad:
                out.append(lines[i + 1])            # .balign 4
                out.append("\t.space 4 @ SHIFT" if m.group(2) == "bss" else "\t.word 0 @ SHIFT")
                dinserted += 1
                i += 2
                continue
            i += 1
        p.write_text("\n".join(out) + "\n")
    log(f"   inserted {inserted} NOPs in asm (requested {n_points}) + {len(cxx_points)} before compiled "
        f"functions; .text grows by {(inserted + len(cxx_points)) * 4:#x}")
    log(f"   inserted {dinserted} zero words at data unit starts in asm + {len(cxx_units)} before C++ data "
        f"units: " + ", ".join(f"{k} {len(v)}" for k, v in dpts.items())
        + f" (rodata slack {ro_slack} words)")
    if inserted != n_points or dinserted != len(asm_unit_pad):
        log("   FAIL: could not place every insertion")
        return False
    res = work / "out"
    errs = B.build(asm, res, check_layout=False, pad_before={e["symbol"] for e in cxx},
                   pad_data_before={e["unit"] for e in cxx_units})
    if errs:
        log(f"   FAIL: shifted copy did not assemble: {errs[:3]}")
        return False

    (r0, r1), (d0, d1), (b0, b1) = seg["rodata"], seg["data"], seg["bss"]

    def f(x: int) -> int:
        if t0 <= x <= t1:
            return x + 4 * bisect.bisect_right(points, x)
        if r0 <= x <= r1:
            return x + 4 * bisect.bisect_right(dpts["rodata"], x)
        if d0 <= x < d1:                  # the .data end label is the first .bss label
            return x + 4 * bisect.bisect_right(dpts["data"], x)
        if b0 <= x <= b1:
            return x + 4 * len(dpts["data"]) + 4 * bisect.bisect_right(dpts["bss"], x)
        return x

    tkinds: dict[int, str] = {}
    kinds = parse_asm_kinds(tkinds)
    # PC-relative offset words (config/naming/pointer_overrides.csv action=pcrel) hold
    # T - (A + 8); after a shift they must hold f(T) - (f(A) + 8)
    pcrel = {}
    po = ROOT / "config" / "naming" / "pointer_overrides.csv"
    if po.is_file():
        import csv
        for r in csv.DictReader(po.open(encoding="utf-8")):
            if r["action"].strip() == "pcrel" and r["confidence"].strip() in ("high", "medium"):
                t, ins = (int(x, 16) for x in r["target"].replace("0x", "").split("@"))
                pcrel[int(r["word_addr"], 16)] = (t, ins)

    def predict_word(a: int, w: int) -> int:
        if a in pcrel:
            t, ins = pcrel[a]
            return (f(t) - (f(ins) + 8)) & 0xFFFFFFFF
        return f(w)

    pool = set(cache["jt_lits"])
    for la, sz in cache["lits"]:
        pool.update(range(la & ~3, la + sz, 4))
    orig = {k: u32s((EXT / f"{k}.bin").read_bytes()) for k in ("text", "rodata", "data")}
    got = {k: u32s((res / f"{k}.bin").read_bytes()) for k in ("text", "rodata", "data")}

    # predicted .text
    pred_text = [None] * (len(orig["text"]) + len(points))
    for p in points:
        pred_text[(f(p) - 4 - t0) // 4] = NOP
    crossing, unresolved, wild_branches, wild_pcrel = [], [], [], []
    img_end = lay["data"]["addr"] + lay["data"]["size"] + lay["bss_size"]
    sym_counts = {"text": 0, "rodata": 0, "data": 0}
    for i, w in enumerate(orig["text"]):
        a = t0 + 4 * i
        k = kinds.get(a, "wraw")
        new = w
        if k in ("insn", "inst"):
            if (w >> 28) != 0xF and (w >> 25) & 7 == 5:            # B / BL
                t = (a + 8 + (sext24(w & 0xFFFFFF) << 2)) & 0xFFFFFFFF
                if t0 <= t < t1:
                    new = (w & 0xFF000000) | (((f(t) - (f(a) + 8)) >> 2) & 0xFFFFFF)
                else:
                    # "branch" out of the image: data decoded as code; stays raw by design
                    wild_branches.append((a, w))
            else:
                t = pcrel_target(w, a)
                if t is not None and not (t0 <= t < img_end):
                    # PC-relative "access" far outside the image (data decoded as code,
                    # e.g. Fates 0x001B5C2C -> 0xF6DB5C34): the word stays what it was
                    # and nothing real is addressed, like a wild branch. Reported only.
                    wild_pcrel.append((a, t))
                elif t is not None and f(t) - f(a) != t - a:
                    crossing.append((a, t))
        elif k == "wsym":
            new = predict_word(a, w)
            sym_counts["text"] += new != w
        elif a in pool and f(w) != w:
            # only literal-pool / jump-table words are pointer candidates in .text;
            # other raw words there are inline data (strings, tables) reached by ADR
            unresolved.append((a, w))
        pred_text[(f(a) - t0) // 4] = new
    assert None not in pred_text
    pred_text, thumb_calls, thumb_crossing = predict_thumb(pred_text, orig["text"], tkinds, t0, f)

    def diff(pred, actual):
        return [i for i in range(max(len(pred), len(actual)))
                if i >= len(pred) or i >= len(actual) or pred[i] != actual[i]]

    bad_text = diff(pred_text, got["text"])
    pred = {}
    for sec in ("rodata", "data"):
        base = lay[sec]["addr"]
        pr = [None] * (len(orig[sec]) + len(dpts[sec]))
        for p in dpts[sec]:
            pr[(f(p) - 4 - base) // 4] = 0
        for i, w in enumerate(orig[sec]):
            a = base + 4 * i
            k = kinds.get(a, "wraw")
            if k == "wsym":
                new = predict_word(a, w)
                sym_counts[sec] += new != w
            else:
                if f(w) != w:
                    unresolved.append((a, w))
                new = w
            pr[(f(a) - base) // 4] = new
        assert None not in pr
        pred[sec] = pr
    bad_ro = diff(pred["rodata"], got["rodata"])
    bad_da = diff(pred["data"], got["data"])

    syms = B.sym_map(res)
    for name, bad, actual, predicted, base in (
            ("text", bad_text, got["text"], pred_text, t0),
            ("rodata", bad_ro, got["rodata"], pred["rodata"], lay["rodata"]["addr"]),
            ("data", bad_da, got["data"], pred["data"], lay["data"]["addr"])):
        log(f"   {name:6} predicted vs actual: {len(bad)} differing words "
            f"({sym_counts[name]} symbolic words changed value as predicted)")
        for i in bad[:8]:
            a = base + 4 * i
            g = actual[i] if i < len(actual) else None
            pv = predicted[i] if i < len(predicted) else None
            log(f"      {a:08X} ({B.nearest(syms, a)}) got {g and f'{g:08X}'} predicted {pv and f'{pv:08X}'}")

    # segment starts: .rodata and .data pages fixed, .bss right after the grown .data
    secaddr = elf_section_addrs(res / "fe1.elf")
    want_seg = {".rodata": r0, ".data": d0, ".bss": d1 + 4 * len(dpts["data"])}
    seg_bad = [(n, secaddr.get(n), v) for n, v in want_seg.items() if secaddr.get(n) != v]
    log(f"   segment starts as predicted: {'yes' if not seg_bad else seg_bad}")

    # every symbol with a known original address must sit at f(original); this is the
    # check that covers .bss (no bytes in the image) and C++-owned data
    known = known_symbol_addrs()
    sym_bad, sym_checked = [], {"text": 0, "rodata": 0, "data": 0, "bss": 0}
    name_addr = re.compile(r"^(?:func|lab|D)_([0-9A-F]{8})$")
    for addr, n in syms:
        m = name_addr.match(n)
        o = int(m.group(1), 16) if m else known.get(n)
        if o is None:
            continue
        k = ("text" if t0 <= o <= t1 else "rodata" if r0 <= o <= r1 else "data" if d0 <= o < d1
             else "bss" if b0 <= o <= b1 else None)
        if k is None:
            continue
        sym_checked[k] += 1
        if addr != f(o):
            sym_bad.append((n, o, addr, f(o)))
    log(f"   symbols at their predicted address: " + ", ".join(f"{k} {v}" for k, v in sym_checked.items())
        + f"; wrong: {len(sym_bad)}")
    for n, o, a, want in sym_bad[:8]:
        log(f"      {n} (orig {o:08X}) at {a:08X}, predicted {want:08X}")

    # cross-check unresolved words against the generator's reasoned reject list
    listed = {}
    pu = BUILD / "ptr_unresolved.txt"
    if pu.is_file():
        for line in pu.read_text().splitlines():
            if line and not line.startswith("#"):
                parts = line.split()
                listed[int(parts[0], 16)] = parts[2] if len(parts) > 2 else "?"
    unlisted = [(a, w) for a, w in unresolved if a not in listed]
    # raw words that equal the address of a label something else references symbolically
    # are the likeliest real pointers among them (listed for review, not a failure)
    label_addrs = set(known.values())
    for _, n in syms:
        m = name_addr.match(n)
        if m:
            label_addrs.add(int(m.group(1), 16))
    suspects = [(a, w) for a, w in unresolved if w in label_addrs]
    reasons: dict[str, int] = {}
    for a, _ in unresolved:
        reasons[listed.get(a, "UNLISTED")] = reasons.get(listed.get(a, "UNLISTED"), 0) + 1
    log(f"   branch-shaped words aimed outside the image (data decoded as code, left raw): {len(wild_branches)}"
        + "".join(f" {a:08X}" for a, _ in wild_branches[:5]))
    log(f"   PC-relative words aimed outside the image (data decoded as code, left as is): {len(wild_pcrel)}"
        + "".join(f" {a:08X}->{t:08X}" for a, t in wild_pcrel[:5]))
    log(f"   Thumb BL/BLX re-aimed by the linker (predicted): {thumb_calls}; raw Thumb branches / "
        f"PC-relative loads straddling an insertion point: {len(thumb_crossing)}")
    for a, t, why in thumb_crossing[:8]:
        log(f"      {a:08X} -> {t:08X} {why} ({B.nearest(syms, f(a))})")
    log(f"   PC-relative accesses straddling an insertion point: {len(crossing)}")
    for a, t in crossing[:8]:
        log(f"      {a:08X} -> {t:08X} ({B.nearest(syms, f(a))})")
    log(f"   raw in-range words the shift would move (left unmoved): {len(unresolved)} "
        f"({len(unresolved) - len(unlisted)} reasoned in build/ptr_unresolved.txt, {len(unlisted)} not); "
        f"by reason: {dict(sorted(reasons.items()))}")
    for a, w in unlisted[:8]:
        log(f"      {a:08X} = {w:08X}")
    dsus = [(a, w) for a, w in suspects if not t0 <= w <= t1]
    log(f"   of those, equal to a labelled address (review candidates): {len(suspects)}, "
        f"{len(suspects) - len(dsus)} into .text, {len(dsus)} into data:"
        + "".join(f" {a:08X}={w:08X}" for a, w in dsus[:10]))
    # every compiled function must sit exactly where the prediction puts it
    addrs = dict((n, a) for a, n in syms)
    misplaced = [(e["name"], addrs.get(e["symbol"]), f(int(e["addr"], 16))) for e in cxx
                 if addrs.get(e["symbol"]) != f(int(e["addr"], 16))]
    log(f"   compiled functions moved to their predicted address: {len(cxx) - len(misplaced)}/{len(cxx)}")
    for n, got_a, want in misplaced[:8]:
        log(f"      {n}: at {got_a and f'{got_a:08X}'} predicted {want:08X}")
    dmis = [(n, addrs.get(n), f(int(e["start"], 16) + off)) for e in cxx_units for n, off in e["labels"]
            if addrs.get(n) != f(int(e["start"], 16) + off)]
    nlab = sum(len(e["labels"]) for e in cxx_units)
    log(f"   C++ data labels moved to their predicted address: {nlab - len(dmis)}/{nlab} "
        f"({len(cxx_units)} unit(s))")
    for n, got_a, want in dmis[:8]:
        log(f"      {n}: at {got_a and f'{got_a:08X}'} predicted {want:08X}")
    ok = (not bad_text and not bad_ro and not bad_da and not crossing and not thumb_crossing
          and not unlisted and not misplaced
          and not dmis and not seg_bad and not sym_bad)
    log(f"   shift: {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    tests = {"clean": test_clean, "mutation": test_mutation, "shift": test_shift}
    run = tests if which == "all" else {which: tests[which]}
    results = {k: fn() for k, fn in run.items()}
    log("== summary: " + ", ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in results.items()))
    (BUILD / "m1_tests.txt").write_text("\n".join(LOG) + "\n")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
