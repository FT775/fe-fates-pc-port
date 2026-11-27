#!/usr/bin/env python3
"""H6 sampled mode (owner F-024, 2026-11-15: H6 on a sampled record set per function, weekly or near the 90% gate,
fitting in about an hour). `h56.py h6 --sample` uses this module; docs/harness/H56.md section 9. Standard library only;
offline: no game, no engine build, only the host C compiler.

What it does, in order:
 1. trace build: replay.exe once more, with the readable sources outside src/readable/core/ compiled with
    -fsanitize-coverage=trace-pc, h6trace.c linked in and replay.c built with -DFE_REPLAY_TRACE. Every record it
    replays (readable side) then reports the set of readable basic blocks run B reached ("path": a hash of the set).
 2. profile: that build replays every kept record once (one replay.exe per record folder, side by side).
 3. select, per override met with a MATCH record: its records are grouped by input signature =
    (block path, result r0, the capture's path signature, the replay verdict, the entry arguments r0-r3).
    First, a greedy cover: groups are taken
    until every block any of the override's records reached is reached by a kept record ("every met branch keeps at
    least one record"; a block-set difference also tells a taken from a not-taken branch). Then more groups, the
    least-seen path first, then the least-seen result, until N groups (N = --sample-n). One record per group: the one
    whose bytes have the smallest sha256 (content, not folder order: a new route adding a duplicate rarely changes it).
    The cover may need more than N groups: then all of the cover is kept (reported as over N).
 4. one sample folder per readable source file: the kept records of that file's overrides, in sha256 order, in one
    records.fecap, their page files hard-linked (copied if a link is refused) into its pages/. The mutants of that file
    are replayed on that one folder (one replay.exe per mutant instead of one per record folder).
The file's record digest (sha256 of the sorted record sha256s, plus N and RULE) goes into h6cache's key instead of
the record folders, so a round that adds records only for overrides of other files still hits.

    python tools/harness/h6sample.py --selftest
"""
from __future__ import annotations

import collections
import concurrent.futures
import hashlib
import json
import os
import shutil
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import harness as H  # noqa: E402
import mutate  # noqa: E402

rcheck = H.rcheck
RULE = "cover+fill/2"  # bump when the selection rule changes meaning (it is part of the cache key)
DEFAULT_N = 64  # measured on round 10 (H56.md section 9): N=64 cold 42.5 min, 51.1%; N=32 36.7 min, 50.7%
PAGE_HEAD = struct.Struct("<II4I")
PAGE_COPIED = 0x1
ZERO_PATH = "0" * 16


class SampleError(Exception):
    pass


# ------------------------------------------------------------------ 1. trace build
def build_trace(cc: str, out_dir: str, sources: list[str], jobs: int) -> tuple[str | None, str]:
    """replay_trace.exe from the h6 sources (replay.c, readable sources, the overrides table) + h6trace.c."""
    obj = os.path.join(out_dir, "obj")
    os.makedirs(obj, exist_ok=True)
    core = os.path.normcase(os.path.join(ROOT, "src", "readable", "core"))
    srcs = list(dict.fromkeys(sources + [os.path.join(HERE, "h6trace.c")]))

    def one(k_s):
        k, s = k_s
        o = os.path.join(obj, f"{k:03d}_" + os.path.splitext(os.path.basename(s))[0] + ".o")
        flags = list(H.CFLAGS)
        ns = os.path.normcase(os.path.abspath(s))
        if os.path.basename(ns) == "replay.c":
            flags.append("-DFE_REPLAY_TRACE")
        elif ns.startswith(os.path.normcase(os.path.join(ROOT, "src", "readable"))) and not ns.startswith(core):
            flags.append("-fsanitize-coverage=trace-pc")
        rc, out = mutate.run([cc] + flags + H.INCS + ["-c", s, "-o", o], timeout=900)
        return o, ("" if rc == 0 else f"compile {rcheck.rel(s)}:\n{out}")
    with concurrent.futures.ThreadPoolExecutor(max(1, jobs)) as ex:
        res = list(ex.map(one, enumerate(srcs)))
    errs = [e for _o, e in res if e]
    if errs:
        return None, "\n".join(errs)[:4000]
    exe = os.path.join(out_dir, "replay_trace" + H.EXE)
    rc, out = mutate.run([cc] + [o for o, _e in res] + ["-o", exe], timeout=900)
    return (exe, "") if rc == 0 else (None, f"link replay_trace:\n{out[:4000]}")


