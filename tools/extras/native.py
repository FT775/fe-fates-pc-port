#!/usr/bin/env python3
"""Native extras: our own small code patches for this game, as Zakuro / Citra cheat codes.

The Awakening entry of usa_extras.py relocates another release's codes. A native entry
(config/extras/<game key>.json, "kind": "native") holds patches found in this game's own code
instead: for each site its address, the function that holds it (config/functions.csv), the
instruction shape of every original word (a regex on objdump's text), the SHA-1 of the original
bytes, and the words of the patch with their expected disassembly. Nothing here contains game
bytes; the original bytes are only read from extracted/code.bin (gitignored) and printed into the
gitignored build/extras/ map.

    python tools/extras/usa_extras.py verify                 # every site against code.bin
    python tools/extras/usa_extras.py build [--speed N]      # verify, then write the cheat file
    python tools/extras/native.py --selftest                 # the parts that need no game

Output (all gitignored, never %APPDATA%):
    build/extras/cheats/<title id>.txt    Zakuro / Citra / Azahar cheat file, every extra OFF
    build/extras/<key>_map.csv            every word: address, function, original and new text, bytes

A cheat that is OFF has no "*citra_enabled" line. The owner turns it on in Zakuro's Cheats
window (docs/EXTRAS.md). Code type 0 (32-bit write) only: "0XXXXXXX YYYYYYYY".
"""
from __future__ import annotations

import bisect
import csv
import hashlib
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

CONFIG_DIR = ROOT / "config" / "extras"
OUT = ROOT / "build" / "extras"
ENABLED = "*citra_enabled"


class Problem(Exception):
    pass


def h(x: str) -> int:
    return int(x, 16)


def f2w(v: float) -> int:
    return struct.unpack("<I", struct.pack("<f", v))[0]


def w2f(w: int) -> float:
    return struct.unpack("<f", struct.pack("<I", w))[0]


def config_path(key: str = GAME.key) -> Path:
    return CONFIG_DIR / f"{key}.json"


def load_config(key: str = GAME.key, path: Path | None = None) -> dict:
    p = path or config_path(key)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    if cfg.get("kind") != "native":
        raise Problem(f"{p.name}: not a native extras file")
    return cfg


def speed_words(cfg: dict, speed: int) -> dict[str, int]:
    s = cfg.get("speed", {})
    lo, hi = s.get("min", 100), s.get("max", 200)
    if not lo <= speed <= hi:
        raise Problem(f"speed {speed}%: must be {lo}..{hi}")
    return {"{speed}": f2w(speed / 100), "{fast}": f2w(2 * speed / 100)}


def fill_text(text: str, speed: int) -> str:
    return text.replace("{speed}", str(speed))


def patch_words(site: dict, speed_map: dict[str, int]) -> list[int]:
    out = []
    for w in site["words"]:
        out.append(speed_map[w] if w in speed_map else h(w))
    return out


def objdump() -> Path:
    d = toolchain.find({})
    if d is None:
        raise Problem("GNU ARM objdump not found (run python tools/toolchain.py)")
    return d / f"arm-none-eabi-objdump{toolchain.EXE}"


