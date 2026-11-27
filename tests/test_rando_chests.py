"""Self-tests for the randomizer's chests track (tools/randomizer/chests.py; docs/rando/CHESTS.md).

    python -m unittest tests.test_rando_chests          (from the repo root)

A made-up script (built here, no game bytes) and the items track's made-up tables first; the last class runs on the
user's own extracted RomFS when it is there (skipped otherwise): every script walks to its end, the counts, and
many seeds through every guard. The track is off by default: nothing planned, the plan untouched.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, ROOT)
import chests as C  # noqa: E402
from tests import test_rando_items as TI  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _edition as E  # noqa: E402  (round 84: Seal legs run only in the Seal edition)

SEEDS = [f"c{n}" for n in range(30)]


def make_cmb(funcs: list[tuple[int, list[int], list[tuple]]]) -> bytes:
    """A made-up compiled script in the format chests.read_cmb reads. funcs: (event type, event args, code), code
    = [("call", name, argc) | ("str", text) | ("int", n) | ("pop",)]."""
    strings: list[bytes] = []

    def soff(s: str) -> int:
        b = s.encode("utf-8") + b"\0"
        off = sum(len(x) for x in strings)
        strings.append(b)
        return off
    names = {}
    bodies = []
    for typ, args, code in funcs:
        out = bytearray()
        for ins in code:
            if ins[0] == "call":
                o = names.setdefault(ins[1], soff(ins[1]))
                out += bytes([0x47]) + o.to_bytes(2, "big") + bytes([ins[2]])
            elif ins[0] == "str":
                o = soff(ins[1])
                out += bytes([0x1D]) + o.to_bytes(2, "big")
            elif ins[0] == "int":
                out += bytes([0x19, ins[1]])
            elif ins[0] == "pop":
                out += bytes([0x21])
        out += bytes([0x54, 0, 0, 0])
        bodies.append((typ, args, bytes(out)))
    head = 0x40
    tab = head
    pos = tab + 4 * (len(bodies) + 1)
    blobs, starts = [], []
    for typ, args, code in bodies:
        f = pos
        argo = f + 0x18
        codeo = argo + 4 * len(args)
        h = struct.pack("<IIBBHIII", f, codeo, typ, len(args), 0, len(starts), 0, argo)
        blob = h + struct.pack(f"<{len(args)}I", *args) + code
        starts.append(f)
        blobs.append(blob)
        pos += len(blob)
    pool = pos
    d = bytearray(b"cmb\0" + struct.pack("<I", 0x20110819) + bytes(head - 8))
    struct.pack_into("<I", d, C.H_FUNCS, tab)
    struct.pack_into("<I", d, C.H_POOL, pool)
    d += struct.pack(f"<{len(starts) + 1}I", *(starts + [0]))
    for b in blobs:
        d += b
    for s in strings:
        d += s
    return bytes(d)


GIVE = lambda iid: [("call", "ev::MindGetUnit", 0), ("str", iid), ("call", "ev::ItemGain", 2), ("pop",)]  # noqa: E731


class ReaderTests(unittest.TestCase):
    def test_reads_chest_village_talk_event_and_gold(self):
        d = make_cmb([(0x15, [3, 4, 1, 1, 10, 0, 0, 0], GIVE("IID_キルソード")),
                      (0x15, [7, 8, 1, 1, 1, 0, 0, 0], GIVE("IID_アーマーキラー")),
                      (0x17, [0, 0, 0, 2, 0, 0], GIVE("IID_調合薬")),
                      (0x00, [], [("int", 0), ("int", 5), ("call", "ev::GoldGain", 2), ("pop",)]),
                      (0x0C, [], [("call", "ev::ArgsGetString", 0), ("call", "ev::ItemGain", 2), ("pop",)])])
        rows, bad = C.calls_in("Scripts/A007_Terrain.cmb", d)
        self.assertEqual(bad, 0)
        self.assertEqual([r["kind"] for r in rows], ["chest", "village", "talk", "gold", "event"])
        self.assertEqual([r["item"] for r in rows], ["IID_キルソード", "IID_アーマーキラー", "IID_調合薬", "gold:5", "variable"])
        self.assertEqual([r["call"] for r in rows], [0, 1, 2, 3, 4])
        self.assertEqual((rows[0]["x"], rows[0]["y"], rows[0]["chapter"]), (3, 4, "A007"))
        self.assertTrue(all(f["walked"] for f in C.read_cmb(d)))

    def test_not_a_script_is_refused(self):
        with self.assertRaises(C.ChestsError):
            C.read_cmb(b"xxxx" + bytes(60))

    def test_chapter_of(self):
        self.assertEqual(C.chapter_of("C/R002_Terrain.cmb"), "R002")
        self.assertEqual(C.chapter_of("A004.cmb"), "A004")


def fake_rows():
    r = lambda ch, i, kind, item, call="ev::ItemGain", x=None: dict(  # noqa: E731
        {"chapter": ch, "file": f"{ch}_Terrain.cmb", "call": i, "func": i, "call_name": call, "kind": kind,
         "item": item}, **({"x": x, "y": x} if x is not None else {}))
    return [r("A007", 0, "chest", "IID_キルソード", x=1), r("A007", 1, "chest", "IID_アーマーキラー", x=2),
            r("A007", 2, "village", "IID_鋼の剣", x=3), r("A007", 3, "chest", "IID_扉の鍵", x=4),
            r("A007", 4, "chest", "IID_マスタープルフ", x=5), r("A008", 0, "talk", "IID_調合薬"),
            r("A008", 1, "event", "IID_キルソード"), r("A008", 2, "event", "IID_鉄の剣", call="ev::ItemGainSilent"),
            r("A008", 3, "chest", "variable", x=6), r("Z000", 0, "chest", "IID_キルソード", x=7),
            r("A009", 0, "chest", "IID_キルソード", x=8), r("A009", 1, "chest", "IID_キルソード", x=9)]


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.f = TI.fake_facts()
        self.rows = fake_rows()

    def test_off_by_default_plans_nothing_and_leaves_the_plan(self):
        self.assertEqual(C.plan_chests(self.f, self.rows, "s1"), ([], []))
        plan = {"seed": "s1", "persons": []}
        before = json.dumps(plan, sort_keys=True)
        self.assertEqual(json.dumps(C.add_to_plan(plan, []), sort_keys=True), before)

    def test_same_seed_same_plan_and_guards_green(self):
        on = {"chests": "on"}
        diff = set()
        for s in SEEDS:
            e, _ = C.plan_chests(self.f, self.rows, s, on)
            e2, _ = C.plan_chests(self.f, self.rows, s, on)
            self.assertEqual(e, e2)
            g = C.check_chests(self.f, self.rows, e, on)
            self.assertTrue(all(v["ok"] for v in g.values()), (s, {k: v for k, v in g.items() if not v["ok"]}))
            diff.add(json.dumps(e, sort_keys=True))
        self.assertGreater(len(diff), 1, "seeds differ")

    def test_only_changeable_calls_are_planned(self):
        e, _ = C.plan_chests(self.f, self.rows, "s2", {"chests": "on"})
        planned = {(x["chapter"], x["orig"]) for x in e}
        self.assertIn(("A007", "IID_キルソード"), planned)
        self.assertIn(("A008", "IID_調合薬"), planned)          # a talk gift
        for kept in (("A007", "IID_扉の鍵"), ("A007", "IID_マスタープルフ"), ("A008", "IID_鉄の剣"),
                     ("Z000", "IID_キルソード"), ("A008", "variable")):
            self.assertNotIn(kept, planned, kept)
        self.assertNotIn(("A008", "IID_キルソード"), planned, "event gifts are not changed")

    def test_same_item_twice_in_a_chapter_is_one_slot(self):
        e, _ = C.plan_chests(self.f, self.rows, "s3", {"chests": "on"})
        a9 = [x for x in e if x["chapter"] == "A009"]
        self.assertEqual(len(a9), 1)
        self.assertEqual(len(a9[0]["calls"]), 2)

    def test_kinds_option(self):
        e, _ = C.plan_chests(self.f, self.rows, "s4", {"chests": "on", "chest_kinds": "chest"})
        self.assertEqual({x["kind"] for x in e}, {"chest"})

    def test_guard_catches_a_bad_entry(self):
        on = {"chests": "on"}
        e, _ = C.plan_chests(self.f, self.rows, "s5", on)
        bad = [dict(e[0], new="IID_扉の鍵")] + e[1:]
        g = C.check_chests(self.f, self.rows, bad, on)
        self.assertFalse(g["chests: story_and_key_items_kept"]["ok"])
        bad = [dict(e[0], new="IID_調合薬")] + e[1:]
        self.assertFalse(C.check_chests(self.f, self.rows, bad, on)["chests: same_band"]["ok"])
        kept = {"chapter": "A007", "kind": "chest", "orig": "IID_扉の鍵", "new": "IID_鉄の剣",
                "calls": [["A007_Terrain.cmb", 3]]}
        self.assertFalse(C.check_chests(self.f, self.rows, e + [kept], on)["chests: only_changeable_calls"]["ok"])

    def test_engine_table_and_plan_list(self):
        e, _ = C.plan_chests(self.f, self.rows, "s6", {"chests": "on"})
        t = C.engine_table(e)
        for x in e:
            if x["new"] != x["orig"]:
                self.assertEqual(t[x["chapter"]][x["orig"]], x["new"])
        p = C.add_to_plan({}, e)
        self.assertEqual(len(p["chests"]), len(e))


class HookSharedTests(unittest.TestCase):
    """Round 71: the hook knows only (chapter, item), so a slot whose item a KEPT ev::ItemGain gift of the same chapter
    also hands over is kept whole."""

    def setUp(self):
        self.f = TI.fake_facts()

    def test_a_slot_shared_with_a_kept_gift_is_kept(self):
        extra = {"chapter": "A008", "file": "A008.cmb", "call": 9, "func": 9, "call_name": "ev::ItemGain",
                 "kind": "event", "item": "IID_調合薬"}
        rows = fake_rows() + [extra]
        on = {"chests": "on"}
        e, _ = C.plan_chests(self.f, rows, "sh1", on)
        self.assertNotIn(("A008", "IID_調合薬"), {(x["chapter"], x["orig"]) for x in e})
        self.assertIn(("A007", "IID_キルソード"), {(x["chapter"], x["orig"]) for x in e})
        g = C.check_chests(self.f, rows, e, on)
        self.assertTrue(all(v["ok"] for v in g.values()))
        # the talk gift planned anyway is caught by the guard
        talk = {"chapter": "A008", "kind": "talk", "orig": "IID_調合薬", "new": "IID_調合薬",
                "calls": [["A008_Terrain.cmb", 0]]}
        self.assertFalse(C.check_chests(self.f, rows, e + [talk], on)["chests: only_changeable_calls"]["ok"])

    def test_a_kept_kind_shares_too(self):
        # chest_kinds=chest keeps the talk gift: nothing of A008 is planned
        e, _ = C.plan_chests(self.f, fake_rows(), "sh2", {"chests": "on", "chest_kinds": "chest"})
        self.assertFalse(any(x["chapter"] == "A008" for x in e))

    def test_guards_carry_the_randomizer_detail_field(self):
        g = C.check_chests(self.f, fake_rows(), [], {"chests": "on"})
        self.assertTrue(all("detail" in v and "ok" in v for v in g.values()))


# the same list as fates_rando_chests.rs's tests (LIST): both readers take it and refuse the same changes
RUST_LIST = ("fates-rando-chests 1\nseed c71\nc A007 4949445f41 4949445f42 100\nc A007 4949445f43 4949445f44 110\n"
             "c X001 4949445f41 4949445f44 110\nend 3\n")


class ListTests(unittest.TestCase):
    """Round 71: chests.txt, the list the core's hook reads (fates_rando_chests.rs Table::parse)."""

    E = [{"chapter": "A007", "kind": "chest", "orig": "IID_キルソード", "new": "IID_鋼の剣", "calls": []},
         {"chapter": "A007", "kind": "chest", "orig": "IID_鉄の剣", "new": "IID_鉄の剣", "calls": []},
         {"chapter": "X001", "kind": "village", "orig": "IID_キルソード", "new": "IID_銀の剣", "calls": []}]
    OFFS = {"IID_鋼の剣": 0x29E0E, "IID_銀の剣": 0x2A000}

    def test_format(self):
        t = C.engine_list(self.E, self.OFFS, "s71")
        lines = t.splitlines()
        self.assertEqual(lines[0], "fates-rando-chests 1")
        self.assertEqual(lines[1], "seed s71")
        self.assertEqual(lines[-1], "end 2", "an unchanged item is not listed")
        self.assertEqual(lines[2], "c A007 " + "IID_キルソード".encode("cp932").hex() + " "
                         + "IID_鋼の剣".encode("cp932").hex() + " 29e0e")
        t.encode("ascii")
        self.assertTrue(t.endswith("\n"))

    def test_round_trip(self):
        p = C.parse_engine_list(C.engine_list(self.E, self.OFFS, "s71"))
        self.assertEqual(p["seed"], "s71")
        self.assertEqual([(e["chapter"], e["orig"].decode("cp932"), e["new"].decode("cp932"), e["new_at"])
                          for e in p["entries"]],
                         [("A007", "IID_キルソード", "IID_鋼の剣", 0x29E0E), ("X001", "IID_キルソード", "IID_銀の剣", 0x2A000)])

    def test_refusals(self):
        with self.assertRaises(C.ChestsError):
            C.engine_list(self.E, {"IID_鋼の剣": 1}, "s")                       # a new item with no offset
        with self.assertRaises(C.ChestsError):
            C.engine_list([dict(self.E[0], chapter="a7")], self.OFFS, "s")       # not a chapter id
        with self.assertRaises(C.ChestsError):
            C.engine_list([self.E[0], dict(self.E[0])], self.OFFS, "s")         # listed twice
        self.assertEqual(C.engine_list([], {}, "s"), "fates-rando-chests 1\nseed s\nend 0\n")

    def test_the_rust_tests_list_reads_the_same(self):
        p = C.parse_engine_list(RUST_LIST)
        self.assertEqual(len(p["entries"]), 3)
        self.assertEqual(p["entries"][0], {"chapter": "A007", "orig": b"IID_A", "new": b"IID_B", "new_at": 0x100})
        for bad in (RUST_LIST.replace("end 3\n", ""), RUST_LIST.replace("end 3", "end 2"),
                    RUST_LIST.replace("c X001", "c x001"), RUST_LIST.replace("4949445f43 ", "4949445f4 "),
                    RUST_LIST.replace("c X001", "c A007"), RUST_LIST.replace("chests 1", "chests 2"),
                    RUST_LIST + "c A009 41 42 1\n"):
            with self.assertRaises(C.ChestsError, msg=bad):
                C.parse_engine_list(bad)
        self.assertEqual(C.parse_engine_list("fates-rando-chests 1\nseed s\nend 0\n")["entries"], [])


