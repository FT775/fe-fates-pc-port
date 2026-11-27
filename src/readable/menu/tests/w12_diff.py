#!/usr/bin/env python3
"""Host differential test of the options wiring's W1 (config_options_hook), W2 (config_serialize_guard) and the
options file reader (src/readable/core/options.c), all OFF, against the game's own code (docs/OPTIONS_WIRING.md
sections 4 and 7, "host tests"; F-034).

    python src/readable/menu/tests/w12_diff.py                 300 scenarios, seed 20261118
    python src/readable/menu/tests/w12_diff.py --seed 2 -n 400 another random sequence
    python src/readable/menu/tests/w12_diff.py --plant         also plant bugs: each must be caught
    python src/readable/menu/tests/w12_diff.py --options       only the options file test lines

Method (menu_diff / writer_diff's): one made-up scenario per case runs on both sides.

  Reference: the ORIGINAL ARM code from the owner's extracted/text.bin in arm_mini.py: GameConfigData::Reset
  (0x001D06DC), ::Deserialize (0x001D0374), ::Serialize (0x0050AEA0) and the four lines' GetValue / SetValue
  (as writer_diff), composed by section 4's rules written out here in Python (W1 steps 0-4, W2's own/applied
  rule, the depth count, the restore when W2 cannot write) and the gate's rules (armed + listed + readable;
  a session's stores logged with their old value and put back, newest first, on a failure).
  Readable: the C W1/W2 through the real gate (src/readable/core/writer.c, built with -DFE_WRITER_TESTS so the
  test can arm), the real config_write_options and the real options.c reading a file below build/. The game's
  three functions are C fixtures in the driver ("the original"); the cases with the hooks off compare them
  with the ARM code on the same states, so a fixture that is not the game's code shows as a mismatch too.

  The callees are one stub table on both sides: Stream::ReadByte / ReadLong / WriteByte / WriteLong (they
  store the position word +0x10 and the byte(s) at buffer +0x4 + position, as the game's do), the four
  Sound::SetVolume*, the movie player's virtual (+0x10 of its class table), ShowMovieSubtitle, Map::Get and
  map::Image::Danger::Update (as writer_diff).

  A scenario: the boot Reset (the block pointer not stored yet), a save load, a change on the game's own screen,
  the made-up suspend save (GameBackup::Serialize's order on a versus copy: ctor Reset, Reset, FromGame's Reset,
  the global block's Serialize into a memory stream, the copy's Deserialize from it, the copy's Serialize into
  the suspend file) followed by a game save, a game reset (ProcSequence::GameReset), a later save, a Serialize
  whose stream calls Deserialize on the global block (the depth rule), a save into a stream whose buffer is
  not mapped (W2 cannot write: restore and the game's Serialize), the options file changed between steps.
  Gate settings per case: everything on (most cases), or one of the three entries not armed / not listed, or
  shadow / capture / original mode.

Per case it compares: the ordered list of calls (every stub with its arguments), the bytes of the three blocks,
every stream (position word and buffer), the danger flag word, the gate's log at the end (address, size, old,
new, writer), W1/W2's record (lines, own[], applied[], depth, counts) and the gate's stray-store count (0).

Clean saves (every run, and inside every planted bug): load, apply, then the made-up suspend save and a game save
with nothing changed on the game's screen; every stream the C writes must equal the same steps run by the game's own
code with NO options file (section 7's "both outputs equal to the game's with no options"; the model is not used).

Also (--options and every run): the options file test lines shared with the page
(src/readable/core/tests/options_cases.json: patch 0002's own test vectors and more), the reader against a
Python copy of the page's Rust parse on 2,000 made-up files, the size limit and the %APPDATA% refusal; and the
unarmed table: the driver built WITHOUT -DFE_WRITER_TESTS (the table const and every entry 0, as in every
library) with FE_WRITERS listing all three and readable mode runs every scenario: nothing stores, no session
opens, every block and save is the game's.

All values are made-up test values, never game data. Needs extracted/text.bin and a host C compiler; SKIPs
(exit 0, says so) without them. Writes only under build/readable/writers/w12/. Exit 0 only when every case
matches and, with --plant, every planted bug is caught.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "battle", "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
sys.path.insert(0, HERE)
import arm_mini as A  # noqa: E402
import writer_diff as WD  # noqa: E402  (build_driver's include list, find_cc)

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "writers", "w12")
SRC_MENU = os.path.join(ROOT, "src", "readable", "menu")
SRC_CORE = os.path.join(ROOT, "src", "readable", "core")
CASES_JSON = os.path.join(ROOT, "src", "readable", "core", "tests", "options_cases.json")
WRITER_C = os.path.join(SRC_CORE, "writer.c")

SP, SP_NEST = 0x0FFFF000, 0x0FFFE000
STACK = (0x0FFFD000, 0x0FFFF100)

# the game's functions (read 2026-11-18 in asm/, the owner's code.bin) and their callees
RESET, DESERIALIZE, SERIALIZE = 0x001D06DC, 0x001D0374, 0x0050AEA0
READ_BYTE, READ_LONG, WRITE_BYTE, WRITE_LONG = 0x0044C07C, 0x0044C094, 0x0044C3DC, 0x0044C41C
SOUND = {0x0041F5F4: "bgm", 0x0041F49C: "se", 0x0041F880: "sys", 0x0041F938: "voice"}
SHOW_SUB = 0x0020C5B4
MOVIE_FN = 0x0BAD3000           # the movie player's virtual +0x10 (a made-up code address, a stub)
G_CONFIG, G_MOVIE, G_MAPIMAGE = 0x006DA0F8, 0x006DC588, 0x006D73E8
MAP_GET, UPDATE = 0x00342574, 0x0038F834
# line: (bit, GetValue, SetValue, offset, GetNum) in the writer's order
LINES = [(0x1, 0x003BC358, 0x003BC36C, 0x8, 5), (0x2, 0x003BC954, 0x003BC968, 0xC, 3),
         (0x4, 0x003BAEEC, 0x003BAF00, 0xE, 3), (0x8, 0x003BC508, 0x003BC51C, 0x16, 2)]
# options file line (danger_zone, hp_bars, animation_skip, anim_speed) -> line index above, page -> byte
PAGE_KEYS = ["danger_zone", "hp_bars", "animation_skip", "anim_speed"]
PAGE_LAST = [2, 2, 2, 3]
PAGE_LINE = {0: 2, 1: 3, 2: 0, 3: 1}            # page key index -> LINES index
# None = no game value behind the page value: not touched (round 38, OK A T3: no danger byte hides the zone)
TO_BYTE = {0: [0, 0, 1], 1: [0, 1, 2, 0], 2: [0, 0, None], 3: [0, 1, 0]}  # LINES index -> page value -> byte

# made-up layout
CFG_G, CFG_V, CFG_B = 0x08100000, 0x08100100, 0x08100200   # global block, versus copy, a stray block
CFG_U = 0x08104FF0   # a block whose +0x10 .. +0x16 lie on a page that is not mapped (the block check's case)
MOVIE, MOVIE_VT = 0x08140000, 0x08141000
MAPIMG = 0x08200000
ITEM = 0x08130000
STREAMS = {n: (0x08110000 + 0x40 * i, 0x08120000 + 0x100 * i) for i, n in
           enumerate(["save", "save2", "mem", "file1", "file2", "file3", "nest"])}
UNMAPPED_BUF = 0x0BAD0000
RESULT_OK, RESULT_OFF, RESULT_REFUSED, RESULT_ROLLED = 0, 1, 2, 3
W_OPTIONS, W_HOOK, W_GUARD = 1, 2, 3
NAMES = {W_OPTIONS: "config_options", W_HOOK: "config_options_hook", W_GUARD: "config_save_guard"}
GATES = ["on"] * 10 + ["nohook", "noguard", "nowriter", "unlisted_guard", "unlisted_hook", "shadow", "capture",
                       "original"]


# ------------------------------------------------------------------ the page's parse (Rust, patch 0002)
RUST_WS = set(chr(c) for c in list(range(0x09, 0x0E)) + [0x20, 0x85, 0xA0, 0x1680] + list(range(0x2000, 0x200B))
              + [0x2028, 0x2029, 0x202F, 0x205F, 0x3000])


def rust_trim(s: str) -> str:
    b, e = 0, len(s)
    while b < e and s[b] in RUST_WS:
        b += 1
    while e > b and s[e - 1] in RUST_WS:
        e -= 1
    return s[b:e]


def rust_u8(v: str):
    if v.startswith("+") and len(v) > 1:
        v = v[1:]
    if not v or any(c not in "0123456789" for c in v):
        return None
    n = int(v)
    return n if n <= 255 else None


def page_parse(data: bytes) -> list[int]:
    """fe_options::parse (patch 0002) for the four game lines: [danger_zone, hp_bars, animation_skip, anim_speed]."""
    out = [0, 0, 0, 0]
    try:
        text = data.decode("utf-8")  # read_to_string: invalid UTF-8 is an error, unwrap_or_default: empty
    except UnicodeDecodeError:
        return out
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for line in lines:
        if line.endswith("\r"):
            line = line[:-1]
        t = rust_trim(line)
        if not t or t.startswith("#") or "=" not in t:
            continue
        key, value = t.split("=", 1)
        key, value = rust_trim(key), rust_trim(value)
        if key in PAGE_KEYS:
            k = PAGE_KEYS.index(key)
            n = rust_u8(value)
            out[k] = n if n is not None and n <= PAGE_LAST[k] else 0
    return out


def file_parse(data: bytes | None) -> list[int]:
    if data is None or len(data) > 65536:
        return [0, 0, 0, 0]
    return page_parse(data)


def random_file(rng) -> bytes:
    """A made-up options file: mostly the page's own form, sometimes junk the parse must survive."""
    parts = []
    if rng.random() < 0.3:
        parts.append("# FE options. 0 is off, and off is the original game.")
    keys = PAGE_KEYS + ["stance_forecast", "growth_display", "dual_strike", "future_key", "Danger_zone", "hp_bar"]
    for _ in range(rng.randrange(0, 9)):
        k = rng.choice(keys)
        v = rng.choice(["0", "1", "2", "3", "4", "+1", "-1", "01", "x", "", "1 # c", "256", "+", "２", "1.0", "2"])
        sep = rng.choice([" = ", "=", "  =\t", " =  ", "= "])
        pre = rng.choice(["", "", " ", "\t", "　", "﻿", "#"])
        parts.append(pre + k + sep + v + rng.choice(["", "", " ", "\r", " ", "\x1c"]))
    if rng.random() < 0.15:
        parts.append("no equals sign here")
    text = rng.choice(["\n", "\r\n"]).join(parts) + rng.choice(["", "\n", "\r\n"])
    data = text.encode("utf-8")
    r = rng.random()
    if r < 0.03:
        data += b"\xff"                    # not UTF-8: the whole file counts as empty
    elif r < 0.05:
        data = b"\xed\xa0\x80" + data      # an encoded surrogate: not UTF-8 either
    elif r < 0.07:
        data = b"\xc0\xaf" + data          # an overlong form
    return data


