#!/usr/bin/env python3
"""testcache: the row-result cache of tools/check_all.py (docs/CHECK_ALL.md, owner item A).

A PASS of a pure host test (the readable comparisons and their planted-bug passes) is stored
under a key that is the sha256 of EVERY declared input of the row:

  * the row definition (command, environment, required/rejected lines, note patterns, needs)
  * every file the row declares (its test script, every source and header it can compile, the
    helper modules it imports, the ARM bytes extracted/text.bin + code.bin), each by sha256
  * the host C compiler: path, resolved path, `--version`, `-dumpmachine`, sha256 of the binary
  * the Python version, and the FE_* environment variables
  * the harness: tools/check_all.py and tools/testcache.py (a change to either changes every key)

A row is cached only if its declared input list is shown COMPLETE (completeness()):
  1. every module its scripts import (stdlib aside) resolves to a declared file;
  2. every repository path its scripts spell (os.path.join(ROOT, "src", "readable"), Path / ...)
     lies inside the declared files (a directory must be declared whole);
  3. the C preprocessor (cc -MM -MG) over every .c of the declared source folders names only
     declared files as dependencies (a header outside the list, or one it cannot find, fails).
Any problem: the row is "uncacheable" and always runs.

A hit needs: the same key; an entry younger than 7 days; and a clean run of that row (check_all
--no-cache) recorded within 7 days with the same compiler and harness digests. A compiler or
harness change therefore refuses every hit until the next clean run. Only PASS results are
stored; FAIL, KNOWN and SKIP always run again.

    python tools/testcache.py status [--dir DIR]     entries, ages, the last clean run per row
    python tools/testcache.py clear  [--dir DIR]     delete every entry and the clean record
    python tools/testcache.py selftest               the 7-day age refusals on a made-up cache (temp folder)

Standard library only. Every write is a temp file + rename (a reader never sees half a file).
"""
from __future__ import annotations

import argparse
import ast
import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

FORMAT = 1
MAX_AGE_S = 7 * 24 * 3600          # entries and clean runs older than a week give no hit
TOPS = ("src", "include", "tools", "config", "extracted", "engine", "play", "mods", "asm", "data", "tests")
HERE = Path(__file__).resolve().parent
_HASH_MEMO: dict[tuple, str] = {}
_C_MEMO: dict[tuple, tuple] = {}
_MEMO_LOCK = threading.Lock()


# ------------------------------------------------------------------ small helpers
def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(p: Path) -> str:
    st = p.stat()
    memo = (str(p), st.st_size, st.st_mtime_ns)
    with _MEMO_LOCK:
        if memo in _HASH_MEMO:
            return _HASH_MEMO[memo]
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    d = h.hexdigest()
    with _MEMO_LOCK:
        _HASH_MEMO[memo] = d
    return d


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def expand(root: Path, patterns: list[str]) -> list[str]:
    """Declared files, sorted repo-relative posix paths. "dir/**" = every file below dir;
    other patterns are globs. __pycache__ and .pyc are never inputs.

    Round 85 (plan section 4 item 4): paths are made relative WITHOUT resolving links, so a declared folder that
    is a junction or symlink (extracted/ pointing at another drive) keeps its repository path. A glob that reaches
    outside the root ("../x") keeps its "../" path (still hashed by content through root / path); on another drive
    the absolute path is kept. Never a crash."""
    out = set()
    root_abs = os.path.abspath(root)
    for pat in patterns:
        if pat.endswith("/**"):
            base = root / pat[:-3]
            if base.is_dir():
                for dp, dn, fn in os.walk(base):
                    dn[:] = sorted(d for d in dn if d != "__pycache__")
                    for f in fn:
                        if not f.endswith(".pyc"):
                            out.add(Path(dp, f).relative_to(root).as_posix())
            continue
        for p in glob.glob(str(root / pat)):
            if os.path.isfile(p):
                a = os.path.abspath(p)
                try:
                    rel = os.path.relpath(a, root_abs)
                except ValueError:          # another drive (Windows): keep the absolute path
                    rel = a
                out.add(Path(rel).as_posix())
    return sorted(out)


def recursive_roots(patterns: list[str]) -> list[str]:
    return [p[:-3].rstrip("/") for p in patterns if p.endswith("/**")]


