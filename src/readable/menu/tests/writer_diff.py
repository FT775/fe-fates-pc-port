#!/usr/bin/env python3
"""Host differential test of the first readable writer (config_write_options, OFF) against the
game's own options-screen code, through the writer gate and its undo log.

    python src/readable/menu/tests/writer_diff.py            600 cases
    python src/readable/menu/tests/writer_diff.py -n 3000    more cases
    python src/readable/menu/tests/writer_diff.py --seed 7   another random sequence
    python src/readable/menu/tests/writer_diff.py --plant    also plant bugs: each must be caught

The writer (src/readable/menu/menu_config_writer.c) sets lines of GameConfigData the way
anonymous_namespace::ConfigItem::KeyCall does: the line's GetValue, then its SetValue(int) only
when the value differs. The reference here runs the ORIGINAL ARM code from the owner's
extracted/text.bin in arm_mini.py: for each selected line, in the writer's order (battle, game
speed, danger, HP bars), the line's GetValue and then, when the answer differs, its SetValue
(Battle 0x003BC36C, GameSpeed 0x003BC968, DangerPanel 0x003BAF00, HPGauge 0x003BC51C).
DangerPanel's tail branch to map::Image::Danger::Update and the BL to Map::Get are answered by one
stub table on both sides; the Update stub STORES (it sets bit 1 of the word at its argument
+0x1F8 .. the DangerImage flags, MapImage +0x1008 +0x200), so a guest callee's stores go through
the gate's logging host and must be undone too.

Per case it compares (the C side built with -DFE_WRITER_TESTS so the test can arm the writer):
  - the result (OK / OFF / REFUSED / ROLLED_BACK);
  - ONE ordered list of events: every guest store (address, size, value; stack stores of the ARM
    code left out) interleaved with every guest call (address, argument registers);
  - the number of data bytes read (literal pools and the stack left out; the C side reads every
    byte through the host);
  - the bytes of the options block and the danger flag word afterwards;
  - the writer's undo log: each entry's address, size, OLD value (the reference takes it from
    memory before the store), new value, writer id and frame;
  - then fe_writer_undo_last: every mapped byte must be back to the case's start.
A store the reference makes to unmapped memory must make the writer roll back with every byte
back (the gate refuses a store it could not undo). Modes: about 70% armed + listed + readable;
the rest OFF (not armed, not in FE_WRITERS, shadow, capture, original), a value past a line's
range (REFUSED: nothing read, nothing stored) and a setter called with no session (no store).
OFF, REFUSED and stray cases must read nothing (stray: only the block pointer) and store
nothing, and shadow / capture / original must be counted as mode refusals.

All values are made-up test values, never game data. Needs extracted/text.bin and a host C
compiler (FE_HOST_CC, or the ones tools/readable/check.py looks for); SKIPs (exit 0, says so)
without them. Exit 0 only when every case matches (and, with --plant, every planted bug is
caught). Writes only under build/readable/writers/.
"""
from __future__ import annotations

import argparse
import os
import random
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "battle", "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402
from stance_diff import State  # noqa: E402

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "writers")
SRC_MENU = os.path.join(ROOT, "src", "readable", "menu")
SRC_CORE = os.path.join(ROOT, "src", "readable", "core")
SP = 0x0FFFF000
STACK = (SP - 0x1000, SP + 0x100)

G_CONFIG, G_MAPIMAGE = 0x006DA0F8, 0x006D73E8
MAP_GET, UPDATE = 0x00342574, 0x0038F834
ARITY = {MAP_GET: 0, UPDATE: 1}
# line: (bit, GetValue, SetValue, byte offset, GetNum)
LINES = [
    ("battle", 0x1, 0x003BC358, 0x003BC36C, 0x8, 5),
    ("game_speed", 0x2, 0x003BC954, 0x003BC968, 0xC, 3),
    ("danger", 0x4, 0x003BAEEC, 0x003BAF00, 0xE, 3),
    ("hp_gauge", 0x8, 0x003BC508, 0x003BC51C, 0x16, 2),
]
CFG = 0x08100000
MAPIMG = 0x08200000
ITEM = 0x08130000
UNMAPPED = [0x40, 0x7FF0, 0x0BAD0000]
MODES = ["on", "on", "on", "on", "on", "on", "on", "unarmed", "unlisted", "shadow", "capture", "original",
         "range", "stray"]
