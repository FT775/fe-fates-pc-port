#!/usr/bin/env python3
"""The text look (PORT_PLAN step 3): one mod, `mods/LookText`, renames ONE name the owner sees
within a few minutes of loading a save: Jakob (Corrin's butler) shows as "Jacques"
(docs/LOOK_TEXT.md).

    python tools/mods/look_text.py install      make mods/LookText if it is missing, then build
                                                and install it (tools/mods/mods.py install)
    python tools/mods/look_text.py make         only make mods/LookText
    python tools/mods/look_text.py check        build into a scratch folder, read the name back
                                                from the built file, check nothing else changed,
                                                install into a scratch Zakuro-style folder under
                                                build/look_text/check/ and uninstall back
                                                byte-identical (never %APPDATA%)
    python tools/mods/mods.py uninstall         takes it out again

The label is found at run time by its English text in your own game files (the one name
label of m/@E/GameData.bin.lz whose text is exactly "Jakob"), so no game text is stored in
this repository beyond the one name. Standard library only; built entirely with
tools/mods/mods.py (text pipeline T1, tools/mods/textmod.py).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import look_step4 as L4  # noqa: E402  (load_mods, tree_hash, _global_first)

MOD_NAME = "LookText"
OLD_NAME, NEW_NAME = "Jakob", "Jacques"


def label(M, ctx) -> bytes:
    van = M.TX.archive(M.NAME_ARCHIVE, ctx.romfs)
    hit = [lab for lab, _v, a in van.entries
           if lab.startswith(M.NAME_PREFIX) and not a and van.text_of[lab] == OLD_NAME]
    if len(hit) != 1:
        raise M.ModError(f"expected one name label with the text {OLD_NAME!r} in {M.NAME_ARCHIVE}, found {len(hit)}")
    return hit[0]


def make(M, ctx) -> str:
    lab = label(M, ctx)
    van = M.TX.archive(M.NAME_ARCHIVE, ctx.romfs)
    m = M.new_mod(ctx, MOD_NAME, f"The text look (docs/LOOK_TEXT.md): {OLD_NAME}'s name shows as {NEW_NAME}",
                  tables=[])
    path = os.path.join(m.dir, M.TX.TEXT_DIR, *M.NAME_ARCHIVE.split("/")) + M.TX.SUFFIX
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = "\n".join([M.TX.HEADER, "#name " + M.TX.msg.isbin.quote(van.name),
                      "# only the labels you change are needed; the rest of the archive stays as in the game",
                      f"[{lab.decode('cp932')}]", M.TX.msg.escape(NEW_NAME)]) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    return f"{M.NAME_ARCHIVE}: one name label, {OLD_NAME} -> {NEW_NAME}"


def check(M) -> int:
    top = os.path.join(ROOT, "build", "look_text", "check")
    shutil.rmtree(top, ignore_errors=True)
    zak = os.path.join(top, "zakuro")
    ctx = M.Ctx(mods_dir=os.path.join(top, "mods"), stage_dir=os.path.join(top, "stage"), zakuro_dir=zak)
    assert os.path.abspath(ctx.zakuro_dir).startswith(os.path.abspath(top)), "scratch only"
    os.makedirs(ctx.mods_dir)
    bad = []
    print("  edit:", make(M, ctx))
    r = M.build(ctx)
    for w in getattr(r, "warnings", []) or []:
        print("  build warning:", w)
    if r.errors:
        for e in r.errors:
            print("  build error:", e)
        return 1
    files = r.paths()
    print(f"  built {len(files)} file(s): {', '.join(files)}")
    if files != [M.NAME_ARCHIVE]:
        bad.append(f"expected exactly {M.NAME_ARCHIVE} to be built, got {files}")
    # read back: decode the built archive with the text tools; exactly one label differs
    lab = label(M, ctx)
    p = os.path.join(ctx.stage_romfs, *M.NAME_ARCHIVE.split("/"))
    if os.path.exists(p):
        stage_root = ctx.stage_romfs
        got = M.TX.archive(M.NAME_ARCHIVE, stage_root)
        van = M.TX.archive(M.NAME_ARCHIVE, ctx.romfs)
        gl = [(l, a) for l, _v, a in got.entries]
        vl = [(l, a) for l, _v, a in van.entries]
        if gl != vl:
            bad.append("the built archive has a different label list")
        diff = [l for l, _v, a in van.entries if not a and got.text_of.get(l) != van.text_of[l]]
        if diff != [lab] or got.text_of[lab] != NEW_NAME:
            bad.append(f"labels changed: {len(diff)} (wanted exactly the one {OLD_NAME} label -> {NEW_NAME})")
        else:
            print(f"  read back: built file says {got.text_of[lab]!r} for the label that says {OLD_NAME!r} "
                  f"in the game; the other {len(vl) - 1} labels and aliases are unchanged OK")
    # install / uninstall in a scratch Zakuro folder
    tdir = ctx.title_dir()
    os.makedirs(os.path.join(tdir, "romfs"), exist_ok=True)
    with open(os.path.join(tdir, "owner-note.txt"), "w") as fh:
        fh.write("a file that is not ours\n")
    before = L4.tree_hash(zak)
    for line in M.install(ctx):
        print("  install:", line)
    inst = L4.tree_hash(zak)
    for f in files:
        k = os.path.relpath(os.path.join(tdir, "romfs", *f.split("/")), zak)
        with open(os.path.join(ctx.stage_romfs, *f.split("/")), "rb") as fh:
            if inst.get(k) != hashlib.sha256(fh.read()).hexdigest():
                bad.append(f"installed {f} differs from the build")
    print(f"  installed {len(files)} file(s) into {os.path.relpath(tdir, ROOT)}")
    ok, msgs = M.uninstall(ctx)
    for line in msgs:
        print("  uninstall:", line)
    after = L4.tree_hash(zak)
    same = ok and after == before
    print(f"  uninstall back byte-identical: {'OK' if same else 'BAD'} ({len(before)} file(s) before, "
          f"{len(after)} after)")
    if not same:
        bad.append("uninstall not byte-identical")
    print("CHECK", "PASS" if not bad else "FAIL: " + "; ".join(bad))
    return 0 if not bad else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("make", "install", "check"))
    ap.add_argument("--mods-dir"); ap.add_argument("--stage-dir"); ap.add_argument("--zakuro-dir")
    a = ap.parse_args(argv)
    M = L4.load_mods()
    try:
        if a.cmd == "check":
            return check(M)
        ctx = M.Ctx(mods_dir=a.mods_dir, stage_dir=a.stage_dir, zakuro_dir=a.zakuro_dir)
        if a.cmd == "make" or not os.path.isdir(os.path.join(ctx.mods_dir, MOD_NAME)):
            print("made:", make(M, ctx))
        if a.cmd == "install":
            fwd = ["install"] + sum(([f"--{k.replace('_', '-')}", v] for k, v in
                                     (("mods_dir", a.mods_dir), ("stage_dir", a.stage_dir),
                                      ("zakuro_dir", a.zakuro_dir)) if v), [])
            return M.main(L4._global_first(fwd))
    except M.ModError as e:
        print(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
