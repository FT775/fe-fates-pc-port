"""Tests for text mods (pipeline T1: tools/mods/textmod.py and its use in mods.py) and
for whole-file (romfs/) mods, Fire Emblem Fates.

    python -m unittest tests.test_text_mods          (from the repo root)

Most tests use synthetic message archives made here (invented labels and text, LZ13
compressed like the game's), in a scratch folder under build/ that is deleted afterwards:
a fake RomFS, a scratch mods workspace, a scratch stage folder and a fake Zakuro data
folder. The real mods/, build/mods/, %APPDATA%\\zakuro and play/ are never touched.

UserFilesTests reads the user's own extracted/romfs/ at run time (skipped when it is
absent): all 1,328 message archives must round-trip byte for byte through the mod text
form (and none may exist outside the message folders), renaming one unit name must
change only the expected bytes, and the rename demo must build, install into a scratch
Zakuro folder under build/ and uninstall back to the exact earlier state. The new-item
demo (ExampleItem) must build; its staged files are decompressed and parsed here: the
new Item record resolves by its ID, its name and help messages exist, the Chapter 1 unit
carries it; install and uninstall restore the scratch folder; a new Person row, an item
without text and a placement naming an unknown item are refused.

MapModTests and FaceModTests (also on the user's own files, skipped when absent) cover
mods/<Name>/maps/ and mods/<Name>/faces/ (tools/mods/mapface.py): the ExampleMap and
ExampleFace demos are built, their staged files decoded here (one unit moved, only its
position; one portrait picture changed and bluer), installed into a scratch Zakuro folder
under build/ and uninstalled back exactly; bad positions, unknown items, map/table and
mod/mod conflicts, size changes without "allow_face_resize" and mixed sizes are refused;
unedited folders stage nothing.

CastleModTests (on the user's own files, skipped when absent) cover mods/<Name>/castle/
(tools/mods/castlemod.py over tools/castle): the ExampleCastle demo is built and its staged
file decompressed here (exactly the one Strength byte of one dish changed), installed into a
scratch Zakuro folder under build/ and uninstalled back exactly; a dish added through a mod
decodes back with its label; refused: rows added to AcceShop, removed rows, renamed labels,
added list items, wrong columns, unknown folders and files, a castle file also replaced as a
whole file; two mods setting one cell differently conflict unless the later one overrides;
unedited folders stage nothing. No game text is written in this file or anywhere in the
repository.
"""
from __future__ import annotations

import contextlib
import errno
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))
sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
import lz  # noqa: E402
import msg  # noqa: E402
import textmod as TX  # noqa: E402

SCRATCH_PARENT = os.path.join(ROOT, "build", "test-textmods")
USER_ROMFS = os.path.join(ROOT, "extracted", "romfs")
REL = "m/@E/Synthetic.bin.lz"
FATES_ARCHIVES = 1328          # message archives in the Special Edition (USA) RomFS (scout, 2026-11-10)
NAME = b"MESS_ARCHIVE_Synthetic"


