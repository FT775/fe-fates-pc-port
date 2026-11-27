# The server mode of the windowless boot (owner OK "E", 2026-11-13)

**In plain words.** Today every look-ahead step starts a fresh boot.exe, loads a 2 GB ROM and a 120 MB library,
plays 22 to 80 frames, saves, quits, and then Python decodes and hashes the savestate and draws a contact sheet.
That is about 2.4 to 3.8 s a step for about 0.3 s of play. The server mode keeps one boot running: the ROM and the
library load once, and the robot sends it commands on a pipe ("step to frame F", "save a state in memory", "read
these bytes"). A step then costs what the emulation costs. The proof does not change: a finished chain is replayed
from frame 0 on two copies of the **original** boot.exe, and both must match each other and the server.
Tags: **[high]** measured or checked by a script here, **[med]** strong indirect evidence.

Sources: docs/collab/SPEED_AGREED.md (item E, items 2, 4, 5), SPEED_2026-11-13.md, SPEED_GROK.md.

## 1. What was built [high]

| Piece | Where | Notes |
|---|---|---|
| Server source (Rust, MIT as Zakuro) | `tools/harness/patches/zakuro-server/` (Cargo.toml, src/main.rs) | boot.rs's settings and per-frame loop, kept running; tracked |
| Build | `python tools/harness/build.py --server [--jobs N]` | copies the crate to `engine/zakuro-server/` (beside the pin, never inside it), lock file = engine/zakuro's (every shared crate at the same version), `cargo build --release --offline`, below-normal priority, into **`engine/target/zakuro-server/release/boot-server.exe`**; record in `server_build.json` there |
| Client | `tools/harness/server.py` | starts the server with headless.py's settings, timeouts, markers and board from live memory, the proofs |
| Look-ahead driver | `tools/harness/robot/fastlook.py` | items 2, 4, 5 on the server; default-off |

The Zakuro tree (`engine/zakuro`) is not edited (`engine.py status`: pin + 5 patches, OK) and
`engine/target/zakuro-test/release/examples/boot.exe` was never rebuilt, replaced or held open by a server run
(sha256 `4d6f0e97...` before and after). The server links zakuro-core by path with boot.exe's features (zakuro-fs
"testing" included) and engine/zakuro's `[profile.release]`. First build 101 s (-j 8), later builds 34-42 s.

### The protocol

One command per line on stdin; each reply line starts with `@@zs ` (any other stdout line is not a reply). Logs go
to stderr (the client writes them to `server.log`).

```
ping                                     -> @@zs ok frame F cycles C
input set|add SPEC | input clear         SPEC as ZAKURO_INPUT ("300:A,420:DOWN+A,500:@160x180"); absolute frames,
                                         each held 6 frames; the list survives a load
step N | step to F [timeout=MS] [dump_at=F,..] [shots=F,..]
                                         -> @@zs ok frame F cycles C ms T | @@zs err timeout ... | @@zs err outcome ...
save slot NAME | save file PATH          (a file is written whole, then renamed)
load slot NAME | load file PATH
peek 0xADDR,LEN[;...]                    -> @@zs bin N, then N raw bytes
set dump_ranges ...|dump_dir P|shot_dir P|timeout MS ;  dump ; shot ; slots ; drop slot NAME ; quit
audio start | audio save PATH | audio stop   (round 61) the sound the console played, as a 16-bit stereo WAV
```

Timeouts without polling: the server stops a step itself past its timeout; the client waits for each reply with a
blocking queue read with a deadline and kills the server's process tree (job object) if none comes.

## 2. Determinism against the original boot.exe [high]

References: `parallel.py runs --route bt-ch8 --route cq-ch6 --route rv-ch6` on the original boot.exe (session
`sp-server-ref`; the hashes are the ones in ROBOT.md / ROUTES_SPLIT.md). Proof commands:
`server.py --prove NAME --route R --expect <summary.json>` (pass 1: the whole route in one step; pass 2, same process:
the frame-0 state loaded again, save folder re-laid, then chunks of 80 frames with markers + board reads) and
`server.py --roundtrip NAME --route R --cuts F,F` (below).

