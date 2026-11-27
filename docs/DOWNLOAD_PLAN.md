# The download a stranger could use: desk study (round 70, track download)

Round 70, 2026-11-24. Desk work only: nothing was built, downloaded or installed, no game was started, and
the real %APPDATA% / %LOCALAPPDATA% were only read (a listing, section 4.4). Big goal 4 of
[docs/ROADMAP.md](ROADMAP.md). The scripts behind the numbers are in `build/r70/download/` (gitignored):
`licences.py` (licence list), `imports.py` (what the page's Python needs), `realdirs.py` (the
"real folders unchanged" check), with their outputs `licences.json`, `licence_groups.md`, `wintree*.txt`.

## 0. For you, in plain words

**What the download would be.** A folder a stranger unzips. It holds our changed Zakuro program with **no
game code in it**, our tools (the Randomizer page, PLAY, Seal of Flames install), a small bundled Python, and
the licence notices. The stranger puts their own Fire Emblem Fates file in `roms\`, double-clicks PLAY, and
the program turns their own copy into PC code once (Zakuro's own **Recompile**, about 8 minutes on this PC,
estimate). After that it plays like yours: the Randomizer page, 60 fps, recolour, Nuzlocke, growths.

**What blocks it.** Two things, both licence questions, no technical ones:

1. **3dsrecomp has no licence file.** Its two parts (`recomp3ds` and `recomp-abi`, from
   github.com/fearkov/3dsrecomp) are compiled **into every Zakuro program**, also the one with no game code
   (Zakuro's Recompile button and its code loader are 3dsrecomp's code). Its `Cargo.toml` files say
   `license = "MIT"`, but the repository has no LICENSE file and no copyright line, and our rule since day
   one (CREDITS.md, patches/zakuro/NOTICE.md) is "personal use, unmodified". **Default: no download that
   ships a program until its author says OK; the release stays source-only.** (Grok's roadmap line "the
   recompiler is MIT" read the Cargo.toml; the missing file is what stops us.)
2. **Four small libraries inside Zakuro are MPL-2.0** (Symphonia, the AAC sound decoder Zakuro's core
   uses). MPL is a mild copyleft: shipping is allowed if we say where their source is and include the
   licence, and our own code stays MIT. Your rule says copyleft = stop, so it is listed as a stop until
   you say "MPL is fine" (or not).

Nothing else in the 243 libraries the Windows program uses is a stop (section 6).

**What you could ask the author (fearkov).** One line is enough, for example: *"3dsrecomp's Cargo.toml
says MIT but the repo has no LICENSE file. Could you add one (MIT with your copyright line), or tell me
whether I may share a Windows build of my patched Zakuro, which includes recomp3ds and recomp-abi
unmodified, with people who bring their own game? No game code would be in it."* You would send that
yourself; Claude does not contact anyone.

**Your calls.** (a) Ask the author or not (default: the release stays source-only until an OK).
(b) MPL-2.0 Symphonia: fine with a notice, or a stop (default: stop until you say fine).
(c) A portable folder (everything the program writes stays inside the download folder; default **yes**,
section 3.3).

**What round 71 would do for it** (only the cheap proof; the package waits for the author): build the
no-game-code program into a staging folder, recompile a test copy of the game in a sandbox under `build\`,
and check headless that it plays the same game as your program (section 4). If that fails, the download
slips and no extra engine OK is spent.

## 1. Two kinds of Zakuro program

| | Your program today (`play\game\Fire Emblem Fates.exe`) | Library mode (the download) |
|---|---|---|
| Game code | linked in by `engine.py port` (144.5 MB exe) | none; Zakuro's Recompile writes `%APPDATA%\3dsrecomp\0004000000179800.dll` on the player's PC (this PC's old one is 121 MB) |
| Made by | 3dsrecomp `port` + cargo, on the owner's PC | `cargo build --release -p zakuro` of our patched Zakuro (about 25 MB, estimate = 144.5 - 121) |
| Can be shared | never (it holds the game's code) | only with 3dsrecomp's author's OK (it holds recomp3ds + recomp-abi) |
| One-game features | on (`linked.is_some()`) | **off** unless we add a "port mode" (section 3) |

Facts read in the patched source (`engine/zakuro`, branch fe14 = pin c856685 + 30 patches):
- `crates/zakuro/Cargo.toml`: `recomp3ds = { git = "https://github.com/fearkov/3dsrecomp" }`;
  workspace `recomp-abi` (used by `zakuro-core`). Cargo.lock pins both at df82e6e.
- Recompile in Zakuro (`crates/zakuro/src/recompile.rs`, `lib.rs` `toolchain` / `recompile`): uses the PC's
  C compiler (`recomp3ds::compile::check`, gcc then clang then cc), else Zig in
  `%LOCALAPPDATA%\zakuro\tools\zig-0.17.0`, else **asks the player** to download Zig 0.17.0
  (`zig.rs`: 100,268,137 bytes for Windows x64, checked by SHA-256, through curl).
- Where things go on Windows: settings `%APPDATA%\zakuro\settings.toml` (`settings.rs path()`, whatever
  `--data` says); data `%APPDATA%\zakuro` unless `--data` (`lib.rs default_data_dir`); library
  `%APPDATA%\3dsrecomp\<title>.dll` and learned hints `<title>.hints` (`recomp-abi library_dir`); recompile
  work folder `%LOCALAPPDATA%\3dsrecomp\<title>\` (`recomp3ds build.rs cache_dir`; 1.3 GB for Fates here);
  Zig `%LOCALAPPDATA%\zakuro\tools` (0.4 GB unpacked here); GPU pipeline cache `%LOCALAPPDATA%\zakuro\pipelines`
  (`zakuro-gpu raster/hardware.rs`); temporary files: the system temp folder (`TEMP` / `TMP`).

## 2. One-game gates, patch by patch

"Library mode" below = the same patched Zakuro with no linked game code (`self.linked == None`).

| Patch | Gate (read in the patch / source) | In library mode | Change needed |
|---|---|---|---|
| 0001-0004 | Awakening title ids only (`game_ui::is_awakening`) | inert, as today | none |
| **0005** | `linked.is_some()` in `run()` (reads `game-path.txt` beside the exe), `program_title(linked)` (window title = exe name), the title bar code at `lib.rs` ~2169 | window says "Zakuro", `game-path.txt` is ignored, Zakuro's library list opens | port mode (3.1) |
| **0006** | none on `linked`: `Settings::load()` uses `Settings::first_run()` only when there is **no** settings.toml | works, but on a PC that already has Zakuro the shared `%APPDATA%\zakuro\settings.toml` exists, so no 60 fps / 16:9 defaults, and our program would write into the stranger's own Zakuro settings | portable folder (3.3) |
| 0007, 0008, 0010, 0011, 0014-0025 (core randomizer, Nuzlocke) | title id 0004000000179800 and `Config::fates_rando` (the frontend sets it true), `hooks_on` | work | none; but `find_tool` looks for `tools\randomizer\rando.py` in the exe's parent folders (6 up) and Python makes its runs in `<that folder>\build\rando-make`: the download folder must be writable (not Program Files) and keep the layout (3.2) |
| 0009, 0029, 0030 (the page) | `rando_link::is_fates` (title id) | works | none; Python found by `FEF_PYTHON`, then `py -3`, then `python` (`rando_page.rs pythons`, `fates_rando_session.rs probe_python`): the launcher sets `FEF_PYTHON` to the bundled one (5) |
| **0012** | `picker_applies()` = `self.linked.is_some()` and the ROM is Fates SE USA; headless `--game` / `FEF_GAME_CHOICE` exit 2 without it | no Choose your game page, no Seal of Flames, no Switch game | port mode (3.1); `game-choice.txt` and the default Seal profile are found next to the exe's parent folder (same layout as play\) |
| 0013 | rides on 0012's choice (`Config::fates_rando_game`) | Seal randomizer unreachable | port mode |
| 0026 | `FEF_PAGEBOT` only | works | none |
| **0027** | text only; the Install button runs `tools\play\sof.py`, found in the exe's parent folders (`game_pick::repo`) | works once the page shows (needs port mode) | none beyond the layout |
| 0028 | core, title id | works | none |
| `lib.rs` overlay check (`ours`, ~2258) | `linked.is_none_or(...)` | true for every game | port mode compares with the marker's title id |

## 3. What the download needs that does not exist yet

### 3.1 Port mode (one new frontend patch, round 71 staging or later)

A program with **no linked code** but a small marker file beside it (`port.json`:
`{"program_id": "0004000000179800", "name": "Fire Emblem Fates"}`) behaves like a program made of one game:
- `crates/zakuro/src/lib.rs`: a new `fn one_game(&self) -> Option<u64>` = the linked program id, else the
  marker's; it replaces `self.linked.is_some()` in `run()` (game-path.txt), `program_title`, the title bar,
  `picker_applies` and the overlay check (5 places, listed in section 2).
- `start()`: in port mode, when `zakuro_core::recompiled::installed(id)` is none or `outdated()`, it puts
  the game in Zakuro's own Recompile line (`self.recompile(vec![Wanted { .. }], false)`), which asks before
  any Zig download (`menus.compiler_offer`), shows its progress, and swaps the new code in when done
  (`loader::swap_recompiled`, existing code). Headless never recompiles.
- Tests: the marker is read; no marker = Zakuro exactly as before; a linked program ignores the marker.
- Counted: **estimate** 1 h 20 (code 50 min, tests 30 min); no build of its own (it rides the round's
  engine build). It changes nothing for your program (it is linked, so the marker path never runs).

### 3.2 Folder layout (same as the repo's, so every "beside the exe" lookup works unchanged)

```
FE Fates port\            any folder the player can write to (not Program Files)
  PLAY.bat                the launcher (3.3)
  play\game\Fire Emblem Fates.exe   our patched Zakuro, no game code
  play\game\port.json     the marker (3.1); game-path.txt is written by PLAY on first run
  python\                 the bundled Python (5)
  tools\  config\  docs\  LICENSE  CREDITS.md  NOTICES\   (licence texts, section 6)
  roms\                   the player's own .cci; roms\seal for the Seal of Flames zip
