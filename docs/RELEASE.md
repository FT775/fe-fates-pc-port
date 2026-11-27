# Making a release (one double-click)

Round 68 (release part B, F-053). The plan with your default answers is build/RELEASE_PLAN_2026-11-23.md.

## The short version

1. Double-click **`RELEASE.bat`** in the project folder.
2. Read the first screen. It says what will run, how long each step should take, and
   **`ENGINE BUILD: NO`**. Press Enter to start (or type N and Enter to stop).
3. Wait. About 7 minutes (the counted time is on the first screen).
4. The last screen says **`Ready. Core passed. Not pushed.`** Nothing has left your PC.
5. When you want it on GitHub, you run the push yourself (see "Sending it to GitHub").

`RELEASE WITH ENGINE BUILD.bat` does the same, plus it rebuilds the parts of the game that are out of date
and installs them. Its first screen lists every build. Pressing Enter there is your OK for those builds.

Both files wait for a key at the end, so the window does not close before you have read it.

## What it does, step by step

| Step | What happens | If it stops |
|---|---|---|
| 0 header | lists the steps, their counted time, and the builds (or `ENGINE BUILD: NO`) | - |
| 1 preflight | on master, nothing uncommitted, no build/STOP_ROUND, the game, boot-server and robot are not running, the capture library is not in use, at least 20 GB free (30 with the engine), your ROM is the right one, the test inputs have the right shas (and the Seal set's inputs when the Seal edition is packaged), the tag is free | one line says what to fix |
| 2 core tests | `run_tests.py --core` then `check_all.py --core --jobs 4` (with `--full`: the FULL tests) | the tests that failed are named |
| 3 engine build | engine version only: builds into a staging folder, never straight into play/ | nothing was installed |
| 4 smoke | the short headless game runs (no window; 6 Fates jobs since round 84, 8 before; when the Seal edition is packaged, then its 2 Seal jobs), on the staged build or on the frozen copies | nothing was installed; a Seal failure names the Seal edition |
| 5 package | the zip of the tracked files, a git bundle of the history, SHA256SUMS.txt, the release notes, and the gates (no game bytes, no private strings, credits present, .bat files CRLF). Since round 84 it packages twice, Seal edition first, then Vanilla+ (see "Two editions: two zips") | the gate that failed is named, with the edition |
| 6 install | engine version only: backs up first, installs, checks; any failed check puts the old files back by itself. Without the engine: only checks that the installed files match their build records | it says whether the old files are back |
| 7 record | build/release/rNN/release.json, FINAL_SHA.txt, UNDO.txt | - |
| 8 tag | a local git tag rNN with the notes as its message (never pushed) | - |
| 9 last screen | `Ready. Core passed. Not pushed.`, the notes, what was skipped, counted vs actual time, the files, the undo line, the push command | - |

The first failure stops everything with one plain line: `STOPPED at step N (...): <what to do>`.

The tag is the next round number after the newest report (for example r68). `--tag r70` picks another one.

## Two editions: two zips (round 84)

One commit gives two zips. `RELEASE.bat` makes both by itself (Seal edition first, then Vanilla+); if either one
fails, it stops and names the edition.

| Zip | Folder | What is in it | Who gets it |
|---|---|---|---|
| `FE-Fates-port-rNN.zip` (Vanilla+, "the FE Fates PC port") | `build/release/rNN/package/vanilla/` | every tracked file except the Seal edition's folders and files listed in `config/release/editions.json` (`tools/seal/`, `config/seal/`, `tests/seal/`, `docs/seal/`, its own start file and drop folder, and the old starter stub in `tools/play/`). No bundle | the public one (the public snapshot is made from this folder only) |
| `FE-Fates-port-rNN-seal-edition.zip` (the Seal edition; players read its full name) | `build/release/rNN/package/seal/` | every tracked file, plus the git bundle of the history (HEAD, master and the tags; since round 85 never the helper branches) | private (a public Seal edition release is its own later yes) |

Round 85 added to the Vanilla+ leave-out list: this release plan (docs/PUBLIC_RELEASE_PLAN.md), the game-picker
design page, the unsent licence letter draft, the 4 one-line Seal stubs that point into the left-out folder, and 4
robot scripts that start with your own folder path. Both RELEASE .bat files stay in the zip, labelled "for the
project owner".

The whole flow, from your release run to the public page: `RELEASE WITH ENGINE BUILD.bat --full` (both zips, local
tag) -> `RELEASE.bat push rNN` (private, you) -> `RELEASE.bat publish rNN` (the public copy and its checks; sends
nothing) -> your yes -> the printed public push and GitHub release commands (you, or Claude right after your yes).

Neither zip ever holds the mod itself. Each folder has its own `RELEASE_NOTES.md`, `SHA256SUMS.txt` and
`package.json`, so the two runs never wipe each other.

**By hand** (a round or a practice run; it zips the commit, so the work must be committed first):

```bash
python tools/release/package.py build --tag rNN --edition seal --out <folder>
python tools/release/package.py build --tag rNN --edition vanilla --out <folder>
python tools/release/package.py markers
```

- `--edition seal`: today's 11 gates (credits in CREDITS.md, the drop folder's README.txt and the notes; Seal data
  files hold ids only).
