#!/usr/bin/env python3
"""Watchdogs for short robot runs (F-039 step 3, docs/tests/WATCHDOGS.md).

One run of boot.exe on an existing route, watched while it goes. boot.exe dumps both screens and the game's own
data+bss block (0x006B4000, 0xC9000 bytes: config/game.json segments) every --every frames; the watchdog hashes each
sample as it appears and deletes the files at once. Five watchdogs, each with a plain one-line verdict and the press
index (the route's ZAKURO_INPUT entries, counted from 1):

    crash      boot.exe exited early, with a non-zero code, an outcome other than Completed, or a panic
    hang       no new frame for --hang-s seconds of wall time (120 by default), or the game's data+bss unchanged
               for 600 frames (the frames run, the game does not)
    stuck      no new picture (top and bottom; a loop such as a blinking cursor counts as unchanged) for 600 frames
               while 3 presses went in; config/harness/watchdog.json "static_ok" lists screens that are
               legitimately static
    softlock   6 presses in a row (over at least 600 frames) changed nothing in the game's data+bss beyond its own
               tickers (256-byte blocks that changed in at least half of the last 16 press-free stretches)
    roundtrip  savestate at the route's save frame (a hub), loaded again by a second boot.exe and saved at once:
               the guest memory (FCRAM, VRAM, DSP RAM, AXI WRAM) must be byte-identical, metadata as h4a accepts

Everything a run writes is below build/watchdog/<session>/ (data, tmp, appdata, localappdata copies, results);
the start save is copied from build/harness/saves/ (only read). The owner's saves, %APPDATA%, %LOCALAPPDATA%: never.
boot.exe runs below normal priority, without a window. No new play: only existing routes (a plant variant cuts an
existing route and adds presses on its last screen, kept in the session folder, never in routes.json).

    python tools/harness/watchdog.py --selftest                     the detectors on made-up samples (no game)
    python tools/harness/watchdog.py run --route title [--roundtrip]
    python tools/harness/watchdog.py live-selftest [--jobs 2]       one planted fault of each kind + 3 clean routes
"""
from __future__ import annotations

import argparse
import concurrent.futures
import ctypes
import glob
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "build", "watchdog")
CONFIG = os.path.join(ROOT, "config", "harness", "watchdog.json")
GUEST_RANGE = (0x006B4000, 0xC9000)  # data 0x4AF50 + bss 0x7BE28 from config/game.json, rounded up to a page
BLOCK = 256  # soft-lock: the game's data+bss compared in blocks of this many bytes
HOLD = 6  # boot.exe holds each scripted button for 6 frames
BELOW_NORMAL = 0x00004000
CREATE_NO_WINDOW = 0x08000000
DEFAULT_SAVE = "new-game-empty"


class Stop(Exception):
    """A setup problem: printed, the run is not made."""


def rel(p: str) -> str:
    try:
        return os.path.relpath(p, ROOT).replace("\\", "/")
    except ValueError:
        return p


def below(p: str, top: str) -> bool:
    p, top = os.path.abspath(p), os.path.abspath(top)
    return p.startswith(top + os.sep) and ".." not in p.split(os.sep)


# ------------------------------------------------------------------ presses
def parse_presses(spec: str) -> list[tuple[int, str]]:
    out = []
    for item in (spec or "").split(","):
        item = item.strip()
        if item:
            f, b = item.split(":", 1)
            out.append((int(f), b))
    return out


class Presses:
    def __init__(self, spec: str):
        self.items = parse_presses(spec)
        self.frames = [f for f, _ in self.items]

    def index_at(self, frame: int) -> int:
        """1-based index of the last press that started at or before frame (0: none yet)."""
        lo, hi = 0, len(self.frames)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.frames[mid] <= frame:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def between(self, a: int, b: int) -> list[int]:
        """1-based indexes of the presses held at any frame in (a, b]."""
        return [i + 1 for i, f in enumerate(self.frames) if f + HOLD > a + 1 and f <= b]

    def describe(self, idx: int) -> str:
        if idx <= 0 or idx > len(self.items):
            return "press 0 (before the first press)"
        f, b = self.items[idx - 1]
        return f"press {idx} of {len(self.items)} (frame {f} {b})"


# ------------------------------------------------------------------ allow-list
def load_allow(path: str = CONFIG) -> dict:
    if not os.path.isfile(path):
        return {"static_ok": []}
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    for e in cfg.get("static_ok", []):
        if not e.get("why"):
            raise Stop(f"{rel(path)}: every static_ok entry needs a 'why'")
        if not (("route" in e and "from" in e and "to" in e) or "picture" in e):
            raise Stop(f"{rel(path)}: static_ok entry needs route/from/to or picture: {e}")
    return cfg


def static_allowed(allow: dict, route: str, start: int, end: int, picture: str) -> str | None:
    for e in allow.get("static_ok", []):
        if "picture" in e and e["picture"] == picture:
            return e["why"]
        if e.get("route") == route and e["from"] <= start and end <= e["to"]:
            return e["why"]
    return None


