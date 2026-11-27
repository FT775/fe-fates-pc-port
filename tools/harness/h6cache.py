#!/usr/bin/env python3
"""H6 result cache (owner OK A, docs/collab/SPEED_AGREED.md): one entry per readable source file, holding every
mutant's verdict row of a clean `mutate.mutate` run. `h56.py h6` reuses the rows when the key is equal, so a round
that did not change a file (or anything it depends on) does not re-mutate it. Standard library only.

Key of a file = sha256 over, as JSON:
  env   the code of h56.py, harness.py, mutate.py, this file, replay.c, replay_abi.h; the compiler's `--version` and
        `-dumpmachine`; the compile flags and include folders; the mutant operator set (OPS_VERSION, mutate.MUTANT_CAP);
        mutants_equivalent.csv; the library the original side runs (its bytes)
  file  the raw source; its preprocessed text (`cc -E -P` with the build's flags, so every header it includes counts);
        the preprocessed text of every readable file it can call into (transitively, by name) plus src/readable/core/
        and replay.c; the overrides mutated (name, address); the mutant list (id, operator, line, column, old, new and
        the mutated text); the record folders replayed (every file's name, size and bytes), or, in the sampled mode
        (`h56.py h6 --sample`, h6sample.py), the digest of the file's SAMPLED records instead: sha256 of the sorted
        sha256s of the kept records of the file's overrides, the sample size N and the selection rule. A record's bytes
        name its page files by their hash (and replay.exe checks every page against it), so the digest pins the pages
        too. The sample folder's own path is not in the key: a round that adds records only for overrides of OTHER
        files keeps this file's sample, and hits.
A hit needs the same key AND an entry younger than MAX_AGE_DAYS (7): a file is re-mutated at least once a week even
when nothing changed (Grok: clean once a week and on any compiler or harness change; a compiler or harness change is
a key change, so it is always a miss). `--no-cache` runs every file cold and refreshes the entries.

On a miss the last entry of the same file is compared part by part, so the summary says WHY: tools, compiler, flags,
operators, equivalents, library, source, headers (preprocessed text changed, raw source did not), deps:<file>,
targets, mutants, records, too old. Entries are written atomically (temp file, then rename).

    python tools/harness/h6cache.py --selftest
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_DIR = os.path.join(ROOT, "build", "harness", "h56", "h6cache")
MAX_AGE_DAYS = 7.0
OPS_VERSION = "rel,arith,const,named,field,swap,drop,giveup/1"  # bump when mutate.py's operators change meaning
FORMAT = 1
TOOL_FILES = ("h56.py", "harness.py", "mutate.py", "h6cache.py", "h6sample.py", "h6trace.c", "replay.c",
              "replay_abi.h")
DEF_RX = re.compile(r"^[A-Za-z_][\w \t\*]*?\b([A-Za-z_]\w*)\s*\(", re.M)
CALL_RX = re.compile(r"\b([A-Za-z_]\w*)\s*\(")


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def nk(p: str) -> str:
    """One spelling of a path (registry sources are relative with '/', readable_sources absolute with '\')."""
    return os.path.normcase(os.path.abspath(p))


def rel(p: str) -> str:
    try:
        return os.path.relpath(p, ROOT).replace("\\", "/")
    except ValueError:
        return p.replace("\\", "/")


def folder_digest(d: str) -> str:
    """Every file below d: relative name, size and bytes (records, summary, run.json, pages)."""
    h = hashlib.sha256()
    for base, dirs, files in os.walk(d):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(base, f)
            h.update(f"{os.path.relpath(p, d)}\0{os.path.getsize(p)}\0{sha_file(p)}\n".encode())
    return h.hexdigest()


def cc_env(cc: str) -> dict:
    """The compiler's own folder first on PATH (as mutate.run does): MSYS2 gcc needs its DLLs and cc1."""
    env = dict(os.environ)
    if os.path.isabs(cc):
        env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    return env


def compiler_id(cc: str) -> str:
    out = []
    for arg in ("--version", "-dumpmachine"):
        try:
            r = subprocess.run([cc, arg], capture_output=True, text=True, timeout=60, env=cc_env(cc))
            out.append((r.stdout + r.stderr).strip())
        except (OSError, subprocess.TimeoutExpired) as e:
            out.append(f"error: {e}")
    return "\n".join(out)


def preprocess(cc: str, cflags: list[str], incs: list[str], src: str) -> str:
    """sha256 of `cc -E -P` of src with the build's flags (headers count); 'error: ...' if it does not preprocess."""
    fl = [f for f in cflags if f not in ("-Werror",)]
    try:
        r = subprocess.run([cc] + fl + ["-I", os.path.dirname(src)] + incs + ["-E", "-P", src],
                           capture_output=True, timeout=300, env=cc_env(cc))
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"error: {e}"
    if r.returncode:
        return "error: " + sha_bytes(r.stdout + r.stderr)
    return sha_bytes(r.stdout)


def strip(text: str) -> str:
    """Comments blanked (strings kept: a name in a string is harmless here, it only adds a dependency)."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)


def has_body(code: str, open_paren: int) -> bool:
    """A definition, not a prototype: the parameter list is followed by '{'."""
    depth = 0
    for i in range(open_paren, len(code)):
        if code[i] == "(":
            depth += 1
        elif code[i] == ")":
            depth -= 1
            if depth == 0:
                return code[i + 1:].lstrip()[:1] == "{"
    return False


def file_deps(sources: list[str], always: list[str]) -> dict[str, list[str]]:
    """source -> every source it can reach by calling a name defined there (transitively), itself first, then
    `always` (core machinery, replay.c). By name only, so it over-counts (a static of the same name elsewhere),
    never under-counts a direct call; calls through function pointers are covered by `always` only."""
    defined: dict[str, set[str]] = {}
    calls: dict[str, set[str]] = {}
    for s in sources:
        code = strip(open(s, encoding="utf-8", errors="replace").read())
        for m in DEF_RX.finditer(code):
            if has_body(code, m.end() - 1):
                defined.setdefault(m.group(1), set()).add(s)
        calls[s] = {m.group(1) for m in CALL_RX.finditer(code)}
    direct = {s: {f for n in calls[s] for f in defined.get(n, ()) if f != s} for s in sources}
    out = {}
    for s in sources:
        seen, todo = [s], [s]
        while todo:
            for f in sorted(direct.get(todo.pop(), ())):
                if f not in seen:
                    seen.append(f)
                    todo.append(f)
        out[s] = seen + [a for a in always if a not in seen]
    return out


class Cache:
    def __init__(self, cc: str, cflags: list[str], incs: list[str], lib: str, all_sources: list[str],
                 core: list[str], cache_dir: str = DEFAULT_DIR, enabled: bool = True, jobs: int = 2,
                 tool_dir: str = HERE, equiv: str | None = None, ops: str = OPS_VERSION, cap: int = 0,
                 now: float | None = None):
        self.dir, self.enabled, self.now = cache_dir, enabled, now
        self.hits, self.misses, self.reasons, self.reused = 0, 0, {}, 0
        self.store_errors: dict[str, str] = {}  # round 9: a failed store warns and keeps the h6 result
        tools = {f: sha_file(os.path.join(tool_dir, f)) for f in TOOL_FILES if os.path.isfile(os.path.join(tool_dir, f))}
        self.env = {"format": FORMAT, "tools": tools, "compiler": sha_bytes(compiler_id(cc).encode()),
                    "flags": list(cflags) + [rel(x) if os.path.isabs(x) else x for x in incs],
                    "operators": f"{ops};cap={cap}",
                    "equivalents": sha_file(equiv) if equiv and os.path.isfile(equiv) else None,
                    "library": sha_file(lib) if lib and os.path.isfile(lib) else None}
        all_sources, core = [nk(x) for x in all_sources], [nk(x) for x in core]
        srcs = list(dict.fromkeys(all_sources + core))
        with concurrent.futures.ThreadPoolExecutor(max(1, jobs)) as ex:
            pp = list(ex.map(lambda s: preprocess(cc, cflags, incs, s), srcs))
        self.pre = dict(zip(srcs, pp))
        self.raw = {s: sha_file(s) for s in srcs}
        self.deps = file_deps([s for s in all_sources if s not in core], core)
        self._folders: dict[str, str] = {}

    def folder(self, d: str) -> str:
        if d not in self._folders:
            self._folders[d] = folder_digest(d)
        return self._folders[d]

    def parts(self, src: str, targets: list[tuple[str, str]], mutants: list[tuple], runs: list[str],
              sampled: dict | None = None) -> dict:
        """sampled: {"digest", "n", "rule"} of the file's sampled records (h56.py h6 --sample); it replaces the
        record folders in the key (their paths change every run; their content is what the digest says)."""
        src = nk(src)
        deps = self.deps.get(src, [src])
        return {"env": self.env,
                "source": self.raw.get(src) or sha_file(src),
                "preprocessed": self.pre.get(src) or "not a readable source: " + self.raw.get(src, sha_file(src)),
                "deps": {rel(d): self.pre.get(d) for d in deps if d != src},
                "targets": [list(t) for t in sorted(targets)],
                "mutants": sha_bytes(json.dumps(mutants, sort_keys=True).encode()),
                "records": ({"sampled": dict(sampled)} if sampled is not None
                            else {rel(r): self.folder(r) for r in runs})}

    @staticmethod
    def key(parts: dict) -> str:
        return sha_bytes(json.dumps(parts, sort_keys=True).encode())

    def path(self, src: str, key: str = "") -> str:
        src = nk(src)
        stem = re.sub(r"[^A-Za-z0-9_.]", "_", rel(src))
        return os.path.join(self.dir, stem, (key or "latest") + ".json")

    def lookup(self, src: str, parts: dict) -> tuple[list[dict] | None, str]:
        """(rows, '') on a hit; (None, why) on a miss."""
        k = self.key(parts)
        why = ""
        if not self.enabled:
            why = "--no-cache"
        else:
            p = self.path(src, k)
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as fh:
                        e = json.load(fh)
                except (OSError, ValueError):
                    e = None
                age = ((self.now or time.time()) - e["created"]) / 86400.0 if e else 1e9
                if e and e.get("key") == k and age <= MAX_AGE_DAYS:
                    self.hits += 1
                    self.reused += len(e["rows"])
                    return e["rows"], ""
                why = f"too old ({age:.1f} days)" if e else "unreadable entry"
            else:
                why = self.diff(src, parts)
        self.misses += 1
        self.reasons[rel(src)] = why
        return None, why

    def diff(self, src: str, parts: dict) -> str:
        p = self.path(src)
        if not os.path.isfile(p):
            return "no entry"
        try:
            with open(p, encoding="utf-8") as fh:
                old = json.load(fh)["parts"]
        except (OSError, ValueError, KeyError):
            return "no readable entry"
        out = []
        for k in ("tools", "compiler", "flags", "operators", "equivalents", "library", "format"):
            if old["env"].get(k) != parts["env"].get(k):
                out.append(k if k != "tools" else "tools(" + ",".join(
                    sorted(f for f in set(old["env"]["tools"]) | set(parts["env"]["tools"])
                           if old["env"]["tools"].get(f) != parts["env"]["tools"].get(f))) + ")")
        if old["source"] != parts["source"]:
            out.append("source")
        elif old["preprocessed"] != parts["preprocessed"]:
            out.append("headers")
        for d in sorted(set(old["deps"]) | set(parts["deps"])):
            if old["deps"].get(d) != parts["deps"].get(d):
                out.append("deps:" + d)
        for k in ("targets", "mutants", "records"):
            if old[k] != parts[k]:
                out.append(k)
        return ("changed: " + ", ".join(out)) if out else "changed: unknown"

    def store(self, src: str, parts: dict, rows: list[dict], seconds: float, warn=None) -> bool:
        """Keep one file's verdicts. Never raises (round 9): a full disk, a locked or unwritable folder or rows that
        cannot be written are a warning; the h6 run keeps its result, the file is simply not cached."""
        try:
            k = self.key(parts)
            e = {"key": k, "created": self.now or time.time(), "source": rel(src), "parts": parts, "rows": rows,
                 "seconds": seconds}
            text = json.dumps(e, indent=0)
            for p in (self.path(src, k), self.path(src)):
                write_atomic(p, text)
            return True
        except Exception as ex:  # noqa: BLE001  the cache is an extra; never the reason an h6 run fails
            msg = f"{type(ex).__name__}: {ex}"
            self.store_errors[rel(src)] = msg
            (warn or (lambda s: print(s, file=sys.stderr, flush=True)))(
                f"h6cache: WARNING: could not store {rel(src)} ({msg}); result kept, not cached")
            return False

    def summary(self) -> dict:
        return {"enabled": self.enabled, "hits": self.hits, "misses": self.misses, "mutants_reused": self.reused,
                "miss_reasons": dict(sorted(self.reasons.items())), "dir": rel(self.dir),
                "store_errors": dict(sorted(self.store_errors.items()))}


def write_atomic(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def selftest() -> int:
    errors, n = [], 0

    def ok(cond, what):
        nonlocal n
        n += 1
        if not cond:
            errors.append(what)

    sys.path.insert(0, HERE)
    import harness as H  # noqa: E402
    cc = H.rcheck.find_cc()
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.join(ROOT, "build")) as t:
        inc = os.path.join(t, "inc")
        os.makedirs(inc)
        hdr = os.path.join(inc, "k.h")
        with open(hdr, "w") as fh:
            fh.write("#define K 3\n")
        a, b, c, core = (os.path.join(t, x) for x in ("a.c", "b.c", "c.c", "core.c"))
        with open(a, "w") as fh:
            fh.write('#include "k.h"\nint b1(int);\nint a1(int x) {\n  return b1(x) + K;\n}\n')
        with open(b, "w") as fh:
            fh.write("int b1(int x) {\n  return x * 2; /* c1( in a comment */\n}\n")
        with open(c, "w") as fh:
            fh.write("int c1(int x) {\n  return x;\n}\n")
        with open(core, "w") as fh:
            fh.write("int rt(void) {\n  return 0;\n}\n")
        recs = os.path.join(t, "recs")
        os.makedirs(recs)
        with open(os.path.join(recs, "records.fecap"), "wb") as fh:
            fh.write(b"\x01\x02")
        tools = os.path.join(t, "tools")
        os.makedirs(tools)
        for f in TOOL_FILES:
            with open(os.path.join(tools, f), "w") as fh:
                fh.write(f)
        deps = file_deps([a, b, c], [core])
        ok(deps[a] == [a, b, core] and deps[b] == [b, core] and deps[c] == [c, core], f"file deps ({deps})")
        cdir = os.path.join(t, "cache")
        now = 1_000_000.0

        def mk(**kw):
            if not cc:
                return None
            return Cache(cc, ["-O1"], ["-I", inc], "", [a, b, c], [core], cdir, jobs=2, tool_dir=tools,
                         now=kw.get("now", now), enabled=kw.get("enabled", True))
        if not cc:
            print("h6cache self-test: no host C compiler; key checks skipped")
        else:
            rows = [{"id": "m1", "result": "caught"}, {"id": "m2", "result": "survived"}]
            muts = [("m1", "rel", 4, 10, "+", "-"), ("m2", "const", 4, 18, "K", "K+1")]
            x = mk()
            pa = x.parts(a, [("a1", "0x1000")], muts, [recs])
            r, why = x.lookup(a, pa)
            ok(r is None and why == "no entry", f"first lookup misses ({why})")
            x.store(a, pa, rows, 1.0)
            r, why = mk().lookup(a, pa)
            ok(r == rows, f"same key hits ({why})")
            y = mk(now=now + 8 * 86400)
            r, why = y.lookup(a, y.parts(a, [("a1", "0x1000")], muts, [recs]))
            ok(r is None and why.startswith("too old"), f"an entry older than 7 days is refused ({why})")
            r, why = mk(enabled=False).lookup(a, pa)
            ok(r is None and why == "--no-cache", "--no-cache never hits")
            with open(hdr, "w") as fh:
                fh.write("#define K 4\n")
            z = mk()
            r, why = z.lookup(a, z.parts(a, [("a1", "0x1000")], muts, [recs]))
            ok(r is None and why == "changed: headers", f"a header change misses as 'headers' ({why})")
            pb = z.parts(b, [("b1", "0x2000")], [], [recs])
            z.store(b, pb, rows, 1.0)
            with open(hdr, "w") as fh:
                fh.write("#define K 3\n")
            r, why = mk().lookup(b, mk().parts(b, [("b1", "0x2000")], [], [recs]))
            ok(r == rows, f"a header b.c does not include does not touch b.c ({why})")
            with open(b, "a") as fh:
                fh.write("int b2(void) {\n  return 1;\n}\n")
            w = mk()
            r, why = w.lookup(a, w.parts(a, [("a1", "0x1000")], muts, [recs]))
            ok(r is None and "deps:" in why and "b.c" in why, f"a callee file change misses ({why})")
            with open(os.path.join(recs, "records.fecap"), "ab") as fh:
                fh.write(b"\x03")
            with open(os.path.join(tools, "mutate.py"), "a") as fh:
                fh.write("#")
            v = mk()
            r, why = v.lookup(c, v.parts(c, [("c1", "0x3000")], [], [recs]))
            ok(r is None and why == "no entry", "another file's entry is not used")
            v.store(c, v.parts(c, [("c1", "0x3000")], [], [recs]), rows, 1.0)
            with open(os.path.join(tools, "harness.py"), "a") as fh:
                fh.write("#")
            u = mk()
            r, why = u.lookup(c, u.parts(c, [("c1", "0x3000")], muts, [recs]))
            ok(r is None and "tools(harness.py)" in why and "mutants" in why, f"a harness change misses ({why})")
            s = u.summary()
            ok(s["misses"] == 1 and s["hits"] == 0 and rel(c) in s["miss_reasons"], f"summary ({s})")
            leftovers = [f for _, _, fs in os.walk(cdir) for f in fs if f.startswith(".tmp-")]
            ok(not leftovers, "no temp file left by the atomic writes")
            # round 9: a store that cannot write warns and returns False; it never raises
            said = []
            blocked = os.path.join(t, "blocked")
            open(blocked, "w").close()  # a file where the cache folder should be
            tc = mk()
            tc.dir = blocked
            try:
                got = tc.store(c, tc.parts(c, [("c1", "0x3000")], [], [recs]), rows, 1.0, warn=said.append)
                ok(got is False and said and "WARNING" in said[0], "a failed store warns and returns False")
                ok(rel(c) in tc.summary()["store_errors"], "a failed store is listed in the summary")
            except Exception as ex:  # noqa: BLE001
                ok(False, f"a failed store raised {ex!r}")
            got = tc.store(c, {"env": object()}, rows, 1.0, warn=said.append)
            ok(got is False, "rows/parts that cannot be written: store returns False")
            # sampled mode (F-024): the key holds the sampled-record digest, not the folders
            sm = mk()
            s1 = {"digest": "d1", "n": 8, "rule": "r"}
            other = os.path.join(t, "recs_other")
            os.makedirs(other)
            with open(os.path.join(other, "records.fecap"), "wb") as fh:
                fh.write(b"\x09")
            ps = sm.parts(b, [("b1", "0x2000")], [], [recs], sampled=s1)
            r, why = sm.lookup(b, ps)
            ok(r is None, f"sampled: first lookup misses ({why})")
            sm.store(b, ps, rows, 1.0)
            with open(os.path.join(recs, "records.fecap"), "ab") as fh:
                fh.write(b"\x05")  # more records in the folders (other functions'): the sample of b is the same
            sm2 = mk()
            r, why = sm2.lookup(b, sm2.parts(b, [("b1", "0x2000")], [], [recs, other], sampled=dict(s1)))
            ok(r == rows, f"sampled: same sampled records, other records added: a hit ({why})")
            r, why = sm2.lookup(b, sm2.parts(b, [("b1", "0x2000")], [], [recs], sampled=dict(s1, digest="d2")))
            ok(r is None and why == "changed: records", f"sampled: another sample of b misses as records ({why})")
            r, why = sm2.lookup(b, sm2.parts(b, [("b1", "0x2000")], [], [recs], sampled=dict(s1, n=9)))
            ok(r is None and why == "changed: records", f"sampled: another N misses ({why})")
            r, why = sm2.lookup(b, sm2.parts(b, [("b1", "0x2000")], [], [recs]))
            ok(r is None, f"sampled and full keys never mix ({why})")
    for e in errors:
        print(f"  FAIL  {e}")
    print(f"h6cache self-test: {n - len(errors)}/{n} checks passed")
    return 1 if errors else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    print(__doc__)
    sys.exit(2)
