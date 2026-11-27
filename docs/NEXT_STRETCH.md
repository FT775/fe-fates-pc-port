# The next stretch: after round 81 (round 78, 2026-11-25)

This page takes over from build/roadmap/NEXT_STRETCH_2026-11-24.md for the time **after round 81**. That old
page still records what you picked on 2026-11-24 (F-057). Written in round 78, a desk round: nothing was built,
started, downloaded or deleted. Grok's answer is in docs/collab/NEXT_STRETCH_R78_GROK.md, word for word.

## In plain words

- **Already picked, and coming next** (your picks of 2026-11-24, F-057, on your standing OK, F-059 (3)):
  - **Round 80:** a faster enemy phase (Normal / 2x / 4x, Start skips the rest) and "True hit" (the battle
    forecast shows the real chance next to the game's number). Engine build.
  - **Round 81:** your game settings kept for every New Game. Engine build. It writes into a new part of
    the game, so it needs a second yes from you at that round (F-057).
  - **Then the full every-path check**, before you play (F-051).
  - **Round 82 ran it (2026-11-26, F-068, docs/tests/CHECK_R82.md and CHECK_R82_NEW.md):** 0 table FAIL on all 4 paths; three FAILs wait for your yes (Seal + Classic gives the plain game, use Casual or Phoenix there; one rare Seal seed is refused; four robot routes lack checkpoints).
- **Nothing below is picked.** It is a ranked list. You pick. If you say nothing, the defaults in "Your calls"
  apply, and no engine round after 81 starts without your yes at that round.
- **The one thing still missing is you playing one seed.** Grok says nothing matters more, and I agree.
- **Disk space is the real limit now.** There is about 43 GB free (43.2 GB as Windows counts it, df at 17:31
  today), and we stop at 30 GB free. Rounds 80 and 81 and the full check after them need about 43 GB
  (estimate from counted rounds). So a cleanup yes from you is needed first (see "Your calls", calls 1a
  and 1b).
  **Done:** you said "Yes, all of wave 2" on 2026-11-25; 38.6 GB was deleted (OK A dumps included) and D: went
  from 44 to 83 GB free (df). After round 80, D: has about 80 GB free (df, 2026-11-25 evening).
  The biggest part of that cleanup is the "OK A dumps": 26 GB of raw test recordings from rounds 40 and 41.
  Their results are already saved in the docs. If we ever redo that test, it makes new ones. Deleting them
  loses nothing you use.
- Every hour is marked **counted** (measured in a round, with where) or **estimate** (never measured).

## What changed since 2026-11-24

- **Round 72-73:** the full check passed (164 cells, that is 164 checks; 0 FAIL). Your play evening was
  ready, and you said "keep building" (round 73b). So no seed has been played yet.
- **Round 74:** the full swap was built (a swapped person comes with their own face, name and battle look),
  plus preset buttons and a short share code. Engine build, installed (game exe c49a0ab1).
- **Round 75 and 76:** the full swap passed the four hard chapters by robot. "How they look" is now offered
  on your page for Birthright, Conquest and Revelation. "Keep the face" stays the default.
- **Seal of Flames:** the full swap stays grey there. The name plate above a portrait keeps the old Seal
  name (a FAIL, F-062 (5)). Since round 77 it is refused everywhere, not only on the page (F-063).
- **Round 75b:** the "seed doctor" became **guarantees inside the randomizer** (F-061). Each needed role
  (healer, door opener, flier, dragon vein user) joins in time, always on. The easy / fair / harsh label was
  left for later.
- **Round 77:** the "Getting ready" launcher, and release r77 made on this PC. Full tests passed. It is
  **not pushed**: every push and the public snapshot wait for you.
- **Not settled:** the 3dsrecomp licence. Claude drafted the note in this round
  (docs/collab/LICENCE_REQUEST_3DSRECOMP.md). Only you send it.

## Numbers every engine round shares

- **Fixed engine-round steps:** planned at 3 h 15 (docs/ROUND71_PLAN.md, sitting 2: backups, build, one
  repair build, boot-server and cargo tests, two checks, install, report). **Counted** in real rounds:
  - round 71: build 10 min, check and install 10 min (REPORT_2027-01-16);
  - round 74: build 6 min, repair build and re-proof about 14 min (06:31-06:45), checks and install about
    12 min (06:46-06:58) (REPORT_2027-01-20).
  - Whole engine rounds: round 71 planned 8 h 45, took about 2 h 30; round 74 planned 8 h 30, took about
    2 h 07 (both counted, same reports). The plans stay as caps. The hours below stay estimates.
- **The full every-path check:** round 76 planned 7 h (docs/ROADMAP.md row 76); counted about 3 h 10 of
  wall clock, its check track 2 h 42 and integrate 27 min (REPORT_2027-01-23). Round 72: planned 8 h 35
  (ROADMAP row 72; the round's cap was 7 h, REPORT_2027-01-17), counted about 5 h 50 (same report).
- **Tests, counted in release r77** (build/r77/release/run.log): unit tests FULL 4.1 min (planned 3.2);
  check_all --slow 77.1 min (planned 75.6); smoke 98 s; package 30 s; the whole release 83.4 min.
- **Disk now: 43.2 GB free on D:** (counted, df at 17:31 today: 44,222 MB; GB here is the Windows count,
  1 GB = 1,024 MB, as in build/r78/disk/DISK_BEFORE_R80.md). The stop rule: no engine round if D: would fall
  under 30 GB free.
- **Disk per round.** The old estimate was 8-10 GB per engine round (build/roadmap/ROADMAP_PLAN_2026-11-24.md).
  The **counted** round folders are bigger (du, today; build/r78/disk/new_mb.txt, and build/backup in
  DISK_BEFORE_R80.md section 2):
  - engine rounds: round 71 used 11.0 GB, round 74 used 13.7 GB (counted folders), plus about 0.7 GB each of
    growth in engine/ (estimate split of a counted 1.3 GB), so about 11.7 and 14.3 GB;
  - full checks: round 72 used 6.9 GB, round 76 used 14.5 GB (F-062: D: went from 59 to 44 GB free);
  - backups: build/backup is 2.9 GB in all (2,965 MB).
  - This page uses **14 GB per engine round and 15 GB per full check** (the counted highs, rounded).
- **Cleanup waiting for your yes** (build/CLEANUP_PLAN_2026-11-24.md; wave 2 re-measured today in
  build/r78/disk/wave2_mb.txt, same rows, same sizes): wave 2 is 38.6 GB, but only 12.4 GB without the old
  OK A memory dumps (12,746 MB; the cleanup plan rounds the same size to 12.5); wave 3a is 7.6 GB; wave 3b is
  1.8 GB (both plan numbers, not re-measured today). C: has about 113 GB free (df, today).
- **What the OK A dumps are:** 26.1 GB of raw memory recordings from the round 40/41 OK A test runs. The
  summed-up results stay in git and the docs. OK A is still not finished; if it is ever run again, it makes
  fresh dumps. The cleanup plan makes them a separate call for you, so calls 1a and 1b below split them out.

## The ranked list (after round 81)

Grok's order holds. Where I differ, it says so and why. All hours are **estimates** unless marked.

### 1. The easy / fair / harsh label (Grok's #1)

- **What you see:** one word on the seed's spoiler, in the launcher's summary and on the page: easy, fair
  or harsh. It says how hard the enemies will be. The guarantees only make sure the right roles join in time.
- **Hours:** about 4 h (estimate; round 78's question to Grok, item G).
- **Engine build:** no. The page's words live in the Python side (F-051 (3)). If it needs a new spot on the
  page, that spot rides the next engine round.
- **Risks:** a wrong label misleads. Nobody has played a seed, so there is no real "how hard was it" yet.
- **Where I differ from Grok:** I agree it goes first. But I would build it from the **settings you picked**
  (enemy boosts, enemy skills, boss strength, growths, Nuzlocke) plus seed facts the tool already counts
  (when each role joins). Not from a guess at the seed's luck. Its words get checked after your play evening.
- **Depends on:** round 82's full check (the robot's numbers for every path).

### 2. The Seal name-plate fix, so the full swap can be offered on Seal (Grok's #2)

- **What you see:** on Seal of Flames, "How they look" stops being grey. With the full swap on, the name
  plate above a portrait shows the new person's name, as it already does on Fates.
- **Hours:** about 6-8 h (estimate; round 78's question, item H), plus about 1 h of desk trace first.
- **Engine build:** yes (your OK at its round), only after a cleanup.
- **Risks:** the cause is a guess. F-062 (5): the plate name likely comes straight from the scene's own
  script (a script command argument), which our name-swap patch (patch 0035, the "name trap") passes on
  unchanged. Not proven. That is why a 1 h trace comes first. Separately, the Seal guarantees were never seen
  in a real Seal story game (no Seal story save exists). Only if a Seal story save exists by then could that
  round look at it too; no hours are counted for it here.
- **Where I differ from Grok:** I agree it is a bug, not a new toy. But I would **pair it with Rewind** in
  one engine round (see the stretch table). That saves one engine round of disk (about 14 GB counted) and one
  block of fixed steps.
- **Depends on:** cleanup (wave 2 at least, more for later rounds); your play evening if paired with Rewind.

### 3. The seed kit for the official Zakuro (Grok's #3, only if the licence is still missing)

- **What you see:** a small zip with no game and no program in it. A stranger who already has the official
  Zakuro runs it, picks randomizer settings, and it writes a randomized mod into their Zakuro. It asks before
  it installs. Undo puts their old files back.
- **Hours:** about 7 h (estimate, Grok; docs/DOWNLOAD_PLAN.md section 7 gives no figure, "a plan only").
- **Engine build:** no.
- **Risks:** it loses everything that lives in our patches: the in-game page, Nuzlocke, the growth view, the
  Seal picker, the 60 fps / 16:9 defaults (DOWNLOAD_PLAN section 7). Its Read Me must say so plainly.
  Our randomizer tool (rando.py) refuses to write into Zakuro's own data folder on purpose, so the kit needs
  its own "install into my Zakuro" step with Undo. The bundled Python adds about 11 MB (estimate,
  DOWNLOAD_PLAN section 5).
- **Where I differ from Grok:** a small point. Grok calls the licence note "the only door" to a real
  download. There are two stops: 3dsrecomp (the note) and the MPL-2.0 sound libraries (Symphonia). MPL is a
  mild sharing licence on four small sound parts inside Zakuro: shipping is allowed if we include its text
  and say where their source is, and our own code stays ours. Your rule says any sharing licence is a stop
  until you decide, so that one is your own call, "MPL is fine" or not (DOWNLOAD_PLAN 6.2). The kit avoids
  both.
- **Depends on:** no answer from the 3dsrecomp author by its round; you OK its Read Me before anything is
  public.

### 4. Rewind, with "continue from that turn" (Grok's #4)

- **What you see:** a Rewind row (off by default). On the battle map you hold a key and the turn goes back
  to the start of your phase, up to 8 turns in a chapter. A small note is drawn on the picture (never a
  window). Greyed in Nuzlocke. In the same build: if the game closes badly, the next start offers "continue
  from that turn".
- **Hours:** about 11 h (estimate, old page item 3), plus a 1 h desk step for the trigger.
- **Engine build:** yes (your OK at its round).
- **Risks (carried from the old page, still true):**
  - **Not Backspace.** In Fates that is the Select button. Rewind needs a key the game leaves free.
  - **The trigger is not proven.** The memory value it would watch (to know when to save a turn) also
    turns on in Preparations' View Map. A 1 h desk step settles it before any build.
  - **Size.** One saved state is about 141 MB (ROBOT.md, round 3), so 8 are about 1.1 GB per chapter
    (estimate). They live in play/ next to the saves (F-048).
  - **Old states** must be refused after an update.
- **Depends on:** your play evening (Grok: after you have played a seed); cleanup.

### 5. Who can marry whom (Grok: the one extra fans ask for)

- **What you see:** a page for your run that lists who can marry whom, made from the game's tables on your
  PC. With randomized people and the full swap, it shows which children you can get.
- **Hours:** about 3 h (estimate, old page item 9).
- **Engine build:** no. It is a page next to the spoiler, made on your PC, never in git.
- **Risks:** the support tables have not been checked to read cleanly. Names and pairs only, never a line of
  game dialogue.
- **Depends on:** nothing. It can ride with item 1 in one desk round.

### Parked (each stays parked until its condition comes true)

| Item | Hours (estimate, old page) | Engine | Unparks when |
|---|---|---|---|
| One screen for a TV / Steam Deck, plus a Steam shortcut | about 19 h | yes (shortcut: no) | you say you play on a TV, couch or Deck |
| Mouse on the battle map (first version) | about 11 h (full: about 16 h) | yes | you have played a seed and ask for it |
| A second Fates fan mod as its own game (+ option sets) | about 10 h, then 3-5 h per mod | yes | you name a mod you want |
| Check words from the share code | about 1 h | no | you ask, or someone wants to share a seed |
| A comfort growth row (+25 / +50) | about 2 h | no | you ask after playing |
| A Nuzlocke run card | about 1 h 30 | rides a page build | you play a Nuzlocke |
| A controller button picture on the pause screen | about 2 h | rides an engine round | an engine round has room for it |

Small open fixes that can ride any desk round (about 1 h together, estimate; REPORT_2027-01-24): the
launcher's Zakuro row ticks too early; its Y answer is a raw STOP line; PLAY.bat exits 0 when Python cannot
start. The 2 s Start-game goal (counted 6.0 s Fates, 7.8 s Seal, REPORT_2027-01-23) needs an engine round;
it can ride item 2's round.

## The stretch (rounds 82 on; all estimates)

Before it: round 80 (about 14 h 30-17 h) and round 81 (about 11-13 h), estimates from docs/ROADMAP.md.
Disk walk: starts at 43.2 GB (counted), assumes the full wave 2 (38.6 GB) before round 80, and uses the
counted highs (14 GB per engine round, 15 GB per full check, about 1 GB per desk round).

| Round | What | Engine | Hours (estimate) | D: free after (estimate) |
|---|---|---|---|---|
| 80 | Faster enemy phase + True hit (picked) | yes | 14 h 30-17 h | about 68 GB |
| 81 | Settings for every New Game (picked; writer-group yes at that round) | yes | 11-13 h | about 54 GB |
| 82 | The full every-path check (F-051) | no | about 7 h (round 76 took about 3 h 10, counted) | about 39 GB |
| 83 | **Your play evening:** one seed to chapter 6, or "keep building" in one line | no | 1 h prep + your time | about 39 GB |
| 84 | Item 1 the label + item 5 who can marry whom + the small fixes; a read-only plan for more disk room | no | about 9 h | about 38 GB |
| 85 | Item 3 the seed kit, only if the licence is still missing (else skipped) | no | about 7 h | about 37 GB |
| 86 | Item 2 Seal name plate + item 4 Rewind in one engine round (two 1 h desk traces first) | yes | about 16-18 h (see the note below) | **about 23 GB: under 30 GB without more room** |
| 87 | The full check again (F-051) | no | about 7 h | needs more room too |
| 88 | Your play evening (Rewind and Seal full swap to try) | no | 1 h prep + your time | - |

- **The disk stop bites at round 86.** Wave 2 alone is not enough for the whole stretch. Round 84 writes a
  read-only plan for more room: waves 3a and 3b (9.4 GB), and moving the bulk of the round 70-76 folders
  (about 56.5 GB counted today) to C:, as was done for old chains on 2026-11-17. Nothing moves without your yes.
- Round 86's hours: its parts add up to 19-21 h (item 2 about 6-8 h, item 4 about 11 h, two 1 h desk
  traces). One shared block of fixed engine steps (about 3 h 15 planned) is counted once instead of twice,
  so about 16-18 h (all estimates).
- Without the OK A dumps, wave 2 is only 12.4 GB. Then round 81 would likely stop at its disk check (a
  round-74-sized pair of rounds ends at about 27 GB; estimate, DISK_BEFORE_R80.md section 4).
- After round 81 the total is about 48-50 h of estimates (rounds 82-88, without your own play time), or about
  41-43 h if the seed kit is skipped. Real time has run well under the plans lately (see the counted numbers
  above), but the plans stay the caps.
- Each step ends somewhere safe. You can stop after any play evening.

## Your calls (silence means the default)

| # | When | Call | Default |
|---|---|---|---|
| 1a | **done 2026-11-25** (your "Yes, all of wave 2"; 38.6 GB deleted with 1b, D: 44 -> 83 GB free; log build/r80/cleanup/WAVE2_DELETED.txt) | Cleanup wave 2 without the OK A dumps (12.4 GB: old build caches and old test trees that can be made again) | **nothing is deleted without your yes**; a round that would go under 30 GB stops at its disk check and reports. Round 80 alone could end at about 28.9 GB, under the line (estimate from counted sizes: 43.2 - 14.3), so a yes before round 80 is safer |
| 1b | **done 2026-11-25** (deleted together with 1a) | The OK A dumps too (26.1 GB): raw test recordings from rounds 40/41. Their results are already saved in the docs; if we ever redo that test, it makes new ones. Deleting them loses nothing you use | **kept until you say yes**. Without 1b, 1a alone (12.4 GB) is likely not enough for round 81 |
| 2 | before round 80 | Send the 3dsrecomp licence note (Claude drafted it this round) | **not sent**; Claude never sends it. About 15 min for you (estimate, Grok) |
| 3 | any time | The MPL-2.0 sound libraries (Symphonia) in a download | **stop until you say "MPL is fine"** (DOWNLOAD_PLAN) |
| 4 | at round 81 | The new writer group for settings kept for every New Game (F-057) | **asked at round 81**; nothing that needs the new writer group is built without your yes |
| 5 | after round 81 | Picks from the ranked list | **items 1 and 5 together (round 84)**, then item 2 with item 4 after your play evening; item 3 only if no licence answer by round 85 |
| 6 | round 86 | Pair the Seal name plate with Rewind in one engine round | **paired, if you OK that engine round** (saves one engine round of disk and fixed steps) |
| 7 | round 84 | More disk room: waves 3a and 3b, and moving round 70-76 bulk to C: | **Claude writes a read-only plan**; nothing moves or goes without your yes |
| 8 | round 84 | What the label is built from | **your settings plus counted seed facts**, words checked after your play evening |
| 9 | round 83 | Your play evening | **one seed to chapter 6**, your own settings; "keep building" in one line also works |
| 10 | any time | Push the 11 waiting commits; the public r77 snapshot | **held**; Claude pushes nothing |
| 11 | any time | Do you play on a TV, couch or Deck? | **parked** until you say so |

## Not doing, and why (still true from the old page)

- **Assist screen (free gold, double EXP):** it needs a new writer group and touches the same growth code as
  the randomizer. Only the small growth row stays (parked).
- **Stacking several mods with the randomizer on top:** do one mod at a time first. The map, portrait and
  castle mod tools have not been seen in the game yet (MODDING.md).
- **Race mode and a seed of the week:** almost no strangers can play before the licence is settled.
- **Full swap part 2 and a cross-gender shuffle study:** they wait until you have played the full swap.
- **Extra enemy skills:** they can make a seed unwinnable and would need the full every-chapter check again.
- **Lab work that does not change your evening:** counting functions the robot touched, putting the readable
  functions into the game you play (that needs "OK C", which cannot be asked for yet), story scenes at
  60 fps, moving to a newer Zakuro just to move.
- **A third promotion choice:** still "later". It needs an engine change your F-046 OK did not cover.
- **Citra / Azahar save import:** still not built (ROADMAP call 4). Say so if you want it.
- **Pulling Rewind or the mouse in front of your play evening:** no (Grok, both times).

## Sources

- docs/collab/NEXT_STRETCH_R78_GROK.md (round 78's question and Grok's answer, word for word).
- build/roadmap/NEXT_STRETCH_2026-11-24.md (the old ranked page; items, hours and risks carried from it).
- docs/ROADMAP.md rows 72-81; docs/DECISIONS.md F-046, F-048, F-051, F-057, F-059, F-061, F-062 (5), F-063.
- docs/REPORT_2027-01-16.md (round 71 times), REPORT_2027-01-17.md (round 72 times), REPORT_2027-01-19.md
  (round 73b), REPORT_2027-01-20.md (round 74 builds and times), REPORT_2027-01-23.md (round 76 times, the
  Seal FAIL, the Start-game times), REPORT_2027-01-24.md (round 77, the release, the open items).
- build/r77/release/run.log (the release's test times); docs/ROUND71_PLAN.md (sitting 2).
- docs/DOWNLOAD_PLAN.md sections 5, 6.2 and 7 (the licence stops, plan B); docs/LAUNCHER_PLAN.md;
  CREDITS.md (3dsrecomp "no licence file"; Seal of Flames by Laz14, gamebanana.com/mods/656034,
  CC BY-NC-ND 4.0, never shipped).
- docs/collab/LICENCE_REQUEST_3DSRECOMP.md (the licence note draft, for you to send).
- build/CLEANUP_PLAN_2026-11-24.md; build/r78/disk/ (today's sizes); df and du on 2026-11-25 at 17:31.