# ------------------------------------------------------------------ the reference
class Mem(A.Memory):
    """Guest memory; while a gate session is open, every store (stack left out) is logged with its old value."""

    def __init__(self, text: bytes):
        super().__init__(text)
        self.session = None
        self.sess_from = 0
        self.fail = False
        self.log: list[tuple] = []

    def mapped(self, a: int) -> bool:
        return self.pages.get((a & A.MASK) >> 12) is not None

    def write(self, a: int, n: int, v: int) -> None:
        a &= A.MASK
        if self.session is not None and not (STACK[0] <= a < STACK[1]):
            if not all(self.mapped(a + i) for i in range(n)):
                self.fail = True           # the gate refuses a store it could not undo: nothing stored
                return
            old = self.read(a, n)
            self.log.append((a, n, old, v & ((1 << (8 * n)) - 1), self.session))
        super().write(a, n, v)


class Ref:
    def __init__(self, text: bytes, case: dict):
        self.text, self.case = text, case
        self.mem = Mem(text)
        for a, d in case["mem"]:
            self.mem.map(a, d)
        self.ev: list[str] = []
        self.lines, self.own, self.applied = 0, [0] * 4, [0] * 4
        self.depth = self.calls = self.applies = self.saves = self.give_ups = 0
        self.file = None
        g = case["gate"]
        self.on = {w: g["armed"][w] and g["listed"][w] and g["mode"] == "readable" for w in (1, 2, 3)}

    # ---- stubs (the same effects on both sides)
    def u32(self, a):
        return self.mem.read(a, 4)

    def st_pos(self, s):
        pos, buf = self.u32(s + 0x10), self.u32(s + 4)
        self.mem.write(s + 0x10, 4, pos + 1)
        return buf + pos

    def read_byte(self, s):
        self.ev.append(f"rb:{s:x}")
        a = self.st_pos(s)
        return self.mem.read8(a)

    def read_long(self, s):
        self.ev.append(f"rl:{s:x}")
        v = 0
        for i in range(4):
            v |= self.mem.read8(self.st_pos(s)) << (8 * i)
        return v

    def write_byte(self, s, v):
        self.ev.append(f"wb:{s:x}:{v & 0xFF:x}")
        if s == STREAMS["nest"][0] and self.u32(s + 0x10) == 0 and self.mem.session is None:
            self.ev.append("nest")
            self.hook(DESERIALIZE, CFG_G, STREAMS["save2"][0], sp=SP_NEST)
        self.mem.write(self.st_pos(s), 1, v)

    def write_long(self, s, v):
        self.ev.append(f"wl:{s:x}:{v & A.MASK:x}")
        for i in range(4):
            self.mem.write(self.st_pos(s), 1, v >> (8 * i))

    def stubs(self):
        st = {READ_BYTE: lambda c, a: self.read_byte(a[0]), READ_LONG: lambda c, a: self.read_long(a[0]),
              WRITE_BYTE: lambda c, a: self.write_byte(a[0], a[1]) or 0,
              WRITE_LONG: lambda c, a: self.write_long(a[0], a[1]) or 0,
              MOVIE_FN: lambda c, a: self.ev.append(f"movie:{a[0]:x}") or 0,
              MAP_GET: lambda c, a: self.ev.append("mapget") or self.case["map_value"]}
        for addr, name in SOUND.items():
            st[addr] = (lambda nm: lambda c, a: self.ev.append(f"{nm}:{a[0] & A.MASK:x}") or 0)(name)
        return st

    # ---- the game's own functions on the ARM interpreter
    def arm(self, func, r0, r1=0, sp=SP):
        cpu = A.Cpu(self.mem, self.stubs())
        cpu.r[13], cpu.r[14], cpu.r[0], cpu.r[1] = sp, A.RETURN_SENTINEL, r0, r1
        pc = cpu.run(func, stop={MOVIE_FN, SHOW_SUB, WRITE_BYTE, UPDATE})
        if pc == MOVIE_FN:                     # Reset's tail call of the movie player's virtual
            self.ev.append(f"movie:{cpu.r[0]:x}")
        elif pc == SHOW_SUB:                   # Deserialize's tail call
            self.ev.append(f"sub:{cpu.r[0]:x}")
        elif pc == WRITE_BYTE:                 # Serialize's last byte, a tail branch
            self.write_byte(cpu.r[0], cpu.r[1])
        elif pc == UPDATE:                     # DangerPanel::SetValue's tail branch
            self.ev.append(f"upd:{cpu.r[0]:x}")
            a = cpu.r[0] + 0x200
            self.mem.write(a, 4, self.u32(a) | 2)
        return cpu.r[0]

    # ---- the gate and config_write_options (writer_diff's reference)
    def write_options(self, want: dict, rebuild: bool = True, any_byte: bool | None = None) -> int:
        """config_write_options; rebuild=False: the danger line's byte is stored as DangerPanel::SetValue stores
        it, but the zone is not rebuilt (no Map::Get, no Update): config_apply_options (W1's apply, the screen's
        value range; round 40) and config_restore_options (W2's give-up, any_byte: any value)."""
        if any_byte is None:
            any_byte = not rebuild
        for i, v in want.items():
            if v >= (0x100 if any_byte else LINES[i][4]):  # the restore puts back the save's own byte, any value
                return RESULT_REFUSED
        if not self.on[W_OPTIONS]:
            return RESULT_OFF
        self.begin(W_OPTIONS)
        for i, (bit, get, setv, off, num) in enumerate(LINES):
            if i not in want or self.mem.fail:
                continue
            if self.arm(get, ITEM) == want[i]:
                continue
            if not rebuild and bit == 0x4:
                self.mem.write(self.u32(G_CONFIG) + off, 1, want[i])
                continue
            self.arm(setv, ITEM, want[i])
        return RESULT_OK if self.end() else RESULT_ROLLED

    def begin(self, w):
        self.mem.session, self.mem.sess_from, self.mem.fail = w, len(self.mem.log), False

    def end(self) -> bool:
        ok = not self.mem.fail
        if not ok:  # newest first
            while len(self.mem.log) > self.mem.sess_from:
                a, n, old, _new, _w = self.mem.log.pop()
                A.Memory.write(self.mem, a, n, old)
        self.mem.session = None
        self.mem.fail = False
        return ok

    def is_global(self, this):
        return this != 0 and this == self.u32(G_CONFIG) and self.mem.mapped(this) and self.mem.mapped(this + 0x16)

    # ---- section 4: W1 and W2
    def hook(self, func, this, stream=0, sp=SP):
        apply = self.on[W_HOOK] and self.depth == 0 and self.is_global(this)
        self.arm(func, this, stream, sp)
        if not apply:
            return
        self.lines = 0
        self.calls += 1
        page = file_parse(self.file)
        if not any(page):
            return
        if not self.on[W_GUARD]:
            return
        want, own = {}, {}
        for k in range(4):
            if page[k] and TO_BYTE[PAGE_LINE[k]][page[k]] is not None:
                i = PAGE_LINE[k]
                want[i] = TO_BYTE[i][page[k]]
                own[i] = self.mem.read8(this + LINES[i][3])
        if not want:
            return
        if self.write_options(want, rebuild=False, any_byte=False) != RESULT_OK:  # config_apply_options (round 40)
            return
        for i in want:
            self.own[i], self.applied[i] = own[i], want[i]
        self.lines = sum(LINES[i][0] for i in want)
        self.applies += 1

    def guard(self, this, stream):
        self.depth += 1
        if self.lines == 0 or not self.is_global(this):
            self.arm(SERIALIZE, this, stream)
            self.depth -= 1
            return
        word = self.u32(this + 4)
        b = [self.mem.read8(this + 8 + k) for k in range(15)]
        for i, (bit, _g, _s, off, _n) in enumerate(LINES):
            if self.lines & bit:
                if b[off - 8] == self.applied[i]:
                    b[off - 8] = self.own[i]
                else:
                    self.own[i] = b[off - 8]
        done = False
        if self.on[W_GUARD]:
            self.begin(W_GUARD)
            for kind, v in [("b", 1), ("l", word)] + [("b", x) for x in b]:
                if self.mem.fail:
                    break
                (self.write_byte if kind == "b" else self.write_long)(stream, v)
            done = self.end()
        if done:
            self.saves += 1
            self.depth -= 1
            return
        back = {i: self.own[i] for i, ln in enumerate(LINES) if self.lines & ln[0]}
        self.write_options(back, rebuild=False)
        self.lines = 0
        self.give_ups += 1
        self.arm(SERIALIZE, this, stream)
        self.depth -= 1

    # ---- a scenario
    def run(self):
        for op in self.case["ops"]:
            kind = op[0]
            if kind == "file":
                self.file = self.case["files"][op[1]] if op[1] is not None else None
            elif kind == "ptr":
                A.Memory.write(self.mem, G_CONFIG, 4, op[1])
            elif kind == "poke":
                A.Memory.write(self.mem, op[1], 1, op[2])
            elif kind == "rewind":
                A.Memory.write(self.mem, STREAMS[op[1]][0] + 0x10, 4, 0)
            elif kind == "reset":
                self.hook(RESET, op[1])
            elif kind == "load":
                self.hook(DESERIALIZE, op[1], STREAMS[op[2]][0])
            elif kind == "save":
                self.guard(op[1], STREAMS[op[2]][0])
        return self.result()

    def result(self):
        m = self.mem
        blocks = "".join(bytes(m.read8(b + i) for i in range(0x18)).hex() for b in (CFG_G, CFG_V, CFG_B))
        streams = []
        for s, buf in STREAMS.values():
            streams.append(f"{m.read(s + 0x10, 4):x}" + bytes(m.read8(buf + i) for i in range(0x40)).hex())
        flags = m.read(MAPIMG + 0x1008 + 0x200, 4)
        log = ",".join(f"{a:x}:{n}:{o:x}:{v:x}:{w}" for a, n, o, v, w in m.log) or "-"
        st = (f"{self.lines:x}:{bytes(self.own).hex()}:{bytes(self.applied).hex()}:{self.depth}:{self.calls}:"
              f"{self.applies}:{self.saves}:{self.give_ups}")
        return [",".join(self.ev) or "-", blocks, "/".join(streams), f"{flags:x}", log, st, "0"]


