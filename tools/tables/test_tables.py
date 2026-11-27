#!/usr/bin/env python3
"""Tests for the Fates data-table tools (tools/tables/).

Standard library only (unittest). Needs the user's own extracted/romfs/ and
extracted/text.bin; every test is skipped when they are missing. Nothing is written
outside build/tables/.

    python tools/tables/test_tables.py            all tests
    python tools/tables/test_tables.py -k Stat    one test by name

What is covered:
  * one Person stat cell edited -> rebuilt GameData.bin.lz -> decompressed: exactly that
    one byte differs from the original (and it holds the new value); the same for a
    per-chapter Person file and for a Dispos unit position;
  * every table file rebuilds byte-identical from an unedited dump (all 412 files);
  * every layout passes check.py, and check.py rejects each mutated layout;
  * the dump -> CSV -> read-back path keeps every cell (CSV quoting, UTF-8 BOM);
  * the '#N' record references (DisposFaction.first_unit) and str:self IDs survive;
  * the code-evidence decoder passes its self-test and still finds the accessors the
    layouts cite (Unit::GetGrow reads Person+0x40[i], Job::IsFlyer reads Job+0x1A), also
    through the table getters (ExpTable::GetBattle, WeaponLevel::Get, ItemRefine::Get);
  * the GameData tables without a stored count (WeaponBonus, TerrainCost, ...): one-byte
    edits land where the layout says, a row added to them is refused with the reason,
    and their fixed:N counts are proven (N-1 and N+1 are rejected);
  * new rows (config/tables/appends.csv): an Item and a Job appended to GameData.bin ->
    rebuilt -> decompressed: the count is one higher, the new record resolves by its ID
    label and decodes to exactly the row, every other table decodes unchanged and passes
    check.py; Person (fixed 256-person bit set), unlisted tables, a planted fixed-array
    policy, bad numbering, a reused label and a deleted row are refused; the fixed-array
    scan (evidence.py --bitsets) finds GameProfile::UpdateReliance's 256-entry set.
"""
from __future__ import annotations

import csv
import io
import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tablelib as T  # noqa: E402
import build as B  # noqa: E402
import check as K  # noqa: E402

HAVE_ROMFS = os.path.isfile(os.path.join(T.ROMFS, "GameData", "GameData.bin.lz"))
HAVE_TEXT = os.path.isfile(os.path.join(T.ROOT, "extracted", "text.bin"))
GAMEDATA = "GameData/GameData.bin.lz"


def lz_dec(c: T.Container) -> bytes:
    return c.dec


def diff_bytes(a: bytes, b: bytes) -> list[int]:
    if len(a) != len(b):
        raise AssertionError(f"sizes differ: {len(a)} vs {len(b)}")
    return [i for i in range(len(a)) if a[i] != b[i]]