- `--edition vanilla`: 12 gates. The archive gate checks that exactly the left-out paths are missing; the edition
  gate checks no left-out path, no `config/seal*` file, patch 0043 in the commit, one credit line in the notes, and no
  strong Seal marker outside the allowed files (frozen history, the CREDITS.md / README.md / LICENSE credit lines,
  and the shared-by-design files, each named with its reason in editions.json). Bundle checks say "not applicable".
- `markers` writes nothing. It scans tracked files and new files git does not ignore, so it sees what the next
  commit will hold.
- No `--edition` flag = the old single package, unchanged.
- Packaging time (counted in round 84, never uploaded): about 17 s for Vanilla+, about 45 s for the Seal edition
  with its bundle. The practice zips are made from the round's final committed tree; their results are in
  docs/REPORT_2027-02-01.md.

## The questions it may ask

- **"FULL is due."** The full test set is due when the game's readable code or patches changed since the
  last tag, the randomizer's seed output changed, three releases went by on the core only, or this is the
  first release. It asks: `Go on with the CORE only? Type Y and Enter for yes, anything else stops`.
  Y makes the release with the core only and notes that FULL is still due. To run FULL, start again with
  `--full` (counted about 100 minutes on 4 lanes).
- **"Press Enter to start."** With the engine file, this is your OK for the builds it listed.

## Undo

Type in a terminal in the project folder: `python tools/release/release.py undo r68` (or
`RELEASE.bat undo r68`).