# ------------------------------------------------------------------ cases
def make_case(rng, cid: int, files_dir: str) -> dict:
    mem: dict[int, int] = {}

    def put(a, n, v):
        for i in range(n):
            mem[a + i] = (v >> (8 * i)) & 0xFF

    def fill(a, n):
        for i in range(n):
            mem[a + i] = rng.randrange(256)

    for i in range(-0x2000, 0x100):
        mem[SP + i] = 0
    put(G_CONFIG, 4, 0)
    put(G_MOVIE, 4, MOVIE)
    put(MOVIE, 4, MOVIE_VT)
    put(MOVIE_VT + 0x10, 4, MOVIE_FN)
    put(G_MAPIMAGE, 4, MAPIMG)
    fill(MAPIMG + 0x1008 + 0x1F0, 0x20)
    fill(ITEM, 0x10)
    for b in (CFG_G, CFG_V, CFG_B):
        fill(b, 0x20)
    fill(CFG_U, 0x10)                       # its page only: +0x10 .. +0x16 are on the next page, not mapped
    bad_stream = rng.random() < 0.15
    for name, (s, buf) in STREAMS.items():
        fill(s, 0x20)
        put(s + 0x10, 4, 0)
        if name == "file2" and bad_stream:
            put(s + 4, 4, UNMAPPED_BUF)    # W2 cannot write this save: restore, then the game's Serialize
        else:
            put(s + 4, 4, buf)
            fill(buf, 0x40)
    for name in ("save", "save2"):          # a game save's record: version (0 has one extra byte), word, bytes
        s, buf = STREAMS[name]
        rec = [rng.choice([1, 1, 1, 0, 2])] + [rng.randrange(256) for _ in range(4)]
        for off, num in [(8, 5), (9, 3), (0xA, 3), (0xB, 3), (0xC, 3)]:
            rec.append(rng.randrange(num) if rng.random() < 0.9 else rng.randrange(256))
        if rec[0] == 0:
            rec.append(rng.randrange(256))
        for off, num in [(0xD, 3), (0xE, 3), (0xF, 256), (0x10, 256), (0x11, 256), (0x12, 256), (0x13, 256),
                         (0x14, 3), (0x15, 3), (0x16, 2)]:
            rec.append(rng.randrange(num) if rng.random() < 0.9 else rng.randrange(256))
        for i, v in enumerate(rec):
            mem[buf + i] = v
    # gate settings
    gate = rng.choice(GATES)
    armed = {1: 1, 2: 1, 3: 1}
    listed = {1: 1, 2: 1, 3: 1}
    mode = "readable"
    if gate == "nohook":
        armed[2] = 0
    elif gate == "noguard":
        armed[3] = 0
    elif gate == "nowriter":
        armed[1] = 0
    elif gate == "unlisted_guard":
        listed[3] = 0
    elif gate == "unlisted_hook":
        listed[2] = 0
    elif gate in ("shadow", "capture", "original"):
        mode = gate
    # options files
    files = []
    for k in range(3):
        if rng.random() < 0.6:  # the page's own form with one or more game lines set
            vals = [rng.randrange(PAGE_LAST[j] + 1) if rng.random() < 0.6 else 0 for j in range(4)]
            text = "# FE options. 0 is off, and off is the original game.\n" + "".join(
                f"{PAGE_KEYS[j]} = {vals[j]}\n" for j in range(4))
            files.append(text.encode())
        else:
            files.append(random_file(rng))
    if rng.random() < 0.15:  # only a line with no game value behind it (danger_zone = 2): W1 stores nothing, no session
        files[2] = b"danger_zone = 2" + bytes([10])
    # the steps
    ops = [("file", rng.choice([0, 0, 1, None])), ("reset", CFG_G), ("ptr", CFG_G)]  # boot: Reset, then the pointer
    ops.append(("load", CFG_G, "save"))
    menu = ["screen", "suspend", "suspend", "save", "gamereset", "load2", "file", "nest", "copyload", "stray",
            "unmapped", "unmapped"]
    for _ in range(rng.randrange(2, 7)):
        ops += step(rng, rng.choice(menu))
    if rng.random() < 0.7:
        ops += step(rng, "suspend") + [("save", CFG_G, "file2")]
    paths = []
    for k, data in enumerate(files):
        p = os.path.join(files_dir, f"c{cid:04d}_{k}.txt")
        with open(p, "wb") as fh:
            fh.write(data)
        paths.append(p)
    return {"mem": regions(mem), "gate": {"armed": armed, "listed": listed, "mode": mode}, "files": files,
            "paths": paths, "ops": ops, "map_value": rng.choice([0, 0, 1, 0x08300000]), "gate_name": gate}


def step(rng, what: str) -> list:
    if what == "screen":  # a line changed on the game's own screen (SetValue's store, as the player makes it)
        i = rng.randrange(4)
        return [("poke", CFG_G + LINES[i][3], rng.randrange(LINES[i][4]))]
    if what == "suspend":  # GameBackup::Serialize on a versus copy
        return [("reset", CFG_V), ("reset", CFG_V), ("reset", CFG_V), ("rewind", "mem"), ("save", CFG_G, "mem"),
                ("rewind", "mem"), ("load", CFG_V, "mem"), ("save", CFG_V, "file1")]
    if what == "save":
        return [("save", CFG_G, rng.choice(["file2", "file3"]))]
    if what == "gamereset":
        return [("reset", CFG_G)]
    if what == "load2":
        return [("rewind", "save2"), ("load", CFG_G, "save2")]
    if what == "file":
        return [("file", rng.choice([0, 1, 2, None]))]
    if what == "nest":  # a Serialize whose stream deserializes the global block (depth 1)
        return [("rewind", "nest"), ("rewind", "save2"), ("save", rng.choice([CFG_V, CFG_G]), "nest")]
    if what == "unmapped":  # *G_GameConfig points at a block not wholly in mapped memory (W1/W2's block check)
        call = rng.choice([("reset", CFG_U), ("load", CFG_U, "save2"), ("save", CFG_U, "file3")])
        pre = [("rewind", "save2")] if call[0] == "load" else []
        return pre + [("ptr", CFG_U), call, ("ptr", CFG_G)]
    if what == "copyload":
        return [("rewind", "save"), ("load", CFG_V, "save")]
    return [("reset", CFG_B), ("save", CFG_B, "file3")]  # a block that is neither


def regions(mem: dict) -> list:
    out, start, prev, buf = [], None, None, bytearray()
    for a in sorted(mem):
        if start is None or a != prev + 1:
            if start is not None:
                out.append((start, bytes(buf)))
            start, buf = a, bytearray()
        buf.append(mem[a])
        prev = a
    if start is not None:
        out.append((start, bytes(buf)))
    return out


