"""Seed fingerprints (round 67, release part A, goal 3): sha256 of what each guarded seed produces, never game values.

The hard rule: a seed's output stays byte-identical unless the round announces the change. This tool keeps the
proof cheap enough for the core test:

  config/release/seed_fingerprints.json   the recorded hashes, keyed "<game>/<flag set>/<seed>" (plus "ids/..." keys)
  config/release/seed_changes.json        the changes the current round announces:
                                          {"round": N, "changes": [{"key": "...", "reason": "..."}]}

    python tools/release/fingerprints.py check  [--jobs N] [--keys K,K]   exit 0 = no unannounced change
    python tools/release/fingerprints.py update --round N [--jobs N]      rewrite the LISTED keys only (round commit)
    python tools/release/fingerprints.py init                             first write (refuses if the file exists)
    python tools/release/fingerprints.py compute [--keys K,K]             print the current hashes as JSON
    python tools/release/fingerprints.py keys                             list the keys and what each one makes

check: a key whose hash changed and that is listed in seed_changes.json passes with a note; a change that is NOT
listed FAILS with "seeds changed without notice: <keys>" (never a jump to FULL). A new or vanished key counts as a
change. Seal of Flames keys skip with a plain reason when the mod is not installed (play/seal-of-flames).
ids/r62-page reads build/r62/check/runs: missing in the work folder (with .git) it is an ERROR (round 67); in a
release copy (no .git: the zip is a `git archive`) it skips with a plain reason (round 85).
update: refuses (writes nothing) when any key changed that is not listed, or seed_changes.json is for another round.
A GUARDED key (r63fboss1 patch/plan) whose guarded shas change FAILS check and update even when listed.

Every make is fresh (rando cache OFF), headless, below normal priority, under build/release/fingerprints/.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
import makes as MK  # noqa: E402

STORE = os.path.join(ROOT, "config", "release", "seed_fingerprints.json")
CHANGES = os.path.join(ROOT, "config", "release", "seed_changes.json")
WORK_TOP = os.path.join(ROOT, "build", "release", "fingerprints")
R62_RUNS = os.path.join(ROOT, "build", "r62", "check", "runs")
R62_SCHEMA = os.path.join(ROOT, "tests", "test_rando_page_r62_schema.json")
FORMAT = 1

# the existing guards these keys carry on (docs/tests/STORY_BOSSES.md, docs/rando/SEAL_BOSSES.md: r63fboss1 patch
# 372b5d5c..., plan c5825cce... until round 75b; tests/test_rando_page62b.py: the round-62/62b page run ids)
# Round 75b (seed guarantees, F-059 (3) standing OK): the plan gains the guarantees block, the 'guarantees: timing'
# guard and rando_version 2, so the guarded plan sha is re-recorded (d1f81611...). The patch sha is unchanged
# (372b5d5c...): the cell diff of the round-63 and round-75b patch (build/r75b/f1/r63fboss1_celldiff.txt) has all 30
# cells (19 boss, 11 enemy) equal and the two files byte-identical. Run id now r63fboss1-d8084ab3.
R63FBOSS1 = "fates/boss-classes/r63fboss1"
GUARDED = {R63FBOSS1: {"patch": "372b5d5cb1f2bb5f37a1a48b0a999bf152333d38558eac1706ad0a4a7e9ab16e",
                       "plan": "d1f81611374ab190c0689750dfbb39647405f602049e6db4255a634038552b4d"}}
R62_IDS = "ids/r62-page"


class FingerprintError(Exception):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: str) -> str:
    with open(path, "rb") as fh:
        return sha(fh.read())


def tree_sha(top: str) -> str:
    """one hash for a folder: every file's relative path and sha256, sorted"""
    lines = []
    for dp, _dn, fs in os.walk(top):
        for f in fs:
            q = os.path.join(dp, f)
            lines.append(f"{os.path.relpath(q, top).replace(os.sep, '/')}\0{file_sha(q)}\n")
    return sha("".join(sorted(lines)).encode("utf-8"))


def combine(parts: dict) -> str:
    return sha(";".join(f"{k}={parts[k]}" for k in sorted(parts)).encode("utf-8"))


# ------------------------------------------------------------------------------------------------ what is guarded
R62_RELEASE_SKIP = ("not part of a release copy: build/r62/check/runs (the round-62 page runs this key is read from) "
                    "stays in the project's work folder, where this key is still checked")


