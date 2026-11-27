"""One robot check of the whole randomizer (round 49 integrate): one mod with every switch on, in the robot's OWN
test game, then the same run with the mod uninstalled (off = original). Read only: no pokes, no writer.

    python tools/randomizer/robot_all.py MODFOLDER [JOB]

MODFOLDER  a folder made by `rando.py make ... --out build/rando49/all/mods` (plan.json, tables/*.csv)
Everything lives below build/rando49/all/ (zak/ = the mods tool's install target, stage/, server/<run>/ with its
own data, APPDATA and LOCALAPPDATA folders; results robot/<JOB>.json). The game server is headless and below
normal priority (tools/harness/server.py). build/STOP_ROUND is checked before every start.

Each run: save bt-ch1-clear (Chapter 1 cleared, from the existing recordings), the recorded bt-ch2 presses up to
frame 5117 (no new play), memory read at frames 4800 and 5117 (the Chapter 2 map, as rounds 47 and 49's tracks):
  - the 49 Person rows: class, class line, bases, growths, weapon exp, 5 skill slots, 3 personal skills
  - the Item table's shop stock bytes (every item) and the castle reward lists (AchieveBonusBattle / Visit)
  - the Chapter 2 player units' items (Gunter, Felicia; Corrin comes from the save)
  - the Chapter 2 enemy units: class and items against their DisposUnit rows (Normal slots), and that each one
    can use the weapons it holds
"""
from __future__ import annotations

import csv
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TOP = os.path.join(ROOT, "build", "rando49", "all")
STOP = os.path.join(ROOT, "build", "STOP_ROUND")
SAVE, ROUTE, LAST, READS, CHAPTER = "bt-ch1-clear", "bt-ch2", 5117, (4800, 5117), "A002"


def _csv_rows(mod: str | None, table: str) -> list[dict]:
    if not mod:
        return []
    p = os.path.join(mod, "tables", f"{table}.csv")
    if not os.path.isfile(p):
        return []
    rd = list(csv.reader(io.StringIO(open(p, encoding="utf-8-sig").read())))
    return [dict(zip(rd[0], r)) for r in rd[1:]]


def expected_persons(facts, skill_ix: dict, mod: str | None) -> dict:
    """{person index: wanted values}: the original rows with the mod's Person.csv cells on top."""
    import skills as S
    jix = {lab: R.ival(j["index"]) for lab, j in facts.jobs.items()}
    rows = {p["label"]: dict(p) for p in facts.persons}
    for m in _csv_rows(mod, "Person"):
        rows[m["label"]].update({k: v for k, v in m.items() if k not in ("index", "label")})
    out = {}
    for p0 in facts.persons:
        if not facts.in_scope(p0):
            continue
        p = rows[p0["label"]]
        out[R.ival(p["index"])] = {
            "pid": p["label"], "job": jix[p["job"]], "job_low": jix[p["job_low"]],
            "base": [R.ival(p[f"base.{s}"]) for s in R.STATS], "growth": [R.ival(p[f"growth.{s}"]) for s in R.STATS],
            "wexp": [R.ival(p[f"weapon_exp.{k}"]) for k in R.KINDS],
            "skills": [skill_ix[p[f"skill.{i}"]] for i in range(1, S.SLOTS + 1)],
            "personal": [skill_ix[p[c]] for c in S.PERSONAL_CELLS]}
    return out


def read_person(s, a: int) -> dict:
    import robot_check as RC
    b = s.peek1(a, RC.PREC)
    return {"index": struct.unpack_from("<H", b, 0x24)[0], "job": struct.unpack_from("<H", b, 0x2C)[0],
            "job_low": struct.unpack_from("<H", b, 0x2E)[0], "base": [RC.s8(x) for x in b[0x38:0x40]],
            "growth": [RC.s8(x) for x in b[0x40:0x48]], "wexp": list(b[0x60:0x68]),
            "skills": list(struct.unpack_from("<5h", b, 0x68)), "personal": list(struct.unpack_from("<3h", b, 0x74))}


