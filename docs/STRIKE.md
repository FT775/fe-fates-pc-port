# How hard one strike hits (Fates): `Side::GetSimplePower`, read from the code

**In plain words.** When two units fight, the game works out the attack and defense numbers first
(the forecast's numbers). Then one function turns them into the damage of one strike: attack minus
defense, the six damage skills (Luna, Dragon Fang, Ignis, Rend Heaven, Vengeance, Astra), the other
side's Dragonskin and its "halve damage" skill, the terrain it stands on, and the half damage of an
Attack Stance partner. This batch rewrites that function in plain C so a modder can read exactly how
it goes. It is a **reader**: it stores nothing into the game (F-017, F-021). Nothing changes in the
game.

Status 2026-11-17 (round 21, batch `strike`, docs/tracks/REWRITE_ORDER4.md row 1), **UNVERIFIED** in
the project's sense:

- **1 readable override**: `strike_power` (`src/readable/strike/strike.c`), the whole of
  `map::BattleInfo::Side::GetSimplePower` (0x005253A8). Registry row and target row added.
- It gives the same answers as the game's own ARM code on made-up cases (several seeds), with the
  same guest calls in the same order and the same unmapped reads; every planted bug is caught
  (section 6). Not yet in a live compare: a separate capture step rebuilds the capture library and
  compares it in real play.

Read in the game's ARM code (objdump of extracted/text.bin, read only, 2026-11-17) [high unless
marked]. No table values or game text are copied here. Skill names are the game's ID labels given
in English [med for the English].

---

## 1. Who asks, and with what

- The forecast (`BattleInfo::CalculateSimple`) asks with skill 0 and stores the answer into the
  side's `power` word. That store is the forecast's, not this function's.
- A real strike (`BattleCalculator::CalculateAttackSingle`) asks with the number of the skill that
  went off, and Vengeance's extra damage as the fourth argument.
- The AI's fight preview (`AIBattleSimulator::CalculateIndication`) asks it several times.

Arguments: the striking side, the other side, the skill number, the Vengeance value. A side is a
`BattleSide` record of 0x200 bytes (config/readable/structs/BattleSide.csv); docs/BATTLE2.md section 1
describes the four sides, their two detail rows and their skill bits.

## 2. The steps, in the game's order

```
0 at once when the side holds no item, or its flag 0x40 ("no damage") is set.

row    = 1 when the striking side is a follower (type 2 or 3), else 0
damage = own attack (own detail row 0)
         - the other's defense in that row (its resistance when the side's flag 0x20 says magic)
  Luna:        + half that defense back (a quarter when the other has Dragonskin)
         - the other's matching bonus (the word right after defense / resistance)
  Dragon Fang: + half of Unit::GetAttack(own unit, own item, rank bonus unless the triangle word
               is negative) (a quarter against Dragonskin)
  Ignis:       + half of the own Str for a magic weapon, of the own Mag otherwise
               (Unit::GetStrImpl / GetPowImpl with the own item; a quarter against Dragonskin)
  Rend Heaven: + half of the foe's Mag for a magic weapon, of its Str otherwise
               (the foe's unit and the foe's own item; a quarter against Dragonskin)
  Vengeance:   + the value passed in (half against Dragonskin)
  Astra:       halved; x 35 / 100, toward zero, against Dragonskin
then:
  the other has Dragonskin:       halved (x 3/4 when the weapon has the "pierces Dragonskin" flag)
  the other's "halve damage" bit: halved  [low for which skill sets that bit]
  the other's terrain, bit 21:    halved;  bit 22: quartered (both can apply)
  an Attack Stance follower (own flag bit 1): halved
  below 0 -> 0
```

- "Magic weapon" is `Item::IsMagic` of the striking weapon's record, for Rend Heaven too.
- Str and Mag are asked with extras and losses on and rally kind 0 (the fifth word, on the stack).
- The skill tests are separate ifs. If two skill caches hold the same number, a strike with that
  number takes both steps (the test checks this).
- Every halving is the game's arithmetic shift: it rounds down, also for a negative number. The
  Astra 35 % is a multiply by 35 that wraps at 32 bits, then a division by 100 toward zero.
- Dragonskin and the "halve damage" skill are bits of the other side's skill bits, in the row the
  striking side reads (`BattleSide +0xE6`, `+0x17A` for row 1). The skill numbers come from the
  caches below.
- The terrain pointer of the other side is read once; its attribute word twice (as the game does).

This matches docs/FORMULAS.md section 5 and docs/BATTLE2.md section 3, now with the Ignis and Rend
Heaven steps written too.

## 3. One-time caches and the getters

GetSimplePower looks up nine things by name the first time it runs and keeps them (guard word, then
the value): the six damage skills, Dragonskin, the "halve damage" skill and the "pierces Dragonskin"
item flag. These are the only stores in the function, and they are the game's own one-time fill.
The readable code reads them only when all nine guards say they are filled; while one is cold it
gives up at once and the original runs (and fills it).

Before a getter is called, the readable code asks that getter's own caches, so no override gives up
inside this one:

