#!/usr/bin/env python3
"""Check the Fates extras with the test robot: the same route with and without a patch.

Each variant is one headless run (boot.exe, the capture library in original mode, the route's own
start save) with a cheat file laid into the run's own data folder (ZAKURO_DATA/cheats/<title>.txt,
the extras named ON, built by tools/extras/native.py from config/extras/fe14.json). Runs go through
tools/harness/parallel.py's pool: the owner's budget (config/harness/resources.json: runs at once,
below-normal priority, memory), one Windows job object per run, %APPDATA% checked before and after.
Nothing is installed anywhere: the cheat file lives only in build/extras/robot/<session>/jobs/.

At every sample frame boot.exe dumps a few game globals (ZAKURO_DUMP_MEM_AT):
    GameTime 0x006DCA84 (+0 game frames, +4 vertical blanks, +0x10/+0x14/+0x18 step min/max/current),
    the battle world 0x006BC2F8 (BattleWorld::Get; non-zero during a 3D battle),
    the two random generators 0x00752B7C (system) and 0x00752B8C (game: RandomGetGame 0x003A8BC4),
    UnitPool 0x006D9F40, GameUserData 0x006DA248.
At the route's save frame the savestate gives the whole guest memory; the units of every force are
read from it (linear heap 0x30000000 = FCRAM offset 0, checked against a dumped page), and the
in-game save files the route wrote are hashed.

    python tools/extras/extras_robot.py compare --route bt-ch2 --variant off --variant fps60 \\
        --variant battle_speed --variant wide [--window 10200:11400:4] [--every 300] [--session NAME]
    python tools/extras/extras_robot.py compare --route bt-ch2 --variant off=+10500:A \\
        --variant fast=battle_speed+10500:A          # a variant may add inputs (here: A in the battle)
    python tools/extras/extras_robot.py --selftest

A variant is NAME=EXTRAS[@FROM][+FRAME:BUTTON...] or just EXTRAS (@FROM: the patch starts at that frame,
through a code-type-4 test on GameTime's vertical-blank count, so runs stay identical up to there) (ids from config/extras/fe14.json joined
by ',', or 'off'); --speed sets the Faster battles percent. The first variant is the reference.
Results: build/extras/robot/<session>/report.json (+ results/<run>.json, shots/<run>.png).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
HARNESS = os.path.join(ROOT, "tools", "harness")
OUT = os.path.join(ROOT, "build", "extras", "robot")
SELF = os.path.abspath(__file__)
sys.path.insert(0, HERE)
sys.path.append(HARNESS)
import native  # noqa: E402
import parallel  # noqa: E402  (tools/harness: Pool, Limits, Session, the %APPDATA% guard)

GAMETIME, WORLD, RNG, POOL, GUD = 0x006DCA84, 0x006BC2F8, 0x00752B7C, 0x006D9F40, 0x006DA248
HEAP = 0x30000000
DUMPS = [(GAMETIME, 0x20), (WORLD, 4), (RNG, 0x20), (POOL, 8), (GUD, 4), (HEAP, 0x1000)]
UNIT_SIZE = 0x140
VSYNC_LAG = 16  # GameTime's vertical-blank count = boot.exe frame - 16 on every route measured (ch2-a)
CREATE_NO_WINDOW = 0x08000000


def rmtree_own(path: str) -> None:
    """Deletes a folder of ours only (below build/extras/robot/)."""
    if not below(path, OUT) or os.path.abspath(path) == os.path.abspath(OUT):
        raise SystemExit(f"refusing to delete {path}: not below {OUT}")
    shutil.rmtree(path)


def rel(p: str) -> str:
    return os.path.relpath(p, ROOT).replace("\\", "/")


def below(p: str, top: str) -> bool:
    p, top = os.path.abspath(p), os.path.abspath(top)
    return os.path.commonpath([p, top]) == top


# ------------------------------------------------------------------ variants
def parse_variant(spec: str, ids: set[str]) -> dict:
    name, _, body = spec.partition("=") if "=" in spec else (None, "", spec)
    parts = body.split("+")
    head, _, at = parts[0].partition("@")
    gate = int(at) if at else None
    extras = [] if head in ("", "off") else head.split(",")
    for e in extras:
        if e not in ids:
            raise SystemExit(f"error: variant {spec}: no extra {e!r} (known: {', '.join(sorted(ids))})")
    inputs = parts[1:]
    for i in inputs:
        if not re.fullmatch(r"\d+:([A-Z]+|@\d+x\d+)", i):
            raise SystemExit(f"error: variant {spec}: input {i!r} is not FRAME:BUTTON or FRAME:@XxY (a touch)")
    if name is None:
        name = ("-".join(extras) or "off") + (f"-from{gate}" if gate else "")
        if inputs:
            name += "-in" + "-".join(re.sub(r"[:@]", "", i) for i in inputs)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise SystemExit(f"error: variant name {name!r}: letters, digits, _ . - only")
    return {"name": name, "extras": extras, "inputs": inputs, "from_frame": gate}


def merge_inputs(route_input: str, extra: list[str], frames: int | None = None) -> str:
    """The route's inputs plus extra ones, in frame order; an extra input on a frame the route already
    uses is refused (boot.exe holds one entry per frame), inputs at or after frames are dropped."""
    items = [x for x in route_input.split(",") if x]
    used = {int(x.split(":")[0]) for x in items}
    for x in extra:
        if int(x.split(":")[0]) in used:
            raise SystemExit(f"error: input {x}: the route already has an input on that frame")
    items = sorted(items + extra, key=lambda x: int(x.split(":")[0]))
    return ",".join(x for x in items if frames is None or int(x.split(":")[0]) < frames)


def sample_frames(route: dict, window: tuple[int, int, int] | None, every: int) -> list[int]:
    end = route["save_at"]
    fr = set(range(every, end, every)) if every else set()
    if window:
        a, b, s = window
        fr |= set(range(a, min(b, end), s))
    fr.add(end)
    fr |= {f for f in route.get("shots", []) if f <= end}
    return sorted(f for f in fr if f > 0)


# ------------------------------------------------------------------ the worker (one run)
def read_dump(tmp: str, addr: int, frame: int) -> bytes | None:
    p = os.path.join(tmp, f"zakuro-dump-0x{addr:08X}-{frame}.bin")
    try:
        with open(p, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def sample(tmp: str, frame: int) -> dict | None:
    gt = read_dump(tmp, GAMETIME, frame)
    if not gt or len(gt) < 0x20:
        return None
    v = struct.unpack("<8I", gt)
    w = read_dump(tmp, WORLD, frame)
    rng = read_dump(tmp, RNG, frame) or b""
    return {"tick": v[0], "vsync": v[1], "step_min": v[4], "step_max": v[5], "step": v[6], "accum": v[7],
            "battle": bool(w and struct.unpack("<I", w)[0]),
            "rng_system": hashlib.sha1(rng[0:0x10]).hexdigest()[:12],
            "rng_game": hashlib.sha1(rng[0x10:0x20]).hexdigest()[:12]}


def thumb(path: str) -> str | None:
    sys.path.insert(0, HARNESS)
    import harness  # noqa: E402  (read_ppm)
    try:
        w, h, px = harness.read_ppm(path)
    except (OSError, ValueError):
        return None
    out = bytearray()
    for y in range(5, h, 10):
        for x in range(5, w, 10):
            o = (y * w + x) * 3
            out.append((px[o] + 2 * px[o + 1] + px[o + 2]) // 4)
    return out.hex()


def units_from_fcram(fcram: bytes, forces: int) -> list[dict]:
    def u32(a):
        o = a - HEAP
        return struct.unpack_from("<I", fcram, o)[0] if 0 <= o <= len(fcram) - 4 else None
    out = []
    if not forces:
        return out
    for force in range(3):
        unit, n = u32(forces + 12 * force), 0
        while unit and n < 256:
            o = unit - HEAP
            if not 0 <= o <= len(fcram) - UNIT_SIZE:
                break
            b = fcram[o:o + UNIT_SIZE]
            out.append({"force": force, "x": b[0xF4], "y": b[0xF5], "hp": b[0xF3],
                        "flags": f"{struct.unpack_from('<I', b, 8)[0]:08X}",
                        "sha1": hashlib.sha1(b).hexdigest()[:16], "raw": b.hex()})
            unit, n = struct.unpack_from("<I", b, 0x14)[0], n + 1
    return out


def masked(raw: bytes) -> bytes:
    """A unit's bytes with every aligned word that points into the linear heap zeroed: where the game
    allocated an object (a map actor after a battle) is not game state, and patches that change
    timing change it."""
    b = bytearray(raw)
    for i in range(0, len(b) - 3, 4):
        if HEAP <= struct.unpack_from("<I", b, i)[0] < HEAP + 0x08000000:
            b[i:i + 4] = bytes(4)
    return bytes(b)


def units_digest(units: list[dict]) -> str:
    h = hashlib.sha1()
    for u in units:
        h.update(masked(bytes.fromhex(u["raw"])))
    return h.hexdigest()[:16]


def save_files(data_dir: str) -> dict:
    out = {}
    user = os.path.join(data_dir, "user")
    for root, _d, names in os.walk(user):
        for n in sorted(names):
            p = os.path.join(root, n)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, user).replace("\\", "/")] = hashlib.sha256(fh.read()).hexdigest()[:16]
    return out


def worker(spec_path: str) -> int:
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    sys.stdin.readline()  # the pool's "go": we are in our job object now
    root = spec["root"]
    if not below(root, OUT):
        print(f"worker: {root} is not below {rel(OUT)}")
        return 3
    hl = parallel.headless_module()
    hl.BUILD = root
    hl.LOCALAPPDATA = os.path.join(root, "localappdata")
    route = spec["route"]
    data_dir, tmp, run_dir = (os.path.join(root, d) for d in ("data", "tmp", "runs"))
    for d in (data_dir, tmp, run_dir):
        os.makedirs(d, exist_ok=True)
    out = {"spec": spec}
    try:
        rom = hl.find_rom()
        out["dlc_beside_rom"] = hl.refuse_cias(rom)
        laid = hl.lay_save(spec["save"], data_dir)
        out["save_files_in"] = laid
        out["save_files_start"] = save_files(data_dir)
        cheats = os.path.join(data_dir, "cheats", f"{hl.TITLE}.txt")
        os.makedirs(os.path.dirname(cheats), exist_ok=True)
        with open(cheats, "w", encoding="utf-8") as fh:
            fh.write(spec["cheat_text"])
        state_file = os.path.join(tmp, "state.bin")
        env = hl.boot_env(route, data_dir, tmp, run_dir, "original", "ab", True, spec["lib"], state_file)
        env["ZAKURO_DUMP_MEM"] = ";".join(f"0x{a:08X},{n}" for a, n in DUMPS)
        env["ZAKURO_DUMP_MEM_AT"] = "1"
        env["RUST_LOG"] = "zakuro_core::cheats=info,zakuro_core::loader=info"
    except hl.Stop as e:
        out["setup_error"] = str(e)
        with open(spec["result"], "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
        print(f"SETUP: {e}")
        return 3
    log_path = os.path.join(run_dir, "boot.log")
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        try:
            p = subprocess.run([spec["boot"], rom, str(route["frames"])], cwd=tmp, env=env, stdout=log,
                               stderr=subprocess.STDOUT, timeout=spec["timeout"],
                               creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = -1
    text = open(log_path, encoding="utf-8", errors="replace").read()
    m = re.search(r"outcome:\s+(\w+) after (\d+) frames", text)
    ins = re.search(r"^instructions:\s+(\d+)", text, re.M)
    out.update(exit_code=rc, seconds=round(time.time() - t0, 1), outcome=m.group(1) if m else None,
               frames=int(m.group(2)) if m else None, instructions=int(ins.group(1)) if ins else None,
               cheat_log=[ln.strip() for ln in text.splitlines() if "cheat" in ln.lower() or "interpreter" in ln][:12])
    out["samples"] = {str(f): s for f in spec["samples"] if (s := sample(tmp, f))}
    for f, s in out["samples"].items():  # a 40x24 grey thumbnail of the top screen (build/ only), to line runs up
        s["thumb"] = thumb(os.path.join(tmp, f"zakuro-top-{f}.ppm"))
    end = route["save_at"]
    if os.path.isfile(state_file):
        with open(state_file, "rb") as fh:
            data = fh.read()
        version, secs = hl.state_sections(data)
        del data
        out["state"] = hl.sections_digest(version, secs, [data_dir, spec["run"]])
        fcram = secs[1]
        page = read_dump(tmp, HEAP, end)
        out["heap_map_checked"] = bool(page) and fcram[:len(page)] == page
        pool = read_dump(tmp, POOL, end)
        ptr = struct.unpack("<I", pool[4:8])[0] if pool else 0  # UnitPool+4: the forces
        units = units_from_fcram(fcram, ptr) if out["heap_map_checked"] else []
        out["units"] = units  # raw bytes are game state (heap), kept in gitignored build/ only
        out["units_sha1"] = units_digest(units)
        gud = read_dump(tmp, GUD, end)
        if gud and out["heap_map_checked"]:
            g = struct.unpack("<I", gud)[0] - HEAP
            if 0 <= g <= len(fcram) - 0x80:
                out["game_user_data_sha1"] = hashlib.sha1(fcram[g:g + 0x80]).hexdigest()[:16]
        del secs, fcram
        os.remove(state_file)
    out["save_files_out"] = save_files(data_dir)
    sheet = hl.contact_sheet(tmp, spec.get("sheet_frames", []), os.path.join(root, "shots", "sheet.png"))
    out["sheet"] = sheet
    shutil.rmtree(tmp, ignore_errors=True)
    with open(spec["result"], "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return 0 if rc == 0 and "state" in out else 1


# ------------------------------------------------------------------ analysis
def battles(samples: dict) -> list[dict]:
    """Stretches of sample frames with the battle world alive: first and last frame seen, and the
    game frames per vertical blank inside (1.0 = 60 fps, 0.5 = 30 fps)."""
    fr = sorted(int(f) for f in samples)
    out, cur = [], None
    for f in fr:
        s = samples[str(f)]
        if s["battle"] and cur is None:
            cur = {"first": f, "last": f, "steps": set()}
        if s["battle"]:
            cur["last"] = f
            cur["steps"].add(s["step"])
        elif cur is not None:
            cur["ended_by"] = f
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    for b in out:
        a, z = samples[str(b["first"])], samples[str(b["last"])]
        dv = z["vsync"] - a["vsync"]
        b["ticks_per_vblank"] = round((z["tick"] - a["tick"]) / dv, 3) if dv else None
        b["frames"] = b["last"] - b["first"]
        b["steps"] = sorted(b["steps"])
    return out


def map_rate(samples: dict) -> float | None:
    fr = sorted(int(f) for f in samples)
    pairs = [(a, b) for a, b in zip(fr, fr[1:]) if not samples[str(a)]["battle"] and not samples[str(b)]["battle"]]
    t = sum(samples[str(b)]["tick"] - samples[str(a)]["tick"] for a, b in pairs)
    v = sum(samples[str(b)]["vsync"] - samples[str(a)]["vsync"] for a, b in pairs)
    return round(t / v, 3) if v else None


def compare(ref: dict, other: dict) -> dict:
    """What changed against the reference run."""
    rb, ob = battles(ref.get("samples", {})), battles(other.get("samples", {}))
    out = {"battles": len(ob), "battles_ref": len(rb),
           "battle_frames": [b["frames"] for b in ob], "battle_frames_ref": [b["frames"] for b in rb],
           "battle_starts": [b["first"] for b in ob], "battle_starts_ref": [b["first"] for b in rb],
           "ticks_per_vblank_in_battle": [b["ticks_per_vblank"] for b in ob],
           "ticks_per_vblank_in_battle_ref": [b["ticks_per_vblank"] for b in rb],
           "map_ticks_per_vblank": map_rate(other.get("samples", {})),
           "map_ticks_per_vblank_ref": map_rate(ref.get("samples", {}))}
    out["save_files_same"] = ref.get("save_files_out") == other.get("save_files_out")
    out["save_written"] = sorted(k for k, v in (ref.get("save_files_out") or {}).items()
                                 if v != (ref.get("save_files_start") or {}).get(k))
    out["units_same"] = ref.get("units_sha1") == other.get("units_sha1")
    out["units_count"] = [len(ref.get("units") or []), len(other.get("units") or [])]
    out["units_raw_same"] = [u["raw"] for u in ref.get("units") or []] == [u["raw"] for u in other.get("units") or []]
    out["game_user_data_same"] = ref.get("game_user_data_sha1") == other.get("game_user_data_sha1")
    rs, os_ = ref.get("samples", {}), other.get("samples", {})
    common = sorted(set(rs) & set(os_), key=int)
    out["rng_game_same_at_end"] = bool(common) and rs[common[-1]]["rng_game"] == os_[common[-1]]["rng_game"]
    out["rng_game_first_diff"] = next((int(f) for f in common if rs[f]["rng_game"] != os_[f]["rng_game"]), None)
    out["memory_same"] = (ref.get("state") or {}).get("memory") == (other.get("state") or {}).get("memory")
    if not out["units_same"] and ref.get("units") and other.get("units"):
        diffs = []
        for a, b in zip(ref["units"], other["units"]):
            if a != b:
                ra, rb = bytes.fromhex(a["raw"]), bytes.fromhex(b["raw"])
                ma, mb = masked(ra), masked(rb)
                offs = [i for i in range(min(len(ra), len(rb))) if ma[i] != mb[i]]
                if not offs:
                    continue
                diffs.append({"force": a["force"], "x": a["x"], "y": a["y"], "hp": a["hp"], "hp_this": b["hp"],
                              "bytes": {f"0x{i:03X}": [ra[i], rb[i]] for i in offs[:24]}})
        out["unit_diffs"] = diffs[:8]
    return out


# ------------------------------------------------------------------ the session
def run_compare(a) -> int:
    cfg = native.load_config()
    ids = {e["id"] for e in cfg["extras"]}
    variants = [parse_variant(v, ids) for v in a.variant]
    if len({v["name"] for v in variants}) != len(variants):
        raise SystemExit("error: two variants have the same name")
    limits = parallel.load_limits(cli_jobs=a.jobs)
    sess_name = a.session or f"{a.route}-{time.strftime('%Y%m%d-%H%M%S')}"
    sess = parallel.Session(sess_name, None, keep=a.keep)
    sess.dir = os.path.join(OUT, sess_name)
    if os.path.isdir(sess.dir):
        rmtree_own(sess.dir)
    sess.stage()
    if a.route not in sess.routes:
        raise SystemExit(f"error: no route {a.route}")
    base = dict(sess.routes[a.route])
    if a.until:
        if a.until >= base["frames"]:
            raise SystemExit("error: --until must be before the route's end")
        base["frames"], base["save_at"] = a.until + 10, a.until
        base["shots"] = [f for f in base.get("shots", []) if f < a.until]
    window = tuple(int(x) for x in a.window.split(":")) if a.window else None
    samples = sample_frames(base, window, a.every)
    sheet = sorted(set(int(x) for x in a.sheet.split(","))) if a.sheet else \
        [f for f in base.get("shots", []) if f in samples][:8]
    jobs = []
    for v in variants:
        route = dict(base)
        route["input"] = merge_inputs(base["input"], v["inputs"], base["frames"])
        route["shots"] = samples
        job = sess.job(v["name"], a.route, route, info={"variant": v["name"]}, timeout=a.timeout)
        spec_path = os.path.join(sess.dir, "jobs", v["name"], "spec.json")
        with open(spec_path, encoding="utf-8") as fh:
            spec = json.load(fh)
        spec.update(route=route, samples=samples, sheet_frames=[f for f in sheet if f in samples],
                    cheat_text=native.cheat_text(cfg, a.speed, set(v["extras"]),
                                                gate=None if v["from_frame"] is None else v["from_frame"] - VSYNC_LAG), extras=v["extras"],
                    inputs=v["inputs"], speed=a.speed)
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, indent=1)
        job.cmd = [sys.executable, SELF, "--worker", spec_path]
        jobs.append(job)
    before = parallel.snapshot(parallel.appdata_dirs())
    t0 = time.time()
    pool = parallel.Pool(limits, mem_per_run_gb=1.5, reserve_gb=2.0)
    print(f"[{sess_name}] {len(jobs)} run(s) of {a.route} ({len(samples)} sample frames), up to {limits.jobs} at once, "
          f"{limits.priority}, budget {limits.mem_gb:g} GB")
    results = pool.run(jobs)
    changed = parallel.snapshot_diff(before, parallel.snapshot(parallel.appdata_dirs()))
    runs = {}
    for r in results:
        res = (r.get("result") or {})
        res.pop("spec", None)
        res["pool"] = {k: r[k] for k in ("exit_code", "killed", "wall_seconds", "peak_mem_mb")}
        runs[r["name"]] = res
        os.makedirs(os.path.join(sess.dir, "results"), exist_ok=True)
        with open(os.path.join(sess.dir, "results", f"{r['name']}.json"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1)
        png = os.path.join(sess.dir, "jobs", r["name"], "shots", "sheet.png")
        if os.path.isfile(png):
            os.makedirs(os.path.join(sess.dir, "shots"), exist_ok=True)
            shutil.copy2(png, os.path.join(sess.dir, "shots", f"{r['name']}.png"))
    ref = variants[0]["name"]
    report = {"session": sess_name, "route": a.route, "until": a.until, "speed": a.speed,
              "wall_seconds": round(time.time() - t0, 1), "limits": limits.as_dict(), "pool": pool.stats(),
              "appdata_unchanged": not changed, "appdata_changed": changed[:10], "reference": ref,
              "variants": variants, "runs": {}, "compare": {}}
    for v in variants:
        r = runs.get(v["name"], {})
        bt = battles(r.get("samples", {}))
        report["runs"][v["name"]] = {
            "exit_code": r.get("exit_code"), "outcome": r.get("outcome"), "frames": r.get("frames"),
            "seconds": r.get("seconds"), "instructions": r.get("instructions"),
            "memory": (r.get("state") or {}).get("memory"), "units_sha1": r.get("units_sha1"),
            "units": len(r.get("units") or []), "heap_map_checked": r.get("heap_map_checked"),
            "save_files_out": r.get("save_files_out"), "battles": bt, "map_ticks_per_vblank": map_rate(r.get("samples", {})),
            "cheat_log": r.get("cheat_log"), "setup_error": r.get("setup_error"), "peak_mem_mb": r.get("pool", {}).get("peak_mem_mb")}
        if v["name"] != ref and ref in runs:
            report["compare"][v["name"]] = compare(runs[ref], r)
    with open(os.path.join(sess.dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=list)
    for d in ("bin", "lib") + (() if a.keep else ("jobs",)):
        p = os.path.join(sess.dir, d)
        if os.path.isdir(p):
            rmtree_own(p)
    for n, r in report["runs"].items():
        bt = r["battles"]
        print(f"  {n:<22} exit {r['exit_code']} {r['outcome']} {r['frames']} frames {r['seconds']} s, "
              f"map {r['map_ticks_per_vblank']} game frames/vblank, {len(bt)} battle(s): "
              + ", ".join(f"{b['first']}-{b['last']} ({b['frames']} f, {b['ticks_per_vblank']}/vbl, step {b['steps']})" for b in bt))
    for n, c in report["compare"].items():
        print(f"  {n} vs {ref}: battle frames {c['battle_frames']} vs {c['battle_frames_ref']}; save files "
              f"{'same' if c['save_files_same'] else 'DIFFER'} (written by the route: {', '.join(c['save_written']) or 'none'}); units {'same' if c['units_same'] else 'DIFFER'}; "
              f"game RNG at end {'same' if c['rng_game_same_at_end'] else 'DIFFERS (first at ' + str(c['rng_game_first_diff']) + ')'}; "
              f"whole memory {'same' if c['memory_same'] else 'differs'}")
    print(f"[{sess_name}] %APPDATA% (zakuro, 3dsrecomp) {'unchanged' if not changed else 'CHANGED'}; report {rel(os.path.join(sess.dir, 'report.json'))}")
    ok = all(r.get("exit_code") == 0 for r in runs.values()) and len(runs) == len(variants) and not changed
    if a.check:
        problems = check_verdict(report)
        report["check"] = problems or "all met"
        with open(os.path.join(sess.dir, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1, default=list)
        for p in problems:
            print("  CHECK FAILED:", p)
        print(f"[{sess_name}] check: {'all met' if not problems else str(len(problems)) + ' failed'}")
        ok = ok and not problems
    return 0 if ok else 1


def check_verdict(report: dict) -> list[str]:
    """The rules an extra must keep (docs/EXTRAS.md): against the reference run (all extras off), the units,
    the game's random generator and the save files are the same at the end; with fps60 the last battle runs
    at one game frame per vertical blank and lasts within 5% of the reference (no faster logic); with
    battle_speed it is shorter than the reference; wide changes no battle length."""
    out = []
    ref = report["reference"]
    rb = report["runs"].get(ref, {}).get("battles") or []
    if not rb:
        return [f"{ref}: no battle seen"]
    rlen = rb[-1]["frames"]
    for v in report["variants"]:
        n = v["name"]
        if n == ref:
            continue
        c = report["compare"].get(n)
        if not c:
            out.append(f"{n}: no result")
            continue
        for key, what in (("units_same", "units"), ("rng_game_same_at_end", "game random generator"),
                          ("save_files_same", "save files")):
            if not c.get(key):
                out.append(f"{n}: {what} differ from {ref}")
        bt = report["runs"][n].get("battles") or []
        if not bt:
            out.append(f"{n}: no battle seen")
            continue
        last = bt[-1]
        if any(x.startswith(("A", "B", "Y")) or "@" in x for x in [i.split(":")[1] for i in v["inputs"]]):
            continue  # a battle button was pressed: its length is the button's, not the extra's
        if "fps60" in v["extras"]:
            if last["ticks_per_vblank"] != 1.0:
                out.append(f"{n}: last battle at {last['ticks_per_vblank']} game frames per vertical blank, not 1.0")
            if "battle_speed" not in v["extras"] and abs(last["frames"] - rlen) > 0.05 * rlen:
                out.append(f"{n}: last battle {last['frames']} frames vs {rlen}: more than 5% apart")
        if "battle_speed" in v["extras"] and report["speed"] > 100 and last["frames"] >= rlen:
            out.append(f"{n}: battle_speed {report['speed']}% did not shorten the battle ({last['frames']} vs {rlen})")
        if v["extras"] == ["wide"] and last["frames"] != rlen:
            out.append(f"{n}: wide changed the battle length ({last['frames']} vs {rlen})")
    return out


# ------------------------------------------------------------------ self-test (no game)
def selftest() -> int:
    fails = []

    def ok(c, what):
        print(("ok   " if c else "FAIL ") + what)
        if not c:
            fails.append(what)

    ids = {"fps60", "battle_speed", "wide"}
    v = parse_variant("fast=battle_speed+10500:A", ids)
    ok(v == {"name": "fast", "extras": ["battle_speed"], "inputs": ["10500:A"], "from_frame": None},
       "variant with a name and an input")
    g = parse_variant("fps60@10300", ids)
    ok(g["from_frame"] == 10300 and g["name"] == "fps60-from10300", "variant switched on from a frame")
    ok(parse_variant("off", ids)["extras"] == [] and parse_variant("fps60,wide", ids)["name"] == "fps60-wide", "plain variants")
    ok(merge_inputs("300:A,700:B", ["500:X"]) == "300:A,500:X,700:B", "inputs merged in frame order")
    r = {"save_at": 1000, "shots": [100, 2000]}
    ok(sample_frames(r, (400, 500, 50), 300) == [100, 300, 400, 450, 600, 900, 1000], "sample frames")
    mk = lambda tick, vs, b, step=1: {"tick": tick, "vsync": vs, "battle": b, "step": step, "rng_game": "x", "rng_system": "y"}  # noqa: E731
    s = {"10": mk(10, 10, False), "20": mk(20, 20, True, 2), "40": mk(30, 40, True, 2), "60": mk(40, 60, True, 2),
         "80": mk(60, 80, False), "100": mk(80, 100, False)}
    bt = battles(s)
    ok(len(bt) == 1 and bt[0]["first"] == 20 and bt[0]["last"] == 60 and bt[0]["ticks_per_vblank"] == 0.5
       and bt[0]["ended_by"] == 80, "battle stretch and 30 fps inside it")
    ok(map_rate(s) == 1.0, "map rate from map-only pairs")
    fc = bytearray(0x10000)
    struct.pack_into("<I", fc, 0x200, 0x30000400)          # force 0 first unit
    fc[0x400 + 0xF4], fc[0x400 + 0xF5], fc[0x400 + 0xF3] = 3, 4, 17
    us = units_from_fcram(bytes(fc), 0x30000200)
    ok(len(us) == 1 and (us[0]["x"], us[0]["y"], us[0]["hp"]) == (3, 4, 17), "units read from FCRAM")
    try:
        parse_variant("nope", ids)
        ok(False, "unknown extra refused")
    except SystemExit:
        ok(True, "unknown extra refused")
    print(f"{'PASS' if not fails else 'FAIL'}: {len(fails)} failure(s)")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--worker"]:
        return worker(argv[1])
    if argv[:1] == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--route", required=True)
    c.add_argument("--variant", action="append", required=True)
    c.add_argument("--speed", type=int, default=150)
    c.add_argument("--window", help="FROM:TO:STEP dense sample frames")
    c.add_argument("--every", type=int, default=300, help="a sample every N frames over the whole route")
    c.add_argument("--until", type=int, help="stop the route here (its save frame)")
    c.add_argument("--sheet", help="frames for the contact sheet (default: the route's shots)")
    c.add_argument("--jobs", type=int)
    c.add_argument("--timeout", type=float, default=900)
    c.add_argument("--session")
    c.add_argument("--keep", action="store_true")
    c.add_argument("--check", action="store_true", help="exit 1 unless the extras keep the rules (check_verdict)")
    a = ap.parse_args(argv)
    return run_compare(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
