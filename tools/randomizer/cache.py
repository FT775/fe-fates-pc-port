#!/usr/bin/env python3
"""Speed for the randomizer's make (F-047 start delay, round 59; docs/rando/SPEED.md).

The in-game Start game runs `rando.py make --patch-out` and the player waited ~10 s (page defaults) to ~35 s
(everything on). Most of that time was spent reading the same game tables again and again, not randomizing.
install() makes those reads cheap without changing a single output byte:

  1. table file lists      tablelib.TableDef.files() listed and stat'ed a whole folder on every call (thousands of
                           calls per make, ~5 s): remembered per (RomFS folder, pattern) for this process.
  2. parsed tables         gamedata._load / load_handover, enemies.script_pids and mods.vanilla() results are kept
                           on disk, one folder per game (fates / seal), as pickles. Each call gets a fresh copy (a
                           caller may change its rows), exactly what a fresh read would give.
  3. LZ decompression      lz.decompress results are kept on disk by the SHA-256 of the compressed bytes (a pure
                           function of its input, so a hit can never be stale).
  4. reach answers        tiles a class can reach from a tile (the enemies and Move no-stuck rules; ~13 000 searches
                           in an everything-on make) depend only on the terrain tables: kept on disk too
                           (memo_dict("reach"), given to EnemyTables as _reach_memo; used by reach_tiles).
  5. fast_patch=True       (the in-game path only: `make --patch-out` with no --zakuro-dir) the mods tool's rebuilt
                           files are LZ-encoded as plain literals instead of the game's slow greedy matcher; the
                           patch only ever looks at the decompressed bytes, which are the same, so the patch text is
                           byte-identical. Never for PLAY RANDOMIZED installs (those files go into a data folder).

  6. progress_lines=True  `progress N stage` lines on stdout (flushed) as the make passes its stages, for the
                           in-game "Making your game... N%" line (the core reads the output it already pumps).

Invalidation (a cache hit only when nothing it depends on changed):
  - code: SHA-256 of the readers' own code: tools/randomizer/{cache,gamedata,enemies,sources}.py,
    tools/{tables,mods,assets}/*.py and the table layouts config/tables/** (CODE_PARTS);
  - game: SHA-256 of every file under the RomFS parts the randomizer reads (GameData, Scripts, m, map/config, talk,
    exalt; whatever of them exists in the active RomFS folder, Fates' or the Seal of Flames layer). The contents are
    hashed; a small index (size, mtime_ns -> sha256) skips re-hashing files whose size and time did not change
    (set FEF_RANDO_CACHE_STRICT=1 to re-hash every file);
  - the RomFS folder itself and the call's arguments are part of each entry's key.
Any change -> a miss -> the original function runs and the entry is rewritten. Entries are written whole then
renamed (two makes at once never see half a file).

Where: install(cache_dir=...) or FEF_RANDO_CACHE; the in-game core passes <data>/rando/cache (SPEED.md); default
build/rando/cache (the repo's build folder, gitignored). Game data never leaves the owner's machine.

    python tools/randomizer/cache.py status [--cache-dir DIR] [--game fates|seal]
    python tools/randomizer/cache.py warm   [--cache-dir DIR] [--game fates|seal] [--seal-romfs DIR]
    python tools/randomizer/cache.py clear  [--cache-dir DIR]

Standard library only. Pickle is used because the cache is the tool's own, in the owner's own folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

FORMAT = 1
DEFAULT_DIR = os.path.join(ROOT, "build", "rando", "cache")
# the code the cached readers run: their own modules, the table tools, the LZ / IS .bin codecs, the table layouts
# (a change anywhere here = every entry made again). Other randomizer modules only USE the tables, so editing them
# does not throw the cache away.
CODE_PARTS = (("tools/randomizer/cache.py", ""), ("tools/randomizer/gamedata.py", ""),
              ("tools/randomizer/enemies.py", ""), ("tools/randomizer/sources.py", ""), ("tools/tables", ".py"),
              ("tools/mods", ".py"), ("tools/assets", ".py"), ("config/tables", ""))
GAME_PARTS = ("GameData", "Scripts", "m", "map/config", "talk", "exalt")
LZ_PACK = "lz.pack"

_STATE: dict = {"installed": None}


# ------------------------------------------------------------------------------------------------ hashing
def _files_under(top: str, ext: str = "") -> list[tuple[str, str]]:
    """(relative path with /, absolute path) of every file under top (ext: only that ending), sorted. top may be
    one file (rel "")."""
    out = []
    if os.path.isfile(top):
        return [("", top)]
    if not os.path.isdir(top):
        return out
    for dp, dn, fs in os.walk(top):
        dn[:] = sorted(d for d in dn if d != "__pycache__")
        for f in sorted(fs):
            if ext and not f.endswith(ext):
                continue
            p = os.path.join(dp, f)
            out.append((os.path.relpath(p, top).replace(os.sep, "/"), p))
    return out


def code_hash(root: str = ROOT) -> str:
    """SHA-256 of the code and configuration every cached result depends on."""
    h = hashlib.sha256(f"fef-rando-cache {FORMAT}\n".encode())
    for part, ext in CODE_PARTS:
        for rel, p in _files_under(os.path.join(root, *part.split("/")), ext):
            with open(p, "rb") as fh:
                data = fh.read()
            h.update(f"{part}/{rel}\0{len(data)}\0".encode("utf-8"))
            h.update(data)
    return h.hexdigest()


def game_hash(romfs: str, index_path: str | None = None, strict: bool | None = None) -> str:
    """SHA-256 of every file the randomizer may read in this RomFS folder (GAME_PARTS). index_path: a JSON file
    (rel -> [size, mtime_ns, sha256]) that lets unchanged files skip re-hashing (strict: re-hash all)."""
    return game_files(romfs, index_path, strict)[0]


def game_files(romfs: str, index_path: str | None = None, strict: bool | None = None) -> tuple[str, set]:
    """(game_hash, the set of every such file's own SHA-256)."""
    if strict is None:
        strict = os.environ.get("FEF_RANDO_CACHE_STRICT", "") not in ("", "0")
    old: dict = {}
    if index_path and not strict:
        try:
            with open(index_path, encoding="utf-8") as fh:
                got = json.load(fh)
            if got.get("romfs") == os.path.normcase(os.path.realpath(romfs)):
                old = got.get("files", {})
        except (OSError, ValueError):
            old = {}
    new: dict = {}
    h = hashlib.sha256(b"fef-rando-game 1\n")
    for part in GAME_PARTS:
        for rel, p in _files_under(os.path.join(romfs, *part.split("/"))):
            key = f"{part}/{rel}"
            st = os.stat(p)
            o = old.get(key)
            if o and o[0] == st.st_size and o[1] == st.st_mtime_ns:
                sha = o[2]
            else:
                with open(p, "rb") as fh:
                    sha = hashlib.sha256(fh.read()).hexdigest()
            new[key] = [st.st_size, st.st_mtime_ns, sha]
            h.update(f"{key}\0{sha}\n".encode("utf-8"))
    if index_path and new != old:
        _write_atomic(index_path, json.dumps({"romfs": os.path.normcase(os.path.realpath(romfs)), "files": new},
                                             sort_keys=True).encode("utf-8"))
    return h.hexdigest(), {v[2] for v in new.values()}


def _write_atomic(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    try:
        os.replace(tmp, path)
    except OSError:          # another make renamed the same entry at the same moment: theirs is as good
        try:
            os.remove(tmp)
        except OSError:
            pass


# ------------------------------------------------------------------------------------------------ the cache
class Cache:
    """One make's view of the disk cache. game: "fates" / "seal" (the folder name); the RomFS folder and the
    fingerprints are read from the table tools at the first use (sources.activate may switch them after install)."""

    def __init__(self, cache_dir: str | None = None, game: str | None = None):
        self.top = os.path.abspath(cache_dir or os.environ.get("FEF_RANDO_CACHE") or DEFAULT_DIR)
        self._game = game
        self._code: str | None = None
        self._games: dict[str, str] = {}          # romfs -> game hash
        self._game_shas: dict[str, set] = {}      # romfs -> SHA-256 of each of its game files
        self._mem: dict[str, bytes] = {}          # entry key -> pickled result (this process)
        self._lz: dict[str, bytes] | None = None
        self._memos: dict[str, tuple[str, str, dict, int]] = {}   # name -> (key, path, dict, size when loaded)
        self._lz_new = False
        self.hits = 0
        self.misses = 0
        self.lz_hits = 0
        self.lz_misses = 0

    # -- where and what
    def game(self) -> str:
        if self._game:
            return self._game
        try:
            import sources as S
            return S.current()
        except Exception:  # noqa: BLE001
            return "fates"

    def folder(self) -> str:
        return os.path.join(self.top, self.game())

    def romfs(self) -> str:
        import gamedata as GD
        return GD.M.T.ROMFS

    def code(self) -> str:
        if self._code is None:
            self._code = code_hash()
        return self._code

    def game_fp(self, romfs: str) -> str:
        k = os.path.normcase(os.path.realpath(romfs))
        if k not in self._games:
            self._games[k], self._game_shas[k] = game_files(romfs, os.path.join(self.folder(), "game-index.json"))
        return self._games[k]

    def is_game_file(self, sha: str) -> bool:
        """Whether these bytes are one of the active RomFS folder's own files (by content)."""
        romfs = self.romfs()
        self.game_fp(romfs)
        return sha in self._game_shas[os.path.normcase(os.path.realpath(romfs))]

    def key(self, name: str, args: tuple) -> tuple[str, str]:
        romfs = self.romfs()
        k = hashlib.sha256("\0".join([str(FORMAT), self.code(), self.game_fp(romfs),
                                      os.path.normcase(os.path.realpath(romfs)), name,
                                      repr(args)]).encode("utf-8")).hexdigest()
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{name}-{'-'.join(map(str, args))}")[:80]
        return k, os.path.join(self.folder(), "tables", f"{safe}.pkl")

    # -- results of a pure reader
    def call(self, name: str, args: tuple, fn):
        """fn() through the cache: a fresh copy of the stored result on a hit, fn()'s result (stored) on a miss."""
        k, path = self.key(name, args)
        blob = self._mem.get(k)
        if blob is None:
            try:
                with open(path, "rb") as fh:
                    head = fh.read(64)
                    blob = fh.read() if head == k.encode("ascii") else None
            except OSError:
                blob = None
        if blob is not None:
            self.hits += 1
            self._mem[k] = blob
            return pickle.loads(blob)
        self.misses += 1
        result = fn()
        blob = pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
        self._mem[k] = blob
        _write_atomic(path, k.encode("ascii") + blob)
        return pickle.loads(blob)

    # -- LZ decompression, by content
    def _lz_pack(self) -> dict[str, bytes]:
        if self._lz is None:
            self._lz = {}
            try:
                with open(os.path.join(self.folder(), LZ_PACK), "rb") as fh:
                    got = pickle.load(fh)
                if isinstance(got, dict) and got.get("format") == FORMAT:
                    self._lz = got["entries"]
            except (OSError, pickle.UnpicklingError, EOFError, KeyError, TypeError, ValueError):
                self._lz = {}
        return self._lz

    def lz_decompress(self, data: bytes, orig_fn) -> bytes:
        """Only the game's own files are kept (a made file is different every seed: never stored)."""
        k = hashlib.sha256(data).hexdigest()
        if not self.is_game_file(k):
            return orig_fn(data)
        pack = self._lz_pack()
        got = pack.get(k)
        if got is not None:
            self.lz_hits += 1
            return got
        self.lz_misses += 1
        out = orig_fn(data)
        pack[k] = out
        self._lz_new = True
        return out

    # -- answers worked out from the tables (seed-independent), kept between makes
    def memo_dict(self, name: str) -> dict:
        """A dict kept on disk for this game and code (e.g. "reach": tiles reachable from a tile). The caller
        stores only answers that depend on nothing but the tables (game files) and the code (CODE_PARTS)."""
        if name in self._memos:
            return self._memos[name][2]
        k, path = self.key("memo", (name,))
        d: dict = {}
        try:
            with open(path, "rb") as fh:
                if fh.read(64) == k.encode("ascii"):
                    d = pickle.load(fh)
        except (OSError, pickle.UnpicklingError, EOFError, TypeError, ValueError):
            d = {}
        if not isinstance(d, dict):
            d = {}
        self._memos[name] = (k, path, d, len(d))
        return d

    def save(self) -> None:
        """Writes the LZ pack and the memo dicts when this make added entries (at exit and by uninstall)."""
        for name, (k, path, d, n) in list(self._memos.items()):
            if len(d) != n:
                _write_atomic(path, k.encode("ascii") + pickle.dumps(d, protocol=pickle.HIGHEST_PROTOCOL))
                self._memos[name] = (k, path, d, len(d))
        if self._lz_new and self._lz is not None:
            _write_atomic(os.path.join(self.folder(), LZ_PACK),
                          pickle.dumps({"format": FORMAT, "entries": self._lz}, protocol=pickle.HIGHEST_PROTOCOL))
            self._lz_new = False

    def stats(self) -> dict:
        return {"dir": self.folder(), "hits": self.hits, "misses": self.misses, "lz_hits": self.lz_hits,
                "lz_misses": self.lz_misses}


# ------------------------------------------------------------------------------------------------ fast patch LZ
_FAST_RAW: dict[bytes, bytes] = {}


def literal_lz(data: bytes, fmt: int) -> bytes:
    """data as a valid Nintendo LZ stream of format fmt (0x10 / 0x11 / 0x13) made only of literals: every flag
    byte 0, eight bytes after each. Decompresses to exactly data (lz.decompress); larger than the game's own
    encoding, which is why it is only used for the in-memory patch (never written to a data folder)."""
    n = len(data)
    out = bytearray()
    if fmt == 0x13:
        out += bytes((0x13, n & 255, n >> 8 & 255, n >> 16 & 255))
        inner = 0x11
    else:
        inner = fmt
    if 0 < n < 0x1000000:
        out += bytes((inner, n & 255, n >> 8 & 255, n >> 16 & 255))
    else:                                   # a size field of 0 means "the size follows as a u32"
        out += bytes((inner, 0, 0, 0)) + n.to_bytes(4, "little")
    out += b"".join(b"\0" + data[i:i + 8] for i in range(0, n, 8))
    return bytes(out)


# ------------------------------------------------------------------------------------------------ install
def progress(n: int, what: str) -> None:
    """One progress line for the in-game page: `progress <0-100> <stage>`."""
    print(f"progress {int(n)} {what}", flush=True)


# the make's stages as the in-game make goes through them (rando.cmd_make), and the share of a typical
# everything-on make already done when each one ends (measured, round 59; docs/rando/SPEED.md)
STAGES = (("tracks", "make_all", 70, "planned"), ("ingame", "rebuilt_files", 92, "files rebuilt"),
          ("ingame", "make_patch", 99, "patch made"))


def install(cache_dir: str | None = None, game: str | None = None, fast_patch: bool = False,
            progress_lines: bool = False) -> Cache:
    """Puts the cache under the readers named in the module text (idempotent: a second call returns the first
    Cache, switching fast_patch / progress_lines on if asked). Outputs are byte-identical with and without it."""
    st = _STATE.get("installed")
    if st is not None:
        if fast_patch and not st["fast_patch"]:
            _install_fast_patch(st)
        if progress_lines and not st.get("progress"):
            _install_progress(st)
        return st["cache"]
    import gamedata as GD
    import enemies as E
    M = GD.M
    T = M.T
    import lz
    c = Cache(cache_dir, game)
    orig = {"files": T.TableDef.files, "_load": GD._load, "load_handover": GD.load_handover,
            "script_pids": E.script_pids, "vanilla": M.vanilla, "decompress": lz.decompress,
            "compress_like": lz.compress_like, "enemy_tables": E.load_tables}
    st = {"cache": c, "orig": orig, "fast_patch": False, "mods": (GD, E, M, T, lz)}

    files_memo: dict = {}

    def files(self):
        k = (T.ROMFS, self.file)
        got = files_memo.get(k)
        if got is None:
            got = files_memo[k] = orig["files"](self)
        return list(got)

    def _load(name, only_first=False):
        return c.call("load", (name, bool(only_first)), lambda: orig["_load"](name, only_first=only_first))

    def load_handover(rels=GD.HANDOVER_RX):
        return c.call("handover", tuple(rels), lambda: orig["load_handover"](rels))

    def script_pids(romfs):
        if os.path.normcase(os.path.realpath(romfs)) != os.path.normcase(os.path.realpath(T.ROMFS)):
            return orig["script_pids"](romfs)
        return c.call("script_pids", (), lambda: orig["script_pids"](romfs))

    def enemy_tables(*a, **k):
        t = orig["enemy_tables"](*a, **k)
        t._reach_memo = c.memo_dict("reach")     # (chapter, x, y, move cost class, mov) -> tiles (EnemyTables.reach_tiles)
        return t

    def vanilla():
        if M._VANILLA is None:
            M._VANILLA = c.call("vanilla", (), orig["vanilla"])
        return M._VANILLA

    def decompress(data):
        if not isinstance(data, bytes):
            return orig["decompress"](data)
        raw = _FAST_RAW.get(data) if _FAST_RAW else None
        if raw is not None:
            return raw
        return c.lz_decompress(data, orig["decompress"])

    T.TableDef.files = files
    GD._load = _load
    GD.load_handover = load_handover
    E.script_pids = script_pids
    E.load_tables = enemy_tables
    M.vanilla = vanilla
    lz.decompress = decompress
    _STATE["installed"] = st
    if fast_patch:
        _install_fast_patch(st)
    if progress_lines:
        _install_progress(st)
    import atexit
    atexit.register(c.save)
    return c


def _install_fast_patch(st: dict) -> None:
    lz = st["mods"][4]
    orig = st["orig"]

    def compress_like(data, orig_bytes, parse=None):
        if lz.lz_type(orig_bytes) is None:
            return data
        out = literal_lz(bytes(data), orig_bytes[0])
        _FAST_RAW[out] = bytes(data)
        return out

    compress_like.__wrapped__ = orig["compress_like"]
    lz.compress_like = compress_like
    st["fast_patch"] = True


def _install_progress(st: dict) -> None:
    import importlib
    import functools
    import rando  # noqa: F401  (first: ingame puts tools/play, which has its own rando.py, ahead on sys.path)
    wrapped = []
    for modname, attr, pct, what in STAGES:
        mod = importlib.import_module(modname)
        f = getattr(mod, attr)

        def w(*a, _f=f, _pct=pct, _what=what, **k):
            r = _f(*a, **k)
            progress(_pct, _what)
            return r

        functools.update_wrapper(w, f)
        setattr(mod, attr, w)
        wrapped.append((mod, attr, f))
    st["progress"] = wrapped
    progress(5, "started")


def uninstall() -> None:
    """Puts every reader back (tests)."""
    st = _STATE.get("installed")
    if st is None:
        return
    st["cache"].save()
    GD, E, M, T, lz = st["mods"]
    o = st["orig"]
    T.TableDef.files = o["files"]
    GD._load = o["_load"]
    GD.load_handover = o["load_handover"]
    E.script_pids = o["script_pids"]
    E.load_tables = o["enemy_tables"]
    M.vanilla = o["vanilla"]
    lz.decompress = o["decompress"]
    lz.compress_like = o["compress_like"]
    for mod, attr, f in st.get("progress") or []:
        setattr(mod, attr, f)
    _FAST_RAW.clear()
    _STATE["installed"] = None


def installed() -> Cache | None:
    st = _STATE.get("installed")
    return st["cache"] if st else None


# ------------------------------------------------------------------------------------------------ command line
def warm(cache_dir: str | None = None, game: str | None = None, seal_romfs: str | None = None) -> dict:
    """Fills the cache for one game: every table the randomizer reads, its file lists and the LZ pack."""
    import sources as S
    if game:
        S.activate(game, seal_romfs)
    c = install(cache_dir, game or S.current())
    import gamedata as GD
    import enemies as E
    t0 = time.perf_counter()
    GD.load_facts()
    E.load_tables()
    for n in ("Skill", "Chapter"):
        try:
            GD._load(n)
        except Exception:  # noqa: BLE001  (a table a story does not have)
            pass
    GD.M.vanilla()
    c.save()
    return dict(c.stats(), seconds=round(time.perf_counter() - t0, 2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("status", "warm", "clear"):
        p = sub.add_parser(name)
        p.add_argument("--cache-dir")
        if name != "clear":
            p.add_argument("--game", choices=("fates", "seal"))
        if name == "warm":
            p.add_argument("--seal-romfs")
    a = ap.parse_args(argv)
    top = os.path.abspath(a.cache_dir or os.environ.get("FEF_RANDO_CACHE") or DEFAULT_DIR)
    if a.cmd == "clear":
        if os.path.isdir(top):
            shutil.rmtree(top)
        print(f"cleared {top}")
        return 0
    if a.cmd == "warm":
        print(json.dumps(warm(a.cache_dir, a.game, a.seal_romfs), indent=1))
        return 0
    games = [a.game] if a.game else sorted(d for d in os.listdir(top)) if os.path.isdir(top) else []
    for g in games:
        d = os.path.join(top, g)
        n = sum(len(fs) for _dp, _dn, fs in os.walk(d))
        size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _dn, fs in os.walk(d) for f in fs)
        print(f"{g}: {n} files, {size // 1024} KB in {d}")
    if not games:
        print(f"no cache in {top}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
