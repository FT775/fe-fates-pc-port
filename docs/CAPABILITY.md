# The stat getter a class change would pass through (capability batch)

**In plain words.** Three new readers, all read-only. The game asks a unit's stats in two ways: one
function per stat (strength, magic, ...), or one function that takes the stat's number (0 HP, 1 strength,
2 magic, 3 skill, 4 speed, 5 luck, 6 defense, 7 resistance) and looks the right getter up in a table.
This batch rewrites the second one, and the two stat totals the status screen and the help text show
(the sum of strength to resistance, with and without debuffs). Nothing here stores into the game. A class
change, a stat booster or a randomizer that edits the class and person tables changes what these return,
without any change here: they only pass the question on to the per-stat getters, which already had
readers.

Plan row: docs/tracks/REWRITE_ORDER3.md batch 3. Code: `src/readable/capability/`. Host test:
`src/readable/capability/tests/capability_diff.py`. Status of all three: **unverified** (below
shadow-clean). They have not run in the game yet; a separate capture step records that.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only, 2026-11-16)
[high]. No table values or game text are copied here.

## 1. Before starting: the stack words

The plan said: read the five-argument guest call; if the limit is still there, this batch does not
start. What was found:

- `Unit::GetCapabilityImpl` itself **receives** two words on the stack (the loss bool and the rally kind)
  and **passes one** (the rally kind) to the getter it calls. Reading the words it receives is plain:
  the override gets sp (`FE_ARG(13)`) and reads them, as the stat getters already do. Passing one word
  is `guest_call5` (docs/READABLE.md 17), already used by the staff batch.
- The two totals **call** `GetCapabilityImpl`, so they must pass two stack words, which `guest_call5`
  cannot. This batch adds `guest_call6` to include/readable/fe_guest.h (docs/READABLE.md 18): the same
  slot as `guest_call5`, one more word above it, still below sp. It has its own test with planted bugs
  (section 6). guest_call5's code is not touched.

So the limit was lifted for the getter, and lifted with one small, separately tested addition for the
totals. The batch started.

## 2. The functions

| Readable name | Game function | What it decides |
|---|---|---|
| `unit_capability` | `Unit::GetCapabilityImpl` 0x0052F7A0 | one stat by its number (below) |
| `unit_capability_rating` | `Unit::GetCapabilityRating` 0x005309E0 | strength + magic + skill + speed + luck + defense + resistance, debuffs taken off |
| `unit_capability_rating_no_weakness` | `Unit::GetNoWeaknessCapabilityRating` 0x00532B70 | the same sum with debuffs not taken off |

**One stat by number** (`unit_capability(unit, stat, item, extras)`, with the loss bool and the rally
kind on the stack):

```
entry = the 8-byte entry of the stat in the table at 0x006D9CE0 (a C++ member-function pointer:
        the function, then a "this" adjustment word)
entry names a getter      -> getter(unit, item, extras, loss), rally kind as its stack word
entry is empty, stat 0    -> GetMHPImpl(unit, extras, loss, rally kind)  (a tail branch; the item is not passed)
entry is empty, stat != 0 -> 0
```

The stat-0 tail branch is a plain `b`, not a call. 3dsrecomp turns it into a direct jump to the HP
getter's override inside GetCapabilityImpl's own generated code, so in the library the game's code makes
**no guest call** there; only the HP getter's own calls are seen. The readable code therefore runs the C of
`unit_max_hp` directly at that point (no guest call), as `cursor_terrain` and `hp_window_max_hp` do for
their inlined branches. Until round 15 it made a guest call there; section 10 says how the live capture
found that and what changed.

In the game's table stat 0 is empty and stats 1..7 name `GetStrImpl`, `GetPowImpl`, `GetTechImpl`,
`GetQuickImpl`, `GetLuckImpl`, `GetDefImpl`, `GetMdefImpl`, each with adjustment 0 (seen in
extracted/data.bin; only the shape is used in tests, not copied).