def covered(path: str, files: set[str], roots: list[str]) -> bool:
    path = path.strip("/")
    return path in files or any(path == r or path.startswith(r + "/") for r in roots)


# ------------------------------------------------------------------ the compiler
_CC_MEMO: dict[str, dict] = {}


def cc_env(cc: str) -> dict:
    """The environment with the compiler's own folder first on PATH (MSYS2 gcc needs its DLLs)."""
    env = dict(os.environ)
    exe = cc if os.path.isfile(cc) else shutil.which(cc)
    if exe:
        env["PATH"] = os.path.dirname(os.path.abspath(exe)) + os.pathsep + env.get("PATH", "")
    return env


def compiler_identity(cc: str | None) -> dict:
    """Path, resolved path, --version, -dumpmachine and the binary's sha256 (or 'none')."""
    if not cc:
        return {"cc": None}
    with _MEMO_LOCK:
        if cc in _CC_MEMO:
            return _CC_MEMO[cc]
    exe = cc if os.path.isfile(cc) else shutil.which(cc)
    ident = {"cc": cc, "resolved": os.path.abspath(exe) if exe else None}
    for flag in ("--version", "-dumpmachine"):
        try:
            r = subprocess.run([exe or cc, flag], capture_output=True, text=True, timeout=60, env=cc_env(cc))
            ident[flag] = (r.stdout + r.stderr).strip()
        except (OSError, subprocess.SubprocessError) as e:
            ident[flag] = f"error: {e}"
    if exe and os.path.isfile(exe):
        ident["sha256"] = sha256_file(Path(exe))
    with _MEMO_LOCK:
        _CC_MEMO[cc] = ident
    return ident


def harness_digest(extra: list[Path] = ()) -> str:
    """tools/check_all.py + tools/testcache.py (+ extra): any change refuses every hit."""
    h = hashlib.sha256()
    for p in [HERE / "check_all.py", HERE / "testcache.py", *extra]:
        h.update(p.name.encode() + b"\0" + (sha256_file(p) if p.is_file() else "missing").encode() + b"\0")
    return h.hexdigest()


# ------------------------------------------------------------------ completeness
class _Scan:
    """What a set of AST nodes does: repository paths it spells, modules it imports (with the
    names it then uses from each; None = every name), folders it adds to sys.path, and the
    names it refers to."""

    def __init__(self):
        self.paths: set[str] = set()
        self.search: set[str] = set()
        self.imports: dict[tuple[str, int], set[str] | None] = {}
        self.names: set[str] = set()


def _is_root(n) -> bool:
    """A name for the repository root (ROOT, root, REPO, self.root, ...)."""
    nm = n.id if isinstance(n, ast.Name) else (n.attr if isinstance(n, ast.Attribute) else "")
    return "ROOT" in nm.upper() or "REPO" in nm.upper()


def _run_paths(parts: list, out: set[str]) -> None:
    """Constant parts right after the root (or leading constants) name a repository path."""
    prev, run = None, []
    for p in parts + [None]:
        if isinstance(p, ast.Constant) and isinstance(p.value, str):
            run.append(p.value)
            continue
        if run and (prev is None or _is_root(prev)) and run[0].replace("\\", "/").split("/")[0] in TOPS:
            out.add("/".join(x.replace("\\", "/").strip("/") for x in run if x))
        prev, run = p, []


def _div_chain(n) -> list:
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
        return _div_chain(n.left) + [n.right]
    return [n]


def _node_paths(n, parent) -> set[str]:
    out: set[str] = set()
    if isinstance(n, ast.Call):
        f = n.func
        fname = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
        if fname in ("join", "Path", "PurePath", "joinpath"):
            _run_paths(list(n.args), out)
    elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div) and not (
            isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div)):
        _run_paths(_div_chain(n), out)
    elif isinstance(n, ast.Constant) and isinstance(n.value, str) and not isinstance(parent, ast.Expr):
        s = n.value.replace("\\", "/")      # (a bare string statement is a docstring)
        if "/" in s and "\n" not in s and " " not in s and s.split("/")[0] in TOPS:
            out.add(s.strip("/"))
    return out