class WiringTests(unittest.TestCase):
    """Round 71: the option, the page row and the make flags. Off (the default) = no key anywhere, so every old answer
    keeps its text, run id and flags."""

    @classmethod
    def setUpClass(cls):
        import ingame as IG
        import tracks as TR
        cls.IG, cls.TR = IG, TR
        cls.rows = IG.schema()["rows"]

    def test_option_off_by_default_and_kept_out(self):
        TR = self.TR
        o = TR.check_topts({})
        self.assertIs(o["chests"], False)
        self.assertFalse(TR.active(o)["chests"])
        self.assertNotIn("chests", TR.stored_topts(o))
        self.assertEqual(TR.topts_text(o), "")
        on = TR.check_topts({"chests": True})
        self.assertEqual(TR.stored_topts(on)["chests"], True)
        self.assertEqual(TR.chests_opts(on), {"chests": "on"})
        self.assertIn("chests", TR.INGAME_ONLY)

    def test_the_page_row(self):
        r = next(r for r in self.rows if r["key"] == "chests")
        self.assertEqual((r["label"], r["kind"], r["default"], r["all"], r["flag"]),
                         ("Chest and village items", "onoff", False, False, "--chests"))
        self.assertTrue(r["omit_default"])
        self.assertEqual(r["section"], "Items and shops")
        self.assertIn("story and key items stay", r["help"])

    def test_off_keeps_the_answer_run_id_and_flags(self):
        IG = self.IG
        for game in E.legs(self, (None, "seal")):
            base = IG.page_restore(self.rows, {"randomizer": True, "seed": "w71"}, game)
            a = IG.page_answers(self.rows, base, game)
            self.assertNotIn("chests", a)
            self.assertNotIn("--chests", IG.make_args(a))
            on = IG.page_answers(self.rows, dict(base, chests=True), game)
            self.assertIs(on["chests"], True)
            args = IG.make_args(on)
            self.assertEqual(args[args.index("--chests") + 1], "on")
            self.assertNotEqual(IG.run_id(on, game), IG.run_id(a, game))
            # an answer saved before round 71 (no key) and one with the row off give the same id
            off = IG.page_answers(self.rows, IG.page_restore(self.rows, dict(a, chests=False), game), game)
            self.assertEqual(IG.run_id(off, game), IG.run_id(a, game))
            ev, turned = IG.page_everything(self.rows, base, game)
            self.assertIs(ev["chests"], False, "Randomize everything keeps it off (round 71)")
            self.assertNotIn("Chest and village items", turned)

    def test_make_takes_the_flag(self):
        import contextlib
        import importlib.util
        import io
        spec = importlib.util.spec_from_file_location("rando_r71", os.path.join(ROOT, "tools", "randomizer",
                                                                                "rando.py"))
        rando = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rando)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                rando.main(["make", "--help"])
            except SystemExit:
                pass
        self.assertIn("--chests", buf.getvalue())