RESULT = {"OK": 0, "OFF": 1, "REFUSED": 2, "ROLLED_BACK": 3}


def word(st, a: int) -> int:
    return int.from_bytes(bytes(st.mem.get(a + i, 0) for i in range(4)), "little")


def make_case(rng):
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.put(G_CONFIG, 4, CFG if rng.random() > 0.05 else rng.choice(UNMAPPED))
    st.fill(CFG, 0x20)
    for _name, _bit, _g, _s, off, num in LINES:  # current values: mostly in range, some junk
        st.put(CFG + off, 1, rng.randrange(num) if rng.random() < 0.85 else rng.choice([num, 0x80, 0xFF]))
    st.put(G_MAPIMAGE, 4, MAPIMG if rng.random() > 0.08 else rng.choice(UNMAPPED))
    st.fill(MAPIMG + 0x1008 + 0x1F0, 0x20)
    st.fill(ITEM, 0x10)
    mode = rng.choice(MODES)
    lines = rng.randrange(1, 16) if rng.random() > 0.05 else rng.choice([0, 15])
    values = []
    for _name, bit, _g, _s, off, num in LINES:
        v = rng.randrange(num)
        if mode == "range" and (lines & bit) and rng.random() < 0.5:
            v = rng.choice([num, num + 1, 0xFF, 0x100, 0xFFFFFFFF])
        values.append(v)
    if mode == "range" and not any((lines & LINES[i][1]) and values[i] >= LINES[i][5] for i in range(4)):
        i = rng.randrange(4)
        lines |= LINES[i][1]
        values[i] = LINES[i][5]
    map_value = 0 if rng.random() < 0.3 else rng.choice([0x08300000, 1, 0xFFFFFFFF])
    frame = rng.randrange(1 << 32)
    stray_line = rng.randrange(4)
    return st, mode, lines, values, map_value, frame, stray_line


# ------------------------------------------------------------------ the ARM side
class EventMemory(A.Memory):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.events: list[str] = []
        self.data_reads = 0
        self.unmapped_store = False
        self.counting = True

    def read8(self, a: int) -> int:
        a &= A.MASK
        if self.counting and not (0 <= a - self.text_base < len(self.text)) and not (STACK[0] <= a < STACK[1]):
            self.data_reads += 1
        return super().read8(a)

    def write(self, a: int, n: int, v: int) -> None:
        a &= A.MASK
        if not (STACK[0] <= a < STACK[1]):
            if any(self.pages.get(((a + i) & A.MASK) >> 12) is None for i in range(n)):
                self.unmapped_store = True
            self.events.append(f"s{a:x}:{n}:{v & ((1 << (8 * n)) - 1):x}")
        super().write(a, n, v)


class EventCpu(A.Cpu):
    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            self.mem.events.append(f"c{target:x}" + "".join(f":{r:x}" for r in self.r[:ARITY[target]]))
        return super().call(target, ret)


def update_effect(mem: EventMemory, image: int) -> None:
    """The Update stub on both sides: flags word (image +0x200) |= 2, read and stored as words."""
    a = (image + 0x200) & A.MASK
    v = mem.read(a, 4)
    mem.write(a, 4, v | 2)