def enemy_check(s, us: list[dict], t, mod: str | None) -> dict:
    """Force-1 units on the Chapter 2 map against their DisposUnit rows (+ the mod's cells), Normal slots."""
    import enemies as E
    want: dict[tuple, dict] = {}
    for m in _csv_rows(mod, "DisposUnit"):
        want[(m["file"], int(m["index"]))] = {k: v for k, v in m.items() if k not in ("file", "index", "label")}
    jix = {lab: R.ival(j["index"]) for lab, j in t.f.jobs.items()}
    iix = {R.ival(i["index"]): lab for lab, i in t.f.items.items()}
    rows = [d for d in t.dispos if E.chapter_of(d["file"]) == CHAPTER and str(d["team"]) == "1"]
    out = {"units": [], "matched": 0, "changed": 0, "mismatches": []}
    for u in us:
        if u["force"] != 1:
            continue
        ub = s.peek1(int(u["unit"], 16), 0x120)
        items = [struct.unpack_from("<HH", ub, 0x108 + 4 * i) for i in range(5)]
        got_items = [iix.get(a, str(a)) for a, _b in items if a]
        wexp = list(ub[0xE8:0xF0])
        cand = [d for d in rows if d["pid"] == u["pid"] and R.ival(d["pos.x"]) == u["x"]
                and R.ival(d["pos.y"]) == u["y"] and R.ival(d["flags"]) & 0x100]
        rec = {"pid": u["pid"], "jid": u["jid"], "items": got_items, "x": u["x"], "y": u["y"]}
        if len(cand) != 1:
            rec["match"] = f"{len(cand)} rows"
            out["units"].append(rec)
            continue
        d = cand[0]
        key = (d["file"], R.ival(d["index"]))
        exp = dict(d, **{k: v for k, v in want.get(key, {}).items() if v != ""})
        ej = exp.get("jid") or t.unit_job(d)
        eitems = [exp.get(f"item_{i}", "") for i in E.ITEM_SLOTS
                  if R.ival(d.get(f"item_{i}_forge.normal", 0) or 0) >= 0 and exp.get(f"item_{i}", "")]
        changed = ej != (d.get("jid") or t.unit_job(d)) or eitems != [d.get(f"item_{i}", "") for i in E.ITEM_SLOTS
                  if R.ival(d.get(f"item_{i}_forge.normal", 0) or 0) >= 0 and d.get(f"item_{i}", "")]
        rec.update({"match": f"{d['file']}#{d['index']}", "expect": {"jid": ej, "items": eitems}, "changed": changed})
        diff = []
        if u["job"] != jix.get(ej):
            diff.append(f"class {u['jid']} != {ej}")
        if got_items != eitems:
            diff.append(f"items {got_items} != {eitems}")
        jrow = t.f.jobs.get(u["jid"])
        unusable = [iid for iid in got_items if jrow is not None and t.f.item_kind(iid) is not None
                    and not t.special_item(iid)
                    and min(wexp[t.f.item_kind(iid)], t.f.wexp_max(jrow)[t.f.item_kind(iid)]) < t.f.item_rank(iid)]
        if unusable:
            diff.append(f"cannot use {unusable}")
        out["matched"] += 1
        out["changed"] += 1 if changed else 0
        if diff:
            out["mismatches"].append(f"{rec['match']} {u['pid']}: " + "; ".join(diff))
        out["units"].append(rec)
    return out