| Route | Original boot.exe | Server, one step | Server, chunks of 80 | Notes |
|---|---|---|---|---|
| title | `c3cbbe48...`, 13,443,408,000 | same | same (38 chunks) | |
| bt-ch8 | `bee8415f...`, 353,561,630,400 | same | same (987 chunks, 9 marker + board reads) | |
| cq-ch6 | `73534534...`, 169,342,129,440 | same | same (473 chunks, 9 slot and 1 file save/load round trips, 4 reads) | |
| rv-ch6 | `6f54e4cd...`, 124,306,712,640 | same | same (347 chunks, no saves) | with saves: see below |
| rv-ch6, round trips at 8000 and 16000 | original boot.exe chain (save at 8000, load, save at 16000, load, save at 27730): `2239c643...`, 124,306,712,640 | server, slot round trip at 8000, file round trip at 16000: **`2239c643...`, 124,306,712,640** | | `--roundtrip` |

**A state save changes later guest memory (not the game).** Zakuro's `save_state` first writes what the host GPU
drew down into guest memory (`gpu.write_back_all`), and that marks those pictures clean. A run that saved at frame X
can therefore hold other bytes in FCRAM at a later frame than a run that did not save there, with the **same
instruction count** (rv-ch6: saves every 4,000 frames gave `2239c643...`; save-only and save+load gave the same hash,
so the load is exact and the save is the cause; bt-ch8 with 22 saves and 9 screenshots: `a557f5f4...`, same
instructions). This is boot.exe's own behaviour (ZAKURO_SAVE_AT), not the server's: the original boot.exe making the
same cuts gives the server's hash byte for byte (last table row). It also means today's look-ahead chains (one save
and one load per step) end at other memory bytes than their clean replay: the old-tool run of section 4 ended at
`4580d610...`, the clean replay at `8750aeb8...`. A screenshot reads the screen through the same write-back
(`sync_gpu`), so pictures are taken only when asked. The server therefore never saves on its own, and fastlook never
saves in the middle of a call. How fastlook's chains and `verify` deal with the rest is in section 4, "Breaks of the
line".

## 3. Step cost [high]

`build/speed/server/measure.py`: one state (bt-ch2 frame 5100, player phase), load + step 80 frames + save, 8 times
each, on this PC with the round-8 robots running, same minutes for both:

| Path | Median | Spread |
|---|---|---|
| Today's tools (fresh boot.exe: auto.segment's path with markers, contact sheet, decode + sha256, one Python process per step) | **2.40 s** | 2.34-2.60 s |
| Server, slot (memory) | **0.39 s** | 0.36-0.41 s |
| Server, file | 0.41 s | 0.38-0.43 s |
| Server, slot + markers + board read | 0.40 s | 0.37-0.52 s |

The brief's 3.84 s was profiled on a quieter machine with a heavier post-pass; here the same path measured 2.40 s.
About 0.3 s of the server's 0.39 s is the 80 frames themselves. Server boot: 0.5-2.2 s, once. A marker read from live
memory touches 30-33 pages of 64 KiB (about 8 ms) instead of a 56 MiB dump.

## 4. The look-ahead driver: fastlook.py [high]