# ------------------------------------------------------------------ the C side
DRIVER = r'''
/* Generated by src/readable/menu/tests/w12_diff.py: W1/W2 (menu_options_hook.c) through the writer gate on
   made-up scenarios read from stdin. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "menu_writer.h"
#include "fe_options.h"

#ifdef _WIN32
#define putenv _putenv
#endif
static uint8_t **pages, **nopages;
static uint32_t used[4096]; static int nused;
static uint8_t *at(uint32_t a, int make) {
    uint8_t *p = pages[a >> 12];
    if (!p && make && nused < 4096) { p = pages[a >> 12] = calloc(4096, 1); used[nused++] = a >> 12; }
    return p ? p + (a & 0xFFF) : NULL;
}
static uint8_t r8(Context *c, uint32_t a) { (void)c; uint8_t *p = at(a, 0); return p ? *p : 0; }
static uint16_t r16(Context *c, uint32_t a) { return (uint16_t)(r8(c, a) | r8(c, a + 1) << 8); }
static uint32_t r32(Context *c, uint32_t a) { return (uint32_t)r16(c, a) | (uint32_t)r16(c, a + 2) << 16; }
static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; uint8_t *p = at(a, 0); if (p) *p = v; }
static void w16(Context *c, uint32_t a, uint16_t v) { w8(c, a, (uint8_t)v); w8(c, a + 1, (uint8_t)(v >> 8)); }
static void w32(Context *c, uint32_t a, uint32_t v) { w16(c, a, (uint16_t)v); w16(c, a + 2, (uint16_t)(v >> 16)); }
static void interp(Context *c, uint32_t a, uint32_t o) { (void)c; (void)a; (void)o; }
static void svc(Context *c, uint32_t n) { (void)c; (void)n; }

/* generated code's way to load and store: the direct page when there is one, else the host */
static uint32_t g_rd32(Context *c, uint32_t a) {
    uint8_t *p = c->read_pages[a >> 12];
    if (p && (a & 0xFFF) <= 0xFFC) { uint32_t v; memcpy(&v, p + (a & 0xFFF), 4); return v; }
    return c->host->read32(c, a);
}
static uint8_t g_rd8(Context *c, uint32_t a) { uint8_t *p = c->read_pages[a >> 12]; return p ? p[a & 0xFFF] : c->host->read8(c, a); }
static void g_wr32(Context *c, uint32_t a, uint32_t v) {
    uint8_t *p = c->write_pages[a >> 12];
    if (p && (a & 0xFFF) <= 0xFFC) memcpy(p + (a & 0xFFF), &v, 4);
    else c->host->write32(c, a, v);
}
static void g_wr8(Context *c, uint32_t a, uint8_t v) { uint8_t *p = c->write_pages[a >> 12]; if (p) p[a & 0xFFF] = v; else c->host->write8(c, a, v); }

static char ev[1 << 16]; static size_t nev;
static void evt(const char *fmt, uint32_t a, uint32_t b) {
    if (nev + 64 >= sizeof ev) return;
    if (nev) ev[nev++] = ',';
    nev += (size_t)snprintf(ev + nev, sizeof ev - nev, fmt, a, b);
}
static uint32_t map_value;
#define CFG_G 0x08100000u
#define NEST_S @NEST@u
#define SAVE2_S @SAVE2@u
void fx_deserialize(Context *ctx);
static uint32_t st_pos(Context *c, uint32_t s) {
    uint32_t pos = g_rd32(c, s + 0x10u), buf = g_rd32(c, s + 4u);
    g_wr32(c, s + 0x10u, pos + 1u);
    return buf + pos;
}
static void ret(Context *c) { c->r[15] = c->r[14] & ~3u; }
static void s_read_byte(Context *c) { evt("rb:%x", c->r[0], 0); uint32_t a = st_pos(c, c->r[0]); c->r[0] = g_rd8(c, a); ret(c); }
static void s_read_long(Context *c) {
    evt("rl:%x", c->r[0], 0);
    uint32_t s = c->r[0], v = 0;
    for (int i = 0; i < 4; i++) v |= (uint32_t)g_rd8(c, st_pos(c, s)) << (8 * i);
    c->r[0] = v; ret(c);
}
static void s_write_byte(Context *c) {
    uint32_t s = c->r[0], v = c->r[1];
    evt("wb:%x:%x", s, v & 0xFFu);
    if (s == NEST_S && g_rd32(c, s + 0x10u) == 0 && !fe_writer_open()) {
        FeState keep; fe_save(c, &keep);
        evt("nest", 0, 0);
        c->r[0] = CFG_G; c->r[1] = SAVE2_S; c->r[14] = 0x00123450u;
        config_options_hook(c, fx_deserialize);
        fe_load(c, &keep, 0);
    }
    g_wr8(c, st_pos(c, s), (uint8_t)v);
    ret(c);
}
static void s_write_long(Context *c) {
    uint32_t s = c->r[0], v = c->r[1];
    evt("wl:%x:%x", s, v);
    for (int i = 0; i < 4; i++) g_wr8(c, st_pos(c, s), (uint8_t)(v >> (8 * i)));
    ret(c);
}
static void s_bgm(Context *c) { evt("bgm:%x", c->r[0], 0); ret(c); }
static void s_se(Context *c) { evt("se:%x", c->r[0], 0); ret(c); }
static void s_sys(Context *c) { evt("sys:%x", c->r[0], 0); ret(c); }
static void s_voice(Context *c) { evt("voice:%x", c->r[0], 0); ret(c); }
static void s_movie(Context *c) { evt("movie:%x", c->r[0], 0); ret(c); }
static void s_sub(Context *c) { evt("sub:%x", c->r[0], 0); ret(c); }
static void s_map_get(Context *c) { evt("mapget", 0, 0); c->r[0] = map_value; ret(c); }
static void s_update(Context *c) {
    evt("upd:%x", c->r[0], 0);
    uint32_t a = c->r[0] + 0x200u;
    g_wr32(c, a, g_rd32(c, a) | 2u);
    ret(c);
}
static Code lookup(Context *c, uint32_t a) {
    (void)c;
    switch (a) {
    case @READ_BYTE@u: return s_read_byte;
    case @READ_LONG@u: return s_read_long;
    case @WRITE_BYTE@u: return s_write_byte;
    case @WRITE_LONG@u: return s_write_long;
    case @BGM@u: return s_bgm;
    case @SE@u: return s_se;
    case @SYS@u: return s_sys;
    case @VOICE@u: return s_voice;
    case @MOVIE_FN@u: return s_movie;
    case @SHOW_SUB@u: return s_sub;
    case @MAP_GET@u: return s_map_get;
    case @UPDATE@u: return s_update;
    default: return NULL;
    }
}
void fe_stub_original(Context *ctx) { ctx->r[0] = 0xDEADBEEFu; ctx->r[15] = ctx->r[14] & ~3u; }

/* ---- the game's three functions (fixtures; the hooks-off cases compare them with the ARM code) */
static void fx_reset(Context *ctx) {
    uint32_t self = ctx->r[0], lr = ctx->r[14];
    static const uint8_t v[] = {1, 0, 0, 1, 2, 0, 0, 0x80};
    g_wr32(ctx, self + 4u, 0x00011E5Eu);
    for (uint32_t k = 0; k < 8; k++) g_wr8(ctx, self + 8u + k, v[k]);
    static const uint32_t snd[4] = {@BGM@u, @SE@u, @SYS@u, @VOICE@u};
    for (uint32_t k = 0; k < 4; k++) { g_wr8(ctx, self + 0x10u + k, 0xFF); (void)guest_call(ctx, snd[k], 0xFFu, 0, 0, 0); }
    g_wr8(ctx, self + 0x14u, 0); g_wr8(ctx, self + 0x15u, 0); g_wr8(ctx, self + 0x16u, 1);
    uint32_t movie = g_rd32(ctx, @G_MOVIE@u);
    (void)guest_call(ctx, g_rd32(ctx, g_rd32(ctx, movie) + 0x10u), movie, 0, 0, 0);
    ctx->r[15] = lr & ~3u;
}
void fx_deserialize(Context *ctx) {
    uint32_t self = ctx->r[0], s = ctx->r[1], lr = ctx->r[14];
    uint32_t ver = guest_call(ctx, @READ_BYTE@u, s, 0, 0, 0);
    g_wr32(ctx, self + 4u, guest_call(ctx, @READ_LONG@u, s, 0, 0, 0));
    for (uint32_t k = 8; k <= 0xC; k++) g_wr8(ctx, self + k, (uint8_t)guest_call(ctx, @READ_BYTE@u, s, 0, 0, 0));
    if ((int32_t)ver < 1) (void)guest_call(ctx, @READ_BYTE@u, s, 0, 0, 0);
    for (uint32_t k = 0xD; k <= 0xF; k++) g_wr8(ctx, self + k, (uint8_t)guest_call(ctx, @READ_BYTE@u, s, 0, 0, 0));
    static const uint32_t snd[4] = {@BGM@u, @SE@u, @SYS@u, @VOICE@u};
    for (uint32_t k = 0; k < 4; k++) {
        uint32_t b = guest_call(ctx, @READ_BYTE@u, s, 0, 0, 0);
        g_wr8(ctx, self + 0x10u + k, (uint8_t)b);
        (void)guest_call(ctx, snd[k], b, 0, 0, 0);
    }
    g_wr8(ctx, self + 0x14u, (uint8_t)guest_call(ctx, @READ_BYTE@u, s, 0, 0, 0));
    uint32_t movie = g_rd32(ctx, @G_MOVIE@u);
    (void)guest_call(ctx, g_rd32(ctx, g_rd32(ctx, movie) + 0x10u), movie, 0, 0, 0);
    g_wr8(ctx, self + 0x15u, (uint8_t)guest_call(ctx, @READ_BYTE@u, s, 0, 0, 0));
    g_wr8(ctx, self + 0x16u, (uint8_t)guest_call(ctx, @READ_BYTE@u, s, 0, 0, 0));
    (void)guest_call(ctx, @SHOW_SUB@u, (g_rd32(ctx, self + 4u) & 0x10000u) ? 1u : 0u, 0, 0, 0);
    ctx->r[15] = lr & ~3u;
}
static void fx_serialize(Context *ctx) {
    uint32_t self = ctx->r[0], s = ctx->r[1], lr = ctx->r[14];
    (void)guest_call(ctx, @WRITE_BYTE@u, s, 1, 0, 0);
    (void)guest_call(ctx, @WRITE_LONG@u, s, g_rd32(ctx, self + 4u), 0, 0);
    for (uint32_t k = 8; k <= 0x16; k++) (void)guest_call(ctx, @WRITE_BYTE@u, s, g_rd8(ctx, self + k), 0, 0);
    ctx->r[15] = lr & ~3u;
}

static const Host host = {r8, r16, r32, w8, w16, w32, interp, lookup, svc};
static uint32_t vfp[32], fpscr;
static int hexval(int ch) { return ch <= '9' ? ch - '0' : (ch | 32) - 'a' + 10; }
static char paths[3][1024];

int main(void) {
    pages = calloc(1u << 20, sizeof *pages);
    nopages = calloc(1u << 20, sizeof *nopages);
    static char line[1 << 16];
    unsigned id = 0, armed = 0, listed = 0; char mode[32] = "readable";
    Context c; memset(&c, 0, sizeof c);
    while (fgets(line, sizeof line, stdin)) {
        line[strcspn(line, "\r\n")] = 0;
        if (!strncmp(line, "case ", 5)) {
            sscanf(line + 5, "%u %x %x %31s %x", &id, &armed, &listed, mode, &map_value);
            for (int i = 0; i < nused; i++) { free(pages[used[i]]); pages[used[i]] = NULL; }
            nused = 0; nev = 0; ev[0] = 0;
            fe_writer_test_reset_all();
            memset(&c, 0, sizeof c);
            c.read_pages = nopages; c.write_pages = pages; c.vfp = vfp; c.fpscr = &fpscr; c.host = &host;
            c.r[14] = 0x00123450u; c.r[13] = 0x0FFFF000u; c.budget = 1000;
            fe_force_mode(!strcmp(mode, "shadow") ? FE_MODE_SHADOW : !strcmp(mode, "capture") ? FE_MODE_CAPTURE
                          : !strcmp(mode, "original") ? FE_MODE_ORIGINAL : FE_MODE_READABLE);
            setup_gate(armed, listed);
            putenv((char *)"FE_OPTIONS="); putenv((char *)"FEF_OPTIONS=");
        } else if (!strncmp(line, "path ", 5)) {
            int k = line[5] - '0';
            snprintf(paths[k], sizeof paths[k], "%s", line + 7);
        } else if (!strncmp(line, "mem ", 4)) {
            uint32_t addr; int off = 0;
            sscanf(line + 4, "%x %n", &addr, &off);
            const char *h = line + 4 + off;
            for (uint32_t i = 0; h[2 * i]; i++) *at(addr + i, 1) = (uint8_t)(hexval(h[2 * i]) << 4 | hexval(h[2 * i + 1]));
        } else if (!strncmp(line, "op ", 3)) {
            char kind[16]; uint32_t a = 0, b = 0;
            sscanf(line + 3, "%15s %x %x", kind, &a, &b);
            if (!strcmp(kind, "file")) {
                static char env1[1100], env2[1100];
                if (a == 0xFFu) { putenv((char *)"FE_OPTIONS="); putenv((char *)"FEF_OPTIONS="); }
                else if (b) { snprintf(env2, sizeof env2, "FEF_OPTIONS=%s", paths[a]); putenv((char *)"FE_OPTIONS="); putenv(env2); }
                else { snprintf(env1, sizeof env1, "FE_OPTIONS=%s", paths[a]); putenv(env1); }
            } else if (!strcmp(kind, "ptr")) { uint8_t *p = at(@G_CONFIG@u, 0); if (p) memcpy(p, &a, 4); }
            else if (!strcmp(kind, "poke")) { uint8_t *p = at(a, 0); if (p) *p = (uint8_t)b; }
            else if (!strcmp(kind, "rewind")) { uint8_t *p = at(a + 0x10u, 0); if (p) memset(p, 0, 4); }
            else {
                c.r[0] = a; c.r[1] = b; c.r[14] = 0x00123450u; c.exit = EXIT_NONE;
                if (!strcmp(kind, "reset")) config_options_hook(&c, fx_reset);
                else if (!strcmp(kind, "load")) config_options_hook(&c, fx_deserialize);
                else config_serialize_guard(&c, fx_serialize);
                if (c.r[15] != 0x00123450u) evt("badreturn:%x", c.r[15], 0);
                if (c.exit != EXIT_NONE) evt("exit:%x", (uint32_t)c.exit, 0);
                if (fe_writer_open()) evt("open", 0, 0);
            }
        } else if (!strncmp(line, "end", 3)) {
            printf("%u %s ", id, nev ? ev : "-");
            static const uint32_t blocks[3] = {CFG_G, 0x08100100u, 0x08100200u};
            for (int k = 0; k < 3; k++) for (uint32_t i = 0; i < 0x18; i++) { uint8_t *p = at(blocks[k] + i, 0); printf("%02x", p ? *p : 0); }
            printf(" ");
            for (int k = 0; k < @NSTREAMS@; k++) {
                uint32_t s = 0x08110000u + 0x40u * (uint32_t)k, buf = 0x08120000u + 0x100u * (uint32_t)k;
                printf("%s%x", k ? "/" : "", r32(&c, s + 0x10u));
                for (uint32_t i = 0; i < 0x40; i++) printf("%02x", r8(&c, buf + i));
            }
            printf(" %x ", r32(&c, 0x08200000u + 0x1008u + 0x200u));
            uint32_t n = fe_writer_log_count();
            if (!n) printf("-");
            for (uint32_t i = 0; i < n; i++) {
                FeWriterEntry e; fe_writer_log_entry(i, &e);
                printf("%s%x:%u:%x:%x:%u", i ? "," : "", e.address, e.size, e.old_value, e.new_value, e.writer);
            }
            ConfigOptionsState s; config_options_state(&s);
            printf(" %x:", s.lines);
            for (int i = 0; i < 4; i++) printf("%02x", s.own[i]);
            printf(":");
            for (int i = 0; i < 4; i++) printf("%02x", s.applied[i]);
            printf(":%u:%u:%u:%u:%u %u %u\n", s.depth, s.calls, s.applies, s.saves, s.give_ups, fe_writer_stray_stores(),
                   fe_writer_totals[FE_WT_SESSIONS]);
        } else if (!strncmp(line, "parse ", 6)) {
            FeOptions o; fe_options_read_path(line + 6, &o);
            printf("parse %u %u %u %u\n", o.line[0], o.line[1], o.line[2], o.line[3]);
        }
    }
    return 0;
}
'''

