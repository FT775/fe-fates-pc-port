# How loud are the four volume lines (Fates): the four `Volume*::GetValue`

**In plain words.** The options screen has four sound sliders: music, sound effects, system sounds
and voices. The save keeps each one as a byte from 0 to 255; 255 means "full" and is what a new
game starts with. The slider itself has 32 steps. When the screen asks a slider "how far are you",
the game turns the byte into a step: 255 is step 32 (full), and any other byte is divided by 8
(so 0 .. 7 is step 0, 8 .. 15 step 1, ..., 248 .. 254 step 31). This batch
(docs/tracks/REWRITE_ORDER4.md row 6, round 23) rewrites those four questions. They store nothing:
they only read. Moving a slider (`SetValue`), loading the options from the save (`Deserialize`)
and the options writer are not touched.

Status 2026-11-17 (round 23 batch `volume`), **UNVERIFIED** in the project's sense:

- **4 readable overrides** (`src/readable/volume/volume.c`, registry and target rows added):
  `volume_bgm_value`, `volume_se_value`, `volume_sys_se_value`, `volume_voice_value`.

They give the same answers as the game's own ARM code on made-up cases (two seeds), with the same
unmapped reads and the same guest calls in the same order; the planted bugs and the tier-2 result are
in section 4. No live capture yet: the separate capture step does that (Grok: an options screen
already recorded, `bt-ch8-options` or an `opt-*` route, one route). Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin and the class tables
in rodata, read only, 2026-11-17) [high unless marked]. No table values or game text are copied here.

---

## 1. What they decide

The four bodies are the same 21 words (84 bytes with the literal pool) except for the byte they read:

| Function | Address | Byte (GameConfigData) |
|---|---|---|
| `anonymous_namespace::VolumeBGM::GetValue(void)` | 0x003BCA4C | +0x10 `volume_bgm` |
| `anonymous_namespace::VolumeSE::GetValue(void)` | 0x003BC7C4 | +0x11 `volume_se` |
| `anonymous_namespace::VolumeSysSE::GetValue(void)` | 0x003BB078 | +0x12 `volume_sys_se` |
| `anonymous_namespace::VolumeVoice::GetValue(void)` | 0x003BB168 | +0x13 `volume_voice` |

```
r0 = the option line (its first word is its class table)
get_max = class_table[+0x94]                 VolumeItemBase::GetMax 0x003BB3F8 (returns 32)
byte    = (*G_GameConfig 0x006DA0F8)[field]
if byte >= 0xFF: return get_max(line)        a tail call (bx r1)
max   = get_max(line)                        a virtual call (blx r1)
step  = 256 / max                            RVCT signed division 0x002FFA0C
byte  = (*G_GameConfig)[field]               read again, after the call
return byte / step                           RVCT signed division 0x002FFA0C
```

Details that matter for matching the game exactly:

- **The maximum is a virtual call.** All four class tables (address points 0x00637944 and the three
  after it, 0xA8 bytes apart) hold `VolumeItemBase::GetMax` (0x003BB3F8: `mov r0,#32; bx lr`) at
  +0x94, so in the game the answer is always 0 .. 32. The readable code still calls whatever the
  line's table holds, through the guest, with the line as its argument, exactly once on either path
  (docs/DECISIONS.md F-018), so a line whose table is different gets the game's answer too.
- **The division is RVCT's signed one** (0x002FFA0C): toward zero, 0 for a division by zero (its
  handler 0x0013F8B4 returns 0). The readable code computes it in C (`rvct_div`, the same helper as
  src/readable/shop_grey/); it is not a guest call. A GetMax of 0, or one beyond -256 .. 256, makes
  the step 0 and the answer 0; a negative GetMax gives a negative answer, as the game's code would.
- **The byte is read twice on the dividing path**, once before the call and once after, each time
  through the pointer in `G_GameConfig`. The readable code does the same, so an unmapped options
  pointer counts the same unmapped bytes.
- **The byte is unsigned** (`ldrb`). 0xFE is not full: it gives 0xFE / 8 = 31.

## 2. Why they are readers

The bodies store nothing but their own stack (push/pop); GetMax stores nothing; the division stores
nothing. There is no one-time cache, so the readable code never gives up. Not here, and why:

- **`SetValue`** (for example `VolumeSysSE::SetValue` 0x003BB0CC): byte = min(step * (256 / GetMax),
  255), then `GameConfigData::SetVolume*` stores it (and the sound volume follows). A writer (F-021).