def arm_run(text: bytes, case) -> dict:
    st, mode, lines, values, map_value, frame, stray_line = case
    mem = EventMemory(text)
    for a, d in st.regions():
        mem.map(a, d)
    before = {a: st.mem[a] for a in st.mem}
    if mode in ("unarmed", "unlisted", "shadow", "capture", "original", "range"):
        res = "REFUSED" if mode == "range" else "OFF"
        return {"result": RESULT[res], "events": "-", "reads": 0, "log": "-", "undo": 1, "same": 1,
                "modeuse": int(mode in ("shadow", "capture", "original"))}
    if mode == "stray":  # a setter with no session: reads the block pointer, stores nothing
        reads = 4 + (0 if word(st, G_CONFIG) else 0)
        return {"result": 9, "events": "-", "reads": reads, "log": "-", "undo": 1, "same": 1, "modeuse": 0}
    cpu = EventCpu(mem, {MAP_GET: lambda cpu, a: map_value})
    for name, bit, get, setv, off, num in LINES:
        if not (lines & bit):
            continue
        v = values[LINES.index((name, bit, get, setv, off, num))]
        cpu.r[13], cpu.r[14], cpu.r[0] = SP, A.RETURN_SENTINEL, ITEM
        cpu.run(get)
        if cpu.r[0] == v:
            continue
        cpu.r[13], cpu.r[14], cpu.r[0], cpu.r[1] = SP, A.RETURN_SENTINEL, ITEM, v
        if cpu.run(setv, stop={UPDATE}) == UPDATE:  # DangerPanel's tail branch
            mem.events.append(f"c{UPDATE:x}:{cpu.r[0]:x}")
            update_effect(mem, cpu.r[0])
    if mem.unmapped_store:
        return {"result": RESULT["ROLLED_BACK"], "same": 1, "modeuse": 0}
    # the undo log the reference expects: old values from memory in store order
    shadow = dict(before)
    log = []
    for e in mem.events:
        if e[0] != "s":
            continue
        a, n, v = e[1:].split(":")
        a, n, v = int(a, 16), int(n), int(v, 16)
        old = sum(shadow.get(a + i, 0) << (8 * i) for i in range(n))
        for i in range(n):
            shadow[a + i] = (v >> (8 * i)) & 0xFF
        log.append(f"{a:x}:{n}:{old:x}:{v:x}:1:{frame:x}")
    cfgp = word(st, G_CONFIG)
    mem.counting = False
    block = bytes(mem.read8(cfgp + i) for i in range(0x18)).hex()
    imgp = word(st, G_MAPIMAGE)
    flags = mem.read(imgp + 0x1008 + 0x200, 4) if imgp == MAPIMG else 0
    return {"result": RESULT["OK"], "events": ",".join(mem.events) or "-", "reads": mem.data_reads,
            "log": ",".join(log) or "-", "block": block, "flags": f"{flags:x}", "undo": 1, "same": 1,
            "modeuse": 0}


