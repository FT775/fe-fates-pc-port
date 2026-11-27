"""The in-game randomizer's Python side (F-044 addendum, round 50 P1/P2; tools/randomizer/ingame.py):
`rando.py schema` = PLAY RANDOMIZED's lists, and `make --patch-out` = the mods tool's rebuilt files when laid on the
game's files as the game holds them in memory (the reference of zakuro-core's fates_rando). Real-data tests skip
without the extracted tables.

    python -m unittest tests.test_rando_ingame
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
import ingame as IG  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rando_makes as RM  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _edition as E  # noqa: E402  (round 84: Seal legs run only in the Seal edition)

try:
    import gamedata as GD
    if GD.available():
        GD = None
except Exception:  # noqa: BLE001
    GD = None

CLI = os.path.join(ROOT, "tools", "randomizer", "rando.py")
ALL_ON = ["--growth-mode", "redistribute", "--bases-mode", "redistribute", "--personal-skills", "shuffle",
          "--skill-slots", "class", "--starting-items", "on", "--shops", "on", "--rewards", "on",
          "--enemy-weapons", "on", "--enemy-classes", "on", "--boss-classes", "on"]
# round W1: every table-only option the page can lay (WIRE_56 sample r56tab without the PersonChapter rows)
W1_PAGE = ["--children", "on", "--promotions", "on", "--reclass", "random", "--weapon-stats", "on",
           "--weapon-traits", "25", "--enemy-upgrade", "25", "--class-growths", "delta", "--class-bases", "delta",
           "--enemy-growths", "flat", "--enemy-drops", "10", "--class-move", "small", "--assign-evenly", "on"]
# engine round E1 / shops-only make flags (one list each, so the shared makes and the tests use the same flags)
E1_FLAGS = ["--recruit", "route", "--music", "maps+battles", "--enemy-levels", "2", "--boss-stats", "linear"]
SHOPS_FLAGS = ["--classes", "off", "--growths", "off", "--join-stats", "off", "--shops", "on", "--rewards", "on"]
GD_BASE, FILE_BASE = 0x30000000, 0x38000000


def play_rando():
    return IG.play_randomized()


class SchemaTests(unittest.TestCase):
    def test_schema_is_play_randomized_lists(self):
        PR = play_rando()
        rows = {r["key"]: r for r in IG.schema()["rows"]}
        self.assertFalse(rows["randomizer"]["default"])
        self.assertEqual(rows["seed"]["pattern"], PR.SEED_RX.pattern)
        for k in PR.SWITCHES:
            self.assertEqual(rows[k]["label"], PR.SWITCH_LABELS[k])
            self.assertTrue(rows[k]["default"])
        for k, (_label, kind, default) in PR.OPTIONS.items():
            self.assertEqual(rows[k]["default"], default, k)
            # round 62b: "Randomize everything" never turns on Nuzlocke, children or the full swap
            self.assertEqual(rows[k]["all"], default if k in IG.PAGE_FIXED or k in IG.NOT_IN_EVERYTHING
                             else PR.SUGGESTED.get(k, default), k)
            self.assertEqual(bool(rows[k].get("fixed")), k in IG.PAGE_FIXED, k)
            if kind != "onoff" and not isinstance(kind[0], int):
                self.assertEqual(rows[k]["choices"], list(kind))
        for k in ("trees", "keep_royals", "children"):
            self.assertIn(k, rows)
        self.assertFalse(rows["children"].get("fixed"))            # round W1: children are built
        self.assertNotIn("(not built)", rows["children"]["label"])

    def test_w1_rows_order_and_grey_rows(self):
        """Rows in WIRE_56 section 3's order; Nuzlocke live with its flag (engine round E2, round 60), "recruits
        first" grey with no flag; the PersonChapter options grey with their reason; every new row defaults to
        'changes nothing'."""
        import tracks as TR
        rows = IG.schema()["rows"]
        keys = [r["key"] for r in rows]
        # round 62b: the page order is PAGE (sections), hidden rows after; every round-62 key is still a row
        self.assertEqual([k for k in keys if k in IG.PAGE], list(IG.PAGE))
        self.assertEqual(set(IG.ARG_ORDER) - set(keys), set())
        by = {r["key"]: r for r in rows}
        # engine round E2 (round 60): Nuzlocke is live with its flag, off by default and never in "Everything on";
        # "recruits first" stays grey at "all" with no flag (Grok's pick, docs/collab/NUZLOCKE_E2_GROK.md)
        self.assertFalse(by["nuzlocke"].get("fixed"))
        self.assertEqual(by["nuzlocke"]["flag"], "--nuzlocke")
        self.assertFalse(by["nuzlocke"]["default"])
        self.assertFalse(by["nuzlocke"]["all"])
        self.assertIn("Classic is locked", by["nuzlocke"]["help"])
        self.assertIn("keep your first healer and lock opener alive", by["nuzlocke"]["help"])   # round 75b call 6
        self.assertTrue(by["recruits"]["fixed"])
        self.assertNotIn("flag", by["recruits"])
        self.assertEqual((by["recruits"]["default"], by["recruits"]["all"]), ("all", "all"))
        self.assertIn("story ally cannot be told from a recruit", by["recruits"]["label"])
        self.assertEqual(by["music"]["default"], "off")
        self.assertEqual(by["recruit"]["default"], "off")
        # engine round E1 (round 59): the shuffle ("keep the face"), music, enemy levels and tougher bosses are live
        for k in ("recruit", "recruit_class", "recruit_stats", "music", "enemy_levels", "boss_stats",
                  "boss_max_boost", "boss_variance"):
            self.assertFalse(by[k].get("fixed"), k)
            self.assertIn("flag", by[k], k)
        # round 76 (F-062): the full swap look is offered on Fates (default "keep", never in Randomize everything),
        # grey on Seal of Flames with its reason (the scene name plates FAIL)
        self.assertFalse(by["recruit_look"].get("fixed"))
        self.assertEqual(by["recruit_look"]["default"], "keep")
        self.assertEqual(by["recruit_look"]["all"], "keep")
        self.assertEqual(by["recruit_look"]["label"], "How they look")
        with self.subTest(game="seal"):
            E.need_seal(self)
            self.assertIn("Seal of Flames", by["recruit_look"]["grey_for"]["seal"])
        for k in TR.W1_KEYS:
            self.assertEqual(by[k]["default"], TR.DEFAULT_TOPTS[k], k)
        o = TR.check_topts({k: by[k]["default"] for k in TR.W1_KEYS})
        self.assertFalse(any(TR.active(o).values()))

    def test_schema_cli_prints_json(self):
        out = subprocess.run([sys.executable, CLI, "schema"], capture_output=True, text=True, timeout=120, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json.loads(out.stdout), IG.schema())

    def test_make_args_from_an_answer(self):
        args = IG.make_args({"seed": "abc", "shops": True, "growth_mode": "full", "children": True,
                             "enemy_drops": 7, "boss_stats": "linear", "music": "maps", "nuzlocke": True,
                             "recruit": "any", "promotions": "on"})
        self.assertEqual(args[:2], ["--seed", "abc"])
        d = dict(zip(args[2::2], args[3::2]))
        self.assertEqual(d["--shops"], "on")
        self.assertEqual(d["--growth-mode"], "full")
        self.assertEqual(d["--children"], "on")           # round W1: a normal row now
        self.assertEqual(d["--promotions"], "on")
        self.assertEqual(d["--enemy-drops"], "5")         # the page has no step: rounded to 5s
        self.assertEqual(d["--boss-stats"], "linear")     # engine round E1: a normal row now
        self.assertEqual(d["--music"], "maps")
        self.assertEqual(d["--recruit"], "any")
        self.assertEqual(d["--recruit-look"], "keep")     # grey row: always its default
        self.assertEqual(d["--nuzlocke"], "on")           # engine round E2: a live row
        self.assertNotIn("--recruits", d)                 # grey at "all", no flag
        self.assertEqual(d["--classes"], "on")
        out = subprocess.run([sys.executable, CLI, "make", "--help"], capture_output=True, text=True, timeout=120,
                             cwd=ROOT).stdout
        for flag in d:
            self.assertIn(flag, out, flag)                # every flag the page passes is one rando.py takes


class PatchFormatTests(unittest.TestCase):
    def test_parse_rejects_bad_files(self):
        for bad in ("", "fates-rando-patch 9\nend 0\n", "fates-rando-patch 1\nseed x\n",
                    "fates-rando-patch 1\nfile gamedata g\nv 0 00 01\nend 2\n"):
            with self.assertRaises(IG.PatchError):
                IG.parse_patch(bad)

    def test_parse_roundtrip(self):
        p = IG.parse_patch("fates-rando-patch 1\nseed s\nfile dispos GameData/Dispos/A/A001.bin.lz\nv 10 0102 0304\n"
                           "p 20 4a4944 - - - 30\np 24 - 4a4944 g 40 -\nend 3\n")
        f = p["files"][0]
        self.assertEqual(f["v"], [(0x10, b"\x01\x02", b"\x03\x04")])
        self.assertEqual(f["p"], [(0x20, b"JID", None, "-", None, 0x30), (0x24, None, b"JID", "g", 0x40, None)])


def strip_colour(text: str) -> tuple[str, list[str]]:
    """the patch without the recolour section (file asset / file face and their v lines), the end count put back;
    and the stripped lines."""
    out, colour, inside = [], [], False
    for ln in text.split("\n"):
        if ln.startswith("file "):
            inside = ln.split(" ")[1] in ("asset", "face")
        if inside and (ln.startswith("file ") or ln.startswith("v ")):
            colour.append(ln)
            continue
        out.append(ln)
    n = sum(1 for ln in colour if ln.startswith("v "))
    out = [f"end {int(ln.split(' ')[1]) - n}" if ln.startswith("end ") else ln for ln in out]
    return "\n".join(out), colour


@unittest.skipIf(GD is None, "no extracted RomFS / table layouts here")
class RealPatchTests(unittest.TestCase):
    """For each seed: make --patch-out, then lay the patch on memory images of the original files and compare
    with memory images of the mods tool's rebuilt files (labels compared as text; plain bytes byte for byte);
    then revert and get the original images back byte for byte.

    Round 67 (release part A, goal 2): setUpClass starts the makes of the tests that will run, side by side, one
    fresh make per (seed, flags) with the rando cache OFF (tests/_rando_makes.py); each test reads its own make and
    asserts exactly what it asserted before."""

    MAKES = {"test_everything_on": ("r50all", ALL_ON), "test_defaults": ("r50def", []),
             "test_w1_table_options": ("r56tab", W1_PAGE),
             "test_e1_shuffle_music_enemy_levels_bosses": ("r59e1", E1_FLAGS),
             "test_shuffle_recolour_lines": ("r59col", ["--recruit", "route"]),
             "test_shops_rewards_only": ("r50shops", SHOPS_FLAGS)}

    @classmethod
    def setUpClass(cls):
        os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build"))
        cls.made = RM.start(cls, cls.MAKES, cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def make(self, seed, extra):
        m = self.made.get((seed, tuple(extra)))
        if m is None:       # a make no listed test asked for: made here and now, as before round 67
            m = RM.MK.make(seed, ["--seed", seed, *extra], os.path.join(self.tmp.name, seed), timeout=600)
        self.assertEqual(m.rc, 0, m.stdout[-2000:] + m.stderr[-2000:])
        with open(m.patch, encoding="ascii") as fh:
            text = fh.read()
        files = IG.rebuilt_files(m.mods, os.path.join(m.work, "w2"))
        return text, files

    def check_seed(self, seed, extra):
        T = IG._T()
        text, files = self.make(seed, extra)
        again, _s = IG.make_patch(files, seed, {})
        # round 59: with the shuffle on, the make appends the recolour's resident files (file asset / file face,
        # docs/rando/COLOURS.md 5.1) after the rebuilt files; without them the patch is make_patch's exactly
        core, colour = strip_colour(text)
        self.assertEqual(core.split("\n", 3)[3], again.split("\n", 3)[3], "same seed -> same patch")
        if "--recruit" not in extra:
            self.assertEqual(colour, [], "no shuffle: no recolour lines")
        patch = IG.parse_patch(text)
        patch["files"] = [f for f in patch["files"] if f["kind"] not in ("asset", "face")]
        gd = T.container(IG.GAMEDATA_REL)
        gd_img = IG.memory_image(gd, GD_BASE)
        gd_entry = [f for f in patch["files"] if f["kind"] == "gamedata"]
        for f in gd_entry + [f for f in patch["files"] if f["kind"] != "gamedata"]:
            o = T.container(f["rel"])
            n = T.Container(f["rel"], files[f["rel"]])
            base = GD_BASE if f["kind"] == "gamedata" else FILE_BASE
            img = gd_img if f["kind"] == "gamedata" else IG.memory_image(o, base)
            before = bytes(img)
            images = {GD_BASE: gd_img} if f["kind"] == "gamedata" else {GD_BASE: gd_img, FILE_BASE: img}
            self.assertEqual(IG.apply_image(f, img, base, images, GD_BASE), [], f["rel"])
            after = bytes(img)
            self.assertNotEqual(IG.apply_image(f, img, base, images, GD_BASE), [], "second apply: guard refuses")
            self.assertEqual(bytes(img), after, "a refused apply writes nothing")
            want = IG.memory_image(n, 0x7000_0000)
            wimages = {0x7000_0000: want}
            nrel = set(n.b.relocs)
            slots = nrel | set(o.b.relocs)
            plain = [i for i in range(len(n.data)) if (i & ~3) not in slots]
            self.assertEqual(bytes(img[i] for i in plain), bytes(n.data[i] for i in plain), f["rel"])
            for s in nrel:
                v = n.u32(s)
                got = struct.unpack_from("<I", img, s)[0]
                if v < n.se:
                    self.assertEqual(got - base, v, f"{f['rel']} data pointer {s:#x}")
                else:
                    self.assertEqual(IG.read_cstr(images, got), IG.read_cstr(wimages, 0x7000_0000 + v),
                                     f"{f['rel']} label at {s:#x}")
            for s in set(o.b.relocs) - nrel:
                self.assertEqual(struct.unpack_from("<I", img, s)[0], 0, f"{f['rel']} {s:#x} null")
            if f["kind"] != "gamedata":
                self.assertEqual(IG.apply_image(f, img, base, images, GD_BASE, revert=True), [])
                self.assertEqual(bytes(img), before, f"{f['rel']} revert = original")
        for f in gd_entry:
            self.assertEqual(IG.apply_image(f, gd_img, GD_BASE, {GD_BASE: gd_img}, GD_BASE, revert=True), [])
        self.assertEqual(bytes(gd_img), bytes(IG.memory_image(gd, GD_BASE)), "GameData revert = original")
        return patch

    def test_everything_on(self):
        p = self.check_seed("r50all", ALL_ON)
        kinds = {f["kind"] for f in p["files"]}
        # round 61 (track cells): personal skills / skill slots also edit the route-variant HANDOVER rows
        # (GameData/Person/{A,B,C}_HANDOVER), laid as `person` files; check_seed above checked them cell for cell
        self.assertEqual(kinds, {"gamedata", "dispos", "person"})

    def test_defaults(self):
        p = self.check_seed("r50def", [])
        self.assertTrue(any(f["kind"] == "gamedata" for f in p["files"]))

    def test_w1_table_options(self):
        """Round W1: children, promotions, stats (class and enemy growth rows), weapons and misc on: the patch laid
        on memory images = the mods tool's rebuilt GameData and placements, cell for cell; revert = original."""
        p = self.check_seed("r56tab", W1_PAGE)
        self.assertEqual({f["kind"] for f in p["files"]}, {"gamedata", "dispos"})

    def test_e1_shuffle_music_enemy_levels_bosses(self):
        """Engine round E1: the shuffle ("keep the face", its route-variant rows), music (maps and battles),
        enemy levels and tougher bosses give person and map settings files; laid on memory images they equal the
        mods tool's rebuilt files (song names written over the old ones in place); revert = original."""
        p = self.check_seed("r59e1", E1_FLAGS)
        kinds = {f["kind"] for f in p["files"]}
        self.assertEqual(kinds, {"gamedata", "dispos", "person", "mapconfig"})
        for f in p["files"]:
            if f["kind"] in ("person", "mapconfig"):
                self.assertEqual(f["p"], [], f["rel"])    # no label pointers: laid only in the game's read
        self.assertTrue(any(f["rel"].endswith("_HANDOVER.bin.lz") for f in p["files"]))

    def test_shuffle_recolour_lines(self):
        """Round 59 recolour: with the shuffle ("keep the face") the patch carries the swapped spots' battle hair cells
        (file asset) and FaceData colours (file face, with the record count), each v line counted in the end line;
        no picture tint lines (dropped after the round-59 review)."""
        text, _files = self.make("r59col", ["--recruit", "route"])
        _core, colour = strip_colour(text)
        self.assertTrue(any(ln.startswith("file asset asset/ROM") for ln in colour), colour[:3])
        self.assertTrue(any(ln.startswith("file face face/FaceData.bin.lz ") for ln in colour))
        self.assertNotIn("tint ", text)
        p = IG.parse_patch(text)        # the end count matches every v line
        self.assertTrue(p["count"] > 0)

    def test_rename_in_place_refusals(self):
        """A song name longer than the old one, or an old name another cell still shows, is refused (never half
        made)."""
        T = IG._T()
        o = T.container("map/config/A005.bin")
        slot = next(s for s in sorted(o.relset) if (o.string_at(o.u32(s)) or b"").startswith(b"STRM_MAP_"))
        old = o.string_at(o.u32(slot))
        with self.assertRaises(IG.PatchError):
            IG._renames_in_place(o, {o.u32(slot): [(slot, old, old + b"XX")]})
        out = IG._renames_in_place(o, {o.u32(slot): [(slot, old, b"STRM_MAP_B2")]})
        self.assertEqual(out[0][0], "v")
        self.assertGreaterEqual(out[0][1], o.se)

    def test_e2_nuzlocke_rules_beside_the_patch(self):
        """Engine round E2: --patch-out with Nuzlocke on writes the patch (no table cell for Nuzlocke) and
        nuzlocke.json beside it (the core keeps it with the run); Nuzlocke off leaves no rules file there."""
        for on in (True, False):
            out = os.path.join(self.tmp.name, f"nz{int(on)}")
            patch = os.path.join(out, "patch.txt")
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "nuzlocke.json"), "w") as fh:
                fh.write("{}")                            # a stale file from an earlier make in this folder
            r = subprocess.run([sys.executable, CLI, "make", "--seed", "r60nz", "--classes", "off", "--growths",
                                "off", "--join-stats", "off", "--out", os.path.join(out, "mods"), "--patch-out",
                                patch, "--nuzlocke", "on" if on else "off"],
                               capture_output=True, text=True, timeout=600, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
            self.assertTrue(os.path.isfile(patch))
            rules = os.path.join(out, "nuzlocke.json")
            self.assertEqual(os.path.isfile(rules), on)
            if on:
                with open(rules, encoding="utf-8") as fh:
                    d = json.load(fh)
                self.assertTrue(d["nuzlocke"])
                self.assertEqual(d["recruits"], "all")
                self.assertEqual(d["record_force"], 4)
                self.assertTrue(d["game_over_not_recorded"])   # Corrin's rows: that death ends the game

    def test_e2_full_look_and_recruits_first_refused(self):
        """Nuzlocke's 'one recruit per chapter' (not offered, Grok's pick): --patch-out refuses it with the reason, no
        patch file, while the mod folder is written. Round 76 (F-062): the full swap look is offered on the page, so
        it is no longer refused (tests.test_rando_full74 makes it)."""
        for i, extra in [(1, ["--nuzlocke", "on", "--recruits", "first"])]:
            out = os.path.join(self.tmp.name, f"w2ref{i}")
            patch = os.path.join(out, "p.patch")
            r = subprocess.run([sys.executable, CLI, "make", "--seed", "r58ref", "--classes", "off", "--growths", "off",
                                "--join-stats", "off", "--out", os.path.join(out, "mods"), "--patch-out", patch]
                               + extra, capture_output=True, text=True, timeout=600, cwd=ROOT)
            self.assertNotEqual(r.returncode, 0, r.stdout[-2000:])
            self.assertIn("in-memory patch refused: " + extra[-2][2:], r.stdout)
            self.assertIn("Revelation 13" if i == 0 else "cannot tell a story join", r.stdout)
            self.assertFalse(os.path.exists(patch))
            self.assertTrue(os.path.isfile(os.path.join(out, "mods", "Rando-r58ref", "plan.json")))

    def test_shops_rewards_only(self):
        p = self.check_seed("r50shops", SHOPS_FLAGS)
        self.assertEqual({f["kind"] for f in p["files"]}, {"gamedata"})


if __name__ == "__main__":
    unittest.main()