def is_release_copy(root: str | None = None) -> bool:
    """True in an unpacked release zip. package.py makes the zip with `git archive` (tracked files only, no marker
    file of its own), so the sign is the missing .git (a folder in a clone, a file in a git worktree)."""
    return not os.path.exists(os.path.join(root or ROOT, ".git"))


def r62_status(fates_why: str | None, runs: str | None = None, root: str | None = None) -> tuple[str, str | None]:
    """What happens to ids/r62-page: ("skip", reason), ("error", message) or ("make", None).
    Round 67 rule: in the work folder (with .git) a missing build/r62 is an ERROR, never a quiet skip. Round 85
    (plan section 4 item 4): a release copy never carries build/, so there the key is skipped with a plain reason."""
    runs = runs or R62_RUNS
    root = root or ROOT
    if fates_why:
        return "skip", fates_why
    if os.path.isdir(runs):
        return "make", None
    if is_release_copy(root):
        return "skip", R62_RELEASE_SKIP
    # round 67 integrate (review): a machine with the game data must also have the round-62 runs, else the page-id
    # guard would stop guarding quietly; only the Seal keys (mod not installed) may skip
    return "error", (f"{os.path.relpath(runs, root)} is missing (the round-62 check runs the page ids are read from); "
                     f"restore it from the build archive")


def seal_ready() -> str | None:
    """None when Seal of Flames can be made here, else the plain reason"""
    try:
        import gamedata as GD
        why = GD.available()
        if why:
            return why
        import sources as S
        if not os.path.isfile(S.RULES["seal"]):
            return S.SEAL_EDITION_MISSING
        if not os.path.isdir(os.path.join(S.seal_romfs(), "GameData")):
            return "Seal of Flames is not installed (play/seal-of-flames)"
    except Exception as e:  # noqa: BLE001
        return f"Seal of Flames cannot be read: {e}"
    return None


def fates_ready() -> str | None:
    try:
        import gamedata as GD
        return GD.available()
    except Exception as e:  # noqa: BLE001
        return f"the extracted tables cannot be read: {e}"


def make_specs() -> dict[str, dict]:
    """key -> {"game", "answer", "args", "what"}: the page's own answers, made the way the in-game core makes them
    (ingame.make_args; Seal with --game seal)"""
    import ingame as IG
    rows = IG.schema()["rows"]
    out = {}
    for game in ("fates", "seal"):
        g = None if game == "fates" else game
        default = IG.page_answers(rows, IG.page_restore(rows, {"randomizer": True, "seed": "1"}, g), g)
        every, _turned = IG.page_everything(rows, IG.page_restore(rows, {"seed": "1"}, g), g)
        every = IG.page_answers(rows, every, g)
        for flags, answer, what in (("default", default, "Randomizer on, every other row at its default"),
                                    ("everything-on", every, "the page's 'Randomize everything'")):
            args = IG.make_args(answer) + (["--game", "seal"] if g else [])
            out[f"{game}/{flags}/1"] = {"game": game, "answer": answer, "args": args, "what": what + ", seed 1"}
    a = {"randomizer": True, "classes": False, "growths": False, "join_stats": False, "boss_classes": True,
         "seed": "r63fboss1"}
    out[R63FBOSS1] = {"game": "fates", "answer": a, "args": IG.make_args(a),
                      "what": "round 63's boss seed (Boss classes on alone); patch and plan shas guarded since r63"}
    return out


def r62_answer_sets() -> list[tuple[str, str | None, dict]]:
    """tests/test_rando_page62b.py's answer sets: every round-62 check run, plus off / defaults-on / all1-3"""
    out = []
    for f in sorted(glob.glob(os.path.join(R62_RUNS, "*", "*", "options.json"))):
        game = os.path.basename(os.path.dirname(os.path.dirname(f)))
        with open(f, encoding="utf-8") as fh:
            a = json.load(fh)
        a.pop("game", None)
        out.append((f"{game}/{os.path.basename(os.path.dirname(f))}", None if game == "fates" else game, a))
    with open(R62_SCHEMA, encoding="utf-8") as fh:
        old = json.load(fh)["rows"]
    every = {r["key"]: r.get("all", r["default"]) for r in old}
    for game in (None, "seal"):
        out.append((f"{game or 'fates'}/off", game, {"randomizer": False}))
        out.append((f"{game or 'fates'}/defaults-on", game, {"randomizer": True, "seed": "r62bdef"}))
        for i, extra in enumerate(({}, {"recruit": "any", "recruit_class": "slot", "recruit_stats": "slot",
                                        "boss_stats": "ease"},
                                   {"recruit": "any", "nuzlocke": True, "difficulty": "hard"}), 1):
            out.append((f"{game or 'fates'}/all{i}", game, dict(every, randomizer=True, seed=f"r62ball{i}", **extra)))
    return out