# the gate setup: with FE_WRITER_TESTS the test arms and lists; without it (the "const" pass) the table is the
# library's (every entry 0) and FE_WRITERS comes from the environment
GATE_TESTS = r'''
static void fe_writer_test_reset_all(void) { fe_writer_test_reset(); config_options_test_reset(); }
static void setup_gate(unsigned armed, unsigned listed) {
    static const char *names[4] = {"", "config_options", "config_options_hook", "config_save_guard"};
    char list[256] = "other";
    for (int w = 1; w <= 3; w++) {
        fe_writer_test_arm(w, (int)((armed >> w) & 1u));
        if ((listed >> w) & 1u) { strcat(list, ","); strcat(list, names[w]); }
    }
    fe_writer_test_switches(list);
}
'''
GATE_CONST = r'''
static void fe_writer_test_reset_all(void) { }
static void setup_gate(unsigned armed, unsigned listed) { (void)armed; (void)listed; }
'''


def driver_text(const: bool) -> str:
    t = DRIVER.replace('#include "fe_options.h"\n', '#include "fe_options.h"\n' + (GATE_CONST if const else GATE_TESTS))
    subst = {"NEST": STREAMS["nest"][0], "SAVE2": STREAMS["save2"][0], "READ_BYTE": READ_BYTE, "READ_LONG": READ_LONG,
             "WRITE_BYTE": WRITE_BYTE, "WRITE_LONG": WRITE_LONG, "BGM": 0x0041F5F4, "SE": 0x0041F49C,
             "SYS": 0x0041F880, "VOICE": 0x0041F938, "MOVIE_FN": MOVIE_FN, "SHOW_SUB": SHOW_SUB, "MAP_GET": MAP_GET,
             "UPDATE": UPDATE, "G_MOVIE": G_MOVIE, "G_CONFIG": G_CONFIG}
    for k, v in subst.items():
        t = t.replace(f"@{k}@", f"0x{v:08X}")
    return t.replace("@NSTREAMS@", str(len(STREAMS)))