def _scan(nodes: list, parents: dict, consts: dict | None = None) -> _Scan:
    sc = _Scan()
    consts = consts or {}
    alias: dict[str, tuple[str, int]] = {}          # local name -> module of `import M [as N]`
    attrs: dict[str, set[str]] = {}
    bare: set[str] = set()
    sys_path_nodes: set[int] = set()
    for top in nodes:
        for n in ast.walk(top):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("insert", "append") \
                    and ast.unparse(n.func.value) == "sys.path":
                for a in n.args:                    # a folder searched for imports, not data
                    for m in ast.walk(a):
                        sys_path_nodes.add(id(m))
                        sc.search |= _node_paths(m, parents.get(m))
                        if isinstance(m, ast.Name):
                            sc.search |= consts.get(m.id, set())   # sys.path.insert(0, SOME_DIR)
    for top in nodes:
        for n in ast.walk(top):
            if id(n) not in sys_path_nodes:
                sc.paths |= _node_paths(n, parents.get(n))
            if isinstance(n, ast.Import):
                for a in n.names:
                    key = (a.name.split(".")[0], 0)
                    alias[(a.asname or a.name).split(".")[0]] = key
                    sc.imports.setdefault(key, set())
            elif isinstance(n, ast.ImportFrom):
                key = ((n.module or "").split(".")[0], n.level)
                names = {a.name for a in n.names}
                cur = sc.imports.get(key, set())
                sc.imports[key] = None if (cur is None or "*" in names) else (cur | names)
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                attrs.setdefault(n.value.id, set()).add(n.attr)
            elif isinstance(n, ast.Name):
                sc.names.add(n.id)
                par = parents.get(n)
                if not (isinstance(par, ast.Attribute) and par.value is n):
                    bare.add(n.id)
    for local, key in alias.items():                # import M: the names used as M.x
        if key in sc.imports and sc.imports[key] is None:
            continue
        if local in bare:
            sc.imports[key] = None                  # M passed around whole: every name counts
        else:
            sc.imports[key] = (sc.imports.get(key) or set()) | attrs.get(local, set())
    return sc


def _is_main_guard(st) -> bool:
    return isinstance(st, ast.If) and "__name__" in ast.unparse(st.test) and "__main__" in ast.unparse(st.test)


def analyze_module(source: str, name: str, used: set[str] | None) -> _Scan:
    """What importing this module and using `used` of it can reach (None: run as a script, or
    every name): its module-level code (not the __main__ block), the functions and classes named
    and every module-level function, class or constant they refer to, transitively. A module
    constant (ROOT-relative path assigned at module level) counts where it is used."""
    tree = ast.parse(source, name)
    parents = {}
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n):
            parents[c] = n
    consts: dict[str, set[str]] = {}
    for st in tree.body:
        if isinstance(st, ast.Assign) and all(isinstance(t, ast.Name) for t in st.targets):
            got = set()
            for m in ast.walk(st.value):
                got |= _node_paths(m, parents.get(m))
            for t in st.targets:
                consts[t.id] = got
    if used is None:
        return _scan([tree], parents, consts)
    defs, always = {}, []
    for st in tree.body:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs[st.name] = st
        elif isinstance(st, (ast.Assign, ast.AnnAssign)) and all(
                isinstance(t, ast.Name) for t in (st.targets if isinstance(st, ast.Assign) else [st.target])):
            for t in (st.targets if isinstance(st, ast.Assign) else [st.target]):
                defs[t.id] = st
        elif _is_main_guard(st):
            continue
        else:
            always.append(st)
    total = _scan(always, parents, consts)
    todo = set(used) | total.names
    done: set[str] = set()
    while todo:
        nm = todo.pop()
        if nm in done:
            continue
        done.add(nm)
        node = defs.get(nm)
        if node is None:
            continue
        sc = _scan([node], parents, consts)
        total.paths |= sc.paths
        total.search |= sc.search
        for k, v in sc.imports.items():
            cur = total.imports.get(k, set())
            total.imports[k] = None if (cur is None or v is None) else (cur | v)
        todo |= sc.names - done
    return total


