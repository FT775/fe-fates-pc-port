#!/usr/bin/env python3
"""Tests for the map tools (tools/maps/).

Standard library only (unittest). Needs your own extracted/romfs/; every test is skipped
when it is missing. Scratch files go to build/maps_test/ only.

    python tools/maps/test_maps.py            all tests
    python tools/maps/test_maps.py -k Move    one test by name

What is covered:
  * every Dispos file (185) and Terrain file (109) goes through the spreadsheet form and
    comes back byte-identical (in memory), and one map does so through real files
    (export -> build);
  * one enemy moved in units.csv -> rebuilt -> parsed again: only that unit's position
    changed (every other unit, group and byte is the same);
  * a unit added at the end of a group: the file grows by one record, the group's count
    is one higher, every other unit is unchanged and the new one decodes to the row;
    adding to a Mob group (encounter maps) or to a versus map is refused with the reason;
  * a position outside the map, a start position off the map, a moved unit on a tile its
    class cannot walk on, a deleted row, an unknown item and a new group are refused with
    a clear message; an item that a mod adds (--tables) is accepted;
  * one terrain tile changed -> only that grid byte changes; a tile number that does not
    exist and a map-size change are refused.
"""
from __future__ import annotations

import csv
import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import maplib as M  # noqa: E402

SCRATCH = os.path.join(M.ROOT, "build", "maps_test")
HAVE = os.path.isdir(os.path.join(M.T.ROMFS, "GameData", "Dispos"))
_WORLD = None


def world() -> M.World:
    global _WORLD
    if _WORLD is None:
        _WORLD = M.World()
    return _WORLD


def fresh(name: str) -> str:
    """A newly exported package in the scratch folder."""
    root = os.path.join(SCRATCH, "pk")
    d = os.path.join(root, name)
    if os.path.isdir(d):
        shutil.rmtree(d)
    M.export(name, root, world(), png=False)
    return root


def read_units(root: str, name: str):
    return M.read_csv(os.path.join(root, name, "units.csv"))


def write_units(root: str, name: str, head, rows) -> None:
    M.write_csv(os.path.join(root, name, "units.csv"), head, rows)


def first_chapter_with(pred):
    """(name, package) of the first map whose units satisfy pred(dispos, terrain)."""
    for n, p in M.packages().items():
        if p["dispos"] and p["terrain"] and not n.endswith(("E", "V")):
            d, t = M.Dispos(p["dispos"]), M.Terrain(p["terrain"])
            hit = pred(d, t)
            if hit is not None:
                return n, p, hit
    raise unittest.SkipTest("no map fits")


def walk_cost(t: M.Terrain, job: str, x: int, y: int) -> int:
    mc = world().move_class(job)
    return world().cost[mc][t.columns_of_tiles()[t.tile(x, y)]]


def enemy_and_free_tile(d: M.Dispos, t: M.Terrain):
    """An enemy (side 1, on all difficulties, own class known, not paired) and a free,
    walkable tile next to it inside the playable area."""
    cols = M.unit_columns()
    rows = M.unit_rows(d)
    taken = {(int(r[cols.index("x")]), int(r[cols.index("y")])) for r in rows}
    x0, y0, x1, y1 = t.play
    for k, r in enumerate(rows):
        u = dict(zip(cols, r))
        if u["side"] != "enemy" or u["normal"] != "1" or int(u["other_flags"], 0) & (M.FLAG_PAIRED | M.FLAG_ANYWHERE):
            continue
        if k and int(dict(zip(cols, rows[k - 1]))["other_flags"], 0) & M.FLAG_PAIRED:
            continue
        p = world().person(u["pid"], d.rel)
        job = u["jid"] or (p or {}).get("job", "")
        if world().move_class(job) is None:
            continue
        x, y = int(u["x"]), int(u["y"])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if x0 <= nx < x1 and y0 <= ny < y1 and (nx, ny) not in taken and walk_cost(t, job, nx, ny) >= 0:
                return k, (nx, ny), job
    return None


@unittest.skipUnless(HAVE, "needs extracted/romfs (python tools/assets/romfs.py)")
class RoundTrip(unittest.TestCase):
    def test_all_files_in_memory(self):
        ds, dn, ts, tn, bad = M.roundtrip_all()
        self.assertEqual((dn, tn), (185, 109), "expected 185 Dispos and 109 Terrain files")
        self.assertEqual(bad, [])
        self.assertEqual((ds, ts), (185, 109))

    def test_one_map_through_files(self):
        name = "A007" if "A007" in M.packages() else next(iter(M.packages()))
        root = fresh(name)
        files, rep = M.build_package(name, root, world())
        self.assertTrue(rep.ok(), rep.errors)
        self.assertTrue(files)
        for rel, data in files.items():
            self.assertEqual(data, M.T.container(rel).raw, rel)