| Step | Getter | Caches asked first |
|---|---|---|
| Dragon Fang | `Unit::GetAttack` (readable `unit_attack`) | Item::IsMagic's, the Str and Mag caches, the weapon-exp limit's three |
| Ignis, Rend Heaven | `Item::IsMagic`, `Unit::GetStrImpl` / `GetPowImpl` (`item_is_magic`, `unit_strength`, `unit_magic`) | Item::IsMagic's, the Str and Mag caches |

`Unit::GetStrImpl` and `GetPowImpl` take a fifth word on the guest stack; the readable code passes it
with `guest_call5` (include/readable/fe_guest.h; its one store is in the dead stack below sp,
docs/READABLE.md section 17). That is why the battle2 batch could not write these two steps in round
11 and now they are written.

## 4. The registry row

0x005253A8 was the address of the stance batch's helper row `stance_follow_up_damage` (the last
step: a follower deals half, then below 0 is 0). A registry address is listed once, so that row is
now the override row `strike_power`, as docs/BATTLE2.md section 3 laid out. `stance_follow_up_damage`
stays a C function in src/readable/battle/stance_gauge.c (not edited), and `strike_power` calls it for
its last step; the row's evidence names it. Its own host test (stance_diff.py) still runs and passes.
The same merge was done before for `unit_hit` and `unit_attack`.

The target row in config/harness/targets.csv carries the tag "guard user (calls 0x00302C6C)": the
function calls the guard routine itself.

## 5. Not here, and why

- **Stores (writers)**: `BattleInfo::CalculateSimple` and `CalculateDetail` (they store the forecast
  numbers, including this answer, into the sides), `CalculateAttackSingle` and the rest of the strike
  list. Left out, as the plan row says.
- **Already readers**: `Side::GetSimpleTimes` (strike count, the first battle batch).
- **`forecast_damage`** in src/readable/battle2/battle2_calc.c: the round-11 copy of this function
  without the Ignis and Rend Heaven steps and without a row. It is not edited (new files only) and is
  still run by battle2_diff.py through a test-only entry; `strike_power` is the one the game uses. The
  integrate step may remove the copy (open issue).
- No damage switch, no new option: this only reads.

## 6. Checks and results

**Host differential test:** `python src/readable/strike/tests/strike_diff.py` (the method of
battle2_diff.py, whose made-up fight sides it borrows read only, and of item_diff.py for the fifth
word): the ARM interpreter src/readable/battle/tests/arm_mini.py runs the original from
extracted/text.bin; the readable C built with the host gcc runs through its real override entry on
the same memory. Compared: r0, unmapped reads, and the whole ordered list of guest calls with their
arguments (GetStrImpl / GetPowImpl with the fifth word at sp; the dead stack holds junk, so a word in
the wrong slot or never stored shows). Every callee (ToData, IsMagic, GetAttack, GetStrImpl,
GetPowImpl) is answered by one table on both sides; on the ARM side each raises "cold guard" while
one of its own caches is cold, so the readable code must give up before the call. The states are
random test values, never game data, often outside what the game uses (unmapped sides and records,
negative and huge numbers, skill caches holding 0 or sharing one number, a foe without a unit).

**Planted bugs** (`--plant`, 35): each cache group not asked (own, IsMagic's, Str's, Mag's,
weapon-exp's, the Dragon Fang check moved to Astra), both early returns, the row rule, magic flag,
attack row, bonus offset, each skill step's Dragonskin rule, the Fang bool, Str and Mag swapped for
Ignis, Rend Heaven with the own unit or own item, the fifth word wrong or never stored, a bool wrong,
IsMagic read as "equals 1", Vengeance and Astra rules, an else-if that drops a shared number's second
step, the pierce flag cut to 32 bits, the halve-damage bit, terrain of the wrong side and the wrong
bit, a negative skill number's bit, the last step dropped.

Results (2026-11-17):

- Seed 20261117, 300 cases, `--plant`: **300 cases, 0 mismatches, 35/35 planted bugs caught**.
- Seed 7, 300 cases, `--plant`: **0 mismatches, 35/35 caught**. Seeds 11 and 3 with `--plant`: the
  same.
- Seed 7, 1500 cases: **1,500 cases, 0 mismatches** (296 cold at a cache on both sides, 78 allowed
  early give-ups). Seed 20261117, 1500 cases: 0 mismatches (303 cold, 68 allowed early give-ups).
- Every skill step met with and without the other side's Dragonskin, most with damage above 0;
  shared skill numbers met (for example Ignis + Rend Heaven, Rend Heaven + Vengeance); 391 stat
  calls with a fifth word listed in the 1500-case run.
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_strike --only 0x005253A8`;
  verify library built from the tree of that moment, 349 s): **1 GAVE-UP, 0 MISMATCH**
  (`readable-verify: OK`). GAVE-UP: the nine caches are cold in verify's made-up memory, so it proves
  nothing either way. No classifier change.
- `python tools/readable/check.py --selftest`: readable OK (lint 288 rows 0 problems, 54 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27, verify pipeline 28/28).
  `python tools/harness/gen_stubs.py --check`: OK (254 overrides, 62 guard users).
- battle2_diff.py (`--only forecast_damage`) and stance_diff.py rerun after the row change: 0
  mismatches.

**Capture (not done here).** Any fight already on disk reaches it: every forecast and every strike
asks. One route is enough; `cheat-skill-proc` would also meet skill steps, `bt-ch2` is the first
plain fight. A separate capture step does it.
