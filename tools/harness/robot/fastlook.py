"""The look-ahead driver on the server mode (docs/harness/SERVER.md; docs/collab/SPEED_AGREED.md items 2, 4, 5).
Default-off: no other robot tool calls it; probe.py, auto.py, act.py and the shell helpers are unchanged.

A chain here is a start save zip played from frame 0 (or from an existing robot chain's state, imported read-only),
a list of absolute-frame presses (inputs.txt, every press ever sent, nothing else) and the state at the chain's
frame. Each call boots boot-server.exe once (or talks to `serve`, which keeps one running), and:

- item 2: no savestate decode, no sha256, no contact sheet on a look-ahead; the screen markers are read from live
  memory page by page (no 56 MiB heap dump); a picture only with --shot;
- item 4: the look printed at the end of a call is kept (last.json); `look` on an unchanged chain prints it again
  without booting;
- item 5: `phase` runs one recorded press list per player phase: steps of presses, each checked against the screen
  it expects; the first unexpected screen stops the phase, the chain goes back to the start of that step (the
  state this call or `serve` started from, loaded again in the same server, then the recorded presses stepped
  again: no second boot, and no state save in the middle of a phase) and only the presses of the steps that passed
  are recorded. No mash: a press
  is sent only if the plan lists it, or (`"answer": true` in a wait step) when a talk / tutorial screen named in
  auto.py's ANSWER table is up, and then it is recorded like any other.

    python tools/harness/robot/fastlook.py new CHAIN --save bt-ch1-clear          # from frame 0 of a save
    python tools/harness/robot/fastlook.py new CHAIN --save S --import-chain c10   # from robot chain c10's state
    python tools/harness/robot/fastlook.py phase CHAIN plan.json [--shot] [--keep-failed | --whole]
    python tools/harness/robot/fastlook.py look CHAIN [--shot] | board CHAIN | export CHAIN
    python tools/harness/robot/fastlook.py verify CHAIN       # replay inputs.txt from frame 0 on 2 ORIGINAL boot.exe
    python tools/harness/robot/fastlook.py serve CHAIN [--clean]  # keep one server for this chain (other calls use it)
    python tools/harness/robot/fastlook.py stop CHAIN
    python tools/harness/robot/fastlook.py clean CHAIN        # state.bin again on the clean line (frame 0 + presses)
    python tools/harness/robot/fastlook.py --selftest         # fake server: phase stop / rollback / recording, ...

Round 10: `serve` keeps mid-chain slots in the server's memory (taken at the start of each phase call, at most
MAX_SLOTS, never written to disk): a stop goes back from the newest slot at or before the step's start instead of
replaying from the session's start, while the save folder is unchanged since the slot (else the full replay as
before). A slot save writes the GPU's pictures into memory like any save, so each slot is a break of the line
(chain.json "breaks", same game, `clean` rebuilds state.bin); `serve --no-slots` keeps the strict clean line.
The cursor read is stale at phase start (docs/ROBOT.md 3e): after an `until` step or a step marked "end_turn" the
look prints cursor None (cursor_raw keeps the read) until a step moves the cursor; `{"refresh_cursor": true}` (alone,
or on any step) presses RIGHT LEFT and checks the screen did not change. `verify`'s clean server pass gets a timeout
scaled by the frame count (clean_timeout). The look lists support pairs (markers "supports": points, the rank they
reach, the next threshold) by name.

Round 11 (docs/ROBOT.md 3j tool finding, bt-ch16): under `serve` the files and the server must agree. A tool that
puts chain.json / inputs.txt back by itself (act2.py's `undo` from hist/) used to leave the server at its later frame
with the undone presses; the next call went on from there and the clean replay diverged. Now each served call first
compares the files with what the server last wrote: a rollback of the server's own presses (inputs.txt a prefix,
the dropped presses at or after chain.json's frame, the kept ones before it) takes the server back to that frame too (printed as "note:");
any other outside change is refused, and `stop` then saves nothing. `phase --whole` (plan request "whole") makes a
stop take the whole call back inside fastlook (nothing of the call recorded), so a caller needs no file undo at all.

plan.json: a list of steps, in order. A step is one of
    {"press": "LEFT LEFT A W30 A", "gap": 22, "wait": 60, "expect": "CLASS" | ["CLASS", ...]}
        st.sh's form: from the chain's frame + 10, a press every `gap` frames ("W<n>" waits n frames), then `wait`
        frames; the screen is checked at the end
    {"abs": "5130:A,5180:A", "to": 5300, "expect": ...}       absolute frames (a recorded route's own presses)
    {"until": ["CLASS", ...], "max": 3000, "every": 30, "answer": false}
        no press: advance `every` frames at a time until one of the screens is current (enemy phase, events)
"expect" may be omitted (no check). A screen is markers.py's current main-sequence process class, or
"TalkKeyWait" when a talk window waits for a key (as auto.py and act.py name it).

Saves and the clean replay (docs/harness/SERVER.md 2 and 6): a state save, and a screenshot, write the host GPU's
pictures into guest memory (Zakuro's write-back; boot.exe's ZAKURO_SAVE_AT does the same), so a chain whose line was
saved and loaded again in the middle holds other bytes than the clean replay from frame 0 (same instructions, same
game). fastlook never saves in the middle of a call. Where the line is broken anyway (a one-shot call continuing
from the state.bin an earlier call saved, a `serve` started on a saved state.bin, a picture on a line that goes on)
chain.json's "breaks" lists it. `verify` therefore compares the two original boot.exe copies with a server pass on
the CLEAN line (frame 0 + inputs.txt), checks that the chain's own state has the same instruction count, and names
the breaks if state.bin's bytes differ; `clean` (or `serve --clean`) puts state.bin back on the clean line.

Folders: build/harness/robot/fast/<chain>/ (--dir to move it; below build/ only): chain.json, inputs.txt,
state.bin, last.json, server/ (the server's scratch). Budget: robot/budget.py's priority class; the server
process is below normal (or idle) and dies with this process. It does not take build/harness/robot/probe.lock:
it never runs boot.exe. Never written: build/harness/robot/states/ (an import only reads it), %APPDATA%,
%LOCALAPPDATA%, the saves in build/harness/saves/.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.append(os.path.join(ROOT, "tools", "harness"))
sys.path.append(HERE)
import server as srv  # noqa: E402
import headless as hl  # noqa: E402

FAST = os.path.join(ROOT, "build", "harness", "robot", "fast")
ROBOT_STATES = os.path.join(ROOT, "build", "harness", "robot", "states")  # read only (an import)
HUMAN = "map__SequenceHuman__anonymous_namespace__ProcSequence"
ANSWER = {"TalkKeyWait": "A", "TalkUtil__ProcBind": "A", "ProcTutorialViewer": "START", "ProcMovie": "START",
          "GameMessage": "A", "event__anonymous_namespace__ProcEvent": "A"}  # auto.py's screen -> button, as there


DIRS = {"LEFT", "RIGHT", "UP", "DOWN"}
REFRESH = "RIGHT LEFT"  # docs/ROBOT.md 3e: the cursor read is stale at phase start until the cursor moves
MAX_SLOTS = 6  # mid-chain slots kept in the server's memory under serve (oldest dropped)


def clean_timeout(frames: int) -> float:
    """Seconds for one clean-line server pass of `frames` frames: 120 s + 10 ms a frame (100 frames a second; round 9
    measured about 177 on the busy PC: 106,429 frames in the old flat 600 s), never below the server's 600 s."""
    return max(600.0, 120.0 + frames / 100.0)


def disk_digest(s) -> str | None:
    """A digest of the server's save folder (names, sizes, bytes), or None when the server has none: a mid-chain slot
    is only used while the game has not written its save since the slot (memory comes back, files would not)."""
    import hashlib
    top = getattr(s, "data_dir", None)
    if not top:
        return None
    user = os.path.join(top, "user")
    h = hashlib.sha256()
    for dp, dn, fn in os.walk(user):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            h.update(os.path.relpath(p, user).encode() + b"\0")
            try:
                with open(p, "rb") as fh:
                    h.update(fh.read())
            except OSError:
                h.update(b"?")
    return h.hexdigest()


def screen_of(m: dict | None) -> str | None:
    if not m:
        return None
    return "TalkKeyWait" if "TalkKeyWait" in (m.get("classes") or []) else m.get("current")


