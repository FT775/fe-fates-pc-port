"""Offline checks for tools/mods/mods.py (run: python tools/mods/mods.py selftest).

Everything happens in a temporary folder under build/mods-selftest/ (deleted afterwards):
scratch mods workspaces, scratch stage folders and fake Zakuro data folders. The real
mods/, build/mods/ and %APPDATA%\\zakuro are never touched. Needs the user's
extracted/romfs/ (the original text and files are read from it).

Covers:
  text mods (real archives): sample round trips from every place (shared English, each
      route, common), a full dump builds nothing, the ExampleText rename, route and common
      archive edits, broken text files, install/uninstall
  install safety: existing files backed up and restored, fresh folder left without a
      trace, hand-edited files never deleted, missing Zakuro folder, lower-case title folder,
      an install crashed or out of disk space at every step undone exactly,
      a refused uninstall finished by uninstall --restore-backups
  romfs (whole-file) mods: install as-is with manifest, game spelling of a path, .lz
      checks, same-bytes / junk / new files, conflicts and override, romfs + text clash
  table mods: on a synthetic table (an invented layout over an invented container in a
      fake RomFS, so the mods.py table path is tested against the tools/tables interface
      whatever layouts config/tables/ holds); "table mods off" handling; and, when real
      layouts exist in config/tables/, an unedited mod and the Example demo
Prints one PASS/FAIL line per check (SKIP lines are not counted) and
"mods selftest: N/M checks passed".
"""
from __future__ import annotations

import os
import shutil
import struct
import tempfile
import traceback


