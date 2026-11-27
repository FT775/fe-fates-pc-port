"""Round 50 read-only robot tests for the in-game randomizer (docs/RANDOMIZER_INGAME.md section 7, T1 and T3, plus a
guard dry run of a made patch against the game's real memory). Reads only: no pokes, no writer.

    python tools/randomizer/robot_ingame.py JOB PATCH RUN:SAVE:ROUTE:FIRST:LAST[:STEP] ...

For every frame FIRST..LAST (every STEP frames, default 1) of the recorded ROUTE started from SAVE it reads:
  - the MainSequence ProcInst (*0x006D88D4, first 0x40 bytes) and the GameConfigData word (*0x006DA0F8 +0..+0x10),
    the T1 candidates for "the mode was picked this frame";
  - GameData's data start by the patch's chain ([[*0x006D3868 + 4] + 112] + 32);
  - the placement object (*0x006D6DC8: name, ArchiveFile at +16, data at +20, data start by the same chain);
  - the unit pool's first unit of each force (0x006D9F40 +4), for T3 "units made in the frame the file loaded".
Every time GameData or a placement file is (newly) seen, its memory is compared with the original file (every byte that
is not a pointer slot; pointer slots: the label text) and the patch's guard is run dry for that file (every cell must
hold its original value). Results: build/rando50/robot/<JOB>.json. Servers run headless below build/rando50/server/
(headless.Server: data, APPDATA and LOCALAPPDATA there too).
"""
from __future__ import annotations

import json
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
sys.path.insert(0, HERE)
import server as sv  # noqa: E402
import ingame as IG  # noqa: E402

TOP = os.path.join(ROOT, "build", "rando50")
MAINSEQ, CONFIG, GD_ARCH, DISPOS, POOL = 0x006D88D4, 0x006DA0F8, 0x006D3868, 0x006D6DC8, 0x006D9F40


class Mem:
    def __init__(self, s):
        self.s = s

    def u32(self, a):
        if not a:
            return 0
        try:
            return struct.unpack("<I", self.s.peek1(a, 4))[0]
        except Exception:  # noqa: BLE001
            return 0

    def raw(self, a, n):
        try:
            return self.s.peek1(a, n) if a else b""
        except Exception:  # noqa: BLE001
            return b""

    def start(self, arch):
        a = self.u32(arch + 4) if arch else 0
        b = self.u32(a + 112) if a else 0
        return b + 32 if b else 0

    def cstr(self, a, n=64):
        b = self.raw(a, n)
        e = b.find(b"\0")
        return None if e < 0 else b[:e]


def compare_file(m: Mem, rel: str, base: int, gd_base: int, patch: dict | None) -> dict:
    """memory at base vs the original file; then the patch's guard, dry."""
    T = IG._T()
    c = T.container(rel)
    mem = m.raw(base, len(c.data))
    slots = set(c.b.relocs)
    plain_bad = [i for i in range(len(c.data)) if (i & ~3) not in slots and mem[i:i + 1] != c.data[i:i + 1]]
    ptr_bad = []
    for s in sorted(slots):
        v = c.u32(s)
        got = struct.unpack_from("<I", mem, s)[0]
        if v < c.se:
            if got != base + v:
                ptr_bad.append(s)
        elif m.cstr(got) != c.string_at(v):
            ptr_bad.append(s)
    out = {"rel": rel, "base": f"{base:08x}", "bytes": len(c.data), "plain_mismatch": len(plain_bad),
           "plain_first": [f"{i:#x}" for i in plain_bad[:5]], "pointer_mismatch": len(ptr_bad),
           "pointer_first": [f"{i:#x}" for i in ptr_bad[:5]], "pointer_slots": len(slots)}
    if patch is not None:
        f = next((f for f in patch["files"] if IG.os.path.basename(f["rel"]) == os.path.basename(rel)), None)
        if f is None:
            out["guard"] = "no cells in the patch"
        else:
            bad = 0
            for off, old, _new in f["v"]:
                bad += mem[off:off + len(old)] != old
            for off, old, _new, where, loff, _ooff in f["p"]:
                cur = struct.unpack_from("<I", mem, off)[0]
                bad += (cur != 0) if old is None else (m.cstr(cur) != old)
                if loff is not None:     # the new label must be where the patch says
                    bad += m.cstr((gd_base if where == "g" else base) + loff) != _new
            out["guard"] = {"cells": len(f["v"]) + len(f["p"]), "would_refuse": bad}
    return out