# ------------------------------------------------------------------ the detectors (pure: fed one sample at a time)
class Watch:
    """Fed samples in frame order: (frame, picture hash, guest bytes or None). Returns the first verdict."""

    def __init__(self, route: str, presses: Presses, allow: dict | None = None, stuck_frames: int = 600,
                 stuck_presses: int = 3, soft_presses: int = 6, soft_frames: int = 600, guest_frames: int = 600,
                 hang_s: float = 120.0, min_idle: int = 4, idle_keep: int = 16):
        self.route, self.p, self.allow = route, presses, allow or {"static_ok": []}
        self.stuck_frames, self.stuck_presses = stuck_frames, stuck_presses
        self.soft_presses, self.soft_frames, self.guest_frames = soft_presses, soft_frames, guest_frames
        self.hang_s, self.min_idle, self.idle_keep = hang_s, min_idle, idle_keep
        self.idle_window = []  # the last idle_keep press-free change masks
        self.prev = None  # (frame, picture, guest array)
        self.pic_since = None  # frame of the last new picture
        self.recent = {}  # picture hash -> last frame seen
        self.guest_since = None  # frame of the last raw data+bss change
        self.state_since = None  # frame of the last data+bss change beyond the tickers
        self.idle_count = None
        self.idle_total = 0
        self.samples = 0
        self.last_wall = None
        self.verdict = None
        self.allowed_static = []  # (from, to, why) stretches the allow-list excused
        self.trace = []  # per sample: frame, picture hash (8), data+bss changed, changed beyond the tickers

    def _set(self, kind: str, frame: int, idx: int, what: str) -> dict:
        self.verdict = {"kind": kind, "frame": frame, "press": idx,
                        "line": f"{kind.upper()}: {what}; at frame {frame}, {self.p.describe(idx)}"}
        return self.verdict

    def feed(self, frame: int, picture: str, guest: bytes | None, wall: float | None = None) -> dict | None:
        import numpy as np
        if self.verdict:
            return self.verdict
        self.samples += 1
        self.last_wall = time.time() if wall is None else wall
        # compared in 256-byte blocks: a counter's high bytes change rarely and a ring buffer writes a new slot each
        # time, but their block changes with every sample (measured on the main menu: 78 of 3216 blocks tick)
        n = len(guest) // BLOCK * BLOCK if guest is not None else 0
        g = np.frombuffer(guest[:n], dtype="<u8").reshape(-1, BLOCK // 8) if guest is not None else None
        if self.prev is None:
            self.prev = (frame, picture, g)
            self.pic_since = self.guest_since = self.state_since = frame
            self.recent[picture] = frame
            if g is not None:
                self.idle_count = np.zeros(g.shape[0], dtype=np.int32)
            return None
        pf, ppic, pg = self.prev
        # a new picture: one not seen in the last stuck_frames frames (a loop such as a blinking cursor repeats
        # the same few pictures and counts as unchanged)
        seen = self.recent.get(picture)
        if picture != ppic and (seen is None or frame - seen > self.stuck_frames):
            self.pic_since = frame
        self.recent[picture] = frame
        if len(self.recent) > 4096:
            self.recent = {k: v for k, v in self.recent.items() if frame - v <= self.stuck_frames}
        if g is not None and pg is not None and len(g) == len(pg):
            d = (g != pg).any(axis=1)
            if d.any():
                self.guest_since = frame
            pressed = self.p.between(pf, frame)
            if not pressed:  # a press-free stretch: what changes here, the game changes by itself
                self.idle_count += d
                self.idle_window.append(d)
                if len(self.idle_window) > self.idle_keep:
                    self.idle_count -= self.idle_window.pop(0)
                self.idle_total = len(self.idle_window)
            if self.idle_total >= self.min_idle:
                # tickers: words that changed in at least half of the last idle_keep press-free stretches
                ticker = self.idle_count * 2 >= self.idle_total
                if (d & ~ticker).any():
                    self.state_since = frame
            else:
                self.state_since = frame  # too few press-free stretches to know the tickers: count as a change
        self.prev = (frame, picture, g)
        self.trace.append([frame, picture[:8], self.guest_since == frame, self.state_since == frame])
        # hang: the guest stands still while frames run
        if g is not None and frame - self.guest_since >= self.guest_frames:
            return self._set("hang", frame, self.p.index_at(frame),
                             f"the game's data+bss unchanged for {frame - self.guest_since} frames (no guest progress)")
        # stuck frame: picture unchanged while presses go in
        pressed = self.p.between(self.pic_since, frame)
        if frame - self.pic_since >= self.stuck_frames and len(pressed) >= self.stuck_presses:
            why = static_allowed(self.allow, self.route, self.pic_since, frame, picture)
            if why:
                if not self.allowed_static or self.allowed_static[-1][0] != self.pic_since:
                    self.allowed_static.append([self.pic_since, frame, why])
                else:
                    self.allowed_static[-1][1] = frame
            else:
                return self._set("stuck", frame, pressed[0],
                                 f"no new picture for {frame - self.pic_since} frames (last {picture[:12]}) while "
                                 f"{len(pressed)} presses went in")
        # soft-lock: presses change nothing in the game's state
        pressed = self.p.between(self.state_since, frame)
        if g is not None and len(pressed) >= self.soft_presses and frame - self.state_since >= self.soft_frames:
            return self._set("softlock", frame, pressed[0],
                             f"{len(pressed)} presses in {frame - self.state_since} frames changed nothing in the "
                             f"game's data+bss beyond its tickers")
        return None

    def wall_check(self, now: float, frame_hint: int | None = None) -> dict | None:
        if self.verdict or self.last_wall is None:
            return self.verdict
        if now - self.last_wall >= self.hang_s:
            f = self.prev[0] if self.prev else (frame_hint or 0)
            return self._set("hang", f, self.p.index_at(f),
                             f"no new frame for {now - self.last_wall:.0f} s of wall time after frame {f}")
        return None

    def finish(self, rc: int | None, outcome: str | None, frames_done: int | None, frames_wanted: int,
               log_text: str) -> dict:
        if self.verdict:
            return self.verdict
        last = self.prev[0] if self.prev else 0
        panic = re.search(r"panicked at|thread '.*' panicked|STATUS_ACCESS_VIOLATION|exception", log_text, re.I)
        if rc != 0 or outcome != "Completed" or (frames_done or 0) < frames_wanted or panic:
            bits = [f"exit code {rc}"]
            bits.append(f"outcome {outcome or 'none'}" + (f" after {frames_done} frames" if frames_done else ""))
            if panic:
                bits.append(f"log: {panic.group(0)}")
            f = frames_done or last
            return self._set("crash", f, self.p.index_at(f),
                             "boot.exe stopped early (" + ", ".join(bits) + f"; last sample frame {last})")
        self.verdict = {"kind": "clean", "frame": frames_done, "press": len(self.p.items),
                        "line": f"CLEAN: {frames_done} frames, {self.samples} samples, all "
                                f"{len(self.p.items)} presses, no crash, hang, stuck frame or soft-lock"
                                + (f" ({len(self.allowed_static)} allow-listed static stretch(es))"
                                   if self.allowed_static else "")}
        return self.verdict


# ------------------------------------------------------------------ savestates (headless.py's format)
def headless():
    sys.path.insert(0, HERE)
    try:
        import headless as hl  # noqa: E402
    finally:
        sys.path.remove(HERE)
    return hl


def corrupt_state(src: str, dst: str, section: int = 1, offset: int = 0x100000) -> str:
    """A copy of a savestate with one byte of one guest memory section flipped (FCRAM by default), re-encoded
    as literal-only LZ4 blocks so it still loads. For the round-trip plant only (robot data under build/)."""
    hl = headless()
    with open(src, "rb") as fh:
        data = fh.read()
    vl = struct.unpack_from("<I", data, 8)[0]
    head = data[:12 + vl + 8]
    _version, secs = hl.state_sections(data)
    del data
    sec = bytearray(secs[section])
    sec[offset] ^= 0xFF
    secs[section] = bytes(sec)
    with open(dst, "wb") as fh:
        fh.write(head)
        for s in secs:
            comp = struct.pack("<I", len(s)) + hl.lz4_literals(s)
            fh.write(struct.pack("<Q", len(comp)))
            fh.write(comp)
    return f"flipped byte 0x{offset:X} of section {hl.SECTIONS[section]}"


def digest_file(path: str, own: list[str]) -> tuple[dict, bytes]:
    hl = headless()
    with open(path, "rb") as fh:
        data = fh.read()
    version, secs = hl.state_sections(data)
    del data
    return hl.sections_digest(version, secs, own), hl.strip_meta(secs[0], own)


# ------------------------------------------------------------------ process control
def suspend(pid: int, on: bool) -> bool:
    if os.name != "nt":
        import signal
        os.kill(pid, signal.SIGSTOP if on else signal.SIGCONT)
        return True
    k32, nt = ctypes.windll.kernel32, ctypes.windll.ntdll
    h = k32.OpenProcess(0x0800, False, pid)  # PROCESS_SUSPEND_RESUME
    if not h:
        return False
    try:
        return (nt.NtSuspendProcess(h) if on else nt.NtResumeProcess(h)) == 0
    finally:
        k32.CloseHandle(h)


# ------------------------------------------------------------------ one watched run
class Lane:
    """build/watchdog/<session>/: shared copies of boot.exe and the library, one folder per run."""

    def __init__(self, session: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", session):
            raise Stop(f"session {session}: letters, digits, _ . - only")
        self.hl = headless()
        self.dir = os.path.join(OUT, session)
        self.routes = self.hl.load_routes()

    def stage(self) -> None:
        hl = self.hl
        for p in (hl.BOOT, hl.LIB):
            if not os.path.isfile(p):
                raise Stop(f"no {rel(p)}")
        if os.path.isdir(self.dir):
            shutil.rmtree(self.dir)
        os.makedirs(os.path.join(self.dir, "bin"))
        os.makedirs(os.path.join(self.dir, "results"))
        self.boot = os.path.join(self.dir, "bin", os.path.basename(hl.BOOT))
        self.lib = os.path.join(self.dir, "bin", os.path.basename(hl.LIB))
        shutil.copy2(hl.BOOT, self.boot)
        shutil.copy2(hl.LIB, self.lib)

    def route(self, name: str) -> dict:
        r = self.routes.get(name)
        if r is None:
            raise Stop(f"no route {name}")
        if r.get("cheat") or r.get("pokes"):
            raise Stop(f"route {name}: cheat routes run in stages; the watchdogs take plain routes")
        if "options" in r:
            raise Stop(f"route {name}: options-track routes stay off the shared capture library")
        return dict(r)

    def watch(self, run: str, route_name: str, route: dict, every: int = 30, roundtrip: bool = False,
              corrupt: bool = False, plant: dict | None = None, limits: dict | None = None, say=print,
              keep_guest: str | None = None) -> dict:
        hl = self.hl
        root = os.path.join(self.dir, "runs", run)
        if not below(root, OUT):
            raise Stop(f"{root}: not below build/watchdog/")
        if os.path.isdir(root):
            shutil.rmtree(root)
        data_dir, tmp_dir, run_dir = (os.path.join(root, d) for d in ("data", "tmp", "run"))
        appdata, lad = os.path.join(root, "appdata"), os.path.join(root, "localappdata")
        for d in (data_dir, tmp_dir, run_dir, appdata):
            os.makedirs(d)
        seed = os.path.join(hl.BUILD, "localappdata")
        if os.path.isdir(seed):
            shutil.copytree(seed, lad)
        else:
            os.makedirs(lad)
        save_name = route.get("save") or DEFAULT_SAVE
        backup = hl.find_backup(save_name)  # build/harness/saves/<name>.zip: only read
        cheat = hl.save_is_cheat(backup)
        if cheat:
            raise Stop(f"{run}: start save {save_name} is a cheat save ({cheat}); the watchdogs take real-play saves")
        if hl.save_is_options(backup):
            raise Stop(f"{run}: start save {save_name} is an options save")
        save_copy = os.path.join(root, os.path.basename(backup))
        shutil.copy2(backup, save_copy)
        hl.lay_save(save_copy, data_dir)
        frames = int(route["frames"])
        save_at = int(route["save_at"])
        samples = sorted(set(range(every, frames, every)) | {int(s) for s in route["shots"]})
        state_a = os.path.join(tmp_dir, "state.bin")
        wroute = dict(route, shots=samples)
        old_build = hl.BUILD
        hl.BUILD = OUT  # boot_env's folder rule: below build/watchdog/ here
        try:
            env = hl.boot_env(wroute, data_dir, tmp_dir, run_dir, "original", "ab", True, self.lib, state_a)
        finally:
            hl.BUILD = old_build
        env.update(LOCALAPPDATA=lad, APPDATA=appdata,
                   ZAKURO_DUMP_MEM=f"0x{GUEST_RANGE[0]:08X},{GUEST_RANGE[1]}", ZAKURO_DUMP_MEM_AT="1")
        lim = dict(limits or {})
        w = Watch(route_name, Presses(route["input"]), load_allow(), **lim)
        rom = hl.find_rom()
        log_path = os.path.join(run_dir, "boot.log")
        started = time.time()
        planted = None
        killed_by_watch = False
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            proc = subprocess.Popen([self.boot, rom, str(frames)], cwd=tmp_dir, env=env, stdout=log,
                                    stderr=subprocess.STDOUT,
                                    creationflags=(CREATE_NO_WINDOW | BELOW_NORMAL) if os.name == "nt" else 0)
            w.last_wall = time.time()
            done: set[int] = set()
            last_png = None
            try:
                while True:
                    exited = proc.poll() is not None
                    tops = {}
                    for p in glob.glob(os.path.join(tmp_dir, "zakuro-top-*.ppm")):
                        m = re.search(r"zakuro-top-(\d+)\.ppm$", p)
                        if m:
                            tops[int(m.group(1))] = p
                    ready = sorted(f for f in tops if f not in done)
                    newest = max(tops) if tops else -1
                    for f in ready:
                        if f == newest and not exited:
                            break  # the newest sample may still be being written
                        top = tops[f]
                        bot = os.path.join(tmp_dir, f"zakuro-bottom-{f}.ppm")
                        dump = os.path.join(tmp_dir, f"zakuro-dump-0x{GUEST_RANGE[0]:08X}-{f}.bin")
                        h = hashlib.sha256()
                        for q in (top, bot):
                            if os.path.isfile(q):
                                with open(q, "rb") as fh:
                                    h.update(fh.read())
                        guest = None
                        if os.path.isfile(dump):
                            with open(dump, "rb") as fh:
                                guest = fh.read()
                            if keep_guest:  # discovery only: the samples kept for a look offline
                                os.makedirs(keep_guest, exist_ok=True)
                                shutil.move(dump, os.path.join(keep_guest, f"{f}.bin"))
                            else:
                                os.remove(dump)
                        if last_png is not None:  # keep only the latest sample's pictures (for a verdict picture)
                            for old in glob.glob(os.path.join(tmp_dir, f"zakuro-*-{last_png}.ppm")):
                                os.remove(old)
                        last_png = f
                        done.add(f)
                        w.feed(f, h.hexdigest(), guest)
                        if plant and not planted and f >= plant.get("at", 0):
                            if plant["kind"] == "kill":
                                proc.kill()
                                planted = f"killed boot.exe after sample frame {f}"
                            elif plant["kind"] == "pause":
                                planted = f"suspended boot.exe after sample frame {f}: " + \
                                          ("ok" if suspend(proc.pid, True) else "FAILED")
                            say(f"[{run}] plant: {planted}")
                        if w.verdict:
                            break
                    if w.verdict:
                        break
                    if exited:
                        break
                    if w.wall_check(time.time()):
                        break
                    time.sleep(0.2)
            except BaseException:  # never leave a boot.exe behind
                if proc.poll() is None:
                    suspend(proc.pid, False)
                    proc.kill()
                raise
            if proc.poll() is None:  # a verdict before the end (hang, stuck, soft-lock): stop the run
                killed_by_watch = True
                if plant and plant["kind"] == "pause":
                    suspend(proc.pid, False)
                proc.kill()
            proc.wait()
        rc = proc.returncode
        text = open(log_path, encoding="utf-8", errors="replace").read()
        m = re.search(r"outcome:\s+(\w+) after (\d+) frames", text)
        verdict = w.finish(rc, m.group(1) if m else None, int(m.group(2)) if m else None, frames, text)
        picture = None
        if verdict["kind"] != "clean" and last_png is not None:
            picture = hl.contact_sheet(tmp_dir, [last_png], os.path.join(self.dir, "results", f"{run}.png"))
        result = {"run": run, "route": route_name, "save": save_name, "frames": frames, "every": every,
                  "seconds": round(time.time() - started, 1), "exit_code": rc, "samples": w.samples,
                  "verdict": verdict, "plant": planted or (plant or {}).get("kind"),
                  "stopped_by_watchdog": killed_by_watch, "allowed_static": w.allowed_static,
                  "picture": rel(picture) if picture else None, "limits": lim,
                  "trace": w.trace}
        say(f"[{run}] {verdict['line']}")
        if roundtrip and verdict["kind"] == "clean":
            result["roundtrip"] = self.roundtrip(run, route_name, rom, root, data_dir, tmp_dir, run_dir, appdata, lad,
                                                 state_a, save_at, corrupt, say)
            if result["roundtrip"]["kind"] != "clean":
                result["verdict"] = result["roundtrip"]
        if verdict["kind"] != "clean":
            result["log_tail"] = text.splitlines()[-12:]
        with open(os.path.join(self.dir, "results", f"{run}.json"), "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=1)
        shutil.rmtree(root, ignore_errors=True)  # bulky own intermediates (states, dumps, copies)
        return result

    def roundtrip(self, run, route_name, rom, root, data_dir, tmp_dir, run_dir, appdata, lad, state_a, save_at,
                  corrupt, say) -> dict:
        hl = self.hl
        own = [data_dir, run]
        if not os.path.isfile(state_a):
            return {"kind": "roundtrip", "line": f"ROUNDTRIP: no savestate at frame {save_at}", "press": None,
                    "frame": save_at}
        da, ma = digest_file(state_a, own)
        load = state_a
        note = None
        if corrupt:
            load = os.path.join(tmp_dir, "state-corrupt.bin")
            note = corrupt_state(state_a, load)
            say(f"[{run}] plant: corrupt reloaded copy, {note}")
        state_b = os.path.join(tmp_dir, "state-b.bin")
        old_build = hl.BUILD
        hl.BUILD = OUT
        try:
            env = hl.boot_env({"input": "", "shots": [], "save_at": save_at}, data_dir, tmp_dir, run_dir, "original",
                              "ab", True, self.lib, state_b)
        finally:
            hl.BUILD = old_build
        env.update(LOCALAPPDATA=lad, APPDATA=appdata, ZAKURO_LOAD=load)
        env.pop("ZAKURO_INPUT", None)
        env.pop("ZAKURO_DUMP_AT", None)
        log_path = os.path.join(run_dir, "boot-load.log")
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            p = subprocess.run([self.boot, rom, str(save_at + 1)], cwd=tmp_dir, env=env, stdout=log,
                               stderr=subprocess.STDOUT, timeout=600,
                               creationflags=(CREATE_NO_WINDOW | BELOW_NORMAL) if os.name == "nt" else 0)
        text = open(log_path, encoding="utf-8", errors="replace").read()
        loaded = re.search(r"loaded the state at frame (\d+)", text)
        if p.returncode != 0 or not loaded or not os.path.isfile(state_b):
            return {"kind": "roundtrip", "frame": save_at, "press": None,
                    "line": f"ROUNDTRIP: the reload failed (exit {p.returncode}, "
                            f"{'loaded' if loaded else 'not loaded'}, {'saved' if os.path.isfile(state_b) else 'no state'})"}
        db, mb = digest_file(state_b, own)
        ok, why = hl.compare_digests(da, db, ma, mb)
        idx = Presses(self.routes[route_name]["input"]).index_at(save_at) if route_name in self.routes else None
        pdesc = Presses(self.routes[route_name]["input"]).describe(idx) if route_name in self.routes else ""
        out = {"kind": "clean" if ok else "roundtrip", "frame": save_at, "press": idx, "memory_a": da["memory"],
               "memory_b": db["memory"], "corrupt": note,
               "line": (f"ROUNDTRIP OK: savestate at frame {save_at} saved, loaded, saved again: {why}" if ok else
                        f"ROUNDTRIP: savestate at frame {save_at} saved, loaded, saved again: {why}; {pdesc}")}
        say(f"[{run}] {out['line']}")
        return out


def static_variant(route: dict, cut: int, button: str, step: int, count: int) -> dict:
    """An existing route cut at frame `cut`, then `count` presses of `button` every `step` frames on the screen it
    reached (the stuck-frame / soft-lock plant). Kept in memory and in the results, never in routes.json."""
    keep = [x for x in route["input"].split(",") if x.strip() and int(x.split(":")[0]) < cut]
    extra = [f"{cut + step * (i + 1)}:{button}" for i in range(count)]
    frames = cut + step * (count + 2)
    return dict(route, input=",".join(keep + extra), frames=frames, save_at=frames - 10,
                shots=[s for s in route["shots"] if int(s) < frames])


# ------------------------------------------------------------------ live self-test
def free_gb(path: str = ROOT) -> float:
    return shutil.disk_usage(path).free / (1 << 30)


def live_selftest(a) -> int:
    hl = headless()
    sys.path.insert(0, HERE)
    import parallel  # noqa: E402  (the %APPDATA% snapshot)
    if free_gb() < 8:
        print(f"watchdog live: STOP, only {free_gb():.1f} GB free on the build drive")
        return 3
    lane = Lane(a.session)
    lane.stage()
    before = parallel.snapshot(parallel.appdata_dirs())
    t_route = lane.route("title")
    plan = []  # (run, route name, route, kwargs, expected kind)
    for name in a.clean:
        plan.append((f"clean-{name}", name, lane.route(name), {"roundtrip": True}, "clean"))
    plan.append(("plant-kill", "title", t_route, {"plant": {"kind": "kill", "at": 1500}}, "crash"))
    plan.append(("plant-pause", "title", t_route, {"plant": {"kind": "pause", "at": 1500},
                                                    "limits": {"hang_s": a.pause_hang_s}}, "hang"))
    sv = lane.route(a.static_route)
    plan.append(("plant-static", a.static_route,
                 static_variant(sv, a.static_cut, a.static_button, a.static_step, a.static_count),
                 {"limits": {"soft_presses": 10 ** 6}}, "stuck"))  # each plant row tests its own watchdog
    plan.append(("plant-softlock", a.static_route,
                 static_variant(sv, a.static_cut, a.static_button, a.static_step, a.static_count + 8),
                 {"limits": {"stuck_frames": 10 ** 6}}, "softlock"))
    plan.append(("plant-corrupt", "title", t_route, {"roundtrip": True, "corrupt": True}, "roundtrip"))
    if a.only:
        plan = [p for p in plan if p[0] in a.only]
    lock = threading.Lock()

    def say(s):
        with lock:
            print(s, flush=True)

    def one(item):
        run, name, route, kw, want = item
        if free_gb() < 8:
            return {"run": run, "verdict": {"kind": "skipped", "line": "SKIPPED: under 8 GB free"}}, want
        try:
            return lane.watch(run, name, route, every=a.every, say=say, **kw), want
        except Exception as e:  # noqa: BLE001  (reported as a failed row, never a pass)
            return {"run": run, "verdict": {"kind": "error", "line": f"ERROR: {type(e).__name__}: {e}"}}, want

    jobs = max(1, min(a.jobs, int(os.environ.get("FEF_ROBOT_JOBS", a.jobs))))
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        results = list(ex.map(one, plan))
    after = parallel.snapshot(parallel.appdata_dirs())
    touched = parallel.snapshot_diff(before, after)
    rows, bad = [], 0
    for r, want in results:
        got = r["verdict"]["kind"]
        ok = got == want
        bad += not ok
        rows.append({"run": r["run"], "want": want, "got": got, "ok": ok, "line": r["verdict"]["line"],
                     "roundtrip": (r.get("roundtrip") or {}).get("line"), "seconds": r.get("seconds")})
        print(f"  {'PASS' if ok else 'FAIL'}  {r['run']:<22} want {want:<9} got {got:<9} {r['verdict']['line']}")
        if r.get("roundtrip") and r["roundtrip"]["line"] != r["verdict"]["line"]:
            print(f"        {r['roundtrip']['line']}")
    summary = {"rows": rows, "jobs": jobs, "appdata_touched": touched, "free_gb_after": round(free_gb(), 1),
               "plan": [{"run": p[0], "route": p[1], "input_tail": p[2]["input"].split(",")[-4:], "frames": p[2]["frames"]}
                        for p in plan]}
    with open(os.path.join(lane.dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    shutil.rmtree(os.path.join(lane.dir, "bin"), ignore_errors=True)
    print(f"watchdog live: {len(rows) - bad}/{len(rows)} as expected, jobs {jobs}, %APPDATA% "
          f"{'untouched' if not touched else 'TOUCHED: ' + ', '.join(touched[:3])}; {rel(lane.dir)}/summary.json")
    return 0 if bad == 0 and not touched else 1


# ------------------------------------------------------------------ self-test (no game)
def selftest() -> tuple[list[str], str]:
    fails, n = [], 0

    def check(cond, what):
        nonlocal n
        n += 1
        if not cond:
            fails.append(what)

    import numpy as np  # noqa: F401
    p = Presses("100:A,400:B,700:DOWN+A")
    check(p.index_at(50) == 0 and p.index_at(100) == 1 and p.index_at(699) == 2 and p.index_at(9999) == 3, "index_at")
    check(p.between(90, 120) == [1] and p.between(104, 110) == [1] and p.between(105, 399) == [], "between")
    check(p.describe(2) == "press 2 of 3 (frame 400 B)", "describe")
    base = bytes(4096)

    def guest(tick, state=0):
        b = bytearray(base)
        b[0:4] = struct.pack("<I", tick)  # a ticker (a frame counter)
        b[1000] = state % 256  # another 256-byte block than the ticker
        return bytes(b)

    # clean: picture and state change after each press
    pr = Presses(",".join(f"{f}:A" for f in range(300, 3000, 300)))
    w = Watch("t", pr, stuck_frames=600, soft_presses=4, soft_frames=600, guest_frames=600)
    for f in range(30, 3000, 30):
        k = pr.index_at(f)
        w.feed(f, f"pic{k}", guest(f, k))
    v = w.finish(0, "Completed", 3000, 3000, "")
    check(v["kind"] == "clean", f"clean run: {v['line']}")
    # crash: early exit
    w = Watch("t", pr)
    for f in range(30, 1200, 30):
        w.feed(f, f"pic{f}", guest(f, f))
    v = w.finish(1, None, None, 3000, "")
    check(v["kind"] == "crash" and v["press"] == pr.index_at(1170), f"crash: {v}")
    v = Watch("t", pr).finish(0, "Faulted", 900, 3000, "")
    check(v["kind"] == "crash", "crash: Faulted")
    # hang: no new frame (wall)
    w = Watch("t", pr, hang_s=10)
    w.feed(30, "a", guest(30), wall=1000.0)
    check(w.wall_check(1005.0) is None and w.wall_check(1011.0)["kind"] == "hang", "hang wall")
    # hang: guest still while frames run
    w = Watch("t", pr, guest_frames=300)
    for f in range(30, 900, 30):
        w.feed(f, f"p{f}", guest(0))
    check(w.verdict and w.verdict["kind"] == "hang" and "no guest progress" in w.verdict["line"], f"hang guest {w.verdict}")
    # stuck frame: picture still, presses in, ticker running
    w = Watch("t", pr, stuck_frames=600, stuck_presses=3, soft_presses=99)
    for f in range(30, 3000, 30):
        w.feed(f, "still", guest(f, pr.index_at(f)))
    check(w.verdict and w.verdict["kind"] == "stuck" and w.verdict["press"] == 1, f"stuck {w.verdict}")
    # stuck frame: a blinking cursor (two pictures in a loop) is still stuck
    w = Watch("t", pr, stuck_frames=600, stuck_presses=3, soft_presses=99)
    for f in range(30, 3000, 30):
        w.feed(f, "blink" + str((f // 30) % 2), guest(f, pr.index_at(f)))
    check(w.verdict and w.verdict["kind"] == "stuck", f"stuck blink {w.verdict}")
    # stuck frame allow-listed
    allow = {"static_ok": [{"route": "t", "from": 0, "to": 5000, "why": "test"}]}
    w = Watch("t", pr, allow=allow, stuck_frames=600, soft_presses=99)
    for f in range(30, 3000, 30):
        w.feed(f, "still", guest(f, pr.index_at(f)))
    check(w.finish(0, "Completed", 3000, 3000, "")["kind"] == "clean" and w.allowed_static, "stuck allow-list")
    allow = {"static_ok": [{"picture": "still", "why": "test"}]}
    w = Watch("t", pr, allow=allow, stuck_frames=600, soft_presses=99)
    for f in range(30, 3000, 30):
        w.feed(f, "still", guest(f, pr.index_at(f)))
    check(w.verdict is None, "stuck allow-list by picture")
    # soft-lock: picture animates, only the ticker moves, presses change nothing
    w = Watch("t", pr, stuck_frames=99999, soft_presses=4, soft_frames=600)
    for f in range(30, 3000, 30):
        w.feed(f, f"anim{f % 90}", guest(f, 0))
    check(w.verdict and w.verdict["kind"] == "softlock", f"softlock {w.verdict}")
    # no soft-lock while the state answers presses
    w = Watch("t", pr, stuck_frames=99999, soft_presses=4, soft_frames=600)
    for f in range(30, 3000, 30):
        w.feed(f, f"anim{f % 90}", guest(f, pr.index_at(f)))
    check(w.verdict is None, f"no softlock {w.verdict}")
    # a ticker that only changes while presses go in is not taken as a ticker
    w = Watch("t", pr, stuck_frames=99999, soft_presses=4, soft_frames=600)
    for f in range(30, 3000, 30):
        w.feed(f, "x" + str(f), guest(f, pr.index_at(f) % 2))
    check(w.verdict is None, f"toggle state {w.verdict}")
    # allow-list file rules
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        q = os.path.join(td, "w.json")
        with open(q, "w") as fh:
            json.dump({"static_ok": [{"route": "t", "from": 1, "to": 2}]}, fh)
        try:
            load_allow(q)
            check(False, "allow-list without why accepted")
        except Stop:
            check(True, "")
        check(load_allow(os.path.join(td, "none.json")) == {"static_ok": []}, "no allow-list file")
        # corrupt_state: still parses, memory differs in exactly one section
        hl = headless()
        st = hl.fake_state(b"meta", [bytes(0x200000), bytes(64), bytes(64), bytes(64)])
        a_p, b_p = os.path.join(td, "a.bin"), os.path.join(td, "b.bin")
        with open(a_p, "wb") as fh:
            fh.write(st)
        corrupt_state(a_p, b_p)
        da, ma = digest_file(a_p, [])
        db, mb = digest_file(b_p, [])
        ok, why = hl.compare_digests(da, db, ma, mb)
        check(not ok and "fcram" in why and "vram" not in why, f"corrupt_state: {why}")
        ok, why = hl.compare_digests(da, digest_file(a_p, [])[0], ma, ma)
        check(ok, "roundtrip same state")
    # static_variant keeps the route's presses before the cut
    r = {"input": "100:A,400:B,700:A", "frames": 1000, "save_at": 990, "shots": [500, 900]}
    v = static_variant(r, 500, "SELECT", 100, 5)
    check(v["input"] == "100:A,400:B,600:SELECT,700:SELECT,800:SELECT,900:SELECT,1000:SELECT"
          and v["frames"] == 1200 and v["save_at"] == 1190 and v["shots"] == [500, 900], f"static_variant {v}")
    check(load_allow() is not None, "config/harness/watchdog.json reads")
    return fails, f"watchdog self-test: {n - len(fails)}/{n} checks passed"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--route", required=True)
    r.add_argument("--session", default="run")
    r.add_argument("--every", type=int, default=30)
    r.add_argument("--roundtrip", action="store_true")
    r.add_argument("--hang-s", type=float, default=120)
    ls = sub.add_parser("live-selftest")
    ls.add_argument("--session", default="selftest")
    ls.add_argument("--jobs", type=int, default=2)
    ls.add_argument("--every", type=int, default=30)
    ls.add_argument("--clean", nargs="+", default=["title", "new-game", "bt-ch8-pair"])
    ls.add_argument("--pause-hang-s", type=float, default=15)
    ls.add_argument("--only", nargs="+", help="just these rows (clean-<route>, plant-kill, plant-pause, ...)")
    ls.add_argument("--static-route", default="new-game")
    ls.add_argument("--static-cut", type=int, default=1000)
    ls.add_argument("--static-button", default="SELECT")
    ls.add_argument("--static-step", type=int, default=120)
    ls.add_argument("--static-count", type=int, default=10)
    a = ap.parse_args(argv)
    if a.selftest:
        f, s = selftest()
        for x in f:
            print("  FAIL  " + x)
        print(s)
        return 1 if f else 0
    try:
        if a.cmd == "run":
            lane = Lane(a.session)
            lane.stage()
            res = lane.watch(a.route, a.route, lane.route(a.route), every=a.every, roundtrip=a.roundtrip,
                             limits={"hang_s": a.hang_s})
            shutil.rmtree(os.path.join(lane.dir, "bin"), ignore_errors=True)
            return 0 if res["verdict"]["kind"] == "clean" else 1
        if a.cmd == "live-selftest":
            return live_selftest(a)
    except Stop as e:
        print(f"watchdog: SETUP: {e}")
        return 3
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