@unittest.skipUnless(HAVE_ROMFS, "needs extracted/romfs (run tools/extract_rom.py)")
class TableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = T.registry()

    def one_byte_edit(self, table: str, rel: str, k: int, column: str, field_off: int, delta: int = 1):
        head, rows = B.dump_rows(self.reg, table)
        col = head.index(column)
        t = self.reg[table]
        idx = [j for j, r in enumerate(rows) if (r[0] == rel if t.multi else True)]
        old = int(rows[idx[k]][col])
        new = old + delta
        c0, nc, _head, _want = B.edit_rebuild(self.reg, table, rel, {column: str(new)}, k)
        d0, d1 = lz_dec(c0), lz_dec(nc)
        changed = diff_bytes(d0, d1)
        start, _count = T.locate(t, c0)
        want_pos = 0x20 + start + k * t.size + field_off  # 0x20 = IS .bin header
        self.assertEqual(changed, [want_pos], f"{table}[{k}].{column}: changed bytes {changed[:8]}")
        self.assertEqual(struct.unpack_from("<b", d1, want_pos)[0], new)
        # the stored (LZ13) file is a valid, different file that decompresses to d1
        self.assertNotEqual(nc.raw, c0.raw)
        self.assertEqual(T.lz.decompress(nc.raw), d1)
        return old, new

    def test_person_stat_edit_changes_exactly_one_byte(self):
        # Person record 1 (the player character), base strength: s8 at +0x39
        self.one_byte_edit("Person", GAMEDATA, 1, "base.str", 0x39)

    def test_person_growth_edit_changes_exactly_one_byte(self):
        self.one_byte_edit("Person", GAMEDATA, 5, "growth.spd", 0x44, delta=5)

    def test_chapter_person_edit_changes_exactly_one_byte(self):
        rel = self.reg["PersonChapter"].files()[0]
        self.one_byte_edit("PersonChapter", rel, 0, "base.hp", 0x38, delta=3)

    def test_dispos_position_edit_changes_exactly_one_byte(self):
        self.one_byte_edit("DisposUnit", "GameData/Dispos/A001.bin.lz", 0, "pos.y", 0x0D)

    def test_new_gamedata_tables_one_byte_edits(self):
        # weapon triangle matrix (sword vs lance), a boon growth, battle exp, a move cost
        self.one_byte_edit("WeaponInteract", GAMEDATA, 0, "attacker_sword.lance", 0xC + 1)
        self.one_byte_edit("Personality", GAMEDATA, 2, "boon_growth.str", 0x15, delta=5)
        self.one_byte_edit("ExpBattle", GAMEDATA, 1, "damage.10", 10)
        self.one_byte_edit("TerrainCost", GAMEDATA, 3, "cost.4", 4)
        self.one_byte_edit("WeaponBonus", GAMEDATA, 0, "rank_s.hit", 1)

    def test_fixed_tables_refuse_appends(self):
        # tables without a stored count (fixed:N / one) refuse a new row with a reason
        for name in ("WeaponBonus", "TerrainCost", "WeaponInteract"):
            head, rows = B.dump_rows(self.reg, name)
            extra = list(rows[-1])
            extra[head.index("index")] = str(len(rows))
            with self.assertRaises(T.LayoutError) as cm:
                B.build_file(self.reg, GAMEDATA, B.tables_in(self.reg, GAMEDATA),
                             override={name: (head, rows + [extra])})
            self.assertIn("no stored count", str(cm.exception))

    def appended(self, name: str, base_label: str | None = None, label: str = "_MODTEST",
                 policies=None, changes: dict | None = None):
        """A copy of one row of `name` appended to GameData.bin (new label, number set).
        Returns (original container, rebuilt container, head, new row)."""
        head, rows = B.dump_rows(self.reg, name)
        col = {h: i for i, h in enumerate(head)}
        src = next(r for r in rows if r[col["label"]] == base_label) if base_label else rows[1]
        pol = T.append_policies().get(name)
        new = list(src)
        lab = (pol.prefix if pol else "") + label.lstrip("_")
        new[col["index"]] = str(len(rows))
        new[col["label"]] = lab
        for f in T.Codec(self.reg, name).fields:
            if f.kind == "str" and f.ref == "self":
                new[col[f.name]] = lab
        if pol and pol.number_field:
            new[col[pol.number_field]] = str(int(rows[0][col[pol.number_field]]) + len(rows))
        for h, v in (changes or {}).items():
            new[col[h]] = v
        out = B.build_file(self.reg, GAMEDATA, B.tables_in(self.reg, GAMEDATA),
                           override={name: (head, rows + [new])}, policies=policies)
        return T.container(GAMEDATA), T.Container(GAMEDATA, out), head, new

    def test_append_item_and_job(self):
        for name, extra in (("Item", {"might": "9", "miid_name": "MIID_MODTEST"}), ("Job", {"mov": "7"})):
            c0, nc, head, new = self.appended(name, changes=extra)
            t = self.reg[name]
            self.assertTrue(nc.is_lz and nc.raw[0] == c0.raw[0])          # same LZ format
            self.assertEqual(T.lz.decompress(nc.raw), nc.dec)
            s0, n0 = T.locate(t, c0)
            s1, n1 = T.locate(t, nc)
            self.assertEqual((s1, n1), (s0, n0 + 1))
            lab = T.untext(new[head.index("label")])
            self.assertEqual(nc.label_off[lab], s1 + n0 * t.size)            # resolves by its ID
            self.assertNotIn(lab, c0.label_off)
            cd = T.Codec(self.reg, name)
            labels = T.record_labels(t, nc, s1, n1)
            self.assertEqual(cd.decode(nc, n0, s1 + n0 * t.size, labels[n0]), new)
            for other in B.tables_in(self.reg, GAMEDATA):
                ot, oc = self.reg[other], T.Codec(self.reg, other)
                a0, k0 = T.locate(ot, c0)
                a1, k1 = T.locate(ot, nc)
                l0, l1 = T.record_labels(ot, c0, a0, k0), T.record_labels(ot, nc, a1, k1)
                got = [oc.decode(nc, i, a1 + i * ot.size, l1[i]) for i in range(k1)]
                want = [oc.decode(c0, i, a0 + i * ot.size, l0[i]) for i in range(k0)]
                want = B.shift_cells(self.reg, other, want, B.LAST_MOVES[GAMEDATA])
                self.assertEqual(got[:k0] if other == name else got, want, other)
            saved = T._CACHE.get(GAMEDATA)
            try:
                T._CACHE[GAMEDATA] = nc
                for other in B.tables_in(self.reg, GAMEDATA):
                    self.assertEqual(K.check_table(self.reg, other)[1], [], f"{name} append: {other}")
            finally:
                T._CACHE[GAMEDATA] = saved

    def test_append_refusals(self):
        # Person: the game keeps a 256-person bit set (appends.csv evidence); never deleted
        for name, why in (("Person", "256"), ("Belong", "nobody has checked")):
            with self.assertRaises(T.LayoutError) as cm:
                self.appended(name)
            self.assertIn(why, str(cm.exception), name)
        # planted: the same Item append with a policy that names a fixed array is refused
        pols = T.append_policies()
        planted = dict(pols, Item=T.AppendPolicy("Item", False, "item_number", "IID_",
                                                 "planted: a fixed array of 355 item flags"))
        with self.assertRaises(T.LayoutError) as cm:
            self.appended("Item", policies=planted)
        self.assertIn("planted: a fixed array", str(cm.exception))
        # a refuse_if_files glob that matches a RomFS file refuses too
        tripped = dict(pols, Item=T.AppendPolicy("Item", True, "item_number", "IID_", "x",
                                                 "GameData/GameData.bin.l?"))
        with self.assertRaises(T.LayoutError) as cm:
            self.appended("Item", policies=tripped)
        self.assertIn("exists", str(cm.exception))
        # a wrong record number, a reused label, a gap in the numbering, a deleted row
        with self.assertRaises(T.LayoutError) as cm:
            self.appended("Item", changes={"item_number": "7"})
        self.assertIn("item_number must be", str(cm.exception))
        head, rows = B.dump_rows(self.reg, "Item")
        dup = list(rows[3])
        dup[head.index("index")] = str(len(rows))
        with self.assertRaises(T.LayoutError):
            B.build_file(self.reg, GAMEDATA, B.tables_in(self.reg, GAMEDATA),
                         override={"Item": (head, rows + [dup])})
        gap = list(rows[3])
        gap[head.index("index")] = str(len(rows) + 1)
        with self.assertRaises(T.LayoutError):
            B.build_file(self.reg, GAMEDATA, B.tables_in(self.reg, GAMEDATA),
                         override={"Item": (head, rows + [gap])})
        with self.assertRaises(T.LayoutError) as cm:
            B.build_file(self.reg, GAMEDATA, B.tables_in(self.reg, GAMEDATA),
                         override={"Item": (head, rows[:-1])})
        self.assertIn("never deleted", str(cm.exception))

    def test_fixed_counts_are_proven(self):
        # a fixed:N count that is one too small or too large is rejected by check.py
        import copy
        for name in [n for n in self.reg if self.reg[n].count.startswith("fixed:")]:
            self.assertEqual(K.fixed_count_errors(self.reg, name), [], name)
            n = int(self.reg[name].count[6:])
            for wrong in (n - 1, n + 1):
                bad = copy.copy(self.reg[name])
                bad.count = f"fixed:{wrong}"
                self.assertNotEqual(K.fixed_count_errors(dict(self.reg, **{name: bad}), name), [],
                                    f"{name} fixed:{wrong}")

    def test_new_table_references(self):
        # the header points at every new table; references decode as labels
        head, rows = B.dump_rows(self.reg, "GameDataHeader")
        for col in ("personality_table", "item_kind_table", "item_subkind_table", "item_refine_table",
                    "weapon_level_table", "weapon_bonus_table", "weapon_interact_table", "exp_table",
                    "terrain_cost_table", "unknown_table_0x50", "achieve_bonus_table", "arena_table"):
            self.assertEqual(rows[0][head.index(col)], "#0", col)
        self.assertTrue(rows[0][head.index("tutorial_table")].startswith("TUTID_"))
        for name in ("ArenaLow", "ArenaHigh"):
            head, rows = B.dump_rows(self.reg, name)
            self.assertTrue(all(r[head.index("job")].startswith("JID_") for r in rows), name)
            self.assertTrue(all(r[head.index("weapon")].startswith("IID_") for r in rows), name)
        head, rows = B.dump_rows(self.reg, "AchieveBonusBattle")
        self.assertTrue(all(r[head.index("item")].startswith("IID_") for r in rows))
        head, rows = B.dump_rows(self.reg, "Tutorial")
        self.assertTrue(all(r[head.index("tutid")] == r[head.index("label")] for r in rows))
        # every sub-kind names one of the nine kinds; every item's sub-kind and refine rows exist
        self.assertEqual(len(B.dump_rows(self.reg, "ItemKind")[1]), 9)
        self.assertEqual(len(B.dump_rows(self.reg, "ItemSubKind")[1]), 21)

    def test_edit_test_multi_cell(self):
        self.assertTrue(B.edit_test(self.reg))

    def test_all_files_rebuild_byte_identical(self):
        by_file: dict[str, list[str]] = {}
        dumps = {n: B.dump_rows(self.reg, n) for n in self.reg if os.path.exists(T.layout_path(n))}
        for n in dumps:
            for rel in self.reg[n].files():
                by_file.setdefault(rel, []).append(n)
        bad = [rel for rel, names in sorted(by_file.items())
               if B.build_file(self.reg, rel, names, override=dumps) != T.container(rel).raw]
        self.assertEqual(bad, [])
        self.assertEqual(len(by_file), 1 + 117 + 109 + 185)

    def test_layouts_pass_and_selftest_rejects_mutations(self):
        for n in self.reg:
            if os.path.exists(T.layout_path(n)):
                nrec, errs = K.check_table(self.reg, n)
                self.assertEqual(errs, [], n)
                self.assertGreater(nrec, 0, n)
        self.assertEqual(K.selftest(self.reg), 0)

    def test_csv_text_round_trip(self):
        for n in ("Person", "DisposUnit", "TerrainGrid"):
            head, rows = B.dump_rows(self.reg, n)
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            w.writerow(head)
            w.writerows(rows)
            back = list(csv.reader(io.StringIO(buf.getvalue())))
            self.assertEqual(back[0], head)
            self.assertEqual(back[1:], rows, n)

    def test_references(self):
        head, rows = B.dump_rows(self.reg, "DisposFaction")
        col = head.index("first_unit")
        self.assertTrue(all(r[col].startswith("#") for r in rows))
        self.assertEqual(rows[0][col], "#0")
        head, rows = B.dump_rows(self.reg, "Person")
        self.assertTrue(all(r[head.index("pid")] == r[head.index("label")] for r in rows))
        # class references are labels, never bare numbers, in the vanilla data
        self.assertTrue(all(r[head.index("job")].startswith("JID_") for r in rows))

    def test_id_lists(self):
        names = T.id_names("PersonFlag", self.reg)
        self.assertEqual(len(names), 63)
        self.assertTrue(all(n.startswith(b"SPID_") for n in names))
        self.assertEqual(len(T.id_names("ItemFlag", self.reg)), 64)