def dispos_rel(name: bytes) -> str | None:
    T = IG._T()
    stem = name.decode("ascii", "replace").split("/")[-1].split(".")[0]
    for top, _d, files in os.walk(os.path.join(T.ROMFS, "GameData", "Dispos")):
        for fn in files:
            if fn.split(".")[0].lower() == stem.lower():
                return os.path.relpath(os.path.join(top, fn), T.ROMFS).replace("\\", "/")
    return None


def run_one(job: str, patch: dict | None, spec: str) -> dict:
    parts = spec.split(":")
    name, save, route, first, last = parts[:5]
    first, last = int(first), int(last)
    step = int(parts[5]) if len(parts) > 5 else 1
    rin = json.load(open(os.path.join(ROOT, "config", "harness", "routes.json"), encoding="utf-8"))["routes"][route]["input"]
    inp = ",".join(x for x in rin.split(",") if x and int(x.split(":")[0]) <= last)
    out = {"run": name, "save": save, "route": route, "first": first, "last": last, "step": step, "events": [],
           "files": []}
    if os.path.exists(os.path.join(ROOT, "build", "STOP_ROUND")):
        out["stopped"] = "build/STOP_ROUND exists"
        return out
    t0 = time.time()
    with sv.Server(f"{job}-{name}", save=save, root=os.path.join(TOP, "server")) as s:
        s.inputs_set(inp)
        m = Mem(s)
        prev = {}
        seen_files = set()
        f = first
        s.step_to(first)
        while True:
            ms = m.u32(MAINSEQ)
            cfg = m.u32(CONFIG)
            gd = m.start(m.u32(GD_ARCH))
            dobj = m.u32(DISPOS)
            dname = m.cstr(dobj, 16) if dobj else None
            darch = m.u32(dobj + 16) if dobj else 0
            ddata = m.u32(dobj + 20) if dobj else 0
            dbase = m.start(darch) if darch else 0
            fp = m.u32(POOL + 4)
            heads = list(struct.unpack("<4I", m.raw(fp, 16))) if fp else []
            cur = {"mainseq": m.raw(ms, 0x40).hex() if ms else "", "config": m.raw(cfg, 0x10).hex() if cfg else "",
                   "gd": gd, "dispos": (dname.decode("ascii", "replace") if dname else None, darch, ddata, dbase),
                   "heads": heads}
            changed = [k for k in cur if prev.get(k) != cur[k]]
            if changed:
                ev = {"frame": f, "changed": changed}
                for k in changed:
                    ev[k] = cur[k] if k != "gd" else f"{cur[k]:08x}"
                out["events"].append(ev)
            if gd and ("gd", gd) not in seen_files:
                seen_files.add(("gd", gd))
                r = compare_file(m, IG.GAMEDATA_REL, gd, gd, patch)
                r["frame"] = f
                out["files"].append(r)
            if dname and dbase and (dname, dbase) not in seen_files:
                seen_files.add((dname, dbase))
                rel = dispos_rel(dname)
                if rel:
                    r = compare_file(m, rel, dbase, gd, patch)
                    r.update(frame=f, name=dname.decode("ascii", "replace"), data_field=f"{ddata:08x}")
                    out["files"].append(r)
                else:
                    out["files"].append({"frame": f, "name": dname.decode("ascii", "replace"), "rel": None})
            prev = cur
            if f >= last:
                break
            f = min(last, f + step)
            s.step_to(f)
        out["digest"] = s.state_digest()
    out["seconds"] = round(time.time() - t0, 1)
    return out


def main(argv):
    job, patch_path = argv[:2]
    patch = None if patch_path == "none" else IG.parse_patch(open(patch_path, encoding="ascii").read())
    res = {"job": job, "patch": patch_path, "runs": []}
    os.makedirs(os.path.join(TOP, "robot"), exist_ok=True)
    path = os.path.join(TOP, "robot", f"{job}.json")
    for spec in argv[2:]:
        res["runs"].append(run_one(job, patch, spec))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1)
    for r in res["runs"]:
        print(r["run"], r.get("stopped", ""), "events", len(r["events"]), "files", len(r["files"]), r.get("seconds"))
        for fl in r["files"]:
            print("  file", fl.get("frame"), fl.get("name", ""), fl.get("rel"), "plain", fl.get("plain_mismatch"),
                  "ptr", fl.get("pointer_mismatch"), "guard", fl.get("guard"))
    print("result:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