def load_mods():
    spec = importlib.util.spec_from_file_location(f"{TX.GAME.key}_mods_for_text_tests",
                                                  os.path.join(ROOT, "tools", "mods", "mods.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = load_mods()


def rebuild_from_dump(args) -> tuple[str, bytes, bytes, list[str]]:
    """For the user-files test (module level so a process pool can run it): read the stored
    file here, go dump -> mod text -> parse -> diff -> build, and hand BOTH byte strings
    back so the test compares them itself instead of trusting a verdict from the tool."""
    rel, romfs = args
    with open(os.path.join(romfs, *rel.split("/")), "rb") as fh:
        raw = fh.read()
    van = TX.Archive(rel, raw)
    name, items, errs = TX.parse_mod_text(van.dump().encode("utf-8"), rel)
    changes, errs2, _w, _n = TX.diff_text(van, name, items, rel)
    problems = errs + errs2 + ([f"{len(changes)} label(s) read back changed"] if changes else [])
    return rel, raw, TX.build_archive(van, changes), problems

# Round 67 (release part A): a FIXED sample of 40 message archives that the core test always runs (the full 1,328
# round trip is in tests/heavy.txt): the 20 largest, the largest and the two smallest of each of the 5 places
# (shared English, the three routes, common), the smallest Japanese-named ones and the smallest overall.
SAMPLE_ARCHIVES = [
    "m/@E/GameData.bin.lz",
    "m/B/@E/B028.bin.lz",
    "m/@E/\u306b\u304e\u3084\u304b\u3057_\u901a\u308a\u3059\u304c\u308a.bin.lz",
    "m/@E/\u5e97\u756a_\u98df\u6750_\u81ea\u57ce.bin.lz",
    "m/@E/Ending.bin.lz",
    "m/A/@E/A028.bin.lz",
    "m/B/@E/B008.bin.lz",
    "m/@E/\u30de\u30a4\u30eb\u30fc\u30e0_\u6328\u62f6.bin.lz",
    "m/B/@E/B007.bin.lz",
    "m/B/@E/B011.bin.lz",
    "m/A/@E/A018.bin.lz",
    "m/A/@E/A010.bin.lz",
    "m/B/@E/B013.bin.lz",
    "m/B/@E/B024.bin.lz",
    "m/B/@E/B016.bin.lz",
    "m/B/@E/B009.bin.lz",
    "m/A/@E/A022.bin.lz",
    "m/B/@E/B025.bin.lz",
    "m/A/@E/A009.bin.lz",
    "m/B/@E/B014.bin.lz",
    "m/@E/\u521d\u671f\u8a2d\u5b9a.bin.lz",
    "m/@E/UnitList.bin.lz",
    "m/A/@E/A027.bin.lz",
    "m/A/@E/A024.bin.lz",
    "m/B/@E/B019.bin.lz",
    "m/B/@E/B023.bin.lz",
    "m/C/@E/C022.bin.lz",
    "m/C/@E/C027.bin.lz",
    "m/C/@E/C013.bin.lz",
    "m/common/\u652f\u63f4S_\u82b1.bin.lz",
    "m/common/\u30a2\u30af\u30bb\u30b5\u30ea\u30fc.bin.lz",
    "m/common/\u306b\u304e\u3084\u304b\u3057_\u901a\u308a\u3059\u304c\u308a.bin.lz",
    "m/@E/\u30e0\u30fc\u30d3\u30fc\u53f0\u672c_\u25cb\uff11\uff13\u3000\u898b\u3048\u3056\u308b\u6249.bin.lz",
    "m/@E/\u30e0\u30fc\u30d3\u30fc\u53f0\u672c_\u25cb\uff11\uff10\u3000\u6b4c\u306e\u7d42\u308f\u308a.bin.lz",
    "m/@E/CardEntry.bin.lz",
    "m/@E/\u306b\u304e\u3084\u304b\u3057_\u7269\u3092\u3082\u3089\u3063\u305f\u6642.bin.lz",
    "m/B/@E/B018.bin.lz",
    "m/A/@E/A016.bin.lz",
    "m/B/@E/B012.bin.lz",
    "m/B/@E/B027.bin.lz",
]

# invented content: three messages, one alias, a line break and a '$' code
ENTRIES = [
    (b"MPID_Alpha", "Alpha", False),
    (b"MPID_Beta", "Beta knight", False),
    (b"MPID_Beta_Alias", b"MPID_Beta", True),
    (b"MID_Talk", "Hello there.\nSecond line.$k", False),
]


def synthetic_archive(entries=ENTRIES, name=NAME) -> tuple[bytes, bytes]:
    """(stored LZ13 bytes, decompressed bytes)."""
    dec = msg.build_bytes(name, entries)
    return lz.compress(dec, 0x13), dec


def header(name=NAME) -> str:
    return f"{TX.HEADER}\n#name {msg.isbin.quote(name)}\n"


def snapshot(root):
    out = {}
    for d, _dirs, files in os.walk(root):
        rel = os.path.relpath(d, root)
        out[("dir", rel)] = None
        for f in files:
            with open(os.path.join(d, f), "rb") as fh:
                out[("file", os.path.join(rel, f))] = fh.read()
    return out


class Scratch(unittest.TestCase):
    """A fake RomFS with the synthetic archive, under build/test-textmods/."""

    def setUp(self) -> None:
        os.makedirs(SCRATCH_PARENT, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="t-", dir=SCRATCH_PARENT)
        self.romfs = os.path.join(self.tmp, "romfs")
        self.raw, self.dec = synthetic_archive()
        self.put(self.romfs, REL, self.raw)
        TX.clear_cache()

    def tearDown(self) -> None:
        TX.clear_cache()
        shutil.rmtree(self.tmp, ignore_errors=True)
        with contextlib.suppress(OSError):
            os.rmdir(SCRATCH_PARENT)

    @staticmethod
    def put(root, rel, data: bytes) -> str:
        p = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)
        return p

    def van(self) -> TX.Archive:
        return TX.archive(REL, self.romfs)

    def diff(self, text: str):
        name, items, perr = TX.parse_mod_text(text.encode("utf-8"), "t.txt")
        changes, err, warn, notes = TX.diff_text(self.van(), name, items, "t.txt")
        return changes, perr + err, warn, notes


class TextModTests(Scratch):
    def test_unchanged_full_dump_round_trips(self):
        changes, errors, _w, _n = self.diff(self.van().dump())
        self.assertEqual((changes, errors), ({}, []))
        self.assertEqual(TX.build_archive(self.van(), {}), self.raw)
        self.assertEqual(TX.roundtrip_one((REL, self.romfs)), (REL, True, ""))

    def test_same_length_rename_changes_only_that_message(self):
        changes, errors, warns, _n = self.diff(header() + "[MPID_Alpha]\nOmega\n")
        self.assertEqual(errors, [])
        self.assertEqual(warns, [])
        self.assertEqual(changes, {b"MPID_Alpha": "Omega"})
        out = TX.build_archive(self.van(), changes)
        self.assertEqual(out[0], 0x13, "stays LZ13 like the original")
        new = lz.decompress(out)
        self.assertEqual(len(new), len(self.dec))
        diff = [i for i, (a, b) in enumerate(zip(new, self.dec)) if a != b]
        start = self.van().offset[b"MPID_Alpha"]
        self.assertTrue(diff)
        self.assertTrue(all(start <= i < start + 10 for i in diff), diff)

    def test_longer_rename_keeps_everything_else(self):
        changes, errors, _w, _n = self.diff(header() + "[MPID_Alpha]\nAlpha the Second\n")
        self.assertEqual(errors, [])
        out = TX.build_archive(self.van(), changes)
        name, entries, _b = msg.parse(lz.decompress(out))
        want = [(b"MPID_Alpha", "Alpha the Second", False)] + ENTRIES[1:]
        self.assertEqual((name, entries), (NAME, want))

    def test_alias_rules(self):
        # alias line as dumped: fine, no change
        changes, errors, _w, _n = self.diff(header() + "[MPID_Beta_Alias] = MPID_Beta\n")
        self.assertEqual((changes, errors), ({}, []))
        # changing the shared message changes the alias too (noted)
        changes, errors, _w, notes = self.diff(header() + "[MPID_Beta]\nGamma knight\n")
        self.assertEqual(errors, [])
        self.assertTrue(any("MPID_Beta_Alias" in n for n in notes), notes)
        _name, entries, _b = msg.parse(lz.decompress(TX.build_archive(self.van(), changes)))
        self.assertEqual(entries[2], (b"MPID_Beta_Alias", b"MPID_Beta", True))
        self.assertEqual(entries[1][1], "Gamma knight")
        # giving the alias its own text splits it off
        changes, errors, _w, notes = self.diff(header() + "[MPID_Beta_Alias]\nOwn text\n")
        self.assertEqual(errors, [])
        _name, entries, _b = msg.parse(lz.decompress(TX.build_archive(self.van(), changes)))
        self.assertEqual(entries[1], (b"MPID_Beta", "Beta knight", False))
        self.assertEqual(entries[2], (b"MPID_Beta_Alias", "Own text", False))
        # changed or invented alias lines are refused
        _c, errors, _w, _n = self.diff(header() + "[MPID_Beta_Alias] = MPID_Alpha\n")
        self.assertTrue(any("alias lines must stay as dumped" in e for e in errors), errors)
        _c, errors, _w, _n = self.diff(header() + "[MPID_Alpha] = MPID_Beta\n")
        self.assertTrue(any("not an alias" in e for e in errors), errors)

    def test_new_labels_only_for_new_rows(self):
        # a label the archive does not have: refused, unless a row the mod adds names it
        body = header() + "[MIID_NEWTHING]\nNew thing\n"
        name, items, _p = TX.parse_mod_text(body.encode("utf-8"), "t.txt")
        _c, errors, _w, _n = TX.diff_text(self.van(), name, items, "t.txt")
        self.assertTrue(any("refused unless a row this mod adds uses them" in e for e in errors), errors)
        changes, errors, _w, notes = TX.diff_text(self.van(), name, items, "t.txt", {b"MIID_NEWTHING"})
        self.assertEqual((changes, errors), ({b"MIID_NEWTHING": "New thing"}, []))
        self.assertTrue(any("new message" in n for n in notes), notes)
        _name, entries, _b = msg.parse(lz.decompress(TX.build_archive(self.van(), changes)))
        self.assertEqual(entries[:len(ENTRIES)], ENTRIES)            # the game's messages unchanged
        self.assertEqual(entries[len(ENTRIES):], [(b"MIID_NEWTHING", "New thing", False)])
        # a new label cannot be an alias
        name, items, _p = TX.parse_mod_text((header() + "[MIID_NEWTHING] = MPID_Alpha\n").encode(), "t.txt")
        _c, errors, _w, _n = TX.diff_text(self.van(), name, items, "t.txt", {b"MIID_NEWTHING"})
        self.assertTrue(any("new label" in e for e in errors), errors)

    def test_broken_edits_give_clear_errors(self):
        cases = [
            ("[MPID_Alpha]\nX\n", "first line must be '#msgarchive 1'"),
            (f"{TX.HEADER}\n[MPID_Alpha]\nX\n", "second line must be the '#name"),
            (header(b"MESS_ARCHIVE_Other") + "[MPID_Alpha]\nX\n", "keep the #name line as dumped"),
            (header() + "[MPID_Nobody]\nX\n", "new labels are refused"),
            (header() + "[MPID_Alpha]\nX\n[MPID_Alpha]\nY\n", "appears twice"),
            (header() + "[MPID_Alpha]\nbad \\q escape\n", "line 4: bad escape"),
            (header() + "[MPID_Alpha]\nfirst line\nsecond line\n", "must stay on the ONE line"),
            (header() + "[MPID_Alpha] Omega\n", "put the text on the next line"),
            (header() + "[MPID_Alpha]", "label without a text line"),
            (header() + "[MPID_Alpha]\n", "label without a text line"),     # newline at end of file
            (header() + "[MPID_Alpha\nX\n", "without ']'"),
            (header() + "[MPID_Alpha]\n\\u12\n", "four hex digits"),
        ]
        for text, want in cases:
            with self.subTest(want=want):
                changes, errors, _w, _n = self.diff(text)
                self.assertTrue(any(want in e for e in errors), errors)
        _n, _i, errors = TX.parse_mod_text(b"#msgarchive 1\n#name \"x\"\n[A]\ncaf\xe9\n", "t.txt")
        self.assertTrue(any("not UTF-8" in e for e in errors), errors)

    def test_editor_variants_are_accepted(self):
        text = ("﻿" + header() + "\n# my rename\n\n[MPID_Alpha]\nOmega\n\n# done\n").replace("\n", "\r\n")
        changes, errors, _w, _n = self.diff(text)
        self.assertEqual((changes, errors), ({b"MPID_Alpha": "Omega"}, []))
        # an empty message is the line right after the label, even if blank
        changes, errors, warns, _n = self.diff(header() + "[MPID_Alpha]\n\n")
        self.assertEqual((changes, errors), ({b"MPID_Alpha": ""}, []))
        self.assertTrue(any("now empty" in w for w in warns), warns)

    def test_warnings(self):
        _c, errors, warns, _n = self.diff(header() + "[MID_Talk]\nHello there.\\nSecond line.\n")
        self.assertEqual(errors, [])
        self.assertTrue(any("control code" in w for w in warns), warns)
        _c, errors, warns, _n = self.diff(header() + "[MPID_Alpha]\nAlphä\n")
        self.assertEqual(errors, [])
        self.assertTrue(any("font" in w for w in warns), warns)

    def test_read_back_guard_refuses_a_lost_edit(self):
        # if the encoder ever dropped or garbled an edit, build_archive must refuse, not ship it
        real = msg.build_bytes

        def drops_changes(name, entries):
            return real(name, [e for e in ENTRIES])          # ignores the edit
        TX.msg.build_bytes = drops_changes
        try:
            with self.assertRaises(TX.TextError) as cm:
                TX.build_archive(self.van(), {b"MPID_Alpha": "Omega"})
        finally:
            TX.msg.build_bytes = real
        self.assertIn("does not read back as the edit", str(cm.exception))
        self.assertIn("MPID_Alpha", str(cm.exception))

    def test_not_a_message_archive(self):
        self.put(self.romfs, "GameData/Table.bin.lz", lz.compress(b"\0" * 64, 0x13))
        with self.assertRaises(TX.TextError) as cm:
            TX.archive("GameData/Table.bin.lz", self.romfs)
        self.assertIn("not a message archive", str(cm.exception))
        with self.assertRaises(TX.TextError) as cm:
            TX.archive("m/@E/Missing.bin.lz", self.romfs)
        self.assertIn("no RomFS file", str(cm.exception))

    def test_archive_places(self):
        self.assertEqual(TX.archive_place("m/@E/GameData.bin.lz"), "English (all routes)")
        self.assertEqual(TX.archive_place("m/A/@E/X.bin.lz"), "English, Birthright route only (A)")
        self.assertEqual(TX.archive_place("m/C/@E/X.bin.lz"), "English, Revelation route only (C)")
        self.assertEqual(TX.archive_place("m/common/X.bin.lz"), "common (no language folder)")
        self.assertEqual(TX.archive_place("GameData/X.bin.lz"), "other")
        # message_archives looks in the message folders unless asked to search everywhere
        self.put(self.romfs, "m/B/@E/Route.bin.lz", self.raw)
        self.put(self.romfs, "m/common/Shared.bin.lz", self.raw)
        self.put(self.romfs, "elsewhere/Stray.bin.lz", self.raw)
        self.assertEqual(TX.message_archives(self.romfs),
                         ["m/@E/Synthetic.bin.lz", "m/B/@E/Route.bin.lz", "m/common/Shared.bin.lz"])
        self.assertIn("elsewhere/Stray.bin.lz", TX.message_archives(self.romfs, everywhere=True))

    def test_mod_text_files_keyed_by_romfs_path(self):
        mod = os.path.join(self.tmp, "mods", "A")
        self.put(mod, "text/m/@E/Synthetic.bin.lz.txt", b"")
        self.put(mod, "text/notes.md", b"")
        files = TX.mod_text_files(mod)
        self.assertEqual([r for r, _p in files], [REL])


class ModsIntegrationTests(Scratch):
    """mods.py build / install / status / uninstall with text, on the synthetic RomFS."""

    def setUp(self) -> None:
        super().setUp()
        os.makedirs(os.path.join(self.tmp, "zakuro"))
        self.ctx = M.Ctx(mods_dir=os.path.join(self.tmp, "mods"), stage_dir=os.path.join(self.tmp, "stage"),
                         zakuro_dir=os.path.join(self.tmp, "zakuro"), quiet=True, romfs=self.romfs)

    def text_mod(self, name, body, order=None, override=False):
        m = M.new_mod(self.ctx, name, tables=[])
        self.put(m.dir, "text/" + REL + ".txt", body.encode("utf-8"))
        m.meta["override"] = override
        if order is not None:
            m.meta["order"] = order
        m.save()
        return m

    def test_full_dump_mod_stages_nothing(self):
        m = M.new_mod(self.ctx, "Full", text=[REL])
        self.assertEqual(m.tables(), [])
        self.assertEqual([r for r, _p in m.texts()], [REL])
        r = M.build(self.ctx)
        self.assertEqual((r.errors, r.files), ([], {}))
        self.assertEqual(M.read_staged(self.ctx)["files"], [])

    def test_edit_full_dump_stages_one_archive(self):
        m = M.new_mod(self.ctx, "Full", text=[REL])
        path = m.texts()[0][1]
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.replace("[MPID_Alpha]\nAlpha\n", "[MPID_Alpha]\nOmega\n"))
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertEqual(sorted(r.files), [REL])
        self.assertEqual(r.text_counts, {"Full": 1})
        staged = M.read_staged(self.ctx)["files"][0]
        self.assertEqual((staged["kind"], staged["labels"]), ("text", 1))
        with open(os.path.join(self.ctx.stage_dir, "changes.txt"), encoding="utf-8") as fh:
            self.assertIn("[MPID_Alpha]: Alpha -> Omega", fh.read())

    def test_install_status_uninstall(self):
        z = self.ctx.zakuro_dir
        self.put(z, "settings.toml", b"x")
        self.put(z, f"mods/{M.TITLE_HEX}/romfs/{REL}", b"someone else's file")
        before = snapshot(z)
        self.text_mod("Rename", header() + "[MPID_Alpha]\nOmega\n")
        self.assertEqual(M.build(self.ctx).errors, [])
        M.install(self.ctx)
        dst = os.path.join(self.ctx.title_dir(), "romfs", *REL.split("/"))
        with open(dst, "rb") as fh:
            placed = fh.read()
        self.assertEqual(msg.parse(lz.decompress(placed))[1][0], (b"MPID_Alpha", "Omega", False))
        loud = M.Ctx(mods_dir=self.ctx.mods_dir, stage_dir=self.ctx.stage_dir, zakuro_dir=z, romfs=self.romfs)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            M.cmd_status(loud)
        self.assertIn("(1 text label(s))", out.getvalue())
        self.assertIn(f"romfs/{REL}: intact", out.getvalue())
        ok, _msgs = M.uninstall(self.ctx)
        self.assertTrue(ok)
        self.assertEqual(snapshot(z), before)

    def test_conflict_and_override(self):
        self.text_mod("A", header() + "[MPID_Alpha]\nOmega\n", order=10)
        b = self.text_mod("B", header() + "[MPID_Alpha]\nSigma\n", order=20)
        r = M.build(self.ctx)
        self.assertTrue(any(e.startswith("conflict:") for e in r.errors), r.errors)
        self.assertEqual(r.files, {})
        b.meta["override"] = True
        b.save()
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertEqual(msg.parse(lz.decompress(r.files[REL]))[1][0][1], "Sigma")
        # different labels of the same archive from two mods merge into one file
        b.meta["override"] = False
        b.save()
        self.put(b.dir, "text/" + REL + ".txt", (header() + "[MPID_Beta]\nSigma\n").encode())
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        ents = msg.parse(lz.decompress(r.files[REL]))[1]
        self.assertEqual((ents[0][1], ents[1][1]), ("Omega", "Sigma"))

    def test_disabled_text_mod_changes_nothing(self):
        m = self.text_mod("Off", header() + "[MPID_Alpha]\nOmega\n")
        m.meta["enabled"] = False
        m.save()
        r = M.build(self.ctx)
        self.assertEqual((r.errors, r.files, r.text_merged), ([], {}, {}))
        self.assertEqual(M.read_staged(self.ctx)["files"], [])
        with open(os.path.join(self.ctx.stage_dir, "changes.txt"), encoding="utf-8") as fh:
            self.assertNotIn("MPID_Alpha", fh.read())

    def test_text_edit_makes_the_build_out_of_date(self):
        m = self.text_mod("Rename", header() + "[MPID_Alpha]\nOmega\n")
        self.assertEqual(M.build(self.ctx).errors, [])
        built = M.read_staged(self.ctx)["fingerprint"]
        self.assertEqual(M.fingerprint(self.ctx), built)
        self.put(m.dir, "text/" + REL + ".txt", (header() + "[MPID_Alpha]\nSigma\n").encode())
        self.assertNotEqual(M.fingerprint(self.ctx), built)
        loud = M.Ctx(mods_dir=self.ctx.mods_dir, stage_dir=self.ctx.stage_dir,
                     zakuro_dir=self.ctx.zakuro_dir, romfs=self.romfs)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            M.cmd_status(loud)
        self.assertIn("OUT OF DATE", out.getvalue())

    def test_list_shows_text_labels(self):
        self.text_mod("Rename", header() + "[MPID_Alpha]\nOmega\n[MPID_Beta]\nSigma\n")
        self.text_mod("Bad", header() + "[MPID_Nobody]\nX\n")
        loud = M.Ctx(mods_dir=self.ctx.mods_dir, stage_dir=self.ctx.stage_dir,
                     zakuro_dir=self.ctx.zakuro_dir, romfs=self.romfs)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            M.cmd_list(loud)
        rows = {}
        for ln in out.getvalue().splitlines():
            if " - " in ln:
                # (override column is blank)
                *_head, cells, texts, files, maps, faces, castle, name = ln.split(" - ")[0].split()
                rows[name] = [cells, texts, files, maps, faces, castle]
        self.assertEqual(rows["Rename"], ["0", "2", "0", "0", "0", "0"])
        self.assertEqual(rows["Bad"], ["0", "0!", "0", "0", "0", "0"])

    def test_broken_edit_stops_build_and_install(self):
        self.text_mod("Bad", header() + "[MPID_Nobody]\nX\n")
        r = M.build(self.ctx)
        self.assertTrue(any("Bad/text/m/@E/Synthetic.bin.lz.txt line 3" in e for e in r.errors), r.errors)
        self.assertEqual(r.files, {})
        self.assertIsNone(M.read_staged(self.ctx))
        m = M.new_mod(self.ctx, "Wrong", tables=[])
        self.put(m.dir, "text/m/@E/Missing.bin.lz.txt", header().encode())
        r = M.build(self.ctx)
        self.assertTrue(any("no RomFS file m/@E/Missing.bin.lz" in e for e in r.errors), r.errors)

    def asset_mod(self, name, rel, data, order=None, override=False):
        m = M.new_mod(self.ctx, name, tables=[])
        self.put(m.dir, "romfs/" + rel, data)
        m.meta["override"] = override
        if order is not None:
            m.meta["order"] = order
        m.save()
        return m

    def test_romfs_file_installs_as_is_and_uninstalls(self):
        z = self.ctx.zakuro_dir
        self.put(z, "settings.toml", b"x")
        self.put(self.romfs, "face/Pic.bch.lz", lz.compress(b"original picture" * 8, 0x13))
        before = snapshot(z)
        new = lz.compress(b"replaced picture" * 8, 0x13)
        self.asset_mod("Pic", "face/Pic.bch.lz", new)
        self.text_mod("Rename", header() + "[MPID_Alpha]\nOmega\n")
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.paths(), ["face/Pic.bch.lz", REL])
        self.assertEqual(r.asset_counts, {"Pic": 1, "Rename": 0})
        kinds = {f["path"]: f.get("kind") for f in M.read_staged(self.ctx)["files"]}
        self.assertEqual(kinds, {"face/Pic.bch.lz": "romfs", REL: "text"})
        M.install(self.ctx)
        with open(os.path.join(self.ctx.title_dir(), "romfs", "face", "Pic.bch.lz"), "rb") as fh:
            self.assertEqual(fh.read(), new)
        loud = M.Ctx(mods_dir=self.ctx.mods_dir, stage_dir=self.ctx.stage_dir, zakuro_dir=z, romfs=self.romfs)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            M.cmd_status(loud)
            M.cmd_list(loud)
        self.assertIn("romfs/face/Pic.bch.lz  (whole file from Pic)", out.getvalue())
        self.assertIn("romfs/face/Pic.bch.lz: intact", out.getvalue())
        ok, _msgs = M.uninstall(self.ctx)
        self.assertTrue(ok)
        self.assertEqual(snapshot(z), before)

    def test_romfs_checks_and_conflicts(self):
        self.put(self.romfs, "face/Pic.bch.lz", lz.compress(b"original picture" * 8, 0x13))
        a = self.asset_mod("A", "face/pic.bch.lz", b"not compressed", order=10)    # other case too
        r = M.build(self.ctx)
        self.assertTrue(any("not LZ-compressed" in e for e in r.errors), r.errors)
        self.assertEqual(r.paths(), [])
        self.put(a.dir, "romfs/face/pic.bch.lz", lz.compress(b"first", 0x13))
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.paths(), ["face/Pic.bch.lz"], "installed under the game's spelling")
        b = self.asset_mod("B", "face/Pic.bch.lz", lz.compress(b"second", 0x13), order=20)
        r = M.build(self.ctx)
        self.assertTrue(any(e.startswith("conflict: romfs face/Pic.bch.lz") for e in r.errors), r.errors)
        b.meta["override"] = True
        b.save()
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        with open(os.path.join(self.ctx.stage_romfs, "face", "Pic.bch.lz"), "rb") as fh:
            self.assertEqual(lz.decompress(fh.read()), b"second")
        # a whole-file replacement and a text edit of the same archive cannot be combined
        self.asset_mod("Whole", REL, lz.compress(b"x" * 40, 0x13))
        self.text_mod("Rename", header() + "[MPID_Alpha]\nOmega\n")
        r = M.build(self.ctx)
        self.assertTrue(any("replaced as a whole file" in e for e in r.errors), r.errors)
        self.assertEqual(r.files, {})

    def test_romfs_change_makes_the_build_out_of_date(self):
        m = self.asset_mod("Pic", "face/New.bin", b"one")
        self.assertEqual(M.build(self.ctx).errors, [])
        built = M.read_staged(self.ctx)["fingerprint"]
        self.put(m.dir, "romfs/face/New.bin", b"two")
        self.assertNotEqual(M.fingerprint(self.ctx), built)

    def test_add_text_command(self):
        m = M.new_mod(self.ctx, "T", tables=[])
        path = M.add_text(self.ctx, m, REL.replace("/", "\\") + ".txt")
        self.assertTrue(path.endswith(os.path.join("text", "m", "@E", "Synthetic.bin.lz.txt")))
        with self.assertRaises(M.ModError):
            M.add_text(self.ctx, m, REL)
        with self.assertRaises(M.ModError):
            M.add_text(self.ctx, m, "m/@E/Missing.bin.lz")


