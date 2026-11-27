# Build the game program yourself (Road B)

Written 2026-11-26 (round 85). This page is for someone who downloaded the project's source and wants the full
port: the in-game Randomizer page, Nuzlocke, the growth view, True hit, New Game defaults and the built-in 60 fps
battles and 16:9 top screen. All of those live in our patches to Zakuro, so you have to build the program on your own
PC. **Nobody has tried these steps on a clean PC yet.** If a step fails, the message it prints is the best clue.

The plain game without these extras does not need a build: see "Road A" in [README.md](../README.md).

Every time and size below says **counted** (measured, with where) or **estimate** (a guess).

## What you get, and the one rule

- You get `play\game\Fire Emblem Fates.exe`: Zakuro (fearkov's 3DS runtime, MIT) with our 43 patches and the
  game's code built in. `PLAY.bat` starts it by itself once it is there.
- The program is made from **your own** copy of the game, so it holds the game's code. **It is for you only: never
  share it**, never upload it, never put it in a zip for someone else.
- 3dsrecomp (fearkov's recompiler) has **no licence file**. The build fetches it unmodified at a fixed version
  (a "pin", in `config/upstream.json`) for your own build only. It is not included in this download, and nothing
  here changes it.

## What you need first

| Tool | Why | Where to get it |
|---|---|---|
| Windows 11 (64-bit) | the only system the project is made for | - |
| Your own decrypted Fire Emblem Fates **Special Edition (USA)** `.cci` | the game; product `CTR-P-BFZE`, title `0004000000179800`; its SHA-256 must match `config/game.json` (`rom_sha256`). Birthright or Conquest alone, other regions, encrypted dumps and updates are refused | your own cartridge, dumped by you |
| Python 3.13 | runs every tool, and the Randomizer page calls it while you play; standard library only (no `pip install`) | python.org (tick "Add python.exe to PATH") |
| Git for Windows | `engine.py fetch` clones Zakuro and 3dsrecomp | git-scm.com |
| Rust through rustup, toolchain `stable-x86_64-pc-windows-msvc` | builds Zakuro, 3dsrecomp and the program (`config/upstream.json` names the toolchain) | rustup.rs, then `rustup toolchain install stable-x86_64-pc-windows-msvc` |
| Visual Studio C++ Build Tools | Rust's MSVC linker ("Desktop development with C++") | visualstudio.microsoft.com, "Build Tools for Visual Studio" |
| A C compiler that makes MSVC objects: **Zig** or **LLVM clang** | compiles the C code 3dsrecomp writes. `engine.py` uses the Zig that stock Zakuro downloads on its first Recompile (`%LOCALAPPDATA%\zakuro\tools\zig-*\zig.exe`), else `clang` on PATH. MinGW gcc does not work | stock Zakuro (github.com/fearkov/zakuro, Releases; run one Recompile) or llvm.org |
| An archiver: `llvm-ar` or MSYS2 `ar` | packs the compiled code into one library | comes with LLVM; or MSYS2 (msys2.org) with binutils, looked for at `C:\msys64\ucrt64\bin\ar.exe` |

If Zig sits in a folder whose path has a space (for example a Windows user name with a space), `engine.py` stops and
says so. Then pass the compiler yourself: `--cc "<path to zig.exe without spaces> cc -target x86_64-windows-msvc"`.
`--ar <path>` does the same for the archiver.

## The commands

Open a command window in the project folder (in Explorer: click the address bar, type `cmd`, press Enter). Put your
`.cci` in the `roms` folder first. Then:

```bat
python tools\engine\engine.py fetch
python tools\engine\engine.py apply
python tools\engine\engine.py port --dry-run
python tools\engine\engine.py port
PLAY.bat
```

Type or copy one line at a time; each line is only the command. What they do, in order:

1. `fetch` clones Zakuro and 3dsrecomp into `engine\` at the pins.
2. `apply` puts our 43 patches on Zakuro (a local branch, fe14).
3. `port --dry-run` checks everything and prints the plan; it builds nothing.
4. `port` builds 3dsrecomp, recompiles the game and builds the program.
5. `PLAY.bat` plays.

- `fetch` and `apply` are safe to run again; they only fix what is missing.
- `port --dry-run` lists the compiler, the archiver, your game file and where the program will go. Fix anything it
  names before the real `port`.
- `port` builds 3dsrecomp first, then recompiles the game's code, then builds Zakuro with the game inside and copies
  the program to `play\game\`. It checks your game file's SHA-256 first and stops on any other copy.
- `python tools\engine\engine.py status` says what is fetched, patched and built.
- For the Randomizer page, also prepare the game's files once: `PLAY.bat` shows a "Getting ready" window; press
  **R** there (it writes about 1.8 GB into `extracted\`; the tool's own figure).

## Time and disk

| What | Figure |
|---|---|
| Installing Rust, the Build Tools and a compiler | 30-60 min (**estimate**) |
| First build (`port`) on a new PC | 30-60 min (**estimate**; never timed on a clean PC) |
| A rebuild on the owner's PC with warm caches | about 10 min for the whole build step (**counted**, round 71) |
| The build's work folder `build\port\fef` | 4.98 GB (**counted**, the installed program's build record, 2026-11-26) |
| The program itself | 145 MB (**counted**, same record) |
| The game files for the Randomizer page (`extracted\`) | about 1.8 GB (the tool's own figure) |
| Free space to plan for | about 15 GB on the project's drive, plus the tools on C: (**estimate**) |

## Where things go

`engine\` (the fetched sources and Rust's build output), `build\port\fef\` (the generated project) and `play\game\`
(the program) are made on your PC and are never in git or in a release. `build\port\fef\` and `play\game\` hold the
game's code, and 3dsrecomp's source in `engine\` has no licence to share: keep all three to yourself.

## More

- How the engine steps work and what was checked: [ENGINE.md](ENGINE.md).
- Why each patch exists: `patches/zakuro/README.md`; notices: `patches/zakuro/NOTICE.md`.
- Playing, saves and keys: `Read Me First.txt`.