class JudgeTests(unittest.TestCase):
    E = [{"chapter": "A007", "kind": "chest", "orig": "IID_A", "new": "IID_B", "calls": [], "x": 3, "y": 4}]

    def test_planned_item_passes(self):
        self.assertTrue(C.judge_gain(self.E, "A007", None, ["IID_B"], 3, 4)["ok"])
        self.assertTrue(C.judge_gain(self.E, "A007", "IID_A", ["IID_B"])["ok"])

    def test_original_item_fails_with_a_reason(self):
        r = C.judge_gain(self.E, "A007", "IID_A", ["IID_A"])
        self.assertFalse(r["ok"])
        self.assertIn("hook", r["why"])

    def test_unplanned_chest_must_give_its_original(self):
        self.assertTrue(C.judge_gain(self.E, "A008", "IID_C", ["IID_C"])["ok"])
        self.assertFalse(C.judge_gain(self.E, "A008", "IID_C", ["IID_B"])["ok"])
        self.assertTrue(C.judge_gain([], "A007", "IID_A", ["IID_A"])["ok"], "an off run gives the original")

    def test_nothing_or_two_items_fail(self):
        self.assertFalse(C.judge_gain(self.E, "A007", "IID_A", [])["ok"])
        self.assertFalse(C.judge_gain(self.E, "A007", "IID_A", ["IID_B", "IID_B"])["ok"])
        self.assertFalse(C.judge_gain(self.E, "A007", None, ["IID_B"])["ok"])


