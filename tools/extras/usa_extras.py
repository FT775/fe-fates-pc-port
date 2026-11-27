#!/usr/bin/env python3
"""Relocate another release's built-in tweaks (cheat codes) to this game's code.

Per-game data lives in config/readable/extras.json (entry = config/game.json "key"). The
Awakening entry (fe13) relocates another release's codes; it can be re-checked against the
Awakening port read-only:
    python tools/extras/usa_extras.py verify --game fe13 --root "../FE AWAKENING pc port"

Fates (fe14) has a native map instead: config/extras/fe14.json, our own patches found in this
game's code (60 fps battles, faster battles, 16:9; docs/EXTRAS.md). When config/extras/<key>.json
exists and says "kind": "native", verify and build use it (tools/extras/native.py) and the
config/readable/extras.json entry for that game is not read:
    python tools/extras/usa_extras.py verify                 # every Fates site against code.bin
    python tools/extras/usa_extras.py build [--speed N]      # -> build/extras/cheats/0004000000179800.txt

What the fe13 entry does (the original purpose of this tool):

github.com/Zelkin1/fe-awakening-recomp (MIT) ships three built-in tweaks for the EUR
release (000400000009F100): "16:9", "Smooth map sprites" and "Faster battles". They are
plain Action Replay 32-bit writes (code type 0) in Zakuro's enhancements.txt, plus a
feet hook (feet.rs) at two EUR addresses. This tool holds the EUR -> USA address map
found by docs/analysis/EXTRAS_USA.md, checks every USA address against our own
extracted/code.bin (by disassembling it and matching the instruction shape the patch
relies on), then relocates the EUR codes to USA addresses and writes:

  build/extras/usa_map.csv                     the map, with evidence and confidence
  build/extras/cheats/<target title id>.txt     Citra/Azahar/Zakuro cheat file
  build/extras/enhancements_usa.txt            the same codes as a Zakuro
                                               enhancements.txt section, for a Rust build

Nothing here contains game bytes: only addresses and descriptions of instruction shapes.
The EUR codes are read at run time from the read-only clone in build/ext/ (gitignored),
and all output goes to gitignored build/extras/. It never writes into %APPDATA%.

Usage:
    python tools/extras/usa_extras.py verify          # check the map against code.bin
    python tools/extras/usa_extras.py build [--speed N]   # verify, relocate, write outputs
        --speed   Faster battles speed in percent, 100..200 (default 150)
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import toolchain  # noqa: E402
from gamecfg import GAME  # noqa: E402

CONFIG = ROOT / "config" / "readable" / "extras.json"


class Ctx:
    """The per-game extras map (config/readable/extras.json, entry = config/game.json key)
    and the repo whose extracted/ files it is checked against (this one by default;
    --root lets the fe13 entry be re-checked against the Awakening port, read-only)."""

    def __init__(self, key: str, root: Path = ROOT):
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        if key not in cfg:
            sys.exit(f"error: {CONFIG.relative_to(ROOT)} has no entry for game {key!r}")
        e = cfg[key]
        self.key, self.entry, self.root = key, e, root
        self.status = e.get("status", "todo")
        if self.status != "ready":
            return
        h = lambda x: int(x, 16)  # noqa: E731
        self.code_bin = root / "extracted" / "code.bin"
        self.exheader = root / "extracted" / "exheader.bin"
        self.funcs = root / "config" / "functions.csv"
        self.enh_txt = ROOT / e["enhancements_txt"]
        self.src_id, self.dst_id = e["source_title_id"], e["target_title_id"]
        self.title = e["title"]
        self.text_base, self.text_size = h(e["text_base"]), h(e["text_size"])
        self.src_cave = (h(e["source_cave"][0]), h(e["source_cave"][1]))
        self.dst_cave = h(e["target_cave"])
        self.regions = [(h(r["lo"]), h(r["hi"]), h(r["offset"]), r["what"]) for r in e["regions"]]
        self.data_words = {h(x) for x in e["data_words"]}
        self.pointer_words = {h(x) for x in e["pointer_words"]}
        self.map = []
        for r in e["map"]:
            checks = []
            for c in r["checks"]:
                if "at" in c:
                    checks.append((h(c["at"]), c["insn"]))
                elif "word" in c:
                    checks.append(("word", h(c["word"]), c["is"]))
                elif "func" in c:
                    checks.append(("func", h(c["func"]), "start"))
                elif "callers_of" in c:
                    checks.append(("callers", h(c["callers_of"]), (h(c["window"][0]), h(c["window"][1]),
                                                                  c["calls"], c["owner"])))
            self.map.append((r["feature"], h(r["source"]), h(r["target"]), r["kind"], r["what"], checks,
                             r["confidence"]))


OUT = ROOT / "build" / "extras"
C: Ctx  # set in main()


def eur_to_usa(a: int) -> int:
    if C.src_cave[0] <= a < C.src_cave[1]:
        return C.dst_cave + (a - C.src_cave[0])
    for lo, hi, off, _ in C.regions:
        if lo <= a < hi:
            return a - off
    raise KeyError(f"EUR address 0x{a:08X} has no USA mapping")


def load_code() -> bytes:
    return C.code_bin.read_bytes()


def word(code: bytes, a: int) -> int:
    return struct.unpack_from("<I", code, a - C.text_base)[0]


def objdump_path() -> Path:
    d = toolchain.find({})
    if d is None:
        sys.exit("error: GNU ARM objdump not found (run python tools/toolchain.py)")
    return d / f"arm-none-eabi-objdump{toolchain.EXE}"


def disasm(words: dict[int, int]) -> dict[int, str]:
    """Disassemble single ARM words at their addresses -> 'mnemonic operands' text."""
    out: dict[int, str] = {}
    od = objdump_path()
    with tempfile.TemporaryDirectory() as td:
        for a, w in words.items():
            p = Path(td) / "w.bin"
            p.write_bytes(struct.pack("<I", w))
            r = subprocess.run([str(od), "-D", "-b", "binary", "-marm", f"--adjust-vma=0x{a:x}", str(p)],
                               capture_output=True, text=True).stdout
            line = next((x for x in r.splitlines() if re.match(r"^\s+[0-9a-f]+:\t", x)), "")
            parts = line.split("\t")
            out[a] = re.sub(r"\s+", " ", " ".join(parts[2:]).strip()) if len(parts) > 2 else "?"
    return out


def branch_target(a: int, w: int) -> int | None:
    if (w >> 25) & 7 != 5 or (w >> 28) == 0xF:
        return None
    off = w & 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    return (a + 8 + off * 4) & 0xFFFFFFFF


def encode_branch(a: int, w: int, target: int) -> int:
    off = (target - (a + 8)) // 4
    if not -0x800000 <= off < 0x800000 or (target - a) % 4:
        raise ValueError(f"branch at 0x{a:08X} cannot reach 0x{target:08X}")
    return (w & 0xFF000000) | (off & 0xFFFFFF)


def load_funcs() -> dict[int, str]:
    with C.funcs.open(newline="") as f:
        return {int(r["addr"], 16): r["name"] for r in csv.DictReader(f)}


def verify(code: bytes) -> list[dict]:
    funcs = load_funcs()
    want = {}
    for row in C.map:
        for c in row[5]:
            if isinstance(c[0], int):
                want[c[0]] = word(code, c[0])
    text = disasm(want)
    results = []
    for feature, eur, usa, kind, what, checks, conf in C.map:
        ok, ev = True, []
        for c in checks:
            if isinstance(c[0], int):
                seen = text[c[0]] if "@" in c[1] else text[c[0]].split(" @ ")[0]
                good = re.search(c[1], seen) is not None
                ev.append(f"0x{c[0]:08X} '{text[c[0]]}'" + ("" if good else " MISMATCH"))
            elif c[0] == "word":
                v = word(code, c[1])
                if c[2] == "five_thirds":
                    good = abs(struct.unpack("<f", struct.pack("<I", v))[0] - 5 / 3) < 1e-6
                    ev.append(f"0x{c[1]:08X} holds float 5/3" if good else f"0x{c[1]:08X} not 5/3")
                else:
                    good = v == int(c[2].split(":")[1], 16)
                    ev.append(f"0x{c[1]:08X} -> 0x{v:08X}")
            elif c[0] == "func":
                good = c[1] in funcs
                ev.append(f"{funcs.get(c[1], 'no function')} starts at 0x{c[1]:08X}")
            elif c[0] == "callers":
                lo, hi, calls, want_owner = c[2]
                inside, outside, owner = callers_window(code, c[1], lo, hi, funcs)
                good = inside == calls and owner == want_owner
                ev.append(f"{inside} calls to 0x{c[1]:08X} return into the window, all in {owner}; "
                          f"{outside} other callers outside it")
            else:
                good = False
            ok &= good
        results.append({"feature": feature, "eur": f"0x{eur:08X}", "usa": f"0x{usa:08X}",
                        "offset": f"0x{eur - usa:X}", "kind": kind, "what": what,
                        "evidence": "; ".join(ev), "checks_pass": "yes" if ok else "NO",
                        "confidence": conf if ok else "low"})
    # the cave must be spare zero bytes inside USA .text's last page
    ex = C.exheader.read_bytes()
    t_addr, t_pages, t_size = struct.unpack_from("<III", ex, 0x10)
    end, page_end = t_addr + t_size, t_addr + t_pages * 0x1000
    cave_len = C.src_cave[1] - C.src_cave[0]
    cave_ok = end <= C.dst_cave and C.dst_cave + cave_len <= page_end and \
        not any(code[C.dst_cave - C.text_base:C.dst_cave - C.text_base + cave_len])
    results.append({"feature": "code cave", "eur": f"0x{C.src_cave[0]:08X}", "usa": f"0x{C.dst_cave:08X}",
                    "offset": f"0x{C.src_cave[0] - C.dst_cave:X}", "kind": "spare bytes for the routines",
                    "what": f"USA .text ends 0x{end:08X}, last page ends 0x{page_end:08X}",
                    "evidence": f"0x{cave_len:X} bytes at 0x{C.dst_cave:08X} are zero padding" if cave_ok else "NOT free",
                    "checks_pass": "yes" if cave_ok else "NO", "confidence": "high" if cave_ok else "low"})
    return results


def callers_window(code: bytes, target: int, lo: int, hi: int, funcs: dict[int, str]):
    starts = sorted(funcs)
    inside, outside, owners = 0, 0, set()
    for off in range(0, C.text_size, 4):
        a = C.text_base + off
        w = struct.unpack_from("<I", code, off)[0]
        if (w >> 24) & 0xF == 0xB and branch_target(a, w) == target:
            if lo <= a + 4 < hi:
                inside += 1
                owners.add(funcs[starts[bisect.bisect_right(starts, a) - 1]])
            else:
                outside += 1
    return inside, outside, ",".join(sorted(owners)) or "-"


def eur_codes() -> list[tuple[str, str, list[tuple[int, str]], str]]:
    """(name, header line, [(addr, value text)], extra lines) of the EUR Awakening section."""
    if not C.enh_txt.is_file():
        sys.exit(f"error: {C.enh_txt} missing (shallow-clone Zelkin1/fe-awakening-recomp into build/ext/)")
    out, taking = [], False
    for line in C.enh_txt.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("="):
            taking = s.split()[1] == C.src_id
            continue
        if not taking or not s or s.startswith("#"):
            continue
        m = re.match(r"^([0-9A-Fa-f]{8}) (\S+)$", s)
        if m:
            out[-1][2].append((int(m.group(1), 16), m.group(2)))
        elif s.startswith("~"):
            out[-1] = (out[-1][0], out[-1][1], out[-1][2], s)
        elif "|" in s:
            out.append((s.split("|")[0].strip(), s, [], ""))
    return out


def relocate(code: bytes, speed: int) -> tuple[list, list[str], dict[int, str]]:
    sections, problems = [], []
    for name, header, lines, setting in eur_codes():
        new = []
        for a, v in lines:
            na = eur_to_usa(a)
            if v.startswith("{"):
                new.append((na, v))
                continue
            w = int(v, 16)
            if a in C.pointer_words:
                w = eur_to_usa(w)
            elif a not in C.data_words:
                t = branch_target(a, w)
                if t is not None:
                    w = encode_branch(na, w, eur_to_usa(t))
            new.append((na, f"{w:08X}"))
        sections.append((name, header, new, setting))
    # check: every relocated branch lands where the map says, every site is real code
    words = {a: int(v, 16) for _, _, new, _ in sections for a, v in new if not v.startswith("{")}
    text = disasm(words)
    usa_data = {eur_to_usa(x) for x in C.data_words | C.pointer_words}
    for a, w in words.items():
        t = branch_target(a, w)
        if t is not None and a not in usa_data and not (C.dst_cave <= t < C.dst_cave + 0x100
                                                            or t in {m[2] for m in C.map}):
            problems.append(f"branch at 0x{a:08X} -> 0x{t:08X} is not a mapped target")
    return sections, problems, text


def fill(v: str, speed: int) -> str:
    if v == "{100/x}":
        return f"{struct.unpack('<I', struct.pack('<f', 100 / speed))[0]:08X}"
    if v == "{x/100}":
        return f"{struct.unpack('<I', struct.pack('<f', speed / 100))[0]:08X}"
    return v


def main() -> int:
    global C
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["verify", "build"])
    ap.add_argument("--speed", type=int, default=150)
    ap.add_argument("--game", default=GAME.key, help="entry of config/readable/extras.json (default: this game)")
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="repo whose extracted/ and config/functions.csv are checked (read only)")
    a = ap.parse_args()
    if not 100 <= a.speed <= 200:
        sys.exit("error: --speed must be 100..200")
    native_cfg = ROOT / "config" / "extras" / f"{a.game}.json"
    if native_cfg.is_file():  # our own patches for this game (config/extras/, tools/extras/native.py)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import native  # noqa: E402
        cfg = native.load_config(a.game)
        if a.cmd == "build" and a.root.resolve() != ROOT.resolve():
            sys.exit("error: build writes this repo's build/extras/; run it with the default --root")
        if a.cmd == "verify":
            ok, rows = native.verify(cfg, a.speed, a.root)
            print(f"{len(rows)} words in {len(cfg['extras'])} extras: {'all check out' if ok else 'SOME FAIL'}")
            return 0 if ok else 1
        return native.build(cfg, a.speed, a.root)
    C = Ctx(a.game, a.root)
    if C.status != "ready":
        print(f"{C.entry.get('title', a.game)}: no extras map yet ({C.status}).")
        print(C.entry.get("todo", ""))
        return 2
    if a.cmd == "build" and a.root.resolve() != ROOT.resolve():
        sys.exit("error: build writes this repo's build/extras/; run it with the default --root")
    code = load_code()
    results = verify(code)
    for r in results:
        print(f"[{r['checks_pass']:>3}] {r['feature']:<19} EUR {r['eur']} -> USA {r['usa']} "
              f"(d={r['offset']}, {r['confidence']}): {r['evidence']}")
    bad = [r for r in results if r["checks_pass"] != "yes"]
    if a.cmd == "verify":
        print(f"{len(results) - len(bad)}/{len(results)} map rows check out")
        return 1 if bad else 0
    if bad:
        print("refusing to build: some map rows fail their checks")
        return 1
    sections, problems, text = relocate(code, a.speed)
    for p in problems:
        print("problem:", p)
    if problems:
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "usa_map.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(results[0]))
        wr.writeheader()
        wr.writerows(results)
    credit = ("Ported to the USA release from Zelkin1's fe-awakening-recomp (MIT) EUR enhancement; "
              "addresses moved by tools/extras/usa_extras.py. Personal use.")
    cheat = []
    for name, header, new, setting in sections:
        title = f"{name} {a.speed}%" if setting else name
        note = header.split("|")[3].strip() if header.count("|") >= 3 else ""
        cheat.append(f"[{title} (EUR extra, USA port)]")
        if note:
            cheat.append(f"*{note}")
        cheat.append(f"*{credit}")
        cheat += [f"{ad:08X} {fill(v, a.speed)}" for ad, v in new]
        cheat.append("")
    cdir = OUT / "cheats"
    cdir.mkdir(exist_ok=True)
    (cdir / f"{C.dst_id}.txt").write_text("\n".join(cheat), encoding="utf-8")
    enh = [f"= {C.dst_id} {C.title}"]
    for name, header, new, setting in sections:
        enh.append(header.replace("Claude, for this recomp", "Claude, for this recomp; USA port"))
        if setting:
            enh.append(setting)
        enh += [f"{ad:08X} {v}" for ad, v in new]
    (OUT / "enhancements_usa.txt").write_text("\n".join(enh) + "\n", encoding="utf-8")
    n = sum(len(s[2]) for s in sections)
    print(f"relocated {n} code lines in {len(sections)} enhancements; wrote {OUT / 'usa_map.csv'}, "
          f"{cdir / (C.dst_id + '.txt')}, {OUT / 'enhancements_usa.txt'}")
    for name, _, new, _ in sections:
        print(f"--- {name}")
        for ad, v in new:
            if not v.startswith("{"):
                print(f"  {ad:08X}: {text.get(ad, '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
