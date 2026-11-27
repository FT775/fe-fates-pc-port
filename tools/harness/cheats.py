#!/usr/bin/env python3
"""The robot's cheat track (docs/CHEATS.md): pokes into the robot's OWN test game's memory, in headless runs only.
Standard library only.

Owner's OK (2026-11-12 night, in chat): the robot may poke values into its own test game's memory in headless runs,
never into the owner's Zakuro cheat file, saves or mods. This module is the whole mechanism; nothing in the engine
changed (no Zakuro build).

A cheat route (config/harness/routes.json, name `cheat-*`, `"cheat": true`) declares its pokes:

    "pokes": [{"frame": 10400, "at": "0x006D1998 * +0x8 * * +0xD4 * +6", "size": 1, "value": 1, "expect": 0,
               "why": "1 Pearl: Castle::Get 0x0044544C ... GetGemstoneNum 0x00540AD4, ore index 6 (katana ore)"}]

How a poke is applied (deterministic, no engine change): the run is cut into stages at the poke frames. Stage k runs
boot.exe up to frame F (from the start save, or from the patched state of stage k-1 through ZAKURO_LOAD) and keeps
the savestate of frame F (ZAKURO_SAVE_AT) and a memory dump of the same moment (ZAKURO_DUMP_MEM at F: boot.exe dumps
after frame F-1 and saves before frame F, so both show one moment). The poke's address is followed in that dump
(the path below), the byte(s) are checked (`expect`), mapped to their place in the savestate's FCRAM section (the
linear heap 0x30000000 is FCRAM + 0, checked page by page against the dump; any other address is found by its page,
which must occur once), written there, and the patched state is the start of the next stage. Replays repeat byte for
byte: every stage is a normal deterministic run and the patch is a pure function of its state.

Path ("at"): tokens separated by spaces, read left to right from an address:

    0x006D1998        a guest address (hex), or a name of config/readable/globals.csv (G_UnitPool, G_EquipSkill)
    unit:10           the Unit of person id 10 (Person +0x24) in forces 0..3 (first match; markers.force_units)
    *                 the u32 stored at the address becomes the address (a pointer is followed)
    +0x8, +6, -4      added
    Unit.equip_skills[0]   a field of config/readable/structs/<Struct>.csv (offset + index * element size)

A poke writes "value" (a number) or "value_from" (a path: the address it names, e.g. "unit:1 Unit.person *" is
Corrin's Person record; size 4). A cheat route needs pokes unless it starts from a cheat save (cheat-*), e.g. to
replay a packed cheat save.

What a run records (run.json "pokes"): frame, path, the resolved address, the FCRAM offset and how it was found,
the old and the new bytes. run.json "cheat": true. Only numbers, no game bytes beyond the poked ones.

    python tools/harness/cheats.py --selftest      invented memory and savestates, no game
    python tools/harness/cheats.py --check         the cheat routes of config/harness/routes.json: rules and paths
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
READABLE = os.path.join(ROOT, "config", "readable")
LINEAR = 0x30000000  # the linear heap: FCRAM + 0 on this boot (checked page by page before every poke)
PAGE = 0x1000
SIZES = (1, 2, 4)


class Stop(Exception):
    """A cheat route that cannot be applied as written (a setup problem: nothing is poked)."""


# ------------------------------------------------------------------ route rules
def is_cheat(route: dict) -> bool:
    return route.get("cheat") is True


def check_routes(routes: dict) -> list[str]:
    """The cheat track's rules over the whole route table (headless.load_routes calls it): a route named cheat-*
    says "cheat": true and the other way round; pokes only in cheat routes; a real-play route never starts from a
    cheat route's save (saves packed from cheat runs are named cheat-*, headless.pack_save enforces it)."""
    bad = []
    for name, r in routes.items():
        named = name.startswith("cheat-")
        if named != is_cheat(r):
            bad.append(f"route {name}: a cheat route is named cheat-* and has \"cheat\": true (both or neither)")
        if r.get("pokes") and not is_cheat(r):
            bad.append(f"route {name}: pokes only in a cheat route")
        if not is_cheat(r) and str(r.get("save", "")).startswith("cheat-"):
            bad.append(f"route {name}: a real-play route may not start from a cheat save ({r['save']})")
        if is_cheat(r):
            try:
                pokes = parse_pokes(r)
            except Stop as e:
                bad.append(f"route {name}: {e}")
                continue
            if not pokes and not str(r.get("save", "")).startswith("cheat-"):
                bad.append(f"route {name}: a cheat route without pokes (only one that starts from a cheat save may)")
            for p in pokes:
                if not (0 < p["frame"] < int(r["save_at"])):
                    bad.append(f"route {name}: poke frame {p['frame']} must be inside the run, before save_at")
    return bad