def completeness(root: Path, spec: dict, files: list[str], cc: str | None) -> list[str]:
    """Problems that make the declared input list incomplete ([] = complete)."""
    fset = set(files)
    roots = recursive_roots(spec.get("files", []))
    problems: list[str] = []

    def problem(msg):
        if msg not in problems:
            problems.append(msg)

    for e in spec.get("py", []):
        if e not in fset:
            problem(f"entry script {e} is not a declared input")
    search_dirs = {str(Path(e).parent).replace("\\", "/") for e in spec.get("py", [])}
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | set(sys.builtin_module_names)
    wanted: dict[str, set[str] | None] = {e: None for e in spec.get("py", []) if e in fset}
    done: dict[str, set[str] | None] = {}
    while True:                                   # import closure from the entry scripts
        pending = [f for f, u in wanted.items()
                   if f not in done or (done[f] is not None and (u is None or not u <= done[f]))]
        if not pending:
            break
        f = pending[0]
        used = None if wanted[f] is None else set(wanted[f])
        done[f] = used
        try:
            sc = analyze_module((root / f).read_text(encoding="utf-8"), f, used)
        except (OSError, SyntaxError, ValueError) as e:
            problem(f"{f}: cannot parse ({e})")
            continue
        search_dirs |= sc.search | {str(Path(f).parent).replace("\\", "/")}
        for p in sorted(sc.paths):
            if not covered(p, fset, roots):
                problem(f"{f} names {p}, which is not (wholly) declared")
        for (mod, level), names in sorted(sc.imports.items(), key=lambda kv: kv[0]):
            if level:
                problem(f"{f}: relative import (level {level}) is not followed")
                continue
            if not mod or mod in stdlib or mod == "__future__":
                continue
            hit = next((c for d in sorted(search_dirs) for c in (f"{d}/{mod}.py", f"{d}/{mod}/__init__.py")
                        if c in fset), None)
            if hit:
                cur = wanted.get(hit, set())
                wanted[hit] = None if (cur is None or names is None) else (cur | names)
                continue
            where = next((c for d in sorted(search_dirs) for c in (f"{d}/{mod}.py", f"{d}/{mod}/__init__.py")
                          if (root / c).is_file()), None)
            if where is None:
                try:
                    found = importlib.util.find_spec(mod)
                except (ImportError, ValueError):
                    found = None
                where = getattr(found, "origin", None) if found else None
            problem(f"{f} imports {mod} from outside the declared inputs ({where or 'not found'})")
    # the C side: every dependency the preprocessor names must be declared
    c_dirs = spec.get("c_dirs", [])
    if c_dirs:
        cfiles = sorted(f for f in files if f.endswith(".c") and any(covered(f, set(), [d]) for d in c_dirs))
        if not cc:
            problem("no host C compiler: the header list cannot be checked")
        elif cfiles:
            inc = []
            for d in spec.get("include", []):
                inc += ["-I", d]
            for d in sorted({str(Path(f).parent).replace("\\", "/") for f in cfiles}):
                inc += ["-I", d]
            memo = (str(root), cc, tuple(inc), tuple(cfiles),
                    sha256_text("".join(sha256_file(root / f) for f in files)))
            with _MEMO_LOCK:
                got = _C_MEMO.get(memo)
            if got is None:
                got = c_dependencies(root, cc, inc, cfiles)
                with _MEMO_LOCK:
                    _C_MEMO[memo] = got
            deps, err = got
            if err:
                problem(f"preprocessor: {err}")
            for d in sorted(deps):
                if d not in fset:
                    problem(f"a compiled file includes {d}, which is not declared")
    return problems


def c_dependencies(root: Path, cc: str, inc: list[str], cfiles: list[str]) -> tuple[set[str], str]:
    """Quoted-include dependencies of cfiles (cc -MM -MG), repo-relative; (deps, error)."""
    deps: set[str] = set()
    for i in range(0, len(cfiles), 40):
        chunk = cfiles[i:i + 40]
        try:
            r = subprocess.run([cc, "-MM", "-MG", *inc, *chunk], cwd=str(root), capture_output=True,
                               text=True, timeout=300, env=cc_env(cc))
        except (OSError, subprocess.SubprocessError) as e:
            return deps, str(e)
        if r.returncode:
            return deps, (r.stderr.strip().splitlines() or [f"exit {r.returncode}"])[0][:200]
        text = r.stdout.replace("\\\r\n", " ").replace("\\\n", " ")
        for line in text.splitlines():
            m = re.match(r"^\S+\.o:\s*(.*)$", line)
            if not m:
                continue
            for tok in re.split(r"(?<!\\)\s+", m.group(1).strip()):
                if not tok:
                    continue
                tok = tok.replace("\\ ", " ")
                p = Path(tok)
                if p.is_absolute():
                    try:
                        tok = p.resolve().relative_to(root.resolve()).as_posix()
                    except ValueError:
                        tok = p.as_posix()      # outside the root: never declared
                else:
                    tok = os.path.normpath(tok).replace("\\", "/")
                deps.add(tok)
    return deps, ""