- **`ResetValue`, `Deserialize`** (`GameConfigData::Deserialize` 0x001D040C stores the four bytes
  and calls `Sound::SetVolume*`) and the options writer: writers.
- **`GetValueHelp`, `GetName`**: not in Grok's row.
- The menu readers (src/readable/menu/, docs/MENUS.md) were not edited. docs/MENUS.md section 1 still
  says "not rewritten" for these four; the integrate step owns that line.

**Reach.** The options screen (Grok: an options screen already recorded, `bt-ch8-options` or an
`opt-*` route; one route). The separate capture step picks it. No chapter is added.

## 3. Checks

**Host differential test:** `python src/readable/volume/tests/volume_diff.py` (female_diff.py's and
shop_grey_diff.py's method: the ARM interpreter src/readable/battle/tests/arm_mini.py on
extracted/text.bin against the readable C built with the host gcc; r0, unmapped reads and the ordered
list of guest calls with their argument; nested give-ups and guest writes flagged). The made-up states
are random test values, never game data, and often outside what the game uses: every byte value, with
0xFE and 0xFF often; the other three lines' bytes different from the asked one; class tables whose
GetMax slot holds `VolumeItemBase::GetMax` or one of two made-up functions, with two more made-up
functions in the neighbouring slots (+0x90, +0x98); GetMax answers of 32 (the game's), 0, 1, 255,
256, 257, 1000, negative ones, the most negative and the largest int; an options pointer of 0 or
unmapped, or the pointer word itself missing. The original's tail call to GetMax (a plain `bx r1`,
which arm_mini does not stub) is answered and listed as a call by the test's own Cpu subclass.

**Planted bugs** (`--plant`, 19): the GetMax slot moved to +0x90 or +0x98; GetMax called with 0
instead of the line, on the full path or the dividing path; 0xFE also full; 0xFF not full; the full
path answering 32 without the call; the byte range 0xFF instead of 0x100; the division turned round;
the step taken as GetMax itself; an unsigned division; a division by zero answering the dividend; the
byte read signed; the byte not read again after the call; the options block read at the pointer
word's own address; each of the four lines reading its neighbour's byte.

Not planted, because they cannot change an answer: the order of the first reads (an unmapped read
counts the same bytes in any order and gives 0 either way); `rvct_div`'s "over -1" branch (the most
negative int over -1 cannot occur: 256 / max and a byte over a step never reach it); calling GetMax
before the full test on the full path too (the same one call either way).

**Tier 2** (`tools/readable/verify.py`): section 4.

## 4. Results (2026-11-17)

- Host test, seed 20261117, 300 cases per function, with `--plant`: **1,200 cases, 0 mismatches,
  19/19 planted bugs caught**.
- Host test, seed 7, with `--plant`: **1,200 cases, 0 mismatches, 19/19 planted bugs caught**. Paths
  met per function: byte 0xFF (tail call) 31 .. 44, byte 0xFE 14 .. 23, other bytes 194 .. 208,
  options pointer unmapped 23 .. 32, pointer word missing 10 .. 18; GetMax 32 in 177 .. 192 cases,
  0 in 3 .. 7, negative in 30 .. 42, over 256 in 9 .. 18, other values in 59 .. 66; every case made
  one guest call.
- Host test, seed 7, 1500 cases per function: **6,000 cases, 0 mismatches**.
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_volume --only
  0x003BCA4C,0x003BC7C4,0x003BB078,0x003BB168`; library build 330 s): **4 UNSAMPLED, 0 MISMATCH**
  (`readable-verify: OK (4 UNSAMPLED)`). UNSAMPLED: verify's one made-up state has no real class
  table, so the game's own code (interpreter and generated original alike) follows the junk GetMax
  slot into junk and runs past the instruction limit; nothing was compared, which proves nothing
  either way. The host test above is the evidence for these four. No classifier change. This run left
  out `src/readable/item_enhance/` (the row 5 batch, running at the same time, was not registered
  yet and stage.py refuses an unregistered marker) through a scratch wrapper that changed only which
  folders were walked, nothing in the repo. Logs kept in build/readable/volume/verify_logs/; the
  552 MB library was deleted after.
- `python tools/readable/check.py --selftest` on the plain tree (after the row 5 batch registered
  its row): readable OK (lint 296 rows 0 problems, 58 sources, host 146/146, capture 568/568, undo
  554/554, self-test 27/27 broken inputs, verify pipeline 28/28).
- `python tools/harness/gen_stubs.py --check`: OK (262 overrides, 66 guard users; the four volume
  rows carry no guard tag: no body calls the guard routine).