Items of SPEED_AGREED.md: **2** (no decode, no sha256, no contact sheet on a look-ahead; markers read lazily from live
memory; a picture only with `--shot`, or of the surprise at a stop that goes back), **4** (the look printed at the end of a call is kept in
`last.json`; `look` on an unchanged chain prints it again without booting: 0.15 s), **5** (one recorded press list
per phase; each step names the screen it expects; the first unexpected screen stops the phase, the chain goes back
to the start of that step and only passed steps are recorded; no mash: a press is sent only if the plan lists it, or
in a wait step with `"answer": true` when a talk/tutorial screen of auto.py's table is up, and then it is recorded).

**Real sequence, measured.** Birthright chapter 2 from the clear save `bt-ch1-clear`, frame 0 to 11,070: the opening
(title, load, events) and four player phases with their enemy phases, ending in Corrin's Attack-Stance battle, as five
`phase` calls (plans: bt-ch2's recorded presses, 28 checked steps; the screens expected were read once with the server
beforehand). Back to back, same minutes:

| Way | Wall time |
|---|---|
| Today's tools: one fresh boot.exe per checked step (28), auto.segment's path, no extra look boot | **111.9 s, 115.9 s** |
| fastlook, `serve` (one server for the session; 5 phase calls + kept look + stop) | **47.3 s, 48.0 s** (31 s in a quieter run) |
| fastlook, one-shot (a server per call) | 52.1 s, 53.6 s (27.8 s in a quieter run, chain `sp-demo-oneshot2`) |

What is left is mostly the 11,070 frames themselves. A planted wrong expectation (`ChapterFileMenu` where the player
phase came back) stopped at step 0, the chain went back to frame 11,070, inputs.txt unchanged (md5 before = after),
a picture of the surprise written; going back cost 35 s, because under `serve` it replays from the session's start
(a load and re-stepping, never a state save mid-line).

**Proof on the original boot.exe.** `fastlook.py verify sp-demo`: the chain's inputs.txt (77 presses, byte for byte
bt-ch2's own presses before frame 11,070) replayed from frame 0 of `bt-ch1-clear` on two copies of the original
boot.exe (parallel.py's Session, side by side, below normal): **DETERMINISTIC**, memory `8750aeb8...`, instructions
49,650,986,880, both equal to the server's state at that frame. %APPDATA% unchanged.

**Breaks of the line, and what `verify` compares [high].** Because a save writes the GPU's pictures into guest
memory (section 2), a chain whose state was saved and then loaded again in the middle ends with other memory bytes
than its clean replay. The game does not change: the instruction count is the same. fastlook never saves in the
middle of a call, but some chains are broken anyway: a one-shot call goes on from the state.bin that the previous
call saved, a `serve` started on a saved state.bin does the same, and so does a picture (`--shot`, or a stop picture
under `--keep-failed` with `"shot": true`) on a line that goes on. Each such point is written to chain.json's
`"breaks"` (frame + why). A stop that goes back re-steps from the base and removes the breaks made since.

`verify` therefore compares three things:
1. the two original boot.exe copies with each other (h4a);
2. both copies with a server pass on the **clean** line: frame 0 of the save + inputs.txt, nothing saved before the
   chain's frame (memory hash and instruction count);
3. the chain's own state.bin with that clean pass: the **instruction count must be equal** (the presses give what was
   looked at). Its memory bytes may differ only by write-back. That is reported in `chain_state` with the breaks,
   and it is not a failure.

SAME needs all three; the replay on the original boot.exe stays the proof. `fastlook.py clean CHAIN` (or `serve
--clean`) rebuilds state.bin on the clean line: frame 0 plus the presses, about 300 frames a second (84 s for
11,070 frames on the busy machine). After that the state equals the replay byte for byte and the breaks are cleared.

Measured on the reviewer's case, chain `sp-demo-oneshot2` built with five **one-shot** calls (same presses as
`sp-demo`). chain.json recorded breaks at 5100, 6450, 8010 and 10110. state.bin memory was `15a9f576...` (the value
the reviewer measured), and its instruction count was 49,606,175,520, equal to the clean line. `verify`: the copies
are DETERMINISTIC, both at `8750aeb8...` and 49,650,986,880, equal to the clean server pass, so the verdict is
**SAME**. chain_state names the four breaks (248.7 s). After `clean`, state.bin = `8750aeb8...` and breaks = [].
Under `serve` (chain `sp-demo-serve`) there is no break, and state.bin equals the replay with no rebuild.

`--shot` under `serve`, or a kept failed step's picture, adds a break. It does not change the verdict (rule 3 above).
It does mean state.bin is no longer the replay's bytes until `clean`. Self-test: `fastlook.py --selftest` (29 checks
on a fake server: phase pass and record, stop and go back, the server's press list after a stop, `--keep-failed`
without a picture, until/answer, breaks from reloads and from pictures, back_to dropping them, the kept look without
a boot, `clean`, and judge's verdicts). It caught every planted fault tried: no back_to on a stop, no break for a
picture, a picture by default under --keep-failed, no break for a reload, and breaks not dropped on going back.