def run(M) -> int:
    TX = M.TX
    lz = M.lz
    results: list[tuple[str, bool, str]] = []
    scratch = os.path.join(M.ROOT, "build", "mods-selftest")      # scratch, deleted afterwards
    os.makedirs(scratch, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="run-", dir=scratch)
    ROMFS = M.ROMFS
    NAMES = M.NAME_ARCHIVE

    def ctx(name: str, romfs: str | None = None):
        base = os.path.join(tmp, name)
        os.makedirs(os.path.join(base, "zakuro"))
        return M.Ctx(mods_dir=os.path.join(base, "mods"), stage_dir=os.path.join(base, "stage"),
                     zakuro_dir=os.path.join(base, "zakuro"), quiet=True, romfs=romfs)

    def check(name: str, fn) -> None:
        try:
            ok, detail = fn()
        except Exception as e:  # a crash is a failure, with its last frame
            ok, detail = False, f"{type(e).__name__}: {e} @ {traceback.extract_tb(e.__traceback__)[-1].lineno}"
        results.append((name, ok, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))

    def skip(name: str, why: str) -> None:
        print(f"  SKIP  {name}  ({why})")

    def snapshot(root):
        out = {}
        for d, _dirs, files in os.walk(root):
            rel = os.path.relpath(d, root)
            out[("dir", rel)] = None
            for f in files:
                with open(os.path.join(d, f), "rb") as fh:
                    out[("file", os.path.join(rel, f))] = fh.read()
        return out

    def put(root, rel, data):
        p = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)
        return p

    def read(path):
        with open(path, "rb") as fh:
            return fh.read()

    def text_mod(c, name, rel, edits, order=None, override=False):
        """A text-only mod giving each label in edits {label bytes: text} new text."""
        m = M.new_mod(c, name, tables=[])
        van = TX.archive(rel, c.romfs)
        lines = [TX.HEADER, "#name " + TX.msg.isbin.quote(van.name)]
        for lab, v in edits.items():
            lines += [f"[{lab.decode('cp932')}]", TX.msg.escape(v)]
        put(m.dir, f"text/{rel}.txt", ("\n".join(lines) + "\n").encode("utf-8"))
        m.meta["override"] = override
        if order is not None:
            m.meta["order"] = order
        m.save()
        return m

    all_rels = TX.message_archives(ROMFS)
    by_place: dict[str, list[str]] = {}
    for r in all_rels:
        by_place.setdefault(TX.archive_place(r), []).append(r)
    route_rel = next(r for p, rs in sorted(by_place.items()) if "route only" in p for r in rs)
    common_rel = by_place.get("common (no language folder)", [None])[0]

    def first_own_label(rel):
        van = TX.archive(rel)
        return next(lab for lab, v, a in van.entries if not a and v)

    try:
        # ================================================================ text
        def t_text_sample():
            pick = sorted({rs[k] for rs in by_place.values() for k in (0, len(rs) // 2, len(rs) - 1)} | {NAMES})
            bad = []
            for r in pick:                        # compare bytes here, not the tool's own verdict
                raw = read(os.path.join(ROMFS, *r.split("/")))
                van = TX.Archive(r, raw)
                name, items, errs = TX.parse_mod_text(van.dump().encode("utf-8"), r)
                ch, errs2, _w, _n = TX.diff_text(van, name, items, r)
                if errs or errs2 or ch or TX.build_archive(van, ch) != raw or not TX.roundtrip_one((r, ROMFS))[1]:
                    bad.append(r)
            places = len(by_place)
            return not bad and places >= 5, f"{len(pick) - len(bad)}/{len(pick)} archives from {places} places " \
                "byte-identical" + (f"; failed {bad[:3]}" if bad else "")
        check("text: archives from every place (shared, A/B/C routes, common) round-trip byte for byte",
              t_text_sample)

        def t_text_full_dump():
            c = ctx("text-full")
            m = M.new_mod(c, "Words", text=[NAMES])
            r = M.build(c)
            return (not r.errors and not r.paths() and not m.tables() and len(m.texts()) == 1), \
                f"{len(r.paths())} file(s) staged, errors {r.errors[:2]}"
        check("text: an unedited full text dump stages nothing", t_text_full_dump)

        def t_text_example():
            c = ctx("text-example")
            _m, _what = M.make_text_example(c)
            r = M.build(c)
            if r.errors or r.paths() != [NAMES]:
                return False, f"staged {r.paths()}, errors {r.errors[:2]}"
            van = TX.archive(NAMES)
            out = r.files[NAMES]
            _n, got, _b = TX.msg.parse(lz.decompress(out))
            changed = [e[0] for e, v in zip(got, van.entries) if e != v]
            lab = M.example_name_label(c)
            ok = (changed == [lab] and len(got) == len(van.entries) and out[0] == van.raw[0] == 0x13
                  and dict((e[0], e[1]) for e in got)[lab] == M.TEXT_EXAMPLE_NEW)
            return ok, f"labels changed: {len(changed)}, LZ13 kept: {out[0] == van.raw[0] == 0x13}"
        check("text: the ExampleText mod changes exactly one name label, still LZ13", t_text_example)

        def t_text_route_common():
            c = ctx("text-route")
            rels = [route_rel] + ([common_rel] if common_rel else [])
            want = {}
            for k, rel in enumerate(rels):
                lab = first_own_label(rel)
                want[rel] = lab
                text_mod(c, f"R{k}", rel, {lab: "Selftest edit"})
            r = M.build(c)
            if r.errors or r.paths() != sorted(rels):
                return False, f"staged {r.paths()}, errors {r.errors[:2]}"
            bad = []
            for rel, lab in want.items():
                _n, got, _b = TX.msg.parse(lz.decompress(r.files[rel]))
                van = TX.archive(rel)
                changed = [e[0] for e, v in zip(got, van.entries) if e != v]
                if changed != [lab] or r.files[rel][0] != van.raw[0]:
                    bad.append(rel)
            return not bad and common_rel is not None, f"route + common archives rebuilt: {len(rels) - len(bad)}/" \
                f"{len(rels)}" + (f"; bad {bad}" if bad else "")
        check("text: a route-only archive (m/<route>/@E) and an m/common archive edit build and read back",
              t_text_route_common)

        def t_text_broken():
            c = ctx("text-broken")
            m = M.new_mod(c, "Broken", tables=[])
            hdr = f"{TX.HEADER}\n#name {TX.msg.isbin.quote(TX.archive(NAMES).name)}\n"
            p = os.path.join(m.dir, "text", *NAMES.split("/")) + ".txt"
            bad = []
            for body, want in [(hdr + "[MPID_SELFTEST_NEW]\nX\n", "new labels are refused"),
                               ("[A]\nX\n", "first line must be"),
                               (hdr + "[" + M.example_name_label(c).decode("cp932") + "]\nline one\nline two\n",
                                "ONE line")]:
                put(m.dir, os.path.relpath(p, m.dir).replace(os.sep, "/"), body.encode("utf-8"))
                r = M.build(c)
                if r.paths() or not any(want in e for e in r.errors):
                    bad.append(f"{want}: {r.errors[:1]}")
            put(m.dir, "text/GameData/GameData.bin.lz.txt", hdr.encode())    # not a message archive
            os.remove(p)
            r = M.build(c)
            if not any("not a message archive" in e for e in r.errors):
                bad.append(f"non-archive path: {r.errors[:1]}")
            return not bad and M.read_staged(c) is None, "; ".join(bad) or "4 broken text files refused, nothing staged"
        check("text: broken text edits are refused with the file and line", t_text_broken)

        # ================================================================ install safety
        two_labels = {}

        def two_file_ctx(name):
            """Two text mods editing two archives (shared names + a route archive)."""
            c = ctx(name)
            M.make_text_example(c)
            lab = first_own_label(route_rel)
            text_mod(c, "Route", route_rel, {lab: "Selftest edit"})
            r = M.build(c)
            assert not r.errors and r.paths() == sorted([NAMES, route_rel]), r.errors[:2]
            two_labels["paths"] = r.paths()
            return c

        def t_install_existing():
            c = two_file_ctx("install1")
            z = c.zakuro_dir
            tid = M.TITLE_HEX
            put(z, "settings.toml", b"games = 'x'\n")
            put(z, f"mods/{tid}/romfs/{NAMES}", b"someone else's file")
            put(z, f"mods/{tid}/textures/pack.json", b"{}")
            put(z, "mods/00040000000A0500/romfs/x.bin", b"other game")
            before = snapshot(z)
            M.install(c)
            tdir = c.title_dir()
            st = M.read_staged(c)
            placed = all(M.file_sha(os.path.join(tdir, "romfs", *f["path"].split("/"))) == f["sha256"]
                         for f in st["files"])
            backed = read(os.path.join(tdir, M.BACKUP, "romfs", *NAMES.split("/"))) == b"someone else's file"
            M.install(c)                                   # again: undo + redo, same result
            again = M.read_manifest(c) is not None and len(M.read_manifest(c)["files"]) == 2
            no_tmp = not any(M.TMP_SUFFIX in f for _d, _s, fs in os.walk(z) for f in fs)
            ok, _ = M.uninstall(c)
            same = snapshot(z) == before
            return placed and backed and again and no_tmp and ok and same, \
                f"placed {placed}, backup kept {backed}, reinstall {again}, no temp files {no_tmp}, " \
                f"restored exactly {same}"
        check("install over existing files backs them up; uninstall restores the folder exactly", t_install_existing)

        def t_install_fresh():
            c = two_file_ctx("install2")
            z = c.zakuro_dir
            put(z, "settings.toml", b"x")
            before = snapshot(z)
            M.install(c)
            mid = os.path.isfile(os.path.join(z, "mods", M.TITLE_HEX, "romfs", *route_rel.split("/")))
            man = os.path.isfile(os.path.join(z, "mods", M.TITLE_HEX, M.MANIFEST))
            ok, _ = M.uninstall(c)
            return mid and man and ok and snapshot(z) == before, \
                f"installed under mods/{M.TITLE_HEX}/romfs with {M.MANIFEST}; folders install made are removed again"
        check("install into a fresh Zakuro folder (title 0004000000179800); uninstall leaves no trace",
              t_install_fresh)

        def t_changed_after():
            c = two_file_ctx("install3")
            z = c.zakuro_dir
            before = snapshot(z)
            M.install(c)
            p = os.path.join(c.title_dir(), "romfs", *route_rel.split("/"))
            put(z, os.path.relpath(p, z).replace(os.sep, "/"), b"edited by hand")
            ok, _ = M.uninstall(c)
            kept = read(p) == b"edited by hand"
            gone = not os.path.exists(os.path.join(c.title_dir(), "romfs", *NAMES.split("/")))
            try:
                M.install(c)
                refused = False
            except M.ModError:
                refused = True
            os.remove(p)
            ok2, _ = M.uninstall(c)
            return (not ok) and kept and gone and refused and ok2 and snapshot(z) == before, \
                f"hand-edited file kept {kept}, ours removed {gone}, reinstall refused {refused}"
        check("a file changed after install is never deleted by uninstall", t_changed_after)

        def t_no_zakuro():
            c = two_file_ctx("install4")
            shutil.rmtree(c.zakuro_dir)
            try:
                M.install(c)
                return False, "installed without a Zakuro folder"
            except M.ModError:
                return not os.path.exists(c.zakuro_dir), "refused, nothing created"
        check("install refuses when Zakuro's data folder does not exist", t_no_zakuro)

        def t_lower_case():
            c = two_file_ctx("install5")
            z = c.zakuro_dir
            os.makedirs(os.path.join(z, "mods", M.TITLE_HEX.lower()))
            before = snapshot(z)
            M.install(c)
            used = os.path.basename(c.title_dir()) == M.TITLE_HEX.lower()
            ok, _ = M.uninstall(c)
            return used and ok and snapshot(z) == before, "only a lower-case title folder exists: it is used"
        check("Zakuro's folder rule: a lower-case title folder is used when only it exists", t_lower_case)

        # review 2026-11-11 #1: an install stopped at any step is undone to the exact bytes
        class Crash(BaseException):
            """a simulated crash: install does not catch it, like a killed process"""

        def journal_ctx(name):
            c = two_file_ctx(name)
            z = c.zakuro_dir
            put(z, "settings.toml", b"x")
            put(z, f"mods/{M.TITLE_HEX}/romfs/{NAMES}", b"the owner's previous file")
            return c, snapshot(z)

        def reset(z, snap):
            shutil.rmtree(z)
            for (kind, rel), data in sorted(snap.items(), key=lambda kv: kv[0][1]):
                p = os.path.normpath(os.path.join(z, rel))
                if kind == "dir":
                    os.makedirs(p, exist_ok=True)
                else:
                    put(z, os.path.relpath(p, z).replace(os.sep, "/"), data)

        def fail_at(n, exc):
            calls = [0]

            def fault(_step):
                calls[0] += 1
                if calls[0] == n + 1:
                    raise exc
            M.FAULT = fault

        def all_steps(c):
            seen = []
            M.FAULT = seen.append
            try:
                M.install(c)
            finally:
                M.FAULT = None
            M.uninstall(c)
            return seen

        def t_crash_every_step():
            c, before = journal_ctx("journal1")
            steps = all_steps(c)
            bad = []
            try:
                for n, step in enumerate(steps):
                    reset(c.zakuro_dir, before)
                    fail_at(n, Crash(step))
                    try:
                        M.install(c)
                        bad.append(f"{step}#{n}: no crash")
                        continue
                    except Crash:
                        pass
                    M.FAULT = None
                    if n % 2:                              # half: the next install recovers first
                        M.install(c)
                    ok, _m = M.uninstall(c)
                    if not ok or snapshot(c.zakuro_dir) != before:
                        bad.append(f"{step}#{n}")
            finally:
                M.FAULT = None
            return not bad and "moved" in steps, f"{len(steps)} stopping points (move-aside, copy, rename, " \
                f"each manifest write): {len(steps) - len(bad)} restored exactly" + (f"; bad {bad[:4]}" if bad else "")
        check("an install crashed at any step is undone exactly by uninstall or the next install", t_crash_every_step)

        def t_disk_full():
            import errno
            c, before = journal_ctx("journal2")
            steps = all_steps(c)
            bad = []
            try:
                for n, step in enumerate(steps):
                    reset(c.zakuro_dir, before)
                    fail_at(n, OSError(errno.ENOSPC, "No space left on device"))
                    try:
                        M.install(c)
                        bad.append(f"{step}#{n}: installed")
                    except M.ModError as e:
                        if "disk full" not in str(e) or snapshot(c.zakuro_dir) != before:
                            bad.append(f"{step}#{n}")
                    finally:
                        M.FAULT = None
            finally:
                M.FAULT = None
            return not bad, f"disk full at each of {len(steps)} points: undone at once, folder exact" + \
                (f"; bad {bad[:4]}" if bad else "")
        check("disk full during install: what was done is undone at once", t_disk_full)

        # review 2026-11-11 #2: a refused uninstall can be finished with one command
        def t_restore_backups():
            c, before = journal_ctx("journal3")
            M.install(c)
            p = os.path.join(c.title_dir(), "romfs", *NAMES.split("/"))
            with open(p, "wb") as fh:
                fh.write(b"changed after install")
            ok, msgs = M.uninstall(c)
            told = M.RESTORE_COMMAND in "\n".join(msgs) and "your previous file" in "\n".join(msgs)
            try:
                M.install(c)
                refused = False
            except M.ModError as e:
                refused = M.RESTORE_COMMAND in str(e)
            ok2, _m = M.uninstall(c, restore_backups=True)
            back = read(p) == b"the owner's previous file"
            kept = read(os.path.join(c.title_dir(), M.CHANGED, "romfs", *NAMES.split("/"))) == b"changed after install"
            shutil.rmtree(os.path.join(c.title_dir(), M.CHANGED))
            same = snapshot(c.zakuro_dir) == before
            return (not ok) and told and refused and ok2 and back and kept and same, \
                f"explained {told}, install refused with the command {refused}, previous file back {back}, " \
                f"changed file kept {kept}, folder otherwise exact {same}"
        check("after a refused uninstall, uninstall --restore-backups puts the previous file back, keeps the changed one",
              t_restore_backups)

        # the uninstall is journaled too: a crash in uninstall, or in install's own undo, never
        # strands the owner's previous file or mistakes it for a changed mod file
        def t_crash_in_uninstall():
            c, before = journal_ctx("journal4")
            runs = bad = 0
            fails = []
            try:
                for label, first in (("uninstall", lambda: M.uninstall(c)), ("install over install", lambda: M.install(c))):
                    reset(c.zakuro_dir, before)
                    M.install(c)
                    seen = []
                    M.FAULT = seen.append
                    first()
                    M.FAULT = None
                    for n, step in enumerate(seen):
                        reset(c.zakuro_dir, before)
                        M.install(c)
                        fail_at(n, Crash(step))
                        try:
                            first()
                            fails.append(f"{label} {step}#{n}: no crash")
                            continue
                        except Crash:
                            pass
                        finally:
                            M.FAULT = None
                        runs += 1
                        ok, msgs = M.uninstall(c)
                        if not ok or snapshot(c.zakuro_dir) != before or "was changed after" in "\n".join(msgs):
                            bad += 1
                            fails.append(f"{label} {step}#{n}")
            finally:
                M.FAULT = None
            return not fails and runs > 0, f"{runs} crashes inside uninstall / install's undo: " \
                f"{runs - bad} restored exactly" + (f"; bad {fails[:4]}" if fails else "")
        check("a crash during uninstall (or install's automatic undo) is finished exactly by the next uninstall",
              t_crash_in_uninstall)

        # ================================================================ romfs (whole files)
        # a small LZ file from the game and a changed copy, recompressed (LZ13)
        cand = []
        for d, _dn, fn in os.walk(os.path.join(ROMFS, M.GAME.romfs.gamedata_dir)):
            for f in fn:
                if f.endswith(".bin.lz"):
                    p = os.path.join(d, f)
                    cand.append((os.path.getsize(p), os.path.relpath(p, ROMFS).replace(os.sep, "/")))
        cand.sort()
        asset_rel = next(r for _s, r in cand if lz.lz_type(read(os.path.join(ROMFS, *r.split("/")))) == 0x13)
        asset_orig = read(os.path.join(ROMFS, *asset_rel.split("/")))
        dec = bytearray(lz.decompress(asset_orig))
        dec[-1] ^= 0xFF
        asset_new = lz.compress(bytes(dec), 0x13)

        def asset_mod(c, name, rel, data, order=None, override=False):
            m = M.new_mod(c, name, tables=[])
            put(m.dir, f"romfs/{rel}", data)
            m.meta["override"] = override
            if order is not None:
                m.meta["order"] = order
            m.save()
            return m

        def t_asset_install():
            c = ctx("asset1")
            z = c.zakuro_dir
            put(z, "settings.toml", b"x")
            before = snapshot(z)
            asset_mod(c, "Pic", asset_rel, asset_new)
            M.make_text_example(c)
            r = M.build(c)
            if r.errors or r.paths() != sorted([asset_rel, NAMES]):
                return False, f"staged {r.paths()}, errors {r.errors[:2]}"
            st = M.read_staged(c)
            kinds = sorted(f.get("kind", "table") for f in st["files"])
            staged_ok = read(os.path.join(c.stage_romfs, *asset_rel.split("/"))) == asset_new
            M.install(c)
            placed = read(os.path.join(c.title_dir(), "romfs", *asset_rel.split("/"))) == asset_new
            man = M.read_manifest(c)
            listed = sorted(e["path"] for e in man["files"]) == sorted("romfs/" + p for p in (asset_rel, NAMES))
            changes = read(os.path.join(c.stage_dir, "changes.txt")).decode("utf-8")
            ok, _ = M.uninstall(c)
            return (staged_ok and placed and listed and kinds == ["romfs", "text"] and ok
                    and f"romfs {asset_rel}: whole file replaced" in changes and snapshot(z) == before), \
                f"copied byte for byte {placed}, in manifest {listed}, kinds {kinds}, restored exactly"
        check("romfs: a whole replacement file installs as-is next to a text mod; uninstall restores",
              t_asset_install)

        def t_asset_case():
            c = ctx("asset2")
            asset_mod(c, "Lower", asset_rel.lower(), asset_new)
            r = M.build(c)
            hit = r.paths() == [asset_rel] and any("the game spells it" in n for n in r.notes)
            return hit and not r.errors, f"lower-case path staged as {r.paths()}"
        check("romfs: a path typed in other upper/lower case is installed under the game's spelling", t_asset_case)

        def t_asset_checks():
            c = ctx("asset3")
            bad = []
            m = asset_mod(c, "Raw", asset_rel, bytes(dec))                     # not compressed
            r = M.build(c)
            if r.paths() or not any("not LZ-compressed" in e for e in r.errors):
                bad.append(f".lz without LZ: {r.errors[:1]}")
            shutil.rmtree(m.dir)
            m = asset_mod(c, "Same", asset_rel, asset_orig)                    # same bytes
            put(m.dir, "romfs/GameData/Thumbs.db", b"junk")
            r = M.build(c)
            if r.errors or r.paths() or not any("same bytes" in n for n in r.notes) \
                    or not any("Thumbs.db: skipped" in n for n in r.notes):
                bad.append(f"same bytes / junk: {r.errors[:1]} {r.paths()}")
            shutil.rmtree(m.dir)
            m = asset_mod(c, "New", "GameData/SelftestNew.bin", b"new file")   # not in the game
            r = M.build(c)
            if r.errors or r.paths() != ["GameData/SelftestNew.bin"] or not any("is added" in w for w in r.warnings):
                bad.append(f"new file: {r.errors[:1]} {r.paths()}")
            shutil.rmtree(m.dir)
            m = asset_mod(c, "Code", "exefs/code.bin", b"x")                   # not a data mod
            r = M.build(c)
            if r.paths() or not any("not data mods" in e for e in r.errors):
                bad.append(f"exefs: {r.errors[:1]}")
            shutil.rmtree(m.dir)
            return not bad, "; ".join(bad) or ".lz without LZ refused, same bytes and junk skipped, new file " \
                "added with a warning, exefs refused"
        check("romfs: LZ, same-bytes, junk, new-file and code checks", t_asset_checks)

        def t_asset_conflicts():
            c = ctx("asset4")
            asset_mod(c, "A", asset_rel, asset_new, order=10)
            dec2 = bytearray(dec)
            dec2[-2] ^= 0xFF
            other = lz.compress(bytes(dec2), 0x13)
            b = asset_mod(c, "B", asset_rel, other, order=20)
            r1 = M.build(c)
            refused = any(e.startswith("conflict: romfs") for e in r1.errors) and not r1.paths()
            b.meta["override"] = True
            b.save()
            r2 = M.build(c)
            won = not r2.errors and read(os.path.join(c.stage_romfs, *asset_rel.split("/"))) == other
            c2 = ctx("asset5")
            names_dec = bytearray(lz.decompress(read(os.path.join(ROMFS, *NAMES.split("/")))))
            names_dec[-1] ^= 0xFF
            asset_mod(c2, "Whole", NAMES, lz.compress(bytes(names_dec), 0x13))
            M.make_text_example(c2)
            r3 = M.build(c2)
            clash = any("replaced as a whole file" in e for e in r3.errors) and not r3.paths()
            return refused and won and clash, f"same path refused {refused}, override wins {won}, " \
                f"romfs + text on one file refused {clash}"
        check("romfs: conflicts between mods (override wins) and a romfs file + text edit of it", t_asset_conflicts)

        # ================================================================ tables
        T = M.T

        def synthetic_tables(base):
            """A fake RomFS with GameData/Synth.bin.lz (LZ13) holding 3 records of an
            invented 12-byte layout, plus config/tables/ describing it."""
            romfs, cfg = os.path.join(base, "romfs"), os.path.join(base, "config")
            pids = [b"PID_SELFTEST_A", b"PID_SELFTEST_B", b"PID_SELFTEST_C"]
            data = bytearray(struct.pack("<I", 3))
            relocs, strs = [], []
            for k, pid in enumerate(pids):
                o = len(data)
                data += struct.pack("<IIBbH", 0, 0, 20 + k, k - 1, 5)
                relocs += [o, o + 4]
                strs += [pid, b"MPID_SELFTEST_" + bytes([65 + k])]
            labels = [(4 + 12 * k, pid) for k, pid in enumerate(pids)]
            tab, noffs, soffs = M.TX.msg.isbin.build_pool([n for _o, n in labels], strs)
            se = len(data) + 4 * len(relocs) + 8 * len(labels)
            for r, so in zip(relocs, soffs):
                struct.pack_into("<I", data, r, se + so)
            b = M.TX.msg.isbin.IsBin()
            b.data, b.relocs, b.strtab = bytes(data), relocs, tab
            b.labels = [(o, n, no) for (o, n), no in zip(labels, noffs)]
            put(romfs, "GameData/Synth.bin.lz", lz.compress(b.build(), 0x13))
            put(cfg, "tables.csv", b"table,file,start,count,record_size,code_global,count_global,description\n"
                                   b"Synth,GameData/Synth.bin.lz,offset:4,header:0,0xC,,,selftest table\n")
            put(cfg, "Synth.csv", b"offset,size,type,name,confidence,evidence\n"
                                  b"0x0,4,str:self,pid,high,selftest\n0x4,4,str,mpid_name,high,selftest\n"
                                  b"0x8,1,u8,hp,high,selftest\n0x9,1,s8,base_stats.str,high,selftest\n"
                                  b"0xA,2,u16,move,high,selftest\n")
            return romfs, cfg

        class Backend:
            def __init__(self, cfg, romfs):
                self.cfg, self.romfs = cfg, romfs

            def __enter__(self):
                self.saved = (T.CONFIG, T.ROMFS)
                T.CONFIG, T.ROMFS = self.cfg, self.romfs
                M.reset_tables()

            def __exit__(self, *exc):
                T.CONFIG, T.ROMFS = self.saved
                M.reset_tables()

        if T is None:
            skip("tables: synthetic table checks", f"tools/tables cannot be loaded: {M._TABLES_IMPORT_ERROR}")
        else:
            syn_romfs, syn_cfg = synthetic_tables(os.path.join(tmp, "synthetic"))
            SYN = "GameData/Synth.bin.lz"

            def decode(data):
                c = T.Container(SYN, data)
                t = M.reg()["Synth"]
                s, n = T.locate(t, c)
                labels = T.record_labels(t, c, s, n)
                return [M.codec("Synth").decode(c, i, s + i * t.size, labels[i]) for i in range(n)]

            def set_cell(m, idx, col, v):
                path = os.path.join(m.dir, "tables", "Synth.csv")
                head, rows = M.read_table_csv(path)
                rows[idx][head.index(col)] = v
                M.write_table_csv(path, head, rows)

            def t_syn_unedited():
                with Backend(syn_cfg, syn_romfs):
                    c = ctx("syn1", syn_romfs)
                    m = M.new_mod(c, "Plain")
                    r = M.build(c)
                    return (not r.errors and not r.paths() and len(m.tables()) == 1
                            and M.table_names() == ["Synth"]), f"{len(m.tables())} table copied, errors {r.errors[:2]}"
            check("tables (synthetic layout): an unedited spreadsheet stages nothing", t_syn_unedited)

            def t_syn_one_cell():
                with Backend(syn_cfg, syn_romfs):
                    c = ctx("syn2", syn_romfs)
                    z = c.zakuro_dir
                    before = snapshot(z)
                    m = M.new_mod(c, "Str")
                    van = M.vanilla()["Synth"][1]
                    set_cell(m, 1, "base_stats.str", "10")
                    r = M.build(c)
                    if r.errors or r.paths() != [SYN]:
                        return False, f"staged {r.paths()}, errors {r.errors[:3]}"
                    got = decode(r.files[SYN])
                    want = [list(x) for x in van]
                    want[1][M.vanilla()["Synth"][0].index("base_stats.str")] = "10"
                    lz13 = r.files[SYN][0] == 0x13
                    M.install(c)
                    placed = read(os.path.join(c.title_dir(), "romfs", *SYN.split("/"))) == r.files[SYN]
                    ok, _ = M.uninstall(c)
                    return got == want and lz13 and placed and ok and snapshot(z) == before, \
                        f"decodes to the edit {got == want}, LZ13 {lz13}, installed and removed {placed and ok}"
            check("tables (synthetic layout): a one-cell edit stages one container that decodes back; "
                  "install/uninstall", t_syn_one_cell)

            def t_syn_invalid():
                with Backend(syn_cfg, syn_romfs):
                    c = ctx("syn3", syn_romfs)
                    bad = []
                    for k, (col, v, want) in enumerate([("hp", "300", "out of range"),
                                                        ("base_stats.str", "abc", "not a whole number"),
                                                        ("pid", "PID_OTHER", "own ID")]):
                        m = M.new_mod(c, f"Bad{k}")
                        set_cell(m, 0, col, v)
                        r = M.build(c)
                        if r.paths() or not any(want in e for e in r.errors):
                            bad.append(f"{col}={v}: {r.errors[:1]}")
                        m.meta["enabled"] = False
                        m.save()
                    a = M.new_mod(c, "A")
                    set_cell(a, 2, "move", "6")
                    b = M.new_mod(c, "B")
                    set_cell(b, 2, "move", "7")
                    r = M.build(c)
                    if not any(e.startswith("conflict:") for e in r.errors):
                        bad.append(f"conflict not refused: {r.errors[:1]}")
                    b.meta["override"] = True
                    b.save()
                    r = M.build(c)
                    if r.errors or decode(r.files[SYN])[2][M.vanilla()["Synth"][0].index("move")] != "7":
                        bad.append(f"override: {r.errors[:1]}")
                    return not bad, "; ".join(bad) or "range, number, own-ID refused; conflict refused, override wins"
            check("tables (synthetic layout): invalid cells and conflicts are refused", t_syn_invalid)

            def t_tables_off():
                empty = os.path.join(tmp, "no-layouts")
                os.makedirs(empty)
                with Backend(empty, syn_romfs):
                    c = ctx("syn4")                         # real RomFS for the text part
                    why = M.tables_status()
                    m = M.new_mod(c, "WithTables", tables=[])
                    put(m.dir, "tables/Person.csv", b"index,label\n")
                    r1 = M.build(c)
                    refused = any("table mods are not available" in e for e in r1.errors) and not r1.paths()
                    m.meta["enabled"] = False
                    m.save()
                    M.make_text_example(c)
                    r2 = M.build(c)
                    m2 = M.new_mod(c, "Default")            # no layouts: no spreadsheets, no error
                    try:
                        M.make_example(c)
                        demo = False
                    except M.ModError as e:
                        demo = "example-text" in str(e)
                    return (why is not None and refused and not r2.errors and r2.paths() == [NAMES]
                            and m2.tables() == [] and demo), \
                        f"reason given {why is not None}, table mod refused {refused}, text still builds " \
                        f"{not r2.errors}, table demo points to example-text {demo}"
            check("tables off (no layouts): spreadsheets refused with the reason, text mods still work", t_tables_off)

        why = M.tables_status() or (None if M.table_names() else "config/tables/ has no layout files yet")
        if why:
            skip("tables (real layouts): unedited mod and the Example demo", why)
        else:
            def t_real_unedited():
                c = ctx("real1")
                m = M.new_mod(c, "Plain")
                r = M.build(c)
                return not r.errors and not r.paths(), f"{len(m.tables())} tables copied, errors {r.errors[:2]}"
            check("tables (real layouts): an unedited mod with every spreadsheet stages nothing", t_real_unedited)

            if "Person" in M.vanilla():
                def t_real_example():
                    c = ctx("real2")
                    rel, key, col = M.example_target(c)
                    _m, what = M.make_example(c)
                    r = M.build(c)
                    if r.errors or r.paths() != [rel]:
                        return False, f"staged {r.paths()}, errors {r.errors[:2]}"
                    nc = T.Container(rel, r.files[rel])
                    t = M.reg()["Person"]
                    s, n = T.locate(t, nc)
                    labels = T.record_labels(t, nc, s, n)
                    got = [M.codec("Person").decode(nc, i, s + i * t.size, labels[i]) for i in range(n)]
                    head, rows = M.vanilla()["Person"]
                    vr = [x for x in rows if M.row_rel("Person", M.row_key("Person", x)) == rel]
                    diff = [(g[head.index("label")], h) for g, w in zip(got, vr) for h, a, b in zip(head, g, w)
                            if a != b]
                    return len(diff) == 1 and diff[0][1] == col, f"{what}; cells changed {len(diff)}"
                check("tables (real layouts): the Example mod changes exactly one Person cell", t_real_example)
            else:
                skip("tables (real layouts): the Example demo", "config/tables/ has no Person layout yet")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            os.rmdir(scratch)
        except OSError:
            pass

    n_ok = sum(ok for _n, ok, _d in results)
    print(f"mods selftest: {n_ok}/{len(results)} checks passed")
    return 0 if n_ok == len(results) else 1