**The two totals** call `GetCapabilityImpl(unit, s, no item, extras on, loss, rally kind 0)` for s = 1..7
in that order and add the answers (32-bit wrap, as the game's adds). `GetCapabilityRating` passes loss 1,
`GetNoWeaknessCapabilityRating` loss 0. HP is not counted.

## 3. Where the readable code is narrower (it gives up; the game's own code then runs)

- A stat number of 8 or more. The game does no bounds check: it reads past the table and calls whatever
  it finds. No caller passes such a number.
- A table entry with a non-zero adjustment word. Such an entry would mean "add half of it to this", and
  with bit 0 set "call through the vtable". The game's table has none; the four ARM words of those paths
  are the only ones the host test does not run (28 of 32 words run).
- A table entry naming a function that is not one of the seven getters (a readable function only calls
  callees known to be safe to replay, docs/READABLE.md rule 4).
- A cold one-time cache of the getter it would call (section 4).

## 4. Why these are readers, guest calls and caches

None of the three stores into the game. They read the table and the two stack words and ask other
readers. The only stores are guest_call5's word and guest_call6's two words in the dead stack below sp,
the same words the game's own calls put in the same place (docs/READABLE.md 17 and 18).

Every callee is an older batch's readable override, called through the guest in the game's order with
the game's arguments (docs/DECISIONS.md F-018): the five battle getters (`unit_strength`, `unit_magic`,
`unit_skill`, `unit_speed`, `unit_luck`, src/readable/battle/formula_stats.c), `unit_defense` and
`unit_resistance` (src/readable/sheet/sheet_stats.c), and for the totals `GetCapabilityImpl` itself (this
batch). The one exception is `unit_max_hp` (sheet batch): the game reaches it by a tail branch that the
library keeps inline, so its C runs directly, with no guest call (section 2). It is a reader too.

Caches asked first, so that no callee gives up inside a guest call (a nested give-up):
- one stat: only the caches of the getter the table entry names (the battle getters through
  `unit_stat_caches_ready`, defense and resistance through their guard words, copied into capability.h
  with a note to keep them in step with sheet.h). HP: `unit_max_hp` asks its own two guard words first,
  before it reads anything; as it runs inside this override (not a guest call), a cold HP cache is a
  plain give-up of `unit_capability`, never a nested one;
- the totals: the caches of all seven getters.
None of the three has a cache of its own; none calls the guard routine (no guard tag in targets.csv).

Not changed: `unit_skill_chance` (skill batch) and `unit_level_up_preview` (growth batch) are helpers
that get "the stat now" from a callback because of the two stack words. They still do; a later batch may
switch them to `guest_call6`.

## 5. Checks