# ------------------------------------------------------------------ 2. profile
def read_records(path: str) -> list[dict]:
    """Every record of a records.fecap: offset, length, address, kind, sha256 of its bytes, page files it needs."""
    data = open(path, "rb").read()
    out = []
    for off, w in H.records_of(data):
        n = w[2]
        if n < H.HEADER_BYTES or off + n > len(data):
            raise SampleError(f"{rcheck.rel(path)}: record at {off} cut short")
        pages = []
        for i in range(w[12]):
            p = off + H.HEADER_BYTES + i * H.PAGE_BYTES
            _addr, flags, h0, h1, h2, h3 = PAGE_HEAD.unpack_from(data, p)
            if flags & PAGE_COPIED:
                pages.append(f"{h3:08X}{h2:08X}{h1:08X}{h0:08X}.pg")
        args = struct.unpack_from("<4I", data, off + H.HEADER.size)  # entry r0-r3 (FeCapRegs.r[0..3])
        out.append({"off": off, "len": n, "address": f"0x{w[3]:08X}", "kind": w[4],
                    "args": "%08X,%08X,%08X,%08X" % args,
                    "sha": hashlib.sha256(data[off:off + n]).hexdigest(), "pages": pages})
    return out


def profile_one(exe: str, lib: str, d: str, work: str, k: int) -> tuple[list[dict], dict[str, list[int]], str]:
    """(records with their trace, path -> blocks, problem) of one record folder."""
    out = os.path.join(work, f"trace_{k:03d}.jsonl")
    cmd = [exe, "run", "--lib", lib, "--dir", os.path.abspath(d), "--side", "readable", "--out", os.path.abspath(out)]
    wide = H.wide_results()
    if wide:
        cmd += ["--wide", ",".join(wide)]
    rc, text = mutate.run(cmd, {"FE_READABLE": "original", "FE_READABLE_LOG": out + ".log"}, timeout=7200)
    recs = read_records(os.path.join(d, "records.fecap"))
    rows, blocks = [], {}
    if os.path.isfile(out):
        with open(out, encoding="utf-8") as fh:
            rows = [json.loads(ln) for ln in fh if ln.strip()]
    for f in (out, out + ".log"):
        if os.path.isfile(f):
            os.remove(f)
    if rc != 0:
        return [], {}, f"{rcheck.rel(d)}: trace replay rc {rc}: {text[-300:]}"
    if len(rows) != len(recs):
        return [], {}, f"{rcheck.rel(d)}: {len(rows)} trace row(s) for {len(recs)} record(s)"
    for rec, row in zip(recs, rows):
        if row["address"].upper().replace("0X", "0x") != rec["address"]:
            return [], {}, f"{rcheck.rel(d)}: trace row {row['address']} for record {rec['address']} at {rec['off']}"
        if "blocks" in row:
            blocks[row["path"]] = [int(x, 16) for x in row["blocks"]]
        rec.update(folder=d, path=row.get("path", ZERO_PATH), full=bool(row.get("trace_full")), r0=row.get("r0"),
                   signature=row.get("signature"), verdict=row.get("verdict"),
                   probe=row.get("kind") == "probe")
    return recs, blocks, ""


def profile(exe: str, lib: str, dirs: list[str], work: str, jobs: int) -> tuple[list[dict], dict, list[str]]:
    os.makedirs(work, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max(1, jobs)) as ex:
        res = list(ex.map(lambda kd: profile_one(exe, lib, kd[1], work, kd[0]), enumerate(dirs)))
    recs, blocks, problems = [], {}, []
    for r, b, p in res:
        recs += r
        blocks.update(b)
        if p:
            problems.append(p)
    return recs, blocks, problems