def rel_presses(start: int, spec: str, gap: int, wait: int) -> tuple[str, int]:
    """st.sh's relative form -> (absolute input list, end frame)."""
    f, out = start + 10, []
    for b in spec.split():
        if re.fullmatch(r"W\d+", b):
            f += int(b[1:])
            continue
        out.append(f"{f}:{b}")
        f += gap
    return ",".join(out), f + wait


class Chain:
    server_factory = srv.Server  # the self-test puts a fake here

    def __init__(self, name: str, top: str = FAST):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise SystemExit(f"chain {name}: letters, digits, _ . - only")
        self.name = name
        self.dir = os.path.abspath(os.path.join(top, name))
        if not hl.below(self.dir, os.path.join(ROOT, "build")):
            raise SystemExit(f"{self.dir}: not below build/")
        self.meta_path = os.path.join(self.dir, "chain.json")
        self.inputs_path = os.path.join(self.dir, "inputs.txt")
        self.state_path = os.path.join(self.dir, "state.bin")
        self.last_path = os.path.join(self.dir, "last.json")
        self.meta = json.load(open(self.meta_path, encoding="utf-8")) if os.path.isfile(self.meta_path) else None
        self.base_breaks: list[dict] = []  # breaks of the line up to the state this server started from
        self.sess_breaks: list[dict] = []  # breaks made since (pictures on a line that went on); back_to drops them
        self.use_slots = False  # serve only: mid-chain slots in the server's memory
        self.slots: list[dict] = []  # {"name", "frame", "disk", "fresh"} oldest first
        self.last_back = None  # ("slot" | "base", frame) of the last back_to
        self.synced = None  # serve: (inputs.txt text, chain.json frame) as this server last left them (mark/sync)

    # ------------------------------------------------------------ files (each written whole, then renamed)
    def _write(self, path: str, text: str) -> None:
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(path + ".tmp", path)

    def save_meta(self) -> None:
        self._write(self.meta_path, json.dumps(self.meta, indent=1))

    def breaks(self) -> list[dict]:
        out = []
        for b in self.base_breaks + self.sess_breaks:
            if b not in out:
                out.append(b)
        return out

    def note_shot(self, s) -> None:
        """A picture on a line that goes on: the write-back stays in later memory until back_to re-steps."""
        self.sess_breaks.append({"frame": s.frame, "why": "screenshot (GPU write-back), line went on"})

    def inputs(self) -> str:
        if not os.path.isfile(self.inputs_path):
            return ""
        lines = open(self.inputs_path, encoding="utf-8").read().splitlines()
        return ",".join(t.strip() for ln in lines for t in ln.split("#")[0].split(",") if t.strip())

    def _inputs_text(self) -> str:
        return open(self.inputs_path, encoding="utf-8").read() if os.path.isfile(self.inputs_path) else ""

    @staticmethod
    def _presses(text: str) -> list[str]:
        return [t.strip() for ln in text.splitlines() for t in ln.split("#")[0].split(",") if t.strip()]

    def mark(self) -> None:
        """serve: the files as this server leaves them (checked by sync before the next request)."""
        self.synced = (self._inputs_text(), self.meta["frame"])

    def sync(self, s) -> str | None:
        """serve, round 11 (docs/ROBOT.md 3j tool finding): the chain's files may have been put back by a tool
        outside the server (act2.py's `undo` copies chain.json / inputs.txt / state.bin back from hist/) while the
        server still holds the presses and the frame of the undone calls. The next call then went on from the
        server's frame with presses inputs.txt no longer has, and the clean replay diverged (bt-ch16).
        Here: files unchanged -> nothing. inputs.txt a prefix of the presses this server holds, every dropped press
        at or after chain.json's frame, and that frame not past the server's -> the server goes back to that frame
        on the files' presses (back_to: a slot or the base, no save). Anything else -> refused (SystemExit).
        Round 11 review: every press the files keep must also lie before chain.json's frame (a press at or after it
        would be played again by the next call although it is recorded as an earlier step: chain.json's frame put
        back with inputs.txt left alone is no rollback)."""
        if self.synced is None:
            self.mark()
            return None
        text = self._inputs_text()
        disk = json.load(open(self.meta_path, encoding="utf-8")) if os.path.isfile(self.meta_path) else None
        if disk is not None and (text, disk["frame"]) == self.synced:
            return None
        held, now = self._presses(self.synced[0]), self._presses(text)
        f = None if disk is None else int(disk["frame"])
        if (f is None or f > s.frame or held[:len(now)] != now
                or any(int(x.split(":")[0]) < f for x in held[len(now):])
                or any(int(x.split(":")[0]) >= f for x in now)):
            raise SystemExit(f"{self.name}: chain.json / inputs.txt changed outside the server and are not a rollback "
                             f"of its own presses (server at frame {s.frame} with {len(held)} presses; files: frame "
                             f"{f}, {len(now)} presses). Not continued: stop the server (it then saves nothing) and "
                             "serve again")
        fresh = disk.get("cursor_fresh", True)
        self.meta = disk
        self.back_to(s, f)
        self.meta["cursor_fresh"] = fresh
        self.meta["frame"], self.meta["cycles"] = s.frame, s.cycles
        self.meta["unsaved"] = True
        self.meta["breaks"] = self.breaks()
        self.save_meta()
        self.mark()
        return (f"files rolled back outside the server to frame {f} ({len(held) - len(now)} presses dropped): the "
                f"server went back too (from the {self.last_back[0]} at {self.last_back[1]})")

    def record(self, spec: str, note: str) -> None:
        if not spec:
            return
        old = open(self.inputs_path, encoding="utf-8").read() if os.path.isfile(self.inputs_path) else ""
        self._write(self.inputs_path, old + f"{spec}  # {note}\n")

    # ------------------------------------------------------------ the server
    def boot(self, clean: bool = False, name: str = "server"):
        """A server at the chain's frame. Default: state.bin loaded (fast; the line is broken there if state.bin was
        saved mid-chain, noted in "breaks"). clean=True: frame 0 of the save, then the recorded presses stepped up to
        the chain's frame: the clean replay's own line (costs the frames once, about 300 a second)."""
        if clean and self.meta.get("start") != "frame0":
            raise SystemExit(f"{self.name}: starts from an imported state; no clean line from frame 0")
        s = self.server_factory(name, save=self.meta["save"], root=self.dir, cheat=bool(self.meta.get("cheat")))
        s.inputs_set(self.inputs())
        self.sess_breaks = []
        if not clean and (self.meta["frame"] > 0 or os.path.isfile(self.state_path)):
            s.load_file(self.state_path)
            self.base = ("file", self.state_path)
            self.base_breaks = list(self.meta.get("breaks", []))
            if s.frame > 0:
                self.base_breaks.append({"frame": s.frame, "why": "state.bin saved by an earlier call, loaded"})
        else:  # frame 0 of the save: nothing drawn yet, so this slot's save writes nothing back
            s.save_slot("base0")
            self.base = ("slot", "base0")
            self.base_breaks = []
            if clean and self.meta["frame"] > 0:
                s.step_to(int(self.meta["frame"]), timeout=clean_timeout(int(self.meta["frame"])))
        if s.frame != self.meta["frame"]:
            raise SystemExit(f"{self.name}: state at frame {s.frame}, chain.json says {self.meta['frame']}")
        return s

    def back_to(self, s: srv.Server, frame: int) -> None:
        """The chain at `frame` again: the state this server started from (save folder re-laid, as at boot), then
        the recorded presses stepped up to frame. Loads only, no save: the line stays the clean replay's."""
        for sl in [x for x in self.slots if x["frame"] > frame]:  # slots past the target hold presses not kept
            self._drop_slot(s, sl)
        disk = disk_digest(s) if self.slots else None
        sl = self.slots[-1] if self.slots and self.slots[-1]["disk"] == disk else None
        if sl is not None:  # round 10: from the newest slot (server memory), the save folder as it was then
            s.load_slot(sl["name"])
            s.inputs_set(self.inputs())
            s.step_to(frame, timeout=clean_timeout(frame - sl["frame"]))
            # breaks up to the slot (its own write-back included) stay; pictures after it leave with the re-step
            self.sess_breaks = [b for b in self.sess_breaks if b["frame"] <= sl["frame"]]
            self.meta["cursor_fresh"] = sl["fresh"]
            self.last_back = ("slot", sl["frame"])
            return
        s.reset_disk()
        if self.base[0] == "file":
            s.load_file(self.base[1])
        else:
            s.load_slot(self.base[1])
        s.inputs_set(self.inputs())
        s.step_to(frame, timeout=clean_timeout(frame - s.frame))
        self.sess_breaks = []  # re-stepped from the base: pictures taken since are no longer in this line
        for sl in list(self.slots):  # their states were made on the old line (the files may differ too)
            self._drop_slot(s, sl)
        self.last_back = ("base", s.frame)

    def take_slot(self, s) -> None:
        """serve: a mid-chain slot at the server's frame, in its memory only (never a file). A save writes the GPU's
        pictures into memory, so the line is broken here (same game): noted in breaks; `clean` rebuilds state.bin."""
        if not self.use_slots or s.frame <= 0 or any(x["frame"] == s.frame for x in self.slots):
            return
        name = f"mid{s.frame}"
        s.save_slot(name)
        self.slots.append({"name": name, "frame": s.frame, "disk": disk_digest(s),
                           "fresh": self.meta.get("cursor_fresh", True)})
        self.sess_breaks.append({"frame": s.frame, "why": "mid-chain slot (server memory only; save write-back)"})
        while len(self.slots) > MAX_SLOTS:
            self._drop_slot(s, self.slots[0])

    def _drop_slot(self, s, sl: dict) -> None:
        self.slots.remove(sl)
        try:
            s.drop_slot(sl["name"])
        except (srv.ServerError, AttributeError):
            pass

    def persist(self, s) -> None:
        """state.bin at the frame where the call ends (the last thing a call does; the server is closed after it)."""
        s.save_file(self.state_path)
        self.meta["frame"] = s.frame
        self.meta["cycles"] = s.cycles
        self.meta["breaks"] = self.breaks()
        self.save_meta()

    def look(self, s, shot: bool = False) -> dict:
        m = s.markers()
        b = s.board()
        fresh = self.meta.get("cursor_fresh", True)
        out = {"frame": s.frame, "screen": screen_of(m), "classes": [c for c in m.get("classes", []) if c != "ProcInst"][:16],
               "cursor": b["cursor"] if fresh else None, "cursor_raw": b["cursor"], "cursor_fresh": fresh,
               "units": b["units"]}
        sup = (m.get("state") or {}).get("supports")
        if sup is not None:
            out["supports"] = sup
        if shot:
            out["shot"] = hl.rel(s.shot(os.path.join(self.dir, f"shot-{s.frame}.png")))
            self.note_shot(s)
        self._write(self.last_path, json.dumps(out, indent=1))
        return out

    # ------------------------------------------------------------ a phase
    def phase(self, s, plan: list[dict], keep_failed: bool = False, whole: bool = False, say=print) -> dict:
        """whole=True (round 11): a stop takes the whole call back (to the call's start frame, nothing recorded),
        not just the failed step: what act2.py's undo wanted, done inside the server so files and server agree."""
        done = []
        text0, start0, fresh00 = self._inputs_text(), s.frame, self.meta.get("cursor_fresh", True)
        for i, st in enumerate(plan):
            start = s.frame
            fresh0 = self.meta.get("cursor_fresh", True)
            sent = []
            only_refresh = st.get("refresh_cursor") and not any(k in st for k in ("until", "abs", "press"))
            if only_refresh:
                ok, why, seen = True, None, None
            elif "until" in st:
                want = st["until"] if isinstance(st["until"], list) else [st["until"]]
                every, limit = int(st.get("every", 30)), start + int(st.get("max", 3000))
                seen = screen_of(s.markers())
                while seen not in want and s.frame < limit:
                    press = ANSWER.get(seen) if st.get("answer") else None
                    if press:
                        p = f"{s.frame + 4}:{press}"
                        s.inputs_add(p)
                        sent.append(p)
                    s.step_to(min(s.frame + every, limit))
                    seen = screen_of(s.markers())
                ok = seen in want
                why = None if ok else f"no {want} within {st.get('max', 3000)} frames (screen {seen})"
            else:
                if "abs" in st:
                    spec, end = st["abs"], int(st["to"])
                else:
                    spec, end = rel_presses(start, st.get("press", ""), int(st.get("gap", 22)), int(st.get("wait", 60)))
                frames = [int(x.split(":")[0]) for x in spec.split(",") if x]
                if frames and (min(frames) < start or max(frames) >= end):
                    raise SystemExit(f"step {i}: presses must lie in [{start}, {end})")
                if spec:
                    s.inputs_add(spec)
                    sent = spec.split(",")
                s.step_to(end)
                want = st.get("expect")
                want = [want] if isinstance(want, str) else want
                seen = screen_of(s.markers()) if want else None
                ok = not want or seen in want
                why = None if ok else f"expected {want}, screen {seen}"
            if ok:
                if "until" in st or st.get("end_turn"):
                    self.meta["cursor_fresh"] = False  # a new phase: the cursor read is the old one
                if any(x.split(":")[1] in DIRS for x in sent if ":" in x):
                    self.meta["cursor_fresh"] = True
            if ok and st.get("refresh_cursor"):  # RIGHT LEFT, the screen must stay the one before
                before = screen_of(s.markers())
                spec, end = rel_presses(s.frame - 6, REFRESH, 16, 30)
                s.inputs_add(spec)
                sent += spec.split(",")
                s.step_to(end)
                seen = screen_of(s.markers())
                ok = seen == before
                why = None if ok else f"cursor refresh: screen {before} became {seen}"
                if ok:
                    self.meta["cursor_fresh"] = True
            if not ok:
                say(f"step {i}: STOP at frame {s.frame}: {why}")
                bad = {"step": i, "frame": s.frame, "why": why, "screen": seen}
                # a picture of the surprise by default only when the line goes back (the write-back leaves with it);
                # with --keep-failed the line goes on, so only if the step asks ("shot": true)
                if st.get("shot", not keep_failed):
                    bad["shot"] = hl.rel(s.shot(os.path.join(self.dir, f"stop-{s.frame}.png")))
                    self.note_shot(s)
                if keep_failed:
                    self.record(",".join(sent), f"step {i} (kept after a stop)")
                    if any(x.split(":")[1] in DIRS for x in sent if ":" in x):
                        self.meta["cursor_fresh"] = True
                elif whole:  # the whole call back: inputs.txt as it was, the server at the call's start
                    if self._inputs_text() != text0:
                        self._write(self.inputs_path, text0)
                    self.back_to(s, start0)
                    self.meta["cursor_fresh"] = fresh00
                    bad["undone_steps"] = [d["step"] for d in done]
                    done = []
                else:  # back to the start of the step; its presses are not recorded and leave the server's list
                    self.back_to(s, start)
                    self.meta["cursor_fresh"] = fresh0
                return {"done": done, "stopped": bad}
            self.record(",".join(sent), f"step {i} -> frame {s.frame} {seen or ''}".rstrip())
            done.append({"step": i, "frame": s.frame, "screen": seen, "presses": len(sent)})
        return {"done": done, "stopped": None}


