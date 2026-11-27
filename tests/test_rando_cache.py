"""The randomizer's make cache (F-047 start delay, round 59; tools/randomizer/cache.py, docs/rando/SPEED.md).

  - a cache hit gives byte-identical output (the mod folder and the in-memory patch of `make --patch-out`, cold and
    warm, with fast_patch on), compared with the make as it is without the cache;
  - any input change is a cache miss: a game file's contents (even with the same size and time, in strict mode), a
    file added, the readers' code, the RomFS folder, the call's arguments;
  - the plain-literal LZ of fast_patch decompresses to exactly its input;
  - F-047 agency, host half: a make of changed rows after a finished make (same cache) is byte-identical to a fresh
    make of the final rows, never the earlier ones; progress lines come in order.
Real-data tests skip without the extracted tables. Work folders go under build/ (never %TEMP%).

    python -m unittest tests.test_rando_cache
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "randomizer"))
sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))
import cache as C  # noqa: E402
import lz  # noqa: E402

try:
    import gamedata as GD
    if GD.available():
        GD = None
except Exception:  # noqa: BLE001
    GD = None

WORK = os.path.join(ROOT, "build", "test-rando-cache")
TOOL = os.path.join(ROOT, "tools", "randomizer")


def tmpdir() -> str:
    os.makedirs(WORK, exist_ok=True)
    return tempfile.mkdtemp(dir=WORK)


class FakeCache(C.Cache):
    """A Cache over a test folder: its own RomFS, code hash and game name."""

    def __init__(self, top, romfs, code="code-1"):
        super().__init__(top, "fates")
        self._romfs = romfs
        self._code = code

    def romfs(self):
        return self._romfs


class LiteralLZ(unittest.TestCase):
    def test_roundtrip_every_format(self):
        r = random.Random(59)
        for fmt in (0x10, 0x11, 0x13):
            for n in (0, 1, 7, 8, 9, 15, 16, 17, 1000, 70001):
                data = bytes(r.getrandbits(8) for _ in range(n))
                enc = C.literal_lz(data, fmt)
                self.assertEqual(enc[0], fmt)
                self.assertEqual(lz.lz_type(enc), fmt)
                self.assertEqual(lz.decompress(enc), data, f"fmt {fmt:#x} n {n}")


class Fingerprints(unittest.TestCase):
    def setUp(self):
        self.top = tmpdir()
        self.romfs = os.path.join(self.top, "romfs")
        os.makedirs(os.path.join(self.romfs, "GameData", "Dispos"))
        for i in range(3):
            with open(os.path.join(self.romfs, "GameData", "Dispos", f"A00{i}.bin"), "wb") as fh:
                fh.write(bytes([i]) * 64)

    def tearDown(self):
        shutil.rmtree(self.top, ignore_errors=True)

    def test_game_hash_follows_contents(self):
        idx = os.path.join(self.top, "idx.json")
        h0 = C.game_hash(self.romfs, idx)
        self.assertEqual(C.game_hash(self.romfs, idx), h0)
        p = os.path.join(self.romfs, "GameData", "Dispos", "A001.bin")
        st = os.stat(p)
        with open(p, "wb") as fh:                       # same size, then the old time put back
            fh.write(b"\x09" * 64)
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.assertNotEqual(C.game_hash(self.romfs, idx, strict=True), h0, "strict re-hash sees the new bytes")
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        self.assertNotEqual(C.game_hash(self.romfs, idx), h0, "a new time = re-hashed")
        h1 = C.game_hash(self.romfs, idx)
        with open(os.path.join(self.romfs, "GameData", "Dispos", "A009.bin"), "wb") as fh:
            fh.write(b"new")
        self.assertNotEqual(C.game_hash(self.romfs, idx), h1, "a file added")
        os.makedirs(os.path.join(self.romfs, "sound"))
        h2 = C.game_hash(self.romfs, idx)
        with open(os.path.join(self.romfs, "sound", "x.bcstm"), "wb") as fh:
            fh.write(b"not read by the randomizer")
        self.assertEqual(C.game_hash(self.romfs, idx), h2, "only GAME_PARTS count")

    def test_code_hash_follows_reader_code(self):
        root = os.path.join(self.top, "repo")
        for part, _ext in C.CODE_PARTS:
            p = os.path.join(root, *part.split("/"))
            if part.endswith(".py"):
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w") as fh:
                    fh.write("x = 1\n")
            else:
                os.makedirs(p, exist_ok=True)
                with open(os.path.join(p, "a.py" if "tools" in part else "a.csv"), "w") as fh:
                    fh.write("1\n")
        h0 = C.code_hash(root)
        with open(os.path.join(root, "tools", "randomizer", "gamedata.py"), "a") as fh:
            fh.write("y = 2\n")
        h1 = C.code_hash(root)
        self.assertNotEqual(h1, h0)
        with open(os.path.join(root, "config", "tables", "a.csv"), "a") as fh:
            fh.write("2\n")
        self.assertNotEqual(C.code_hash(root), h1, "a table layout changed")
        h2 = C.code_hash(root)
        os.makedirs(os.path.join(root, "tools", "randomizer"), exist_ok=True)
        with open(os.path.join(root, "tools", "randomizer", "colours.py"), "w") as fh:
            fh.write("z = 3\n")
        self.assertEqual(C.code_hash(root), h2, "a module that only uses the tables does not count")


class CallCache(unittest.TestCase):
    def setUp(self):
        self.top = tmpdir()
        self.romfs = os.path.join(self.top, "romfs")
        os.makedirs(os.path.join(self.romfs, "GameData"))
        self.file = os.path.join(self.romfs, "GameData", "GameData.bin")
        with open(self.file, "wb") as fh:
            fh.write(b"tables v1")
        self.calls = 0

    def tearDown(self):
        shutil.rmtree(self.top, ignore_errors=True)

    def reader(self):
        self.calls += 1
        with open(self.file, "rb") as fh:
            return [{"label": "PID_A", "raw": fh.read().decode()}]

    def test_hit_is_a_fresh_identical_copy(self):
        c = FakeCache(self.top, self.romfs)
        a = c.call("load", ("Person", True), self.reader)
        a[0]["label"] = "changed by a caller"
        c2 = FakeCache(self.top, self.romfs)                  # another make: from disk
        b = c2.call("load", ("Person", True), self.reader)
        self.assertEqual(self.calls, 1)
        self.assertEqual(b, [{"label": "PID_A", "raw": "tables v1"}])
        b2 = c2.call("load", ("Person", True), self.reader)
        self.assertIsNot(b, b2)
        self.assertEqual((c2.hits, c2.misses), (2, 0))

    def test_every_input_change_is_a_miss(self):
        FakeCache(self.top, self.romfs).call("load", ("Person", True), self.reader)
        n = self.calls
        FakeCache(self.top, self.romfs).call("load", ("Person", False), self.reader)
        self.assertEqual(self.calls, n + 1, "other arguments")
        FakeCache(self.top, self.romfs, code="code-2").call("load", ("Person", True), self.reader)
        self.assertEqual(self.calls, n + 2, "other code")
        with open(self.file, "wb") as fh:
            fh.write(b"tables v2")
        got = FakeCache(self.top, self.romfs, code="code-2").call("load", ("Person", True), self.reader)
        self.assertEqual(self.calls, n + 3, "other game files")
        self.assertEqual(got[0]["raw"], "tables v2")
        other = os.path.join(self.top, "romfs2")
        shutil.copytree(self.romfs, other)
        FakeCache(self.top, other, code="code-2").call("load", ("Person", True), self.reader)
        self.assertEqual(self.calls, n + 4, "another RomFS folder")

    def test_memo_dict_kept_per_game_and_code(self):
        c = FakeCache(self.top, self.romfs)
        d = c.memo_dict("reach")
        d[("A001", 1, 2, 3, 5)] = 17
        c.save()
        self.assertEqual(FakeCache(self.top, self.romfs).memo_dict("reach"), {("A001", 1, 2, 3, 5): 17})
        self.assertEqual(FakeCache(self.top, self.romfs, code="code-2").memo_dict("reach"), {})
        with open(self.file, "wb") as fh:
            fh.write(b"tables v3")
        self.assertEqual(FakeCache(self.top, self.romfs).memo_dict("reach"), {})

    def test_lz_only_game_files_are_kept(self):
        raw = os.urandom(300)
        game_lz = C.literal_lz(raw, 0x13)
        with open(os.path.join(self.romfs, "GameData", "A.bin.lz"), "wb") as fh:
            fh.write(game_lz)
        c = FakeCache(self.top, self.romfs)
        self.assertEqual(c.lz_decompress(game_lz, lz.decompress), raw)
        made = C.literal_lz(os.urandom(300), 0x13)            # a made file: never stored
        c.lz_decompress(made, lz.decompress)
        c.save()
        c2 = FakeCache(self.top, self.romfs)
        self.assertEqual(c2.lz_decompress(game_lz, lambda d: self.fail("should be a hit")), raw)
        self.assertEqual(len(c2._lz_pack()), 1)


MAKE = """import sys, os
tool, cache_dir, fast = sys.argv[1:4]
sys.path.insert(0, tool)
if cache_dir != '-':
    import cache
    c = cache.install(cache_dir, fast_patch=fast[0] == '1', progress_lines=fast.endswith('p'))