# ------------------------------------------------------------------ keys and the store
def relevant_env() -> dict:
    return {k: v for k, v in sorted(os.environ.items()) if k.startswith("FE_")}


class Cache:
    def __init__(self, directory: Path, now: float | None = None):
        self.dir = Path(directory)
        self.lock = threading.Lock()
        self._now = now
        self._complete: dict[str, list[str]] = {}

    def now(self) -> float:
        return self._now if self._now is not None else time.time()

    # -- keys
    def key_for(self, root: Path, row_def: dict, spec: dict, cc: str | None) -> tuple[str, dict, list[str]]:
        """(key, info, problems); problems non-empty = the row is not cacheable."""
        files = expand(root, spec.get("files", []))
        if not files:
            return "", {}, ["no declared input files"]
        inputs = [(f, sha256_file(root / f)) for f in files]
        comp = compiler_identity(cc) if spec.get("host_cc") else {"cc": "not used"}
        memo = sha256_text(json.dumps([inputs, spec, comp], sort_keys=True))
        with self.lock:
            problems = self._complete.get(memo)
        if problems is None:
            problems = completeness(root, spec, files, cc if spec.get("host_cc") else None)
            with self.lock:
                self._complete[memo] = problems
        cdig = sha256_text(json.dumps(comp, sort_keys=True))
        hdig = harness_digest()
        material = {"format": FORMAT, "row": row_def, "inputs": inputs, "compiler": comp,
                    "python": sys.version, "env": relevant_env(), "harness": hdig}
        key = sha256_text(json.dumps(material, sort_keys=True))
        info = {"files": len(files), "compiler": cdig, "harness": hdig,
                "inputs_digest": sha256_text(json.dumps(inputs))}
        return key, info, list(problems)

    # -- meta (the clean-run record)
    def _meta_path(self) -> Path:
        return self.dir / "meta.json"

    def meta(self) -> dict:
        try:
            m = json.loads(self._meta_path().read_text(encoding="utf-8"))
            return m if m.get("format") == FORMAT else {"format": FORMAT, "clean": {}}
        except (OSError, ValueError):
            return {"format": FORMAT, "clean": {}}

    def record_clean(self, row_id: str, info: dict) -> None:
        with self.lock:
            m = self.meta()
            m.setdefault("clean", {})[row_id] = {"date": self.now(), "compiler": info.get("compiler"),
                                                 "harness": info.get("harness")}
            atomic_write(self._meta_path(), json.dumps(m, indent=1, sort_keys=True) + "\n")

    # -- entries
    def _entry_path(self, row_id: str, key: str) -> Path:
        return self.dir / "entries" / row_id / f"{key}.json"

    def get(self, row_id: str, key: str, info: dict) -> tuple[dict | None, str]:
        """(entry, "") on a hit, else (None, why not)."""
        clean = self.meta().get("clean", {}).get(row_id)
        if not clean:
            return None, "no clean run recorded for this row (check_all --no-cache)"
        if self.now() - clean.get("date", 0) > MAX_AGE_S:
            return None, "weekly clean run due (last clean run is older than 7 days: check_all --no-cache)"
        if clean.get("compiler") != info.get("compiler"):
            return None, "compiler changed since the last clean run (check_all --no-cache)"
        if clean.get("harness") != info.get("harness"):
            return None, "harness changed since the last clean run (check_all --no-cache)"
        p = self._entry_path(row_id, key)
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None, "no entry for this key"
        if e.get("key") != key or e.get("status") != "PASS":
            return None, "entry does not match"
        if self.now() - e.get("date", 0) > MAX_AGE_S:
            return None, "entry older than 7 days"
        return e, ""

    def put(self, row_id: str, key: str, res: dict, log_text: str, info: dict) -> None:
        if res.get("status") != "PASS":
            return
        e = {"format": FORMAT, "key": key, "row": row_id, "date": self.now(), "status": "PASS",
             "note": res.get("note", ""), "seconds": res.get("seconds", 0.0), "log": log_text, "info": info}
        atomic_write(self._entry_path(row_id, key), json.dumps(e, indent=1) + "\n")

    def status(self) -> str:
        out = [f"testcache {self.dir}"]
        m = self.meta()
        ent = sorted(self.dir.glob("entries/*/*.json")) if self.dir.is_dir() else []
        rows = sorted({p.parent.name for p in ent} | set(m.get("clean", {})))
        if not rows:
            return out[0] + ": empty"
        for r in rows:
            mine = [p for p in ent if p.parent.name == r]
            c = m.get("clean", {}).get(r)
            age = f"{(self.now() - c['date']) / 3600:.1f} h ago" if c else "never"
            out.append(f"  {r:<20} {len(mine)} entr{'y' if len(mine) == 1 else 'ies'}; last clean run {age}")
        return "\n".join(out)

    def clear(self) -> int:
        n = 0
        if self.dir.is_dir():
            for p in self.dir.glob("entries/*/*.json"):
                p.unlink()
                n += 1
            if self._meta_path().is_file():
                self._meta_path().unlink()
        return n