# ------------------------------------------------------------ verify: the proof on the original boot.exe
def judge(originals: list[dict], deterministic: bool, clean: dict, chain: dict) -> dict:
    """verify's verdict. originals: the original boot.exe copies' {memory, instructions} (state at the chain's frame,
    instructions at its end); clean: the server on the clean line {memory, cycles (at the chain's frame),
    instructions_end}; chain: the chain's own state.bin {memory, cycles, breaks}. SAME needs the copies
    deterministic, each equal to the clean line, and the chain's own state at the same instruction count (the same
    game was played). state.bin's bytes may differ from the clean line only where the line was broken by a save or
    a picture (GPU write-back): reported in chain_state, not a failure."""
    problems = []
    same_clean = bool(originals) and all(o["memory"] == clean["memory"] and o["instructions"] == clean["instructions_end"]
                                         for o in originals)
    if not deterministic:
        problems.append("the original boot.exe copies differ from each other (or a copy failed)")
    if not same_clean:
        problems.append("the original boot.exe copies differ from the server's clean line (frame 0 + inputs.txt)")
    game = chain.get("cycles") is None or chain["cycles"] == clean["cycles"]
    if not game:
        problems.append(f"the chain's state has {chain['cycles']} instructions at its frame, the clean replay "
                        f"{clean['cycles']}: not the same game (the recorded presses do not give what was looked at)")
    where = ", ".join(f"{b['frame']} ({b['why']})" for b in chain.get("breaks") or []) or "none recorded"
    if chain.get("memory") is None:
        state = "no state.bin"
    elif chain["memory"] == clean["memory"]:
        state = "clean line: state.bin = the clean replay byte for byte"
    elif game:
        state = ("state.bin differs from the clean replay in GPU write-back bytes only (same instruction count, same "
                 f"game); line broken at: {where}. The replay is the proof; `fastlook.py clean` rebuilds state.bin")
    else:
        state = f"state.bin differs (breaks: {where})"
    ok = deterministic and same_clean and game
    return {"verdict": "SAME" if ok else "DIFFERENT", "chain_state": state, "problems": problems}


