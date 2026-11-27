#!/usr/bin/env python3
"""Client of the persistent server mode of the windowless boot (docs/harness/SERVER.md; owner OK "E", 2026-11-13).
Standard library only. Default-off: nothing else in the harness imports this file.

boot-server.exe (tools/harness/build.py --server -> engine/target/zakuro-server/release/) is boot.exe's loop kept
running: the ROM and the recompiled library load once, then one command per line on a pipe. This module starts it
with the same settings headless.py gives boot.exe (a scratch copy of a save zip as ZAKURO_DATA, the fixed clock, the
capture library in original mode, the hardware rasterizer, LOCALAPPDATA and APPDATA below build/), and talks to it:

    with Server("sp-x", save="bt-ch1-clear") as s:        # boot once (about 1 s)
        s.inputs_add("300:A,700:A")                       # absolute-frame presses, held 6 frames each (ZAKURO_INPUT)
        s.step_to(800)                                    # emulate to frame 800
        s.save_slot("a"); s.load_slot("a")                # states in memory; save_file / load_file for disk
        s.markers()                                       # the screen markers (markers.py) read from live memory
        s.board()                                         # cursor and units, as text, from live memory
        s.shot(png)                                       # a picture only when asked
        s.state_digest()                                  # headless.py's digest of a savestate here (proof runs)

Every command has a timeout: the reply is waited for with a blocking queue read (no polling) and a server that does
not answer in time is killed (its process tree, by a job object). The server also stops a step by itself past its
own timeout. Nothing is ever written outside the server's folder below build/ (default build/harness/server/<name>/):
not %APPDATA%, not %LOCALAPPDATA%, not the saves in build/harness/saves/ (copied, never opened for writing), not
boot.exe or the capture library (both copied: a rebuild elsewhere is never blocked by a file held open here).

    python tools/harness/server.py --selftest           the client against a fake server (no game, no build)
    python tools/harness/server.py --check NAME --save ZIP [--route R]   boot, step a route's input, print
                                                        the memory hash and the instruction count
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.append(HERE)  # appended, as the other harness tools do (tools/build.py must not shadow build.py)
import headless as hl  # noqa: E402  (child_env, CLOCK, find_rom, refuse_cias, find_backup, lay_save, state digests)

SERVER_EXE = os.path.join(ROOT, "engine", "target", "zakuro-server", "release", "boot-server" + (".exe" if os.name == "nt" else ""))
DEFAULT_ROOT = os.path.join(ROOT, "build", "harness", "server")
BUILD_TOP = os.path.join(ROOT, "build")
TAG = b"@@zs "
BELOW_NORMAL, IDLE, CREATE_NO_WINDOW = 0x00004000, 0x00000040, 0x08000000
HEAP_PAGE = 1 << 16  # LazyMemory fetches 64 KiB at a time


class ServerError(Exception):
    """The server answered "err ..." (the server is still up)."""


class ServerDied(Exception):
    """The server did not answer in time, or went away (it is killed, the Server object is closed)."""


def _priority() -> int:
    v = (os.environ.get("FEF_ROBOT_PRIORITY") or "below_normal").strip().lower()
    return IDLE if v == "idle" else BELOW_NORMAL  # never higher than below normal from here


class Server:
    """One boot-server process. name: letters, digits, _ . - (its folder is root/name). save: a save zip as
    headless.find_backup takes it (None: the newest PLAY backup is NOT used; an empty save is required by name).
    cheat: True only for a cheat-track session (docs/CHEATS.md rule 3: a cheat save never starts real play)."""

    def __init__(self, name: str, save: str = "new-game-empty", root: str = DEFAULT_ROOT, exe: str | None = None,
                 lib: str | None = None, timeout: float = 600, cheat: bool = False, copy_tools: bool = True,
                 extra_env: dict | None = None, boot_timeout: float = 120):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ServerError(f"name {name}: letters, digits, _ . - only")
        self.name, self.timeout = name, timeout
        self.dir = os.path.abspath(os.path.join(root, name))
        if not hl.below(self.dir, BUILD_TOP):
            raise ServerError(f"{self.dir}: not below build/")
        exe = exe or SERVER_EXE
        lib = lib or hl.LIB
        for p, what in ((exe, "boot-server.exe (python tools/harness/build.py --server)"),
                        (lib, "the capture library (python tools/harness/build.py)")):
            if not os.path.isfile(p):
                raise ServerError(f"no {hl.rel(p)}: {what}")
        rom = hl.find_rom()
        hl.refuse_cias(rom)
        backup = hl.find_backup(save)
        why = hl.save_is_cheat(backup)
        if why and not cheat:
            raise ServerError(f"start save {hl.rel(backup)} is a cheat save ({why}): never starts real play")
        if os.path.isdir(self.dir):
            shutil.rmtree(self.dir)
        for d in ("data", "tmp", "dumps", "shots", "localappdata", "appdata", "bin"):
            os.makedirs(os.path.join(self.dir, d))
        if copy_tools:  # copies kept in root/_tools/, refreshed when the size or time of the original changes
            tools = os.path.join(os.path.abspath(root), "_tools")
            os.makedirs(tools, exist_ok=True)
            copied = []
            for src in (exe, lib):
                dst = os.path.join(tools, os.path.basename(src))
                st = os.stat(src)
                if not (os.path.isfile(dst) and os.stat(dst).st_size == st.st_size
                        and int(os.stat(dst).st_mtime) == int(st.st_mtime)):
                    tmp = f"{dst}.{os.getpid()}.tmp"
                    shutil.copy2(src, tmp)
                    try:
                        os.replace(tmp, dst)
                    except PermissionError:  # the old copy is running in another server: this one gets its own
                        dst = os.path.join(self.dir, "bin", os.path.basename(src))
                        os.replace(tmp, dst)
                copied.append(dst)
            exe, lib = copied
        seed = hl.LOCALAPPDATA  # the pipeline cache, copied (parallel.py does the same per run)
        if os.path.isdir(seed):
            shutil.copytree(seed, os.path.join(self.dir, "localappdata"), dirs_exist_ok=True)
        self.save_zip, self.exe, self.lib, self.rom = backup, exe, lib, rom
        self.data_dir = os.path.join(self.dir, "data")
        self.save_files = hl.lay_save(backup, self.data_dir)
        env = hl.child_env()  # no inherited ZAKURO_ / FE_ / RUST_LOG, no options file (OPTIONS_WIRING section 6)
        env.update(ZAKURO_DATA=self.data_dir, TMP=os.path.join(self.dir, "tmp"), TEMP=os.path.join(self.dir, "tmp"),
                   ZAKURO_CLOCK=hl.CLOCK, ZAKURO_RECOMPILED=lib, LOCALAPPDATA=os.path.join(self.dir, "localappdata"),
                   APPDATA=os.path.join(self.dir, "appdata"), ZAKURO_RASTERIZER="hardware", FE_READABLE="original")
        env.update(extra_env or {})
        self.env = env
        self.log_path = os.path.join(self.dir, "server.log")
        self._log = open(self.log_path, "wb")
        self._q: queue.Queue = queue.Queue()
        self.proc = subprocess.Popen([exe, rom], cwd=os.path.join(self.dir, "tmp"), env=env, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=self._log, bufsize=0,
                                     creationflags=(_priority() | CREATE_NO_WINDOW) if os.name == "nt" else 0)
        self.job = None
        try:
            import parallel as par  # the job object: the tree dies with this process (KILL_ON_JOB_CLOSE)
            self.job = par.TreeJob(name, "idle" if _priority() == IDLE else "below_normal", None)
            self.job.assign(self.proc)
        except Exception:  # noqa: BLE001  (no job object: plain kill on close)
            self.job = None
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        self.closed = False
        self.calls = 0
        started = time.time()
        first = self._reply(boot_timeout, "boot")
        self.boot_seconds = round(time.time() - started, 3)
        self.frame, self.cycles = self._status(first)

    # ------------------------------------------------------------ the pipe
    def _read(self) -> None:
        """The only reader of stdout: reply lines (and the bytes after "bin N") into the queue; other lines into
        the log. Ends with None when the server goes away."""
        out = self.proc.stdout
        try:
            while True:
                line = out.readline()
                if not line:
                    break
                if not line.startswith(TAG):
                    self._log.write(b"[stdout] " + line)
                    continue
                text = line[len(TAG):].rstrip(b"\r\n").decode("utf-8", "replace")
                if text.startswith("bin "):
                    n = int(text[4:])
                    buf = bytearray()
                    while len(buf) < n:
                        chunk = out.read(n - len(buf))
                        if not chunk:
                            break
                        buf += chunk
                    self._q.put(("bin", bytes(buf)))
                else:
                    self._q.put(("line", text))
        except (OSError, ValueError):
            pass
        self._q.put(None)

    def _reply(self, timeout: float, what: str):
        try:
            item = self._q.get(timeout=timeout)  # a blocking wait with a deadline, not a poll
        except queue.Empty:
            self.kill()
            raise ServerDied(f"{self.name}: no answer to '{what}' in {timeout:.0f} s: killed (log {hl.rel(self.log_path)})") from None
        if item is None:
            self.kill()
            raise ServerDied(f"{self.name}: the server went away during '{what}' (exit {self.proc.poll()}; log "
                             f"{hl.rel(self.log_path)})")
        kind, val = item
        if kind == "bin":
            return val
        if val.startswith("err "):
            raise ServerError(f"{what}: {val[4:]}")
        if val.startswith("ok "):
            return val[3:]
        if val.startswith("ready "):
            return val[6:]
        return val

    def cmd(self, line: str, timeout: float | None = None):
        if self.closed:
            raise ServerDied(f"{self.name}: closed")
        if "\n" in line or "\r" in line:
            raise ServerError("one line per command")
        self.calls += 1
        try:
            self.proc.stdin.write(line.encode("utf-8") + b"\n")
            self.proc.stdin.flush()
        except OSError:
            self.kill()
            raise ServerDied(f"{self.name}: the server went away before '{line[:40]}'") from None
        return self._reply(self.timeout if timeout is None else timeout, line.split(" ")[0])

    @staticmethod
    def _status(text: str) -> tuple[int, int]:
        m = re.search(r"frame (\d+) cycles (\d+)", text)
        if not m:
            raise ServerError(f"no frame/cycles in '{text}'")
        return int(m.group(1)), int(m.group(2))

    def _track(self, text: str) -> dict:
        self.frame, self.cycles = self._status(text)
        out = {"frame": self.frame, "cycles": self.cycles}
        for key in ("ms", "bytes"):
            m = re.search(rf"\b{key} (\d+)", text)
            if m:
                out[key] = int(m.group(1))
        return out

    # ------------------------------------------------------------ commands
    def ping(self) -> dict:
        return self._track(self.cmd("ping"))

    def inputs_set(self, spec: str) -> int:
        return int(self.cmd(f"input set {spec or '-'}").split()[-1])

    def inputs_add(self, spec: str) -> int:
        return int(self.cmd(f"input add {spec or '-'}").split()[-1]) if spec else int(self.cmd("input count").split()[-1])

    def inputs_clear(self) -> None:
        self.cmd("input clear")

    def step_to(self, frame: int, shots: list[int] | None = None, dump_at: list[int] | None = None,
                timeout: float | None = None) -> dict:
        """Emulates to frame (the state is then between frames, at `frame`). shots / dump_at: frames to write the
        screens (shots/) or the marker ranges (dumps/) at, as boot.exe's ZAKURO_DUMP_AT does."""
        t = self.timeout if timeout is None else timeout
        opts = f" timeout={int(t * 1000)}"
        if shots:
            self._ensure_dir("shot_dir", "shots")
            opts += " shots=" + ",".join(str(f) for f in shots)
        if dump_at:
            self._ensure_dump()
            opts += " dump_at=" + ",".join(str(f) for f in dump_at)
        try:
            return self._track(self.cmd(f"step to {frame}{opts}", timeout=t + 30))
        except ServerError as e:
            m = re.search(r"frame (\d+) cycles (\d+)", str(e))
            if m:
                self.frame, self.cycles = int(m.group(1)), int(m.group(2))
            raise

    def step(self, frames: int, **kw) -> dict:
        return self.step_to(self.frame + frames, **kw)

    def save_slot(self, name: str) -> dict:
        return self._track(self.cmd(f"save slot {name}"))

    def load_slot(self, name: str) -> dict:
        return self._track(self.cmd(f"load slot {name}"))

    def drop_slot(self, name: str) -> None:
        self.cmd(f"drop slot {name}")

    def save_file(self, path: str) -> dict:
        path = os.path.abspath(path)
        if not hl.below(path, BUILD_TOP):
            raise ServerError(f"{path}: a state is game memory, build/ only")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return self._track(self.cmd(f"save file {path}"))

    def load_file(self, path: str) -> dict:
        return self._track(self.cmd(f"load file {os.path.abspath(path)}"))

    def peek(self, ranges: list[tuple[int, int]]) -> bytes:
        spec = ";".join(f"0x{a:08X},{n}" for a, n in ranges)
        data = self.cmd(f"peek {spec}")
        if not isinstance(data, bytes) or len(data) != sum(n for _a, n in ranges):
            raise ServerError(f"peek {spec}: wrong answer")
        return data

    def peek1(self, addr: int, n: int) -> bytes:
        return self.peek([(addr, n)])

    def u32(self, addr: int) -> int:
        return struct.unpack("<I", self.peek1(addr, 4))[0]

    def _ensure_dir(self, key: str, sub: str) -> str:
        d = os.path.join(self.dir, sub)
        if getattr(self, "_" + key, None) != d:
            self.cmd(f"set {key} {d}")
            setattr(self, "_" + key, d)
        return d

    def _ensure_dump(self) -> None:
        sys.path.insert(0, HERE)
        import markers as mk  # noqa: E402
        sys.path.remove(HERE)
        self._ensure_dir("dump_dir", "dumps")
        if not getattr(self, "_ranges_set", False):
            self.cmd("set dump_ranges " + ";".join(f"0x{a:08X},{n}" for a, n in mk.ranges(mk.load_config())))
            self._ranges_set = True

    def dump(self) -> str:
        """The marker ranges at this frame into dumps/, named as boot.exe names them (markers.load_dumps reads them)."""
        self._ensure_dump()
        self._track(self.cmd("dump"))
        return os.path.join(self.dir, "dumps")

    def shot(self, png: str | None = None, scale: int = 1) -> str | None:
        """Both screens now, as one PNG (headless.contact_sheet: top over bottom). Only when asked."""
        d = self._ensure_dir("shot_dir", "shots")
        self._track(self.cmd("shot"))
        png = png or os.path.join(self.dir, f"shot-{self.frame}.png")
        return hl.contact_sheet(d, [self.frame], png, scale)

    def markers(self) -> dict:
        """markers.py's walk and game_state at this frame, read from live memory page by page (LazyMemory: only the
        ranges markers.json names, as the dump files would hold them, and code.bin); no 56 MiB dump."""
        sys.path.insert(0, HERE)
        import markers as mk  # noqa: E402
        sys.path.remove(HERE)
        cfg = mk.load_config()
        if not hasattr(self, "_names"):
            self._names = mk.Names()
        mem = LazyMemory(self, mk.ranges(cfg), mk.code_bin())
        out = mk.walk(mem, self._names, cfg)
        state = mk.game_state(mem, cfg)
        if state is not None:
            out["state"] = state
        out["pages"] = mem.fetched
        return out

    def board(self) -> dict:
        """The map cursor and every unit (force, x, y, hp, unit address), the reads of robot/act.py's board() made
        from live memory instead of a 16 KiB + 56 MiB dump. Forces: 0 player, 1 enemy, 2 other."""
        g = 0x006D7000
        heap_lo, heap_hi = 0x30000000, 0x30000000 + (56 << 20)
        pool = struct.unpack("<II", self.peek1(g + 0x2F40, 8))
        cp = self.u32(g + 0x198)
        inside = lambda a, n: heap_lo <= a and a + n <= heap_hi  # noqa: E731  (act.py reads the heap dump only)
        cur = list(struct.unpack("<ii", self.peek1(cp, 8))) if inside(cp, 8) else None
        units = []
        for f in range(3):
            head = pool[1] + f * 12
            u = struct.unpack("<I", self.peek1(head, 4))[0] if inside(head, 12) else 0
            seen = 0
            while u and inside(u, 0x140) and seen < 256:
                ub = self.peek1(u, 0x140)
                units.append({"force": f, "x": ub[0xF4], "y": ub[0xF5], "hp": ub[0xF3],
                              "unit": f"{struct.unpack_from('<I', ub, 8)[0]:x}"})
                u = struct.unpack_from("<I", ub, 0x14)[0]
                seen += 1
        return {"frame": self.frame, "cursor": cur, "units": units}

    def state_digest(self) -> dict:
        """headless.state_digest of a savestate made here (the proof's hash: guest memory, metadata, sections). The
        state goes through a file below this server's folder and is deleted after (storage policy)."""
        p = os.path.join(self.dir, "tmp", "digest-state.bin")
        self.save_file(p)
        with open(p, "rb") as fh:
            data = fh.read()
        os.remove(p)
        return hl.state_digest(data, [self.data_dir, self.name])

    def reset_disk(self) -> list[str]:
        """The save folder back to the start save zip (a state holds memory, not the files the game wrote since):
        call it before loading a state saved before the game last wrote its save, e.g. frame 0 again."""
        user = os.path.join(self.data_dir, "user")
        if os.path.isdir(user):
            shutil.rmtree(user)
        self.save_files = hl.lay_save(self.save_zip, self.data_dir)
        return self.save_files

    # ------------------------------------------------------------ life
    def kill(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.job is not None:
            self.job.kill(self.proc)
            self.job.close()
        else:
            try:
                self.proc.kill()
            except OSError:
                pass
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        self._log.close()

    def close(self) -> None:
        if self.closed:
            return
        try:
            self.cmd("quit", timeout=30)
            self.proc.wait(timeout=30)
        except (ServerError, ServerDied, subprocess.TimeoutExpired):
            pass
        if not self.closed:
            self.closed = True
            if self.job is not None:
                self.job.close()
            self._log.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class LazyMemory:
    """markers.Memory with the same answers, fetched from the server on demand: a read inside one of the dump ranges
    gives what that range's dump file would hold at this frame, a read outside them falls back to code.bin, anything
    else None (markers.Memory's rule: parts in base order, code.bin last)."""

    def __init__(self, server, ranges: list[tuple[int, int]], code: bytes | None):
        self.server = server
        self.ranges = sorted(ranges)
        self.code = code
        self.pages: dict[tuple[int, int], bytes] = {}
        self.fetched = 0

    def _byte_range(self, addr: int, size: int) -> bytes | None:
        for base, n in self.ranges:
            if base <= addr and addr + size <= base + n:
                off = addr - base
                first, last = off // HEAP_PAGE, (off + size - 1) // HEAP_PAGE
                buf = b""
                for p in range(first, last + 1):
                    key = (base, p)
                    if key not in self.pages:
                        lo = p * HEAP_PAGE
                        self.pages[key] = self.server.peek1(base + lo, min(HEAP_PAGE, n - lo))
                        self.fetched += 1
                    buf += self.pages[key]
                o = off - first * HEAP_PAGE
                return buf[o:o + size]
        return None

    def _code(self, addr: int, size: int) -> bytes | None:
        import markers as mk  # noqa: E402  (already imported by Server.markers)
        if self.code is not None and mk.CODE_BASE <= addr and addr + size <= mk.CODE_BASE + len(self.code):
            return self.code[addr - mk.CODE_BASE:addr - mk.CODE_BASE + size]
        return None

    def u32(self, addr: int) -> int | None:
        b = self._byte_range(addr, 4)
        if b is None:
            b = self._code(addr, 4)
        return struct.unpack("<I", b)[0] if b is not None else None

    def u8(self, addr: int) -> int | None:
        b = self._byte_range(addr, 1)
        if b is None:
            b = self._code(addr, 1)
        return b[0] if b is not None else None


# ------------------------------------------------------------------ self-test (fake server, no game)
FAKE = r'''
import sys, struct
mem = bytearray(0x100000)          # invented guest memory at 0x30000000
struct.pack_into("<I", mem, 0x10, 0x30000040)
mem[0x40:0x44] = b"WXYZ"
out = sys.stdout.buffer
frame, cycles, slots, inputs = 0, 0, {}, []
def say(s): out.write(b"@@zs " + s.encode() + b"\n"); out.flush()
say("ready frame 0 cycles 0 ms 5")
for line in sys.stdin:
    line = line.strip()
    verb, _, rest = line.partition(" ")
    if verb == "quit": say("ok bye"); break
    if verb == "ping": say(f"ok frame {frame} cycles {cycles}")
    elif verb == "input": inputs.append(rest); say(f"ok inputs {len(inputs)}")
    elif verb == "set": say("ok set")
    elif verb == "step":
        parts = rest.split()
        to = int(parts[1]) if parts[0] == "to" else frame + int(parts[0])
        if to == 666: out.write(b"a stray print\n"); say(f"err timeout frame 600 cycles {cycles} ms 9")
        elif to == 999:
            import time; time.sleep(30)
        elif to == 777: sys.exit(3)
        else:
            cycles += (to - frame) * 1000; frame = to; say(f"ok frame {frame} cycles {cycles} ms 1")
    elif verb == "save": slots[rest.split(" ", 1)[1]] = (frame, cycles); say(f"ok frame {frame} cycles {cycles} bytes 10 ms 1")
    elif verb == "load":
        rest = rest.split(" ", 1)[1]
        if rest not in slots: say(f"err no slot {rest}")
        else: frame, cycles = slots[rest]; say(f"ok frame {frame} cycles {cycles} ms 1 bytes 10")
    elif verb == "peek":
        data = b""
        for r in rest.split(";"):
            a, n = r.split(","); a = int(a, 16) - 0x30000000; n = int(n)
            data += bytes(mem[a:a + n]) if 0 <= a < len(mem) else bytes(n)
        out.write(b"@@zs bin " + str(len(data)).encode() + b"\n" + data); out.flush()
    else: say(f"err unknown command {verb}")
'''


def selftest() -> tuple[list[str], str]:
    errors: list[str] = []
    n = 0

    def check(cond: bool, what: str) -> None:
        nonlocal n
        n += 1
        if not cond:
            errors.append(f"server: {what}")

    tmp = os.path.join(ROOT, "build", "harness", "selftest", "server")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    fake = os.path.join(tmp, "fake_server.py")
    with open(fake, "w", encoding="utf-8") as fh:
        fh.write(FAKE)

    class FakeServer(Server):
        """Server's pipe code on the fake: everything after the process start is the real client."""

        def __init__(self, timeout: float = 5):
            self.name, self.timeout, self.dir = "fake", timeout, tmp
            self.log_path = os.path.join(tmp, "server.log")
            self._log = open(self.log_path, "wb")
            self._q = queue.Queue()
            self.proc = subprocess.Popen([sys.executable, fake], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=self._log, bufsize=0)
            self.job = None
            self._reader = threading.Thread(target=self._read, daemon=True)
            self._reader.start()
            self.closed, self.calls = False, 0
            self.frame, self.cycles = self._status(self._reply(10, "boot"))

    s = FakeServer()
    check((s.frame, s.cycles) == (0, 0), "the ready line gives frame and cycles")
    r = s.step_to(100)
    check(r["frame"] == 100 and r["cycles"] == 100000 and s.frame == 100, f"step_to tracks the frame ({r})")
    s.save_slot("a")
    s.step(50)
    check(s.frame == 150, "step N is relative")
    s.load_slot("a")
    check(s.frame == 100 and s.cycles == 100000, "load_slot brings frame and cycles back")
    try:
        s.load_slot("nope")
        check(False, "an err reply is not raised")
    except ServerError as e:
        check("no slot nope" in str(e), f"err text kept ({e})")
    check(s.peek1(0x30000040, 4) == b"WXYZ", "peek: binary bytes after the bin line")
    check(s.u32(0x30000010) == 0x30000040, "u32 little-endian")
    two = s.peek([(0x30000040, 2), (0x30000042, 2)])
    check(two == b"WXYZ", "several ranges in one peek")
    try:
        s.step_to(666)
        check(False, "a server-side timeout is not raised")
    except ServerError as e:
        check("timeout" in str(e) and s.frame == 600, f"server timeout: frame tracked from the err line ({e}, {s.frame})")
    t0 = time.time()
    try:
        s.step_to(999, timeout=1)
        check(False, "a hung server is not caught")
    except ServerDied as e:
        check("no answer" in str(e) and time.time() - t0 < 40 and s.closed, f"hung server killed on the deadline ({e})")
    check(s.proc.poll() is not None, "the hung server process is gone")
    s2 = FakeServer()
    try:
        s2.step_to(777)
        check(False, "a dead server is not caught")
    except ServerDied as e:
        check("went away" in str(e), f"a server that exits is reported ({e})")
    s3 = FakeServer()
    s3.close()
    check(s3.closed and s3.proc.poll() is not None, "quit ends the server")
    # LazyMemory answers as markers.Memory does on the same bytes
    sys.path.insert(0, HERE)
    import markers as mk  # noqa: E402
    sys.path.remove(HERE)
    blob = bytes((i * 7) & 0xFF for i in range(3 * HEAP_PAGE + 100))
    code = bytes(range(256)) * 4

    class Peeker:
        def peek1(self, a, k):
            return blob[a - 0x30000000:a - 0x30000000 + k]

    lazy = LazyMemory(Peeker(), [(0x30000000, len(blob))], code)
    ref = mk.Memory([(0x30000000, blob)], code)
    probes = [0x30000000, 0x30000000 + HEAP_PAGE - 2, 0x30000000 + 2 * HEAP_PAGE - 1, 0x30000000 + len(blob) - 4,
              0x30000000 + len(blob) - 3, 0x30000000 + len(blob), mk.CODE_BASE, mk.CODE_BASE + 1020, mk.CODE_BASE + 1023,
              0x10, 0x30000000 + 5]
    check(all(lazy.u32(a) == ref.u32(a) and lazy.u8(a) == ref.u8(a) for a in probes),
          "LazyMemory = markers.Memory (page edges, the range's end, code.bin, outside)")
    check(lazy.fetched == 4, f"pages fetched once each ({lazy.fetched})")
    shutil.rmtree(tmp, ignore_errors=True)
    return errors, f"server client self-test: {n - len(errors)}/{n} checks passed"


def prove(route_name: str, name: str, root: str, chunk: int = 80, slot_every: int = 0, file_every: int = 0,
          look_every: int = 100, shot_every: int = 0, say=print) -> dict:
    """The server against a route: pass 1 steps the route's input to save_at in one command (digest), then on to the
    end (instruction count); pass 2, in the same process, loads the frame-0 state again (save folder re-laid) and steps
    in chunks of `chunk` frames with a markers + board read every look_every chunks (and, if asked, a slot save+load
    every slot_every chunks, a file save+load every file_every chunks, a screenshot every shot_every chunks). Both
    passes must give the memory hash and instruction count of the original boot.exe replay (a parallel.py run).
    A save or a screenshot writes the host GPU's pictures down into guest memory (Zakuro's write-back, as boot.exe's
    ZAKURO_SAVE_AT does): with those on, later guest memory may differ from a run without them (same instructions);
    prove_roundtrip compares round trips with the same round trips made by the original boot.exe."""
    route = hl.load_routes()[route_name]
    save_at, frames = int(route["save_at"]), int(route["frames"])
    out = {"route": route_name, "save_at": save_at, "frames": frames, "chunk": chunk}
    t0 = time.time()
    with Server(name, save=route.get("save") or "new-game-empty", root=root, timeout=1800) as s:
        out["boot_s"] = s.boot_seconds
        s.save_slot("frame0")
        s.inputs_set(route["input"])
        t = time.time()
        s.step_to(save_at)
        d1 = s.state_digest()
        s.step_to(frames)
        out["straight"] = {"memory": d1["memory"], "instructions": s.cycles, "seconds": round(time.time() - t, 1)}
        say(f"[{name}] straight: memory {d1['memory'][:16]} instructions {s.cycles} ({out['straight']['seconds']} s)")
        s.reset_disk()
        s.load_slot("frame0")
        t, k, n = time.time(), 0, {"slot": 0, "file": 0, "look": 0, "shot": 0}
        f = 0
        while f < save_at:
            f = min(f + chunk, save_at)
            s.step_to(f)
            k += 1
            if slot_every and k % slot_every == 0:
                s.save_slot("rt")
                s.load_slot("rt")
                n["slot"] += 1
            if file_every and k % file_every == 0:
                p = os.path.join(s.dir, "tmp", "rt.bin")
                s.save_file(p)
                s.load_file(p)
                os.remove(p)
                n["file"] += 1
            if look_every and k % look_every == 0:
                s.markers()
                s.board()
                n["look"] += 1
            if shot_every and k % shot_every == 0:
                s.shot()
                n["shot"] += 1
        d2 = s.state_digest()
        s.step_to(frames)
        out["chunked"] = {"memory": d2["memory"], "instructions": s.cycles, "commands": s.calls, "chunks": k,
                          "round_trips": n, "seconds": round(time.time() - t, 1)}
        say(f"[{name}] chunked ({k} chunks of {chunk}, round trips {n}): memory {d2['memory'][:16]} instructions "
            f"{s.cycles} ({out['chunked']['seconds']} s)")
    out["same"] = out["straight"]["memory"] == out["chunked"]["memory"] and         out["straight"]["instructions"] == out["chunked"]["instructions"]
    out["wall_s"] = round(time.time() - t0, 1)
    return out


def prove_roundtrip(route_name: str, name: str, root: str, cuts: list[int], say=print) -> dict:
    """Save/load round trips, server against the ORIGINAL boot.exe doing the same: the original runs the route as a
    robot chain does (run k saves its state at cuts[k] with ZAKURO_SAVE_AT, run k+1 starts from it with ZAKURO_LOAD;
    the last run saves at save_at), each a fresh boot.exe (a byte-identical copy below root/, so the original file is
    never held open). The server makes the same cuts in one process: a slot round trip at even cuts, a file round
    trip at odd ones. Same memory hash at save_at and same instruction count at the end = the round trips are exact."""
    route = hl.load_routes()[route_name]
    save_at, frames = int(route["save_at"]), int(route["frames"])
    cuts = sorted(c for c in cuts if 0 < c < save_at)
    out = {"route": route_name, "cuts": cuts}
    t = time.time()
    with Server(name, save=route.get("save") or "new-game-empty", root=root, timeout=1800) as s:
        s.inputs_set(route["input"])
        for k, c in enumerate(cuts):
            s.step_to(c)
            if k % 2 == 0:
                s.save_slot("rt")
                s.load_slot("rt")
            else:
                p = os.path.join(s.dir, "tmp", "rt.bin")
                s.save_file(p)
                s.load_file(p)
                os.remove(p)
        s.step_to(save_at)
        d = s.state_digest()
        s.step_to(frames)
        out["server"] = {"memory": d["memory"], "instructions": s.cycles, "seconds": round(time.time() - t, 1)}
    say(f"[{name}] server, round trips at {cuts}: memory {d['memory'][:16]} instructions {out['server']['instructions']}")
    # the original boot.exe in this area's own folders: headless.run with its folder constants moved (as parallel.py's
    # worker does), restored after
    orig_dir = os.path.abspath(os.path.join(root, name + "-orig"))
    if os.path.isdir(orig_dir):
        shutil.rmtree(orig_dir)
    for d_ in ("bin", "saves", "appdata"):
        os.makedirs(os.path.join(orig_dir, d_))
    shutil.copy2(hl.BOOT, os.path.join(orig_dir, "bin", "boot.exe"))
    lib = os.path.join(orig_dir, "bin", os.path.basename(hl.LIB))
    shutil.copy2(hl.LIB, lib)
    zip_ = hl.find_backup(route.get("save") or "new-game-empty")
    shutil.copy2(zip_, os.path.join(orig_dir, "saves", os.path.basename(zip_)))
    if os.path.isdir(hl.LOCALAPPDATA):
        shutil.copytree(hl.LOCALAPPDATA, os.path.join(orig_dir, "localappdata"))
    keep = {k: getattr(hl, k) for k in ("BUILD", "RUNS", "SAVES", "LOCALAPPDATA", "BOOT", "load_routes", "boot_env")}
    t = time.time()
    try:
        hl.BUILD, hl.RUNS, hl.SAVES = orig_dir, os.path.join(orig_dir, "runs"), os.path.join(orig_dir, "saves")
        hl.LOCALAPPDATA, hl.BOOT = os.path.join(orig_dir, "localappdata"), os.path.join(orig_dir, "bin", "boot.exe")
        state_in = None
        ends = cuts + [save_at]
        for k, c in enumerate(ends):
            last = k == len(ends) - 1
            r = {"frames": frames if last else c + 10, "input": route["input"], "save_at": c,
                 "shots": [frames - 1 if last else c + 5], "verified": False}
            if not last:  # a run's input must lie inside it (headless's route rule): the presses before its end
                kept_in = [x for x in route["input"].split(",") if int(x.split(":")[0]) < c + 10]
                r["input"] = ",".join(kept_in) if kept_in else f"{c + 5}:A"
            hl.load_routes = lambda path=None, r=r: {"rt": r}

            def env(*a, state_in=state_in, **kw):
                e = keep["boot_env"](*a, **kw)
                e["APPDATA"] = os.path.join(orig_dir, "appdata")
                if state_in:
                    e["ZAKURO_LOAD"] = state_in
                return e
            hl.boot_env = env
            res = hl.run(f"{name}-o{k}", "rt", "original", save=os.path.basename(zip_), lib=lib, keep_state=not last,
                         timeout=3600, say=lambda *a: None)
            if res.get("exit_code") != 0 or "state" not in res:
                raise ServerError(f"original run {k} failed: exit {res.get('exit_code')}")
            if not last:
                state_in = os.path.join(orig_dir, f"cut{k}.bin")
                shutil.move(os.path.join(hl.RUNS, f"{name}-o{k}", "state.bin"), state_in)
        out["original"] = {"memory": res["state"]["memory"], "instructions": res["instructions"], "runs": len(ends),
                           "seconds": round(time.time() - t, 1), "boot_exe_sha256": res["boot_exe_sha256"]}
    finally:
        for k_, v in keep.items():
            setattr(hl, k_, v)
    say(f"[{name}] original boot.exe chain, same cuts: memory {out['original']['memory'][:16]} instructions "
        f"{out['original']['instructions']}")
    out["same"] = out["server"]["memory"] == out["original"]["memory"] and \
        out["server"]["instructions"] == out["original"]["instructions"]
    for f in [x for x in os.listdir(orig_dir) if x.endswith(".bin")]:
        os.remove(os.path.join(orig_dir, f))  # states are game memory: regenerated, not kept
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check", metavar="NAME", help="boot, run a route's input to its save_at, print hash and count")
    ap.add_argument("--prove", metavar="NAME", help="--route R: straight and chunked passes (see prove())")
    ap.add_argument("--chunk", type=int, default=80)
    ap.add_argument("--slot-every", type=int, default=0)
    ap.add_argument("--file-every", type=int, default=0)
    ap.add_argument("--roundtrip", metavar="NAME", help="--route R --cuts F,F: round trips vs the original boot.exe's")
    ap.add_argument("--cuts", default="")
    ap.add_argument("--shot-every", type=int, default=0)
    ap.add_argument("--expect", help="a parallel.py summary.json: compare with its run of the same route")
    ap.add_argument("--route")
    ap.add_argument("--save")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    a = ap.parse_args(argv)
    if a.selftest:
        errs, line = selftest()
        for e in errs:
            print("  FAIL", e)
        print(line)
        return 1 if errs else 0
    if a.prove:
        r = prove(a.route, a.prove, a.root, chunk=a.chunk, slot_every=a.slot_every, file_every=a.file_every,
                  shot_every=a.shot_every)
        if a.expect:
            with open(a.expect, encoding="utf-8") as fh:
                ref = [x for x in json.load(fh)["runs"] if x.get("route") == a.route]
            if ref:
                r["original"] = {"memory": ref[0]["memory"], "instructions": ref[0]["instructions"], "run": ref[0]["run"]}
                r["matches_original"] = all(r[k]["memory"] == ref[0]["memory"] and r[k]["instructions"] ==
                                            ref[0]["instructions"] for k in ("straight", "chunked"))
        print(json.dumps(r, indent=1))
        return 0 if r["same"] and r.get("matches_original", True) else 1
    if a.roundtrip:
        r = prove_roundtrip(a.route, a.roundtrip, a.root, [int(x) for x in a.cuts.split(",") if x])
        print(json.dumps(r, indent=1))
        return 0 if r["same"] else 1
    if a.check:
        route = hl.load_routes()[a.route]
        with Server(a.check, save=a.save or route.get("save") or "new-game-empty", root=a.root) as s:
            s.inputs_set(route["input"])
            s.step_to(int(route["save_at"]))
            d = s.state_digest()
            s.step_to(int(route["frames"]))
            print(json.dumps({"route": a.route, "memory": d["memory"], "instructions_at_end": s.cycles,
                              "boot_s": s.boot_seconds}, indent=1))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