def disasm_run(base: int, words: list[int]) -> list[str]:
    """objdump text ('mnemonic operands  @ comment') of consecutive ARM words at base."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "w.bin"
        p.write_bytes(b"".join(struct.pack("<I", w) for w in words))
        r = subprocess.run([str(objdump()), "-D", "-z", "-b", "binary", "-marm", f"--adjust-vma=0x{base:x}", str(p)],
                           capture_output=True, text=True).stdout
    out = {}
    for line in r.splitlines():
        m = re.match(r"^\s+([0-9a-f]+):\t[0-9a-f]+ \t(.*)$", line)
        if m:
            out[int(m.group(1), 16)] = re.sub(r"\s+", " ", m.group(2).replace("\t", " ")).strip()
    return [out.get(base + 4 * i, "?") for i in range(len(words))]


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


def same_insn(expected: str, seen: str, word: int, speed_map: dict[str, int]) -> bool:
    """expected new text vs objdump: '.word X' is a data word, compared by value."""
    e = expected.strip()
    if e.startswith(".word"):
        v = e.split(None, 1)[1].strip()
        return word == (speed_map[v] if v in speed_map else int(v, 16))
    return norm(e) == norm(seen)


class Code:
    def __init__(self, cfg: dict, root: Path = ROOT):
        self.cfg = cfg
        self.base = h(cfg["text_base"])
        self.data = (root / "extracted" / "code.bin").read_bytes()
        self.funcs = load_funcs(root / "config" / "functions.csv")
        self.starts = sorted(self.funcs)

    def word(self, a: int) -> int:
        return struct.unpack_from("<I", self.data, a - self.base)[0]

    def bytes_at(self, a: int, n: int) -> bytes:
        return self.data[a - self.base:a - self.base + n]

    def func_of(self, a: int) -> tuple[str, int, int] | None:
        i = bisect.bisect_right(self.starts, a) - 1
        if i < 0:
            return None
        s = self.starts[i]
        name, end = self.funcs[s]
        return (name, s, end) if a < end else None


def load_funcs(path: Path) -> dict[int, tuple[str, int]]:
    with path.open(newline="", encoding="utf-8") as f:
        return {h(r["addr"]): (r["name"], h(r["end"])) for r in csv.DictReader(f)}


def check_site(code: Code, site: dict, speed_map: dict[str, int]) -> tuple[bool, list[str], list[dict]]:
    """(ok, evidence, rows) for one site."""
    cfg = code.cfg
    at = h(site["at"])
    words = patch_words(site, speed_map)
    n = len(words)
    ev, rows, ok = [], [], True
    if len(site["orig_asm"]) != n or len(site["new_asm"]) != n:
        return False, [f"0x{at:08X}: {n} words but {len(site['orig_asm'])} original / {len(site['new_asm'])} new texts"], []
    cave = [h(x) for x in cfg.get("cave", ["0", "0"])]
    if site["func"] == "(cave)":
        end, page_end = h(cfg["text_end"]), h(cfg["text_page_end"])
        good = cave[0] <= at and at + 4 * n <= cave[1] and end <= at and at + 4 * n <= page_end
        ev.append(f"in the spare bytes after .text (ends 0x{end:08X}, page 0x{page_end:08X})" if good
                  else "NOT inside the cave / spare bytes")
        ok &= good
    else:
        f = code.func_of(at)
        last = code.func_of(at + 4 * n - 4)
        good = f is not None and f[0] == site["func"] and last is not None and last[0] == site["func"]
        ev.append(f"in {f[0]} (0x{f[1]:08X}+0x{at - f[1]:X})" if f else "in no known function")
        if not good:
            ev.append(f"MISMATCH: expected {site['func']}")
        ok &= good
    orig = code.bytes_at(at, 4 * n)
    sha = hashlib.sha1(orig).hexdigest()
    good = sha == site["orig_sha1"]
    ev.append("original bytes: SHA-1 matches" if good else f"original bytes: SHA-1 {sha} MISMATCH")
    ok &= good
    otext = disasm_run(at, [struct.unpack_from("<I", orig, 4 * i)[0] for i in range(n)])
    ntext = disasm_run(at, words)
    for i in range(n):
        a = at + 4 * i
        o_ok = re.search(site["orig_asm"][i], otext[i]) is not None
        n_ok = same_insn(site["new_asm"][i], ntext[i], words[i], speed_map)
        ok &= o_ok and n_ok
        if not o_ok:
            ev.append(f"0x{a:08X} original '{otext[i]}' MISMATCH /{site['orig_asm'][i]}/")
        if not n_ok:
            ev.append(f"0x{a:08X} new '{ntext[i]}' MISMATCH '{site['new_asm'][i]}'")
        rows.append({"address": f"0x{a:08X}", "function": site["func"],
                     "original_bytes": f"{struct.unpack_from('<I', orig, 4 * i)[0]:08X}",
                     "original": otext[i], "new_bytes": f"{words[i]:08X}", "new": ntext[i]
                     if not site["new_asm"][i].startswith(".word") else f".word 0x{words[i]:08X} ({w2f(words[i]):g})"})
    for c in site.get("context", []):
        if "insn" in c:
            a = h(c["at"])
            t = disasm_run(a, [code.word(a)])[0]
            good = re.search(c["insn"], t) is not None
            ev.append(f"context 0x{a:08X} '{t}'" + ("" if good else " MISMATCH"))
        else:
            a = h(c["word"])
            v = w2f(code.word(a))
            good = abs(v - c["float"]) < 1e-6
            ev.append(f"context 0x{a:08X} = {v:g}" + ("" if good else f" MISMATCH (want {c['float']})"))
        ok &= good
    # branches in the new words must land where the text says (objdump prints the target)
    for i, w in enumerate(words):
        if (w >> 25) & 7 == 5 and (w >> 28) != 0xF:
            off = w & 0xFFFFFF
            off -= 0x1000000 if off & 0x800000 else 0
            t = (at + 4 * i + 8 + 4 * off) & 0xFFFFFFFF
            tf = code.func_of(t)
            good = (cave[0] <= t < cave[1]) or (tf is not None and (tf[1] == t or t < tf[2]))
            ev.append(f"branch 0x{at + 4 * i:08X} -> 0x{t:08X} ({'cave' if cave[0] <= t < cave[1] else (tf[0] if tf else '?')})"
                      + ("" if good else " NOT a known target"))
            ok &= good
    return ok, ev, rows


def verify(cfg: dict, speed: int, root: Path = ROOT, say=print) -> tuple[bool, list[dict]]:
    code = Code(cfg, root)
    sm = speed_words(cfg, speed)
    all_ok, rows = True, []
    seen: dict[int, str] = {}
    for ex in cfg["extras"]:
        for site in ex["sites"]:
            ok, ev, r = check_site(code, site, sm)
            for row in r:
                a = h(row["address"])
                if a in seen:
                    ok = False
                    ev.append(f"0x{a:08X} also patched by {seen[a]}")
                seen[a] = ex["id"]
                row["extra"] = ex["id"]
            rows += r
            all_ok &= ok
            say(f"[{'yes' if ok else ' NO'}] {ex['id']:<13} 0x{h(site['at']):08X} {len(site['words'])} word(s), "
                f"{site['what']}: {'; '.join(ev)}")
    return all_ok, rows


def cheat_lines(site: dict, sm: dict[str, int]) -> list[str]:
    at = h(site["at"])
    if at >> 28:
        raise Problem(f"0x{at:08X}: above the 28-bit address of code type 0")
    return [f"{at + 4 * i:08X} {w:08X}" for i, w in enumerate(patch_words(site, sm))]


VSYNC_COUNT = 0x006DCA88  # GameTime+4, counted by the vertical-blank callback TickVSync 0x001063AC


def cheat_text(cfg: dict, speed: int, enable: set[str] = frozenset(), gate: int | None = None) -> str:
    """Citra-format cheats, one per extra, OFF unless its id is in enable (tests only).
    gate (robot tests only): the code runs only once more than gate vertical blanks have passed
    (code type 4 on GameTime's counter), so a patch can start just before one battle."""
    sm = speed_words(cfg, speed)
    out = []
    for ex in cfg["extras"]:
        out.append(f"[{fill_text(ex['name'], speed)}]")
        if ex["id"] in enable:
            out.append(ENABLED)
        out.append(f"*{fill_text(ex['summary'], speed)}")
        out.append("*Fates port extra, found in this game's own code (docs/EXTRAS.md). Off = the original game. "
                   "Turning it off takes effect after a restart of the game.")
        if gate is not None:
            out.append(f"4{VSYNC_COUNT:07X} {gate:08X}")
        for site in ex["sites"]:
            out += cheat_lines(site, sm)
        if gate is not None:
            out.append("D2000000 00000000")
        out.append("")
    return "\n".join(out)


def build(cfg: dict, speed: int, root: Path = ROOT, out: Path = OUT, say=print) -> int:
    ok, rows = verify(cfg, speed, root, say)
    if not ok:
        say("refusing to build: some sites fail their checks")
        return 1
    out.mkdir(parents=True, exist_ok=True)
    key = GAME.key
    with (out / f"{key}_map.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["extra", "address", "function", "original_bytes", "original", "new_bytes", "new"])
        wr.writeheader()
        wr.writerows(rows)
    cdir = out / "cheats"
    cdir.mkdir(exist_ok=True)
    text = cheat_text(cfg, speed)
    path = cdir / f"{cfg['title_id']}.txt"
    path.write_text(text, encoding="utf-8")
    say(f"{len(cfg['extras'])} extras, {len(rows)} code lines, all OFF; wrote {path.relative_to(root)} and "
        f"{(out / (key + '_map.csv')).relative_to(root)}")
    say("install: the owner copies the file into Zakuro's cheats folder (docs/EXTRAS.md); this tool never does")
    return 0


# ------------------------------------------------------------------ self-test (no game)
def selftest() -> int:
    fails = []

    def ok(c, what):
        print(("ok   " if c else "FAIL ") + what)
        if not c:
            fails.append(what)

    cfg = load_config()
    sm = speed_words(cfg, 150)
    ok(sm["{speed}"] == 0x3FC00000 and sm["{fast}"] == 0x40400000, "150% -> 1.5 and 3.0 as floats")
    try:
        speed_words(cfg, 250)
        ok(False, "250% refused")
    except Problem:
        ok(True, "250% refused")
    t = cheat_text(cfg, 150)
    ok(ENABLED not in t, "every extra OFF in the cheat file")
    ok("Faster battles 150%" in t, "speed in the cheat name")
    lines = [ln for ln in t.splitlines() if re.fullmatch(r"[0-9A-F]{8} [0-9A-F]{8}", ln)]
    n = sum(len(s["words"]) for e in cfg["extras"] for s in e["sites"])
    ok(len(lines) == n, f"{n} code lines, all code type 0")
    ok(all(int(ln[:8], 16) >> 28 == 0 for ln in lines), "addresses fit code type 0")
    t2 = cheat_text(cfg, 125, {"fps60"})
    ok(t2.count(ENABLED) == 1 and "3FA00000" in t2 and "40200000" in t2, "test file: one extra on, 125% -> 1.25 / 2.5")
    ids = [e["id"] for e in cfg["extras"]]
    ok(len(ids) == len(set(ids)), "extra ids unique")
    # the Zakuro parser's shape: [name], *notes, code lines
    names = re.findall(r"^\[(.+)\]$", t, re.M)
    ok(len(names) == len(ids), "one [name] per extra")
    print(f"{'PASS' if not fails else 'FAIL'}: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    print(__doc__)
