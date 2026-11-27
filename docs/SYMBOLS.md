# Function names: the Fates symbol map and the function registry

Fire Emblem Fates ships a debug symbol map inside its RomFS. It gives a real C++ name
to almost every function in the game's code. The Awakening port had nothing like it and
had to guess names from RTTI, vtables and sort order (tools/m2/). For Fates we read the
map, check it against the code, and turn it into `config/functions.csv`, the one list of
functions that every other tool reads.

## Regenerate

```
python tools/analysis/funcmap.py      # function starts found by reading the code (~30 s)
python tools/fates/symbols.py         # parse the map, merge, write config/functions.csv
python tools/fates/spotcheck.py       # check the names against the code
python tools/export_symbols.py        # build/symbols.txt etc. for Ghidra / crash lookup
python tools/progress.py              # functions and named counts per library
python tools/fates/flow.py            # selftest of the control-flow walker used for boundaries
python tools/fates/test_symbols.py    # tests (16; the registry ones need extracted/)
```

`tools/fates/symbols.py` re-runs funcmap by itself when `extracted/analysis/functions.csv`
is missing or older than `code.bin`, so usually the second line is all you need.
`python tools/make_config.py` is the same as `tools/fates/symbols.py` (tools/build.py calls
it by that name). `--check` exits 1 when the tracked `config/functions.csv` is stale.

All of these read their constants from `config/game.json` through `tools/gamecfg.py`
(segments, the RomFS paths of the map). Nothing here needs the toolchain except
spotcheck's random sample, which uses objdump found by `tools/toolchain.py` (the
sibling Awakening port's copy works and is only read).

## The map

| File (romfs/debug/) | What it is |
|---|---|
| `name.StackTrace` | 26,122 demangled C++ names, NUL-separated, in address order |
| `addr.StackTrace` | 26,123 pairs of (u32 address, u32 byte offset of the name), ascending, ending with a (0, 0) terminator |
| `TimeStamp.txt` | `2015/11/17 ... Revision 27274` |

Facts checked by the parser: every offset points at the start of a string; addresses are
ascending; no address has the Thumb bit set (Thumb functions are stored at their even
address; 10 of them are only halfword-aligned, which marks them as Thumb by itself); two
addresses carry several names (identical code folded by the linker: 0x001040E8 has five,
0x00104028 two). Names have no return types; templates and `const` are kept; virtual
thunks appear as `virtual X::f(...)`; some local symbols keep their mangled form
(`t._ZSt...`, `i._ZN4Pica...`) or a file-and-line form (`"math_Matrix34.cpp".30`), and
16 compiler-generated helpers are named `<FuncN>`.

## The registry: config/functions.csv