def verify(ch: Chain, copies: int = 2, say=print) -> dict:
    """inputs.txt replayed from frame 0 of the chain's save on `copies` copies of the ORIGINAL boot.exe (parallel.py's
    Session: its own copy of boot.exe, side by side, below normal), compared with each other (h4a's comparison) and
    with a server pass on the clean line (frame 0 + inputs.txt, no save before the chain's frame); the chain's own
    state.bin must have the same instruction count (judge())."""
    if ch.meta.get("start") != "frame0":
        raise SystemExit(f"{ch.name}: starts from an imported state; only a frame-0 chain replays alone")
    if client(ch) is not None:
        raise SystemExit(f"{ch.name} is being served: fastlook.py stop {ch.name} first")
    import parallel as par  # noqa: E402
    frame = int(ch.meta["frame"])
    inp = ch.inputs()
    route = {"frames": frame + 10, "input": inp or f"{frame + 5}:A", "save_at": frame, "shots": [frame + 1],
             "verified": False, "save": ch.meta["save"]}
    if not inp:
        raise SystemExit("no presses recorded")
    # the server on the clean line (a decode + sha256 only here, in the proof)
    with ch.boot(clean=True, name="verify-clean") as s:
        cyc = s.cycles
        d = s.state_digest()
        s.step_to(frame + 10, timeout=clean_timeout(10))
        clean = {"memory": d["memory"], "cycles": cyc, "instructions_end": s.cycles}
    chain = {"cycles": ch.meta.get("cycles"), "breaks": ch.meta.get("breaks", []), "memory": None}
    if os.path.isfile(ch.state_path):
        with open(ch.state_path, "rb") as fh:
            chain["memory"] = hl.state_digest(fh.read(), [ch.name])["memory"]
    limits = par.load_limits(cli_jobs=min(copies, 2))
    sess = par.Session(f"sp-fastlook-{ch.name}-{time.strftime('%H%M%S')}", None)
    sess.stage()
    rname = f"fastlook-{ch.name}"
    jobs = [sess.job(f"{sess.name}-{k + 1}", rname, route, "original", keep_meta=True, timeout=3600) for k in range(copies)]
    out: dict = {}

    def after(rows, sess=sess):
        done = [r for r in rows if r["ok"]]
        digests = [json.load(open(os.path.join(sess.dir, "results", f"{r['run']}.json"), encoding="utf-8"))["run_json"].get("state")
                   for r in done]
        v = par.determinism_verdict(done, digests, [sess.meta(r["run"]) for r in done])
        out["determinism"] = v
        out["original"] = [{"run": r["run"], "memory": r["memory"], "instructions": r["instructions"],
                            "boot_seconds": r["boot_seconds"]} for r in rows]
        return {"fastlook": out}, v["verdict"] == "DETERMINISTIC" and len(done) == len(rows)

    ns = argparse.Namespace(command="determinism", mem_per_run_gb=0.8, reserve_gb=2.0)
    summary, rc = par.execute(sess, jobs, limits, ns, after)
    out["clean_server"] = clean
    out["chain"] = chain
    out["session"] = sess.name
    out.update(judge(out.get("original", []), rc == 0, clean, chain))
    say(json.dumps(out, indent=1))
    return out


def rebuild(ch: Chain, say=print) -> dict:
    """state.bin again on the clean line: frame 0 of the save, inputs.txt stepped to the chain's frame, saved there
    (the save at the end is the one the replay's own save_at makes too)."""
    with ch.boot(clean=True) as s:
        ch.persist(s)
    say(f"{ch.name}: state.bin rebuilt on the clean line at frame {ch.meta['frame']} (breaks cleared)")
    return ch.meta


# ------------------------------------------------------------ serve: one server kept for a chain
def serve(ch: Chain, clean: bool = False, slots: bool = True) -> None:
    from multiprocessing.connection import Listener
    key = os.urandom(16)
    s = ch.boot(clean=clean)
    ch.use_slots = slots
    ch.mark()
    with Listener(("127.0.0.1", 0), authkey=key) as lst:
        ch._write(os.path.join(ch.dir, "serve.json"), json.dumps({"port": lst.address[1], "key": key.hex(), "pid": os.getpid()}))
        print(f"serving {ch.name} on port {lst.address[1]} (frame {s.frame})", flush=True)
        try:
            while True:
                with lst.accept() as conn:
                    req = conn.recv()
                    if req.get("op") == "stop":
                        conn.send(serve_stop(ch, s))
                        break
                    try:
                        out = run_op(ch, s, req, persist=False)
                        if ch.meta.get("breaks", []) != ch.breaks():
                            ch.meta["breaks"] = ch.breaks()
                            ch.save_meta()
                        conn.send({"ok": True, "out": out})
                    except (SystemExit, srv.ServerError) as e:
                        conn.send({"ok": False, "error": str(e)})
        finally:
            s.close()
            try:
                os.remove(os.path.join(ch.dir, "serve.json"))
            except OSError:
                pass


def serve_stop(ch: Chain, s) -> dict:
    """serve's `stop`: the files checked first (Chain.sync); refused -> nothing saved (state.bin, chain.json and
    inputs.txt stay as the outside tool left them), else state.bin at the server's frame."""
    try:
        note = ch.sync(s)
    except SystemExit as e:  # the files are someone else's now: leave them as they are
        return {"ok": False, "error": f"{e}; server stopped, nothing saved"}
    ch.persist(s)
    ch.meta.pop("unsaved", None)
    ch.save_meta()
    return {"ok": True, "frame": s.frame, **({"synced": note} if note else {})}


def client(ch: Chain):
    p = os.path.join(ch.dir, "serve.json")
    if not os.path.isfile(p):
        return None
    from multiprocessing.connection import Client
    info = json.load(open(p, encoding="utf-8"))
    try:
        return Client(("127.0.0.1", info["port"]), authkey=bytes.fromhex(info["key"]))
    except OSError:
        return None


def run_op(ch: Chain, s, req: dict, persist: bool = True) -> dict:
    if not persist:  # served: first make sure the server and the files agree (round 11, Chain.sync)
        note = ch.sync(s)
        try:
            out = _run_op(ch, s, req, persist)
        finally:
            ch.mark()
        if note and isinstance(out, dict):
            out["synced"] = note
        return out
    return _run_op(ch, s, req, persist)


def _run_op(ch: Chain, s, req: dict, persist: bool = True) -> dict:
    op = req["op"]
    if op == "look":
        return ch.look(s, shot=req.get("shot", False))
    if op == "shot":
        out = {"shot": hl.rel(s.shot(os.path.join(ch.dir, f"shot-{s.frame}.png")))}
        ch.note_shot(s)
        return out
    if op == "phase":
        ch.take_slot(s)  # serve only (use_slots): a stop in this call goes back from here
        ch.last_back = None
        r = ch.phase(s, req["plan"], keep_failed=req.get("keep_failed", False), whole=req.get("whole", False))
        if ch.last_back:
            r["back_from"] = {"kind": ch.last_back[0], "frame": ch.last_back[1]}
        r["look"] = ch.look(s, shot=req.get("shot", False))  # item 4: this print is the look
        if persist:  # one-shot: the state where the call ends; under serve only at stop (no save mid-line)
            ch.persist(s)
        else:
            ch.meta["frame"], ch.meta["cycles"] = s.frame, s.cycles
            ch.meta["unsaved"] = True
            ch.meta["breaks"] = ch.breaks()
            ch.save_meta()
        return r
    raise SystemExit(f"unknown op {op}")