def r62_ids() -> dict:
    """the page run ids and make flags of every round-62 answer set on today's page (no make)"""
    import ingame as IG
    rows = IG.schema()["rows"]
    ids, flags = [], []
    for name, game, saved in r62_answer_sets():
        a = IG.page_answers(rows, IG.page_restore(rows, saved, game), game)
        if not a.get("randomizer"):
            ids.append([name, "off"])
            continue
        ids.append([name, IG.run_id(a, game)])
        flags.append([name, IG.make_args(a)])
    parts = {"run_ids": sha(json.dumps(ids).encode("utf-8")), "make_flags": sha(json.dumps(flags).encode("utf-8"))}
    return {"sha256": combine(parts), "parts": parts, "sets": len(ids)}


def all_keys() -> list[str]:
    return sorted(list(make_specs()) + [R62_IDS])


# ------------------------------------------------------------------------------------------------ compute
def made_value(m: "MK.Made") -> dict:
    mod = m.mod_dir()
    if m.rc != 0 or mod is None or not os.path.isfile(m.patch):
        raise FingerprintError(f"make failed (rc {m.rc}): {(m.stdout + m.stderr)[-600:]}")
    parts = {"patch": file_sha(m.patch), "plan": file_sha(os.path.join(mod, "plan.json")),
             "spoiler": file_sha(os.path.join(mod, "spoiler.txt")), "mod": tree_sha(mod)}
    return {"sha256": combine(parts), "parts": parts}


def compute(keys: list[str] | None = None, jobs: int | None = None, work: str | None = None,
            keep: bool = False) -> tuple[dict, dict, dict, float]:
    """-> (values {key: value}, skipped {key: reason}, errors {key: message}, seconds)"""
    t0 = time.monotonic()
    specs = make_specs()
    want = sorted(keys) if keys else sorted(list(specs) + [R62_IDS])
    unknown = [k for k in want if k not in specs and k != R62_IDS]
    if unknown:
        raise FingerprintError(f"unknown keys: {', '.join(unknown)} (known: {', '.join(all_keys())})")
    values, skipped, errors = {}, {}, {}
    why = {"fates": fates_ready(), "seal": seal_ready()}
    todo = []
    work = work or os.path.join(WORK_TOP, f"run-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}")
    for k in want:
        if k == R62_IDS:
            continue
        g = specs[k]["game"]
        if why[g] or (g == "seal" and why["fates"]):
            skipped[k] = why[g] or why["fates"]
            continue
        todo.append((k, specs[k]["args"], os.path.join(work, k.replace("/", "_"))))
    if R62_IDS in want:
        what, msg = r62_status(why["fates"])
        if what == "skip":
            skipped[R62_IDS] = msg
        elif what == "error":
            errors[R62_IDS] = msg
        else:
            try:
                values[R62_IDS] = r62_ids()
            except Exception as e:  # noqa: BLE001
                errors[R62_IDS] = str(e)
    made = MK.make_many(todo, jobs or MK.default_jobs())
    for k, m in made.items():
        try:
            values[k] = made_value(m)
        except FingerprintError as e:
            errors[k] = str(e)
    if not keep and not errors:
        shutil.rmtree(work, ignore_errors=True)
    return values, skipped, errors, round(time.monotonic() - t0, 1)