def parse_pokes(route: dict) -> list[dict]:
    out = []
    for i, p in enumerate(route.get("pokes") or []):
        if not isinstance(p, dict):
            raise Stop(f"poke {i}: an object")
        for k in ("frame", "at", "size"):
            if k not in p:
                raise Stop(f"poke {i}: no '{k}'")
        if ("value" in p) == ("value_from" in p):
            raise Stop(f"poke {i}: give 'value' (a number) or 'value_from' (a path: the address it names), one")
        if int(p["size"]) not in SIZES:
            raise Stop(f"poke {i}: size 1, 2 or 4")
        if "value_from" in p:
            tokens(str(p["value_from"]))
            if int(p["size"]) != 4:
                raise Stop(f"poke {i}: value_from writes an address: size 4")
        size, value = int(p["size"]), int(p.get("value", 0))
        if not (-(1 << (8 * size - 1)) <= value < (1 << (8 * size))):
            raise Stop(f"poke {i}: value {value} does not fit {size} byte(s)")
        if "expect" in p and not (-(1 << (8 * size - 1)) <= int(p["expect"]) < (1 << (8 * size))):
            raise Stop(f"poke {i}: expect does not fit {size} byte(s)")
        tokens(str(p["at"]))  # syntax only; names and fields are checked when resolved
        out.append({"frame": int(p["frame"]), "at": str(p["at"]), "size": size, "value": value,
                    "value_from": str(p["value_from"]) if "value_from" in p else None,
                    "expect": None if "expect" not in p else int(p["expect"]), "why": p.get("why", "")})
    return out


def groups(route: dict) -> list[tuple[int, list[dict]]]:
    """The pokes by frame, in frame order: one stage boundary per frame."""
    by: dict[int, list[dict]] = {}
    for p in parse_pokes(route):
        by.setdefault(p["frame"], []).append(p)
    return sorted(by.items())


# ------------------------------------------------------------------ layouts and paths
_LAYOUT: dict = {}


