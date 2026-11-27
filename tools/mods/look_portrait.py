#!/usr/bin/env python3
"""The portrait look (PORT_PLAN step 5): one mod, `mods/LookPortrait`, in which Jakob's
portraits show Felicia's face (docs/LOOK_PORTRAIT.md). One direction only: Felicia keeps
her own portraits.

    python tools/mods/look_portrait.py install   make mods/LookPortrait if it is missing, then
                                                 build and install it (tools/mods/mods.py install)
    python tools/mods/look_portrait.py make      only make mods/LookPortrait
    python tools/mods/look_portrait.py check     build into a scratch folder, decode the built
                                                 portrait files again and compare every picture
                                                 with Felicia's and Jakob's, install into a
                                                 scratch Zakuro-style folder under
                                                 build/look_portrait/check/ and uninstall back
                                                 byte-identical (never %APPDATA%)
    python tools/mods/mods.py uninstall          takes it out again

How: the existing portrait mod kind (`faces/`, docs/MODDING.md 6b, like ExampleFace). Jakob's
standing (_st) and talk-window (_bu) portrait folders are exported from your own game files
into the mod; each expression picture is replaced by Felicia's picture of the same expression
(her normal expression where she has no picture of that name), always of the same size (exported from your game files into a scratch folder, never stored in the
repository). The sweat and blush overlays stay Jakob's. Characters are found at run time
through their English name labels. Standard library only; built entirely with
tools/mods/mods.py and tools/assets/portrait.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import look_step4 as L4  # noqa: E402

MOD_NAME = "LookPortrait"
TARGET, SOURCE = "Jakob", "Felicia"          # TARGET's portraits show SOURCE's face
KINDS = ("_st", "_bu")                        # standing and talk-window packages


def name_label(M, ctx, english: str) -> str:
    van = M.TX.archive(M.NAME_ARCHIVE, ctx.romfs)
    hit = [lab for lab, _v, a in van.entries
           if lab.startswith(M.NAME_PREFIX) and not a and van.text_of[lab] == english]
    if len(hit) != 1:
        raise M.ModError(f"expected one name label {english!r}, found {len(hit)}")
    return hit[0].decode("cp932")


def records(M, ctx, english: str) -> dict[str, dict]:
    lab = name_label(M, ctx, english)
    out = {}
    for r in M.face_records(ctx, lab):
        for k in KINDS:
            if r["mpid"] == lab and r["package"].endswith(k):
                out.setdefault(k, r)
    if set(out) != set(KINDS):
        raise M.ModError(f"{english}: expected one standing and one talk-window portrait, found {sorted(out)}")
    return out


def expressions(man: dict, src: str) -> dict[str, dict]:
    return {x["member"]: x for x in man["layers"] if x["source"] == src and x["role"] == "expression"}


def source_member(M, member: str, src_members) -> str:
    """SOURCE's picture for TARGET's expression MEMBER: the same expression, or SOURCE's
    normal expression when SOURCE has no picture of that name (so every expression changes)."""
    if member in src_members:
        return member
    return next((x for x in src_members if x.startswith(M.FACE_EXAMPLE_MEMBER)), member)


def make(M, ctx, scratch: str) -> list[str]:
    P = M.MF.portrait()
    P.ROMFS = ctx.romfs
    tgt, srcr = records(M, ctx, TARGET), records(M, ctx, SOURCE)
    m = M.new_mod(ctx, MOD_NAME, f"The portrait look (docs/LOOK_PORTRAIT.md): {TARGET}'s portraits show "
                  f"{SOURCE}'s face", tables=[])
    lines = []
    try:
        for k in KINDS:
            tsrc = f"face/face/{tgt[k]['package']}.arc"
            ssrc = f"face/face/{srcr[k]['package']}.arc"
            d = M.add_face(ctx, m, f"{TARGET}{k}", [tgt[k]], [tsrc])
            sd = os.path.join(scratch, f"{SOURCE}{k}")
            shutil.rmtree(sd, ignore_errors=True)
            sman = P.export_sources([ssrc], sd, [srcr[k]])
            with open(os.path.join(d, "portrait.json"), encoding="utf-8") as fh:
                tman = json.load(fh)
            te, se = expressions(tman, tsrc), expressions(sman, ssrc)
            done, skipped = 0, []
            for member, ly in te.items():
                s = se.get(source_member(M, member, se))
                if s is None or (s["width"], s["height"]) != (ly["width"], ly["height"]):
                    skipped.append(member)
                    continue
                shutil.copyfile(os.path.join(sd, *s["png"].split("/")), os.path.join(d, *ly["png"].split("/")))
                done += 1
            if not done:
                raise M.ModError(f"{k}: no expression of {SOURCE} matches one of {TARGET} by name and size")
            lines.append(f"{tsrc}: {done} of {len(te)} expression pictures now {SOURCE}'s "
                         f"({len(skipped)} kept, no same-size picture)")
    except Exception:
        shutil.rmtree(m.dir, ignore_errors=True)
        raise
    return lines


def decode_arc(P, raw: bytes, out_dir: str) -> dict[str, tuple[int, int, bytes]]:
    """member name -> (w, h, rgba) of its first texture."""
    members, _layout = P.arc.parse_full(raw)
    out = {}
    for i, mm in enumerate(members):
        sub = os.path.join(out_dir, f"{i:02d}")
        P.bch.export(mm["data"], sub)
        with open(os.path.join(sub, "bch.json"), encoding="utf-8") as fh:
            t = json.load(fh)["textures"][0]
        out[P._s(mm["name"])] = P.tex3ds.read_png(os.path.join(sub, t["file"]))
    return out


def mad(a: bytes, b: bytes) -> float:
    """Mean absolute difference per channel over pixels visible in either picture."""
    tot = n = 0
    for i in range(0, len(a), 4):
        if a[i + 3] or b[i + 3]:
            tot += sum(abs(a[i + j] - b[i + j]) for j in range(4))
            n += 4
    return tot / n if n else 0.0


def check(M) -> int:
    top = os.path.join(ROOT, "build", "look_portrait", "check")
    shutil.rmtree(top, ignore_errors=True)
    zak = os.path.join(top, "zakuro")
    ctx = M.Ctx(mods_dir=os.path.join(top, "mods"), stage_dir=os.path.join(top, "stage"), zakuro_dir=zak)
    assert os.path.abspath(ctx.zakuro_dir).startswith(os.path.abspath(top)), "scratch only"
    os.makedirs(ctx.mods_dir)
    bad = []
    for line in make(M, ctx, os.path.join(top, "source")):
        print("  edit:", line)
    r = M.build(ctx)
    for w in r.warnings:
        print("  build warning:", w)
    if r.errors:
        for e in r.errors:
            print("  build error:", e)
        return 1
    files = r.paths()
    print(f"  built {len(files)} file(s): {', '.join(files)}")
    P = M.MF.portrait()
    tgt, srcr = records(M, ctx, TARGET), records(M, ctx, SOURCE)
    want = sorted(f"face/face/{tgt[k]['package']}.arc" for k in KINDS)
    if sorted(files) != want:
        bad.append(f"expected exactly {len(want)} portrait files to be built, got {files}")
    for k in KINDS:
        rel = f"face/face/{tgt[k]['package']}.arc"
        p = os.path.join(ctx.stage_romfs, *rel.split("/"))
        if not os.path.exists(p):
            continue
        with open(p, "rb") as fh:
            built = decode_arc(P, fh.read(), os.path.join(top, "readback", f"built{k}"))
        with open(os.path.join(ctx.romfs, *rel.split("/")), "rb") as fh:
            orig = decode_arc(P, fh.read(), os.path.join(top, "readback", f"orig{k}"))
        sp = os.path.join(ctx.romfs, "face", "face", f"{srcr[k]['package']}.arc")
        with open(sp, "rb") as fh:
            src = decode_arc(P, fh.read(), os.path.join(top, "readback", f"src{k}"))
        if list(built) != list(orig):
            bad.append(f"{k}: member list changed")
        n_sw = n_keep = 0
        worst = 0.0
        for member, (w, h, px) in built.items():
            ow, oh, opx = orig[member]
            if (w, h) != (ow, oh):
                bad.append(f"{k} {member}: size changed"); continue
            s = src.get(source_member(M, member, src)) if not any(member.startswith(o) for o in P.OVERLAYS) else None
            if s is not None and (s[0], s[1]) == (w, h) and not any(member.startswith(o) for o in P.OVERLAYS):
                ds, dt = mad(px, s[2]), mad(px, opx)
                worst = max(worst, ds)
                if not (ds < 6 and ds * 3 < dt):
                    bad.append(f"{k} {member}: built picture is not {SOURCE}'s (diff {ds:.1f} to {SOURCE}, "
                               f"{dt:.1f} to {TARGET})")
                n_sw += 1
            else:
                if mad(px, opx) > 6:
                    bad.append(f"{k} {member}: a kept picture changed")
                n_keep += 1
        print(f"  read back {rel.split('/')[-1].encode('unicode_escape').decode()}: {n_sw} expression "
              f"pictures match {SOURCE}'s (largest mean colour difference {worst:.2f} of 255, ETC1 re-encoding), "
              f"{n_keep} kept as {TARGET}'s (overlays)")
    tdir = ctx.title_dir()
    os.makedirs(os.path.join(tdir, "romfs"), exist_ok=True)
    with open(os.path.join(tdir, "owner-note.txt"), "w") as fh:
        fh.write("a file that is not ours\n")
    before = L4.tree_hash(zak)
    for line in M.install(ctx):
        print("  install:", line.encode("unicode_escape").decode())
    inst = L4.tree_hash(zak)
    for f in files:
        kk = os.path.relpath(os.path.join(tdir, "romfs", *f.split("/")), zak)
        with open(os.path.join(ctx.stage_romfs, *f.split("/")), "rb") as fh:
            if inst.get(kk) != hashlib.sha256(fh.read()).hexdigest():
                bad.append("an installed file differs from the build")
    print(f"  installed {len(files)} file(s) into {os.path.relpath(tdir, ROOT)}")
    ok, msgs = M.uninstall(ctx)
    for line in msgs:
        print("  uninstall:", line.encode("unicode_escape").decode())
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
            for line in make(M, ctx, os.path.join(ROOT, "build", "look_portrait", "source")):
                print("made:", line.encode("unicode_escape").decode())
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
