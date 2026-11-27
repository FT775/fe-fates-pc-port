"""The randomizer with its four tracks put together (round 49 integrate; tools/randomizer/tracks.py, rando.py and
the PLAY RANDOMIZED page's options). Real-data tests skip without the extracted tables; the page tests use no game.

    python -m unittest tests.test_rando_integrate
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
import randolib as R  # noqa: E402
import tracks as TR  # noqa: E402

ALL_ON = {"growth_mode": "full", "adjust_hp": True, "bases_mode": "redistribute", "personal_skills": "shuffle",
          "skill_slots": "class", "starting_items": True, "shops": True, "shop_sides": "mixed", "rewards": True,
          "enemy_weapons": True, "enemy_classes": True, "boss_classes": True}
# round W1 (WIRE_56 sample r56tab): children, promotions, stats, weapons, misc
W1_ON = {"children": True, "promotions": "on", "reclass": "random", "weapon_stats": "on", "weapon_traits": 25,
         "enemy_upgrade": 25, "class_growths": "delta", "class_bases": "delta", "enemy_growths": "flat",
         "boss_stats": "linear", "enemy_drops": 10, "class_move": "small", "assign_evenly": True}
CROSS = ("cross: job_low_fits_final_promotions", "cross: no_stuck_final", "cross: weapons_usable_final",
         "cross: one_writer_per_cell")


class OptionTests(unittest.TestCase):
    def test_defaults_are_all_off(self):
        o = TR.check_topts({})
        self.assertEqual(o, TR.DEFAULT_TOPTS)
        self.assertFalse(any(TR.active(o).values()))
        self.assertEqual(TR.topts_text(o), "")

    def test_bad_options_refused(self):
        for bad in ({"growth_mode": "wild"}, {"growth_max": 200}, {"base_variance": 0}, {"skill_slots": "x"},
                    {"nope": 1}, {"growth_variance": "abc"}):
            with self.assertRaises(R.RandoError, msg=bad):
                TR.check_topts(bad)

    def test_track_option_mapping(self):
        o = TR.check_topts(ALL_ON)
        self.assertEqual(TR.growth_opts(o)["growths"], "full")
        self.assertEqual(TR.skills_opts(o), {"personal": "shuffle", "slots": "class"})
        self.assertEqual(TR.items_opts(o)["inventories"], True)
        self.assertEqual(TR.enemies_opts(o)["gear"], True)
        self.assertFalse(any(TR.active(o)[k] for k in ("children", "promotions", "stats", "weapons", "misc")))
        o = TR.check_topts(dict(ALL_ON, **W1_ON))
        self.assertTrue(all(v for k, v in TR.active(o).items() if k not in ("music", "nuzlocke", "chests")))
        self.assertTrue(all(TR.active(TR.check_topts(dict(ALL_ON, **W1_ON, music="maps", nuzlocke=True,
                                                          chests=True))).values()))
        self.assertEqual(TR.promotions_opts(o), {"promotions": "on", "choices": "2", "reclass": "random", "sides": "any"})
        self.assertEqual(TR.weapons_opts(o), {"stats": True, "traits": 25, "wild_traits": False, "enemy_upgrade": 25,
                                              "upgrade_rank": "same", "difficulty": "normal", "boss_forge": 2})
        self.assertEqual(TR.misc_opts(o), {"enemy_drops": 10, "class_move": "small", "assign_evenly": True})
        self.assertEqual(TR.stats_opts(o)["boss_stats"], "linear")
        self.assertNotIn("class_growth_max", TR.stats_opts(o))       # internal: stays the module's 60
        self.assertEqual(TR.children_opts({}, o)["skill_slots"], "class")
        self.assertEqual(TR.children_opts({}, dict(o, skill_slots="random"))["skill_slots"], "class")

    def test_rules_file_agrees_with_the_modules(self):
        """rules.json (round W1): every module listed; the recruit block = recruit.DEFAULT_RULES; the scope block =
        the enemies track's original scope (F-047: a Seal of Flames rules file carries its own)."""
        import enemies as E
        import recruit as RC
        rules = R.load_rules()
        mods = rules["tracks"]["modules"]
        for m in ("growth", "skills", "items", "enemies", "children", "promotions", "stats", "weapons", "misc",
                  "music", "nuzlocke", "recruit"):
            self.assertEqual(mods[m], f"tools/randomizer/{m}.py")
            self.assertTrue(os.path.isfile(os.path.join(ROOT, mods[m])), m)
        self.assertEqual(rules["recruit"], RC.DEFAULT_RULES)
        self.assertEqual(rules["scope"]["story_file"], E.STORY_FILE.pattern)
        self.assertEqual(rules["scope"]["guarded"], E.GUARDED)
        self.assertEqual(sorted(rules["tracks"]["enemy_guarded_chapters"]), sorted(E.GUARDED))

    def test_w2_options(self):
        o = TR.check_topts({})
        self.assertEqual((o["music"], o["nuzlocke"], o["recruits"]), ("off", False, "all"))
        self.assertFalse(set(TR.stored_topts(o)) & set(TR.W2_KEYS))
        self.assertTrue(TR.active(TR.check_topts({"music": "maps"}))["music"])
        self.assertTrue(TR.active(TR.check_topts({"nuzlocke": True}))["nuzlocke"])
        for bad in ({"music": "loud"}, {"recruits": "some"}):
            with self.assertRaises(R.RandoError, msg=bad):
                TR.check_topts(bad)
        self.assertEqual(TR.check_ropts(None), TR.RECRUIT_DEFAULTS)
        self.assertEqual(TR.check_ropts({"recruit": "Route", "recruit_look": "keep_face"})["recruit_look"], "keep")
        for bad in ({"recruit": "all"}, {"look": "keep"}):
            with self.assertRaises(R.RandoError, msg=bad):
                TR.check_ropts(bad)

    def test_w1_options_refused_and_stored(self):
        for bad in ({"enemy_drops": 7}, {"enemy_drops": 105}, {"promotions": "maybe"}, {"class_growth_variance": 60},
                    {"class_move": "far"}, {"upgrade_rank": "two"}, {"enemy_levels": 6}, {"weapon_traits": -1}):
            with self.assertRaises(R.RandoError, msg=bad):
                TR.check_topts(bad)
        o = TR.check_topts(ALL_ON)
        self.assertFalse(set(TR.stored_topts(o)) & set(TR.W1_KEYS))  # old seeds: mod.json / plan.json unchanged
        o = TR.check_topts({"enemy_drops": 10})
        self.assertEqual(set(TR.stored_topts(o)) & set(TR.W1_KEYS), {"enemy_drops"})
        self.assertEqual(TR.check_topts(TR.stored_topts(o)), o)