@unittest.skipUnless(HAVE_ROMFS and HAVE_TEXT, "needs extracted/text.bin and the RomFS symbol map")
class EvidenceTests(unittest.TestCase):
    def test_selftest(self):
        import evidence as E
        self.assertEqual(E.selftest(), 0)

    def test_cited_accessors(self):
        import evidence as E
        with open(E.TEXT, "rb") as fh:
            text = fh.read()
        syms = E.symbols()
        rets = E.getters(syms)
        by_name = {n: (a, syms[k + 1][0]) for k, (a, n) in enumerate(syms[:-1])}

        def paths(name):
            a, e = by_name[name]
            return E.analyse(text[a - E.TEXT_VA:e - E.TEXT_VA], a, False, rets)
        self.assertIn("arg0+0x9C->+0x40[i]:s8", paths("Unit::GetGrow(int) const"))
        self.assertIn("arg0+0x1A:u16", paths("Job::IsFlyer(void) const"))
        self.assertIn("arg0+0x9C->+0x39:s8", paths(
            "Unit::GetStrImpl(const unit::Item*,bool,bool,unit::detail::EnhanceDefinition::Type) const"))
        self.assertIn("Item+0x1F:u8", paths("unit::Item::GetPower(void) const"))
        # getters of the GameData sub-tables (evidence.TABLE_GETTERS)
        self.assertIn("ItemRefine+0x1:u8", paths("unit::Item::GetPower(void) const"))
        self.assertIn("ExpBattle+0x24[i]:s8", paths(
            "Unit::GetExpDestroy(Unit::ExpMode::Type,const Unit*,bool) const"))
        self.assertIn("ExpBattleFloor+0x0[i]:s8", paths(
            "Unit::GetExpDamage(Unit::ExpMode::Type,const Unit*) const"))
        self.assertIn("Personality+0x3C:s8", paths(
            "PersonEnhanceDual::GetEdit(BattleCapability::Type,int,int,int) const"))

    def test_fixed_array_scan(self):
        # the scan behind config/tables/appends.csv: the 256-person bit set is found
        import evidence as E
        with open(E.TEXT, "rb") as fh:
            text = fh.read()
        hits = E.find_bitsets(text, E.TEXT_VA)
        self.assertIn((0x0019B274, 256, 0x0019B284), hits)


if __name__ == "__main__":
    unittest.main(verbosity=2)