import rando
r = rando.main(sys.argv[4:])
if cache_dir != '-':
    c.save()
    print('CACHE', c.hits, c.misses, c.lz_hits, c.lz_misses)
sys.exit(r)
"""


@unittest.skipIf(GD is None, "no extracted RomFS / table layouts here")
class RealMake(unittest.TestCase):
    """`rando.py make --patch-out` with and without the cache: every output byte the same, cold and warm."""

    ARGS = ["--seed", "cachetest", "--classes", "on", "--growths", "on", "--enemy-classes", "on",
            "--enemy-weapons", "on", "--class-move", "small", "--shops", "on"]

    # the F-047 agency test, host half: the same rows with another seed and two rows changed after a make finished
    ARGS_B = ["--seed", "cachetest2", "--classes", "on", "--growths", "off", "--enemy-classes", "on",
              "--enemy-weapons", "off", "--class-move", "small", "--shops", "on"]

    def make(self, work, cache_dir="-", fast="0", args=None):
        out, patch = os.path.join(work, "mod"), os.path.join(work, "patch.txt")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, "-c", MAKE, TOOL, cache_dir, fast, "make"] + (args or self.ARGS) +
                           ["--out", out, "--patch-out", patch], capture_output=True, text=True, env=env,
                           encoding="utf-8", errors="replace", timeout=900,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        self.assertEqual(p.returncode, 0, p.stdout[-2000:] + p.stderr[-2000:])
        files = {}
        for dp, _dn, fs in os.walk(work):
            for f in fs:
                q = os.path.join(dp, f)
                with open(q, "rb") as fh:
                    files[os.path.relpath(q, work).replace(os.sep, "/")] = hashlib.sha256(fh.read()).hexdigest()
        stats = [ln for ln in p.stdout.splitlines() if ln.startswith("CACHE ")]
        self.last_progress = [int(ln.split()[1]) for ln in p.stdout.splitlines() if ln.startswith("progress ")]
        return files, (list(map(int, stats[0].split()[1:])) if stats else None)

    def test_hit_is_byte_identical_and_changes_miss(self):
        top = tmpdir()
        try:
            cdir = os.path.join(top, "cache")
            base, _ = self.make(os.path.join(top, "base"))
            cold, s1 = self.make(os.path.join(top, "cold"), cdir, "1")
            warm, s2 = self.make(os.path.join(top, "warm"), cdir, "1")
            slow, s3 = self.make(os.path.join(top, "nofast"), cdir, "0")
            # F-047 agency (host half): rows changed after a finished background make -> the make of the final
            # rows is byte-identical to a fresh make of them with no cache and nothing made before
            changed, _ = self.make(os.path.join(top, "changed"), cdir, "1p", self.ARGS_B)
            self.assertEqual(self.last_progress, [5, 70, 92, 99], "progress lines, in order")
            fresh, _ = self.make(os.path.join(top, "fresh"), "-", "0", self.ARGS_B)
            self.assertEqual(changed, fresh, "the final rows' make = a fresh make of them")
            self.assertNotEqual(changed["patch.txt"], base["patch.txt"], "and not the earlier rows' game")
            self.assertIn("patch.txt", base)
            self.assertEqual(cold, base, "cold cache: same bytes")
            self.assertEqual(warm, base, "warm cache: same bytes")
            self.assertEqual(slow, base, "cache without fast_patch: same bytes")
            self.assertGreater(s1[1], 0, "the first make fills the cache")
            self.assertEqual(s2[1], 0, "the second make reads every table from the cache")
            self.assertEqual(s2[3], 0, "and every original LZ file")
            # the readers' code changes -> every table read again (a miss), output still the same
            c = C.Cache(cdir)
            k_now, _ = c.key("load", ("Job", False))
            c._code = "something else"
            k_other, _ = c.key("load", ("Job", False))
            self.assertNotEqual(k_now, k_other)
        finally:
            C.uninstall()
            shutil.rmtree(top, ignore_errors=True)

    # round 67 core sample (the six-make test above is in tests/heavy.txt): one small seed, so the core never trusts
    # the cache blindly
    ARGS_CORE = ["--seed", "cachecore", "--classes", "off", "--growths", "off", "--join-stats", "off",
                 "--shops", "on"]

    def test_one_seed_hit_is_byte_identical_and_change_misses(self):
        top = tmpdir()
        try:
            cdir = os.path.join(top, "cache")
            base, _ = self.make(os.path.join(top, "base"), args=self.ARGS_CORE)
            cold, s1 = self.make(os.path.join(top, "cold"), cdir, "1", self.ARGS_CORE)
            warm, s2 = self.make(os.path.join(top, "warm"), cdir, "1", self.ARGS_CORE)
            self.assertIn("patch.txt", base)
            self.assertEqual(cold, base, "cold cache: same bytes")
            self.assertEqual(warm, base, "warm cache: same bytes")
            self.assertGreater(s1[1], 0, "the first make fills the cache")
            self.assertEqual(s2[1], 0, "the second make reads every table from the cache")
            c = C.Cache(cdir)
            k_now, _ = c.key("load", ("Job", False))
            c._code = "something else"
            self.assertNotEqual(k_now, c.key("load", ("Job", False))[0], "a code change is a miss")
        finally:
            C.uninstall()
            shutil.rmtree(top, ignore_errors=True)

    def test_install_in_process_changes_no_table(self):
        try:
            plain = GD._load("DisposUnit")
            c = C.install(tmpdir())
            a = GD._load("DisposUnit")
            b = GD._load("DisposUnit")
            self.assertEqual(a, plain)
            self.assertEqual(b, plain)
            a[0]["pid"] = "changed by a caller"
            self.assertEqual(GD._load("DisposUnit"), plain, "each call gets its own copy")
            self.assertGreaterEqual(c.hits, 2)
        finally:
            top = C.installed().top if C.installed() else None
            C.uninstall()
            if top:
                shutil.rmtree(os.path.dirname(top) if os.path.basename(top) == "" else top, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
