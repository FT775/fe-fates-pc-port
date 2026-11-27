#!/usr/bin/env python3
"""Tests for tools/harness/h6three.py (docs/harness/H6_THREE.md).

    python tools/harness/test_h6three.py        # small made-up inputs only, a few seconds

The inputs are tiny made-up files (a sampled H6 json with its mutants.csv, an H5 json, host verdict csvs, an
offline json and a live summary) under build/h6three/test-*/ (removed at the end). Nothing of the real runs is read
except the readable sources' #defines and the batches' diff scripts (read-only, for the file status and the classes).
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import shutil
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import h6three as h3  # noqa: E402

TMP = os.path.join(h3.ROOT, "build", "h6three", f"test-{os.getpid()}")
MUT_COLS = ["id", "function", "address", "edited", "file", "line", "operator", "old", "new", "result", "by",
            "reached", "why", "col", "source_line"]
HOST_COLS = ["id", "function", "line", "operator", "old", "new", "h6", "h6_reached", "h6_why", "host", "host_by",
             "host_extra_giveups"]
SRC = "src/readable/support/support_unit.c"  # a real batch with a host adapter (support_diff.py)


def mrow(mid, fn, line, result, reached="", op="const", old="0", new="1", src="return 0;", col="4", file=SRC):
    return dict(id=mid, function=fn, address="0x0", edited=fn, file=file, line=str(line), operator=op, old=old,
                new=new, result=result, by="", reached=reached, why="", col=col, source_line=src)


def write_csv(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


class Fixture:
    """A made-up sample: function f (span 10-20, H5 never ran 15-16), helper lines 30+ (h: no helper ran)."""

    def __init__(self, root):
        self.root = root
        self.mut = os.path.join(root, "mutate", "mutants.csv")
        rows = [
            mrow("f-000", "f", 12, "caught"),
            mrow("f-001", "f", 12, "caught"),
            mrow("f-002", "f", 12, "survived", "reached x5"),          # reached, not noticed
            mrow("f-003", "f", 15, "survived", "not reached"),          # never (H5 agrees)
            mrow("f-004", "f", 13, "survived", "not reached"),          # sample gap (H5 says it ran)
            mrow("f-005", "f", 31, "survived", "not reached"),          # helper line: f's helpers half ran -> no data
            mrow("f-006", "f", 12, "stillborn"),
            mrow("g-000", "g", 40, "caught"),
            mrow("g-001", "g", 52, "survived", "not reached"),          # helper line: g's helpers never ran -> never
            mrow("x-000", "other_fn", 1, "survived", "not reached"),   # not a function the sample judged: ignored
        ]
        write_csv(self.mut, MUT_COLS, rows)
        self.sample = os.path.join(root, "h6_sample.json")
        self.h5 = os.path.join(root, "h5.json")
        write_json(self.sample, dict(total=dict(run="t-run", caught=3, judged=8, h5_input=self.h5), functions={
            "f": dict(source=SRC, mutants_csv=self.mut, judged=6, caught=2),
            "g": dict(source=SRC, mutants_csv=self.mut, judged=2, caught=1)}))
        write_json(self.h5, dict(total={}, overrides=[
            dict(name="f", source=SRC, met=True, span=[10, 20], never_run_lines=[15, 16], lines=8, lines_run=6,
                 with_helpers=dict(lines=12, lines_run=8)),
            dict(name="g", source=SRC, met=True, span=[40, 45], never_run_lines=[], lines=4, lines_run=4,
                 with_helpers=dict(lines=9, lines_run=4))]))
        self.host = os.path.join(root, "h6host")
        self.offline = os.path.join(root, "offline.json")
        self.cheat = os.path.join(root, "offline_cheat.json")
        self.live = os.path.join(root, "summary.json")
        cap = lambda n, **kw: dict(records=n, match=n - 2, gave_up=1, incomplete=1, bad=0, **kw)  # noqa: E731
        write_json(self.offline, dict(verdict="PASS", runs=[
            dict(route="bt-ch2", capture=cap(100)), dict(route="bt-ch3", capture=cap(50)),
            dict(route="rv-ch6", capture=cap(30)), dict(route="opt-ch8-set", capture=cap(10))]))
        write_json(self.cheat, dict(verdict="PASS", runs=[dict(route="cheat-family", cheat=True, capture=cap(7))]))
        write_json(self.live, dict(runs=[dict(route="bt-ch25", cheat=False, capture=cap(20, mismatch_mem=0))]))

    def host_run(self, label, rows, mutants_csv=None, stem="support_unit"):
        p = os.path.join(self.host, label, stem + ".csv")
        write_csv(p, HOST_COLS, rows)
        if mutants_csv:
            write_json(os.path.join(self.host, label, stem + ".json"), dict(mutants_csv=mutants_csv))
        return p

    def args(self, *extra):
        return ["--sample", self.sample, "--host-dir", self.host, "--offline", self.offline, "--offline-cheat",
                self.cheat, "--live", self.live, "--reasons", os.path.join(self.root, "reasons.csv"), *extra]


def hrow(mid, fn, line, h6, host, op="const", old="0", new="1", why="", extra=""):
    return dict(id=mid, function=fn, line=str(line), operator=op, old=old, new=new, h6=h6, host=host, h6_why=why,
                host_extra_giveups=extra)


class Base(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(TMP, self._testMethodName)
        shutil.rmtree(self.root, ignore_errors=True)
        os.makedirs(self.root)
        self.fx = Fixture(self.root)

    def run_main(self, *extra):
        out = io.StringIO()
        js = os.path.join(self.root, "out.json")
        with contextlib.redirect_stdout(out):
            rc = h3.main(self.fx.args("--json", js, *extra))
        with open(js, encoding="utf-8") as fh:
            return rc, json.load(fh), out.getvalue()


class TestNumber1(Base):
    def test_reach_kinds(self):
        lines = h3.h5_line_map(self.fx.h5)
        helpers = h3.h5_helpers(self.fx.h5)
        self.assertEqual(helpers, {"f": (4, 2), "g": (5, 0)})
        kind = lambda line, fn="f", reached="not reached": h3.reach_of(  # noqa: E731
            dict(file=SRC, line=str(line), function=fn, reached=reached), lines, helpers)
        self.assertEqual(kind(12, reached="reached x3"), "reached")
        self.assertEqual(kind(15), "never")
        self.assertEqual(kind(13), "sample-gap")
        self.assertEqual(kind(31), "no-line-data")
        self.assertEqual(kind(52, "g"), "never")

    def test_unmet_override_lines_never_ran(self):
        write_json(self.fx.h5, dict(overrides=[dict(name="f", source=SRC, met=False, span=[10, 20],
                                                    never_run_lines=[])]))
        lines = h3.h5_line_map(self.fx.h5)
        self.assertFalse(lines[SRC][12])

    def test_rates_leave_never_out(self):
        rc, R, out = self.run_main()
        self.assertEqual(rc, 0)
        T = R["number1"]["total"]
        self.assertEqual((T["caught"], T["judged"], T["stillborn"]), (3, 8, 1))
        self.assertEqual((T["never"], T["sample_gap"], T["no_line_data"]), (2, 1, 1))
        self.assertEqual(T["denominator"], 6)        # 8 judged - 2 never
        self.assertEqual(T["rate"], 50.0)
        self.assertEqual(T["denominator_strict"], 5)
        self.assertEqual(T["h6_rate"], 37.5)
        self.assertIn("3 / 6 (50.0%)", out)
        self.assertTrue(R["check"]["agrees"])

    def test_sample_disagreeing_with_csv_fails(self):
        with open(self.fx.sample, encoding="utf-8") as fh:
            s = json.load(fh)
        s["total"]["caught"] = 4
        write_json(self.fx.sample, s)
        rc, R, out = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("WARNING", out)


class TestNumber2(Base):
    def test_same_bug_only_and_newest_wins(self):
        other = os.path.join(self.root, "old_mutants.csv")
        write_csv(other, MUT_COLS, [mrow("f-002", "f", 12, "survived", src="return 0;"),
                                    mrow("f-003", "f", 15, "survived", src="something else;")])
        self.fx.host_run("r13-old", [hrow("f-002", "f", 12, "survived", "survived"),
                                     hrow("f-003", "f", 15, "survived", "caught")], mutants_csv=other)
        time.sleep(0.05)
        p = self.fx.host_run("r14-new", [hrow("f-002", "f", 12, "survived", "caught"),
                                         hrow("f-000", "f", 12, "caught", "caught"),
                                         hrow("f-004", "f", 99, "survived", "caught")])  # no csv: line must agree
        os.utime(p, (time.time() + 5, time.time() + 5))
        rc, R, out = self.run_main()
        f = R["number2"]["files"][SRC]
        self.assertEqual(f["status"], "")
        # f-002: newest says caught; f-003: the old run's source line differs -> no verdict; f-004: line differs
        self.assertEqual((f["surv"], f["surv_known"], f["surv_host_caught"]), (5, 1, 1))
        self.assertEqual((f["caught_known"], f["caught_host_caught"]), (1, 1))
        self.assertFalse(f["survivors_complete"])
        self.assertIsNone(f["either_rate"])
        self.assertIn("partial", out)

    def test_status_of_files_without_a_host_test(self):
        self.assertIn("another workflow", h3.host_status("src/readable/ai_score/ai_score_sim.c", {"x"}))
        self.assertIn("no h6host adapter", h3.host_status("src/readable/ai/made_up.c", {"x"}))
        self.assertIn("no h6host adapter", h3.host_status("src/readable/event/made_up.c", {"x"}))
        self.assertIn("does not test", h3.host_status("src/readable/battle/made_up.c", {"x"}))
        self.assertIn("never names", h3.host_status("src/readable/unit/growth_roll.c", {"no_such_function_xyz"}))
        # round 17: the 13 files that had none now have a host test, each through its own script
        for f in ("ai/ai_area.c", "ai/ai_items.c", "ai/ai_permission.c", "ai/ai_think.c", "ai/ai_value.c",
                  "battle/triangle_tables.c", "battle2/battle2_bonus.c", "battle2/battle2_calc.c",
                  "battle2/battle2_rules.c", "class_change/class_change.c", "event/flags.c", "shop_price/shop_price.c",
                  "unit/forces.c"):
            self.assertEqual(h3.host_status("src/readable/" + f, {"x"}), "", f)
        self.assertEqual(h3.host_status("src/readable/battle/stance_bonus.c", {"x"}), "")
        self.assertEqual(h3.host_status("src/readable/battle/formula_unit.c", {"unit_attack"}), "")


class TestNumber3(Base):
    def test_families_and_cheat_apart(self):
        n3 = h3.number3(self.fx.offline, self.fx.cheat, [self.fx.live])
        F = n3["families"]
        self.assertEqual(sorted(F), ["bt", "cheat", "opt", "rv"])
        self.assertEqual((len(F["bt"]["routes"]), F["bt"]["records"]), (3, 170))
        self.assertEqual(F["cheat"]["records"], 7)
        self.assertEqual(n3["total"]["records"], 210)     # cheat not in the total
        self.assertEqual(n3["total"]["routes"], 5)
        self.assertEqual(n3["total"]["bad"], 0)

    def test_every_difference_kind_counts(self):
        write_json(self.fx.live, dict(runs=[dict(route="bt-ch25", capture=dict(records=5, match=3, bad=1,
                                                                                 mismatch_mem=1, unfaithful=1))]))
        n3 = h3.number3(None, None, [self.fx.live])
        self.assertEqual((n3["families"]["bt"]["bad"], n3["families"]["bt"]["differences"]), (1, 2))

    def test_missing_input_is_said(self):
        n3 = h3.number3(os.path.join(self.root, "nope.json"), None, [])
        self.assertTrue(n3["inputs"][0]["missing"])


class TestReasons(Base):
    def test_most_specific_row_wins(self):
        p = os.path.join(self.root, "reasons.csv")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("file,function,lines,reason,detail\n# a comment, with commas,,,,\n"
                     "support_unit.c,,,whole file,\nsupport_unit.c,,14-16,file lines,\n"
                     "support_unit.c,f,,function,\nsupport_unit.c,f,15,function line,x\n")
        rs = h3.load_reasons(p)
        self.assertEqual(len(rs), 4)
        r = lambda fn, line: h3.reason_of(dict(file=SRC, function=fn, line=str(line)), rs)["reason"]  # noqa: E731
        self.assertEqual(r("f", 15), "function line")
        self.assertEqual(r("f", 12), "function")
        self.assertEqual(r("g", 15), "file lines")
        self.assertEqual(r("g", 30), "whole file")
        self.assertIsNone(h3.reason_of(dict(file="src/readable/x/other.c", function="f", line="1"), rs))

    def test_groups_in_report(self):
        with open(os.path.join(self.root, "reasons.csv"), "w", encoding="utf-8") as fh:
            fh.write("file,function,lines,reason,detail\nsupport_unit.c,f,15,child unit (family record),\n")
        rc, R, out = self.run_main("--never")
        g = R["never_by_reason"]
        self.assertEqual(g["child unit (family record)"]["count"], 1)
        self.assertEqual(g["not sorted yet"]["count"], 2)   # g-001 (never) and f-005 (no line data)
        self.assertEqual(list(g)[-1], "not sorted yet")
        self.assertIn("f-003", out)


class TestCandidates(Base):
    def test_classes(self):
        c = lambda **kw: h3.classify(dict(dict(operator="const", old="0", new="1", source_line="", col=""), **kw))  # noqa: E731
        self.assertEqual(c(h6_why="harmless: gives up more"), "give_up_only")
        self.assertEqual(c(operator="named", old="STAT_STR", new="(STAT_STR + 1)", host_extra_giveups="903"),
                         "give_up_only")
        self.assertEqual(c(old="0u", new="1u", source_line="if (guest_call(ctx, MOVE_MapGet, 0u, 0u, 0u, 0u) == 0)"),
                         "no_arg_call_words")
        self.assertEqual(c(operator="arith", old="+", new="-",
                           source_line="gaddr a = guest_ptr(ctx, mine + FAMILY_PARENT_PERSON);"), "zero_offset")
        self.assertEqual(c(operator="arith", old="+", new="-", source_line="x = y + 5;"), "other")
        self.assertEqual(c(operator="swap", old="f(a, b)", new="b, a"), "swapped_arguments")
        self.assertEqual(c(operator="rel", old="<", new="<="), "boundary_compare")
        self.assertEqual(c(source_line="return v < 0 ? 0 : v;"), "boundary_compare")
        self.assertEqual(c(old="9", new="10", source_line="int32_t f = t[clamp(x, 0, 9)];"), "clamp_limit")
        self.assertEqual(c(old="0xFFFFFFFFu", new="0x100000000u", source_line="if (type == 0xFFFFFFFFu)"),
                         "impossible_value")
        self.assertEqual(c(source_line="if (parent == 0)"), "impossible_value")
        self.assertEqual(c(source_line="return 0;"), "early_return_value")
        self.assertEqual(c(old="1", new="2", source_line="forged = 1;"), "start_value")
        self.assertEqual(c(old="1u", new="2u", source_line="return f(ctx, unit, 1u, 0u, 0);"), "call_argument_constant")
        self.assertEqual(c(operator="named", old="STAT_LCK", new="(STAT_LCK + 1)"), "named_constant")
        self.assertEqual({k for k, _ in h3.CLASSES}, set(h3.CLASS_TEXT))

    def test_return_after_give_up_reads_the_source(self):
        fake = os.path.join(self.root, "fake.c")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write("int f(void) {\n    if (fe_gave_up(ctx))\n        return 0;\n    if (x)\n        return 0;\n}\n")
        rel = os.path.relpath(fake, h3.ROOT)
        c = lambda line: h3.classify(dict(operator="const", old="0", new="1", source_line="return 0;", line=line,  # noqa: E731
                                          file=rel))
        self.assertEqual(c(3), "return_after_give_up")
        self.assertEqual(c(5), "early_return_value")

    def test_candidate_labels_and_today(self):
        self.fx.host_run("r13-after", [hrow("f-002", "f", 12, "survived", "survived", op="rel", old="<", new="<="),
                                       hrow("f-000", "f", 12, "caught", "caught")])
        self.fx.host_run("r14-three", [hrow("f-003", "f", 15, "survived", "survived")])
        rc, R, out = self.run_main("--candidates")
        C = R["candidates"]
        self.assertEqual(C["count"], 1)       # r13-after's miss only; r14-three's is "new, not sorted"
        self.assertEqual(C["classes"]["boundary_compare"]["count"], 1)
        self.assertEqual(len(C["new_not_sorted"]), 1)
        self.assertIn("FOR THE OWNER TO DECIDE", out)
        self.assertIn("NEW (host runs after round 13", out)
        # the candidate's row in today's sample (same id/op/old/new) is looked up, not assumed
        self.assertEqual(C["classes"]["boundary_compare"]["items"][0]["today"], "not in today's sample")

    def test_owner_cleared_leave_the_pile_only(self):
        """An entry of the equivalence list (pinned "[id X line N]") clears that candidate only; number 1 unchanged."""
        self.fx.host_run("r13-after", [hrow("f-002", "f", 12, "survived", "survived"),
                                       hrow("f-004", "f", 14, "survived", "survived")])
        eq = os.path.join(self.root, "equiv.csv")
        write_csv(eq, ["function", "operator", "old", "new", "col", "source_line", "why"],
                  [dict(function="f", operator="const", old="0", new="1", col="", source_line="",
                        why="owner ok (test) [id f-002 line 12]")])
        rc0, R0, out0 = self.run_main("--equiv", "")
        rc, R, out = self.run_main("--equiv", eq)
        C = R["candidates"]
        self.assertEqual((C["count"], C["cleared"], C["pile"]), (2, 1, 1))
        self.assertEqual(R0["candidates"]["pile"], 2)
        self.assertEqual(R["number1"]["total"], R0["number1"]["total"])
        self.assertIn("cleared by the owner: 1", out)
        self.assertIn("none marked", out0)


class TestReadOnly(Base):
    def test_writes_only_the_json(self):
        before = sorted(os.listdir(self.root))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            h3.main(self.fx.args())
        self.assertEqual(sorted(os.listdir(self.root)), before)


def main():
    try:
        r = unittest.main(exit=False, verbosity=1).result
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