## 5. How a robot agent switches to it (round 9)

Nothing changes unless an agent chooses it; probe.py, auto.py, act.py, split.py and the shell helpers are unchanged.

```bash
python tools/harness/build.py --server                       # once (done 2026-11-13)
python tools/harness/robot/fastlook.py new c11 --save bt-ch10-clear          # a chain from frame 0 of a save
python tools/harness/robot/fastlook.py serve c11 &           # keep one server (recommended; or skip: one-shot calls)
python tools/harness/robot/fastlook.py phase c11 plan.json   # one call per player phase, stops on a surprise
python tools/harness/robot/fastlook.py look c11 [--shot]     # free if the chain did not move
python tools/harness/robot/fastlook.py stop c11              # saves the state; then:
python tools/harness/robot/fastlook.py clean c11             # optional: state.bin back on the clean line (section 4)
python tools/harness/robot/fastlook.py export c11            # the absolute input list for routes.json
python tools/harness/robot/fastlook.py verify c11            # the replay proof on 2 original boot.exe copies
```

A plan step is `{"press": "LEFT LEFT A", "gap": 22, "wait": 60, "expect": "map__anonymous_namespace__UnitCommand"}`
(st.sh's form), `{"abs": "5130:A,5180:A", "to": 5300, "expect": ...}`, or `{"until": [CLASS], "max": 3000, "every":
30}` (enemy phase). A screen is markers.py's current class, or `TalkKeyWait`. An existing robot chain can be imported
read-only (`new X --save S --import-chain c10`); it then cannot be verified alone (no frame-0 start).

Rules kept: chains live in `build/harness/robot/fast/<chain>/` (game memory, build/ only); the server's APPDATA,
LOCALAPPDATA and save folder are below the chain's folder; boot-server.exe and the library are used from copies;
the priority class is resources.json's (below normal or idle); fastlook never takes `probe.lock` (it never runs
boot.exe), so a served session counts as one more run beside a parallel.py session: keep such a session one job
under FEF_ROBOT_JOBS. A cheat save never starts a real-play chain (`--cheat` only for cheat-track chains). The
route that is committed is still replayed from frame 0 by `parallel.py determinism` on the original boot.exe; a
server run is never a determinism copy.

## 6. Limits and open points

- The save folder: under `serve` the game's own save files change as they do in the replay. One-shot calls lay
  the start zip again at each boot (as probe.py does), so a chain that reads back a save it wrote can differ between
  the two. In that case use `serve` (or `clean` and then `serve --clean`) for such stretches.
- One-shot chains and pictures on a line that goes on break the line (section 4). `verify` still gives SAME,
  because it judges the clean line and requires an equal instruction count. state.bin's bytes equal the replay
  only after `clean`.
- Going back after a stop under `serve` replays from the session's start (35 s at 11,000 frames); a mid-line state
  slot would be faster but changes later memory (section 2).
- Capture mode is not offered (look-aheads are original mode). Rooms, replay files and ZAKURO_PRESENT are refused.
- `build.py --selftest` currently stops in staging on another area's untracked `src/readable/sheet/` files (no
  functions.csv rows yet); it is not about --server. headless 64/64, markers 31/31, test_parallel 41 OK, server
  client self-test 15/15, fastlook self-test 29/29.

## Round 9 fixes (2026-11-14)

- **Run `fastlook.py clean CHAIN` before reusing state.bin as a save.** A chain's state.bin carries write-back
  bytes from its breaks (one-shot calls, pictures) until `clean` rebuilds it on the clean line; a save packed from
  an unclean state.bin is not the replay's bytes.
- fastlook self-test now 32 checks. New: `back_to` must call `reset_disk()` once on a phase stop (planted bug:
  the call removed -> caught), and a press on the step's end frame is refused (planted bug: `>= end` changed to
  `> end` -> caught).

## Round 10 tool fixes (2026-11-14)

Self-tests: fastlook 49/49 (was 32), markers 44/44, server client 15/15. Each fix has a planted-bug check; all
planted bugs listed below were caught. No game was played for these fixes; the tests use the fake server.

- **verify's clean pass timeout scales with the chain.** `clean_timeout(frames)` = 120 s + 10 ms per frame (100
  frames a second), never below 600 s. Round 9 measured about 177 frames a second on the busy PC. It is used for
  the clean-line step in `boot(clean=True)` (verify, `clean`, `serve --clean`) and for re-stepping in `back_to`.
  A 153,000-frame chain now gets 1,650 s; round 9 stopped at frame 106,429 under the flat 600 s. Planted bug: the
  `timeout=` dropped, caught.
- **Mid-chain slots under `serve`.** At the start of each `phase` call the server saves a slot `mid<frame>` in its
  own memory. It is never written to disk, and at most 6 are kept (the oldest is dropped). A stop goes back from
  the newest slot at or before the step's start, so it no longer replays from the session's start. The phase
  output says which way it went back (`back_from`: slot or base). A slot is used only while the game's save
  folder is unchanged since the slot was taken (sha256 of `data/user`). Otherwise it is the full replay from the
  base as before: folder re-laid, all slots dropped. Honest cost: a slot save writes the GPU's pictures into guest
  memory like any save (section 2). So each slot is listed in chain.json `"breaks"` (same game, same instruction
  count; `verify` still judges the clean line). Run `fastlook.py clean CHAIN` before packing state.bin.
  `serve --no-slots` keeps the strict unbroken line. One-shot calls never take slots. Planted bugs caught: slots
  never used, and a slot used after the save folder changed.
- **The cursor read is never stale at phase start.** After an `until` step (enemy phase) or a step marked
  `"end_turn": true`, the look gives `"cursor": null`, keeps the read in `cursor_raw`, and sets
  `"cursor_fresh": false`. print_look says "stale read ...". The cursor is trusted again after any step that
  presses LEFT/RIGHT/UP/DOWN, or after `{"refresh_cursor": true}`. That step can stand alone or ride on another
  step. It presses RIGHT LEFT (recorded like any press, 16 frames apart, then 30 frames) and stops if the screen
  changed. A stop that goes back restores the freshness the step started with. Planted bugs caught: no stale mark
  after until, the raw cursor shown when stale, the screen check of the refresh skipped, and freshness not restored
  on a stop.
- **Support points in the look.** markers.game_state now also gives `"supports"`:
  `{"<id>-<id>": {"points", "ready", "next"}}`, smaller Person+0x24 id first. `ready` is the highest of C/B/A/S
  whose threshold the points reach (points ready, not the conversation seen). `next` is the points needed for the
  next rank. The look prints the pairs by name, for example `Kaze-Hana 25 (A, next 35); Felicia-Saizo 3 (-, next
  5)` (ids 7-10 and 4-13; names from docs/ROBOT.md's list, others "id N"). A checkpoint can name one pair:
  `"supports.7-10.ready": "A"`. The older `support_pairs`, `support_c` and `support_points_max` are unchanged.
  Planted bugs caught: `>` for `>=`, the wrong threshold bytes, and the pair key not ordered. Not yet checked
  against a live game frame in this round.

## Round 61: the audio command (2026-11-21)
`audio start` drops what was played before and records the console's sound from the next frame (zakuro_core's
`System::take_audio()`, at `AUDIO_SAMPLE_RATE`, about 32728 samples a second). `audio save PATH` writes what was
recorded since start as a 16-bit PCM stereo WAV (whole, then renamed) and keeps recording; `audio stop` ends it. Not
recording, the server never takes the samples, so a run that does not use the command is the same as before. Used by
the music proof by sound (build/r61/hooks/audio/: a61.py records 900 frames on the map, `tools/harness/audioproof.py`
fingerprints): OFF vs ON a different song on all four paths (similarity 0.43 to 0.50), ON vs ON again identical.