def build_driver(cc: str, out: str, menu_dir: str, core_dir: str, const: bool = False) -> str:
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "w12_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text(const))
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        p = os.path.normcase(os.path.abspath(dp))
        if p.startswith(os.path.normcase(SRC_MENU)) or p.startswith(os.path.normcase(SRC_CORE)):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(menu_dir, f) for f in os.listdir(menu_dir) if f.endswith(".c")]
    sources += [os.path.join(core_dir, f) for f in os.listdir(core_dir) if f.endswith(".c")]
    exe = os.path.join(out, "w12_driver.exe" if os.name == "nt" else "w12_driver")
    inc = ["-I", menu_dir, "-I", core_dir, "-I", os.path.join(ROOT, "src", "readable", "unit"),
           "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    flags = [] if const else ["-DFE_WRITER_TESTS"]
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-Wno-format-truncation", "-O1", "-fwrapv"] + flags + inc \
        + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"w12_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


def case_lines(cid: int, case: dict) -> list[str]:
    g = case["gate"]
    armed = sum(g["armed"][w] << w for w in (1, 2, 3))
    listed = sum(g["listed"][w] << w for w in (1, 2, 3))
    out = [f"case {cid} {armed:x} {listed:x} {g['mode']} {case['map_value']:x}"]
    out += [f"path {k} {p}" for k, p in enumerate(case["paths"])]
    for addr, data in case["mem"]:
        for off in range(0, len(data), 2048):
            out.append(f"mem {addr + off:x} {data[off:off + 2048].hex()}")
    for op in case["ops"]:
        k = op[0]
        if k == "file":
            out.append("op file ff 0" if op[1] is None else f"op file {op[1]:x} {int(case['fef'][op[1]])}")
        elif k == "ptr":
            out.append(f"op ptr {op[1]:x} 0")
        elif k == "poke":
            out.append(f"op poke {op[1]:x} {op[2]:x}")
        elif k == "rewind":
            out.append(f"op rewind {STREAMS[op[1]][0]:x} 0")
        elif k == "reset":
            out.append(f"op reset {op[1]:x} 0")
        elif k == "load":
            out.append(f"op load {op[1]:x} {STREAMS[op[2]][0]:x}")
        else:
            out.append(f"op save {op[1]:x} {STREAMS[op[2]][0]:x}")
    out.append("end")
    return out


def make_cases(text: bytes, n: int, seed: int, files_dir: str, const: bool = False):
    rng = random.Random(seed)
    os.makedirs(files_dir, exist_ok=True)
    lines, expected, kinds = [], {}, {}
    for cid in range(n):
        case = make_case(rng, cid, files_dir)
        case["fef"] = [rng.random() < 0.2 for _ in case["files"]]  # read through FEF_OPTIONS instead
        if const:  # the library's table: every entry 0, whatever the case asked
            case["gate"] = {"armed": {1: 0, 2: 0, 3: 0}, "listed": {1: 1, 2: 1, 3: 1}, "mode": "readable"}
        ref = Ref(text, case)
        try:
            want = ref.run()
        except A.Unsupported as e:
            raise SystemExit(f"w12_diff: the ARM side cannot run case {cid}: {e}")
        want.append("0" if not any(ref.on.values()) else "ANY")
        expected[cid] = want
        kinds[cid] = case["gate_name"] if not const else "const"
        lines += case_lines(cid, case)
    return lines, expected, kinds


def compare(exe: str, cc: str, lines: list[str], expected: dict, kinds: dict, show: int, quiet: bool = False,
            env_extra: dict | None = None):
    env = dict(os.environ, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""),
               FE_READABLE_LOG=os.path.join(os.path.dirname(exe), "fe_readable.log"))
    for k in ("FE_WRITERS", "FE_OPTIONS", "FEF_OPTIONS"):
        env.pop(k, None)
    env.update(env_extra or {})
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"w12_diff: the C driver failed ({r.returncode}):\n{r.stderr[-2000:]}")
    got = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if parts and parts[0].isdigit():
            got[int(parts[0])] = parts[1:]
    per: dict[str, list[int]] = {}
    names = ["calls", "blocks", "streams", "danger flags", "gate log", "W1/W2 record", "stray stores", "sessions"]
    for c, want in expected.items():
        key = "on" if kinds[c] == "on" else kinds[c] if kinds[c] == "const" else "off"
        res = per.setdefault(key, [0, 0])
        res[0] += 1
        g = got.get(c)
        bad = []
        if g is None or len(g) != len(want):
            bad = ["output"]
        else:
            for name, w, x in zip(names, want, g):
                if w == "ANY":
                    continue
                if w != x:
                    bad.append(name)
        if bad:
            res[1] += 1
            if res[1] <= show and not quiet:
                print(f"  MISMATCH case {c} ({kinds[c]}): {', '.join(bad)}")
                if g is not None and len(g) == len(want):
                    for name, w, x in zip(names, want, g):
                        if w != x and w != "ANY":
                            print(f"    {name}:\n      original {w[:400]}\n      readable {x[:400]}")
    return per


# ------------------------------------------------------------------ the options file lines
def options_check(cc: str, exe: str, n_random: int, seed: int) -> tuple[int, int, list[str]]:
    """The shared test lines, then random files; C reader vs the expected values and vs the Python copy of the page's
    parse. Returns (checked, bad, messages)."""
    d = os.path.join(OUT, "options")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    with open(CASES_JSON, encoding="utf-8") as fh:
        shared = json.load(fh)["cases"]
    items = []  # (label, data, expected or None, path override)
    for i, c in enumerate(shared):
        data = c["text"].encode("utf-8") if "text" in c else bytes.fromhex(c["hex"])
        items.append((f"shared {i} ({c.get('why', '')})", data, c["expect"]))
    rng = random.Random(seed)
    for i in range(n_random):
        items.append((f"random {i}", random_file(rng), None))
    big = ("danger_zone = 1\n" + "#" * 65536).encode()
    items.append(("over 64 KB", big, [0, 0, 0, 0]))
    items.append(("exactly 64 KB", ("danger_zone = 1\n" + "#" * (65536 - 16)).encode(), [1, 0, 0, 0]))
    lines, want, msgs = [], [], []
    for k, (label, data, exp) in enumerate(items):
        p = os.path.join(d, f"o{k:05d}.txt")
        with open(p, "wb") as fh:
            fh.write(data)
        lines.append(f"parse {p}")
        model = file_parse(data)
        if exp is not None and model != exp:
            msgs.append(f"  the Python copy of the page's parse disagrees with the shared line {label}: {model} vs {exp}")
        want.append((label, exp if exp is not None else model))
    # a missing file and a file inside %APPDATA% / %LOCALAPPDATA% (fake folders below build/: the real ones are never read)
    fake_app = os.path.join(d, "AppData", "Roaming")
    fake_local = os.path.join(d, "AppData", "Local")
    for f in (fake_app, fake_local):
        os.makedirs(os.path.join(f, "Zakuro"), exist_ok=True)
        with open(os.path.join(f, "Zakuro", "fe14-options.txt"), "w") as fh:
            fh.write("danger_zone = 1\nanim_speed = 2\n")
    for label, p in (("missing file", os.path.join(d, "none.txt")),
                     ("inside APPDATA", os.path.join(fake_app, "Zakuro", "fe14-options.txt")),
                     ("inside APPDATA, other slashes and case", os.path.join(fake_app, "Zakuro", "fe14-options.txt")
                      .replace("\\", "/").upper()),
                     ("inside LOCALAPPDATA", os.path.join(fake_local, "Zakuro", "fe14-options.txt"))):
        lines.append(f"parse {p}")
        want.append((label, [0, 0, 0, 0]))
    env = dict(os.environ, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""),
               APPDATA=fake_app, LOCALAPPDATA=fake_local)
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    got = [ln.split()[1:] for ln in r.stdout.split("\n") if ln.startswith("parse ")]
    bad = 0
    for (label, w), g in zip(want, got):
        if [int(x) for x in g] != w:
            bad += 1
            if bad <= 5:
                msgs.append(f"  options MISMATCH {label}: expected {w}, the reader gave {g}")
    if len(got) != len(want):
        bad += 1
        msgs.append(f"  options: {len(got)} answers for {len(want)} files")
    return len(want), bad, msgs


# ------------------------------------------------------------------ clean saves against the game's code alone
# Section 7's host-tests row: the made-up suspend save followed by a game save, "both outputs equal to the game's
# with no options". The cases above compare the C with the section 4 model; these compare every stream the C
# writes with the same steps run by the game's own code with NO options file (the model is not used), on
# scenarios where the known limits of section 5 cannot happen: nothing is changed on the game's screen and no
# Deserialize runs inside a Serialize after the apply.
CLEAN_STEPS = ["suspend", "suspend", "save", "gamereset", "load2", "copyload", "stray"]
CLEAN_CID0 = 90000