# ------------------------------------------------------------------ the C side
DRIVER = r'''
/* Generated by src/readable/menu/tests/writer_diff.py: runs the options writer through the writer
   gate on memory images read from stdin. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "menu_writer.h"

static uint8_t **pages, **nopages, **snap;
static uint32_t used[4096]; static int nused;
static uint8_t *at(uint32_t a, int make) {
    uint8_t *p = pages[a >> 12];
    if (!p && make && nused < 4096) {
        p = pages[a >> 12] = calloc(4096, 1); snap[a >> 12] = calloc(4096, 1); used[nused++] = a >> 12;
    }
    return p ? p + (a & 0xFFF) : NULL;
}
static int reads, host_writes;
static uint8_t r8(Context *c, uint32_t a) { (void)c; reads++; uint8_t *p = at(a, 0); return p ? *p : 0; }
static uint16_t r16(Context *c, uint32_t a) { return (uint16_t)(r8(c, a) | r8(c, a + 1) << 8); }
static uint32_t r32(Context *c, uint32_t a) { return (uint32_t)r16(c, a) | (uint32_t)r16(c, a + 2) << 16; }
static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; host_writes++; uint8_t *p = at(a, 0); if (p) *p = v; }
static void w16(Context *c, uint32_t a, uint16_t v) { w8(c, a, (uint8_t)v); w8(c, a + 1, (uint8_t)(v >> 8)); }
static void w32(Context *c, uint32_t a, uint32_t v) { w16(c, a, (uint16_t)v); w16(c, a + 2, (uint16_t)(v >> 16)); }
static void interp(Context *c, uint32_t a, uint32_t o) { (void)c; (void)a; (void)o; }
static void svc(Context *c, uint32_t n) { (void)c; (void)n; }

/* events: calls carry the log position they happened at, so stores and calls interleave */
static uint32_t call_pos[64], call_f[64], call_a0[64]; static int ncall;
static uint32_t map_value;

/* generated code's way to store: the direct page when there is one, else the host */
static uint32_t g_read32(Context *c, uint32_t a) {
    uint8_t *p = c->read_pages[a >> 12];
    if (p && (a & 0xFFF) <= 0xFFC) { uint32_t v; memcpy(&v, p + (a & 0xFFF), 4); return v; }
    return c->host->read32(c, a);
}
static void g_write32(Context *c, uint32_t a, uint32_t v) {
    uint8_t *p = c->write_pages[a >> 12];
    if (p && (a & 0xFFF) <= 0xFFC) memcpy(p + (a & 0xFFF), &v, 4);
    else c->host->write32(c, a, v);
}
static void stub_map_get(Context *c) {
    if (ncall < 64) { call_pos[ncall] = fe_writer_log_count(); call_f[ncall] = @MAP_GET@u; call_a0[ncall] = 0; ncall++; }
    c->r[0] = map_value; c->r[15] = c->r[14];
}
static void stub_update(Context *c) {
    if (ncall < 64) { call_pos[ncall] = fe_writer_log_count(); call_f[ncall] = @UPDATE@u; call_a0[ncall] = c->r[0]; ncall++; }
    uint32_t a = c->r[0] + 0x200u;
    g_write32(c, a, g_read32(c, a) | 2u);
    c->r[15] = c->r[14];
}
static Code lookup(Context *c, uint32_t a) {
    (void)c;
    if (a == @MAP_GET@u) return stub_map_get;
    if (a == @UPDATE@u) return stub_update;
    return NULL;
}
void fe_stub_original(Context *ctx) { ctx->r[0] = 0xDEADBEEFu; ctx->r[15] = ctx->r[14] & ~3u; }

static const Host host = {r8, r16, r32, w8, w16, w32, interp, lookup, svc};
static uint32_t vfp[32], fpscr;
static int hexval(int ch) { return ch <= '9' ? ch - '0' : (ch | 32) - 'a' + 10; }
static int same_as_start(void) {
    for (int i = 0; i < nused; i++) if (memcmp(pages[used[i]], snap[used[i]], 4096)) return 0;
    return 1;
}

int main(void) {
    pages = calloc(1u << 20, sizeof *pages);
    snap = calloc(1u << 20, sizeof *snap);
    nopages = calloc(1u << 20, sizeof *nopages);
    static char line[1 << 16];
    char mode[32]; unsigned id = 0; uint32_t lines = 0, v[4] = {0}, frame = 0, stray = 0, cfgp = 0, imgp = 0;
    while (fgets(line, sizeof line, stdin)) {
        if (!strncmp(line, "case ", 5)) {
            sscanf(line + 5, "%u %31s %x %x %x %x %x %x %x %x %x %x", &id, mode, &lines, &v[0], &v[1], &v[2], &v[3],
                   &map_value, &frame, &stray, &cfgp, &imgp);
            for (int i = 0; i < nused; i++) { free(pages[used[i]]); pages[used[i]] = NULL; free(snap[used[i]]); snap[used[i]] = NULL; }
            nused = 0; reads = 0; host_writes = 0; ncall = 0;
        } else if (!strncmp(line, "mem ", 4)) {
            uint32_t addr; int off = 0;
            sscanf(line + 4, "%x %n", &addr, &off);
            const char *h = line + 4 + off;
            for (uint32_t i = 0; h[2 * i] && h[2 * i] != '\n' && h[2 * i] != '\r'; i++) {
                uint8_t b = (uint8_t)(hexval(h[2 * i]) << 4 | hexval(h[2 * i + 1]));
                *at(addr + i, 1) = b;
                snap[(addr + i) >> 12][(addr + i) & 0xFFF] = b;
            }
        } else if (!strncmp(line, "run", 3)) {
            fe_writer_test_reset();
            Context c; memset(&c, 0, sizeof c);
            c.read_pages = nopages; c.write_pages = pages; c.vfp = vfp; c.fpscr = &fpscr; c.host = &host;
            c.r[14] = 0x00123450u; c.budget = 1000;
            int armed = strcmp(mode, "unarmed") != 0;
            fe_writer_test_arm(FE_WRITER_CONFIG_OPTIONS, armed);
            fe_writer_test_switches(strcmp(mode, "unlisted") ? "other,config_options" : "other,config_option");
            fe_force_mode(!strcmp(mode, "shadow") ? FE_MODE_SHADOW : !strcmp(mode, "capture") ? FE_MODE_CAPTURE
                          : !strcmp(mode, "original") ? FE_MODE_ORIGINAL : FE_MODE_READABLE);
            fe_writer_set_frame(frame);
            uint32_t before = fe_writer_log_count();
            int result;
            if (!strcmp(mode, "stray")) {
                int (*const set[4])(Context *, uint32_t) = {config_set_battle, config_set_game_speed, config_set_danger,
                                                           config_set_hp_gauge};
                (void)set[stray](&c, 1u);
                result = 9;
            } else {
                ConfigOptionsWanted w = {lines, v[0], v[1], v[2], v[3]};
                result = config_write_options(&c, &w);
            }
            printf("%u %d", id, result);
            if (result == 0) {
                /* events */
                char ev[1 << 14]; size_t ne = 0; ev[0] = 0;
                uint32_t n = fe_writer_log_count(); int ci = 0;
                for (uint32_t i = before; i <= n; i++) {
                    while (ci < ncall && call_pos[ci] == i) {
                        ne += (size_t)snprintf(ev + ne, sizeof ev - ne, "%sc%x", ne ? "," : "", call_f[ci]);
                        if (call_f[ci] == @UPDATE@u) ne += (size_t)snprintf(ev + ne, sizeof ev - ne, ":%x", call_a0[ci]);
                        ci++;
                    }
                    if (i < n) {
                        FeWriterEntry e; fe_writer_log_entry(i, &e);
                        ne += (size_t)snprintf(ev + ne, sizeof ev - ne, "%ss%x:%u:%x", ne ? "," : "", e.address, e.size, e.new_value);
                    }
                }
                printf(" %s %d", ne ? ev : "-", reads);
                printf(" ");
                if (n == before) printf("-");
                for (uint32_t i = before; i < n; i++) {
                    FeWriterEntry e; fe_writer_log_entry(i, &e);
                    printf("%s%x:%u:%x:%x:%u:%x", i > before ? "," : "", e.address, e.size, e.old_value, e.new_value, e.writer, e.frame);
                }
                printf(" ");
                for (uint32_t i = 0; i < 0x18; i++) { uint8_t *p = at(cfgp + i, 0); printf("%02x", p ? *p : 0); }
                uint32_t fl = 0;
                if (imgp == 0x08200000u) for (uint32_t i = 0; i < 4; i++) { uint8_t *p = at(imgp + 0x1208u + i, 0); fl |= (uint32_t)(p ? *p : 0) << (8 * i); }
                printf(" %x", fl);
                int u = n == before ? FE_WRITER_NOTHING : fe_writer_undo_last(&c);
                printf(" %d", (u == FE_WRITER_OK || u == FE_WRITER_NOTHING) && same_as_start());
                printf(" %d\n", host_writes ? -host_writes : 1);
            } else if (result == 3) {
                printf(" %d %d\n", same_as_start(), host_writes ? -host_writes : 1);
            } else {
                printf(" - %d - %d %d %u\n", reads, same_as_start() && fe_writer_log_count() == before && ncall == 0
                       && host_writes == 0, fe_writer_stray_stores() > 0 || result != 9, fe_writer_mode_refusals());
            }
        }
    }
    return 0;
}
'''