# ------------------------------------------------------------------ 3. select
def group_key(r: dict) -> tuple:
    return (r["path"], r.get("r0"), r.get("signature"), r.get("verdict"), r.get("args"))


def select(recs: list[dict], blocks: dict[str, list[int]], n: int) -> tuple[list[dict], dict]:
    """The kept records of ONE override (see the module text). Returns (records, stats)."""
    groups: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in recs:
        groups[group_key(r)].append(r)
    rep = {k: min(v, key=lambda r: r["sha"]) for k, v in groups.items()}
    order = sorted(groups, key=lambda k: rep[k]["sha"])  # deterministic, content-based
    bset = {k: set(blocks.get(k[0], ())) for k in order}
    universe = set().union(*bset.values()) if bset else set()
    chosen: list[tuple] = []
    covered: set[int] = set()
    # a cut trace (more blocks than h6trace.c holds) is always kept: its set is not complete
    for k in order:
        if any(r.get("full") for r in groups[k]):
            chosen.append(k)
            covered |= bset[k]
    while covered != universe:
        best = max((k for k in order if k not in chosen), key=lambda k: len(bset[k] - covered), default=None)
        if best is None or not bset[best] - covered:
            break
        chosen.append(best)
        covered |= bset[best]
    cover_n = len(chosen)
    seen_path = collections.Counter(k[0] for k in chosen)
    seen_r0 = collections.Counter(k[1] for k in chosen)
    rest = [k for k in order if k not in chosen]
    while len(chosen) < n and rest:
        rank = {k: i for i, k in enumerate(rest)}
        k = min(rest, key=lambda k: (seen_path[k[0]], seen_r0[k[1]], rank[k]))
        rest.remove(k)
        chosen.append(k)
        seen_path[k[0]] += 1
        seen_r0[k[1]] += 1
    kept = [rep[k] for k in chosen]
    return kept, {"records": len(recs), "signatures": len(groups), "kept": len(kept), "cover": cover_n,
                  "over_n": cover_n > n, "blocks": len(universe),
                  "blocks_kept": len(set().union(*(bset[k] for k in chosen)))}