def make_clean_cases(text: bytes, n: int, seed: int, files_dir: str):
    rng = random.Random(seed ^ 0xC1EA)
    os.makedirs(files_dir, exist_ok=True)
    lines, expected, noopt, applied, suspends = [], {}, {}, 0, 0
    for cid in range(CLEAN_CID0, CLEAN_CID0 + n):
        case = make_case(rng, cid, files_dir)
        vals = [0, 0, 0, 0]
        while not any(vals):  # at least one game line set on the page
            vals = [rng.randrange(PAGE_LAST[j] + 1) for j in range(4)]
        data = ("# FE options. 0 is off, and off is the original game.\n"
                + "".join(f"{PAGE_KEYS[j]} = {vals[j]}\n" for j in range(4))).encode()
        case["files"][0] = data
        with open(case["paths"][0], "wb") as fh:
            fh.write(data)
        case["fef"] = [rng.random() < 0.2 for _ in case["files"]]
        case["gate"] = {"armed": {1: 1, 2: 1, 3: 1}, "listed": {1: 1, 2: 1, 3: 1}, "mode": "readable"}
        case["gate_name"] = "clean"
        ops = [("file", 0), ("reset", CFG_G), ("ptr", CFG_G), ("load", CFG_G, "save")]
        for _ in range(rng.randrange(1, 5)):
            ops += step(rng, rng.choice(CLEAN_STEPS))
        ops += step(rng, "suspend") + [("save", CFG_G, "file2")]  # the suspend save, then a game save
        case["ops"] = ops
        ref = Ref(text, case)
        want = ref.run()
        want.append("ANY")
        applied += ref.applies > 0
        suspends += sum(1 for op in ops if op[0] == "save" and op[2] == "mem")
        base = dict(case, ops=[("file", None) if op[0] == "file" else op for op in ops])
        nref = Ref(text, base)  # the same steps, no options file: the game's own functions only
        noopt[cid] = nref.run()[2]
        expected[cid] = want
        lines += case_lines(cid, case)
    return lines, expected, noopt, applied, suspends


def clean_check(exe: str, cc: str, lines: list[str], expected: dict, noopt: dict, show: int = 0,
                quiet: bool = False) -> tuple[int, int]:
    """(C streams that differ from the game's no-options saves, cases where the full record differs from the model)"""
    env = dict(os.environ, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""),
               FE_READABLE_LOG=os.path.join(os.path.dirname(exe), "fe_readable_clean.log"))
    for k in ("FE_WRITERS", "FE_OPTIONS", "FEF_OPTIONS"):
        env.pop(k, None)
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"w12_diff: the C driver failed ({r.returncode}):\n{r.stderr[-2000:]}")
    got = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if parts and parts[0].isdigit():
            got[int(parts[0])] = parts[1:]
    dirty = model = 0
    for c, want in expected.items():
        g = got.get(c)
        if g is None or len(g) != len(want) or g[2] != noopt[c]:
            dirty += 1
            if dirty <= show and not quiet:
                print(f"  CLEAN-SAVE MISMATCH case {c}: a save differs from the game's own with no options file")
                if g is not None and len(g) > 2:
                    print(f"    no options {noopt[c][:400]}\n    readable   {g[2][:400]}")
            continue
        if any(w != "ANY" and w != x for w, x in zip(want, g)):
            model += 1
            if model <= show and not quiet:
                print(f"  MISMATCH clean case {c}: the record differs from section 4's model")
    return dirty, model