def driver_text() -> str:
    return DRIVER.replace("@MAP_GET@", f"0x{MAP_GET:08X}").replace("@UPDATE@", f"0x{UPDATE:08X}")


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


def build_driver(cc: str, out: str, menu_dir: str, core_dir: str) -> str:
    """Builds the driver with every source of src/readable/, the menu and core folders' taken from
    menu_dir and core_dir (planted copies), with FE_WRITER_TESTS so the test can arm the writer."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "writer_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        p = os.path.normcase(os.path.abspath(dp))
        if p.startswith(os.path.normcase(SRC_MENU)) or p.startswith(os.path.normcase(SRC_CORE)):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(menu_dir, f) for f in os.listdir(menu_dir) if f.endswith(".c")]
    sources += [os.path.join(core_dir, f) for f in os.listdir(core_dir) if f.endswith(".c")]
    exe = os.path.join(out, "writer_driver.exe" if os.name == "nt" else "writer_driver")
    # the menu headers include "../core/fe_writer.h": a planted copy keeps the menu/ core/ pair
    inc = ["-I", menu_dir, "-I", core_dir, "-I", os.path.join(ROOT, "src", "readable", "unit"),
           "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-fwrapv", "-DFE_WRITER_TESTS"] + inc + [src] \
        + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"writer_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


def make_cases(text: bytes, n: int, seed: int):
    rng = random.Random(seed)
    lines, expected = [], {}
    for cid in range(n):
        case = make_case(rng)
        st, mode, lns, values, map_value, frame, stray = case
        expected[cid] = (arm_run(text, case), mode)
        lines.append(f"case {cid} {mode} {lns:x} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in values)
                     + f" {map_value:x} {frame:x} {stray:x} {word(st, G_CONFIG):x} {word(st, G_MAPIMAGE):x}")
        for addr, data in st.regions():
            for off in range(0, len(data), 4096):
                lines.append(f"mem {addr + off:x} {data[off:off + 4096].hex()}")
        lines.append("run")
    return lines, expected


def expected_tokens(e: dict, mode: str) -> list[str]:
    r = e["result"]
    if r == 0:
        return ["0", e["events"], str(e["reads"]), e["log"], e["block"], e["flags"], "1", "1"]
    if r == 3:
        return ["3", "1", "1"]
    # OFF / REFUSED / stray: nothing logged, nothing stored, nothing called, memory as at the start
    return [str(r), "-", str(e["reads"]), "-", "1", "1", "MODE" if e["modeuse"] else "0"]


def compare(exe: str, cc: str, lines: list[str], expected: dict, show: int, quiet: bool = False):
    log = os.path.join(os.path.dirname(exe), "fe_readable.log")
    env = dict(os.environ, FE_READABLE_LOG=log, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""))
    env.pop("FE_WRITERS", None)
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"writer_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if parts:
            got[int(parts[0])] = parts[1:]
    per: dict[str, list[int]] = {}
    for c, (e, mode) in expected.items():
        key = mode if mode in ("range", "stray") else ("on" if mode == "on" else "off")
        res = per.setdefault(key, [0, 0])
        res[0] += 1
        want = expected_tokens(e, mode)
        g = got.get(c)
        ok = g is not None and len(g) == len(want)
        if ok:
            for w, x in zip(want, g):
                if w == "MODE":
                    ok = ok and int(x) > 0
                else:
                    ok = ok and w == x
        if not ok:
            res[1] += 1
            if res[1] <= show and not quiet:
                print(f"  MISMATCH case {c} ({mode}):\n    original {want}\n    readable {g}")
    return per


# planted bugs: (folder, file, exact text, replacement); each text occurs once in its file
PLANTS = [
    ("menu", "menu_config_writer.c", "GameConfigData, config, danger), 1, value))", "GameConfigData, config, byte_0f), 1, value))"),
    ("menu", "menu_config_writer.c", "GameConfigData, config, hp_gauge), 1, value);", "GameConfigData, config, byte_15), 1, value);"),
    ("menu", "menu_config_writer.c", "GameConfigData, config, battle_mode), 1, value);", "GameConfigData, config, battle_mode), 4, value);"),
    ("menu", "menu_config_writer.c", "GameConfigData, config, game_speed), 1, value);", "GameConfigData, config, ai_skip), 1, value);"),
    # the screen's compare left out: every selected line stores (and the zone is rebuilt)
    ("menu", "menu_config_writer.c", "    if (get(ctx, 0) != value)\n        (void)set(ctx, value);", "    (void)get(ctx, 0);\n    (void)set(ctx, value);"),
    ("menu", "menu_config_writer.c", "    if (get(ctx, 0) != value)", "    if (get(ctx, 0) == value)"),
    # the map read straight from its global instead of calling Map::Get: a missing guest call
    ("menu", "menu_config_writer.c", "    if (fe_writer_call(ctx, MN_MapGet, config, 0u, 0u, 0u) != 0) {",
     "    if (guest_ptr(ctx, 0x006D72F4u) != 0) {"),
    ("menu", "menu_config_writer.c", "    if (fe_writer_call(ctx, MN_MapGet, config, 0u, 0u, 0u) != 0) {",
     "    (void)fe_writer_call(ctx, MN_MapGet, config, 0u, 0u, 0u);\n    {"),
    ("menu", "menu_config_writer.c", "FIELD_ADDR(MapImage, map, danger), 0u", "map + 0x1000u, 0u"),
    # the zone rebuilt before the byte is stored
    ("menu", "menu_config_writer.c",
     "    if (!fe_writer_store(ctx, FIELD_ADDR(GameConfigData, config, danger), 1, value))\n        return 0;\n    if (fe_writer_call(ctx, MN_MapGet, config, 0u, 0u, 0u) != 0) {\n        gaddr map = guest_ptr(ctx, G_MapImage);\n        (void)fe_writer_call(ctx, MN_DangerUpdate, FIELD_ADDR(MapImage, map, danger), 0u, 0u, 0u);\n    }",
     "    if (fe_writer_call(ctx, MN_MapGet, config, 0u, 0u, 0u) != 0) {\n        gaddr map = guest_ptr(ctx, G_MapImage);\n        (void)fe_writer_call(ctx, MN_DangerUpdate, FIELD_ADDR(MapImage, map, danger), 0u, 0u, 0u);\n    }\n    if (!fe_writer_store(ctx, FIELD_ADDR(GameConfigData, config, danger), 1, value))\n        return 0;"),
    # the lines in another order (HP bars before the danger zone)
    ("menu", "menu_config_writer.c",
     "    if (want->lines & MN_SET_DANGER)\n        set_line(ctx, config_danger_value, rebuild ? config_set_danger : config_store_danger, want->danger);\n    if (want->lines & MN_SET_HP_GAUGE)\n        set_line(ctx, config_hp_gauge_value, config_set_hp_gauge, want->hp_gauge);",
     "    if (want->lines & MN_SET_HP_GAUGE)\n        set_line(ctx, config_hp_gauge_value, config_set_hp_gauge, want->hp_gauge);\n    if (want->lines & MN_SET_DANGER)\n        set_line(ctx, config_danger_value, rebuild ? config_set_danger : config_store_danger, want->danger);"),
    # the range check (round 38: one table of each line's last value, shared with W2's restore)
    ("menu", "menu_config_writer.c", "uint32_t last[4] = {4u, 2u, 2u, 1u};", "uint32_t last[4] = {4u, 2u, 3u, 1u};"),
    ("menu", "menu_config_writer.c", "uint32_t last[4] = {4u, 2u, 2u, 1u};", "uint32_t last[4] = {3u, 2u, 2u, 1u};"),
    # a line's compare made against another line's byte
    ("menu", "menu_config_writer.c", "set_line(ctx, config_game_speed_value, config_set_game_speed",
     "set_line(ctx, config_ai_skip_value, config_set_game_speed"),
    # the block pointer read twice per setter: one extra read
    ("menu", "menu_config_writer.c",
     "int config_set_hp_gauge(Context *ctx, uint32_t value) {\n    gaddr config = guest_ptr(ctx, G_GameConfig);",
     "int config_set_hp_gauge(Context *ctx, uint32_t value) {\n    gaddr config = guest_ptr(ctx, G_GameConfig);\n    config = guest_ptr(ctx, G_GameConfig);"),
    # the gate
    ("core", "writer.c", "        old |= (uint32_t)*bytes[k] << (8 * k);", "        old |= (uint32_t)(uint8_t)(value >> (8 * k)) << (8 * k);"),
    ("core", "writer.c", "    e->frame = fe_writer_frame;", "    e->frame = 0;"),
    ("core", "writer.c", "    e->writer = (uint32_t)fe_writer_id;", "    e->writer = 0;"),
    ("core", "writer.c", "    return fe_mode() == FE_MODE_READABLE;\n}", "    return fe_mode() != FE_MODE_ORIGINAL;\n}"),
    ("core", "writer.c", "    if (!fe_writer_table[writer].armed)\n        return 0;\n", ""),
    ("core", "writer.c", "    if (!fe_writer_listed[writer])\n        return 0;\n", ""),
    # a guest callee's stores forwarded without being logged
    ("core", "writer.c",
     "static void fe_writer_write32(Context *ctx, uint32_t a, uint32_t v) { (void)fe_writer_put(ctx, fe_writer_real_write, a, 4, v); }",
     "static void fe_writer_write32(Context *ctx, uint32_t a, uint32_t v) { (void)ctx; uint8_t *p = fe_writer_byte(fe_writer_real_write, a); if (p) { for (int k = 0; k < 4; k++) p[k] = (uint8_t)(v >> (8 * k)); } }"),
    # a store to a byte without a page pointer dropped quietly instead of failing the session
    ("core", "writer.c",
     "        if ((bytes[k] = fe_writer_byte(table, address + k)) == NULL) {\n            fe_writer_give_up(ctx, FE_WRITER_FAIL_HOSTMEM);\n            return 0;\n        }",
     "        if ((bytes[k] = fe_writer_byte(table, address + k)) == NULL)\n            return 1; /* dropped, but reported as stored */"),
    # a stray store performed
    ("core", "writer.c",
     "    if (!fe_writer_in_session(ctx)) {\n        fe_writer_stray++; /* no session: nothing is stored */\n        fe_writer_publish();\n        return 0;\n    }",
     "    if (!fe_writer_in_session(ctx)) {\n        fe_writer_stray++;\n        fe_writer_publish();\n        return fe_writer_put(ctx, ctx->write_pages, address, size, value);\n    }"),
    # undo that only drops the log (the bytes stay). Restore order, conflicts and a full log are
    # planted in the gate's own test (src/readable/core/tests/writer_gate_test.py): this writer
    # never stores a byte twice, and nothing stores between the writer and the undo here
    ("core", "writer.c", "    fe_writer_restore(ctx->write_pages, from);\n    atomic_store(&fe_writer_busy, 0);\n    return FE_WRITER_OK;",
     "    fe_writer_count = from;\n    atomic_store(&fe_writer_busy, 0);\n    return FE_WRITER_OK;"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    lines, expected = make_cases(text, n, seed)
    missed = 0
    for i, (folder, fname, old, new) in enumerate(PLANTS, 1):
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
        exe = build_driver(cc, os.path.join(OUT, "plant", f"p{i:02d}"), menu_dir, core_dir)  # one exe per bug
        try:
            per = compare(exe, cc, lines, expected, 0, quiet=True)
        except SystemExit as e:  # the driver crashed: the bug shows, counted as caught
            print(f"  planted bug {i:2d} ({fname}): caught, the driver failed ({str(e).splitlines()[0]})")
            continue
        bad = sum(v[1] for v in per.values())
        hit = [k for k, v in per.items() if v[1]]
        print(f"  planted bug {i:2d} ({fname}: {old.strip()[:50]!r}): "
              + (f"caught, {bad} mismatches in {', '.join(hit)}" if bad else "NOT CAUGHT"))
        missed += 0 if bad else 1
    return missed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=600, help="cases (default 600)")
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument("--show", type=int, default=5)
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, default=400)
    a = ap.parse_args(argv)
    if not os.path.isfile(TEXT):
        print("writer_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("writer_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_MENU, SRC_CORE)
    lines, expected = make_cases(text, a.n, a.seed)
    per = compare(exe, cc, lines, expected, a.show)
    bad = sum(v[1] for v in per.values())
    print(f"writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against "
          f"config_write_options through the writer gate, seed {a.seed}")
    for k, (n, b) in sorted(per.items()):
        print(f"  {k:10s} {n:5d} cases  {b:3d} mismatches")
    stores = sum(1 for e, m in expected.values() if e["result"] == 0 and e["events"] != "-")
    rolled = sum(1 for e, m in expected.values() if e["result"] == 3)
    updates = sum(1 for e, m in expected.values() if e["result"] == 0 and f"c{UPDATE:x}" in e["events"])
    print(f"writer_diff: exercised: {stores} cases that stored, {updates} that rebuilt the zone (a callee's "
          f"store logged and undone), {rolled} that had to roll back")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"writer_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not bad and not missed
    print(f"writer_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, {bad} mismatches"
          + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "") + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