@unittest.skipUnless(HAVE, "needs extracted/romfs (python tools/assets/romfs.py)")
class Units(unittest.TestCase):
    def test_move_one_enemy(self):
        name, p, (k, (nx, ny), _job) = first_chapter_with(enemy_and_free_tile)
        root = fresh(name)
        head, rows = read_units(root, name)
        xi, yi = head.index("x"), head.index("y")
        before = [list(r) for r in rows]
        rows[k][xi], rows[k][yi] = str(nx), str(ny)
        write_units(root, name, head, rows)
        files, rep = M.build_package(name, root, world())
        self.assertTrue(rep.ok(), rep.errors)
        rel = p["dispos"]
        d0 = M.Dispos(rel)
        d1 = M.Dispos(rel, M.T.Container(rel, files[rel]))
        self.assertEqual(d0.groups, d1.groups)
        diff = [(i, h) for i in range(len(d0.urows)) for h, a, b in zip(d0.uhead, d0.urows[i], d1.urows[i]) if a != b]
        self.assertEqual(diff, [(k, "pos.x"), (k, "pos.y")] if before[k][xi] != str(nx) and before[k][yi] != str(ny)
                         else [(k, "pos.x" if before[k][xi] != str(nx) else "pos.y")])
        # and in the decompressed bytes: only those position bytes
        a, b = d0.c.dec, d1.c.dec
        self.assertEqual(len(a), len(b))
        start, _n = M.T.locate(M.reg()["DisposUnit"], d0.c)
        changed = [i for i in range(len(a)) if a[i] != b[i]]
        rec = 0x20 + start + k * M.UNIT_SIZE
        self.assertTrue(changed and all(i in (rec + 0xC, rec + 0xD) for i in changed), changed[:8])
        # the terrain file of this package is untouched
        if p["terrain"]:
            self.assertEqual(files[p["terrain"]], M.T.container(p["terrain"]).raw)

    def _addable(self, d, t):
        """A group whose last unit is an enemy that can be copied to the end."""
        cols = M.unit_columns()
        rows = M.unit_rows(d)
        for g, first, n in d.groups:
            last = dict(zip(cols, rows[first + n - 1]))
            if g.startswith("Enemy") and last["side"] == "enemy" and not int(last["other_flags"], 0) & M.FLAG_PAIRED:
                return g, first + n - 1
        return None

    def test_add_unit_to_group(self):
        name, p, (g, k) = first_chapter_with(self._addable)
        root = fresh(name)
        head, rows = read_units(root, name)
        new = list(rows[k])
        new[head.index("slot")] = "new"
        rows.append(new)
        write_units(root, name, head, rows)
        files, rep = M.build_package(name, root, world())
        self.assertTrue(rep.ok(), rep.errors)
        rel = p["dispos"]
        d0 = M.Dispos(rel)
        d1 = M.Dispos(rel, M.T.Container(rel, files[rel]))
        self.assertEqual(len(d1.urows), len(d0.urows) + 1)
        self.assertEqual(len(d1.c.data), len(d0.c.data) + M.UNIT_SIZE)
        gi = [x[0] for x in d0.groups].index(g)
        for i, ((g0, f0, n0), (g1, f1, n1)) in enumerate(zip(d0.groups, d1.groups)):
            self.assertEqual(g0, g1)
            self.assertEqual(n1, n0 + (1 if i == gi else 0))
            self.assertEqual(f1, f0 + (1 if i > gi else 0))
        # every old unit unchanged (ignoring the file/index columns), the new one = the copy
        strip = lambda r: r[3:]  # noqa: E731
        old = [strip(r) for r in d0.urows]
        new_rows = [strip(r) for r in d1.urows]
        at = d0.groups[gi][1] + d0.groups[gi][2]
        self.assertEqual(new_rows[:at] + new_rows[at + 1:], old)
        self.assertEqual(new_rows[at], old[k])
        # the rebuilt file still passes the table layout checks
        c1 = M.T.Container(rel, files[rel])
        for tname in M.DISPOS_TABLES:
            M.T.locate(M.reg()[tname], c1)

    def test_army_over_limit_refused_across_groups(self):
        """Review 2026-11-11b #1: an army over 50 on any difficulty is an error when edited rows are
        part of it, even if each group alone stays at or under the limit."""
        def two_groups(d, t):
            cols = M.unit_columns()
            rows = M.unit_rows(d)
            found = []
            for g, first, n in d.groups:
                last = dict(zip(cols, rows[first + n - 1]))
                if (g.startswith("Enemy") and last["side"] == "enemy"
                        and not int(last["other_flags"], 0) & M.FLAG_PAIRED):
                    found.append((g, first + n - 1))
            return found[:2] if len(found) >= 2 else None
        try:
            name, _p, picks = first_chapter_with(two_groups)
        except Exception:
            self.skipTest("no chapter with two addable enemy groups")
        root = fresh(name)
        head, rows = read_units(root, name)
        for _g, k in picks:
            for _i in range(M.FORCE_LIMIT // 2 + 1):
                new = list(rows[k])
                new[head.index("slot")] = "new"
                rows.append(new)
        write_units(root, name, head, rows)
        _files, rep = M.build_package(name, root, world())
        self.assertFalse(rep.ok())
        self.assertTrue(any("over all groups" in e for e in rep.errors), rep.errors[:3])

    def test_add_unit_refused_for_mob_group(self):
        pk = M.packages()
        name = next((n for n, p in pk.items() if n.endswith("E") and p["dispos"]
                     and any(g.startswith("Mob") for g, _f, _n in M.Dispos(p["dispos"]).groups)), None)
        if name is None:
            self.skipTest("no encounter map")
        root = fresh(name)
        head, rows = read_units(root, name)
        gi = head.index("group")
        k = max(i for i, r in enumerate(rows) if r[gi].startswith("Mob"))
        new = list(rows[k])
        new[head.index("slot")] = "new"
        rows.append(new)
        write_units(root, name, head, rows)
        files, rep = M.build_package(name, root, world())
        self.assertFalse(rep.ok())
        self.assertEqual(files, {})
        self.assertTrue(any("refused" in e and "Mob" in e for e in rep.errors), rep.errors)

    def test_add_unit_refused_for_versus_map(self):
        pk = M.packages()
        name = next((n for n, p in pk.items() if n.endswith("V") and p["dispos"]), None)
        if name is None:
            self.skipTest("no versus map")
        root = fresh(name)
        head, rows = read_units(root, name)
        new = list(rows[-1])
        new[head.index("slot")] = "new"
        rows.append(new)
        write_units(root, name, head, rows)
        files, rep = M.build_package(name, root, world())
        self.assertFalse(rep.ok())
        self.assertTrue(any("versus" in e for e in rep.errors), rep.errors)

    def _edit_and_build(self, change, lenient=False, extra=None):
        name, p, (k, _free, job) = first_chapter_with(enemy_and_free_tile)
        root = fresh(name)
        head, rows = read_units(root, name)
        change(head, rows, k, p, job)
        write_units(root, name, head, rows)
        w = M.World(extra) if extra else world()
        return M.build_package(name, root, w, lenient=lenient)

    def test_bad_position_rejected(self):
        def ch(head, rows, k, p, job):
            rows[k][head.index("x")] = "200"
        files, rep = self._edit_and_build(ch)
        self.assertEqual(files, {})
        self.assertTrue(any("position (200," in e and "outside the playable area" in e for e in rep.errors),
                        rep.errors)
        # the message names the row: group and slot
        self.assertTrue(any(" slot " in e for e in rep.errors))

    def test_bad_start_position_rejected(self):
        def ch(head, rows, k, p, job):
            rows[k][head.index("start_y")] = "40"
        files, rep = self._edit_and_build(ch)
        self.assertEqual(files, {})
        self.assertTrue(any("start position" in e and "outside" in e for e in rep.errors), rep.errors)

    def test_unwalkable_tile_rejected(self):
        found = {}

        def ch(head, rows, k, p, job):
            t = M.Terrain(p["terrain"])
            x0, y0, x1, y1 = t.play
            for y in range(y0, y1):
                for x in range(x0, x1):
                    if walk_cost(t, job, x, y) < 0:
                        rows[k][head.index("x")], rows[k][head.index("y")] = str(x), str(y)
                        found["xy"] = (x, y)
                        return
        files, rep = self._edit_and_build(ch)
        if "xy" not in found:
            self.skipTest("no unwalkable tile on that map")
        self.assertEqual(files, {})
        self.assertTrue(any("cannot walk on" in e for e in rep.errors), rep.errors)
        files, rep = self._edit_and_build(ch, lenient=True)
        self.assertTrue(rep.ok(), rep.errors)
        self.assertTrue(any("cannot walk on" in w for w in rep.warnings))

    def test_deleted_row_refused(self):
        def ch(head, rows, k, p, job):
            del rows[k]
        with self.assertRaises(M.MapError) as cm:
            self._edit_and_build(ch)
        self.assertIn("never deleted", str(cm.exception))

    def test_new_group_refused(self):
        def ch(head, rows, k, p, job):
            new = list(rows[k])
            new[head.index("group")] = "NoSuchGroup99"
            new[head.index("slot")] = "new"
            rows.append(new)
        with self.assertRaises(M.MapError) as cm:
            self._edit_and_build(ch)
        self.assertIn("new groups are refused", str(cm.exception))

    def test_item_ids_checked_and_mod_items_accepted(self):
        def ch(head, rows, k, p, job):
            rows[k][head.index("item_1")] = "IID_MapsTestSword"
        files, rep = self._edit_and_build(ch)
        self.assertTrue(any("IID_MapsTestSword is not an item" in e for e in rep.errors), rep.errors)
        extra = os.path.join(SCRATCH, "modtables")
        os.makedirs(extra, exist_ok=True)
        with open(os.path.join(extra, "Item.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            csv.writer(fh, lineterminator="\n").writerows([["index", "label"], ["9999", "IID_MapsTestSword"]])
        files, rep = self._edit_and_build(ch, extra=extra)
        self.assertTrue(rep.ok(), rep.errors)


@unittest.skipUnless(HAVE, "needs extracted/romfs (python tools/assets/romfs.py)")
class TerrainEdits(unittest.TestCase):
    def _pkg(self):
        name = next(n for n, p in M.packages().items() if p["terrain"] and p["dispos"])
        return name, M.packages()[name], fresh(name)

    def _grid(self, root, name):
        return M.read_csv(os.path.join(root, name, "terrain.csv"))

    def test_change_one_tile(self):
        name, p, root = self._pkg()
        t = M.Terrain(p["terrain"])
        head, rows = self._grid(root, name)
        # a tile of the playable area that is not under any unit, set to another tile type
        units = {(int(r[M.unit_columns().index("x")]), int(r[M.unit_columns().index("y")]))
                 for r in M.unit_rows(M.Dispos(p["dispos"]))}
        x, y = next((x, y) for y in range(t.play[1], t.play[3]) for x in range(t.play[0], t.play[2])
                    if (x, y) not in units)
        old = int(rows[y][x + 1])
        new = (old + 1) % len(t.trows)
        rows[y][x + 1] = str(new)
        M.write_csv(os.path.join(root, name, "terrain.csv"), head, rows)
        files, rep = M.build_package(name, root, world())
        self.assertTrue(rep.ok(), rep.errors)
        t1 = M.Terrain(p["terrain"], M.T.Container(p["terrain"], files[p["terrain"]]))
        self.assertEqual(t1.tile(x, y), new)
        diff = [i for i in range(1024) if t.tiles[i] != t1.tiles[i]]
        self.assertEqual(diff, [x | y << 5])
        self.assertEqual(t.trows, t1.trows)
        self.assertEqual(len(t.c.dec), len(t1.c.dec))
        self.assertEqual(files[p["dispos"]], M.T.container(p["dispos"]).raw)

    def test_bad_tile_number_refused(self):
        name, p, root = self._pkg()
        head, rows = self._grid(root, name)
        rows[2][3] = "250"
        M.write_csv(os.path.join(root, name, "terrain.csv"), head, rows)
        with self.assertRaises(M.MapError) as cm:
            M.build_package(name, root, world())
        self.assertIn("outside 0..", str(cm.exception))

    def test_map_size_change_refused(self):
        name, p, root = self._pkg()
        head, rows = M.read_csv(os.path.join(root, name, "map.csv"))
        for r in rows:
            if r[0] == "map_width":
                r[1] = str(int(r[1]) - 1)
        M.write_csv(os.path.join(root, name, "map.csv"), head, rows)
        with self.assertRaises(M.MapError) as cm:
            M.build_package(name, root, world())
        self.assertIn("cannot be changed", str(cm.exception))


@unittest.skipUnless(HAVE, "needs extracted/romfs (python tools/assets/romfs.py)")
class Preview(unittest.TestCase):
    def test_png_is_valid(self):
        name = next(n for n, p in M.packages().items() if p["terrain"] and p["dispos"])
        root = os.path.join(SCRATCH, "png")
        d = M.export(name, root, world(), png=True)
        with open(os.path.join(d, "preview.png"), "rb") as fh:
            data = fh.read()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        t = M.Terrain(M.packages()[name]["terrain"])
        w, h = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        self.assertEqual((w, h), (14 + t.width * 16 + 1, 14 + t.height * 16 + 1))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    unittest.main(verbosity=2)
