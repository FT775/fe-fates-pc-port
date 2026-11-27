# Seal of Flames as an optional edition: Grok's view (2026-11-26, 02:20 EST, during round 82)

## The question (facts only, no game data)

QUESTION FOR GROK (creative lead) - SPLIT SEAL OF FLAMES INTO AN OPTIONAL EDITION? Facts only, no game data. Plain words, under 600 words please. The owner asked: "discuss with Grok before acting".

The owner's idea, in their words: "have Seal of Flames an optional version of this project, not built in. So you can have a PC port
of the project with Seal of Flames or without, but both would include the randomizer built in. So we can have a vanilla+ vs a Seal of
Flames side project in the git. This allows for the projects to not get too tangled up."

Facts today:
- Seal of Flames (Laz14's fan mod, GameBanana 656034, CC BY-NC-ND 4.0) is never shipped by us. The player downloads it; the port
  finds it and layers it on the game at start (a game picker: Fates or Seal). It is always credited.
- It is wired in widely: about 266 tracked files mention it (docs, tests, randomizer modules, harness, release tools), and 18 engine
  source files have Seal branches (game picker, randomizer session, names trap, helpers, settings, the mod layer).
- The randomizer has Seal support with its own rules file; some features differ on Seal (full character swap stays off there:
  its scene name plates keep old names; seed guarantees on Seal only proven on paper).
- Tangling has started to cost us. Round 81b fixed "the randomizer does not start on a Normal + Classic New Game" for Fates, but the
  fix left Seal out on a wrong assumption, so Seal + Classic is still broken (found tonight by the full check, round 82, which is
  still running). Several rounds have spent time on Seal-only gaps.
- Releases: source only for now (a library has no licence yet). Private dev repo with history + a public repo of clean snapshots.
- The full every-path check runs 4 paths: Birthright, Conquest, Revelation, Seal.

Shapes we see:
 A. One repo, two editions. "Vanilla+" (Fates + randomizer + helpers) is the default; Seal becomes an optional edition with a clear
    seam: its own folders (config/seal, tools/seal, docs/seal, tests/seal), an engine feature/flag, its own check path and release zip.
 B. A second repo (Seal edition) that builds on the main one (main pinned as a dependency); main has no Seal code at all.
 C. A long-lived Seal branch of the same repo, merged forward from main.

Questions:
1. Is the split a good idea now? Which shape (A, B, C or another), and why, in plain words?
2. The engine: should Seal be a build-time choice (two programs) or one program that hides Seal unless the Seal edition is installed?
3. Where should the Seal randomizer rules and Seal-only fixes live, so the shared randomizer stays one piece?
4. Order: finish round 82's check first, then the Seal + Classic fix, then the split? Or fold the fix into the split?
5. Releases and checks: two zips? Does the vanilla+ full check drop the Seal path, with Seal getting its own smaller check?
6. Anything fans of fan-mod editions on PC ports expect (naming like "vanilla+", how the mod is credited, how the player picks)?
7. A rough size: a desk round to plan it, then how many rounds?

## Grok's answer

Yes, split it now. The Classic bug is the tangle costing you a round. Do not make a second repo, and do not keep a long-lived branch. Those drift, and Seal becomes the thing you forget. One repo, two editions. Fates plus the randomizer is the default, called Vanilla+. Seal is an optional edition in its own folders, with its own check and its own release notes. Both still include the randomizer. Neither ships Laz14's files.

One program, not two. The Choose your game page shows Seal only if the player added the zip. Two programs means two builds and two things to keep in step. The Vanilla+ zip simply leaves the Seal pages out. The player who wants both uses the Seal edition and still downloads the mod themselves.

The shared randomizer stays one piece. Seal's rules and Seal-only fixes live next to that rules file, in the Seal folders. The start-of-game hook is shared. The bug was assuming Seal did not use it. Do not put Seal chapter logic inside Fates code again.

Finish round 82's check first. Then fix Seal plus Classic on that shared hook, as its own small fix. Do not fold the fix into the move. A broken Classic should not wait while folders are renamed.

Vanilla+'s full check drops the Seal path. Three routes, not four. Seal gets a smaller check: the picker, one chapter, and a Classic New Game that actually starts the seed. Not another 536 runs.

Fans expect the mod named and credited every time, with a link, and a clear "not included, download it yourself." Vanilla+ should say it is Fates with the port's extras, not a new story. The picker you already have is the right way to choose.

After the check and the Classic fix: one short planning round, then two rounds to move the files and split the check. An engine build only if the picker cannot already hide Seal when the zip is absent.