**Host differential test** (`python src/readable/capability/tests/capability_diff.py`, the method of
staff_range_diff.py, whose driver patches and build it reuses). The ARM interpreter
(src/readable/battle/tests/arm_mini.py) runs the original on extracted/text.bin. The readable C is built
with the host gcc. Both sides compare r0, the unmapped reads, and the ordered list of guest calls with
their argument registers and stack words: the getters with their fifth word, `GetCapabilityImpl` (when
the totals call it) with both. The tail branch `b GetMHPImpl` is not a call: since round 15 the test runs
the original's GetMHPImpl on as ARM code, unlisted (as the library does), and lists the calls GetMHPImpl
itself makes (GetLimit, Edit::GetCapability, IsEquipSkill: sheet_diff.py's table). On the C side a guest
call of GetMHPImpl is answered and listed, so a readable side that makes one shows a call the original
never makes. About a third of the getter's cases are stat-0 cases built on sheet_diff.py's made-up units
(person, job, condition bytes, skill caches, torn and unmapped units), so `unit_max_hp` runs on
real-looking state. (Before round 15 the test counted the tail branch as a call, the same as the readable
guest call, so it could not see the difference the live capture found.) Every callee is answered by one
table on both sides. The getters are guarded: reaching one while one of its guards is cold gives up on the ARM side and
counts as a nested give-up on the C side; for the totals `GetCapabilityImpl` is guarded by all seven
getters' guards. Guest writes and nested give-ups are flagged.

Made-up states (random test values, never game data, often outside what the game uses): stat numbers of
8 and more, including ones whose times-8 wraps back into the table; table entries moved to another stat,
empty for a stat other than 0, with an even adjustment, or naming a function that is not a getter (most
often the entry of the stat asked); loss and extras words that are not 0/1; rally kinds of all sizes;
item 0 and unmapped items and units; stat answers huge and negative, so the totals wrap.

**Planted bugs** (`--plant`, 35): the two stack words swapped, the rally kind from the wrong word or
left out; the table step, the table address; the adjustment check reduced to bit 0; the "empty entry, stat
not 0" answer left out or wrong, or given for stat 1 too; HP: extras forced on, the loss bool or 0 passed
as the rally kind, and the round-15 live bug itself (a guest call of GetMHPImpl instead of running
`unit_max_hp`); the getter call with extras and loss swapped, without the item, without the stack
word, extras squashed to 0/1; each getter's cache check left out or asked for the wrong stat; the totals:
the loss bool of each, the first and last stat, extras, rally, item, the sum replaced by the last answer,
`guest_call5` instead of `guest_call6`, a getter's caches left out of the totals' check.

Left out on purpose, because they cannot change an answer: "stat > 8" instead of "stat >= 8" (for stat 8
both sides then read the same two unmapped words and answer 0, so even r0 and the unmapped reads agree).
Since round 15 there is no HP cache check of this batch's own to plant: `unit_max_hp` asks its caches
first itself, and the sheet batch's test plants that check.

## 6. Results (2026-11-16)

Round 15 (after the fix of section 10), the host test as changed there:

| Run | Result |
|---|---|
| host test, seed 20261116, 300 per function, `--plant` (plants on seed 20261117) | **900 cases, 0 mismatches, 35/35 planted bugs caught** (the old guest call, planted: 110 mismatches) |
| host test, seed 7, `--plant` (plants on seed 8) | 900 cases, 0 mismatches, **35/35 planted bugs caught** |
| host test, seed 99, 300 per function | 900 cases, 0 mismatches |
| host test, seed 7, 1,500 per function | **4,500 cases, 0 mismatches** (494 both gave up at a cold cache, 245 early give-ups in the getter) |
| `sheet_diff.py --only unit_max_hp` (the C now run directly) | 400 cases, 0 mismatches |

Paths met on seed 7, 1,500 each: the HP tail branch 490 (158 of them with unmapped reads), the getter
572, a moved getter 29, an empty entry giving 0 141, an adjusted entry 41, an entry naming no getter 24,
a stat past the table 89, a cold cache 114. Original's words run: 28 of 32, 21 of 21, 20 of 20.

Before the fix (first run, same day):

| Run | Result |
|---|---|
| `guest_call6_test.py --plant` | 224/224 checks, **10/10 planted bugs caught** |
| `guest_call5_test.py --plant` (fe_guest.h changed) | 192/192, 7/7 planted bugs caught |
| host test, seed 20261116, 300 per function, `--plant` (plants on seed 20261117) | **900 cases, 0 mismatches, 34/34 planted bugs caught** |
| host test, seed 7, `--plant` (plants on seed 8) | 900 cases, 0 mismatches, **34/34 planted bugs caught** |
| host test, seed 7, 1,500 per function | **4,500 cases, 0 mismatches** (530 both gave up at a cold cache, 314 early give-ups in the getter) |

Parts of the original the cases ran: the getter 28 of 32 words (the four not run are the virtual and
adjusted-pointer paths, section 3), each total all of its words (21 and 20). Paths met on seed 7, 1,500
each: the getter called 837, a moved getter 56, the HP tail call 126, an empty entry giving 0 132, an
adjusted entry 65, an entry naming no getter 45, a stat past the table 126, a cold cache 113; the totals
about 1,040 sums each, about 250 of them wrapped past 2^31.

Tier 2, check.py and gen_stubs: section 8.

## 7. Where the game reaches them

- `GetCapabilityImpl`: the status window's ability page (`ViewerUnitStatus::AbilityWindow::DrawDetail`),
  the unit list, the level-up screen (`LevelUpSequence`), the AI's status-staff score
  (`AIInterferenceSimulator::CalculateScore`), the castle battle score, the chapter scripts'
  `UnitGetCapability`, the help text, the handicap sort, the Dragon Vein check, and the writers
  `Unit::ClassChange`, `LevelUp`, `ItemUse`, `Handover` (which stay writers: they store; not this batch).
- `GetCapabilityRating`: the status window's short page (`AbilityWindow::DrawSimple`) and the online
  team packet. `GetNoWeaknessCapabilityRating`: the help text (`GameHelp::DrawCapability`).

Per the plan, no chapter is added. The status sheet and every fight already reach the getter. Which
recordings already on disk reach them was not checked here (this batch runs no robot games). The capture
step says it; a reader no recording reaches is "not here".

## 8. Gates

- `python tools/harness/gen_stubs.py --check`: OK (248 overrides, 60 guard users).
- `python tools/readable/check.py --selftest`: **readable: OK** (lint 283 rows, 0 problems; 50 sources
  and 50 staged files compile; host 146/146, capture 568/568, undo 554/554; self-test 27/27; verify
  pipeline 28/28).
- Tier 2 (`python tools/readable/verify.py --out build/readable/v_capability --only
  0x0052F7A0,0x005309E0,0x00532B70`; library build 319 s): **0 MISMATCH, 3 GAVE-UP**
  (`readable-verify: OK (3 GAVE-UP)`). GAVE-UP means verify's pristine memory has the getters' one-time
  caches cold, so the readable code gave up and only the fallback ran: that proves nothing either way
  (as for the staff batch and the other cache users). The register and dead-stack notes verify printed for
  the two totals (r1, r14, memory at 0x0FFFEF40) are in the ABI-allowed set and the dead stack. In the
  shadow pass no comparison was logged. The classifier was not changed. The evidence for these three is
  the host test until the capture step records them.

Round 15, after the fix of section 10: gen_stubs `--check` OK (248 overrides, 60 guard users);
`check.py --selftest` **readable: OK** (lint 283 rows, 0 problems; 50 staged files compile; host
146/146, capture 568/568, undo 554/554); tier 2 (`verify.py --out build/readable/verify-r15-capability
--only 0x0052F7A0,0x005309E0,0x00532B70`, library build 335 s): **0 MISMATCH, 3 GAVE-UP**
(`readable-verify: OK (3 GAVE-UP)`), the same notes as before. Classifier not changed.

## 9. Not in this batch

- `Unit::ClassChange`, `MergeSeal`, `LevelUp`, `ItemUse` and any other function that stores a stat (the
  plan says so).
- The chapter scripts' `UnitGetCapability` (0x003ABF44 holds its call): a reader candidate for later.
- Switching the two callback helpers to `guest_call6` (section 4).

## 10. Round 15: the live capture finding and the fix

The capture step (session `r15-cap-capability`, 8 Birthright routes) found **7 MISMATCH_CALLS records in
`unit_capability`** (bt-prologue 1, bt-ch4 2, bt-ch5 2, bt-ch8 2), all "probe calls: 0 vs 1 (1 done
inline by B)" (bt-prologue: 3 done inline). Run A (the game's code) made no call that B was held to; run
B (the readable code) made one. `unit_capability_rating` was clean (SHALLOW), the no-weakness total not
reached. The offline replay judged the 7 as match; the live verdict counts.

