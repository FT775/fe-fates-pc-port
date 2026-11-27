# The code rebuild (M1): the game's code as re-assemblable source

**In plain words.** The game's program (`code.bin`, about 6 MB of ARM machine code and
data) is turned into assembler text, one section per function, and assembled and linked
back. The result must be the original file, byte for byte. That proves every byte is
accounted for and gives a base where hand-written C++ can later replace one function at a
time. Nothing here is needed to play: PLAY uses Zakuro's own recompiled copy of the game.

Status 2026-11-10: **byte-identical** with the current function registry
(`config/functions.csv`, 27,074 rows, Thumb included) [high, `python tools/build.py all`].
The mutation and shift tests pass, and the shift test now checks Thumb code too: every
Thumb call (`bl`/`blx`, 523) is re-aimed by the linker and predicted by the test, and no
raw Thumb branch or literal load crosses an insertion point [high, `python tools/m1_tests.py all`].

```bash
python tools/toolchain.py        # once: finds the Arm GNU toolchain (here: the Awakening port's copy)
python tools/build.py all        # lint + gen asm + build + compare (~15 s with the cache)
python tools/m1_tests.py all     # determinism, mutation and shift tests (~35 s)
```

Everything generated (`asm/`, `build/`) comes from the owner's `extracted/code.bin` and is
gitignored. The tools are the Awakening port's (its docs/MATCHING.md explains sections,
literal pools, the shift test and the C++ flow); this page says what is different for Fates.

## What changed for Fates

| | Awakening | Fates |
|---|---|---|
| Function list | RTTI/heuristic naming (`tools/m2/`, `make_config.py`) | the game's own symbol map (`tools/fates/symbols.py`, docs/SYMBOLS.md); the m2 passes refuse to run here |
| Thumb code | none | 221 Thumb functions (C library, C++ runtime, SDK; no game code), 42 of them starting on a halfword |
| ARM->Thumb entry stubs | none | 22 `add ip, pc, #1 ; bx ip` stubs; 7 carry their Thumb body inside the ARM row |
| Forced raw words | config/raw_insns.txt | config/raw_insns.txt (8 addresses, found by `build.py fixraw`; addresses only) |
| Expected code.bin SHA-1 | `5ae5952f...` | `038db5d79786914f645fbef08242a138703f8d70` (config/game.json `code_bin_sha1`) |

## How Thumb is written (tools/gen_asm.py)

The registry's `mode` column says which functions are Thumb. A halfword-aligned start is
Thumb even without it.

- **Sections stay ARM.** Only ARM functions start a `.text.f_XXXXXXXX` section. A Thumb
  function is written inside the section of the ARM function before it, after a `.thumb`
  line, and the section switches back with `.arm`. So a halfword-aligned start never needs
  padding, and the shift test still inserts its NOPs only between ARM sections.
- **Stub bodies.** In an ARM row, the bytes after an `add ip, pc, #1 ; bx ip` stub are the
  Thumb code the stub jumps to (stub + 8, Thumb bit set), so they are written as Thumb too.
- **Each instruction is checked.** objdump (`-Mforce-thumb`) spells every Thumb
  instruction; one GNU as run with a listing then shows which spellings give back exactly
  the original bytes. Those stay as text (7,554 today). PC-relative instructions (306),
  short branches (B, B<cond>: 1,829, all inside one section) and anything as rejects or
  re-encodes (465, mostly data) become `.inst.n` with the original value. Targets of Thumb
  `ldr rX, [pc, #N]` are literal words: `.word`, made symbolic by the same rules as ARM
  literal pools (125 words). A "load" that would reach past the start of a later function
  is data read as code (0x00103A16 is the text "POSI") and makes no literal word.
- **Calls are symbolic.** The MPCore (ARMv6K) has no Thumb-2, so the only 32-bit Thumb
  instructions are BL and BLX; the sweep makes 4-byte items of those pairs only (0xFFFF
  padding at 0x00100382 used to swallow the next function's first halfword). All 523
  are written `bl NAME` / `blx NAME`, so the linker re-aims them when code moves; most
  leave their section. BL must land on a Thumb instruction, BLX on a 4-aligned ARM one.
  The link uses `--use-blx`: without it ld (its ARM1176 erratum fix, on by default for a
  v6K object) routes every Thumb->ARM call through an added stub and .text grows.
- **Possible missed Thumb starts.** 12 Thumb BLs land inside ARM rows, on 0x0030119C,
  0x00301A10 and 0x00301A1C (all inside unnamed ARM rows; the bytes there look like Thumb
  `push`). They are symbolic too (the target label is untyped, so ld keeps the BL), and
  `build/gen_report.txt` lists them (`thumb_call_targets_in_arm`) for the symbols area.
- **Line tags.** Thumb lines end in `@ XXXXXXXX T`, ARM lines in `@ XXXXXXXX`. The M1
  tests read ARM words from the plain tag, so a Thumb instruction is never mistaken for an
  ARM branch, and read the `T` lines separately: the shift test predicts each symbolic
  Thumb call at its new place and fails if a raw Thumb branch (B, B<cond>, a raw BL/BLX)
  or a Thumb literal load / `adr` would straddle an insertion point. Checked the other way
  too: with the calls written raw, as before 2026-11-10, the test fails (335 calls
  straddle an insertion point).
- **Thumb symbols are plain labels** (`.global name` / `name:`, no `.thumb_func`, no
  `%function`). A typed Thumb symbol would make the linker set bit 0 in `.word name`
  references and turn ARM `bl` into `blx`: different bytes. For the same reason a Thumb
  BL is never aimed at an ARM function start (its `%function` symbol would turn it into a
  BLX); none is.
- **Joins.** A Thumb literal load or `adr` that reaches past its own ARM section joins the
  sections in between, exactly like an ARM PC-relative load (docs D-005 in the Awakening
  port).

Counts are written by every `gen` to `build/gen_report.txt` (`thumb_*` lines).

## Not done yet

- Short Thumb branches (B, B<cond>) and Thumb literal loads stay raw. That is safe while
  Thumb functions share their ARM neighbour's section (the shift test checks it); it
  would matter only if a Thumb function got a section of its own (C++ replacing it).
- The three possible missed Thumb starts above belong in `config/functions.csv` once the
  symbols tools confirm them.
- No C++ yet (`config/src_map.csv` does not exist): the readable layer (docs/READABLE.md)
  is the route for rewritten game code; matching C++ is optional for this port.
- `tools/gen_headers.py` needs `config/naming/classes.csv` (RTTI class list), which the
  Fates repo does not make yet; its check_all row says SKIP with that reason.