def print_look(out: dict) -> None:
    cur = out["cursor"] if out.get("cursor_fresh", True) else (
        f"None (stale read {out.get('cursor_raw')}: move the cursor, e.g. a refresh_cursor step)")
    print(f"frame {out['frame']}  screen {out['screen']}  cursor {cur}")
    for u in out.get("units", []):
        print(f"   {'PEA'[u['force']]} ({u['x']},{u['y']}) hp {u['hp']} {u['unit']}")
    if out.get("supports"):
        import markers as mk  # noqa: E402
        parts = []
        for k, v in sorted(out["supports"].items(), key=lambda kv: [int(x) for x in kv[0].split("-")]):
            a, b = (int(x) for x in k.split("-"))
            parts.append(f"{mk.person_name(a)}-{mk.person_name(b)} {v['points']}"
                         f" ({v['ready']}{', next ' + str(v['next']) if v.get('next') is not None else ''})")
        print("   supports: " + "; ".join(parts))
    if out.get("shot"):
        print("shot:", out["shot"])


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    if argv[:1] == ["--selftest"]:
        return 1 if selftest() else 0
    ap.add_argument("cmd", choices=["new", "phase", "look", "board", "shot", "export", "verify", "serve", "stop", "clean"])
    ap.add_argument("chain")
    ap.add_argument("plan", nargs="?")
    ap.add_argument("--dir", default=FAST)
    ap.add_argument("--save", help="new: the start save zip (build/harness/saves/<name>)")
    ap.add_argument("--import-chain", help="new: start from build/harness/robot/states/<chain>.bin/.frame/.inputs")
    ap.add_argument("--cheat", action="store_true", help="new: a cheat-track chain (docs/CHEATS.md)")
    ap.add_argument("--shot", action="store_true")
    ap.add_argument("--keep-failed", action="store_true")
    ap.add_argument("--whole", action="store_true", help="phase: a stop takes the whole call back (nothing recorded), "
                    "not only the failed step")
    ap.add_argument("--copies", type=int, default=2)
    ap.add_argument("--clean", action="store_true", help="serve: start on the clean line (frame 0 + presses), "
                    "not on state.bin")
    ap.add_argument("--no-slots", action="store_true", help="serve: no mid-chain slots (a stop replays from the "
                    "session's start; the line stays unbroken)")
    a = ap.parse_args(argv)
    sys.path.append(HERE)
    import budget  # noqa: E402  (priority class of resources.json for this process; the server inherits it)
    budget.enter()
    ch = Chain(a.chain, a.dir)
    t0 = time.time()
    if a.cmd == "new":
        if not a.save:
            raise SystemExit("new: --save ZIP")
        if os.path.isdir(ch.dir):
            shutil.rmtree(ch.dir)
        os.makedirs(ch.dir)
        ch.meta = {"save": a.save, "start": "frame0", "frame": 0, "cheat": a.cheat}
        if a.import_chain:  # read only: the robot's states folder is never written
            src = os.path.join(ROBOT_STATES, a.import_chain)
            shutil.copy2(src + ".bin", ch.state_path)
            ch.meta.update(start=f"imported {a.import_chain}", frame=int(open(src + ".frame").read()))
            if os.path.isfile(src + ".inputs"):
                shutil.copy2(src + ".inputs", ch.inputs_path)
        ch.save_meta()
        print(f"chain {ch.name}: {ch.meta}")
        return 0
    if ch.meta is None:
        raise SystemExit(f"no chain {ch.name} in {a.dir} (fastlook.py new)")
    if a.cmd == "export":
        print(json.dumps({"save": ch.meta["save"], "frame": ch.meta["frame"], "input": ch.inputs(),
                          "breaks": ch.meta.get("breaks", [])}, indent=1))
        return 0
    if a.cmd in ("look", "board") and not a.shot and os.path.isfile(ch.last_path):
        last = json.load(open(ch.last_path, encoding="utf-8"))
        if last.get("frame") == ch.meta["frame"]:  # item 4: the state did not move since that look
            print_look(last)
            print(f"(kept look, no boot; {time.time() - t0:.2f} s)")
            return 0
    if a.cmd == "verify":
        r = verify(ch, a.copies)
        return 0 if r["verdict"] == "SAME" else 1
    if a.cmd == "serve":
        serve(ch, clean=a.clean, slots=not a.no_slots)
        return 0
    if a.cmd == "clean":
        if client(ch) is not None:
            raise SystemExit(f"{ch.name} is being served: fastlook.py stop {ch.name} first")
        rebuild(ch)
        print(f"({time.time() - t0:.2f} s)")
        return 0
    if a.keep_failed and a.whole:
        raise SystemExit("--keep-failed and --whole contradict each other")
    req = {"op": "look" if a.cmd == "board" else a.cmd, "shot": a.shot, "keep_failed": a.keep_failed, "whole": a.whole}
    if a.cmd == "phase":
        if not a.plan:
            raise SystemExit("phase CHAIN PLAN")
        req["plan"] = json.load(open(a.plan, encoding="utf-8")) if os.path.isfile(a.plan) else json.loads(a.plan)
    conn = client(ch)
    if a.cmd == "stop":
        if conn is None:
            print("not serving")
            return 0
        conn.send({"op": "stop"})
        print(conn.recv())
        return 0
    if conn is not None:  # a kept server: no boot at all
        conn.send(req)
        res = conn.recv()
        conn.close()
        if not res["ok"]:
            print("error:", res["error"])
            return 2
        out = res["out"]
        ch.meta = json.load(open(ch.meta_path, encoding="utf-8"))
    else:
        with ch.boot() as s:
            out = run_op(ch, s, req)
    if isinstance(out, dict) and out.get("synced"):
        print("note:", out["synced"])
    if a.cmd == "phase":
        for d in out["done"]:
            print(f"step {d['step']}: frame {d['frame']} {d['screen'] or ''} ({d['presses']} presses)")
        if out["stopped"]:
            print(f"STOPPED at step {out['stopped']['step']}: {out['stopped']['why']}  shot {out['stopped'].get('shot')}")
            if out["stopped"].get("undone_steps") is not None:
                print(f"(--whole: passed steps {out['stopped']['undone_steps']} undone too; nothing recorded)")
            if out.get("back_from"):
                print(f"(went back from the {out['back_from']['kind']} at frame {out['back_from']['frame']})")
        print_look(out["look"])
    elif a.cmd == "shot":
        print("shot:", out["shot"])
    else:
        print_look(out)
    print(f"({time.time() - t0:.2f} s{', kept server' if conn is not None else ''})")
    return 3 if a.cmd == "phase" and out.get("stopped") else 0