```
First run (PLAY, existing checks): the ROM's SHA-256 against config/game.json, `extracted\romfs` made from the
player's own file (the randomizer reads its tables there; 1.8 GB here), `game-path.txt` written, the program
started; Zakuro then recompiles once. Disk on the player's PC besides the ROM: about 5.7 GB (romfs 1.8 +
recompile work folder 1.3 + Zig 0.4 + library 0.12 + Python and program 0.05; the work folder could be
removed after).

### 3.3 Portable folder (launcher only, no engine change)

PLAY.bat sets `APPDATA=<port>\appdata`, `LOCALAPPDATA=<port>\localappdata`, `TEMP`/`TMP=<port>\temp` and
`FEF_PYTHON=<port>\python\python.exe` for the program only. Then Zakuro's settings, saves, the recompiled
library, Zig and the caches all stay inside the download folder: no mix-up with a Zakuro the stranger already
has (its settings.toml, or a library made by a newer 3dsrecomp, which each program would call "outdated"),
0006's first-run defaults always apply, and removing the folder removes everything. A player who starts the
exe directly gets ordinary Zakuro places (documented on the how-to-start page). The robot sandbox (4) is
the same mechanism, so the robot tests exactly what a stranger runs.

## 4. Sandbox plan for the robot test (round 71, headless, nothing downloaded)

### 4.1 Folders (all under `build\r71\libmode\`, copies only)
`appdata\`, `localappdata\`, `temp\`, `data\` (the `--data` folder), `rom\` (a copy of the clean dump,
2 GiB; its SHA-256 checked against config/game.json before and after), `stage\` (the staged program +
`port.json` if 3.1 is in), `logs\`. Saves: none of yours are read or written; your saves stay in `play\`
(F-048), the robot's in `data\`.

### 4.2 Environment for every child process
`APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP` pointed at the folders above; `HOME` and `XDG_*` unset;
`HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` = `http://127.0.0.1:9` so that any download attempt (Zakuro uses
curl) fails at once; started below normal priority (PowerShell `Start-Process -Priority BelowNormal` or the
repo's lowprio helper, never `start /belownormal`), headless, self-exiting, with a cap.

### 4.3 Zig without a download
Copy `%LOCALAPPDATA%\zakuro\tools\zig-0.17.0` (0.4 GB, read only) to
`build\r71\libmode\localappdata\zakuro\tools\zig-0.17.0`, set it read-only (`attrib +R /S`), and list its
files' sizes before and after. Zakuro's `zig::installed` then finds it, so it never offers a download.

### 4.4 The real folders stay unchanged
`build/r70/download/realdirs.py snap` lists the real `%APPDATA%\zakuro`, `%APPDATA%\3dsrecomp`,
`%LOCALAPPDATA%\zakuro`, `%LOCALAPPDATA%\3dsrecomp` (taken from USERPROFILE, so a sandboxed environment
cannot fool it): size and time of every file, SHA-256 of files under 4 MiB. Snap before, snap after,
`realdirs.py same before after` must print "real folders unchanged" (exit 0), else the run fails. Tried in
round 70: two snaps 10 s apart (21, 4, 19,507 and 836 files) were equal. This matters: this PC already has
`%APPDATA%\3dsrecomp\0004000000179800.dll` (121 MB, 2026-11-09); the test must prove it used its own.

### 4.5 Steps and caps (each step: build\STOP_ROUND absent before it starts)
1. Stage the no-game-code program (`cargo build --release -p zakuro --locked`, own target folder under
   build\r71) - part of round 71's engine OK. Cap 40 min.
2. Recompile the test copy: `engine\target\3dsrecomp\release\3dsrecomp.exe build <rom copy>` (no window;
   the same `recomp3ds::build` code Zakuro's button calls) with `CC=zig cc` and the sandbox Zig folder first
   in `PATH` (the repo path has spaces and D: has no 8.3 names, so `CC=<full path> cc` would be split
   wrongly by 3dsrecomp's `Compiler::named`). It installs into `build\r71\libmode\appdata\3dsrecomp\`.
   About 8 min (estimate from the file times of this PC's 2026-11-09 recompile), cap 20 min.
3. Headless runs of the staged program on the rom copy (`--headless N --mute --data build\r71\libmode\data`),
   each capped at 10 min, at most 4 at once:
   a. **same game**: guest memory hashes at frames 0 / 3000 / 4600 / 5200 equal to your program's
      (the round-62b frames), randomizer off; the log names the sandbox library.
   b. **page**: `FEF_PAGEBOT` script through the page with the bundled or system Python.
   c. **60 fps and 16:9**: the first-run settings written in the sandbox `appdata\zakuro\settings.toml`
      list the two enhancements; the run's report shows them on.
   d. **recolour**: a seed with recolour, the FaceData cells read back.
   e. **Seal profile**: only with port mode (3.1) and a copy of play\seal-of-flames under build\ (never
      committed); without port mode this row is "not reachable".
4. `realdirs.py same`; list and kill every process started; any visible window = failed run.

Disk: about 6 GB (rom copy 2 + recompile work 1.3 + Zig 0.4 + target 2-3, estimate). D: had 105 GB free on
2026-11-24; the round stops under 30 GB.

## 5. Bundled Python (so the page works on a PC without Python)

- **Needs**: the page's tools use the standard library only (`imports.py` over tools/randomizer, mods,
  tables, play, assets, extras: no third-party module). Tests run on Python 3.13.14 here; bundle the same
  3.13 line.
- **What**: the official "Windows embeddable package" (x64) from python.org: about 11 MB zipped, about
  25 MB unpacked (published sizes, **estimate**; measured at staging). It has no pip, no Tkinter, no IDLE;
  the page does not need them. Its `python313._pth` limits `sys.path`; our scripts add their own folders
  (`MAKE_SCRIPT` does `sys.path.insert(0, tool)`), to be checked by test 4.5-3b.
- **How it is found**: `FEF_PYTHON` (already read by the page and the core; no engine change). Optional
  engine change later: also look in `<port>\python\python.exe` so a direct start of the exe finds it
  (estimate 20 min, rides an engine batch). Bundling also avoids the Windows "python" shortcut that sends
  people to the Microsoft Store.
- **Getting it**: a download from python.org, so it waits for your OK in the release round (77). This PC's
  Python is the Microsoft Store package (WindowsApps), not suitable to copy.
- **Licence**: PSF License 2 (with the BeOpen / CNRI / CWI history notices), plus, under "Additional
  Conditions for this Windows binary build": "Microsoft Distributable Code" (vcruntime140.dll, with
  Microsoft's conditions: keep their notices, do not imply endorsement), bzip2 (BSD-style), libffi (MIT),
  a component under Apache-2.0, and Tcl/Tk's BSD-style terms (Tcl/Tk is not in the embeddable package).
  Read in this PC's Python 3.13 LICENSE.txt (645 lines); the embeddable package's own LICENSE.txt is read
  again at staging. No copyleft. Ship its LICENSE.txt unchanged in `python\`.

## 6. Licence list

### 6.1 How it was made
`build/r70/download/licences.py` read `engine/zakuro/Cargo.lock` (478 packages for all systems) and each
package's `Cargo.toml` from the copies cargo already has on this PC; `cargo tree --frozen --target
x86_64-pc-windows-msvc -e normal -p zakuro` (offline, builds nothing, changes nothing) says which **243**
go into the Windows program. Every one of the 243 was found locally. Build-only tools (for example
`cc`, `bindgen`) are not shipped and not listed.

### 6.2 Stops and notes

| Part | Licence | Verdict |
|---|---|---|
| **recomp3ds 0.1.0, recomp-abi 0.1.0** (github.com/fearkov/3dsrecomp at df82e6e; compiled into the program; also 3dsrecomp's bundled hints for this dump) | `license = "MIT"` in both Cargo.toml files, **no LICENSE file, no copyright line** in the repository (pinned checkout; a newer upstream commit was not checked: no network this round) | **STOP** (owner rule: no licence file = stop; MIT's one condition, keeping the copyright notice, cannot be met without one). Lifted by the author adding a LICENSE file or a written OK |
| **symphonia-core, -common, -metadata, -codec-aac 0.6.1** (used by zakuro-core) | MPL-2.0 (LICENSE file present) | **STOP until you decide** (owner rule: copyleft = stop). MPL-2.0 is file-level: shipping a build is allowed with the licence text and a pointer to the unchanged source (crates.io), our own code stays MIT |
| self_cell 1.3.0 (egui) | Apache-2.0 OR GPL-2.0-only | not a stop: we take Apache-2.0 |
| epaint_default_fonts 0.36.2 (egui's built-in fonts) | (MIT OR Apache-2.0) AND OFL-1.1 AND Ubuntu-font-1.0 | not a stop: the fonts ship unchanged inside the program; include both font licences |
| unicode-ident 1.0.26 | (MIT OR Apache-2.0) AND Unicode-3.0 | notice only |
| 19 crates.io packages with a licence in their Cargo.toml but no licence file inside the published package (accesskit, clipboard-win, cranelift-assembler-x64, cranelift-bitset, dasp_sample, ecolor, egui, egui-winit, emath, epaint, epaint_default_fonts, gilrs, gilrs-core, nokhwa-bindings-windows, nokhwa-core, profiling, spirv, wasmtime-internal-core, wasmtime-internal-jit-icache-coherence) | MIT / Apache-2.0 / BSL-1.0 / Apache-2.0 WITH LLVM-exception (declared by their authors on crates.io) | **your call** (F-055 call D4; it is an exception to your 'no licence file = stop' rule, so the doc does not settle it). Default proposed: not a stop: the declared licence is a standard text we ship; round 77 confirms each repository holds the file (a stop only if one has none). Different from 3dsrecomp: these are published on crates.io under a declared licence, and our standing rule names 3dsrecomp |

### 6.3 The 243 libraries in the Windows program, by licence

| Licence | Count | Libraries |
|---|---|---|
| Apache-2.0 OR MIT | 156 | the common Rust choice (egui, gilrs, image, serde, toml, sha2, rayon, log, windows-sys, and others; full list in build/r70/download/licence_groups.md, gitignored, remade by licences.py) |
| MIT | 17 | bytes, generic-array, glutin-winit, harfrust, libm, lz4_flex, **recomp-abi**, **recomp3ds**, and others |
| Apache-2.0 WITH LLVM-exception | 15 | cranelift-* (11), regalloc2, target-lexicon, wasmtime-internal-core, wasmtime-internal-jit-icache-coherence |
| Apache-2.0 | 14 | ab_glyph, ab_glyph_rasterizer, codespan-reporting, cpal, glutin, glutin_egl_sys, glutin_wgl_sys, nokhwa, nokhwa-bindings-windows, nokhwa-core, owned_ttf_parser, spirv, unicode-general-category, winit |
| Apache-2.0 OR MIT OR Zlib | 11 | bytemuck, cursor-icon, glow, miniz_oxide, and others |
| MIT (Zakuro workspace) | 6 | zakuro, zakuro-common, -core, -cpu, -fs, -gpu (LICENSE file present; our patches' notices in patches/zakuro/NOTICE.md) |
| MIT OR Unlicense | 5 | aho-corasick, byteorder-lite, jiff, jiff-core, memchr |
| **MPL-2.0** | 4 | symphonia-codec-aac, -common, -core, -metadata |
| BSL-1.0 | 2 | clipboard-win, error-code |
| Zlib | 2 | foldhash, nanorand |
| Apache-2.0 OR BSD-3-Clause | 2 | moxcms, pxfm |
| Apache-2.0 OR BSD-2-Clause OR MIT | 2 | zerocopy, zerocopy-derive |
| 0BSD OR Apache-2.0 OR MIT | 1 | adler2 |
| Apache-2.0 AND MIT | 1 | dpi |
| (MIT OR Apache-2.0) AND OFL-1.1 AND Ubuntu-font-1.0 | 1 | epaint_default_fonts |
| ISC | 1 | libloading |
| BSD-3-Clause | 1 | pp-rs |
| Apache-2.0 OR GPL-2.0-only | 1 | self_cell |
| (MIT OR Apache-2.0) AND Unicode-3.0 | 1 | unicode-ident |

No GPL-only, LGPL, AGPL, EUPL or CDDL library is in the Windows program.

### 6.4 Parts that are not Rust libraries

| Part | Licence | In the download? |
|---|---|---|
| Our port (tools, patches, launchers, docs) | MIT (scoped), LICENSE | yes |
| Zakuro (fearkov) | MIT, LICENSE in the checkout | yes, compiled in |
| fe-awakening-recomp parts in patches 0001-0004 (Zelkin1) | MIT, notice in patches/zakuro/NOTICE.md | yes, compiled in |
| 3dsrecomp (fearkov) | no licence file | **stop** (6.2) |
| Python embeddable | PSF-2.0 + components (5) | yes, with its LICENSE.txt, after your OK to download it |
| Zig 0.17.0 | MIT for Zig; its archive also carries LLVM/Clang (Apache-2.0 WITH LLVM-exception) and C library sources, some LGPL (glibc parts) | **not bundled**: Zakuro downloads it on the player's PC only when the player says yes (100 MB). Bundling it would need its own review (the LGPL parts would be a stop) |
| Microsoft VC++ runtime (VCRUNTIME140.dll; the program imports it) | Microsoft redistributable | not bundled by default; most PCs have it, the how-to-start page links Microsoft's installer. Option: build the no-game-code program with a static C runtime (one build flag; must be tested with the loaded library) |
| Windows Media Foundation (mf.dll, mfplat.dll, mfreadwrite.dll; imported by the camera library) | part of Windows | Windows "N" editions need Microsoft's Media Feature Pack or the program will not start; say so on the how-to-start page |
| Seal of Flames (Laz14) | CC BY-NC-ND 4.0 | **never**: the player installs their own download with the Install button |
| The game | Nintendo's | **never**: the player brings their own dump; the recompiled library stays on their PC |

## 7. If the author never answers: a smaller download (plan B, not built)

The randomizer can already write an ordinary mod folder (PLAY RANDOMIZED, `rando.py make --out`), which any
Zakuro loads. A tools-only download (our Python tools + the bundled Python, no program) could write that mod
into the stranger's own official Zakuro, which they get from fearkov (his program, his distribution).
It would lose everything that lives in our patches: the in-game page, Nuzlocke, the growth view, Seal of
Flames' picker, 0006's defaults. Also, `rando.py` refuses to write into %APPDATA% (our safety rule for your
PC), so it would need an explicit "install into my Zakuro" step for strangers. Size: a plan only; it needs
its own round if you want it.

## 8. For round 71's counted header (integrate)

| Item | Counted | Kind |
|---|---|---|
| Stage the no-game-code program (cargo build, own target folder) | 30 min (cap 40) | estimate (roadmap counted 20) |
| Sandbox set-up: folders, rom copy, Zig copy read-only, real-folder snap | 10 min | estimate |
| Recompile the test copy (3dsrecomp build, sandbox) | 15 min (cap 20) | estimate (about 8 min from 2026-11-09 file times) |
| Headless runs a-d (e only with port mode), 4 at once | 25 min | estimate |
| Real-folder compare, process check, write-up | 15 min | estimate |
| **Total without port mode** | **1 h 35** | estimate |
| Port mode patch (3.1), optional, rides the same build | +1 h 20 | estimate |

Patch files: none for the plain staging; port mode = a new `00NN-frontend-...port-mode.patch` touching
`crates/zakuro/src/lib.rs` only. Builds: the staging `cargo build --release -p zakuro` (an engine build:
needs your round-71 OK), no exe / boot-server / capture-library change for this part. Disk: about 6 GB.
Cut order (roadmap): the download staging is the third item to cut if round 71 runs long; since the package
waits for the author anyway, cutting it costs only the early proof.

## 9. Not done in round 70 (on purpose)

No build, no download (no Python, no Zig, no git fetch), no Windows Sandbox, no game start, no change to any
patch, tool or engine file. The upstream 3dsrecomp repository was not re-checked for a newer licence file
(no network); the owner or round 77 can look at its GitHub page.