class PageTests(unittest.TestCase):
    """The PLAY RANDOMIZED page passes only non-default options, by the flags rando.py's --help names."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        sys.path.insert(0, os.path.join(ROOT, "tools", "play"))     # its own "play" module
        try:
            spec = importlib.util.spec_from_file_location("play_rando", os.path.join(ROOT, "tools", "play", "rando.py"))
            PR = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(PR)
        finally:
            sys.path.remove(os.path.join(ROOT, "tools", "play"))
        cls.PR = PR

    def test_page_options_match_randomizer_defaults(self):
        for k, (_label, kind, default) in self.PR.OPTIONS.items():
            if k in TR.RECRUIT_DEFAULTS:                # round W2: the shuffle's own dict (ropts)
                self.assertEqual(default, TR.RECRUIT_DEFAULTS[k], k)
                self.assertEqual(tuple(kind), TR.RECRUIT_CHOICES[k], k)
                continue
            self.assertIn(k, TR.DEFAULT_TOPTS)
            self.assertEqual(default, TR.DEFAULT_TOPTS[k], k)
            if k in TR.CHOICES:
                self.assertEqual(tuple(kind), TR.CHOICES[k], k)
            elif k in TR.NUMBERS:
                self.assertEqual(tuple(kind), TR.NUMBERS[k], k)
            else:
                self.assertEqual(kind, "onoff", k)
        # round 71: the in-game-only options (Chest and village items) are not PLAY RANDOMIZED options
        self.assertEqual(set(self.PR.OPTIONS), (set(TR.DEFAULT_TOPTS) - set(TR.INGAME_ONLY)) | set(TR.RECRUIT_DEFAULTS))
        self.assertTrue(set(self.PR.SUGGESTED) <= set(TR.DEFAULT_TOPTS) | set(TR.RECRUIT_DEFAULTS))
        self.assertNotIn("nuzlocke", self.PR.SUGGESTED)         # never in "Everything on"
        sug = self.PR.SUGGESTED
        TR.check_topts(dict(TR.DEFAULT_TOPTS, **{k: v for k, v in sug.items() if k in TR.DEFAULT_TOPTS}))
        TR.check_ropts({k: v for k, v in sug.items() if k in TR.RECRUIT_DEFAULTS})
        self.assertEqual(sug["recruit"], "route")
        self.assertEqual(sug["music"], "maps+battles")
        import recruit as RC
        self.assertEqual(TR.RECRUIT_DEFAULTS, RC.DEFAULT_OPTS)
        self.assertEqual(TR.RECRUIT_CHOICES, RC.CHOICES)

    def test_w2_page_nuzlocke_profile(self):
        """Round 61: PLAY RANDOMIZED accepts Nuzlocke (the profile keeps a run of no cells and the rules, which the
        core lays when the New Game page answers off); 'first recruit per chapter' stays refused."""
        PR = self.PR
        _a, opts, _ = PR.parse_args(["new", "--nuzlocke", "on"])
        self.assertEqual(PR.changed_options(opts["options"]), {"nuzlocke": True})
        with tempfile.TemporaryDirectory() as t:
            run = PR.write_profile_nuzlocke(PR.Path(t) / "data")
            self.assertEqual(run, PR.Path(t) / "data" / "rando" / PR.TITLE_HEX / "runs" / "profile-nuzlocke")
            self.assertEqual((run / "patch.txt").read_text(encoding="ascii"), PR.EMPTY_PATCH)
            rules = json.loads((run / "nuzlocke.json").read_text(encoding="utf-8"))
            self.assertIs(rules["nuzlocke"], True)
            self.assertEqual(rules["recruits"], "all")
            self.assertTrue(rules["names"])

    def test_w2_page_nuzlocke_not_yet(self):
        """PLAY RANDOMIZED refuses what the page cannot start (round 61: Nuzlocke itself is accepted)."""
        PR = self.PR
        for bad in (["new", "--recruits", "first"], ["new", "--recruit", "everyone"]):
            with self.assertRaises(PR.Stop, msg=bad):
                PR.parse_args(bad)
        _a, opts, _ = PR.parse_args(["new", "--recruit", "route", "--music", "maps", "--nuzlocke", "off"])
        self.assertEqual(PR.changed_options(opts["options"]), {"recruit": "route", "music": "maps"})
        cli = os.path.join(ROOT, "tools", "randomizer", "rando.py")
        help_text = subprocess.run([sys.executable, cli, "make", "--help"], capture_output=True, text=True,
                                   cwd=ROOT, timeout=120).stdout
        cmd = PR.randomizer_command(PR.Path(cli), help_text, "S1", {k: True for k in PR.SWITCHES},
                                    PR.Path(tempfile.gettempdir()) / "x" / "data", opts["options"])
        self.assertEqual(cmd[cmd.index("--recruit") + 1], "route")
        self.assertEqual(cmd[cmd.index("--music") + 1], "maps")
        self.assertNotIn("--nuzlocke", cmd)

    def test_command_from_real_help(self):
        PR = self.PR
        cli = os.path.join(ROOT, "tools", "randomizer", "rando.py")
        help_text = subprocess.run([sys.executable, cli, "make", "--help"], capture_output=True, text=True,
                                   cwd=ROOT, timeout=120).stdout
        help_text += subprocess.run([sys.executable, cli, "--help"], capture_output=True, text=True, cwd=ROOT,
                                    timeout=120).stdout
        sw = {k: True for k in PR.SWITCHES}
        data = PR.Path(tempfile.gettempdir()) / "x" / "data"
        base = PR.randomizer_command(PR.Path(cli), help_text, "S1", sw, data)
        self.assertEqual(base, PR.randomizer_command(PR.Path(cli), help_text, "S1", sw, data, PR.default_options()))
        opts = dict(PR.default_options(), growth_mode="delta", enemy_classes=True, growth_max=90)
        cmd = PR.randomizer_command(PR.Path(cli), help_text, "S1", sw, data, opts)
        for a, b in (("--growth-mode", "delta"), ("--enemy-classes", "on"), ("--growth-max", "90")):
            self.assertEqual(cmd[cmd.index(a) + 1], b)
        self.assertNotIn("--shops", cmd)

    def test_old_randomizer_without_flag_stops(self):
        PR = self.PR
        with self.assertRaises(PR.Stop):
            PR.randomizer_command(PR.Path("r.py"), "usage: {make} --seed S --out DIR --zakuro-dir D", "S1",
                                  {k: True for k in PR.SWITCHES}, PR.Path("d"), {"shops": True})

    def test_parse_args_and_bad_values(self):
        PR = self.PR
        action, opts, _ = PR.parse_args(["new", "--seed", "abc", "--growth-mode", "full", "--shops", "on",
                                         "--base-variance", "7"])
        self.assertEqual(action, "new")
        self.assertEqual(PR.changed_options(opts["options"]), {"growth_mode": "full", "shops": True, "base_variance": 7})
        action, opts, _ = PR.parse_args(["new", "--seed", "abc", "--children", "on", "--promotions", "on",
                                         "--enemy-drops", "15"])
        self.assertEqual(PR.changed_options(opts["options"]), {"children": True, "promotions": "on", "enemy_drops": 15})
        for bad in (["new", "--growth-mode", "wild"], ["new", "--base-variance", "11"], ["new", "--shops", "maybe"],
                    ["new", "--enemy-drops", "7"], ["new", "--promotions", "maybe"]):
            with self.assertRaises(PR.Stop):
                PR.parse_args(bad)


def _real():
    try:
        import gamedata as GD
        return None if GD.available() else GD
    except Exception:  # noqa: BLE001
        return None


GD = _real()


@unittest.skipIf(GD is None, "no extracted RomFS / table layouts here")
class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import enemies as E
        import items as I
        import skills as S
        cls.f = GD.load_facts()
        cls.kw = {"enemy_tables": E.load_tables(), "skill_rows": S.load_skill_rows(), "achieve": I.load_achieve()}

    def make(self, seed, sw=None, topts=None):
        return TR.make_all(self.f, seed, sw or {}, topts or {}, **self.kw)

    def test_default_byte_identical_to_slice1(self):
        for seed in ("same", "r47robot", "x1"):
            for sw in ({}, {"trees": "any", "keep_royals": False}):
                _plan, files = self.make(seed, sw)
                # round 62: slice 1 plus the growth floor (growths are randomized by default)
                p0 = R.make_plan(self.f, seed, sw)
                self.assertEqual(files, TR._with_floor(self.f, sw, TR.check_topts({}), p0, R.render(self.f, p0))[1],
                                 (seed, sw))

    def test_all_on_guards_and_repeatable(self):
        for seed in ("i49a", "i49b", "i49c"):
            plan, files = self.make(seed, None, ALL_ON)
            bad = {k: v["detail"][:3] for k, v in plan["guards"].items() if not v["ok"]}
            self.assertFalse(bad, (seed, bad))
            self.assertEqual(set(plan["tracks"]), {"growth", "skills", "items", "enemies"})
            for sec in ("Growths and bases", "Skills (skills track)", "Items, shops", "Enemies (enemies track)"):
                self.assertIn(sec, files["spoiler.txt"].decode("utf-8"))
            _p2, again = self.make(seed, None, ALL_ON)
            self.assertEqual(files, again, seed)

    def test_tracks_do_not_disturb_each_other(self):
        # the items track's stream follows its own four options only (so they are the same here)
        _p, alone = self.make("ind1", None, {"starting_items": True, "shops": True, "rewards": True})
        _p, mixed = self.make("ind1", None, dict(ALL_ON, shop_sides="own"))
        for t in ("tables/Item.csv", "tables/AchieveBonusBattle.csv", "tables/AchieveBonusVisit.csv"):
            self.assertEqual(alone[t], mixed[t], t)
        pa, _ = self.make("ind1", None, {"enemy_weapons": True})
        pb, _ = self.make("ind1", {"classes": False}, {"enemy_weapons": True, "personal_skills": "random"})
        self.assertEqual(pa["tracks"]["enemies"], pb["tracks"]["enemies"])

    def test_bases_mode_relaxes_only_the_total_line(self):
        plan, _ = self.make("bm1", None, {"bases_mode": "delta", "base_variance": 10})
        self.assertTrue(plan["guards"]["stats_within_caps"]["ok"], plan["guards"]["stats_within_caps"]["detail"][:3])
        self.assertTrue(plan["guards"]["growth: bounds"]["ok"])

    def test_w1_defaults_change_nothing(self):
        """Every W1 option given at its default: the same files as without them (and slice 1's with no track on)."""
        defaults = {k: TR.DEFAULT_TOPTS[k] for k in TR.W1_KEYS}
        for seed in ("r50def", "r50all"):
            for topts in ({}, ALL_ON):
                _p, a = self.make(seed, None, topts)
                _p, b = self.make(seed, None, dict(topts, **defaults))
                self.assertEqual(a, b, (seed, bool(topts)))
        plan, files = self.make("r50all", None, ALL_ON)
        self.assertFalse([k for k in plan["guards"] if k.startswith("cross: ")])
        self.assertFalse(set(plan["topts"]) & set(TR.W1_KEYS))

    def test_w1_everything_on_guards_and_repeatable(self):
        for seed in ("r56all", "w1b"):
            plan, files = self.make(seed, None, dict(ALL_ON, **W1_ON))
            bad = {k: v["detail"][:3] for k, v in plan["guards"].items() if not v["ok"]}
            self.assertFalse(bad, (seed, bad))
            for k in CROSS:
                self.assertIn(k, plan["guards"])
            self.assertEqual(set(plan["tracks"]), {"growth", "skills", "items", "enemies", "children", "promotions",
                                                   "stats", "weapons", "misc"})
            sp = files["spoiler.txt"].decode("utf-8")
            for sec in ("Promotions and Heart Seal classes", "Children (children track)", "Class and enemy stats",
                        "Weapons (weapons track)", "Enemy drops and class movement", "Classes spread evenly"):
                self.assertIn(sec, sp)
            for t in ("tables/Job.csv", "tables/PersonChapter.csv", "tables/Item.csv", "tables/DisposUnit.csv"):
                self.assertIn(t, files)
            _p2, again = self.make(seed, None, dict(ALL_ON, **W1_ON))
            self.assertEqual(files, again, seed)

    def test_w1_modules_do_not_disturb_each_other(self):
        base_p, base = self.make("ind56", None, ALL_ON)
        # stats on: Person, DisposUnit and Item stay; the enemies track's plan stays
        p, f = self.make("ind56", None, dict(ALL_ON, enemy_growths="flat"))
        for t in ("tables/Person.csv", "tables/DisposUnit.csv", "tables/Item.csv"):
            self.assertEqual(base[t], f[t], t)
        # round 62: class growths move the growth floor's Person cells (the totals are kept 20..100) and tougher
        # bosses forge the bosses' weapons (DisposUnit); Item stays and the enemies track's plan stays
        p, f = self.make("ind56", None, dict(ALL_ON, class_growths="delta", enemy_growths="flat", boss_stats="ease"))
        self.assertEqual(base["tables/Item.csv"], f["tables/Item.csv"])
        self.assertEqual(base_p["tracks"]["enemies"], p["tracks"]["enemies"])
        # weapon stats and traits (no upgrades): Person and DisposUnit stay
        p, f = self.make("ind56", None, dict(ALL_ON, weapon_stats="on", weapon_traits=50))
        for t in ("tables/Person.csv", "tables/DisposUnit.csv"):
            self.assertEqual(base[t], f[t], t)
        # enemy drops: Person and Item stay; only flag columns are added to the placements
        p, f = self.make("ind56", None, dict(ALL_ON, enemy_drops=30))
        for t in ("tables/Person.csv", "tables/Item.csv"):
            self.assertEqual(base[t], f[t], t)
        # promotions on/off does not move the children's classes
        pb, _ = self.make("ind56", None, {"children": True, "promotions": "on"})
        import children as C
        ka, _ = C.plan_children(self.f, "ind56", dict(TR.children_opts({}, TR.check_topts({"children": True}))))
        kb, _ = C.plan_children(self.f, "ind56", dict(TR.children_opts({}, TR.check_topts({"children": True})),
                                                     job_promotions={}))
        self.assertEqual([e for e in ka if e.get("cell") == "job"], [e for e in kb if e.get("cell") == "job"])
        self.assertTrue(all(v["ok"] for v in pb["guards"].values()))
        # the old "children" switch name is the children option
        p1, f1 = self.make("ind56", {"children": True}, {})
        p2, f2 = self.make("ind56", None, {"children": True})
        self.assertEqual(f1, f2)

    def test_w1_job_low_gap_closed(self):
        """Promotions on, children off (the w55 seeds failed 14-16 of 22 child rows before W1): every army row's
        job_low, the children's included, is one of the final promotions of its class."""
        import children as C
        kids = {p["label"] for p in C.children(self.f)}
        for seed in ("w55a", "w55b", "w55c"):
            plan, files = self.make(seed, None, {"promotions": "on", "reclass": "random"})
            g = plan["guards"]["cross: job_low_fits_final_promotions"]
            self.assertTrue(g["ok"], (seed, g["detail"][:3]))
            self.assertTrue(all(v["ok"] for v in plan["guards"].values()), seed)
            person = files["tables/Person.csv"].decode("utf-8")
            self.assertTrue(any(k in person for k in kids), "child rows written (job_low)")

    def test_w1_mods_tool_accepts_and_check_remakes(self):
        import mods as M
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build")) as t:
            _plan, files = self.make("r56tab", None, W1_ON)
            d = R.write_mod(files, os.path.join(t, R.mod_name("r56tab")))
            changes, errors, _w = M.diff_mod(M.Mod(d))
            self.assertEqual(errors, [])
            self.assertTrue({"Person", "DisposUnit", "Item", "Job", "PersonChapter"} <= {k[0] for k in changes},
                            {k[0] for k in changes})
            r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "randomizer", "rando.py"), "check", d],
                               capture_output=True, text=True, cwd=ROOT, timeout=900)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:])
            self.assertIn("byte-identical", r.stdout)

    # ---------------------------------------------------------------- round W2 (shuffle, music, Nuzlocke file)
    def test_w2_defaults_change_nothing(self):
        """W2 options at their default and the shuffle off: the same files as without them (r50def = slice 1)."""
        defaults = {k: TR.DEFAULT_TOPTS[k] for k in TR.W2_KEYS}
        for seed, topts in (("r50def", {}), ("r50all", ALL_ON), ("r56tab", W1_ON)):
            _p, a = self.make(seed, None, topts)
            _p, b = TR.make_all(self.f, seed, {}, dict(topts, **defaults), ropts=dict(TR.RECRUIT_DEFAULTS), **self.kw)
            self.assertEqual(a, b, seed)
        _p, a = self.make("r50def")
        p0 = R.make_plan(self.f, "r50def")
        self.assertEqual(a, TR._with_floor(self.f, {}, TR.check_topts({}), p0, R.render(self.f, p0))[1])   # + floor
        code = ("import sys; sys.path.insert(0, 'tools/randomizer'); import gamedata as GD, tracks as TR; "
                "TR.make_all(GD.load_facts(names=False), 'r50def', {}, {}, ropts={'recruit': 'off'}); "
                "print('recruit' in sys.modules, 'music' in sys.modules, 'nuzlocke' in sys.modules)")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, timeout=600)
        self.assertEqual(r.stdout.split(), ["False", "False", "False"], r.stdout + r.stderr[-2000:])

    def test_w2_everything_on_guards_files_and_check(self):
        """Everything on, the shuffle (route, keep), music (maps+battles) and the Nuzlocke rules file included: every
        guard (the shuffle's and music's own, the cross guards), the files merged (PersonChapter: stats + music +
        the route-variant rows), the mods tool accepts the folder and `check` remakes it byte for byte."""
        import json
        import mods as M
        topts = dict(ALL_ON, **W1_ON, music="maps+battles", nuzlocke=True)
        plan, files = TR.make_all(self.f, "w2all", {}, topts, ropts={"recruit": "route"}, **self.kw)
        bad = {k: v["detail"][:3] for k, v in plan["guards"].items() if not v["ok"]}
        self.assertFalse(bad, bad)
        for k in CROSS + ("recruit: R1_permutation", "recruit: R6_flier_before_ninja_doors", "recruit: weapons_usable",
                          "music: same stream layout as the track replaced"):
            self.assertIn(k, plan["guards"])
        self.assertEqual(list(plan["tracks"])[0], "recruit")
        self.assertTrue({"music", "nuzlocke"} <= set(plan["tracks"]))
        self.assertEqual(plan["ropts"]["recruit"], "route")
        sp = files["spoiler.txt"].decode("utf-8")
        for sec in ("Character shuffle (who joins where)", "Music (music track)", "Nuzlocke (rules file"):
            self.assertIn(sec, sp)
        nz = json.loads(files["nuzlocke.json"].decode("utf-8"))
        self.assertTrue(nz["nuzlocke"])
        pc = files["tables/PersonChapter.csv"].decode("utf-8")
        self.assertIn("_HANDOVER", pc)                           # the shuffle's route-variant rows
        self.assertIn("combat_music", pc.splitlines()[0])        # music's cells
        self.assertIn("base.hp", pc.splitlines()[0])             # stats' cells (boss bases)
        self.assertTrue(any(k.startswith("romfs/map/config/") for k in files))
        meta = json.loads(files["mod.json"].decode("utf-8"))
        self.assertEqual(meta["randomizer"]["ropts"]["recruit"], "route")
        with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build")) as t:
            d = R.write_mod(files, os.path.join(t, R.mod_name("w2all")))
            changes, errors, _w = M.diff_mod(M.Mod(d))
            self.assertEqual(errors, [])
            self.assertTrue({"Person", "DisposUnit", "Job", "PersonChapter", "Item"} <= {k[0] for k in changes})
            r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "randomizer", "rando.py"), "check", d],
                               capture_output=True, text=True, cwd=ROOT, timeout=900)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:])
            self.assertIn("byte-identical", r.stdout)

    def test_w2_shuffle_cells_reach_the_files(self):
        """With only the shuffle on (Classes etc. off), every cell the shuffle lays is in the mod folder: main Person
        cells in Person.csv, placements in DisposUnit.csv, route-variant rows in PersonChapter.csv."""
        import csv
        import io
        import recruit as RC
        off = {"classes": False, "growths": False, "join_stats": False}
        for ro in ({"recruit": "route"}, {"recruit": "any", "recruit_class": "slot", "recruit_stats": "slot"}):
            plan, files = TR.make_all(self.f, "w2cells", off, {}, ropts=ro, **self.kw)
            self.assertTrue(all(v["ok"] for v in plan["guards"].values()), ro)
            rt = RC.load_tables(facts=self.f)
            edits, _l = RC.plan_recruit(rt, "w2cells", ro)

            def table(name):
                rows = list(csv.reader(io.StringIO(files[f"tables/{name}.csv"].decode("utf-8").lstrip(chr(0xFEFF)))))
                return [dict(zip(rows[0], r)) for r in rows[1:]]
            person = {r["label"]: r for r in table("Person")}
            dispos = {(r["file"], int(r["index"])): r for r in table("DisposUnit")}
            pc = {(r["file"], int(r["index"])): r for r in table("PersonChapter")}
            # round 75b: the seed guarantees are always on (no page switch), so a person the repair pass gave a role
            # class keeps the repair's class, not the shuffle's: skip that person's class cells and their knock-ons
            # (class, weapon exp, carried items) and check the final class is the repair's
            repaired = {r["pid"]: r["to"] for r in plan["guarantees"]["repairs"]}
            for pid, to in repaired.items():
                # (a row the make leaves as the game has it is not in Person.csv)
                self.assertEqual(person.get(pid, self.f.by_pid[pid])["job"], to, (ro, pid))
            knock = ("job", "job_low", "jid")
            n = 0
            for e in edits:
                cell = e.get("cell") or e.get("column") or ""
                if (e.get("label") in repaired or e.get("spot") in repaired) and (
                        cell in knock or cell.startswith(("weapon_exp", "item_"))):
                    continue
                if e.get("laid_by") == "core" and e["table"] == "Person":
                    self.assertEqual(person[e["label"]][e["cell"]], e["new"], e)
                elif e["table"] == "DisposUnit":
                    self.assertEqual(dispos[(e["file"], e["index"])][e["column"]], e["new"], e)
                elif e.get("laid_by") == "person_hook":
                    self.assertEqual(pc[(e["file"], e["index"])][e["cell"]], e["new"], e)
                else:
                    continue
                n += 1
            self.assertGreater(n, 500, ro)

    def test_w2_modules_do_not_disturb_each_other(self):
        base_p, base = self.make("ind58", None, ALL_ON)
        # music on: every table but PersonChapter stays, the enemies track's plan stays
        p, f = self.make("ind58", None, dict(ALL_ON, music="maps+battles"))
        for t in ("tables/Person.csv", "tables/DisposUnit.csv", "tables/Item.csv"):
            self.assertEqual(base[t], f[t], t)
        self.assertEqual(base_p["tracks"]["enemies"], p["tracks"]["enemies"])
        # Nuzlocke on: no table changes, only the rules file is added
        p, f = self.make("ind58", None, dict(ALL_ON, nuzlocke=True, recruits="first"))
        self.assertEqual({k for k in f if k.startswith("tables/")}, {k for k in base if k.startswith("tables/")})
        for t in (k for k in base if k.startswith("tables/")):
            self.assertEqual(base[t], f[t], t)
        self.assertIn("nuzlocke.json", f)
        self.assertNotIn("nuzlocke.json", base)
        # the shuffle on: the enemies track's draws and music's cells do not move
        p1, f1 = self.make("ind58", None, {"enemy_classes": True, "music": "maps+battles"})
        p2, f2 = TR.make_all(self.f, "ind58", {}, {"enemy_classes": True, "music": "maps+battles"},
                             ropts={"recruit": "route"}, **self.kw)
        self.assertEqual(p1["tracks"]["enemies"], p2["tracks"]["enemies"])
        self.assertEqual(p1["tracks"]["music"], p2["tracks"]["music"])
        self.assertEqual({k: v for k, v in f1.items() if k.startswith("romfs/")},
                         {k: v for k, v in f2.items() if k.startswith("romfs/")})

    def test_w2_route_variant_joins_get_the_new_class(self):
        """Owner OK (F-046): with Classes on, every route-variant join of a person whose class changed gets the new
        class in its placement's jid, with weapons it can use (slice 1's weapons_usable covers them); Classes off:
        no jid written."""
        self.assertTrue(self.f.variant_of, "the HANDOVER rows are loaded with the facts")
        for seed in ("r50def", "r56tab"):
            plan, files = self.make(seed, None, W1_ON if seed == "r56tab" else {})
            self.assertTrue(plan["guards"]["weapons_usable"]["ok"], plan["guards"]["weapons_usable"]["detail"][:3])
            pe = {e["pid"]: e for e in plan["persons"]}
            n = 0
            for d in self.f.dispos:
                main = self.f.variant_of.get(d.get("pid", ""))
                if not main or main not in pe or pe[main]["job"] == pe[main]["old_job"]:
                    continue
                key = f"{d['file']}#{R.ival(d['index'])}"
                self.assertEqual(plan["dispos"][key]["jid"], pe[main]["job"], key)
                n += 1
            self.assertGreater(n, 10, seed)
            self.assertIn("jid", files["tables/DisposUnit.csv"].decode("utf-8").splitlines()[0])
            self.assertIn("route-variant join", files["spoiler.txt"].decode("utf-8"))
        plan, files = self.make("r50shops", {"classes": False}, {})
        self.assertFalse([k for k, v in plan["dispos"].items() if "jid" in v])

    def test_mods_tool_accepts_and_check_remakes(self):
        import mods as M
        with tempfile.TemporaryDirectory() as t:
            _plan, files = self.make("modsall", None, ALL_ON)
            d = R.write_mod(files, os.path.join(t, R.mod_name("modsall")))
            changes, errors, _w = M.diff_mod(M.Mod(d))
            self.assertEqual(errors, [])
            # round 61: PersonChapter too (the skills track's cells in the route-variant HANDOVER rows)
            self.assertEqual({k[0] for k in changes}, {"Person", "PersonChapter", "DisposUnit", "Item",
                                                       "AchieveBonusBattle", "AchieveBonusVisit"})
            r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "randomizer", "rando.py"), "check", d],
                               capture_output=True, text=True, cwd=ROOT, timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:])
            self.assertIn("byte-identical", r.stdout)


if __name__ == "__main__":
    unittest.main()