Cause (confirmed in the library's generated code, build/harness/lib, `f_0052F7A0`): the stat-0 path ends
with `reg15_ = 0x0052A364u; CALL(override_0x0052A364); RETURN();`, a direct jump to the HP getter's
override that the capture does not note as a call. So in run A only the HP getter's own calls (GetLimit,
Edit::GetCapability, IsEquipSkill) are noted; B never called those itself, so they count as "done inline
by B", and B's guest call of GetMHPImpl has nothing in A to match. The 7 records return small max-HP
values (0x10 .. 0x26), which fits.

Fix: the readable code runs `unit_max_hp(ctx, unit, extras, loss, rally kind)` directly at that point
(the same function the HP override runs), so B's own calls are now exactly the HP getter's calls, which A
notes too. The extra HP cache check of this batch (`hp_caches_ready`, `S_CapHpGuard0..1`) is gone:
`unit_max_hp` asks the same two guard words first, before reading anything. The live classifier was not
changed. The host test was changed so it can see this kind of difference (section 5) and catches the old
code as a planted bug.

What is still open: the 8-route capture must be run again with the rebuilt capture library (not done
here: this step builds no capture library and plays no routes). Until it is clean, `unit_capability` is
not cleared.

**Closed in round 15 (integrate, 2026-11-16).** The retry capture `r15-cap-capabilityb` ran the same 8
routes with the capture library rebuilt once by `parallel.py build` (303 s, 248 overrides; the staged
capability.c holds the direct `unit_max_hp` call): 8 of 8 PASS, every memory hash equal to the first try,
415 records, **0 bad of any kind** (mismatch_calls 7 -> 0); `unit_capability` 228 records (169 match, 56
gave up), `unit_capability_rating` 187 (104 match, SHALLOW), the no-weakness total never called. The
integrate compare then used `r15-cap-capabilityb` and left out `r15-cap-capability` (recorded before the
fix): offline 181,444 records, 0 bad; bt-ch27 live with every override (`r15-capn`) met both readers (31
and 17 more records), 0 bad; the 4 cheat routes live with the three readers (`r15-capc-capability`), 300
records, 0 bad. H5 (`r15-h5`): `unit_capability` 259 records (193 match), `unit_capability_rating` 204
(113 match); `unit_capability_rating_no_weakness` is still never met in real play (only the help text
calls it), so its only evidence is the host test. check_all rows: `capability-diff`,
`capability-diff-long` and `guest-call6-test`.