# ------------------------------------------------------------------------------------------------ files
def load_json(path: str, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def check_changes_file(ch: dict) -> list[str]:
    """problems with seed_changes.json's shape ({round: int, changes: [{key, reason}]})"""
    bad = []
    if not isinstance(ch, dict) or set(ch) != {"round", "changes"}:
        return ["seed_changes.json must be {\"round\": N, \"changes\": [...]}"]
    if not isinstance(ch["round"], int) or isinstance(ch["round"], bool):
        bad.append("round must be a number")
    if not isinstance(ch["changes"], list):
        return bad + ["changes must be a list"]
    for i, c in enumerate(ch["changes"]):
        if not isinstance(c, dict) or set(c) != {"key", "reason"} or not all(isinstance(c[x], str) and c[x].strip()
                                                                              for x in ("key", "reason")):
            bad.append(f"changes[{i}] must be {{\"key\": \"...\", \"reason\": \"...\"}} with both filled in")
    return bad


def check_store(st: dict) -> list[str]:
    """problems with seed_fingerprints.json's shape: hashes only"""
    bad = []
    if not isinstance(st, dict) or st.get("format") != FORMAT or not isinstance(st.get("keys"), dict):
        return [f"seed_fingerprints.json must be {{\"format\": {FORMAT}, \"round\": N, \"keys\": {{...}}}}"]
    hexd = set("0123456789abcdef")
    for k, v in st["keys"].items():
        hs = [v.get("sha256")] + list((v.get("parts") or {}).values())
        if not all(isinstance(h, str) and len(h) == 64 and set(h) <= hexd for h in hs) or not v.get("parts"):
            bad.append(f"{k}: values must be sha256 hex only")
        if set(v) - {"sha256", "parts", "sets"}:
            bad.append(f"{k}: unexpected fields {sorted(set(v) - {'sha256', 'parts', 'sets'})}")
    return bad


# ------------------------------------------------------------------------------------------------ verdicts
def guard_broken(k: str, value: dict) -> str:
    """'' when the key keeps its GUARDED part shas, else the names of the parts that differ"""
    parts = value.get("parts", {})
    return ", ".join(p for p, want in sorted(GUARDED.get(k, {}).items()) if parts.get(p) != want)


def evaluate(values: dict, skipped: dict, errors: dict, stored: dict, changes: dict) -> dict:
    """-> {"ok", "rows": [(key, status, note)], "unannounced": [...], "message"}. Status: same, changed-announced
    (pass), changed / new / gone (FAIL unless announced), skipped, error (FAIL)."""
    listed = {c["key"]: c["reason"] for c in (changes or {}).get("changes", [])}
    old = (stored or {}).get("keys", {})
    rows, unannounced, errs, guards = [], [], [], []
    for k in sorted(set(values) | set(skipped) | set(errors) | set(old)):
        if k in errors:
            rows.append((k, "error", errors[k][:300]))
            errs.append(k)
        elif k in skipped:
            rows.append((k, "skipped", skipped[k]))
        elif k not in values:
            if k in listed:
                rows.append((k, "gone-announced", listed[k]))
            else:
                rows.append((k, "gone", "recorded but no longer made"))
                unannounced.append(k)
        elif k not in old:
            if k in listed:
                rows.append((k, "new-announced", listed[k]))
            else:
                rows.append((k, "new", "not recorded yet"))
                unannounced.append(k)
        elif k in GUARDED and guard_broken(k, values[k]):
            # guarded since round 63 (patch and plan shas in the docs): seed_changes.json cannot announce it away
            rows.append((k, "guard-broken", f"{guard_broken(k, values[k])} no longer match the guarded shas "
                                             f"(a person must change GUARDED in tools/release/fingerprints.py)"))
            guards.append(k)
        elif values[k]["sha256"] == old[k]["sha256"]:
            rows.append((k, "same", ""))
        else:
            what = sorted(p for p in values[k].get("parts", {})
                          if values[k]["parts"].get(p) != old[k].get("parts", {}).get(p))
            if k in listed:
                rows.append((k, "changed-announced", f"{', '.join(what)} changed; announced: {listed[k]}"))
            else:
                rows.append((k, "changed", f"{', '.join(what)} changed"))
                unannounced.append(k)
    msg = []
    if unannounced:
        msg.append(f"seeds changed without notice: {', '.join(unannounced)}")
    if errs:
        msg.append(f"could not be made: {', '.join(errs)}")
    if guards:
        msg.append(f"guarded shas changed: {', '.join(guards)}")
    return {"ok": not unannounced and not errs and not guards, "rows": rows, "unannounced": unannounced,
            "errors": errs, "guards": guards,
            "message": "; ".join(msg) or "no seed changed without notice"}


def apply_update(values: dict, skipped: dict, errors: dict, stored: dict, changes: dict, round_no: int) -> dict:
    """the new store for `update --round N`; raises FingerprintError (nothing written) on any refusal"""
    bad = check_changes_file(changes)
    if bad:
        raise FingerprintError("; ".join(bad))
    if changes["round"] != round_no:
        raise FingerprintError(f"seed_changes.json is for round {changes['round']}, not round {round_no}")
    if errors:
        raise FingerprintError(f"could not be made: {', '.join(sorted(errors))}")
    if skipped:
        raise FingerprintError(f"skipped here, so they cannot be updated: {', '.join(sorted(skipped))} "
                               f"({'; '.join(sorted(set(skipped.values())))})")
    ev = evaluate(values, {}, {}, stored, changes)
    if ev["guards"]:
        raise FingerprintError(f"refused: guarded shas changed: {', '.join(ev['guards'])} (seed_changes.json "
                               f"cannot announce a guarded key; a person must change GUARDED first)")
    if ev["unannounced"]:
        raise FingerprintError(f"refused: seeds changed without notice: {', '.join(ev['unannounced'])} "
                               f"(list them in config/release/seed_changes.json with a reason first)")
    keys = dict(stored.get("keys", {}))
    listed = {c["key"] for c in changes["changes"]}
    for k in listed:
        if k in values:
            keys[k] = values[k]
        else:
            keys.pop(k, None)
    return {"format": FORMAT, "round": round_no, "keys": keys,
            "note": "sha256 only (round 67, tools/release/fingerprints.py); change only inside a round commit"}


# ------------------------------------------------------------------------------------------------ CLI
def table(ev: dict) -> str:
    w = max([len(k) for k, _s, _n in ev["rows"]] + [10])
    lines = [f"{'key':<{w}}  {'status':<18} note"]
    lines += [f"{k:<{w}}  {s:<18} {n}" for k, s, n in ev["rows"]]
    lines.append(("PASS: " if ev["ok"] else "FAIL: ") + ev["message"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "compute", "update", "init"):
        p = sub.add_parser(name)
        p.add_argument("--jobs", type=int, default=None, help="makes side by side (default: makes.default_jobs())")
        p.add_argument("--keys", default=None, help="comma-separated keys (default: all)")
        p.add_argument("--keep", action="store_true", help="keep the make folders under build/release/fingerprints")
        if name == "update":
            p.add_argument("--round", type=int, required=True)
    sub.add_parser("keys")
    a = ap.parse_args(argv)
    if a.cmd == "keys":
        for k, s in sorted(make_specs().items()):
            print(f"{k:34} {s['what']}")
        print(f"{R62_IDS:34} the round-62/62b page run ids and make flags ({len(r62_answer_sets())} answer sets)")
        return 0
    keys = [k.strip() for k in a.keys.split(",")] if a.keys else None
    try:
        if keys and a.cmd in ("update", "init"):
            raise FingerprintError(f"{a.cmd} always makes every key (no --keys)")
        values, skipped, errors, secs = compute(keys, a.jobs, keep=a.keep)
        if a.cmd == "compute":
            print(json.dumps({"keys": values, "skipped": skipped, "errors": errors, "seconds": secs}, indent=1,
                             sort_keys=True))
            return 1 if errors else 0
        stored = load_json(STORE)
        changes = load_json(CHANGES, {"round": 0, "changes": []})
        if a.cmd == "init":
            if stored is not None:
                raise FingerprintError(f"{os.path.relpath(STORE, ROOT)} exists; use update --round N")
            if errors or skipped:
                raise FingerprintError(f"init needs every key made: errors {sorted(errors)}, skipped {skipped}")
            for k, want in GUARDED.items():
                got = {p: values[k]["parts"][p] for p in want}
                if got != want:
                    raise FingerprintError(f"{k} no longer gives the guarded shas {want}: {got}")
            round_no = changes.get("round") or 0
            write_json(STORE, {"format": FORMAT, "round": round_no, "keys": values,
                               "note": "sha256 only (round 67, tools/release/fingerprints.py); change only inside a "
                                       "round commit"})
            if not os.path.isfile(CHANGES):
                write_json(CHANGES, {"round": round_no, "changes": []})
            print(f"wrote {os.path.relpath(STORE, ROOT)}: {len(values)} keys ({secs} s)")
            return 0
        if stored is None:
            raise FingerprintError(f"{os.path.relpath(STORE, ROOT)} is missing (run init once)")
        bad = check_store(stored) + check_changes_file(changes)
        if bad:
            raise FingerprintError("; ".join(bad))
        if keys:
            stored = dict(stored, keys={k: v for k, v in stored["keys"].items() if k in keys})
        if a.cmd == "check":
            ev = evaluate(values, skipped, errors, stored, changes)
            print(table(ev))
            print(f"({secs} s, {len(values)} made or read, {len(skipped)} skipped)")
            return 0 if ev["ok"] else 1
        new = apply_update(values, skipped, errors, stored, changes, a.round)
        write_json(STORE, new)
        print(f"updated {os.path.relpath(STORE, ROOT)} for round {a.round}: "
              f"{', '.join(c['key'] for c in changes['changes']) or 'no key changed'}")
        return 0
    except FingerprintError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
