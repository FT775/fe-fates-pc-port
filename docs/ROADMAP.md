# Roadmap: rounds 69-78 (adopted 2026-11-24)

**In plain words.** This is what the next ten rounds promise you, how long each is counted to take, which
ones need an engine build (and so your OK), and the calls you can still change. It is the plain copy of the
owner-approved roadmap in build/ROADMAP_2026-11-24.md (Claude and Grok, after a skeptic's review). The longer
draft with every goal and the reasons is build/roadmap/ROADMAP_PLAN_2026-11-24.md; Grok's own version is
docs/collab/ROADMAP_2026-11-24_GROK.md. A plan is not a promise kept: nothing counts as done until you say ok
(F-037), and every round still gets its own counted time box (F-027).

**Your order of 2026-11-24.** You approved round 69 ("Yes, start round 69") and then asked that the rounds
after it work on the roadmap's **big goals 1-4**:

1. **Chests and villages** hold new items (rounds 70-72).
2. **The full swap**: a swapped character shows their own face and name (rounds 74-76).
3. **The smaller wishes**: the next New Game remembers your switches, growths in Preparations, the help text
   fits, a separate Recolour row, preset buttons and a short share code (rounds 71 and 74).
4. **The download** a stranger can use (desk study in round 70, staged in round 71, released in round 77 only
   if the licence question below is settled).

## The rounds

Total counted: about 60 h across 10 rounds. Three rounds build the engine and need your OK first: 71, 74
and 77 (77 is staged, tested, then installed with your OK).

| Round | Promise to you | Counted | Engine build |
|---|---|---|---|
| 69 | The front page and docs tell the truth; your ok list for rounds 59-68 fits on one page (docs/REVIEW_R59_R68.md); the disk cleanup is measured again | 3 h 10 | no |
| 70 | Desk work before any engine OK: how chests and villages work, the download plan (licence stop: 3dsrecomp has no licence file), the missing-face rule for the full swap, a judge that reads what a chest gave, round 71's exact count and cut order | 4 h 20 | no |
| 71 | Chests and villages hold new items; the next New Game remembers your switches; growths in Preparations; the help text fits; a separate Recolour row | about 13 h (cut order if it runs long: growths in Preparations, the Recolour row, the download staging) | **yes** |
| 72 | The program you would play is checked on every path (the full check), Seal of Flames bosses retried, castle rewards and shops seen | 8 h 35 | no |
| 73 | Your play evening: one seed to chapter 6, or "keep building" in one line | 1 h preparation + your time | no |
| 74 | A swapped character shows their own face and name, their voice lines go quiet, and you get preset buttons and a short share code | about 8 h | **yes** |
| 75 | The four trouble chapters (Revelation 8 and 13, Conquest 9 and 16) work with the full swap, plus the FULL tests | 5 h | no |
| 75b | **Moved up from 79 (owner, 2026-11-25: "Yes, move it up").** Guarantees inside the randomizer: a healer with a staff by chapter 7, a door and chest opener before the first map that needs one, a flier before Birthright 10 and Revelation 11; always on; every seed's result changes, so the fingerprints are re-recorded with your yes when the round starts ; a guarantee never adds a repeated class when it can avoid one (docs/SEED_GUARANTEES_PLAN.md). **Built 2026-11-25 in about 2 h real time (08:35 to about 10:35 by the clock, parts side by side; counted 7 h 50); nothing cut; fingerprints re-recorded after the r63fboss1 boss-cell diff showed every boss and enemy cell equal; one departure for your ok: a last-resort repair may re-class Gunter (F-061).** | 7 h 50 (estimate) | no |
| 76 | Everything checked again with the full swap and the guarantees on. **Done 2026-11-25 in about 3 h 5 real time (11:10 to about 14:15 by the clock, three tracks side by side, then integrate; counted 7 h; F-062).** The full check on all 4 paths: break 536/536, HANDOVER 12/12, Nuzlocke, the page robot; 168 cells, 104 SEEN, 0 FAIL. Revelation 13 and Conquest 9 PASS with the full swap, so "How they look" is now offered on the Fire Emblem Fates page (Keep the face stays the default); it stays grey on Seal of Flames, whose scene name plates keep the old name (FAIL, not fixed). The missing-face case was seen and works. Not reached: the Seal guarantees in a Seal game (a host check is due) | 7 h | no |
| 77 | Release r69 with the engine build (staged, tested, then installed with your OK); a stranger-friendly download only if the licence question is settled. **Desk part built 2026-11-25 (about 14:40 to 15:30 by the clock; F-063):** your launcher idea (docs/LAUNCHER_PLAN.md L1-L6, nothing cut): PLAY's Getting ready window finds your game file (look in the usual folders, the Windows file window, or a typed or dragged path), offers Seal of Flames and the Randomizer, never builds or downloads, and stays silent when nothing is missing; a freshly unzipped folder keeps its own saves; and look = full is now refused for Seal of Flames by every caller, not only the page (Fire Emblem Fates byte for byte unchanged). **Release r77 made 2026-11-25 16:00 to 17:18 (docs/REPORT_2027-01-24.md):** FULL tests 951/0 failed, check_all --slow 163 pass, smoke passed, 11 package gates, local tag r77, no new build due; the launcher's dry try on the real zip passed; every push and the public snapshot wait for you | 6 h 15 | done here, not pushed |
| 78 | With Grok: size the next stretch (mouse on the battle map like the FE8 port, undo turn, TV / Steam Deck layout, mod profiles). **Done 2026-11-25 as a desk round (about 17:30 to 18:01 by the clock; F-064):** the ranked plan for after round 81 is on docs/NEXT_STRETCH.md, with Grok's order, the licence note for you to send and the disk numbers; nothing on it is picked yet, you pick | 2 h | no |
| 79 | *Moved up to 75b and changed (owner, 2026-11-25): guarantees inside the randomizer instead of an after-the-fact seed doctor. The easy / fair / harsh label is left for later. Built in round 75b (F-061).* | - | - |
| 80 | Faster enemy phase (normal, 2x, 4x) + True hit (the battle forecast shows the real chance). **Built and installed 2026-11-25 in about 2 h 28 real time (18:32 to 21:00 by the clock, counted; counted 14 h 30; F-065):** True hit ships (Esc > Helpers > True hit On: the forecast shows such as 70 (real 79), from the game's own curve, checked 101/101; display only). The 2x / 4x speed was cut (the plan's cut 3): it made the enemy turn only a little faster (0.88x / 0.82x of normal time, the goal was 0.55x / 0.33x), so Esc shows a help line pointing at the game's own Options line 6 (Off, Move, All) and the Start key, both seen working. One repair build used. CORE 935 / FULL 957 tests, 0 failed; smoke 8/8; every seed the same; installed exe a8e29ced, boot-server 5692fb64. Your ok: press Esc once and look; look at one forecast with True hit On | about 14 h 30-17 h (estimate) | YES |
| 81 | Your game settings kept for every New Game (F-040's options item; the new writer group was answered by your "ok keep going"). **Built and installed 2026-11-25 in about 2 h 10 real time (21:36 to about 23:45 by the clock, counted; counted 10 h 00; F-066):** Esc > Helpers > New Game defaults has four rows (Battle animations, Map speed, Enemy turn skip, HP bars), each on Game's choice at first; a set row is written into the game's own Options once, when you start a New Game, and never into a game already going or an old save. With every row at Game's choice the program is round 80's (memory compare equal). No cut; the one repair build changed two row words to the game's own (Manual, Movement). Found on the way: the randomizer does not start on Normal + Classic (report only, a later fix needs your yes) | about 11-13 h (estimate) | YES |
| 81b | The Classic fix (your "fix the classic bug first"; Grok: fix it for real, no second Classic switch, one warning line). **Built and installed 2026-11-26 (00:02 to 01:02 by the clock for the build, proofs, checks and install, about 1 h 00, counted; counted 5 h 20; F-067):** a New Game on Normal + Classic now starts the randomizer and the Nuzlocke run, like Casual and Phoenix; if the port ever cannot see a New Game it says "This New Game did not use your seed." once on screen (not seen in any robot run; tests only). Every seed gives the same game as before. No cut, no repair build. Found on the way: on Hard the game offers only Casual / Classic, Hard + Classic was never broken, and two test routes had their names swapped (notes fixed). CORE 944 / FULL 966 tests, 0 failed; smoke 8/8; every seed the same; installed exe c2791862, boot-server 90e5638a. Your ok: start a randomized New Game on Normal + Classic | about 5 h 20 (estimate) | YES |
| 82 | The full every-path check before you play (your "ok start 82"; a check round: nothing built, fixed or installed). **Done 2026-11-26 (tracks 01:18 to 04:17 by the clock, about 3 h 00, then integrate from 04:20, counted; the plan's estimate was 4 h 15; F-068):** the program you will play (round 81b) checked on all 4 paths: break 536/536, HANDOVER 12/12, Nuzlocke, the page robot; 168 cells, 104 SEEN (82 of them carried from round 76, byte-identical runs), 0 table FAIL; 966 tests, smoke 8/8, every seed the same. The Fates way you will start works (Normal + Classic, your four rows, Everything on, Nuzlocke: one pick, the randomized enemy on the map, your settings in the game), and True hit shows the right numbers. Three FAILs, none fixed: Seal of Flames on Normal + Classic gives the plain game without saying so (use Casual or Phoenix on Seal; round 82b is the fix); one rare Seal Everything-on seed is refused, so Start game does nothing (pick another seed); four robot test routes miss their checkpoints (robot records only). Not reached: the real-chance label on screen, a full-swap face on this program | about 4 h 15 (estimate) | no |
| 82b | The Seal of Flames + Classic fix (round 82's FAIL 1; your "Yes, that order"). **Built and installed 2026-11-26 (part 1 03:08 to about 03:58, part 2 04:33 to 04:49 by the clock, about 1 h 11 of work, counted; the plan's estimate was 3 h 25; F-069):** a Seal New Game on Normal + Classic now starts the randomizer and Nuzlocke like Fates does, and the warning line shows on Seal too. Every seed the same. Round 82's FAIL 3 (route checkpoints) fixed; FAIL 2 (one rare refused Seal seed) open. No cut, no repair build. Installed exe 7ddae842, boot-server ee5ec22e (patches 0001-0042). Your ok: a randomized Seal New Game on Normal + Classic | about 3 h 25 (estimate) | YES |
| 83 | Seal edition split A (docs/SEAL_EDITION_PLAN.md section 7; F-070): the Choose your game page shows Seal only when it is added (engine patch 0043), Seal data and Seal-only tests move to Seal folders, the old Seal randomizer stand-in retired. Nothing changes for play otherwise (fingerprints, smoke, the page). **Done 2026-11-26 (F-071):** installed exe 3a471269, all checks PASS, no cuts | about 5 h 31 (estimate); took about 1 h 14 (counted) | YES, done; your start-up look ok'd 2026-11-26 |
| 84 | Seal edition split B (same plan): the rest of the Seal files move, Seal's own smoke set, two practice zips (Vanilla+ and Seal edition; no upload). **Done 2026-11-26 (F-072):** commit aa8ef66, all checks PASS, no cuts, no install | about 5 h 24 (estimate); took about 2 h 21 (counted) | YES, done; your start-up look ok'd 2026-11-26 |
| 85 | Get ready for the first public release since r68 (docs/PUBLIC_RELEASE_PLAN.md; F-073). **Done 2026-11-26 (F-074):** PLAY buttons and launcher say plainly when something is wrong, the 4 unpacked-zip test failures fixed, release tool ready (publish step never pushes), docs for strangers; practice release r86 PASS, unpacked zip 0 failed; no engine build, nothing pushed. Next: your O1 (read the notes), then O2-O5 | about 9.5-13 h (estimate); took about 56 min (counted) | YES, done |

Why the full check waits for round 72: the rule (F-053) runs it before you play or at the next round that
changes the game. Rounds 69 and 70 change no game code and no randomizer output; round 71 is the first that
does, so round 72 checks exactly the program you would play in round 73.

## Rules every round keeps

- No Nintendo or Seal of Flames bytes in git or in a package; chest lists hold facts only (chapter, call, item
  id) and hashes.
- Robot runs are headless, with APPDATA and LOCALAPPDATA pointed at sandbox folders, and nothing is downloaded.
- Every engine round names where its FULL test run happens.
- Disk space is counted in every round, with a stop if D: would fall under 30 GB free.

## Your calls and their defaults

Silence means the default (F-051(4)). Say so in one line if you want the other answer.

| # | Call | Default |
|---|---|---|
| 1 | Robot cheat pokes (items, gold, joins) in the robot's own test game, only in rounds 72 and 75, written in the cheat table. Without them those cells stay "robot could not reach" | **yes** |
| 2 | Growths in Preparations, on a key the game leaves free there | **yes** |
| 3 | The stranger-friendly download needs 3dsrecomp, whose author published no licence file | **no**: no download that ships 3dsrecomp until you (or someone) get its author's OK; the release stays source-only until then |
| 4 | Citra / Azahar save import (Grok's idea, not yours) | **not built** |
| 5 | Chest and village items | **the same-band rule** as castle rewards (each new item about as strong as the old one); the stronger hair colour is shown next to the old one on the review page |

## Where this comes from

- build/ROADMAP_2026-11-24.md: the table, the rules and the five calls above, word for word in meaning.
- 3dsrecomp's licence: CREDITS.md ("no licence file (personal use, unmodified)") and patches/zakuro/NOTICE.md
  ("Nothing from 3dsrecomp (no licence) is in any patch").
- The full-check timing: build/roadmap/ROADMAP_PLAN_2026-11-24.md ("Why the full check is not in round 69").
- The decision: docs/DECISIONS.md F-054 (roadmap adopted 2026-11-24 with these defaults; big goals 1-4 after round 69).
- Rounds 79-81: the owner's picks 2, 4 and 5 from build/roadmap/NEXT_STRETCH_2026-11-24.md (docs/DECISIONS.md F-057); a full check follows them.