One row per function, in address order. Rows tile .text exactly (each `end` is the next
row's `addr`; the last ends at the end of .text).

| Column | Meaning |
|---|---|
| `addr`, `end`, `size` | start, next start, size. The map has no sizes, so size runs to the next start of the merged list (it includes the function's literal pool and any padding). |
| `name` | assembler-safe unique symbol made from the name: `nn::fs::File::Read(...)` -> `nn__fs__File__Read`, `~X` -> `dtor_X`, `operator==` -> `operator_eq`. Overloads that collide get an `_XXXXXXXX` address suffix. Starts with no symbol are `func_XXXXXXXX`. |
| `class` | the enclosing scope of the name (class or namespace path); empty for free C functions |
| `library` | see the tags below |
| `source` | `symbol_map`, `funcmap:<tier>` (a start only funcmap found, kept after the boundary check below), `flow` (a start found by the boundary check itself), `hand` (config/names.csv) or `symbol_map+hand` |
| `kind` | `func`, `ctor`, `dtor`, `operator`, `thunk`, `static_init` (`__sti___<n>_<file>_cpp`), `linker` (`.ARM.Collect$$...`), `local` (mangled / file-line / `<FuncN>`), `unnamed` |
| `confidence` | that `addr` is a real start: `high` for map and hand rows, funcmap's tier otherwise |
| `mode` | `ARM` or `THUMB` (addresses never carry the Thumb bit) |
| `library_by` | how the tag was decided: `name`, `neighbor`, `calls`, `file_name`, `hand`, `none` |
| `signature` | the full demangled name from the map |
| `aliases` | other map names at the same address, joined with ` \| ` |

`config/names.csv` (columns `addr,name,library,class,note`) holds hand names and always
wins. It has one row today: 0x00300654, a 64-bit shift-left helper that the map does not
name, called `__aeabi_llsl` by what the code does.

### Library tags

Same vocabulary as the Awakening port, plus `live2d`:

| Tag | What | Tagged from the name when it starts with |
|---|---|---|
| `game` | Intelligent Systems' own code (incl. `util::`, `prim::`, `cmvm::`, `link::`, `castle::`) | any other namespace or class |
| `ctr_sdk` | Nintendo CTR-SDK | `nn::` (not nex/pia), `nngx*`, `nninit*`, `.nn.svc.*`, `__fb_/__shm_/__tx_/...` (gd), `"math_*.cpp"` |
| `nex` | NEX 3.8.3 online library | `nn::nex::`, `Quazal*`, `quazal_*`, `PRUDP*` |
| `pia` | Pia peer-to-peer library | `nn::pia::` |
| `nw4c` | NintendoWare for CTR | `nw::` |
| `live2d` | Live2D Cubism runtime | `live2d::` (the game's own Live2D wrappers such as `Live2DModelManager` are `game`) |
| `molive` | Mobiclip movie middleware | `mw::`, `mwmo*`, `VX2*`, `DEBLOCK`, `FASTAUDIO*`, `MoDeblock`, `ImaAdpcm*` |
| `pead` | the sead-derived base library | `pead::` |
| `cxx_runtime` | C++ runtime / RogueWave std | `std::`, `__rw::`, `sut::`, `__cxa_*`, `operator new/delete`, `__dynamic_cast`, ... |
| `rvct_clib` | armcc C library | `__aeabi_*`, `x$fpl$*`, `CL$$*`, `.ARM.Collect$$*`, `__hardfp_*`, `_sys_*`, `malloc`, `fputc`, ... |
| `zlib` | zlib | `deflate*`, `build_tree`, `compress_block`, ... |
| `crt0` | the entry stub at the start of .text | (address) |
| `unknown` | no reliable evidence | |

Names that do not tell (anonymous namespaces, plain C names, static initialisers,
unnamed starts) are tagged by evidence, in this order:

1. `neighbor`: the nearest name-tagged functions on both sides agree. `cxx_runtime`
   neighbours are ignored, because std:: template instances are emitted inside any TU.
   Unnamed funcmap-only starts take the tag of the code just before them (they are
   almost always local helpers of that code).
2. `calls`: a vote of the tagged callees and callers (BL/BLX targets read from the code)
   and the two neighbours. Plain C names try the call vote first: armcc puts extern "C"
   functions of several libraries into one block (0x163BD0-0x169400 mixes game camera
   script commands, Mobiclip, NEX and zlib helpers), so their neighbours mean little.
3. `file_name` (static initialisers only): armcc puts every TU's `__sti___<n>_<file>_cpp`
   in one block sorted by file name (0x54C09C-0x5BF7EC), so neighbours mean nothing.
   CamelCase files are game code (NEX DDL clients `*_Blob.cpp` excepted, by their
   calls); `module_File` files take the library of a class `module::File` in the map
   (`snd_SoundSystem` -> `nw::snd::SoundSystem` -> nw4c), then their callees, then a
   module list (`os_`, `fs_`, `applet_` ... ctr_sdk; `transport_`, `session_`, `inet_`,
   `local_` ... pia; `sead*` pead; `eft_`, `ut_`, `io_` nw4c; `mobiclip_`, `helper_` molive).
4. otherwise `unknown`. 46 functions today: 21 C-linkage camera/battle script
   commands (`camdef`, `Quake`, `Miracle`...), 15 local helpers (`<FuncN>` and mangled
   locals), 1 destructor and 9 static initialisers (`viewer_*`, `nitro_convert`, `ubl`,
   `zActor`).

## Counts (rev 27274 map, Special Edition USA code)

| Library | Functions | Named | Bytes |
|---|---:|---:|---:|
| game | 17,094 | 17,083 | 3,310,884 |
| ctr_sdk | 2,541 | 2,479 | 392,170 |
| nex | 2,170 | 2,168 | 522,224 |
| pia | 1,925 | 1,918 | 337,188 |
| nw4c | 1,250 | 1,250 | 274,208 |
| molive | 911 | 156 | 153,356 |
| live2d | 383 | 383 | 75,460 |
| cxx_runtime | 377 | 377 | 172,704 |
| rvct_clib | 226 | 104 | 25,258 |
| pead | 129 | 129 | 14,208 |
| unknown | 46 | 46 | 8,228 |
| zlib | 25 | 25 | 22,776 |
| crt0 | 1 | 0 | 36 |
| **total** | **27,078** | **26,118** | **5,308,700** |

(`Named` counts map names plus the one hand name.) Tag source: 23,394 from the name,
2,332 neighbour, 1,171 file name, 134 call vote, 1 hand, 46 none. Modes: 26,853 ARM,
225 Thumb (rvct_clib 97, cxx_runtime 83, ctr_sdk 45; no game function is Thumb).
Kinds: 20,927 func, 2,541 dtor, 1,160 ctor, 1,206 static_init, 152 operator, 74 thunk,
33 local, 25 linker, 960 unnamed. molive has few names because 755 unnamed starts are
call targets inside the hand-written VX2 / DEBLOCK / FASTAUDIO assembly, which the map
names as one block each. `build/symbols/symbols_report.txt` has the same numbers after
every run.

### Reconcile with funcmap

funcmap (tools/analysis/funcmap.py, now reading its segments from config/game.json)
finds 27,324 starts; the map has 26,117 addresses.

| | Count | What they are |
|---|---:|---|
| equal | 25,653 | both agree (funcmap tiers: 12,165 high, 11,580 medium, 1,908 low) |
| symbol-only | 464 | 451 sit inside a funcmap function: armcc drops the final `b` of a tail call when the callee comes next, so the caller falls through into it and funcmap sees one function. All are kept (the map is right). |
| funcmap-only | 1,671 | 940 kept, 731 rejected by the boundary check below |

### Function boundaries (how funcmap-only starts are checked)

funcmap guesses starts without names. Two of its guesses are often wrong inside a
named function:

- its gap scan takes any `STMFD sp!,{..lr}` / `PUSH {..lr}` as a prologue, but armcc
  often opens a function with one or two instructions before the push (`ldr r0,=x`,
  `add r0,r0,#4`, `cmp r0,#0 ; bxeq lr`). `ProcBattleInfo::Hide` (0x1D42BC) is
  `ldr r0,[pc] ; push ; bl ...` and was once cut to 4 bytes plus a fake `func_001D42C0`;
- a word in a literal pool or in ADR'd text can look like a pointer to a Thumb
  function and so produce a "Thumb start" in the middle of an ARM instruction
  (0x375BA6 inside `map::(anon)::Trade2::GetColorFlag`).

So `tools/fates/symbols.py` does not take funcmap-only starts on trust.
`tools/fates/flow.py` walks the code of each named function from its map start the way
the CPU can run it: fall-through, local branches, ARMCC jump tables, ARM->Thumb
`add ip,pc,#1 ; bx ip` stubs; calls return; literal words, the ADR'd text strings armcc
places between code blocks, and inline data an ADR points at count as data. A
funcmap-only start X inside a named function's window (up to the next map start) is
kept only if

1. that walk (or the walk from a start already kept in the window) cannot reach X, and
   X is not inside a reached instruction or data, or
2. some reached code calls X with BL/BLX (a real entry point even when another function
   also runs into it: the dropped tail branch case above).

Two kinds of start that nobody proposed are then added (`source` = `flow`): BL/BLX
targets that are still not starts (12: small Thumb runtime functions after a literal
pool, e.g. 0x302D1C called from `__ARM_common_get_typeid`), and code right after the
reached end of a function when it is a `PUSH {..lr}` in the same mode (after zero,
`mov r8,r8` or 0xFFFF fill) or a short straight Thumb function packed between an ARM
literal pool and the next Thumb function (9; e.g. 0x10004E after the 6-byte
`.ARM.Collect$$libshutdown`, 0x2FDBEC after
`nn::boss::detail::Privileged::SendPropertyHandle`). The two passes repeat until
neither finds a start, because one feeds the other: the Thumb stdio set-up at 0x103060
(found after 0xFFFF fill) is what calls 0x30119C, 0x301A10 and 0x301A1C.

A Thumb row never takes the `game` tag from a neighbour (armcc built the game's own code
as ARM only); it takes the vote of its Thumb calls instead (0x30119C calls `_sys_open`,
so rvct_clib), or else the non-game side.

| funcmap-only starts | Count |
|---|---:|
| kept: unreachable from the named function | 696 |
| kept: called with BL/BLX | 241 |
| kept: before the first map start (crt0 area) | 3 |
| rejected: reached from the named function | 731 |

The 731 rejected: 276 static-initialiser bodies right after their `__sti` stub, 267
other game code, 109 inside Mobiclip assembly, 79 in libraries; 526 of them start with a
push and 17 were Thumb guesses. The 940 kept: 755 Mobiclip assembly, 112 rvct_clib,
51 ctr_sdk, 11 game, 7 pia, 2 nex, 1 crt0.

Checked by `tools/fates/test_symbols.py`:

- `test_named_bodies_intact`: no unnamed start lies in code a named function reaches
  unless something calls it (the test that catches false splits);
- `test_arm_alignment`: ARM rows start on a word, and end on a halfword only when a
  Thumb row follows (3 do: ARM->Thumb stubs whose Thumb body follows in the same row);
- `test_direct_calls_are_starts`: every BL/BLX target in reached code (over 80,000
  call sites) is a registry start;
- `test_reviewed_boundaries`: the cases below, checked by hand with objdump.

| Address | Before the fix | Now |
|---|---|---|
| 0x1D42BC `ProcBattleInfo::Hide` | 4 bytes + `func_001D42C0` | 48 bytes, one function |
| 0x1E9ABC `BattleController::IsRunning` | 4 bytes + `func_001E9AC0` | 28 bytes |
| 0x1951D8 `ColorHandle::ColorHandle` | 4 bytes + `func_001951DC` | 56 bytes |
| 0x1648DC `BevIsViewer` | 4 bytes (unknown) + body tagged molive | 40 bytes |
| 0x375B58 `Trade2::GetColorFlag` | 78 bytes + Thumb `func_00375BA6` | 92 bytes, ends at `pop {r4,pc}` |
| 0x376B42, 0x376080, 0x4F002E ... | Thumb starts inside ARM game code (8) | gone (0x376B42 sat in ADR'd text) |
| 0x100048 `.ARM.Collect$$libshutdown$$00000002` | 388 bytes | 6 bytes (`bl ; bx lr`), Thumb `func_0010004E` follows |
| 0x103D0C `__cxa_guard_release` | ARM | Thumb (it follows an `add ip,pc,#1 ; bx ip` stub) |
| 0x30119C, 0x301A10, 0x301A1C | inside ARM rows `func_00301148` (316 bytes) and `nn::math::VEC3SafeNormalize` (192 bytes), 12 Thumb BLs from 0x1030A0..0x103132 landing there | own Thumb rows (`push` after the ARM `bx lr` / literal pool); `func_00301148` 84 bytes, `VEC3SafeNormalize` 104 bytes; the caller 0x103060 is its own Thumb row (was inside `func_00102FE2`, now 126 bytes) |
| 0x2FDBF6 (ctr_sdk boss area) | Thumb | still Thumb, and real (`push {lr} ... pop {pc}`, 6 callers); the ARM boss/http functions before such Thumb helpers end on a halfword for that reason |

Halfword-aligned starts: 42 (10 from the map, 31 kept from funcmap, 1 from flow), all
Thumb.

## Are the names right? (the rev-27274 caveat)

The map is from build rev 27274 (2015-11-17). The names are only useful if that build is
the code on this cart, so `tools/fates/spotcheck.py` checks them against the code:

1. **SVC wrappers**: all 24 `.nn.svc.<Name>` functions contain `svc #N` with the number
   3dbrew documents for <Name> (SleepThread 0x0A, CloseHandle 0x23, ...). 24/24.
2. **Starts**: all 26,025 ARM starts from the map decode as valid ARM. The word before a
   start is a return/branch (9,922), zero padding (1,035), Thumb code (44), a call to a
   no-return function (1), or something else (15,023: literal pools and fall-through
   tail calls, which can decode as anything).
3. **Accessors**: of the 430 two-instruction `Get*`/`Is*`/`Has*` functions, 430 load into
   or compute r0 and return; 39 of 40 two-instruction `Set*` store r1/r2 into the object
   (the odd one, `nn::nex::ClientProtocol::SetCallError`, has an empty body).
4. **Vtables**: 460 constructors load a vtable; in 88.7% of them a slot of that vtable is
   named after the constructor's own class. With the constructor names shuffled
   (rotated by one) the rate drops to 8.0%.
5. **20 random game functions** (seed 27274, pool: named game functions of 8..384
   bytes; `build/symbols/spotcheck20.txt`), read by eye on 2026-11-10 after the
   boundary fix. The pool changed with the sizes, so this is a new sample (the sample
   before the fix also fit 20/20). Every name fits what the code does:

| Address | Name | What the code does | Verdict |
|---|---|---|---|
| 0x0011CAEC | `Backup::(anon)::IsResultNotFoundForExtOperation(nn::Result)` | tests the result's module/description fields, calls `nn::fs::IsSdmcInserted` and a `nn::Result::ConstRange<...>::Includes` | fits |
| 0x001CBEF0 | `ActionApproach::Tick` | gets the opponent (`BattleUnit::Opponent`), runs `ActFuncApproach::Tick`, measures the distance (vsqrt), checks `IsAnimFinished` / `ActFuncRange::IsInsideRange`, then `BattleUnit::ExitSegmentRepeat` | fits |
| 0x001E793C | `TimerButtonProc::~TimerButtonProc` | writes its vtable, releases a member through a virtual call, tail-calls `operator delete` | fits |
| 0x00218F3C | `RadialBlurController::Persistent` | interpolates two start/end pairs by a float factor and stores the results as bytes in a global | fits |
| 0x00361610 | `map::SortiePosition::SetMax(int)` | allocates a new array of 2*n bytes (`operator new[]`), copies the old entries, stores the count, frees the old array | fits |
| 0x00388DE8 | `map::Draw::Resume` | `BindManager::Unbind`, `map::World::Setup`, resets `map::Cursor`, tail-calls `CameraBase::Instant` on `map::Camera::Get()` | fits |
| 0x00399FC0 | `map::trick::EnumeratorCannon::~EnumeratorCannon` | base `Enumerator` destructor then `operator delete` | fits |
| 0x003B0670 | `(anon)::LSEPlay(cmvm::CmContext*,const char*,int)` | unless `GameSkip::IsBlackOut`, tail-calls `Sound::LSEPlay(name, n)` (a script command) | fits |
| 0x003E0CA8 | `(anon)::CameraInstant(cmvm::CmContext*)` | `map::Camera::Get`, then falls through into `CameraBase::Instant` (dropped tail branch) | fits |
| 0x003F706C | `link::ec::purchase::DialogWait::Close(bool)` | sets a closed flag, plays one of two `SE_SYS_WAIT_END*` sounds by the argument, `ProcInst::Jump` | fits |
| 0x003F7AF8 | `link::ec::purchase::DialogButton2::GetResult` | returns a byte from a global dialog object | fits |
| 0x003F9630 | `link::ec::purchase::(anon)::ItemButton::OnTouchTrigger` | stores three flag bytes into the button and returns | fits |
| 0x004049E0 | `link::match::Game::TrySend(void*,unsigned int)` | `PiaSession::IsMaster`, `PiaTransport::ConvertToStationId`, `PiaTransport::SendReliable`, error handling via `NexPiaErrorHandling` | fits |
| 0x00416CF0 | `prim::PushState` | tail-calls `prim::Context::PushState` on a global context | fits |
| 0x00453CDC | `castle::MainSeqDrawer::UnBindRefreshLowerDragonMaterials` | clears per-material flag bytes in a global table | fits |
| 0x004568BC | `castle::CastleEditMenu::CreateBind(ProcInst*)` | `operator new(nothrow)`, `ProcInst::ProcInst`, sets fields, array constructor, `BasicMenuPosition::Reset`, `ProcInst::Create` | fits |
| 0x00467054 | `castle::cut::IsDisposableUnit(unsigned char)` | `Terrain::Get`, then `Terrain::IsCastleUnitDispos` | fits |
| 0x004896E0 | `castle::(anon)::MI_Main::OnSelect` | rebuilds the frame's title items (`DeleteTitleItems`, `Mess::Get`, `AddButton`, `SetItem`) | fits |
| 0x00498124 | `castle::Obstacle::~Obstacle` | unlinks entries from a linked list, frees nodes (`operator delete`), then deletes itself | fits |
| 0x00542380 | `castle::AreaObj::IsColsEnable() const` | loads one field into r0 and returns | fits |

**Conclusion**: the rev-27274 map matches the Special Edition (USA) code
(code.bin FNV-1a `9677F5445E8DCD01`) address for address. Caveats that remain:

- Another edition (Birthright/Conquest carts, other regions) or a game update has
  different code; the map must be re-checked (run spotcheck) before trusting it there.
- Names are demangled without return types, and the complete and deleting variants of a
  destructor share one demangled name; use `signature` for meaning, `name` as a label.
- 5 names share 2 addresses (folded code): only the first real name is the `name`, the
  rest are in `aliases`.
- About 450 functions end by falling through into the next one (dropped tail branch).
  The registry splits them at the map's start, which is what the original objects did.
- Unnamed starts (960) are evidence, not proof: the boundary check removes the ones
  that would cut a named function, but a start that nothing reaches or calls could still
  be dead code or data. 755 of them are in the Mobiclip assembly.
- 0x301230 is a Thumb function (`push {r3-r7,lr}` right after the `pop` ending
  0x30119C) that nothing calls or points to; it stays inside the `func_0030119C` row
  because the reach of 0x30119C runs to the literal pool after it. Harmless for the
  rebuild (same mode, same section); split it by hand if it ever matters.
- Mixed-mode code: 3 ARM rows are ARM->Thumb entry stubs whose Thumb body is in the
  same row (`sut::strchr` at 0x102D84 and two rvct_clib helpers); the `mode` column
  gives the entry mode only.
- Library tags from neighbours/calls/file names are evidence, not proof (`library_by`
  says which rule fired). Re-check before back-porting library-level knowledge.

## Exports

`python tools/export_symbols.py` writes (all under build/, gitignored):

- `build/symbols.txt`: `name 0xADDR f` lines for Ghidra's bundled
  `ImportSymbolsScript.py`. `--qualified` uses `nn::fs::File::Read`-style names (spaces
  inside operator names become `_`) instead of the assembler-safe ones.
- `build/symbols_luma.txt`: `ADDR  signature`, sorted: for a crash PC take the last line
  at or below it.
- `build/symbols_full.tsv`: addr, end, mode, library, name, qualified, signature, for
  `tools/fates/ghidra_import.py`. That Ghidra (Jython) script sets Thumb mode at Thumb
  starts, creates the functions inside their C++ namespaces and puts the signature in a
  plate comment. It has not been run in Ghidra yet.

## Other tools in this area

- `tools/analysis/funcmap.py`, `fingerprint.py`: ported (segments from config/game.json /
  layout.json). `funcmap.py --selftest` passes (41 encodings).
- `tools/analysis/splits.py` and `tools/m2/*.py`: the Awakening heuristic naming passes.
  They still hold Awakening addresses and would write wrong rows for Fates, so they
  refuse to run unless given `--awakening-pass`. The symbol map replaces them.
- `config/data_symbols.csv` (vtables, typeinfo, data names) is not produced yet; Fates
  needs its own data pass.

## Where facts came from

Everything above was read from the owner's dump (the map files, code.bin) and checked with
our own code. SVC numbers: the public 3dbrew SVC table. No community tool code was used.