def layouts() -> tuple[dict, dict]:
    """(globals: name -> address, structs: name -> {field: (offset, element size, count)}) from config/readable."""
    if not _LAYOUT:
        gl, st = {}, {}
        with open(os.path.join(READABLE, "globals.csv"), encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                gl[row["name"]] = int(row["address"], 16)
        for path in glob.glob(os.path.join(READABLE, "structs", "*.csv")):
            fields = {}
            with open(path, encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    off, size, typ = int(row["offset"], 16), int(row["size"], 16), row["type"]
                    m = re.search(r"\[(\d+)\]$", typ)
                    count = int(m.group(1)) if m else 1
                    fields[row["name"]] = (off, size // count if count else size, count)
            st[os.path.splitext(os.path.basename(path))[0]] = fields
        _LAYOUT.update(globals=gl, structs=st)
    return _LAYOUT["globals"], _LAYOUT["structs"]


TOKEN = re.compile(r"^(?:0x[0-9A-Fa-f]{1,8}|unit:\d+|\*|[+-](?:0x[0-9A-Fa-f]+|\d+)|[A-Za-z_]\w*(?:\.\w+(?:\[\d+\])?)?)$")


def tokens(path: str) -> list[str]:
    toks = path.split()
    if not toks:
        raise Stop("an empty path")
    for t in toks:
        if not TOKEN.match(t):
            raise Stop(f"path {path!r}: bad token {t!r}")
    if toks[0] in ("*",) or toks[0][0] in "+-" or ("." in toks[0] and not toks[0].startswith("0x")):
        raise Stop(f"path {path!r}: must start with an address, a global or unit:ID")
    return toks


def element_size(path: str) -> int | None:
    """The element size of the field a path ends on (a check against the poke's size), else None."""
    last = path.split()[-1]
    if "." in last and not last.startswith("0x"):
        struct_name, _, field = last.partition(".")
        field = field.split("[")[0]
        fields = layouts()[1].get(struct_name, {})
        if field in fields:
            return fields[field][1]
    return None


def static_bases(path: str) -> list[int]:
    """Addresses a path reads before its first pointer (a static or global): their pages are dumped at the poke
    frame so the address can be found in the savestate (heap pages are in the markers dump already)."""
    gl = layouts()[0]
    t = tokens(path)[0]
    if t.startswith("0x"):
        return [int(t, 16)]
    if t in gl:
        return [gl[t]]
    return []


def resolve(mem, path: str, unit_finder=None) -> tuple[int, list[str]]:
    """The address a path names in memory `mem` (markers.Memory-like: u32/u8), with each step for the record."""
    gl, st = layouts()
    toks = tokens(path)
    steps = []
    first = toks[0]
    if first.startswith("0x"):
        addr = int(first, 16)
    elif first.startswith("unit:"):
        if unit_finder is None:
            raise Stop("unit:ID needs the unit pool")
        addr = unit_finder(int(first[5:]))
        if addr is None:
            raise Stop(f"{first}: no unit with that person id in forces 0..3")
    elif first in gl:
        addr = gl[first]
    else:
        raise Stop(f"{first}: not a global of config/readable/globals.csv")
    steps.append(f"{first} = 0x{addr:08X}")
    for t in toks[1:]:
        if t == "*":
            v = mem.u32(addr)
            if v is None:
                raise Stop(f"{path}: 0x{addr:08X} is not in the dump")
            if v == 0:
                raise Stop(f"{path}: a null pointer at 0x{addr:08X}")
            addr = v
        elif t[0] in "+-":
            addr += int(t, 0)
        else:
            sname, _, rest = t.partition(".")
            m = re.fullmatch(r"(\w+)(?:\[(\d+)\])?", rest)
            fields = st.get(sname)
            if fields is None or not m or m.group(1) not in fields:
                raise Stop(f"{t}: no such field in config/readable/structs/")
            off, esize, count = fields[m.group(1)]
            idx = int(m.group(2) or 0)
            if idx >= count:
                raise Stop(f"{t}: index past the field's {count} element(s)")
            addr += off + idx * esize
        addr &= 0xFFFFFFFF
        steps.append(f"{t} -> 0x{addr:08X}")
    return addr, steps


def unit_finder_for(mem):
    """unit:ID -> the first Unit of forces 0..3 whose Person (+0x9C) has id (+0x24) ID (markers' unit walk)."""
    sys.path.insert(0, HERE)
    import markers as mk  # noqa: E402
    sys.path.remove(HERE)
    cfg = mk.load_config()
    pool = mem.u32(int(cfg["state"]["unit_pool"], 16) + 4)

    def find(pid: int):
        if not pool:
            return None
        for unit in mk.force_units(mem, pool, [0, 1, 2, 3]):
            per = mem.u32(unit + 0x9C)
            if per and mk._u16(mem, per + 0x24) == pid:
                return unit
        return None
    return find


def read_bytes(mem, addr: int, size: int) -> bytes | None:
    vals = [mem.u8(addr + i) for i in range(size)]
    return None if None in vals else bytes(vals)


def page_of(mem, addr: int) -> bytes | None:
    base = addr & ~(PAGE - 1)
    for b, data in getattr(mem, "parts", []):
        if b <= base and base + PAGE <= b + len(data):
            return data[base - b:base - b + PAGE]
    return None


def fcram_offset(mem, addr: int, fcram: bytes) -> tuple[int, str]:
    """Where guest address addr sits in the savestate's FCRAM: the linear heap (0x30000000 + x = FCRAM + x) when
    the dumped page equals FCRAM's page there; else the one page-aligned place in FCRAM holding the dumped page."""
    page = page_of(mem, addr)
    if page is None:
        raise Stop(f"0x{addr:08X}: its page was not dumped at the poke frame")
    if LINEAR <= addr < LINEAR + len(fcram):
        off = addr - LINEAR
        base = off & ~(PAGE - 1)
        if fcram[base:base + PAGE] == page:
            return off, "linear heap (page checked)"
        raise Stop(f"0x{addr:08X}: the linear-heap page differs from FCRAM there (mapping not as assumed)")
    if page.count(0) == PAGE:
        raise Stop(f"0x{addr:08X}: an all-zero page cannot be found by its bytes")
    hits, at = [], fcram.find(page)
    while at >= 0 and len(hits) < 3:
        if at % PAGE == 0:
            hits.append(at)
        at = fcram.find(page, at + 1)
    if len(hits) != 1:
        raise Stop(f"0x{addr:08X}: its page occurs {len(hits)} times in FCRAM (need exactly once)")
    return hits[0] + (addr & (PAGE - 1)), "page search (unique)"


# ------------------------------------------------------------------ savestates
def split_state(data: bytes) -> tuple[bytes, list[bytes]]:
    """A Zakuro savestate (headless.state_sections' layout): the header and each section's raw bytes
    (u64 length, then u32 decoded size + an LZ4 block)."""
    if data[:8] != b"ZAKUROST":
        raise Stop("not a Zakuro savestate")
    vl = struct.unpack_from("<I", data, 8)[0]
    p = 12 + vl + 8
    head, secs = data[:p], []
    while p < len(data):
        cl = struct.unpack_from("<Q", data, p)[0]
        secs.append(data[p + 8:p + 8 + cl])
        if len(secs[-1]) != cl:
            raise Stop("savestate cut short")
        p += 8 + cl
    return head, secs


def lz4_literals(data: bytes) -> bytes:
    """One LZ4 block holding data as literals only (valid for any decoder; no match to get wrong)."""
    n = len(data)
    if n < 15:
        return bytes([n << 4]) + data
    rest, ext = n - 15, bytearray()
    ext += b"\xff" * (rest // 255)
    ext.append(rest % 255)
    return bytes([0xF0]) + bytes(ext) + data


def join_state(head: bytes, secs: list[bytes]) -> bytes:
    out = bytearray(head)
    for s in secs:
        out += struct.pack("<Q", len(s)) + s
    return bytes(out)


def decode_section(raw: bytes) -> bytes:
    sys.path.insert(0, HERE)
    import headless  # noqa: E402  (lz4_block)
    sys.path.remove(HERE)
    return headless.lz4_block(raw[4:], struct.unpack_from("<I", raw, 0)[0])


def apply(state: bytes, mem, pokes: list[dict]) -> tuple[bytes, list[dict]]:
    """The pokes of one frame applied to a savestate (section 1 = FCRAM); returns the new state and the record."""
    head, secs = split_state(state)
    orig = decode_section(secs[1])  # every check reads the state as saved (the dump's moment), not as patched
    fcram = bytearray(orig)
    finder = unit_finder_for(mem)
    done = []
    for p in pokes:
        addr, steps = resolve(mem, p["at"], finder)
        es = element_size(p["at"])
        if es is not None and es != p["size"]:
            raise Stop(f"{p['at']}: the field's element is {es} byte(s), the poke writes {p['size']}")
        old = read_bytes(mem, addr, p["size"])
        if old is None:
            raise Stop(f"{p['at']} = 0x{addr:08X}: not in the dump")
        old_v = int.from_bytes(old, "little")
        if p["expect"] is not None and old_v != p["expect"] % (1 << (8 * p["size"])):
            raise Stop(f"{p['at']} = 0x{addr:08X}: holds {old_v}, the route expects {p['expect']} (wrong place or "
                       f"wrong moment: nothing poked)")
        off, how = fcram_offset(mem, addr, orig)
        if orig[off:off + p["size"]] != old:
            raise Stop(f"0x{addr:08X}: FCRAM +0x{off:X} holds other bytes than the dump")
        value = p["value"]
        if p.get("value_from"):  # an address the game holds now (e.g. a unit's Person record), named by a path
            value, _ = resolve(mem, p["value_from"], finder)
        new = (value % (1 << (8 * p["size"]))).to_bytes(p["size"], "little")
        fcram[off:off + p["size"]] = new
        done.append({"frame": p["frame"], "at": p["at"], "why": p["why"], "address": f"0x{addr:08X}",
                     "fcram_offset": f"0x{off:08X}", "mapped": how, "size": p["size"], "old": old_v,
                     "new": int.from_bytes(new, "little"), "steps": steps,
                     **({"value_from": p["value_from"]} if p.get("value_from") else {})})
    secs[1] = struct.pack("<I", len(fcram)) + lz4_literals(bytes(fcram))
    return join_state(head, secs), done


# ------------------------------------------------------------------ staged runs (headless.run calls this)
def stage_plan(route: dict) -> list[dict]:
    """[{"until": F (exclusive end of the stage: boot.exe runs F + 1 frames, saving at F), "shots": [...],
    "pokes": [...]}, ..., {"until": None (the route's end), "shots": [...]}] for a cheat route."""
    plan, prev = [], 0
    shots = [int(s) for s in route["shots"]]
    for f, pokes in groups(route):
        plan.append({"until": f, "shots": [s for s in shots if prev < s <= f], "pokes": pokes})
        prev = f
    plan.append({"until": None, "shots": [s for s in shots if s > prev], "pokes": []})
    return plan


def run_stages(boot: str, rom: str, route: dict, env: dict, tmp_dir: str, run_dir: str, log_path: str,
               timeout: float, dump_ranges: list[tuple[int, int]], mode: str, say=print) -> tuple[int, str, list, list]:
    """Runs a cheat route stage by stage (module docstring). env: the run's boot.exe settings from headless.boot_env
    (and markers.dump_env when markers are read). Returns (exit code, the last stage's log text, the stages'
    numbers, the poke record)."""
    import subprocess
    import time
    sys.path.insert(0, HERE)
    import markers as mk  # noqa: E402
    sys.path.remove(HERE)
    plan = stage_plan(route)
    stages, record = [], []
    load = None
    rc, text = 1, ""
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        for k, st in enumerate(plan):
            e = dict(env)
            last = st["until"] is None
            frames = int(route["frames"]) if last else st["until"] + 1
            dump_at = sorted(set(st["shots"]) | (set() if last else {st["until"]}))
            if dump_at:
                e["ZAKURO_DUMP_AT"] = ",".join(str(f) for f in dump_at)
            else:
                e.pop("ZAKURO_DUMP_AT", None)
            if not last:
                state_k = os.path.join(tmp_dir, f"stage{k}.state")
                e["ZAKURO_SAVE_AT"] = f"{st['until']}:{state_k}"
                pages = sorted({a & ~(PAGE - 1) for p in st["pokes"] for a in static_bases(p["at"])})
                rngs = list(dump_ranges) + [(a, PAGE) for a in pages]
                e["ZAKURO_DUMP_MEM"] = ";".join(f"0x{a:08X},{n}" for a, n in rngs)
                e["ZAKURO_DUMP_MEM_AT"] = "1"
                if mode == "capture":
                    e["FE_CAPTURE_DIR"] = os.path.join(run_dir, f"stage{k}")
                    os.makedirs(e["FE_CAPTURE_DIR"], exist_ok=True)
            if load:
                e["ZAKURO_LOAD"] = load
            log.write(f"=== cheat stage {k}: frames {'from ' + str(plan[k - 1]['until']) if k else 'from 0'} to "
                      f"{frames}{' (poke frame ' + str(st['until']) + ')' if not last else ''} ===\n")
            log.flush()
            t0 = time.time()
            start_len = os.path.getsize(log_path)
            try:
                p = subprocess.run([boot, rom, str(frames)], cwd=tmp_dir, env=e, stdout=log, stderr=subprocess.STDOUT,
                                   timeout=timeout, creationflags=0x08000000 if os.name == "nt" else 0)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                rc = -1
            log.flush()
            with open(log_path, "rb") as fh:
                fh.seek(start_len)
                text = fh.read().decode("utf-8", "replace")
            loaded = re.search(r"loaded the state at frame (\d+)", text)
            stages.append({"stage": k, "frames": frames, "exit_code": rc, "seconds": round(time.time() - t0, 1),
                           "loaded_at": int(loaded.group(1)) if loaded else None,
                           "instructions": int(m.group(1)) if (m := re.search(r"^instructions:\s+(\d+)", text, re.M))
                           else None})
            if load:
                if not loaded or int(loaded.group(1)) != plan[k - 1]["until"]:
                    raise Stop(f"stage {k}: the patched state did not load at frame {plan[k - 1]['until']}")
                os.remove(load)
            if last or rc != 0:
                break
            if not os.path.isfile(state_k):
                raise Stop(f"stage {k}: no savestate at the poke frame {st['until']}")
            mem = mk.load_dumps(tmp_dir, st["until"])
            with open(state_k, "rb") as fh:
                state = fh.read()
            os.remove(state_k)
            patched, done = apply(state, mem, st["pokes"])
            del state
            for d in done:
                say(f"[cheat] frame {d['frame']}: {d['at']} = {d['address']} (FCRAM +{d['fcram_offset']}, "
                    f"{d['mapped']}): {d['old']} -> {d['new']}")
            record += done
            load = os.path.join(tmp_dir, f"stage{k}.patched")
            with open(load, "wb") as fh:
                fh.write(patched)
            del patched
            if st["until"] not in st["shots"]:  # the poke frame's own dumps (not a shot): gone now
                for f in glob.glob(os.path.join(tmp_dir, f"zakuro-dump-0x*-{st['until']}.bin")):
                    os.remove(f)
    return rc, text, stages, record


# ------------------------------------------------------------------ self-test (no game)
def selftest() -> tuple[list[str], str]:
    errors: list[str] = []
    checks = 0

    def ok(cond: bool, what: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            errors.append(f"cheats: {what}")

    sys.path.insert(0, HERE)
    import headless  # noqa: E402
    import markers as mk  # noqa: E402
    sys.path.remove(HERE)
    gl, st = layouts()
    ok("G_UnitPool" in gl and st["Unit"]["equip_skills"][:2] == (0xFE, 2), "layouts: globals and Unit.equip_skills (s16)")
    # invented memory: a static pointer page at 0x006D1000 -> a heap object in the linear heap
    fcram = bytearray(0x40000)
    heap_obj = LINEAR + 0x12340
    struct.pack_into("<I", fcram, 0x12340 + 8, LINEAR + 0x20000)          # obj+8 -> second object
    struct.pack_into("<I", fcram, 0x20000 + 0xD4, LINEAR + 0x21000)       # +0xD4 -> the ore bytes
    fcram[0x21000:0x2100C] = bytes(12)
    static_page = bytearray(PAGE)
    struct.pack_into("<I", static_page, 0x998, heap_obj)
    static_page[0:16] = b"static page 0001"                               # unique bytes for the page search
    fcram[0x30000:0x31000] = static_page                                  # the static page lives at FCRAM +0x30000
    mem = mk.Memory([(0x006D1000, bytes(static_page)), (LINEAR, bytes(fcram))])
    addr, steps = resolve(mem, "0x006D1998 * +0x8 * +0xD4 * +6")
    ok(addr == LINEAR + 0x21006 and len(steps) == 7, f"resolve follows pointers and offsets ({steps})")
    ok(fcram_offset(mem, addr, bytes(fcram)) == (0x21006, "linear heap (page checked)"), "linear heap mapping")
    ok(fcram_offset(mem, 0x006D1998, bytes(fcram)) == (0x30998, "page search (unique)"), "static page found by its bytes")
    for bad, why in (("* +4", "starts with *"), ("0x10 ++4", "bad token"), ("G_Nope *", "unknown global"),
                     ("0x006D1998 * Unit.nope", "unknown field"), ("0x006D1998 * Unit.equip_skills[5]", "index")):
        try:
            resolve(mem, bad)
            ok(False, f"refused: {why}")
        except Stop:
            ok(True, why)
    a2, _ = resolve(mem, "0x006D1998 * Unit.equip_skills[2]")
    ok(a2 == heap_obj + 0xFE + 4 and element_size("0x006D1998 * Unit.equip_skills[2]") == 2, "struct field with index")
    # a savestate with these sections; apply one poke, decode it again with headless's own reader
    meta = b"meta" * 10
    state = headless.fake_state(meta, [bytes(fcram), b"v" * 64, b"d" * 32, b"w" * 16])
    pk = {"frame": 100, "at": "0x006D1998 * +0x8 * +0xD4 * +6", "size": 1, "value": 1, "expect": 0, "why": "t"}
    new, done = apply(state, mem, [pk])
    ver, secs = headless.state_sections(new)
    ok(secs[1][0x21006] == 1 and secs[1][:0x21006] == bytes(fcram[:0x21006]) and secs[1][0x21007:] == bytes(fcram[0x21007:]),
       "apply writes exactly the poked byte into FCRAM")
    ok(secs[0] == meta and secs[2:] == [b"v" * 64, b"d" * 32, b"w" * 16], "the other sections stay byte for byte")
    ok(done[0]["old"] == 0 and done[0]["new"] == 1 and done[0]["address"] == f"0x{LINEAR + 0x21006:08X}",
       f"the poke is recorded ({done[0]})")
    new2, _ = apply(state, mem, [pk])
    ok(new2 == new, "applying the same poke to the same state gives the same bytes (replays repeat)")
    try:
        apply(state, mem, [dict(pk, expect=5)])
        ok(False, "a wrong expect is refused")
    except Stop:
        ok(True, "a wrong expect is refused")
    w = dict(pk, at="0x006D1998 * Unit.equip_skills[0]", size=2, value=0x77, expect=None)
    _, d2 = apply(state, mem, [w])
    ok(d2[0]["size"] == 2 and d2[0]["new"] == 0x77, "a 2-byte field poke")
    vf = dict(pk, at="0x006D1998 * +0x8 * +0xD4 * +8", size=4, value=None, value_from="0x006D1998 * +0x8 *", expect=0)
    _, d3 = apply(state, mem, [vf])
    ok(d3[0]["new"] == LINEAR + 0x20000, f"value_from writes the address a path names ({d3[0]['new']:#x})")
    two, d4 = apply(state, mem, [dict(pk, at="0x30021000", size=4, value=7, expect=None),
                                 dict(pk, at="0x30021004", size=4, value=9, expect=None)])
    ok(headless.state_sections(two)[1][1][0x21000:0x21008] == struct.pack("<II", 7, 9),
       "two pokes in one page (the page check reads the state as saved)")
    try:
        apply(state, mem, [dict(w, size=4)])
        ok(False, "a size that is not the field's is refused")
    except Stop:
        ok(True, "a size that is not the field's is refused")
    ok(lz4_literals(b"x" * 300) and headless.lz4_block(lz4_literals(b"x" * 300), 300) == b"x" * 300
       and headless.lz4_block(lz4_literals(b"x" * 270), 270) == b"x" * 270
       and headless.lz4_block(lz4_literals(b"ab"), 2) == b"ab", "literal-only LZ4 blocks decode (lengths 2, 270, 300)")
    # route rules
    good = {"frames": 100, "save_at": 90, "input": "1:A", "shots": [10], "cheat": True, "save": "bt-ch8-clear",
            "pokes": [{"frame": 50, "at": "unit:10 Unit.level", "size": 1, "value": 9}]}
    ok(check_routes({"cheat-a": good}) == [], "a good cheat route passes")
    rules = check_routes({"cheat-b": dict(good, cheat=False), "bt-x": dict(good, cheat=False, pokes=None, save="cheat-a"),
                          "cheat-c": dict(good, pokes=[dict(good["pokes"][0], frame=95)]), "cheat-d": dict(good, pokes=[]),
                          "x-e": dict(good)})
    ok(len(rules) == 6 and any("cheat save" in r for r in rules) and any("before save_at" in r for r in rules)
       and any("without pokes" in r for r in rules), f"the rules name every broken route ({rules})")
    plan = stage_plan(dict(good, shots=[10, 50, 60], pokes=[good["pokes"][0], dict(good["pokes"][0], frame=55)]))
    ok([(s["until"], s["shots"]) for s in plan] == [(50, [10, 50]), (55, []), (None, [60])], f"stage plan ({plan})")
    return errors, f"cheats self-test: {checks - len(errors)}/{checks} checks passed"


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        errs, line = selftest()
        for e in errs:
            print(f"  FAIL  {e}")
        print(line)
        return 1 if errs else 0
    if argv == ["--check"]:
        sys.path.insert(0, HERE)
        import headless  # noqa: E402
        try:
            routes = headless.load_routes()  # runs check_routes
        except headless.Stop as e:
            print(f"cheats: {e}")
            return 1
        cheat = {n: r for n, r in routes.items() if is_cheat(r)}
        for n, r in cheat.items():
            print(f"{n}: from {r.get('save')}, {len(parse_pokes(r))} poke(s): "
                  + "; ".join(f"frame {p['frame']} {p['at']} = {p['value_from'] or p['value']}" for p in parse_pokes(r)))
        # rule 3 on the zips themselves: a real-play route's start save (when packed here) carries no cheat state,
        # whatever its name (headless.save_is_cheat: the name, the cheat mark, or the save files of a cheat save)
        checked, tainted = 0, []
        for n, r in routes.items():
            zp = os.path.join(headless.SAVES, f"{r['save']}.zip") if r.get("save") and not is_cheat(r) else None
            if zp and os.path.isfile(zp):
                checked += 1
                why = headless.save_is_cheat(zp)
                if why:
                    tainted.append(f"route {n}: start save {r['save']} is a cheat save ({why})")
        for t in tainted:
            print(f"cheats: {t}")
        if tainted:
            return 1
        print(f"real-play start saves: {checked} packed one(s) checked, none carries cheat state")
        print(f"cheats: {len(cheat)} cheat route(s), rules OK")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
