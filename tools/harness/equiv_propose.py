"""Equivalence classes 1-3 as a PROPOSAL (F-026, F-037; host only, read-only on the sources).

Follows docs/collab/EQUIV_RULES_GROK.md: selects only
  class 1  give_up_only          "gives up, and nothing else"
  class 2  return_after_give_up  "a give-up that returns a number nobody uses"
  class 3  impossible_value      "compared with a value that cannot occur"
from the 237 classed candidates (docs/harness/H6_THREE.md; data build/h6three/three-r37.json), checks every
case against the class's written test, and sorts the 70 unsorted candidates (the same file's new_not_sorted)
into classes (sorting only).

It marks NOTHING: tools/harness/mutants_equivalent.csv is not touched, the headline percent is not changed.
Output: build/equiv/equiv_proposal.json (machine file) and a text summary on stdout. The owner reviews
docs/EQUIV_PROPOSAL.md; only after the owner's ok may a separate script apply one approved class (F-037).

    python tools/harness/equiv_propose.py [--three build/h6three/three-r37.json] [--out build/equiv/equiv_proposal.json]
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import mutate  # noqa: E402

CLASS_OF = {"give_up_only": 1, "return_after_give_up": 2, "impossible_value": 3}
# The written tests (EQUIV_RULES_GROK.md, H6_THREE.md class table), one line each.
WRITTEN = {
    1: "the readable code only gives up more, or later, and never stores a wrong answer",
    2: "after `if (fe_gave_up(ctx))` the planted `return` value is thrown away: the original answers instead",
    3: "the planted compare is against a value that cannot occur (a pointer of 1, a number too big for the field)",
}
# A case the notes already say can change an answer: never proposed (EQUIV_RULES_GROK.md, H6_THREE.md).
CAN_CHANGE = {"reliance_level-008"}

# Reading notes for class 1 (by hand, from the source as it is today; the script checks the facts it can).
#   "more"   the planted copy gives up in every case the original readable code gives up, and in more
#   "later"  on a cold cache the planted copy passes the first guard and gives up in the callee's own guard,
#            before any cached value is read
#   "answer" on a cold cache the planted copy can also return an answer on a path that reads no cached value
#            (no weapon, or a weapon that can never crit); that answer is the readable code's own warm-cache
#            answer for that path, so not a wrong answer, but it is an answer where the original gave up
C1_READ = {
    "unit_attack-018": ("later", "answer",
                        "attack_ready asks STAT_MAG twice instead of STR+MAG: with a cold STR cache it goes on; a "
                        "physical weapon gives up in stat_of(STR) (unit_stat_value's own guard); a magic weapon "
                        "answers from the warm MAG cache"),
    "unit_attack-020": ("later", "answer",
                        "attack_ready asks STAT_SKL instead of STAT_MAG: more give-ups when SKL is cold; with a cold "
                        "MAG cache a magic weapon gives up in stat_of(MAG); a physical weapon answers from the warm "
                        "STR cache"),
    "unit_attack_of_slot-007": ("later", "answer", "same edit as unit_attack-018 (shared helper attack_ready)"),
    "unit_attack_of_slot-009": ("later", "answer", "same edit as unit_attack-020 (shared helper attack_ready)"),
    "unit_attack-022": ("more", "",
                        "`!rank_bonus || exp_ready` made `&&`: with rank_bonus it always gives up, without it gives "
                        "up also when the exp caches are cold; never goes on where the original gave up"),
    "unit_attack_of_slot-011": ("more", "", "same edit as unit_attack-022 (shared helper attack_ready)"),
    "unit_hit-037": ("more", "", "hit_ready: `!rank_bonus || exp_ready` made `&&`; as unit_attack-022"),
    "unit_hit_of_slot-010": ("more", "", "same edit as unit_hit-037 (shared helper hit_ready)"),
    "unit_attack_of_slot-006": ("later", "answer",
                                "guard turned round: gives up when warm (more); when cold it goes on: slot -1 with "
                                "nothing equipped answers 0 before unit_attack's own attack_ready guard; otherwise "
                                "that guard gives up"),
    "unit_avoid_of_slot-002": ("later", "",
                               "guard turned round: gives up when warm; when cold unit_avoid's first line is the "
                               "same avoid_ready guard, so it gives up there (slot_or_none reads no cache)"),
    "unit_crit-031": ("later", "answer",
                      "inner crit_ready guard turned round: when warm it gives up; when cold (NoCritGuard already "
                      "checked warm, so the SKL cache is cold) a weapon with the no-crit flag answers 0, otherwise "
                      "stat_of(SKL) gives up"),
    "unit_crit_of_slot-002": ("later", "answer",
                              "guard turned round: when cold and there is no weapon (slot -1 with nothing equipped, "
                              "or a negative slot: item 0), unit_crit answers 0 before its crit_ready guard; "
                              "otherwise unit_crit's guards give up"),
    "unit_crit_avoid-010": ("later", "",
                            "guard turned round: when the LCK cache is cold the next line stat_of(LCK) gives up at "
                            "once (unit_stat_value's own guard); when warm it gives up"),
    "unit_hit_of_slot-002": ("later", "answer",
                             "guard turned round: when cold and there is no weapon (slot -1 with nothing equipped, "
                             "or a negative slot: item 0), unit_hit answers 0 before its hit_ready guard; "
                             "otherwise unit_hit's guards give up"),
    "unit_move-002": ("more", "",
                      "`with_extras && (cold ...)` made `with_extras || (cold ...)`: "
                      "with with_extras set it always gives up; without it, it gives up whenever one of those six caches is cold "
                      "(the original went on); the original gave up only when both held, and then this does too"),
}

# Reading notes for class 3: what happens when the ORIGINAL compared value does occur (the written test only
# speaks of the planted value). "same" = the code reading shows the same answer with no extra memory read.
C3_READ = {
    "stance_attack_bonus_edit-004": ("same",
                                     "type 0xFFFFFFFF no longer returns at line 77, but line 79 returned 0 for a "
                                     "group of -1, so both groups are not -1, and line 81 then returns 0 because "
                                     "type (-1) equals neither group: the same 0, no extra read"),
    "unit_attack_stance_bonus-032": ("same", "same line as stance_attack_bonus_edit-004 (shared helper)"),
    "unit_attack_stance_bonus-020": ("reads-null",
                                     "family_ready: `family != 0` made `!= 1` (always true): when the unit's family "
                                     "pointer is 0 the planted copy reads link_00 at guest address 0; the answer is "
                                     "the same only if that read gives 0, and it is an extra read of unmapped memory"),
    "unit_guard_stance_bonus-034": ("reads-null", "same line as unit_attack_stance_bonus-020 (shared helper)"),
    "unit_support_level-005": ("reads-null",
                               "`parent == 0` made `== 1` (never true): when SUP_FamilyGetParent returns 0 the "
                               "planted copy reads the points at parent + FAMILY_PARENT_POINTS (near address 0) and "
                               "calls family_parent_level on a null parent"),
    "unit_support_max_level-005": ("reads-null",
                                   "`parent == 0` made `== 1`: when the parent is 0 the planted copy makes the guest "
                                   "call SUP_ParentGetMaxLevel(0) instead of returning 0"),
    "script_trick_test-003": ("reads-null",
                              "`d == 0` made `d == 1`: when no gimmick is found (d == 0, the common case) the planted "
                              "copy reads TrickData.state at guest address 0+offset; the answer is the same only if "
                              "that read gives 0 (H6_SURVIVORS C.7: vein_diff does not count such reads)"),
}

# Sorting the 70 by hand where h6three's rule list said "other" and the data allows a class (sorting only).
SORT_70 = {
    "item_record-031": ("start_value", "`*found = 1` made `2`: a flag value made one bigger (is it only tested as "
                                       "yes/no?)"),
    "battle_seal_effect-035": ("other", "the `0` is inside `sizeof first[0]`: `first[1]` has the same size and "
                                        "sizeof does not read it; looks the same by C rules, but no approved class "
                                        "names it: for a person"),
    "route_cost-031": ("other", "a bit mask `step & 2u` made `3u` (bit 0 already tested before it): no class "
                                "names a mask; for a person"),
    "route_cross-017": ("other", "same line as route_cost-031 (shared helper)"),
    "route_goal_x-008": ("other", "same line as route_cost-031 (shared helper)"),
}

GUARD_RX = re.compile(r"^\s*if\s*\(\s*fe_gave_up\s*\(\s*ctx\s*\)\s*\)\s*$")
GIVEUP_BODY_RX = re.compile(r"return\s+(\(\w+\)\s*)?fe_use_original\s*\(\s*ctx\s*\)\s*;")


def norm(s: str) -> str:
    return " ".join(s.split())


def host_row(label: str, stem: str, cid: str) -> dict | None:
    d = os.path.join(ROOT, "build", "harness", "h6host", label)
    for p in sorted(glob.glob(os.path.join(d, stem + "*.csv"))):
        with open(p, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("id") == cid:
                    return r
    return None


_mut_cache: dict = {}


def remap(c: dict):
    """The planted change in today's source: the mutate.Mutant with the same id, operator, old, new, column and
    source line (as h6host.py matches them), or None."""
    path = os.path.join(ROOT, c["file"])
    key = (path, c["function"])
    if key not in _mut_cache:
        _mut_cache[key] = {m.mid: m for m in mutate.make_mutants(path, c["function"], say=lambda *_: None)}
    m = _mut_cache[key].get(c["id"])
    if m is None:
        return None, "id not made from today's source"
    if (m.op, m.old, m.new, str(m.col), norm(m.src_line)) != (c["operator"], c["old"], c["new"], str(c["col"]),
                                                               norm(c["source_line"])):
        return None, f"today's {c['id']} is a different change ({m.op} {m.old!r}->{m.new!r} line {m.line})"
    return m, ""


def lines_of(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def prev_code_line(lines: list[str], ln: int) -> str:
    i = ln - 2
    while i >= 0 and not lines[i].strip():
        i -= 1
    return lines[i] if i >= 0 else ""


def stores_in(path: str) -> int:
    code = mutate.rcheck.strip_code(open(path, encoding="utf-8").read())
    return len(mutate.STORE_RX.findall(code))


def caller_files(name: str) -> list[str]:
    out = []
    rx = re.compile(r"\b" + re.escape(name) + r"\s*\(")
    for p in glob.glob(os.path.join(ROOT, "src", "readable", "**", "*.c"), recursive=True):
        if os.sep + "tests" + os.sep in p:
            continue
        code = mutate.rcheck.strip_code(open(p, encoding="utf-8").read())
        if len(rx.findall(code)) > (1 if re.search(r"\b" + re.escape(name) + r"\s*\([^;{]*\)\s*\{", code) else 0):
            out.append(p)
    return sorted(out)


def exit_resets() -> list[str]:
    """Every place outside the tests that clears the give-up flag (sticky-flag evidence for class 2)."""
    hits = []
    for p in glob.glob(os.path.join(ROOT, "src", "readable", "**", "*.[ch]"), recursive=True) + \
            glob.glob(os.path.join(ROOT, "include", "readable", "*.h")):
        if os.sep + "tests" + os.sep in p:
            continue
        for i, t in enumerate(open(p, encoding="utf-8", errors="replace").read().splitlines(), 1):
            if re.search(r"->exit\s*=\s*EXIT_NONE", t):
                hits.append(f"{os.path.relpath(p, ROOT).replace(os.sep, '/')}:{i}")
    return hits


def decl_type(lines: list[str], ln: int, var: str) -> str:
    """The declared type of `var` in the function around line ln (a parameter or a local), as written."""
    rx = re.compile(r"\b((?:const\s+)?(?:u?int(?:8|16|32|64)_t|gaddr|int|unsigned))\s+" + re.escape(var) + r"\b")
    for i in range(ln - 1, max(-1, ln - 80), -1):
        m = rx.search(lines[i])
        if m:
            return m.group(1)
    return ""


def check_class1(c, m, lines, host):
    ln = m.line
    t = {}
    t["host_survived"] = bool(host) and host.get("host") == "survived"
    xg = str(c.get("host_extra_giveups") or "").strip()
    t["giveup_count_moved"] = xg.lstrip("-").isdigit() and int(xg) != 0
    # the planted change sits in a give-up decision: an `if (...)` whose body is `return fe_use_original(ctx)`,
    # or a `*_ready` helper / give-up condition that such an `if` asks
    here = lines[ln - 1]
    nxt = lines[ln] if ln < len(lines) else ""
    in_guard_if = bool(re.match(r"^\s*if\s*\(", here)) and (GIVEUP_BODY_RX.search(here) or GIVEUP_BODY_RX.search(nxt))
    in_ready = m.where.endswith("_ready")
    cond_giveup = bool(re.search(r"fe_static_ready|_caches_ready|_ready\s*\(", here)) and \
        any(GIVEUP_BODY_RX.search(lines[j]) for j in range(ln - 1, min(len(lines), ln + 3)))
    t["in_giveup_decision"] = bool(in_guard_if or in_ready or cond_giveup)
    t["not_named_can_change"] = c["id"] not in CAN_CHANGE
    direction, extra, why = C1_READ.get(c["id"], ("", "", "no reading note"))
    t["reading_note"] = bool(direction)
    t["never_wrong_answer_by_reading"] = direction in ("more", "later")
    ok = all(t.values())
    verdict = ("fits" if not extra else "fits, with a note") if ok else "does not fit"
    return t, verdict, f"{direction}{' + ' + extra if extra else ''}: {why}; edited in {m.where}, line {ln}"


def check_class2(c, m, lines, host, resets):
    ln = m.line
    t = {}
    t["host_survived"] = bool(host) and host.get("host") == "survived"
    t["is_return_const_plus_one"] = c["operator"] == "const" and bool(re.match(r"^\s*return\s+\S+\s*;", lines[ln - 1]))
    t["guard_is_only_fe_gave_up"] = bool(GUARD_RX.match(prev_code_line(lines, ln)))
    t["flag_sticky"] = all(r.startswith("include/readable/fe_guest.h") or r.startswith("src/readable/core/capture.c")
                           for r in resets)
    path = os.path.join(ROOT, c["file"])
    callers = caller_files(m.where)
    stores = {os.path.relpath(p, ROOT).replace(os.sep, "/"): stores_in(p) for p in sorted(set(callers + [path]))}
    t["no_guest_store_in_file_or_callers"] = all(v == 0 for v in stores.values())
    t["not_named_can_change"] = c["id"] not in CAN_CHANGE
    ok = all(t.values())
    why = (f"line {ln} `{lines[ln - 1].strip()}` right after `{prev_code_line(lines, ln).strip()}` in {m.where}; "
           f"the flag stays set until FE_ENTRY replays the original, so the value is thrown away; "
           f"stores in this file and its callers' files: {sum(stores.values())}")
    return t, ("fits" if ok else "does not fit"), why, stores


def check_class3(c, m, lines, host):
    ln = m.line
    src = lines[ln - 1]
    t = {}
    t["host_survived"] = bool(host) and host.get("host") == "survived"
    new = re.sub(r"[uUlL]+$", "", c["new"])
    try:
        v_new = int(new, 0)
    except ValueError:
        v_new = None
    # find the compared operand: `<var> ==/!= <old>`
    mm = re.search(r"\b([a-z_]\w*)\s*(==|!=)\s*" + re.escape(c["old"]) + r"\b", src)
    var = mm.group(1) if mm else ""
    typ = decl_type(lines, ln, var) if var else ""
    too_big = v_new is not None and typ in ("uint32_t", "int32_t", "const uint32_t") and v_new > 0xFFFFFFFF
    ptr_one = v_new == 1 and typ == "gaddr"
    t["planted_value_cannot_occur"] = bool(too_big or ptr_one)
    t["not_named_can_change"] = c["id"] not in CAN_CHANGE
    effect, why = C3_READ.get(c["id"], ("", "no reading note"))
    t["original_value_gives_same_answer_by_reading"] = effect == "same"
    written_ok = t["host_survived"] and t["planted_value_cannot_occur"] and t["not_named_can_change"]
    if written_ok and effect == "same":
        verdict = "fits"
    elif written_ok:
        verdict = "fits the written test; held for a person"
    else:
        verdict = "does not fit"
    kind = (f"`{var}` is {typ}; {c['new']} is more than 32 bits" if too_big else
            f"`{var}` is a guest pointer (gaddr); a pointer of 1 is never a real object" if ptr_one else
            f"`{var}` type {typ or '?'}")
    return t, verdict, f"{kind}; {why}; line {ln}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--three", default=os.path.join(ROOT, "build", "h6three", "three-r37.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "equiv", "equiv_proposal.json"))
    a = ap.parse_args()
    cand = json.load(open(a.three, encoding="utf-8"))["candidates"]
    classes = cand["classes"]
    n237 = sum(v["count"] for v in classes.values())
    new70 = cand["new_not_sorted"]
    assert cand["count"] == 237 and n237 == 237, (cand["count"], n237)
    resets = exit_resets()

    out = dict(source=os.path.relpath(a.three, ROOT).replace(os.sep, "/"), count_237=n237, count_unsorted=len(new70),
               written_tests=WRITTEN, giveup_flag_resets=resets, marks_nothing=True,
               mutants_equivalent_csv_touched=False, headline_changed=False, classes={}, unsorted={})
    problems = []

    def one(c, cls):
        m, err = remap(c)
        stem = c["stem"]
        label = (c.get("newest_host") or "").split("(")[-1].rstrip(")") or c.get("label", "")
        host = host_row(label, stem, c["id"]) if label else None
        row = dict(id=c["id"], file=c["file"], function=c["function"], line_then=c["line"], operator=c["operator"],
                   old=c["old"], new=c["new"], source_line=c["source_line"], h6_today=c.get("today"),
                   host_label=label, host=(host or {}).get("host"), host_extra_giveups=c.get("host_extra_giveups"),
                   from_set="237" if c in all237 else "70")
        if m is None:
            row.update(verdict="does not fit", why=f"cannot place it in today's source: {err}", tests={})
            problems.append(c["id"])
            return row
        lines = lines_of(os.path.join(ROOT, c["file"]))
        row["line_now"] = m.line
        row["edited_in"] = m.where
        if cls == 1:
            t, v, why = check_class1(c, m, lines, host)
        elif cls == 2:
            t, v, why, stores = check_class2(c, m, lines, host, resets)
            row["stores"] = stores
        else:
            t, v, why = check_class3(c, m, lines, host)
        row.update(tests=t, verdict=v, why=why)
        return row

    all237 = [c for v in classes.values() for c in v["items"]]
    for name, cls in CLASS_OF.items():
        rows = [one(c, cls) for c in classes[name]["items"]]
        rows += [one(c, cls) for c in new70 if c.get("class") == name]
        out["classes"][name] = dict(class_number=cls, written_test=WRITTEN[cls], count_checked=len(rows),
                                    verdicts=dict(collections.Counter(r["verdict"] for r in rows)), cases=rows)

    sorted70 = collections.defaultdict(list)
    for c in new70:
        k, note = c.get("class", "other"), "h6three.classify rule list"
        if c["id"] in SORT_70:
            k, note = SORT_70[c["id"]]
            note = "by hand: " + note
        sorted70[k].append(dict(id=c["id"], file=c["file"], line=c["line"], operator=c["operator"], old=c["old"],
                                new=c["new"], source_line=c["source_line"], label=c.get("label"),
                                newest_host=c.get("newest_host"), class_rule=c.get("class"), note=note,
                                can_change_answer_per_notes=c["id"] in CAN_CHANGE))
    out["unsorted"] = {k: dict(count=len(v), in_classes_1_to_3=k in CLASS_OF, cases=v)
                       for k, v in sorted(sorted70.items(), key=lambda kv: -len(kv[1]))}
    out["unsorted_count_check"] = sum(len(v) for v in sorted70.values())
    out["problems"] = problems

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    for name, d in out["classes"].items():
        print(f"class {d['class_number']} {name}: checked {d['count_checked']} -> {d['verdicts']}")
        for r in d["cases"]:
            bad = [k for k, v in r["tests"].items() if not v]
            print(f"  {r['id']:32s} [{r['from_set']}] {r['verdict']:42s} failed={bad}")
    print("unsorted 70 by class:", {k: v["count"] for k, v in out["unsorted"].items()},
          "total", out["unsorted_count_check"])
    print("give-up flag cleared at:", resets)
    print("problems:", problems or "none")
    print("wrote", os.path.relpath(a.out, ROOT))
    return 0 if not problems and out["unsorted_count_check"] == len(new70) else 1


if __name__ == "__main__":
    sys.exit(main())