- It asks you to type `r68` back.
- If that release installed something, the files from before it come back and their shas are checked.
- A release without the engine installed nothing. Undo says `nothing was installed`.
- The local tag is deleted only if it was never pushed. **A pushed tag stays.** The files are still put back.
- Backups (build/backup/*.pre-r68) are never deleted.

## Who pushes (read this first)

**No round or workflow ever pushes.** There are two pushes, and each one needs your own words for that one push:

| Push | Where it goes | Who types it |
|---|---|---|
| The private push (`RELEASE.bat push rNN`) | the private development repository (`origin`, full history) | **you**, in your own command window (the tool refuses inside the Claude app) |
| The public push (the commands `RELEASE.bat publish rNN` prints) | the public repository FT775/fe-fates-pc-port (one commit, no history) | **you**, or **Claude in chat right after your yes for that one push** (call B6, docs/PUBLIC_RELEASE_PLAN.md). One yes covers one release only. |

How to open your own command window: open the project folder in Explorer, click the address bar, type `cmd`,
press Enter.

## Sending it to the private repository (only you)

`python tools/release/release.py push r86` (or `RELEASE.bat push r86`)

- **Only you run this.** It refuses inside an agent session, and no round or workflow ever pushes.
- If there is no GitHub address yet, it tells you how: make an **empty** repository on GitHub
  (no README, no licence file), then type `git remote add origin <its URL>`. Then run push again.
  (Done on 2026-11-24: `origin` is the private development repository.)
- Before it sends anything, it shows:
  - private strings it found in the whole history (first push) or since the last pushed tag, shown masked
    like `F***` (user name, home folder, e-mail);
  - whether the tag holds a LICENSE file (since commit 5bb9c38 it does: scoped MIT; tag r68 holds it);
  - the exact commands it will run: `git push -u origin master:main` and `git push origin refs/tags/r86`.
    Your branch here is called `master`; on GitHub it is called `main`, so `master:main` sends one to the other
    (round 85 fix: before, it would have made a second branch called `master` on GitHub).
- Then you type the tag back (`r86`). If it found private strings, you must type `r86 anyway`.
- "Since the last pushed tag": r68 was pushed by hand on 2026-11-24, outside the tool. Round 85 wrote the small
  record the tool itself writes after a push (`build/release/r68/pushed.json`, on your PC only), so the next push
  checks only what is new since r68 (30 commits when round 85 started, 0 private findings, counted). The 2 old
  findings from before r68 are already on the private repository and never reach the public one.
- What it sends: master and the tags. The helper branches are never pushed by this command.

## The public copy: `RELEASE.bat publish rNN` (round 85)

`python tools/release/release.py publish r86` makes the public copy and checks it. **It never pushes or uploads.**

1. It reads the release record: `build/release/r86/release.json` must say ok (not a rehearse), the Vanilla+
   package and all its checks passed, the zip's fingerprint (sha256) equals the `vanilla zip` line in
   `FINAL_SHA.txt` and its `SHA256SUMS.txt`, the local tag r86 sits on the record's commit, and there is no Seal
   edition zip or bundle anywhere under `build/publish/`. If any of this fails, it makes nothing.
2. It makes `build/publish/r86/repo`: a brand-new git folder with the files of the Vanilla+ zip
   (`build/release/r86/package/vanilla/FE-Fates-port-r86.zip`) and nothing else, one commit by FT775 (GitHub's
   no-reply e-mail, times in UTC), message "FE Fates PC port r86 (source only)", and a plain (lightweight)
   tag r86. An older `repo` folder there is moved aside, never deleted.
3. It runs the hard stops of docs/PUBLIC_RELEASE_PLAN.md section 6 that a tool can check: same file list as the
   zip, exactly 1 commit with no parent, only branch `main` and tag r86, the FT775 identity (exact message), an unsigned commit, no program / game /
   archive / bundle file and nothing over 10 MB, none of the left-out paths of `config/release/editions.json` and
   nothing under `play/`, the marker check (0 not allowed), the privacy scan of the copy and the notes (0 private),
   and the full credit line in the notes (one line holding the mod's author, its GameBanana link, its licence
   "CC BY-NC-ND 4.0" and "not included"; the words are checked, not compared with CREDITS.md) with no other line
   naming the mod.
4. If everything passed, it prints the commands for the public push (also saved in
   `build/publish/r86/PUSH_COMMANDS.txt`, with the results in `publish.json`): `gh auth status` (must say FT775),
   a forced push of `main` to https://github.com/FT775/fe-fates-pc-port.git (it replaces r68's copy, call B3), a
   push of tag r86, and `gh release create r86` with `RELEASE_NOTES.md`, the zip and `SHA256SUMS.txt`. The line that
   deletes the old r68 release (and its tag, so r68's files are no longer reachable from the tags page) is printed
   on its own, only for call B4.

Two things no tool checks: the repo description (you change it on GitHub, call B5) and game text in the notes and
new docs (Claude reads them).

## The public notes file (round 85)

The public Vanilla+ notes are a committed file: `config/release/notes/<tag>-vanilla.md` (for example
`r86-vanilla.md`). When the commit holds that file for the release's tag, `package.py build --edition vanilla`
uses it word for word as `RELEASE_NOTES.md`; otherwise the notes are made from the round reports as before.
Either way the credit, marker, game-bytes and privacy checks read the notes, and `SHA256SUMS.txt` lists them. The
file must name `r68` (`last_public_tag` in `config/release/editions.json`, the last copy strangers saw). If the
words change after you read them, commit the change without a new report (a new report would make the tag r87),
then run `package.py build --edition vanilla` and `package.py markers` again before the release.

## Things to know right now (checked 2026-11-24, round 69)

- **The capture library is fresh.** It was rebuilt on 2026-11-24 with your OK (`build.py --swap`, 306 s,
  sha256 `405f2bac...`; the old `610f791d...` is in build/backup/*.2026-11-24-pre-caplib). Smoke with the new
  library passed 8/8 and the memory compare matched the baseline (commit 16105ad). So a plain `RELEASE.bat` no
  longer stops at step 1 for the library.
- **Release r68 exists.** It was made by `RELEASE.bat` from commit 5bb9c38 (build/release/r68/release.json:
  started 05:02, finished 05:07, core only, nothing installed). Its zip, bundle, SHA256SUMS.txt and notes are in
  build/release/r68/package/, and the local tag `r68` points at that commit.
- **There is a LICENSE file** (scoped MIT for the project's own work, like the FE8 port; it claims no rights over
  the game, the fan mod named in CREDITS.md or other third-party work). Tag r68 holds it, so the push screen's licence check
  finds it.
- **The GitHub repositories exist, and the first push is done** (with your OK, 2026-11-24):
  - a **private development repository** with the full history; it is the `origin` remote, and `master` tracks
    `origin/main`. The old commit with the home path (see the privacy scan) went only there;
  - a **public repository** holding **one clean snapshot without history**, made from the release zip, with a
    GitHub release `r68`.
  Later pushes go through `python tools/release/release.py push rNN` as before; only you run it.
- **boot-server**'s build record is older than round 68 and lacks the Zakuro version, so the engine version
  counts a boot-server build (5 minutes, an estimate, not measured yet). Without the engine this is only a
  warning.
- **The full check (F-051 matrix) is still due** before you play: round 68 did not run it, and r68 was made on the
  CORE tests only. The roadmap runs it in round 72, on the program you would play (docs/ROADMAP.md).
- `--dry-run` writes nothing itself, but its freshness check (`build.py --check-fresh`) refreshes files under
  build/ (ignored by git). `--rehearse` keeps the release's own files in build/release/rehearse-<time>/; the
  test tools still write their usual scratch under build/.

## For rounds (agents)

- Rounds run only `--dry-run` or `--rehearse`, and may run `publish rNN` (it never pushes). No round or workflow
  ever runs a push: the private push is the owner's; the public push is the owner's, or Claude's in chat right
  after the owner's yes for that one push. `--rehearse` turns "not on master" and "uncommitted changes"
  and an out-of-date exe or library into printed `WARNING (rehearse)` lines, so a round can rehearse before
  its commit. It never backs up, installs or tags.
- `--yes` skips the Enter prompts and answers the FULL-due question with "go on". It is refused for `undo`
  and `push`.
- `python tools/release/release.py status` shows where things stand and writes nothing.
- `python tools/release/release.py fixtures` checks config/release/fixtures.json (shas only);
  `fixtures --write` rewrites it, only inside a round commit.
- `python tools/release/release.py selftest` = check_all row `release-selftest` (tests.test_release,
  test_package and test_install side by side; temp folders and fakes; nothing built, installed, tagged or
  pushed).
- Tools: tools/release/release.py (the steps), package.py (zip, bundle, gates, privacy scan, notes),
  install.py (plan, staging, backup, install with rollback, verify, undo).
- Two editions (round 84): `python tools/release/package.py build --tag rNN --edition vanilla|seal` writes
  `<out>/vanilla/FE-Fates-port-rNN.zip` (Vanilla+, leaves out the paths in config/release/editions.json, no
  bundle, plus the edition gate) or `<out>/seal/FE-Fates-port-rNN-seal-edition.zip` (full zip + bundle); no flag
  = the old single package. RELEASE.bat runs seal then vanilla once patch 0043 is in the tree; the public
  snapshot takes `vanilla/` only. `package.py markers` lists strong Seal markers the Vanilla+ zip would carry
  (exact allowed paths and shared-by-design paths are in editions.json; `*` stays inside one folder).
  Its smoke step then runs the 2 Seal jobs (`smoke.py --set config/seal/smoke_set.json run --lanes 2`, after
  the 6 Vanilla+ jobs, never at once; about 55 s more, counted at the round-84 gate); a Seal failure stops the
  release and names the edition. Preflight (step 1) also checks the Seal set's inputs
  (`smoke.py --set config/seal/smoke_set.json check`), so a missing or wrong Seal input stops the release at
  step 1, naming the edition, not at step 4.