# ------------------------------------------------------------------ planted bugs (section 7's list first)
HOOK = "menu_options_hook.c"
PLANTS = [
    # wrong byte: the danger line's byte +0xE taken as +0xF (own[] read and W2's substitution)
    ("menu", HOOK, "{MN_SET_DANGER, 0xEu, FE_OPT_DANGER_ZONE", "{MN_SET_DANGER, 0xFu, FE_OPT_DANGER_ZONE", "wrong byte"),
    # wrong mapping: HP bars "shown" and "hidden" swapped; anim_speed 3 -> 2 instead of 0
    ("menu", HOOK, "{MN_SET_HP_GAUGE, 0x16u, FE_OPT_HP_BARS, {0, 1, 0, 0}}", "{MN_SET_HP_GAUGE, 0x16u, FE_OPT_HP_BARS, {0, 0, 1, 0}}", "wrong mapping"),
    ("menu", HOOK, "{MN_SET_GAME_SPEED, 0xCu, FE_OPT_ANIM_SPEED, {0, 1, 2, 0}}", "{MN_SET_GAME_SPEED, 0xCu, FE_OPT_ANIM_SPEED, {0, 1, 2, 2}}", "wrong mapping"),
    # a store when the value is 0: a page line at 0 is set too
    ("menu", HOOK, "        if (page == 0 || mn_opt_lines[i].to_byte", "        if (mn_opt_lines[i].to_byte", "store for 0"),
    # W2's own/applied swap
    ("menu", HOOK, "            *b = mn_opt.own[i]; /* the PC value", "            *b = mn_opt.applied[i]; /* the PC value", "own/applied swap"),
    ("menu", HOOK, "        if (*b == mn_opt.applied[i])", "        if (*b == mn_opt.own[i])", "own/applied swap"),
    # a store outside a gate session: W1 stores with the setters directly; W2 writes the stream with plain guest calls
    ("menu", HOOK, "    if (config_apply_options(ctx, &want) != FE_WRITER_OK)\n        return;",
     "    if (want.lines & MN_SET_DANGER)\n        (void)config_set_danger(ctx, want.danger);\n    if (0)\n        return;",
     "store outside a session"),
    ("menu", HOOK, "        (void)fe_writer_call(ctx, MN_StreamWriteLong, stream, word, 0u, 0u);",
     "        (void)guest_call(ctx, MN_StreamWriteLong, stream, word, 0u, 0u);", "store outside a session"),
    # W1 without W2
    ("menu", HOOK, "    if (!fe_writer_switched_on(FE_WRITER_CONFIG_SAVE_GUARD))\n        return; /* never W1 without W2 */\n", "",
     "W1 without W2"),
    # the block check removed from W1 / from W2
    ("menu", HOOK, "mn_opt.depth == 0 && mn_is_global(ctx, self);", "mn_opt.depth == 0 && self != 0;", "W1 block check"),
    ("menu", HOOK, "    if (mn_opt.lines == 0 || !mn_is_global(ctx, self)) {", "    if (mn_opt.lines == 0 || self == 0) {", "W2 block check"),
    # the Serialize depth check removed (W1 side), and W2 no longer counting
    ("menu", HOOK, "FE_WRITER_CONFIG_OPTIONS_HOOK) && mn_opt.depth == 0 &&", "FE_WRITER_CONFIG_OPTIONS_HOOK) &&", "depth check"),
    ("menu", HOOK, "    gaddr self = ctx->r[0], stream = ctx->r[1];\n    mn_opt.depth++;", "    gaddr self = ctx->r[0], stream = ctx->r[1];", "depth count"),
    # more: the record of the last apply not cleared at a load; own[] not updated after a change on the game's screen
    ("menu", HOOK, "    mn_opt.lines = 0; /* the block holds the save's", "    /* mn_opt.lines kept */ /* the block holds the save's", "stale record"),
    ("menu", HOOK, "            mn_opt.own[i] = *b; /* changed on the game's own screen", "            (void)0; /* changed on the game's own screen", "own not updated"),
    # W2: no restore before the game's Serialize when it could not write; the PC choice kept after a give-up
    ("menu", HOOK, "    (void)config_restore_options(ctx, &back); /* refused too", "    (void)back; /* refused too", "no restore"),
    ("menu", HOOK, "    mn_opt.lines = 0; /* the PC choice is dropped", "    /* kept */ /* the PC choice is dropped", "choice kept"),
    # W2: the version byte and the word in the wrong order; one byte left out
    ("menu", HOOK, "        (void)fe_writer_call(ctx, MN_StreamWriteByte, stream, 1u, 0u, 0u); /* the record's version */\n        (void)fe_writer_call(ctx, MN_StreamWriteLong, stream, word, 0u, 0u);",
     "        (void)fe_writer_call(ctx, MN_StreamWriteLong, stream, word, 0u, 0u);\n        (void)fe_writer_call(ctx, MN_StreamWriteByte, stream, 1u, 0u, 0u);", "record order"),
    ("menu", HOOK, "        for (uint32_t k = 0; k < 15; k++)\n            (void)fe_writer_call", "        for (uint32_t k = 0; k < 14; k++)\n            (void)fe_writer_call", "byte left out"),
    # W1 applying before the game's function (the game then overwrites, or the record is wrong)
    ("menu", HOOK, "    mn_call_original(ctx, original); /* step 1: the game's Reset / Deserialize */\n    if (!apply || fe_gave_up(ctx))\n        return;",
     "    if (!apply) { mn_call_original(ctx, original); return; }", "W1 before the original"),
    # the options file: first of two equal keys wins; a value one past the line's last accepted; '+' refused
    ("core", "options.c", "                out->line[k] = (uint8_t)(v < 0 ? 0 : v); /* the last line wins, a bad one too */",
     "                if (!out->line[k]) out->line[k] = (uint8_t)(v < 0 ? 0 : v);", "parse: first wins"),
    ("core", "options.c", "    return value <= last ? (int)value : -1;", "    return value <= last + 1u ? (int)value : -1;", "parse: range"),
    ("core", "options.c", "    if (b < e && s[b] == '+' && e - b > 1)\n        b++;\n", "", "parse: plus sign"),
    ("core", "options.c", "        return 0; /* never read there", "        (void)0; /* never read there", "parse: APPDATA"),
    ("core", "options.c", "    if (bad || n > FE_OPTIONS_MAX_BYTES)", "    if (bad)", "parse: size limit"),
    # round 38 (OK A findings): the danger zone's page value 2 stored as game byte 1 (T3: no byte hides the zone);
    # W2's give-up restore rebuilding the zone inside a save (T6), from the hook and from the writer; the
    # block-in-mapped-memory check removed (the gap round 35's review found); the gate asked when the file sets
    # only lines with no game value behind them
    ("menu", HOOK, "{0, 0, MN_NOT_OFFERED, 0}}", "{0, 0, 1, 0}}", "danger 2 stored"),
    ("menu", HOOK, "(void)config_restore_options(ctx, &back);", "(void)config_write_options(ctx, &back);",
     "restore rebuilds the zone"),
    ("menu", "menu_config_writer.c", "rebuild ? config_set_danger : config_store_danger", "config_set_danger",
     "restore rebuilds the zone (writer)"),
    ("menu", "menu_config_writer.c", "        last[0] = last[1] = last[2] = last[3] = 0xFFu;", "        (void)0;",
     "restore refuses the save's own byte"),
    ("menu", HOOK, "return self == guest_ptr(ctx, G_GameConfig) && mn_block_mapped(ctx, self);",
     "return self == guest_ptr(ctx, G_GameConfig);", "block-mapped check removed"),
    ("menu", HOOK, "    if (want.lines == 0)\n        return; /* only lines", "    if (0)\n        return; /* only lines",
     "gate asked for nothing"),
    # round 40 (OK A T2, danger 2 -> 0): W1's apply rebuilding the zone inside the load (the game rebuilds it
    # itself after the load; the rebuild while the map was being set up changed the map start's heap), from the
    # hook and from the writer
    ("menu", HOOK, "    if (config_apply_options(ctx, &want) != FE_WRITER_OK)", "    if (config_write_options(ctx, &want) != FE_WRITER_OK)",
     "apply rebuilds the zone"),
    ("menu", "menu_config_writer.c", "{ return mn_write_lines(ctx, want, 0, 0); }", "{ return mn_write_lines(ctx, want, 1, 0); }",
     "apply rebuilds the zone (writer)"),
    # the gate: the hook's own entry not checked (an unarmed W1 would read and apply)
    ("core", "writer.c", "    if (!fe_writer_table[writer].armed)\n        return 0;\n", "", "gate: armed ignored"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    files_dir = os.path.join(OUT, "plant_files")
    shutil.rmtree(files_dir, ignore_errors=True)
    lines, expected, kinds = make_cases(text, n, seed, files_dir)
    clines, cexp, cnoopt, _ca, _cs = make_clean_cases(text, max(n // 2, 50), seed, os.path.join(OUT, "plant_clean"))
    missed = 0
    for i, (folder, fname, old, new, what) in enumerate(PLANTS, 1):
        base = os.path.join(OUT, "plant", "src")
        shutil.rmtree(base, ignore_errors=True)
        menu_dir, core_dir = os.path.join(base, "menu"), os.path.join(base, "core")
        shutil.copytree(SRC_MENU, menu_dir, ignore=shutil.ignore_patterns("tests"))
        shutil.copytree(SRC_CORE, core_dir, ignore=shutil.ignore_patterns("tests"))
        path = os.path.join(menu_dir if folder == "menu" else core_dir, fname)
        body = open(path, encoding="utf-8").read()
        if body.count(old) != 1:
            print(f"  planted bug {i}: its text occurs {body.count(old)} times in {fname} (the list is stale)")
            missed += 1
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body.replace(old, new))
        try:
            exe = build_driver(cc, os.path.join(OUT, "plant", f"p{i:02d}"), menu_dir, core_dir)
        except SystemExit as e:
            print(f"  planted bug {i:2d} ({what}): caught, it does not compile ({str(e).splitlines()[-1][:80]})")
            continue
        bad, hit = 0, []
        try:
            per = compare(exe, cc, lines, expected, kinds, 0, quiet=True)
            bad = sum(v[1] for v in per.values())
            hit = [k for k, v in per.items() if v[1]]
        except SystemExit as e:  # the driver crashed: the bug shows, counted as caught
            bad, hit = 1, [f"driver failed: {str(e).splitlines()[0][:60]}"]
        try:
            dirty, cmodel = clean_check(exe, cc, clines, cexp, cnoopt, quiet=True)
        except SystemExit as e:
            dirty, cmodel = 1, 0
        if dirty or cmodel:
            bad += dirty + cmodel
            hit.append(f"clean saves {dirty}+{cmodel}")
        if fname == "options.c" or "gate:" in what:
            ochecked, obad, _m = options_check(cc, exe, 300, seed + 7)
            if obad:
                bad += obad
                hit.append(f"options {obad}/{ochecked}")
        print(f"  planted bug {i:2d} ({what}): " + (f"caught, {bad} mismatches in {', '.join(hit)}" if bad
                                                    else "NOT CAUGHT"))
        missed += 0 if bad else 1
    return missed


def table_unarmed() -> list[str]:
    """The tracked writer.c table: the three options entries are there and armed 0."""
    body = open(WRITER_C, encoding="utf-8").read()
    errs = []
    for name in ("config_options", "config_options_hook", "config_save_guard"):
        m = re.search(r'\{"' + name + r'",\s*(\d+)\}', body)
        if not m:
            errs.append(f"writer.c's table has no entry {name}")
        elif m.group(1) != "0":
            errs.append(f"writer.c's table ARMS {name} ({m.group(1)}): the tracked table must stay 0")
    if "FE_WRITER_TABLE_CONST const" not in body:
        errs.append("writer.c's table is not const in library builds")
    return errs


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=300, help="scenarios (default 300)")
    ap.add_argument("--seed", type=int, default=20261118)
    ap.add_argument("--show", type=int, default=5)
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, default=200)
    ap.add_argument("--options", action="store_true", help="only the options file lines")
    a = ap.parse_args(argv)
    if not os.path.isfile(TEXT):
        print("w12_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = WD.find_cc()
    if not cc:
        print("w12_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_MENU, SRC_CORE)
    ochecked, obad, msgs = options_check(cc, exe, 2000, a.seed)
    for m in msgs:
        print(m)
    print(f"w12_diff: options file: {ochecked} files (the shared test lines, 2,000 made-up, the 64 KB limit, "
          f"%APPDATA% refused), {obad} mismatches")
    if a.options:
        return 0 if not obad else 1
    tbl = table_unarmed()
    for e in tbl:
        print(f"  {e}")
    files_dir = os.path.join(OUT, "files")
    shutil.rmtree(files_dir, ignore_errors=True)
    lines, expected, kinds = make_cases(text, a.n, a.seed, files_dir)
    per = compare(exe, cc, lines, expected, kinds, a.show)
    bad = sum(v[1] for v in per.values())
    print(f"w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) "
          f"composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed {a.seed}")
    for k, (n, b) in sorted(per.items()):
        print(f"  {k:6s} {n:5d} scenarios  {b:3d} mismatches")
    applied = sum(1 for e in expected.values() if e[5].split(":")[5] != "0")
    guarded = sum(1 for e in expected.values() if e[5].split(":")[6] != "0")
    gave = sum(1 for e in expected.values() if e[5].split(":")[7] != "0")
    nested = sum(1 for e in expected.values() if "nest" in e[0])
    print(f"w12_diff: exercised: {applied} scenarios where W1 stored, {guarded} where W2 wrote a save itself, "
          f"{gave} where W2 could not and restored, {nested} with a Deserialize inside a Serialize")
    # the unarmed table (the library's: const, every entry 0), FE_WRITERS listing all three, readable mode
    cexe = build_driver(cc, os.path.join(OUT, "const"), SRC_MENU, SRC_CORE, const=True)
    clines, cexp, ckinds = make_cases(text, a.n, a.seed, os.path.join(OUT, "const_files"), const=True)
    cper = compare(cexe, cc, clines, cexp, ckinds, a.show,
                   env_extra={"FE_WRITERS": "config_options,config_options_hook,config_save_guard",
                              "FE_READABLE": "readable"})
    cbad = sum(v[1] for v in cper.values())
    print(f"w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): "
          f"{sum(v[0] for v in cper.values())} scenarios, {cbad} mismatches (nothing stored, no session, the game's saves)")
    # the clean saves: load, apply, suspend save, game save; every stream equal to the game's with no options file
    kl, kexp, knoopt, kapplied, ksusp = make_clean_cases(text, max(a.n // 2, 50), a.seed,
                                                         os.path.join(OUT, "clean_files"))
    kdirty, kmodel = clean_check(exe, cc, kl, kexp, knoopt, a.show)
    print(f"w12_diff: clean saves: {len(kexp)} scenarios ({kapplied} with an apply, {ksusp} suspend saves, each "
          f"followed by a game save): {kdirty} differ from the game's own saves with no options file, "
          f"{kmodel} differ from section 4's model")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"w12_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not bad and not obad and not cbad and not tbl and not missed and not kdirty and not kmodel
    print(f"w12_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} scenarios, {bad} mismatches; "
          f"unarmed {cbad}; options {obad}; clean saves {kdirty + kmodel}" + (f"; {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