class _Crash(BaseException):
    """A simulated crash: not caught by install, like a killed process or a power cut."""


class InstallJournalTests(Scratch):
    """Review 2026-11-11 #1/#2: an install stopped at any step (crash or disk full) is undone
    to the exact earlier bytes; a refused uninstall can be finished with one command. All in
    a scratch Zakuro folder under build/ (never %APPDATA%)."""

    PIC = "face/Pic.bch.lz"

    def setUp(self) -> None:
        super().setUp()
        self.z = os.path.join(self.tmp, "zakuro")
        os.makedirs(self.z)
        self.ctx = M.Ctx(mods_dir=os.path.join(self.tmp, "mods"), stage_dir=os.path.join(self.tmp, "stage"),
                         zakuro_dir=self.z, quiet=True, romfs=self.romfs)
        self.put(self.romfs, self.PIC, lz.compress(b"original picture" * 8, 0x13))
        m = M.new_mod(self.ctx, "Pic", tables=[])
        self.put(m.dir, "romfs/" + self.PIC, lz.compress(b"replaced picture" * 8, 0x13))
        m = M.new_mod(self.ctx, "Rename", tables=[])
        self.put(m.dir, "text/" + REL + ".txt", (header() + "[MPID_Alpha]\nOmega\n").encode("utf-8"))
        self.assertEqual(M.build(self.ctx).errors, [])
        # the owner's own files: one at a path the mods replace (moved aside), others untouched
        self.put(self.z, "settings.toml", b"x")
        self.put(self.z, f"mods/{M.TITLE_HEX}/romfs/{REL}", b"the owner's previous file")
        self.put(self.z, f"mods/{M.TITLE_HEX}/textures/pack.json", b"{}")
        self.before = snapshot(self.z)
        self.addCleanup(setattr, M, "FAULT", None)

    def reset(self) -> None:
        shutil.rmtree(self.z)
        for (kind, rel), data in sorted(self.before.items(), key=lambda kv: kv[0][1]):
            p = os.path.normpath(os.path.join(self.z, rel))
            if kind == "dir":
                os.makedirs(p, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as fh:
                    fh.write(data)
        self.assertEqual(snapshot(self.z), self.before)

    def steps(self) -> list[str]:
        seen: list[str] = []
        M.FAULT = seen.append
        M.install(self.ctx)
        M.FAULT = None
        self.assertTrue(M.uninstall(self.ctx)[0])
        self.assertEqual(snapshot(self.z), self.before)
        return seen

    @staticmethod
    def fail_at(n: int, exc) -> None:
        calls = [0]

        def fault(step):
            calls[0] += 1
            if calls[0] == n + 1:
                raise exc
        M.FAULT = fault

    def assert_installed(self) -> None:
        for f in M.read_staged(self.ctx)["files"]:
            p = os.path.join(self.ctx.title_dir(), "romfs", *f["path"].split("/"))
            self.assertEqual(M.file_sha(p), f["sha256"])

    def test_every_step_is_reached(self):
        steps = self.steps()
        for s in ("planned", "moved", "copying", "copied", "placed", "recorded", "manifest"):
            self.assertIn(s, steps)
        self.assertEqual(steps.count("moved"), 1)            # only the owner's file is moved aside

    def test_crash_at_every_step_then_uninstall_restores_exact_bytes(self):
        steps = self.steps()
        for n, step in enumerate(steps):
            with self.subTest(n=n, step=step):
                self.reset()
                self.fail_at(n, _Crash(step))
                with self.assertRaises(_Crash):
                    M.install(self.ctx)
                M.FAULT = None
                man = M.read_manifest(self.ctx)
                self.assertTrue(man is None or M.interrupted(man), step)
                ok, msgs = M.uninstall(self.ctx)
                self.assertTrue(ok, msgs)
                self.assertEqual(snapshot(self.z), self.before, f"after a crash at {step} #{n}: {msgs}")

    def test_crash_at_every_step_then_install_recovers_first(self):
        steps = self.steps()
        for n, step in enumerate(steps):
            with self.subTest(n=n, step=step):
                self.reset()
                self.fail_at(n, _Crash(step))
                with self.assertRaises(_Crash):
                    M.install(self.ctx)
                M.FAULT = None
                M.install(self.ctx)                          # finds the unfinished journal, undoes it
                self.assert_installed()
                bak = os.path.join(self.ctx.title_dir(), M.BACKUP, "romfs", *REL.split("/"))
                with open(bak, "rb") as fh:
                    self.assertEqual(fh.read(), b"the owner's previous file")
                self.assertFalse(M.interrupted(M.read_manifest(self.ctx)))
                self.assertTrue(M.uninstall(self.ctx)[0])
                self.assertEqual(snapshot(self.z), self.before)

    def test_disk_full_at_every_step_is_undone_at_once(self):
        steps = self.steps()
        for n, step in enumerate(steps):
            with self.subTest(n=n, step=step):
                self.reset()
                self.fail_at(n, OSError(errno.ENOSPC, "No space left on device"))
                with self.assertRaises(M.ModError) as cm:
                    M.install(self.ctx)
                M.FAULT = None
                self.assertIn("disk full", str(cm.exception))
                self.assertIn("undone", str(cm.exception))
                self.assertEqual(snapshot(self.z), self.before, f"disk full at {step} #{n}")

    def test_old_version_move_without_a_record_is_put_back(self):
        # what the old code could leave: the previous file moved aside, no manifest entry
        tdir = self.ctx.title_dir()
        dst = os.path.join(tdir, "romfs", *REL.split("/"))
        bak = os.path.join(tdir, M.BACKUP, "romfs", *REL.split("/"))
        os.makedirs(os.path.dirname(bak))
        os.replace(dst, bak)
        ok, msgs = M.uninstall(self.ctx)
        self.assertTrue(ok, msgs)
        self.assertEqual(snapshot(self.z), self.before)

    def test_refused_uninstall_then_restore_backups(self):
        M.install(self.ctx)
        dst = os.path.join(self.ctx.title_dir(), "romfs", *REL.split("/"))
        with open(dst, "wb") as fh:
            fh.write(b"changed by hand after install")
        ok, msgs = M.uninstall(self.ctx)
        self.assertFalse(ok)
        text = "\n".join(msgs)
        bak = os.path.join(self.ctx.title_dir(), M.BACKUP, "romfs", *REL.split("/"))
        self.assertIn("your previous file", text)
        self.assertIn(bak, text)
        self.assertIn("would overwrite the changed file", text)
        self.assertIn(M.RESTORE_COMMAND, text)
        # the next install refuses, and says the same thing (not "move it away")
        with self.assertRaises(M.ModError) as cm:
            M.install(self.ctx)
        self.assertIn(M.RESTORE_COMMAND, str(cm.exception))
        self.assertIn("your previous file", str(cm.exception))
        # the command from the message, through the command line
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = M.main(["--zakuro-dir", self.z, "--mods-dir", self.ctx.mods_dir, "--stage-dir",
                         self.ctx.stage_dir, "uninstall", "--restore-backups"])
        self.assertEqual(rc, 0, out.getvalue())
        with open(dst, "rb") as fh:
            self.assertEqual(fh.read(), b"the owner's previous file")
        changed = os.path.join(self.ctx.title_dir(), M.CHANGED, "romfs", *REL.split("/"))
        with open(changed, "rb") as fh:
            self.assertEqual(fh.read(), b"changed by hand after install")
        after = snapshot(self.z)
        extra = {k for k in after if k not in self.before}
        self.assertTrue(extra and all(M.CHANGED in k[1] for k in extra), extra)
        self.assertEqual({k: v for k, v in after.items() if k in self.before}, self.before)
        # and install works again
        M.install(self.ctx)
        self.assert_installed()
        self.assertTrue(M.uninstall(self.ctx)[0])

    def test_unrecorded_backup_with_a_file_in_place_needs_recover(self):
        tdir = self.ctx.title_dir()
        bak = os.path.join(tdir, M.BACKUP, "romfs", *REL.split("/"))
        self.put(tdir, f"{M.BACKUP}/romfs/{REL}", b"older file")
        with self.assertRaises(M.ModError) as cm:
            M.install(self.ctx)
        self.assertIn(bak, str(cm.exception))
        self.assertIn(M.RESTORE_COMMAND, str(cm.exception))
        self.assertIsNone(M.read_manifest(self.ctx), "refused before changing anything")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(M.main(["--zakuro-dir", self.z, "recover"]), 0, out.getvalue())
        with open(os.path.join(tdir, "romfs", *REL.split("/")), "rb") as fh:
            self.assertEqual(fh.read(), b"older file")
        self.assertEqual(M.backup_files(self.ctx), [])

    # --- crashes inside uninstall / recovery (the uninstall is journaled too)
    def collect(self, fn) -> list[str]:
        seen: list[str] = []
        M.FAULT = seen.append
        try:
            fn()
        finally:
            M.FAULT = None
        return seen

    def crash_each(self, prepare, fn, check) -> int:
        """prepare(); then run fn with a crash at each of its steps in turn; then check()."""
        self.reset()
        prepare()
        steps = self.collect(fn)
        self.assertTrue(steps)
        for n, step in enumerate(steps):
            with self.subTest(n=n, step=step):
                self.reset()
                prepare()
                self.fail_at(n, _Crash(step))
                with self.assertRaises(_Crash):
                    fn()
                M.FAULT = None
                check(f"crash at {step} #{n}")
        return len(steps)

    def uninstall_ok(self, why: str, restore_backups: bool = False) -> None:
        ok, msgs = M.uninstall(self.ctx, restore_backups=restore_backups)
        self.assertTrue(ok, f"{why}: {msgs}")
        self.assertNotIn("was changed after", "\n".join(msgs), why)

    def test_crash_at_every_uninstall_step_then_uninstall_restores_exact_bytes(self):
        def check(why):
            self.uninstall_ok(why)
            self.assertEqual(snapshot(self.z), self.before, why)
        n = self.crash_each(lambda: M.install(self.ctx), lambda: M.uninstall(self.ctx), check)
        self.assertGreaterEqual(n, 5)

    def test_crash_at_every_uninstall_step_then_install_recovers(self):
        def check(why):
            M.install(self.ctx)
            self.assert_installed()
            self.uninstall_ok(why)
            self.assertEqual(snapshot(self.z), self.before, why)
        self.crash_each(lambda: M.install(self.ctx), lambda: M.uninstall(self.ctx), check)

    def test_crash_in_uninstall_when_the_previous_file_equals_the_mod_file(self):
        # the owner's previous file has the very bytes the mod installs: a rerun must not
        # delete the restored file as "ours"
        staged = os.path.join(self.ctx.stage_romfs, *REL.split("/"))
        with open(staged, "rb") as fh:
            same = fh.read()
        self.put(self.z, f"mods/{M.TITLE_HEX}/romfs/{REL}", same)
        self.before = snapshot(self.z)

        def check(why):
            self.uninstall_ok(why)
            self.assertEqual(snapshot(self.z), self.before, why)
        self.crash_each(lambda: M.install(self.ctx), lambda: M.uninstall(self.ctx), check)

    def test_crash_at_every_step_of_install_over_an_install(self):
        # the automatic undo at the start of install is the run that crashes
        def check(why):
            self.uninstall_ok(why)
            self.assertEqual(snapshot(self.z), self.before, why)
        n = self.crash_each(lambda: M.install(self.ctx), lambda: M.install(self.ctx), check)
        self.assertGreater(n, len(self.steps()))

    def test_disk_full_then_crash_while_undoing(self):
        # disk full at install step n, then a crash at each step of the undo in its error handler
        steps = self.steps()
        runs = 0
        for n, step in enumerate(steps):
            k = 0
            while True:
                self.reset()
                calls = [0]

                def fault(s, n=n, k=k):
                    calls[0] += 1
                    if calls[0] == n + 1:
                        raise OSError(errno.ENOSPC, "No space left on device")
                    if calls[0] == n + 2 + k:
                        raise _Crash(s)
                M.FAULT = fault
                try:
                    M.install(self.ctx)
                    crashed = False
                except _Crash:
                    crashed = True
                except M.ModError:
                    crashed = False                          # the undo finished: no more steps
                M.FAULT = None
                why = f"disk full at {step} #{n}, crash at undo step {k}"
                self.uninstall_ok(why)
                self.assertEqual(snapshot(self.z), self.before, why)
                if not crashed:
                    break
                runs += 1
                k += 1
        self.assertGreater(runs, 0)

    def test_crash_at_every_step_of_restore_backups(self):
        dst = os.path.join(self.ctx.title_dir(), "romfs", *REL.split("/"))

        def prepare():
            M.install(self.ctx)
            with open(dst, "wb") as fh:
                fh.write(b"changed by hand after install")

        def check(why):
            self.uninstall_ok(why, restore_backups=True)
            with open(dst, "rb") as fh:
                self.assertEqual(fh.read(), b"the owner's previous file", why)
            changed = os.path.join(self.ctx.title_dir(), M.CHANGED, "romfs", *REL.split("/"))
            with open(changed, "rb") as fh:
                self.assertEqual(fh.read(), b"changed by hand after install", why)
            after = snapshot(self.z)
            self.assertEqual({k: v for k, v in after.items() if k in self.before}, self.before, why)
            self.assertTrue(all(M.CHANGED in k[1] for k in after if k not in self.before), why)
        self.crash_each(prepare, lambda: M.uninstall(self.ctx, restore_backups=True), check)

    def test_status_reports_an_interrupted_uninstall(self):
        M.install(self.ctx)
        steps = self.collect(lambda: M.uninstall(self.ctx))
        self.reset()
        M.install(self.ctx)
        self.fail_at(steps.index("un-restored"), _Crash("x"))  # the previous file is back, not yet recorded
        with self.assertRaises(_Crash):
            M.uninstall(self.ctx)
        M.FAULT = None
        loud = M.Ctx(mods_dir=self.ctx.mods_dir, stage_dir=self.ctx.stage_dir, zakuro_dir=self.z, romfs=self.romfs)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            M.cmd_status(loud)
        self.assertIn("DID NOT FINISH", out.getvalue())
        self.uninstall_ok("status")
        self.assertEqual(snapshot(self.z), self.before)

    def test_status_reports_an_interrupted_install(self):
        self.fail_at(3, _Crash("x"))
        with self.assertRaises(_Crash):
            M.install(self.ctx)
        M.FAULT = None
        loud = M.Ctx(mods_dir=self.ctx.mods_dir, stage_dir=self.ctx.stage_dir, zakuro_dir=self.z, romfs=self.romfs)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            M.cmd_status(loud)
        self.assertIn("DID NOT FINISH", out.getvalue())
        self.assertTrue(M.uninstall(self.ctx)[0])
        self.assertEqual(snapshot(self.z), self.before)


@unittest.skipUnless(os.path.isdir(os.path.join(USER_ROMFS, "m")), "needs the user's extracted/romfs/")
class UserFilesTests(unittest.TestCase):
    """Reads the user's extracted archives at run time; writes nothing but scratch files."""

    def test_every_message_archive_round_trips(self):
        # the comparison is made here, on bytes read from disk, not taken from the tool's verdict
        from concurrent.futures import ProcessPoolExecutor
        rels = TX.message_archives(USER_ROMFS, everywhere=True)
        self.assertEqual(len(rels), FATES_ARCHIVES)
        self.assertEqual([r for r in rels if TX.archive_place(r) == "other"], [],
                         "message archives outside m/@E, m/<route>/@E and m/common")
        places = {TX.archive_place(r) for r in rels}
        self.assertEqual(len(places), 5, places)        # shared English, 3 routes, common
        bad = []
        with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as ex:
            for rel, raw, out, problems in ex.map(rebuild_from_dump, [(r, USER_ROMFS) for r in rels],
                                                  chunksize=8):
                if problems or out != raw:
                    bad.append(f"{rel}: {problems[:1] or 'rebuilt bytes differ'}")
        self.assertEqual(bad, [])
        # and the tool's own command agrees
        ok, n, fails = TX.roundtrip_all(USER_ROMFS)
        self.assertEqual((ok, n, fails), (len(rels), len(rels), []))

    def test_fixed_sample_archives_round_trip(self):
        """Round 67 core sample: the same byte comparison as the every-archive test, on SAMPLE_ARCHIVES."""
        rels = set(TX.message_archives(USER_ROMFS, everywhere=True))
        self.assertEqual(len(SAMPLE_ARCHIVES), 40)
        self.assertEqual(len(set(SAMPLE_ARCHIVES)), 40)
        self.assertEqual([r for r in SAMPLE_ARCHIVES if r not in rels], [], "sample archives missing")
        self.assertEqual(len({TX.archive_place(r) for r in SAMPLE_ARCHIVES}), 5)
        bad = []
        for r in SAMPLE_ARCHIVES:
            rel, raw, out, problems = rebuild_from_dump((r, USER_ROMFS))
            if problems or out != raw:
                bad.append(f"{rel}: {problems[:1] or 'rebuilt bytes differ'}")
        self.assertEqual(bad, [])

    def test_renamed_unit_name_changes_only_expected_bytes(self):
        TX.clear_cache()
        ctx = M.Ctx(quiet=True)
        lab = M.example_name_label(ctx)          # a playable unit's name label, found at run time
        van = TX.archive(M.NAME_ARCHIVE)
        old = van.text_of[lab]
        same = "X" * len(old)
        new = lz.decompress(TX.build_archive(van, {lab: same}))
        self.assertEqual(len(new), len(van.dec))
        start = van.offset[lab]
        diff = [i for i, (a, b) in enumerate(zip(new, van.dec)) if a != b]
        self.assertTrue(diff)
        self.assertTrue(all(start <= i < start + 2 * len(old) for i in diff))
        longer = old + " II"
        _n, entries, _b = msg.parse(lz.decompress(TX.build_archive(van, {lab: longer})))
        changed = [e[0] for e, v in zip(entries, van.entries) if e != v]
        self.assertEqual(changed, [lab])
        self.assertEqual([e[0] for e in entries], [e[0] for e in van.entries])

    def test_new_item_demo_builds_installs_and_uninstalls(self):
        # ExampleItem: a new Item row, its two new messages and a Chapter 1 starting item;
        # built, the staged files decompressed and parsed here, installed into a scratch
        # Zakuro folder under build/ and uninstalled back to the exact earlier state
        TX.clear_cache()
        if M.tables_status():
            self.skipTest(M.tables_status())
        os.makedirs(SCRATCH_PARENT, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix="item-", dir=SCRATCH_PARENT)
        try:
            z = os.path.join(tmp, "zakuro")
            os.makedirs(z)
            ctx = M.Ctx(mods_dir=os.path.join(tmp, "mods"), stage_dir=os.path.join(tmp, "stage"),
                        zakuro_dir=z, quiet=True)
            before = snapshot(z)
            _m, _what = M.make_item_example(ctx)
            r = M.build(ctx)
            self.assertEqual(r.errors, [])
            gamedata = M.reg()["Item"].files()[0]
            dispos = M.ITEM_EXAMPLE_DISPOS
            self.assertEqual(r.paths(), sorted([gamedata, dispos, M.NAME_ARCHIVE]))
            T = M.T
            stage = os.path.join(ctx.stage_romfs, *gamedata.split("/"))
            with open(stage, "rb") as fh:
                raw = fh.read()
            orig = T.container(gamedata)
            self.assertEqual(raw[0], orig.raw[0])                      # same LZ format
            nc = T.Container(gamedata, raw)
            t = M.reg()["Item"]
            s0, n0 = T.locate(t, orig)
            s1, n1 = T.locate(t, nc)
            self.assertEqual(n1, n0 + 1)
            lab = M.ITEM_EXAMPLE_LABEL.encode()
            off = nc.label_off[lab]                                    # the new row resolves by its ID
            self.assertEqual(off, s1 + n0 * t.size)
            cd = T.Codec(M.reg(), "Item")
            head = cd.columns()
            row = dict(zip(head, cd.decode(nc, n0, off, lab)))
            base = dict(zip(head, M.example_item_base(ctx)))
            self.assertEqual(row["iid"], M.ITEM_EXAMPLE_LABEL)
            self.assertEqual(int(row["item_number"]), n0)
            self.assertEqual(int(row["might"]), int(base["might"]) + M.ITEM_EXAMPLE_MIGHT)
            same = [h for h in head if h not in ("index", "label", "iid", "item_number", "might",
                                                 "miid_name", "miid_help")]
            self.assertEqual({h: row[h] for h in same}, {h: base[h] for h in same})
            # its name and help text exist in the staged name archive
            with open(os.path.join(ctx.stage_romfs, *M.NAME_ARCHIVE.split("/")), "rb") as fh:
                _n, entries, _b = msg.parse(lz.decompress(fh.read()))
            texts = {e[0]: e[1] for e in entries if not e[2]}
            self.assertEqual(texts[row["miid_name"].encode()], M.ITEM_EXAMPLE_TEXT)
            self.assertEqual(texts[row["miid_help"].encode()], M.ITEM_EXAMPLE_HELP)
            van = TX.archive(M.NAME_ARCHIVE)
            self.assertEqual([e for e in entries if e[0] in van.index], van.entries)
            # the Chapter 1 unit carries it
            with open(os.path.join(ctx.stage_romfs, *dispos.split("/")), "rb") as fh:
                dc = T.Container(dispos, fh.read())
            du = M.reg()["DisposUnit"]
            ds, dn = T.locate(du, dc)
            dcols = T.Codec(M.reg(), "DisposUnit").columns()
            units = [dict(zip(dcols, T.Codec(M.reg(), "DisposUnit").decode(dc, i, ds + i * du.size, b"")))
                     for i in range(dn)]
            self.assertTrue(any(M.ITEM_EXAMPLE_LABEL in [u[f"item_{k}"] for k in range(1, 6)] for u in units))
            # install, then uninstall restores the folder exactly
            M.install(ctx)
            with open(os.path.join(ctx.title_dir(), "romfs", *gamedata.split("/")), "rb") as fh:
                self.assertEqual(fh.read(), raw)
            ok, _msgs = M.uninstall(ctx)
            self.assertTrue(ok)
            self.assertEqual(snapshot(z), before)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            with contextlib.suppress(OSError):
                os.rmdir(SCRATCH_PARENT)

    def test_new_row_refusals(self):
        # a person row (the game's 256-person bit set), an item without its name text and a
        # placement naming an item nobody adds are refused, naming the reason
        TX.clear_cache()
        if M.tables_status():
            self.skipTest(M.tables_status())
        os.makedirs(SCRATCH_PARENT, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix="refuse-", dir=SCRATCH_PARENT)
        try:
            ctx = M.Ctx(mods_dir=os.path.join(tmp, "mods"), stage_dir=os.path.join(tmp, "stage"),
                        zakuro_dir=os.path.join(tmp, "zakuro"), quiet=True)
            head, rows = M.vanilla()["Person"]
            new = list(rows[1])
            new[0], new[1] = str(len(rows)), "PID_MODTEST"
            new[head.index("pid")] = "PID_MODTEST"
            m = M.new_mod(ctx, "NewPerson", tables=[])
            M.write_table_csv(os.path.join(m.dir, "tables", "Person.csv"), head, [new])
            r = M.compute(ctx)
            self.assertTrue(any("256" in e for e in r.errors), r.errors)
            m.meta["enabled"] = False
            m.save()
            item, _what = M.make_item_example(ctx)
            shutil.rmtree(os.path.join(item.dir, "text"))
            r = M.compute(ctx)
            self.assertTrue(any("which the game does not have" in e for e in r.errors), r.errors)
            os.remove(os.path.join(item.dir, "tables", "Item.csv"))
            r = M.compute(ctx)
            self.assertTrue(any("is not a Item record" in e for e in r.errors), r.errors)
            self.assertEqual(r.files, {})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            with contextlib.suppress(OSError):
                os.rmdir(SCRATCH_PARENT)

    def test_rename_demo_installs_into_scratch_zakuro_and_uninstalls(self):
        TX.clear_cache()
        os.makedirs(SCRATCH_PARENT, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix="user-", dir=SCRATCH_PARENT)
        try:
            z = os.path.join(tmp, "zakuro")
            os.makedirs(os.path.join(z, "mods", "00040000000A0500", "romfs"))   # another game's mods
            with open(os.path.join(z, "settings.toml"), "wb") as fh:
                fh.write(b"x")
            ctx = M.Ctx(mods_dir=os.path.join(tmp, "mods"), stage_dir=os.path.join(tmp, "stage"),
                        zakuro_dir=z, quiet=True)
            self.assertNotEqual(os.path.abspath(z), os.path.abspath(M.Ctx().zakuro_dir))
            before = snapshot(z)
            _m, _what = M.make_text_example(ctx)
            r = M.build(ctx)
            self.assertEqual(r.errors, [])
            self.assertEqual(r.paths(), [M.NAME_ARCHIVE])
            M.install(ctx)
            tdir = ctx.title_dir()
            self.assertEqual(os.path.basename(tdir), "0004000000179800")
            with open(os.path.join(tdir, "romfs", *M.NAME_ARCHIVE.split("/")), "rb") as fh:
                placed = fh.read()
            lab = M.example_name_label(ctx)
            van = TX.archive(M.NAME_ARCHIVE)
            _n, entries, _b = msg.parse(lz.decompress(placed))
            self.assertEqual(placed[0], 0x13)
            self.assertEqual(dict((e[0], e[1]) for e in entries)[lab], M.TEXT_EXAMPLE_NEW)
            self.assertEqual([e[0] for e, v in zip(entries, van.entries) if e != v], [lab])
            self.assertTrue(os.path.isfile(os.path.join(tdir, M.MANIFEST)))
            ok, _msgs = M.uninstall(ctx)
            self.assertTrue(ok)
            self.assertEqual(snapshot(z), before)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            with contextlib.suppress(OSError):
                os.rmdir(SCRATCH_PARENT)


HAVE_MAPS = os.path.isdir(os.path.join(USER_ROMFS, "GameData", "Dispos"))
HAVE_FACES = os.path.isfile(os.path.join(USER_ROMFS, "face", "FaceData.bin.lz"))
HAVE_CASTLE = os.path.isfile(os.path.join(USER_ROMFS, "GameData", "Castle", "DiningData.bin.lz"))


class _UserScratch(unittest.TestCase):
    """A scratch mods workspace, stage folder and Zakuro data folder under build/."""

    def setUp(self) -> None:
        TX.clear_cache()
        if M.tables_status():
            self.skipTest(M.tables_status())
        os.makedirs(SCRATCH_PARENT, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="mapface-", dir=SCRATCH_PARENT)
        self.z = os.path.join(self.tmp, "zakuro")
        os.makedirs(self.z)
        self.ctx = M.Ctx(mods_dir=os.path.join(self.tmp, "mods"), stage_dir=os.path.join(self.tmp, "stage"),
                         zakuro_dir=self.z, quiet=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)
        with contextlib.suppress(OSError):
            os.rmdir(SCRATCH_PARENT)

    def staged(self, rel: str) -> bytes:
        with open(os.path.join(self.ctx.stage_romfs, *rel.split("/")), "rb") as fh:
            return fh.read()

    def install_uninstall(self, rels: list[str]) -> None:
        """install places exactly the staged bytes; uninstall gives back the folder as it was"""
        before = snapshot(self.z)
        M.install(self.ctx)
        for rel in rels:
            with open(os.path.join(self.ctx.title_dir(), "romfs", *rel.split("/")), "rb") as fh:
                self.assertEqual(fh.read(), self.staged(rel), rel)
        ok, _msgs = M.uninstall(self.ctx)
        self.assertTrue(ok)
        self.assertEqual(snapshot(self.z), before)


@unittest.skipUnless(HAVE_MAPS, "needs the user's extracted/romfs/ (map files)")
class MapModTests(_UserScratch):
    """maps/<MAP>/ folders (tools/mods/mapface.py over tools/maps/maplib.py)."""

    def units(self, m):
        ML = M.MF.maplib()
        return ML.read_csv(os.path.join(m.dir, "maps", M.MAP_EXAMPLE_MAP, "units.csv"))

    def put_units(self, m, head, rows):
        M.MF.maplib().write_csv(os.path.join(m.dir, "maps", M.MAP_EXAMPLE_MAP, "units.csv"), head, rows)

    def test_map_demo_builds_installs_and_uninstalls(self):
        ML = M.MF.maplib()
        m, _what = M.make_map_example(self.ctx)
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        rel = ML.packages()[M.MAP_EXAMPLE_MAP]["dispos"]
        self.assertEqual(r.paths(), [rel])                 # the terrain is unchanged: not staged
        raw = self.staged(rel)
        orig = ML.T.container(rel)
        self.assertEqual(raw[0], orig.raw[0])              # same LZ format
        # read back here: exactly one unit differs, and only in its position columns
        new_rows = ML.unit_rows(ML.Dispos(rel, ML.T.Container(rel, raw)))
        old_rows = ML.unit_rows(ML.Dispos(rel))
        cols = ML.unit_columns()
        self.assertEqual(len(new_rows), len(old_rows))
        diff = [(i, c) for i, (a, b) in enumerate(zip(old_rows, new_rows))
                for c, x, y in zip(cols, a, b) if x != y]
        self.assertTrue(diff)
        self.assertEqual(len({i for i, _c in diff}), 1, diff)
        self.assertTrue({c for _i, c in diff} <= {"x", "y", "start_x", "start_y"}, diff)
        self.assertEqual(len(lz.decompress(raw)), len(lz.decompress(orig.raw)))
        st = M.read_staged(self.ctx)
        self.assertEqual([(f["kind"], f["mod"]) for f in st["files"]], [("map", m.name)])
        self.install_uninstall([rel])

    def test_map_checks_ids_and_conflicts(self):
        ML = M.MF.maplib()
        m, _what = M.make_map_example(self.ctx)
        head, rows = self.units(m)
        h = {c: i for i, c in enumerate(head)}
        base = [list(r) for r in rows]
        # off the playable area: refused, nothing staged
        bad = [list(r) for r in base]
        t = ML.Terrain(ML.packages()[M.MAP_EXAMPLE_MAP]["terrain_ref"])
        k = next(i for i, r in enumerate(bad) if r[h["side"]] == "enemy" and r[h["normal"]] == "1")
        bad[k][h["x"]] = bad[k][h["start_x"]] = str(t.play[2])
        self.put_units(m, head, bad)
        r = M.compute(self.ctx)
        self.assertTrue(any("playable area" in e for e in r.errors), r.errors)
        self.assertEqual(r.files, {})
        # an item nobody has: refused
        bad = [list(r) for r in base]
        bad[k][h["item_1"]] = "IID_NO_SUCH_ITEM_MODTEST"
        self.put_units(m, head, bad)
        r = M.compute(self.ctx)
        self.assertTrue(any("IID_NO_SUCH_ITEM_MODTEST" in e for e in r.errors), r.errors)
        # an item another enabled mod adds in its tables/: accepted
        M.make_item_example(self.ctx)
        bad[k][h["item_1"]] = M.ITEM_EXAMPLE_LABEL
        self.put_units(m, head, bad)
        r = M.compute(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertIn(ML.packages()[M.MAP_EXAMPLE_MAP]["dispos"], r.files)
        item = M.find_mod(self.ctx, M.ITEM_EXAMPLE_NAME)
        item.meta["enabled"] = False
        item.save()
        self.put_units(m, head, base)
        # the same map file edited as a spreadsheet too: refused
        rel = ML.packages()[M.MAP_EXAMPLE_MAP]["dispos"]
        dh, drows = M.vanilla()["DisposUnit"]
        row = next(x for x in drows if x[0] == rel)
        tm = M.new_mod(self.ctx, "TableOnMap", tables=[])
        M.write_table_csv(os.path.join(tm.dir, "tables", "DisposUnit.csv"), ["file", "index", "label", "level"],
                          [[row[0], row[1], row[2], str(int(row[dh.index("level")]) % 40 + 1)]])
        r = M.compute(self.ctx)
        self.assertTrue(any("edited both as a map" in e for e in r.errors), r.errors)
        tm.meta["enabled"] = False
        tm.save()
        # two mods editing the same map differently: a conflict, unless the later one overrides
        m2 = M.new_mod(self.ctx, "SecondMap", tables=[])
        shutil.copytree(os.path.join(m.dir, "maps"), os.path.join(m2.dir, "maps"))
        other = [list(r) for r in base]
        other[k][h["level"]] = str(int(other[k][h["level"]]) % 40 + 1)
        ML.write_csv(os.path.join(m2.dir, "maps", M.MAP_EXAMPLE_MAP, "units.csv"), head, other)
        r = M.compute(self.ctx)
        self.assertTrue(any(e.startswith("conflict: map") for e in r.errors), r.errors)
        m2.meta["override"] = True
        m2.save()
        r = M.compute(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.maps[rel][1], "SecondMap")
        # a folder that is not a map name
        os.makedirs(os.path.join(m.dir, "maps", "NOPE999"))
        with open(os.path.join(m.dir, "maps", "NOPE999", "units.csv"), "w") as fh:
            fh.write("group\n")
        r = M.compute(self.ctx)
        self.assertTrue(any("no map called NOPE999" in e for e in r.errors), r.errors)

    def test_unchanged_map_package_stages_nothing(self):
        m = M.new_mod(self.ctx, "PlainMap", tables=[])
        M.add_map(self.ctx, m, M.MAP_EXAMPLE_MAP)
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.paths(), [])


@unittest.skipUnless(HAVE_FACES, "needs the user's extracted/romfs/ (portraits)")
class FaceModTests(_UserScratch):
    """faces/<NAME>/ folders (tools/mods/mapface.py over tools/assets/portrait.py)."""

    def test_face_demo_builds_installs_and_uninstalls(self):
        P = M.MF.portrait()
        m, _what = M.make_face_example(self.ctx)
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertEqual(len(r.paths()), 1)
        rel = r.paths()[0]
        self.assertTrue(rel.startswith("face/face/") and rel.endswith("_st.arc"), rel)
        raw = self.staged(rel)
        with open(os.path.join(USER_ROMFS, *rel.split("/")), "rb") as fh:
            orig = fh.read()
        new_m, _l = P.arc.parse_full(raw)
        old_m, _l = P.arc.parse_full(orig)
        self.assertEqual([x["name"] for x in new_m], [x["name"] for x in old_m])
        changed = [i for i, (a, b) in enumerate(zip(new_m, old_m)) if a["data"] != b["data"]]
        self.assertEqual(len(changed), 1)
        self.assertTrue(P._s(new_m[changed[0]]["name"]).startswith(M.FACE_EXAMPLE_MEMBER))

        def mean_rgb(blob):
            d, _w = P.bch.unwrap(blob)
            bb = P.bch.Bch(d)
            t = bb.textures()[0]
            px = P.bch.decode_level(t["format"], t["width"], t["height"], bb.levels(t)[0])
            vis = [px[i:i + 3] for i in range(0, len(px), 4) if px[i + 3] > 128]
            return t["width"], t["height"], [sum(p[c] for p in vis) / len(vis) for c in range(3)]

        w0, h0, old_rgb = mean_rgb(old_m[changed[0]]["data"])
        w1, h1, new_rgb = mean_rgb(new_m[changed[0]]["data"])
        self.assertEqual((w0, h0), (w1, h1))
        self.assertLess(new_rgb[0], old_rgb[0] - 20)          # less red
        self.assertGreater(new_rgb[2], old_rgb[2] + 20)       # more blue
        st = M.read_staged(self.ctx)
        self.assertEqual([(f["kind"], f["mod"]) for f in st["files"]], [("face", m.name)])
        self.install_uninstall([rel])

    def test_face_resize_needs_the_flag(self):
        # the bust package (small pictures): every expression halved. Refused without
        # "allow_face_resize"; with it the build stages the arc and the pictures are smaller.
        P = M.MF.portrait()
        lab = M.example_name_label(self.ctx).decode("cp932")
        rec = next(x for x in M.face_records(self.ctx, lab) if x["mpid"] == lab and x["package"].endswith("_bu"))
        m = M.new_mod(self.ctx, "FaceResize", tables=[])
        src = f"face/face/{rec['package']}.arc"
        d = M.add_face(self.ctx, m, "bu", [rec], [src])
        with open(os.path.join(d, "portrait.json"), encoding="utf-8") as fh:
            man = json.load(fh)
        exprs = [x for x in man["layers"] if x["role"] == "expression"]
        for ly in exprs:
            P._scale_png(os.path.join(d, *ly["png"].split("/")), 0)
        r = M.compute(self.ctx)
        self.assertTrue(any("allow_face_resize" in e for e in r.errors), r.errors)
        self.assertEqual(r.files, {})
        # one expression left at the old size: refused even with the flag
        m.meta["allow_face_resize"] = True
        m.save()
        P._scale_png(os.path.join(d, *exprs[0]["png"].split("/")), 2)
        r = M.compute(self.ctx)
        self.assertTrue(any("same size" in e for e in r.errors), r.errors)
        P._scale_png(os.path.join(d, *exprs[0]["png"].split("/")), 0)
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertTrue(any("bigger or smaller" in w for w in r.warnings), r.warnings)
        members, _l = P.arc.parse_full(self.staged(src))
        names = {x["member"] for x in exprs}
        for mem in members:
            if P._s(mem["name"]) in names:
                d2, _w = P.bch.unwrap(mem["data"])
                t = P.bch.Bch(d2).textures()[0]
                want = next(x for x in exprs if x["member"] == P._s(mem["name"]))
                self.assertEqual((t["width"], t["height"]), (want["width"] // 2, want["height"] // 2))

    def test_unchanged_face_folder_stages_nothing(self):
        lab = M.example_name_label(self.ctx).decode("cp932")
        recs = [x for x in M.face_records(self.ctx, lab) if x["mpid"] == lab]
        m = M.new_mod(self.ctx, "PlainFace", tables=[])
        M.add_face(self.ctx, m, "plain", recs[:1], [f"face/face/{recs[0]['package']}.arc"])
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.paths(), [])


@unittest.skipUnless(HAVE_CASTLE, "needs the user's extracted/romfs/ (castle files)")
class CastleModTests(_UserScratch):
    """castle/<File>/<Sheet>.csv folders (tools/mods/castlemod.py over tools/castle)."""

    DINING = "GameData/Castle/DiningData.bin.lz"

    def setUp(self) -> None:
        super().setUp()
        if M.CM.status():
            self.skipTest(M.CM.status())
        self.L = M.CM.castle().L

    def sheet(self, m, folder, key):
        p = os.path.join(m.dir, "castle", folder, f"{key}.csv")
        return p, *self.L.read_csv(p)

    def errors_of(self):
        r = M.compute(self.ctx)
        self.assertEqual(r.files, {})
        return " | ".join(r.errors)

    def test_castle_demo_builds_installs_and_uninstalls(self):
        m, _what = M.make_castle_example(self.ctx)
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.paths(), [self.DINING])
        raw = self.staged(self.DINING)
        orig = self.L.container(self.DINING)
        self.assertEqual(raw[0], orig.raw[0])                    # same LZ format
        new, old = lz.decompress(raw), lz.decompress(orig.raw)
        self.assertEqual(len(new), len(old))
        diff = [i for i in range(len(new)) if new[i] != old[i]]
        self.assertEqual(len(diff), 1, diff)                     # one signed byte
        self.assertEqual(new[diff[0]] - old[diff[0]], M.CASTLE_EXAMPLE_DELTA)
        # decoded here: only that dish's str cell differs
        got = M.CM.vanilla(self.DINING, self.L.T.Container(self.DINING, raw))[0]
        want = M.CM.vanilla(self.DINING)[0]
        self.assertEqual(got["DiningData_CookTitle"], want["DiningData_CookTitle"])
        h, grows = got[M.CASTLE_EXAMPLE_SHEET]
        _h, wrows = want[M.CASTLE_EXAMPLE_SHEET]
        cells = [(i, h[j]) for i, (a, b) in enumerate(zip(grows, wrows)) for j in range(len(h)) if a[j] != b[j]]
        i = M.CM.example_dish(wrows, h, M.CASTLE_EXAMPLE_INGREDIENT)
        self.assertEqual(cells, [(i, M.CASTLE_EXAMPLE_COL)])
        st = M.read_staged(self.ctx)
        self.assertEqual([(f["kind"], f["mod"]) for f in st["files"]], [("castle", m.name)])
        self.install_uninstall([self.DINING])

    def test_added_dish_decodes_back(self):
        m = M.new_mod(self.ctx, "NewDish", tables=[])
        M.add_castle(self.ctx, m, "DiningData", ["DiningData_Dish"])
        p, head, rows = self.sheet(m, "DiningData", "DiningData_Dish")
        h = {c: i for i, c in enumerate(head)}
        row = list(rows[0])
        row[0], row[1], row[h["name"]] = str(len(rows)), "ZZ_MODTEST_DISH", "ZZ_MODTEST_DISH"
        row[h["spd"]] = "2"
        self.L.write_csv(p, head, rows + [row])
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        got = M.CM.vanilla(self.DINING, self.L.T.Container(self.DINING, self.staged(self.DINING)))[0]
        grows = got["DiningData_Dish"][1]
        self.assertEqual(len(grows), len(rows) + 1)
        self.assertEqual(grows[:-1], rows)
        self.assertEqual(grows[-1][1], "ZZ_MODTEST_DISH")
        self.assertEqual(grows[-1][h["spd"]], "2")
        # the same label twice is refused by the castle builder
        self.L.write_csv(p, head, rows + [row, [str(len(rows) + 1)] + row[1:]])
        self.assertIn("already used", self.errors_of())

    def test_refusals(self):
        m = M.new_mod(self.ctx, "BadCastle", tables=[])
        M.add_castle(self.ctx, m, "AcceShop")
        p, head, rows = self.sheet(m, "AcceShop", "AcceShop")
        # a row added to AcceShop (fixed 256-entry save array)
        self.L.write_csv(p, head, rows + [[str(len(rows)), "ACCE_MODTEST"] + rows[1][2:]])
        self.assertIn("refused", self.errors_of())
        # a removed row
        self.L.write_csv(p, head, rows[:-1])
        self.assertIn("cannot be removed", self.errors_of())
        # a renamed label
        bad = [list(x) for x in rows]
        bad[1][1] = "ACCE_MODTEST"
        self.L.write_csv(p, head, bad)
        self.assertIn("renamed", self.errors_of())
        # changed columns
        self.L.write_csv(p, head[:-1] + ["something"], rows)
        self.assertIn("columns", self.errors_of())
        self.L.write_csv(p, head, rows)
        # a value that does not fit its byte
        bad = [list(x) for x in rows]
        bad[1][head.index("damage_up")] = "300"
        self.L.write_csv(p, head, bad)
        self.assertTrue(self.errors_of())
        self.L.write_csv(p, head, rows)
        # an unknown file in the folder, an unknown folder
        with open(os.path.join(m.dir, "castle", "AcceShop", "Nope.csv"), "w", encoding="utf-8") as fh:
            fh.write("a,b\n")
        self.assertIn("not a sheet", self.errors_of())
        os.remove(os.path.join(m.dir, "castle", "AcceShop", "Nope.csv"))
        os.makedirs(os.path.join(m.dir, "castle", "NoSuchFile"))
        with open(os.path.join(m.dir, "castle", "NoSuchFile", "x.csv"), "w", encoding="utf-8") as fh:
            fh.write("a,b\n")
        self.assertIn("no castle file called NoSuchFile", self.errors_of())
        shutil.rmtree(os.path.join(m.dir, "castle", "NoSuchFile"))
        # a list item added (JobIntro units)
        M.add_castle(self.ctx, m, "JobIntro")
        lp = os.path.join(m.dir, "castle", "JobIntro", "JobIntro_Group__JobIntro_Unit.csv")
        lh, lrows = self.L.read_csv(lp)
        self.L.write_csv(lp, lh, lrows + [list(lrows[-1])])
        self.assertIn("not added or removed", self.errors_of())
        shutil.rmtree(os.path.join(m.dir, "castle", "JobIntro"))
        # unedited: nothing staged
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.paths(), [])
        # the castle file also replaced as a whole file
        bad = [list(x) for x in rows]
        bad[1][head.index("damage_up")] = str(int(rows[1][head.index("damage_up")]) + 1)
        self.L.write_csv(p, head, bad)
        whole = os.path.join(m.dir, "romfs", "GameData", "AcceShop.bin.lz")
        os.makedirs(os.path.dirname(whole))
        with open(whole, "wb") as fh:
            fh.write(self.L.container(self.DINING).raw)       # any other valid LZ file
        self.assertIn("conflict", self.errors_of())

    def test_two_mods_same_cell(self):
        a = M.new_mod(self.ctx, "CastleA", tables=[])
        b = M.new_mod(self.ctx, "CastleB", tables=[])
        b.meta["order"] = 200
        b.save()
        for m, v in ((a, "5"), (b, "6")):
            M.add_castle(self.ctx, m, "AcceShop")
            p, head, rows = self.sheet(m, "AcceShop", "AcceShop")
            rows[1][head.index("material_count")] = v
            self.L.write_csv(p, head, rows)
        self.assertIn("conflict", self.errors_of())
        b.meta["override"] = True
        b.save()
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        got = M.CM.vanilla("GameData/AcceShop.bin.lz",
                           self.L.T.Container("GameData/AcceShop.bin.lz", self.staged("GameData/AcceShop.bin.lz")))
        self.assertEqual(got[0]["AcceShop"][1][1][head.index("material_count")], "6")
        # the same value in both mods is no conflict; 0x5 is the same number as 5
        b.meta["override"] = False
        b.save()
        p, head, rows = self.sheet(b, "AcceShop", "AcceShop")
        rows[1][head.index("material_count")] = "0x5"
        self.L.write_csv(p, head, rows)
        self.assertEqual(M.compute(self.ctx).errors, [])

    def test_unchanged_castle_folder_stages_nothing(self):
        m = M.new_mod(self.ctx, "PlainCastle", tables=[])
        for name in M.CM.file_folders():
            M.add_castle(self.ctx, m, name)
        r = M.build(self.ctx)
        self.assertEqual(r.errors, [])
        self.assertEqual(r.paths(), [])


if __name__ == "__main__":
    unittest.main()