# ------------------------------------------------------------------ 4. sample folders
def link_or_copy(src: str, dst: str) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def write_folder(d: str, kept: list[dict], meta: dict) -> str:
    """records.fecap (kept records in sha256 order) + pages/ + run.json; returns the record digest."""
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "pages"))
    kept = sorted({r["sha"]: r for r in kept}.values(), key=lambda r: r["sha"])
    by_folder = collections.defaultdict(list)
    for r in kept:
        by_folder[r["folder"]].append(r)
    chunks = {}
    for folder, rs in by_folder.items():
        with open(os.path.join(folder, "records.fecap"), "rb") as fh:
            for r in sorted(rs, key=lambda r: r["off"]):
                fh.seek(r["off"])
                b = fh.read(r["len"])
                if hashlib.sha256(b).hexdigest() != r["sha"]:
                    raise SampleError(f"{rcheck.rel(folder)}: record at {r['off']} changed since the profile")
                chunks[r["sha"]] = b
        have = set()
        for r in rs:
            for p in r["pages"]:
                dst = os.path.join(d, "pages", p)
                if p not in have and not os.path.exists(dst):
                    link_or_copy(os.path.join(folder, "pages", p), dst)
                have.add(p)
    tmp = os.path.join(d, "records.fecap.tmp")
    with open(tmp, "wb") as fh:
        for r in kept:
            fh.write(chunks[r["sha"]])
    os.replace(tmp, os.path.join(d, "records.fecap"))
    digest = record_digest([r["sha"] for r in kept], meta.get("n"))
    with open(os.path.join(d, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(meta, route="h6-sample", records=len(kept), digest=digest,
                       sampled_from=sorted({rcheck.rel(r["folder"]) for r in kept})), fh, indent=1)
    return digest


def record_digest(shas: list[str], n) -> str:
    return hashlib.sha256(json.dumps({"rule": RULE, "n": n, "records": sorted(shas)}).encode()).hexdigest()


# ------------------------------------------------------------------ the whole step, for h56.py
def make_samples(cc: str, lib: str, dirs: list[str], by_file: dict, sources: list[str], work: str, jobs: int,
                 n: int, label: str = "", say=print) -> dict:
    """{"folders": {source: folder}, "digests": {source: digest}, "per_function": {...}, "seconds": {...}}."""
    t0 = time.time()
    exe, err = build_trace(cc, os.path.join(work, "trace"), sources, jobs)
    if exe is None:
        raise SampleError(err)
    t1 = time.time()
    recs, blocks, problems = profile(exe, lib, dirs, os.path.join(work, "trace"), jobs)
    if problems:
        raise SampleError("; ".join(problems[:4]))
    t2 = time.time()
    by_addr = collections.defaultdict(list)
    for r in recs:
        if not r["probe"]:
            by_addr[r["address"]].append(r)
    folders, digests, per_fn = {}, {}, {}
    for src, targets in sorted(by_file.items()):
        kept = []
        for t in targets:
            k, st = select(by_addr.get(t.address, []), blocks, n)
            per_fn[t.function] = dict(st, address=t.address, source=src)
            kept += k
        if not kept:
            continue
        stem = os.path.splitext(os.path.basename(src))[0]
        d = os.path.join(work, "files", stem)
        digests[src] = write_folder(d, kept, {"label": label, "n": n, "rule": RULE, "source": src,
                                              "functions": [t.function for t in targets]})
        folders[src] = d
    shutil.rmtree(os.path.join(work, "trace"), ignore_errors=True)
    t3 = time.time()
    tot = sum(s["records"] for s in per_fn.values())
    kept_n = sum(s["kept"] for s in per_fn.values())
    say(f"h6 sample: N={n}, rule {RULE}: {kept_n} of {tot} record(s) kept over {len(per_fn)} override(s) in "
        f"{len(folders)} file folder(s); cover over N for {sum(1 for s in per_fn.values() if s['over_n'])}; "
        f"distinct paths {len(blocks)}; trace build {t1 - t0:.0f} s, profile {t2 - t1:.0f} s, select+write "
        f"{t3 - t2:.0f} s")
    return {"folders": folders, "digests": digests, "per_function": per_fn,
            "seconds": {"trace_build": round(t1 - t0, 1), "profile": round(t2 - t1, 1), "select": round(t3 - t2, 1)},
            "records_total": tot, "records_kept": kept_n, "n": n, "rule": RULE}


# ------------------------------------------------------------------ self-test
def selftest() -> int:
    errors, n_ok = [], 0

    def ok(cond, what):
        nonlocal n_ok
        n_ok += 1
        if not cond:
            errors.append(what)

    def rec(sha, path, r0="0", sig="1", verdict="match", args="0"):
        return {"sha": sha, "path": path, "r0": r0, "signature": sig, "verdict": verdict, "full": False,
                "args": args}

    blocks = {"pA": [1, 2], "pB": [1, 3], "pC": [1, 2, 3, 4], "pD": [1]}
    recs = [rec("05", "pA"), rec("01", "pA"), rec("02", "pB"), rec("03", "pD"), rec("04", "pD", r0="7")]
    kept, st = select(recs, blocks, 1)
    ks = {r["sha"] for r in kept}
    ok(st["cover"] == 2 and ks == {"01", "02"} and st["over_n"],
       f"cover keeps a record of every block (1,2 and 3) even over N, the smallest sha per group ({ks}, {st})")
    ok(st["blocks"] == 3 and st["blocks_kept"] == 3, f"every met block kept ({st})")
    kept, st = select(recs, blocks, 4)
    ks = [r["sha"] for r in kept]
    ok(len(ks) == 4 and "03" in ks and "04" in ks, f"fill to N with the other signatures ({ks})")
    kept, st = select(recs, blocks, 50)
    ok(len(kept) == 4 and st["signatures"] == 4, f"never more than one record per signature ({st})")
    k1, _ = select(recs, blocks, 3)
    k2, _ = select(list(reversed(recs)), blocks, 3)
    ok([r["sha"] for r in k1] == [r["sha"] for r in k2], "the sample does not depend on record order")
    # rule 2: the entry arguments are part of the input signature (round 10: ai_value_is_argument-000 was caught
    # only by a record whose path, result and signature equalled a kept one's, with other arguments)
    recs3 = [rec("01", "pA"), rec("02", "pA", args="5"), rec("03", "pA", args="6")]
    kept, st = select(recs3, blocks, 2)
    ok(st["signatures"] == 3 and len(kept) == 2, f"other arguments, same path and result: another signature ({st})")
    # planted bug check: the greedy cover must take pC (blocks 1-4) over pA+pB when it alone covers all
    recs2 = [rec("01", "pA"), rec("02", "pB"), rec("09", "pC")]
    kept, st = select(recs2, blocks, 1)
    ok([r["sha"] for r in kept] == ["09"] and st["cover"] == 1, f"greedy cover takes the widest path first ({st})")
    full = dict(rec("08", "pD"), full=True)
    kept, st = select([full] + recs2, blocks, 1)
    ok("08" in {r["sha"] for r in kept}, "a cut trace is always kept")
    ok(record_digest(["b", "a"], 8) == record_digest(["a", "b"], 8) != record_digest(["a", "b"], 9),
       "record digest: order-free, N counts")
    # sample folder: two invented records from two folders, pages linked, sha order, digest
    import tempfile
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build")) as t:
        made = []
        for k in range(2):
            f = os.path.join(t, f"run{k}")
            os.makedirs(os.path.join(f, "pages"))
            words = [1, H.HEADER.size + 2 * H.REGS_BYTES, 0, 0x00200000 + k, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0, 0, 0]
            words[2] = H.HEADER_BYTES + H.PAGE_BYTES
            head = H.HEADER.pack(b"FECAPREC", *words) + bytes(2 * H.REGS_BYTES)
            page = PAGE_HEAD.pack(0x1000, PAGE_COPIED, k + 1, 0, 0, 0xAB) + bytes(H.PAGE_BYTES - PAGE_HEAD.size)
            with open(os.path.join(f, "records.fecap"), "wb") as fh:
                fh.write(head + page)
            pg = f"000000AB0000000000000000{k + 1:08X}.pg"
            with open(os.path.join(f, "pages", pg), "wb") as fh:
                fh.write(bytes([k]) * 4096)
            r = read_records(os.path.join(f, "records.fecap"))
            ok(len(r) == 1 and r[0]["pages"] == [pg] and r[0]["address"] == f"0x{0x00200000 + k:08X}"
               and r[0]["args"] == "00000000,00000000,00000000,00000000",
               f"read_records ({r})")
            made.append(dict(r[0], folder=f))
        d = os.path.join(t, "sample")
        dg = write_folder(d, made, {"n": 8})
        back = read_records(os.path.join(d, "records.fecap"))
        ok([x["sha"] for x in back] == sorted(x["sha"] for x in made), "the sample folder holds the records in sha order")
        ok(sorted(os.listdir(os.path.join(d, "pages"))) == sorted(x["pages"][0] for x in made), "pages linked")
        ok(dg == record_digest([x["sha"] for x in made], 8), "write_folder returns the record digest")
        dg2 = write_folder(os.path.join(t, "sample2"), list(reversed(made)), {"n": 8})
        ok(dg2 == dg and open(os.path.join(t, "sample2", "records.fecap"), "rb").read() ==
           open(os.path.join(d, "records.fecap"), "rb").read(), "the same records give the same folder bytes")
        with open(os.path.join(made[0]["folder"], "records.fecap"), "r+b") as fh:
            fh.seek(100)
            fh.write(b"\xff")
        try:
            write_folder(os.path.join(t, "sample3"), made, {"n": 8})
            ok(False, "a record changed since the profile is refused")
        except SampleError:
            ok(True, "")
    for e in errors:
        print(f"  FAIL  {e}")
    print(f"h6sample self-test: {n_ok - len(errors)}/{n_ok} checks passed")
    return 1 if errors else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    print(__doc__)
    sys.exit(2)
