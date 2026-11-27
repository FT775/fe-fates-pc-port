"""Robot check of a randomizer mod in the robot's OWN test game (F-037 style; docs/RANDOMIZER.md section 5).

    python tools/randomizer/robot_check.py JOB ZAKDIR PLAN RUN:SAVE:ROUTE:LAST:READS[:END] ...

JOB     a name for this job (results in build/rando/robot/<JOB>.json)
ZAKDIR  a robot Zakuro data folder whose mods/ was filled by `tools/mods/mods.py --zakuro-dir ZAKDIR install`
        (copied into each run's own server data folder), or "none" for no mod at all
PLAN    the mod folder's plan.json (the expected values) or "vanilla" (expect the original tables)
RUN...  one or more runs: name, start save (new-game-empty / bt-ch1-clear), recorded route whose presses are
        used up to frame LAST, the frames at which memory is read ("/"-separated), and the end frame (default
        the last read). A digest (whole-memory hash) is taken at the end frame of every run.

Reads only (no pokes, no writer): the unit pool (UnitPool 0x006D9F40: +4 forces, 12 bytes each, first unit,
Unit +0x14 next; Unit +0x9C Person, +0xA0 Job, +0xC8 s8[8] gains, +0xF1 level) and the Person records in memory
(Person::Get: block + 0x10 + index * 0x98, found from the first unit's Person and its pid_number). Every server
runs below build/rando/server/ with its own data folder (headless.Server: APPDATA/LOCALAPPDATA redirected too).
Never the owner's %APPDATA%, saves, mods or settings.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
sys.path.insert(0, HERE)
import headless as hl  # noqa: E402
import server as sv  # noqa: E402
import randolib as R  # noqa: E402

TOP = os.path.join(ROOT, "build", "rando")
POOL = 0x006D9F40
PREC = 0x98


def s8(b: int) -> int:
    return b - 256 if b > 127 else b


class Reader:
    def __init__(self, s):
        self.s = s

    def u32(self, a):
        return struct.unpack("<I", self.s.peek1(a, 4))[0]

    def u16(self, a):
        return struct.unpack("<H", self.s.peek1(a, 2))[0]

    def cstr(self, a):
        if not a:
            return ""
        b = self.s.peek1(a, 48).split(b"\0")[0]
        for enc in ("utf-8", "cp932"):
            try:
                return b.decode(enc)
            except UnicodeDecodeError:
                pass
        return b.hex()

    def person(self, a):
        b = self.s.peek1(a, PREC)
        return {"addr": f"{a:08x}", "pid": self.cstr(struct.unpack_from("<I", b, 8)[0]),
                "index": struct.unpack_from("<H", b, 0x24)[0], "job": struct.unpack_from("<H", b, 0x2C)[0],
                "job_low": struct.unpack_from("<H", b, 0x2E)[0], "base": [s8(x) for x in b[0x38:0x40]],
                "growth": [s8(x) for x in b[0x40:0x48]], "wexp": list(b[0x60:0x68])}

    def units(self, forces=(0, 1, 2, 3)):
        fp = self.u32(POOL + 4)
        out = []
        for f in forces:
            u, n = self.u32(fp + 12 * f), 0
            while u and n < 120:
                n += 1
                ub = self.s.peek1(u, 0x140)
                per, job = struct.unpack_from("<II", ub, 0x9C)
                pb = self.s.peek1(per, PREC)
                jb = self.s.peek1(job, 0x80)
                gain = [s8(x) for x in ub[0xC8:0xD0]]
                pbase, jbase = [s8(x) for x in pb[0x38:0x40]], [s8(x) for x in jb[0x1C:0x24]]
                out.append({"force": f, "unit": f"{u:08x}", "person": f"{per:08x}",
                            "pid": self.cstr(struct.unpack_from("<I", pb, 8)[0]),
                            "pid_number": struct.unpack_from("<H", pb, 0x24)[0],
                            "job": struct.unpack_from("<H", jb, 0x18)[0], "jid": self.cstr(struct.unpack_from("<I", jb, 8)[0]),
                            "level": ub[0xF1], "x": ub[0xF4], "y": ub[0xF5], "hp_now": ub[0xF3],
                            "gain": gain, "person_base": pbase, "job_base": jbase,
                            "raw_stats": [a + b + c for a, b, c in zip(pbase, jbase, gain)]})
                u = struct.unpack_from("<I", ub, 0x14)[0]
        return out


def expected(plan_path: str, facts) -> dict:
    """{person index: {"job", "job_low", "base", "growth", "wexp"}} for every person the plan covers."""
    jix = {lab: R.ival(j["index"]) for lab, j in facts.jobs.items()}
    out = {}
    if plan_path == "vanilla":
        for p in facts.persons:
            if facts.in_scope(p):
                out[R.ival(p["index"])] = {"pid": p["label"], "job": jix[p["job"]], "job_low": jix[p["job_low"]],
                                           "base": [R.ival(p[f"base.{s}"]) for s in R.STATS],
                                           "growth": [R.ival(p[f"growth.{s}"]) for s in R.STATS],
                                           "wexp": [R.ival(p[f"weapon_exp.{k}"]) for k in R.KINDS]}
        return out
    with open(plan_path, encoding="utf-8") as fh:
        plan = json.load(fh)
    for e in plan["persons"]:
        out[e["index"]] = {"pid": e["pid"], "job": jix[e["job"]], "job_low": jix[e["job_low"]], "base": e["base"],
                           "growth": e["growth"], "wexp": e["wexp"]}
    return out


def compare_persons(rd: Reader, first_unit_person: int, exp: dict) -> dict:
    p0 = rd.person(first_unit_person)
    rec0 = first_unit_person - p0["index"] * PREC
    rows, bad = [], []
    for ix, want in sorted(exp.items()):
        got = rd.person(rec0 + ix * PREC)
        diff = [k for k in ("job", "job_low", "base", "growth", "wexp") if got[k] != want[k]]
        if got["index"] != ix:
            diff.append("index")
        rows.append({"index": ix, "pid": want["pid"], "mem_pid": got["pid"], "diff": diff,
                     "mem": {k: got[k] for k in ("job", "job_low", "base", "growth", "wexp")}})
        if diff:
            bad.append(f"{want['pid']}: {', '.join(diff)}")
    return {"record0": f"{rec0:08x}", "checked": len(rows), "mismatches": bad, "rows": rows}


def run_one(job: str, zakdir: str, exp: dict, spec: str) -> dict:
    parts = spec.split(":")
    name, save, route, last, reads = parts[:5]
    reads = [int(x) for x in reads.split("/") if x]
    end = int(parts[5]) if len(parts) > 5 else max(reads)
    rin = json.load(open(os.path.join(ROOT, "config", "harness", "routes.json"), encoding="utf-8"))["routes"][route]["input"]
    inp = ",".join(x for x in rin.split(",") if x and int(x.split(":")[0]) <= int(last))
    orig = hl.lay_save

    def lay(zip_path, data_dir):
        names = orig(zip_path, data_dir)
        assert hl.below(os.path.abspath(data_dir), TOP), data_dir
        if zakdir != "none":
            src = os.path.join(zakdir, "mods")
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(data_dir, "mods"), dirs_exist_ok=True)
        return names

    hl.lay_save = lay
    out = {"run": name, "save": save, "route": route, "last_press": int(last), "reads": [], "zakdir": zakdir}
    t0 = time.time()
    try:
        with sv.Server(f"{job}-{name}", save=save, root=os.path.join(TOP, "server")) as s:
            out["mods_in_data"] = sorted(os.path.relpath(os.path.join(r, f), s.data_dir).replace("\\", "/")
                                         for r, _d, fs in os.walk(os.path.join(s.data_dir, "mods")) for f in fs)
            s.inputs_set(inp)
            rd = Reader(s)
            shots = os.path.join(TOP, "robot", "shots", f"{job}-{name}")
            os.makedirs(shots, exist_ok=True)
            for f in sorted(set(reads + [end])):
                s.step_to(f)
                if f in reads:
                    s.shot(os.path.join(shots, f"f{f:06d}.png"), scale=1)
                    entry = {"frame": f}
                    try:
                        us = rd.units()
                        entry["units"] = us
                        if us:
                            entry["persons"] = compare_persons(rd, int(us[0]["person"], 16), exp)
                    except Exception as e:  # noqa: BLE001
                        entry["error"] = repr(e)
                    out["reads"].append(entry)
            out["digest"] = s.state_digest()
            out["frame"] = s.frame
    finally:
        hl.lay_save = orig
    out["seconds"] = round(time.time() - t0, 1)
    return out


def main(argv):
    job, zakdir, plan_path = argv[:3]
    import gamedata as GD
    facts = GD.load_facts(names=False)
    exp = expected(plan_path, facts)
    res = {"job": job, "zakdir": zakdir, "plan": plan_path, "runs": []}
    os.makedirs(os.path.join(TOP, "robot"), exist_ok=True)
    path = os.path.join(TOP, "robot", f"{job}.json")
    for spec in argv[3:]:
        res["runs"].append(run_one(job, zakdir, exp, spec))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, ensure_ascii=False)
    for r in res["runs"]:
        print(r["run"], "frame", r.get("frame"), "memory", r.get("digest", {}).get("memory", "")[:16], "mods",
              len(r.get("mods_in_data", [])))
        for e in r["reads"]:
            pc = e.get("persons") or {}
            print("  read", e["frame"], "units", len(e.get("units", [])), "persons checked", pc.get("checked"),
                  "mismatches", len(pc.get("mismatches", [])), e.get("error", ""))
    print("result:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