# ------------------------------------------------------------ self-test (a fake server in this process: no game)
class _FakeServer:
    """The Server calls fastlook makes, on a model: the screen is "S<n>" with n = presses before this frame ("WRONG"
    once a B was pressed; "TalkKeyWait" while talk is on and nothing was pressed); a save or a picture adds one
    write-back to the memory (dirt), a load brings back the saved frame and dirt; instructions = frame * 7."""
    made: list = []

    def __init__(self, name, save=None, root=None, cheat=False, talk=False):
        self.name, self.dir = name, os.path.join(root, name)
        os.makedirs(self.dir, exist_ok=True)
        self.frame, self.dirt, self.inp, self.slots, self.talk = 0, 0, [], {}, talk
        self.closed = False
        self.disk_resets = 0  # round 9: back_to must re-lay the save folder (planted bug: reset_disk() removed)
        self.timeouts = []  # round 10: the timeout of every step_to
        self.steps = []  # (from, to) of every step_to
        self.data_dir = os.path.join(self.dir, "data")
        os.makedirs(os.path.join(self.data_dir, "user"), exist_ok=True)
        _FakeServer.made.append(self)

    @property
    def cycles(self):
        return self.frame * 7

    def inputs_set(self, spec):
        self.inp = [x for x in (spec or "").split(",") if x]
        return len(self.inp)

    def inputs_add(self, spec):
        self.inp += [x for x in spec.split(",") if x]
        return len(self.inp)

    def step_to(self, f, timeout=None, **_kw):
        if f < self.frame:
            raise srv.ServerError(f"step to {f} < {self.frame}")
        self.timeouts.append(timeout)
        self.steps.append((self.frame, f))
        self.frame = f

    def _pressed(self):  # cursor moves (round 10) do not change the model's screen
        return [x.split(":")[1] for x in self.inp if int(x.split(":")[0]) < self.frame and x.split(":")[1] not in DIRS]

    def markers(self):
        p = self._pressed()
        if "B" in p:
            return {"current": "WRONG", "classes": ["WRONG"]}
        if self.talk and not p:
            return {"current": "Talk", "classes": ["Talk", "TalkKeyWait"]}
        return {"current": f"S{len(p)}", "classes": [f"S{len(p)}"]}

    def board(self):
        return {"frame": self.frame, "cursor": [1, 2], "units": [{"force": 0, "x": 1, "y": 2, "hp": 20, "unit": "a0"}]}

    def save_slot(self, n):
        self.dirt += self.frame > 0
        self.slots[n] = (self.frame, self.dirt)

    def load_slot(self, n):
        self.frame, self.dirt = self.slots[n]

    def drop_slot(self, n):
        self.slots.pop(n, None)

    def save_file(self, p):
        self.dirt += self.frame > 0
        with open(p + ".tmp", "w") as fh:
            json.dump({"frame": self.frame, "dirt": self.dirt}, fh)
        os.replace(p + ".tmp", p)

    def load_file(self, p):
        d = json.load(open(p))
        self.frame, self.dirt = d["frame"], d["dirt"]

    def shot(self, png=None, scale=1):
        self.dirt += 1
        open(png, "wb").close()
        return png

    def reset_disk(self):
        self.disk_resets += 1
        return []

    def memory(self):
        return f"{self.frame}:{','.join(self._pressed())}:{self.dirt}"

    def state_digest(self):
        self.dirt += self.frame > 0
        return {"memory": self.memory()}

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def selftest() -> list[str]:
    import io
    import contextlib
    import tempfile
    fails: list[str] = []
    n = 0

    def check(cond, what):
        nonlocal n
        n += 1
        print(f"  {'ok  ' if cond else 'FAIL'} {what}")
        if not cond:
            fails.append(what)

    os.makedirs(os.path.join(ROOT, "build", "speed", "server"), exist_ok=True)
    top = tempfile.mkdtemp(prefix="fastlook-selftest-", dir=os.path.join(ROOT, "build", "speed", "server"))
    real_factory = Chain.server_factory
    Chain.server_factory = _FakeServer
    quiet = lambda *_a, **_k: None  # noqa: E731
    try:
        # rel_presses: st.sh's relative form
        check(rel_presses(100, "LEFT W30 A", 22, 60) == ("110:LEFT,162:A", 244), "rel_presses: gap, W<n>, wait")
        check(rel_presses(0, "", 22, 60) == ("", 70), "rel_presses: no press")

        def new(name, **kw):
            c = Chain(name, top)
            os.makedirs(c.dir)
            c.meta = {"save": "x", "start": "frame0", "frame": 0, "cheat": False, **kw}
            c.save_meta()
            return Chain(name, top)

        # one-shot call 1: two steps pass, recorded, state saved at the end, no break (the line was never re-loaded)
        ch = new("a")
        with ch.boot() as s:
            r = run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "expect": "S1"}, {"press": "A", "gap": 22, "wait": 60,
                                                                                      "expect": ["S2"]}]})
        check(r["stopped"] is None and [d["screen"] for d in r["done"]] == ["S1", "S2"], "phase: two steps pass")
        check(ch.inputs() == "10:A,102:A" and ch.meta["frame"] == 184, f"phase: presses recorded ({ch.inputs()}), frame 184")
        check(ch.meta.get("breaks") == [], "one-shot call 1: no break")
        last = json.load(open(ch.last_path))
        check(last["frame"] == 184 and last["screen"] == "S2" and last["units"], "item 4: the phase's look is kept")

        # one-shot call 2: a wrong expectation stops, goes back, records nothing
        ch = Chain("a", top)
        before = open(ch.inputs_path).read()
        with ch.boot() as s:
            r = run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "expect": "S3"}, {"press": "B", "expect": "S4"}]})
            check(r["stopped"] and r["stopped"]["step"] == 1 and r["stopped"]["screen"] == "WRONG", "phase: stops on the surprise")
            check(s.frame == r["done"][0]["frame"] == 276, f"phase stop: server back at the step's start (frame {s.frame})")
            check(s.inp == ch.inputs().split(","), "phase stop: the server's press list = the recorded presses")
            check(s.markers()["current"] == "S3", "phase stop: the screen of the step's start again")
            check(s.disk_resets == 1, f"phase stop: back_to re-laid the save folder once (reset_disk calls {s.disk_resets})")
            check(r["stopped"].get("shot") and ch.breaks() == ch.base_breaks, "stop picture taken; dropped by going back")
        check(open(ch.inputs_path).read() == before + "194:A  # step 0 -> frame 276 S3\n",
              "phase stop: only the passed step recorded")

        # round 9: a press on the step's end frame is refused (planted bug: '>= end' changed to '> end')
        ch = new("e")
        with ch.boot() as s:
            for spec, to, want in (("50:A", 50, False), ("49:A", 50, True), ("0:A", 50, True)):
                try:
                    ch.phase(s, [{"abs": spec, "to": to}], say=quiet)
                    got = True
                except SystemExit:
                    got = False
                check(got == want, f"press range: '{spec}' with to {to} {'accepted' if want else 'refused'}")
                if got:
                    break

        # --keep-failed: the failed step's presses recorded, no picture unless the step asks
        ch = new("k")
        with ch.boot() as s:
            r = ch.phase(s, [{"press": "B", "expect": "S1"}], keep_failed=True, say=quiet)
            check(r["stopped"] and "shot" not in r["stopped"] and s.dirt == 0, "keep-failed: no picture by default")
            check(ch.inputs() == "10:B" and s.frame == 92, "keep-failed: the failed presses kept, line goes on")

        # until + answer: a talk screen answered by its table button, recorded
        ch = new("t")
        _FakeServer.made.clear()
        orig = Chain.server_factory
        Chain.server_factory = type("_Talk", (_FakeServer,), {"__init__": lambda self, *a, **k: _FakeServer.__init__(self, *a, talk=True, **k)})
        with ch.boot() as s:
            r = ch.phase(s, [{"until": ["S1"], "max": 300, "every": 30, "answer": True}], say=quiet)
        Chain.server_factory = orig
        check(r["stopped"] is None and ch.inputs() == "4:A", f"until + answer: TalkKeyWait answered with A ({ch.inputs()})")
        ch2 = new("t2")
        with ch2.boot() as s:
            r = ch2.phase(s, [{"until": ["S9"], "max": 90, "every": 30}], say=quiet)
            check(r["stopped"] and s.frame == 0 and ch2.inputs() == "", "until: no screen in max -> stop, back")

        # breaks: a one-shot call continuing from a saved state.bin; a picture under serve
        ch = Chain("a", top)
        with ch.boot() as s:
            run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "expect": "S4"}]})
        check([b["frame"] for b in ch.meta["breaks"]] == [184, 276] and ch.meta["frame"] == 368,
              f"one-shot calls 2, 3: the reloads at 184 and 276 are breaks ({ch.meta['breaks']})")
        ch = new("v")
        with ch.boot() as s:  # serve: persist=False, nothing saved mid-line
            run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "expect": "S1"}]}, persist=False)
            check(ch.meta["breaks"] == [] and ch.meta.get("unsaved"), "serve: a phase leaves no break")
            run_op(ch, s, {"op": "look", "shot": True}, persist=False)
            check(len(ch.breaks()) == 1 and "screenshot" in ch.breaks()[0]["why"], "serve: a picture on the line is a break")
            ch.back_to(s, s.frame)
            check(ch.breaks() == [] and s.dirt == 0, "back_to: the picture's break leaves with the re-stepped line")

        # item 4 through main(): an unchanged chain's look needs no server at all
        ch = new("m")
        with ch.boot() as s:
            run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "expect": "S1"}]})

        def no_boot(*_a, **_k):
            raise AssertionError("booted")
        Chain.server_factory = no_boot
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["look", "m", "--dir", top])
        check(rc == 0 and "kept look, no boot" in buf.getvalue(), "item 4: look on an unchanged chain does not boot")
        Chain.server_factory = _FakeServer

        # clean: the line rebuilt from frame 0 (no break, memory = a clean pass)
        ch = Chain("a", top)
        rebuild(ch, say=quiet)
        with Chain("a", top).boot(clean=True, name="ref") as s:
            ref = (s.frame, s.cycles)
        st = json.load(open(ch.state_path))
        check(ch.meta["breaks"] == [] and st["dirt"] == 1 and ref == (ch.meta["frame"], ch.meta["cycles"]),
              "clean: state.bin rebuilt on the clean line, breaks cleared")
        imp = new("imp", start="imported c10")
        try:
            imp.boot(clean=True)
            check(False, "clean: an imported chain is refused")
        except SystemExit:
            check(True, "clean: an imported chain is refused")

        # round 10, item 1: the clean pass's timeout scales with the frames (planted bug: no timeout= -> the
        # server's flat 600 s, round 9's 153k-frame chain stopped at 106,429)
        big = new("big", frame=153000)
        with big.boot(clean=True, name="big-clean") as s:
            check(s.timeouts and s.timeouts[-1] is not None and s.timeouts[-1] >= 153000 / 177,
                  f"clean pass: timeout scaled by frames ({s.timeouts[-1:]} s for 153,000 frames)")
        check(clean_timeout(1000) == 600.0 and clean_timeout(300000) > 3000, "clean_timeout: floor 600 s, grows")

        # round 10, item 2: serve's mid-chain slots: a stop goes back from the phase call's slot, not frame 0
        ch = new("sl")
        with ch.boot() as s:
            ch.use_slots = True
            run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "expect": "S1"}]}, persist=False)
            f1 = s.frame
            r = run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "expect": "S2"}, {"press": "B", "expect": "S3"}]},
                       persist=False)
            check(r["stopped"] and r.get("back_from") == {"kind": "slot", "frame": f1},
                  f"slots: the stop went back from the slot at {f1} ({r.get('back_from')})")
            check(s.steps[-1][0] == f1 and s.disk_resets == 0, f"slots: re-stepped from {f1}, not frame 0 ({s.steps[-1]})")
            check(s.inp == ch.inputs().split(",") and s.markers()["current"] == "S2",
                  "slots: press list and screen after going back = the recorded line")
            check(not any(f.endswith(".bin") and "mid" in f for f in os.listdir(ch.dir)),
                  "slots: nothing written to disk for a slot")
            check(any("slot" in b["why"] and b["frame"] == f1 for b in ch.breaks()), "slots: each slot named as a break")
            with open(os.path.join(s.data_dir, "user", "save.dat"), "w") as fh:  # the game wrote its save
                fh.write("x")
            ch.last_back = None
            ch.back_to(s, s.frame)
            check(ch.last_back and ch.last_back[0] == "base" and s.disk_resets == 1 and ch.slots == [],
                  "slots: a save written since the slot -> full replay from the base, folder re-laid, slots dropped")
            for k in range(MAX_SLOTS + 2):
                run_op(ch, s, {"op": "phase", "plan": [{"press": "A"}]}, persist=False)
            check(len(ch.slots) <= MAX_SLOTS and len(s.slots) <= MAX_SLOTS + 1, f"slots: at most {MAX_SLOTS} kept")
        ch = new("ns")
        with ch.boot() as s:  # no slots (one-shot, or serve --no-slots): the old behaviour, no break
            run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "expect": "S1"}]}, persist=False)
            r = run_op(ch, s, {"op": "phase", "plan": [{"press": "B", "expect": "S2"}]}, persist=False)
            check(r.get("back_from", {}).get("kind") == "base" and ch.breaks() == [], "no slots: base replay, no break")

        # round 10, item 3: the cursor read after an end turn is not trusted until the cursor moves
        ch = new("cu")
        with ch.boot() as s:
            r = run_op(ch, s, {"op": "phase", "plan": [{"until": ["S0"], "max": 30}]}, persist=False)
            check(r["look"]["cursor"] is None and r["look"]["cursor_raw"] == [1, 2] and not r["look"]["cursor_fresh"],
                  "cursor: stale after an until (enemy phase) step -> look prints None")
            r = run_op(ch, s, {"op": "phase", "plan": [{"refresh_cursor": True}]}, persist=False)
            check(r["stopped"] is None and r["look"]["cursor"] == [1, 2] and ":RIGHT," in ch.inputs()
                  and ch.inputs().endswith(":LEFT"),
                  f"cursor: refresh_cursor presses RIGHT LEFT, recorded, cursor fresh ({ch.inputs()})")
            run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "end_turn": True}]}, persist=False)
            check(json.load(open(ch.last_path))["cursor"] is None, "cursor: stale after an end_turn step (kept look too)")
            r = run_op(ch, s, {"op": "phase", "plan": [{"press": "UP", "expect": "S0"}]}, persist=False)
            check(r["stopped"] and r["look"]["cursor"] is None, "cursor: a stop that goes back keeps it stale")
            r = run_op(ch, s, {"op": "phase", "plan": [{"press": "DOWN"}]}, persist=False)
            check(r["look"]["cursor"] == [1, 2], "cursor: a direction press makes it fresh")

        # a refresh that changes the screen stops; going back restores the stale state (planted: no restore)
        class _Rt(_FakeServer):
            def markers(self):
                if any(x.endswith(":RIGHT") and int(x.split(":")[0]) < self.frame for x in self.inp):
                    return {"current": "MOVED", "classes": ["MOVED"]}
                return _FakeServer.markers(self)
        Chain.server_factory = _Rt
        ch = new("cr")
        with ch.boot() as s:
            run_op(ch, s, {"op": "phase", "plan": [{"until": ["S0"], "max": 30}]}, persist=False)
            r = run_op(ch, s, {"op": "phase", "plan": [{"press": "UP", "refresh_cursor": True}]}, persist=False)
            check(r["stopped"] and "cursor refresh" in r["stopped"]["why"] and r["look"]["cursor"] is None
                  and ch.inputs() == "", f"cursor: a refresh that changes the screen stops, stays stale ({r['stopped']})")
        Chain.server_factory = _FakeServer

        # round 10, item 5: supports in the look, printed by name
        class _Sup(_FakeServer):
            def markers(self):
                m = _FakeServer.markers(self)
                m["state"] = {"supports": {"7-10": {"points": 25, "ready": "A", "next": 35},
                                           "4-13": {"points": 3, "ready": "-", "next": 5}}}
                return m
        Chain.server_factory = _Sup
        ch = new("sp")
        with ch.boot() as s:
            out = ch.look(s)
        Chain.server_factory = _FakeServer
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_look(out)
        check(out.get("supports", {}).get("7-10", {}).get("ready") == "A" and "Kaze-Hana 25 (A, next 35)" in buf.getvalue()
              and "Felicia-Saizo 3 (-, next 5)" in buf.getvalue(), f"supports: in the look, by name ({buf.getvalue()!r})")

        # round 11, item 1 (docs/ROBOT.md 3j): the bt-ch16 serve divergence, reproduced. Under serve a phase whose
        # step 0 passes and step 1 stops keeps step 0 (recorded, and in the server); act2.py then put the files back
        # from its hist/ copy (its `undo`), the server did not follow, and the next call went on from the server's
        # frame with presses inputs.txt no longer had. Planted bug: sync() returns at once -> the checks below fail.
        files = ("chain.json", "inputs.txt", "state.bin", "last.json")
        ch = new("rb")
        with ch.boot() as s:
            ch.use_slots = True
            ch.mark()
            run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "expect": "S1"}]}, persist=False)
            ch.persist(s)  # a state.bin on disk at this frame, as the hist copy would have one
            ch.mark()
            hist = {f: open(os.path.join(ch.dir, f), "rb").read() for f in files if os.path.isfile(os.path.join(ch.dir, f))}
            f0 = s.frame
            r = run_op(ch, s, {"op": "phase", "plan": [{"press": "RIGHT UP A", "expect": "S2"},
                                                       {"press": "B", "expect": "S3"}]}, persist=False)
            check(r["stopped"] and r["stopped"]["step"] == 1 and len(ch.inputs().split(",")) == 4,
                  "rollback repro: step 0 kept (recorded), step 1 stopped")
            for f, b in hist.items():  # act2.py undo: the files back from hist/, the server untouched
                with open(os.path.join(ch.dir, f), "wb") as fh:
                    fh.write(b)
            ch.meta = json.load(open(ch.meta_path, encoding="utf-8"))  # main() re-reads chain.json the same way
            r = run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "expect": "S2"}]}, persist=False)
            check(r.get("synced") and "rolled back outside" in r["synced"],
                  f"rollback repro: the outside undo was seen ({r.get('synced')})")
            check(r["stopped"] is None and s.inp == ch.inputs().split(",") and ch.inputs().startswith("10:A,")
                  and ch.inputs().split(",")[1] == f"{f0 + 10}:A",
                  f"rollback repro: server presses = inputs.txt, the new call starts at the files' frame {f0} "
                  f"({ch.inputs()})")
            check(s.markers()["current"] == "S2" and s.frame == ch.meta["frame"],
                  "rollback repro: server screen and frame = what the recorded line gives")
            # files changed outside in a way that is no rollback of the server's presses: refused, nothing run
            with open(ch.inputs_path, "a", encoding="utf-8") as fh:
                fh.write("99999:A  # written by someone else\n")
            fr = s.frame
            try:
                run_op(ch, s, {"op": "phase", "plan": [{"press": "A"}]}, persist=False)
                check(False, "foreign edit: refused")
            except SystemExit as e:
                check("not a rollback" in str(e) and s.frame == fr, "foreign edit of inputs.txt under serve: refused")

        # round 11, item 1: phase --whole: a stop takes the whole call back inside the server, files and server agree
        # (planted bug: the whole branch removed -> step 0 stays recorded)
        for served in (False, True):
            ch = new(f"wh{int(served)}")
            with ch.boot() as s:
                ch.use_slots = served
                run_op(ch, s, {"op": "phase", "plan": [{"press": "A", "expect": "S1"}]}, persist=not served)
                text0, f0 = open(ch.inputs_path, encoding="utf-8").read(), s.frame
                r = run_op(ch, s, {"op": "phase", "whole": True, "plan": [{"press": "LEFT A", "expect": "S2"},
                                                                          {"press": "B", "expect": "S3"}]},
                           persist=not served)
                check(r["stopped"] and r["stopped"].get("undone_steps") == [0] and r["done"] == []
                      and open(ch.inputs_path, encoding="utf-8").read() == text0,
                      f"--whole ({'serve' if served else 'one-shot'}): stop -> nothing of the call recorded")
                check(s.frame == f0 == ch.meta["frame"] and s.inp == ch.inputs().split(",")
                      and s.markers()["current"] == "S1",
                      f"--whole ({'serve' if served else 'one-shot'}): server back at the call's start {f0}")

        # round 11 review: each refusal of Chain.sync on its own, a real rollback accepted, and a stop after a refusal
        # saves nothing. Planted bugs (each caught here): the 'kept press at or after the frame' test removed (the
        # reviewer's case: chain.json's frame put back, inputs.txt left alone), the 'dropped press before the frame'
        # test removed, the 'frame past the server's' test removed, serve_stop saving after a refused sync.
        def served3(name):
            c = new(name)
            sv = c.boot()
            c.use_slots = True
            c.mark()
            for _ in range(3):
                run_op(c, sv, {"op": "phase", "plan": [{"press": "A"}]}, persist=False)
            return c, sv

        def set_frame(c, fr):
            d = json.load(open(c.meta_path, encoding="utf-8"))
            d["frame"] = fr
            with open(c.meta_path, "w", encoding="utf-8") as fh:
                json.dump(d, fh)

        def keep_lines(c, k):
            lines = open(c.inputs_path, encoding="utf-8").read().splitlines(keepends=True)
            with open(c.inputs_path, "w", encoding="utf-8") as fh:
                fh.write("".join(lines[:k]))

        def refused(c, sv, what):
            fr, inp = sv.frame, list(sv.inp)
            try:
                run_op(c, sv, {"op": "phase", "plan": [{"press": "A"}]}, persist=False)
                check(False, f"sync refuses: {what} (accepted, server at {sv.frame})")
            except SystemExit as e:
                check("not a rollback" in str(e) and sv.frame == fr and sv.inp == inp,
                      f"sync refuses: {what} (server untouched at {fr})")

        cases = (("chain.json's frame put back to 20, inputs.txt unchanged (presses 102, 194 after it)",
                  lambda c: set_frame(c, 20)),
                 ("inputs.txt cut to its first press, chain.json's frame left at the server's",
                  lambda c: keep_lines(c, 1)),
                 ("chain.json's frame past the server's, inputs.txt unchanged", lambda c: set_frame(c, 400)))
        for k, (what, edit) in enumerate(cases):
            c, sv = served3(f"rf{k}")
            with sv:
                check(sv.frame == 276 and c.inputs() == "10:A,102:A,194:A", f"refusal case {k}: three served phases")
                edit(c)
                refused(c, sv, what)
                if k == 0:  # stop after the refusal: nothing saved, the files as the outside tool left them
                    before = {f: open(os.path.join(c.dir, f), "rb").read() for f in ("chain.json", "inputs.txt")}
                    out = serve_stop(c, sv)
                    after = {f: open(os.path.join(c.dir, f), "rb").read() for f in ("chain.json", "inputs.txt")}
                    check(not out["ok"] and "nothing saved" in out["error"] and before == after
                          and not os.path.isfile(c.state_path),
                          "serve stop after a refused sync: no state.bin, chain.json / inputs.txt untouched")
        c, sv = served3("rf-ok")  # a real rollback (one press kept, the frame where it ended) is followed, and stop saves
        with sv:
            keep_lines(c, 1)
            set_frame(c, 92)
            out = serve_stop(c, sv)
            check(out["ok"] and out.get("synced") and sv.frame == 92 and sv.inp == ["10:A"]
                  and json.load(open(c.state_path))["frame"] == 92,
                  f"sync follows a real rollback to 92, stop saves there ({out})")

        # round 11 review: --whole puts the cursor's freshness back as it was at the call's start (planted bug: not put
        # back -> a direction press of an undone step leaves a stale cursor marked fresh). One-shot shows it; under
        # serve the call's slot restores it as well.
        for served in (False, True):
            ch = new(f"wc{int(served)}")
            with ch.boot() as s:
                ch.use_slots = served
                run_op(ch, s, {"op": "phase", "plan": [{"until": ["S0"], "max": 30}]}, persist=not served)
                r = run_op(ch, s, {"op": "phase", "whole": True, "plan": [{"press": "DOWN", "expect": "S0"},
                                                                          {"press": "B", "expect": "S1"}]},
                           persist=not served)
                check(r["stopped"] and r["stopped"].get("undone_steps") == [0] and r["look"]["cursor"] is None
                      and not ch.meta.get("cursor_fresh", True),
                      f"--whole ({'serve' if served else 'one-shot'}): the cursor stays stale after the undone DOWN")

        # judge: verify's verdict
        cl = {"memory": "M", "cycles": 70, "instructions_end": 140}
        og = [{"memory": "M", "instructions": 140}] * 2
        j = judge(og, True, cl, {"memory": "M", "cycles": 70, "breaks": []})
        check(j["verdict"] == "SAME" and j["chain_state"].startswith("clean line"), "judge: clean chain SAME")
        j = judge(og, True, cl, {"memory": "D", "cycles": 70, "breaks": [{"frame": 30, "why": "x"}]})
        check(j["verdict"] == "SAME" and "write-back" in j["chain_state"] and "30 (x)" in j["chain_state"],
              "judge: one-shot chain (write-back bytes, same instructions) SAME, the break named")
        j = judge(og, True, cl, {"memory": "D", "cycles": 77, "breaks": []})
        check(j["verdict"] == "DIFFERENT", "judge: other instruction count -> DIFFERENT")
        j = judge([og[0], {"memory": "N", "instructions": 140}], False, cl, {"memory": "M", "cycles": 70})
        check(j["verdict"] == "DIFFERENT", "judge: copies differ -> DIFFERENT")
        j = judge([{"memory": "D", "instructions": 140}] * 2, True, cl, {"memory": "M", "cycles": 70})
        check(j["verdict"] == "DIFFERENT", "judge: copies equal but not the clean line -> DIFFERENT")
        j = judge([], False, cl, {"memory": "M", "cycles": 70})
        check(j["verdict"] == "DIFFERENT", "judge: no copy finished -> DIFFERENT")
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        fails.append(f"crashed: {e!r}")
    finally:
        Chain.server_factory = real_factory
        shutil.rmtree(top, ignore_errors=True)
    print(f"fastlook selftest: {n - len([f for f in fails if not f.startswith('crashed')])}/{n} ok"
          + (f", {len(fails)} failed" if fails else ""))
    return fails


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