def run(name: str, zakdir: str, mod: str | None, facts, t, offs, skill_ix) -> dict:
    import headless as hl
    import server as sv
    import robot_check as RC
    import items as I
    if os.path.exists(STOP):
        raise SystemExit("build/STOP_ROUND exists: not started")
    pexp = expected_persons(facts, skill_ix, mod)
    iexp = I._expected(facts, mod)
    rin = json.load(open(os.path.join(ROOT, "config", "harness", "routes.json"), encoding="utf-8"))["routes"][ROUTE]["input"]
    inp = ",".join(x for x in rin.split(",") if x and int(x.split(":")[0]) <= LAST)
    orig = hl.lay_save

    def lay(zip_path, data_dir):
        names = orig(zip_path, data_dir)
        assert hl.below(os.path.abspath(data_dir), TOP), data_dir
        if os.path.isdir(os.path.join(zakdir, "mods")):
            shutil.copytree(os.path.join(zakdir, "mods"), os.path.join(data_dir, "mods"), dirs_exist_ok=True)
        return names

    hl.lay_save = lay
    out = {"run": name, "save": SAVE, "route": ROUTE, "last_press": LAST, "mod": mod, "reads": []}
    t0 = time.time()
    try:
        with sv.Server(f"all49-{name}", save=SAVE, root=os.path.join(TOP, "server")) as s:
            out["pid"] = s.proc.pid
            out["mods_in_data"] = len([f for r, _d, fs in os.walk(os.path.join(s.data_dir, "mods")) for f in fs])
            s.inputs_set(inp)
            rd = RC.Reader(s)
            shots = os.path.join(TOP, "robot", "shots", name)
            os.makedirs(shots, exist_ok=True)
            for f in READS:
                s.step_to(f)
                s.shot(os.path.join(shots, f"f{f:06d}.png"), scale=1)
                e = {"frame": f}
                try:
                    us = rd.units()
                    e["unit_count"] = len(us)
                    if us:
                        p0 = read_person(s, int(us[0]["person"], 16))
                        rec0 = int(us[0]["person"], 16) - p0["index"] * RC.PREC
                        bad = []
                        for ix, w in sorted(pexp.items()):
                            got = read_person(s, rec0 + ix * RC.PREC)
                            diff = [k for k in w if k != "pid" and got[k] != w[k]] + (["index"] if got["index"] != ix else [])
                            if diff:
                                bad.append(f"{w['pid']}: {', '.join(diff)}")
                        e["persons"] = {"checked": len(pexp), "mismatches": bad}
                        e["tables"] = I._read_tables(rd, s, rec0, offs, facts, iexp)
                        e["tables"]["mismatches"] = e["tables"]["mismatches"][:30]
                        pu, seen = [], []
                        for u in us:
                            if u["force"] == 0 and u["pid"] in iexp["ch2"] and not u["pid"].startswith("PID_プレイヤー"):
                                got = I._unit_items(s, int(u["unit"], 16))
                                seen.append(u["pid"])
                                if got != iexp["ch2"][u["pid"]]:
                                    pu.append({"pid": u["pid"], "mem": got, "want": iexp["ch2"][u["pid"]]})
                            if u["force"] == 0 and u["pid_number"] in pexp:
                                ub = s.peek1(int(u["unit"], 16), 0x110)
                                eq = list(struct.unpack_from("<5h", ub, 0xFE))
                                if sorted(eq) != sorted(pexp[u["pid_number"]]["skills"]):
                                    pu.append({"pid": u["pid"], "equipped": eq, "row": pexp[u["pid_number"]]["skills"]})
                        e["player_units"] = {"seen": seen, "mismatches": pu}
                        e["enemies"] = enemy_check(s, us, t, mod)
                except Exception as ex:  # noqa: BLE001
                    e["error"] = repr(ex)
                out["reads"].append(e)
            out["digest"] = s.state_digest()
            out["frame"] = s.frame
    finally:
        hl.lay_save = orig
    out["seconds"] = round(time.time() - t0, 1)
    return out


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if os.path.exists(STOP):
        print("build/STOP_ROUND exists: not started")
        return 3
    mod = os.path.abspath(argv[0])
    job = argv[1] if len(argv) > 1 else "all49"
    if not os.path.normcase(mod).startswith(os.path.normcase(TOP) + os.sep):
        print("ERROR: the mod folder must be below build/rando49/all/")
        return 1
    import gamedata as GD
    import items as I
    import skills as S
    import enemies as E
    facts = GD.load_facts(names=False)
    t = E.load_tables(names=False)
    offs = I._offsets()
    skill_ix = {r["label"]: R.ival(r["index"]) for r in S.load_skill_rows()}
    zak = os.path.join(TOP, "zak")
    mt = [sys.executable, os.path.join(ROOT, "tools", "mods", "mods.py"), "--mods-dir", os.path.dirname(mod),
          "--stage-dir", os.path.join(TOP, "stage"), "--zakuro-dir", zak]
    res = {"job": job, "mod": mod, "steps": [], "runs": []}
    os.makedirs(os.path.join(TOP, "robot"), exist_ok=True)
    path = os.path.join(TOP, "robot", f"{job}.json")

    def save():
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, ensure_ascii=False, default=str)

    def tool(*c):
        r = subprocess.run(mt + list(c), capture_output=True, text=True, encoding="utf-8", errors="replace")
        res["steps"].append({"cmd": list(c), "rc": r.returncode, "out": (r.stdout + r.stderr)[-1500:]})
        save()
        return r.returncode

    os.makedirs(zak, exist_ok=True)       # the mods tool installs only into an existing data folder
    if tool("install") != 0:
        print("install failed; see", path)
        return 1
    res["files_installed"] = len([f for r, _d, fs in os.walk(os.path.join(zak, "mods")) for f in fs])
    res["runs"].append(run("mod", zak, mod, facts, t, offs, skill_ix))
    save()
    tool("uninstall")
    tool("disable", os.path.basename(mod))
    res["files_left_after_uninstall"] = len([f for r, _d, fs in os.walk(os.path.join(zak, "mods")) for f in fs])
    save()
    res["runs"].append(run("off", zak, None, facts, t, offs, skill_ix))
    save()
    for r in res["runs"]:
        print(r["run"], "frame", r.get("frame"), "memory", r.get("digest", {}).get("memory", "")[:16],
              "mod files", r.get("mods_in_data"), f"{r['seconds']} s")
        for e in r["reads"]:
            pc, tb, pu, en = (e.get(k) or {} for k in ("persons", "tables", "player_units", "enemies"))
            print(f"  read {e['frame']}: persons {pc.get('checked')} mism {len(pc.get('mismatches', []))}; "
                  f"tables {tb.get('checked')} mism {len(tb.get('mismatches', []))}; player units {pu.get('seen')} "
                  f"mism {len(pu.get('mismatches', []))}; enemies matched {en.get('matched')} changed "
                  f"{en.get('changed')} mism {len(en.get('mismatches', []))} {e.get('error', '')}")
    print("files installed", res.get("files_installed"), "left after uninstall", res.get("files_left_after_uninstall"))
    print("result:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