def _real():
    try:
        import gamedata as GD
        import sources as S
        return None if GD.available() or not os.path.isdir(os.path.join(S.BASE_ROMFS, "Scripts")) else GD
    except Exception:  # noqa: BLE001
        return None


GD = _real()


@unittest.skipIf(GD is None, "no extracted RomFS / table layouts here")
class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sources as S
        cls.rules = S.load_rules("fates")
        cls.f = GD.load_facts(cls.rules)
        cls.rows, cls.info = C.scan([S.BASE_ROMFS])

    def test_every_script_walks_to_its_end(self):
        self.assertGreaterEqual(self.info["files"], 600)
        self.assertEqual(self.info["functions_not_walked"], 0)

    def test_counts_have_chests_and_villages_on_every_route(self):
        c = C.counts(self.rows, self.rules)
        for route in ("Birthright", "Conquest", "Revelation"):
            self.assertGreater(c[route].get("chest", 0), 10, route)
            self.assertGreater(c[route].get("village", 0), 3, route)

    def test_real_seeds_pass_every_guard(self):
        on = {"chests": "on"}
        for s in SEEDS[:12]:
            e, _ = C.plan_chests(self.f, self.rows, s, on)
            self.assertGreater(len(e), 50)
            g = C.check_chests(self.f, self.rows, e, on)
            self.assertTrue(all(v["ok"] for v in g.values()), (s, {k: v for k, v in g.items() if not v["ok"]}))
            self.assertEqual(e, C.plan_chests(self.f, self.rows, s, on)[0])

    def test_kinds_10_and_1_sit_on_chest_and_village_tiles(self):
        # round 71: the [medium] kind numbers of round 70 checked on the maps: every tile event of kind 10 stands on a
        # treasure chest tile, every one of kind 1 on a village tile (each chapter's own terrain file)
        tk = C.terrain_kinds(self.rows)
        self.assertEqual(C.kinds_ok(tk), [], tk)
        self.assertGreater(sum(tk["chest"].values()), 80)
        self.assertGreater(sum(tk["village"].values()), 20)

    def test_no_hook_shared_slot_in_the_game(self):
        import items as I
        iv = I.ItemView(self.f)
        planned = {(e["chapter"], e["orig"]) for e in C.plan_chests(self.f, self.rows, "c1", {"chests": "on"})[0]}
        self.assertEqual(C.hook_shared(self.rows, iv, {"chest", "village", "talk"}, self.rules) & planned, set())

    def test_the_list_points_at_the_new_labels_in_gamedata(self):
        import ingame as IG
        img = IG.memory_image(IG._T().container(IG.GAMEDATA_REL), 0)
        for s in SEEDS[:3]:
            e, _ = C.plan_chests(self.f, self.rows, s, {"chests": "on"})
            p = C.parse_engine_list(C.engine_list(e, C.label_offsets({x["new"] for x in e}), s))
            self.assertGreater(len(p["entries"]), 40)
            for x in p["entries"]:
                at = x["new_at"]
                self.assertEqual(bytes(img[at:at + len(x["new"]) + 1]), x["new"] + b"\0", x)

    def test_make_all_on_adds_only_its_own_files(self):
        import enemies as E
        import items as I
        import skills as S
        import tracks as TR
        kw = {"enemy_tables": E.load_tables(), "skill_rows": S.load_skill_rows(), "achieve": I.load_achieve(),
              "chest_rows": self.rows}
        p0, f0 = TR.make_all(self.f, "w71", {}, {}, **kw)
        p1, f1 = TR.make_all(self.f, "w71", {}, {"chests": True}, **kw)
        self.assertNotIn("chests", p0)
        self.assertNotIn("chests.txt", f0)
        self.assertNotIn("chests", json.loads(f0["plan.json"]).get("topts", {}))
        self.assertTrue(all(v["ok"] for v in p1["guards"].values()))
        self.assertEqual(len(p1["chests"]), len(C.plan_chests(self.f, self.rows, "w71", {"chests": "on"})[0]))
        self.assertIn("chests", p1["tracks"])
        C.parse_engine_list(f1["chests.txt"].decode("ascii"))
        for k in set(f0) | set(f1):
            if k not in ("plan.json", "mod.json", "spoiler.txt", "chests.txt"):
                self.assertEqual(f0.get(k), f1.get(k), f"{k}: the chests track moved another file")
        self.assertEqual(f1, TR.make_all(self.f, "w71", {}, {"chests": True}, **kw)[1], "repeatable")

    def test_story_items_are_never_planned(self):
        e, _ = C.plan_chests(self.f, self.rows, "story", {"chests": "on"})
        for x in e:
            self.assertNotIn(x["orig"], C.STORY_ITEMS)
            self.assertNotIn(x["new"], C.STORY_ITEMS)
            self.assertFalse(x["orig"].startswith("IID_夜刀神"))


if __name__ == "__main__":
    unittest.main()