def selftest() -> list[str]:
    """Round 9: the 7-day age refusals. A clean run and an entry at t0; hits at t0 + 7 days exactly, refusals one
    second later (clean run first, then the entry when the clean run is renewed). Planted bugs that this catches:
    the age test removed, '>' changed to '>=', MAX_AGE_S changed."""
    import tempfile
    fails: list[str] = []
    n = [0]

    def check(cond, what):
        n[0] += 1
        print(f"  {'ok  ' if cond else 'FAIL'} {what}")
        if not cond:
            fails.append(what)

    t0 = 1_700_000_000.0
    week = 7 * 24 * 3600
    info = {"compiler": "c", "harness": "h"}
    with tempfile.TemporaryDirectory(prefix="testcache-selftest-") as td:
        c = Cache(Path(td), now=t0)
        c.record_clean("r", info)
        c.put("r", "k", {"status": "PASS", "note": "n"}, "log", info)
        check(c.get("r", "k", info)[0] is not None, "a fresh entry with a fresh clean run is a hit")
        check(MAX_AGE_S == week, f"MAX_AGE_S is 7 days ({MAX_AGE_S} s)")
        c._now = t0 + week
        check(c.get("r", "k", info)[0] is not None, "7 days exactly: still a hit")
        c._now = t0 + week + 1
        e, why = c.get("r", "k", info)
        check(e is None and "weekly clean run due" in why, f"clean run 7 days + 1 s old: refused ({why})")
        c.record_clean("r", info)  # a new clean run; the entry stays at t0
        e, why = c.get("r", "k", info)
        check(e is None and why == "entry older than 7 days", f"entry 7 days + 1 s old: refused ({why})")
        c.put("r", "k", {"status": "PASS", "note": "n"}, "log", info)
        check(c.get("r", "k", info)[0] is not None, "renewed entry: a hit again")
        e, why = c.get("r", "k", dict(info, compiler="other"))
        check(e is None and "compiler changed" in why, "another compiler: refused")
        c.put("r", "k2", {"status": "FAIL"}, "log", info)
        check(c.get("r", "k2", info)[0] is None, "a FAIL is never stored")
    print(f"testcache selftest: {n[0] - len(fails)}/{n[0]} ok")
    return fails


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["status", "clear", "selftest"])
    ap.add_argument("--dir", default=str(HERE.parent / "build" / "testcache"))
    a = ap.parse_args(argv)
    if a.command == "selftest":
        return 1 if selftest() else 0
    c = Cache(Path(a.dir))
    if a.command == "status":
        print(c.status())
    else:
        print(f"testcache: {c.clear()} entries deleted from {c.dir}; the next hit needs a clean run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
