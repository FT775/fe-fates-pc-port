# Weapon triangle and weapon ranks: how they work, read from the code

**In plain words.** Every weapon belongs to one of eight kinds (sword, lance, axe, dagger, bow,
tome, staff, stone). In a fight, the kinds of the two weapons decide who has the triangle
advantage, and the advantage gives a little extra damage and hit, more at higher weapon ranks.
Separately, a unit gets a weapon-rank bonus for being good with its weapon. This note says how
both work in Fates, from the game's own code, and which parts now have a readable C version (the
second batch of the readable rewrite, plan step 9, after the stances).

Status 2026-11-11: 7 readable overrides and 6 helpers written, all **UNVERIFIED** in the
project's sense (tier 2 below is a smoke test, not a shadow run). Every one of them gives the
same answers as the game's own ARM code on generated inputs (section 6), and 18 bugs planted on
purpose were all caught. Nothing changes in the game.

Confidence tags: **[high]** read in the code and tested against it, **[med]** read in the code
but its meaning is an inference, **[low]** a guess. No table values are copied here; the table
layouts are in docs/TABLES.md.

---

## 1. Words

| In this note | In the game's code (symbol map) | What it is |
|---|---|---|
| weapon kind | `ItemKind::Type` (0 sword .. 7 stone) | the eight kinds; the triangle and the rank bonus use these |
| sub-kind | `ItemSubKind` (`Item +0x1A`) | the 21 finer kinds of the item data (Hoshido and Nohr names, refining group); each names one kind (`ItemSubKind +0x1`) |
| weapon rank | `WeaponLevel::GetLevel` (0 = S .. 5 = E, 6 = none) | from the unit's weapon exp in that kind |
| rank bonus | `WeaponBonus` | per kind and rank: extra damage and hit for being skilled |
| triangle | `WeaponInteract` | per rank: the triangle's damage and hit; then an 8x8 matrix of +1 / -1 / 0 |
| triangle cell | `map::BattleInfo::Side +0x14` | +1 advantage, -1 disadvantage, 0 neutral, after reversal also +2 / -2 |
| reversing weapon | an item flag found by name (`ItemSkill::Get`), cached | a weapon that turns the triangle round |

A fight has four sides (`map::BattleInfo`, docs/STANCES.md): 0 and 1 are the two leads, 2 and 3
the units behind them. Each side is set against the opposing lead.

## 2. Weapon exp and weapon rank

**Weapon exp** (`Unit::GetWeaponExp` 0x0052DC54) [high]: one byte per kind on the unit
(`Unit +0xE8`), capped at the class's limit for that kind (`Unit::GetWeaponExpLimit`
0x0052F824, the class sheet's `max_weapon_exp`). Two exceptions, each found by a flag bit that
the game looks up by name once and caches:

- stones: the limit is 0 when the unit, its character or its class carries one flag;
- staves: the limit is raised to at least the rank-B threshold when they carry another flag.

**Rank** (`WeaponLevel::GetLevel` 0x005090A4) [high]: the first of the six thresholds (S, A, B,
C, D, E) that the exp reaches. Below the E threshold the answer is 6, "no rank". [high]

## 3. The weapon-rank bonus

`Unit::GetAttack(item, bool)` 0x00534188 and `Unit::GetHit(item, bool)` 0x00532DC4 add, when
their bool is set and the weapon's kind is below 8, the `WeaponBonus` row of that kind at the
unit's rank: the attack column to attack, the hit column to hit [high]. The status and item
windows (`map::ItemMenu::Draw`) always pass 1 [high].

**In a fight the bool is "not at a triangle disadvantage"** [high for the code]: the fight passes
`(triangle cell >= 0)`. So a unit at a disadvantage **loses its whole weapon-rank bonus** for that
fight, on top of the triangle penalty (`Side::CalculateDetailHit` 0x0034909C,
`Side::CalculateDetailAttack` 0x003499D4, `Side::GetSimplePower` 0x00525680, and the same in
`map::CannonCalculator::Calculate`). The item window can therefore show a higher attack and hit
than the forecast does at a disadvantage. [med for "shows": the windows were not run]

## 4. The triangle in a fight

All of this runs in `map::BattleInfo::Calculate` 0x0034A074, which is called by the real fight
(`map::SequenceBattle`), the map's battle preview (`map::(anonymous)::ProcSequence::UpdateInfo`),
the AI's simulator (`AIBattleSimulator::Calculate`), the arena and the AI's pair-up choice. So the
forecast and the fight use the same numbers. [high for the callers, med for which one is the
on-screen forecast: named, not run]

**1. The cell** (`map::BattleInfo::CalculateDetail` 0x003475BC, at 0x00347A6C) [high]: when the
side has a unit and a weapon and the opposing lead has a weapon, the side's cell is
`WeaponInteract` matrix [the side's kind][the opposing lead's kind]. Otherwise nothing is stored.

**2. Reversing weapons** (same function, 0x00347AB4 and 0x00347B04) [high]: a side whose weapon
has the reversing flag is marked (`BattleSide +0x28` bit 13). Then, for every side:

| side reverses | opposing lead reverses | cell becomes |
|---|---|---|
| no | no | unchanged |
| yes | no | cell x (-2) |
| no | yes | cell x (-2) |
| yes | yes | unchanged |

So one reversing weapon in the fight **turns the triangle round and doubles it**; two cancel.

**3. Damage and hit** (`Side::CalculateDetailAttack` 0x00349A60, `CalculateDetailHit` 0x00349128)
[high]: with a cell other than 0, the game takes the rank of **the unit that has the advantage**:
the side itself when its cell is positive, the opposing lead when it is negative. It adds that
rank's `WeaponInteract` (attack, hit) pair times the cell. So:

- at an advantage you gain your own rank's numbers;
- at a disadvantage you lose **your opponent's** rank's numbers (and your own rank bonus, section 3);
- with a reversing weapon both are doubled.

Numbers against a follow-up side (2 or 3) are 0, as in docs/STANCES.md: the triangle never
matters there. Attack is also skipped when the side's flag 0x40 is set (meaning not traced).
The hit is a 16-bit number, floored at 0 later in the same function. [high]

Quirk [med]: an advantaged unit with no rank in that kind (exp below the E threshold) reads rank
row 6, which is not a row: it is the first two cells of the matrix. In the shipped matrix those
are sword-against-sword and sword-against-lance, so such a unit would get no damage and a small
hit change. Only a unit with no exp in its weapon's kind can reach it.

**Cannons** (`map::CannonCalculator::Calculate`) repeat the same lookup, reversal and rank
scaling with their own copies of the code and their own cache; not rewritten. [high for the
shape]

## 5. Cross-check against docs/tracks/rules/RULES.md

| RULES.md line | Code says | Verdict |
|---|---|---|
| Three pairs: sword and tome beat axe and bow; axe and bow beat lance and dagger; lance and dagger beat sword and tome; partners neutral | the matrix is data; the shipped matrix has exactly these cells, staff and stone neutral (checked again 2026-11-11, values not copied; docs/TABLES.md) | **confirmed** |
| The bonus follows the attacker's weapon rank | the bonus follows the rank of the unit **with the advantage**, in both directions: a disadvantaged unit's penalty is its opponent's rank row | **refuted as worded**: right for the side with the advantage, wrong for the one without |
| Rank table E/D +5 hit ... S +2 damage +20 hit, same numbers negative at a disadvantage | the shipped `WeaponInteract` rank rows equal the table (checked 2026-11-11, values not copied); the sign comes from the cell, so the numbers are symmetric | **confirmed** |
| The asterisk is not a second rule | the code has one more rule the wiki table does not show: at a disadvantage the unit also loses its own weapon-rank bonus (`WeaponBonus`) | **new rule** (not an asterisk reading; the wiki may mean something else) |
| A dual weapon reverses the pair's direction | a weapon with one item flag reverses the cell, and doubles it; two such weapons cancel. Which weapons carry the flag is item data, not read here | **confirmed, with the doubling** |

For options: an option that changes the triangle should change the cell (step 1 or 2), not the
rank lookup, or the disadvantaged side's rank-bonus loss would no longer match.

## 6. What is rewritten, what waits

Readable C in `src/readable/battle/` (`triangle.h`, `triangle_tables.c`, `triangle_battle.c`;
registry: config/readable/functions.csv). Overrides replace the game function in shadow/readable
mode; helpers are the pure part of a bigger function that also writes memory, and return what the
game would write. The guest function still called is `unit::Item::ToData` (a reader: loads and
compares only).

| Address | Game function | Readable | Kind | Host diff | Tier 2 (2026-11-11) |
|---|---|---|---|---|---|
| 0x0019B97C | ItemSubKind::Get(int) | item_subkind_record | override | 0 mismatches | ABI-ONLY |
| 0x001A8090 | WeaponBonus::Get(ItemKind::Type) | weapon_bonus_record | override | 0 mismatches | ABI-ONLY |
| 0x001A80D4 | WeaponLevel::Get(void) | weapon_level_record | override | 0 mismatches | CLEAN |
| 0x001D77B8 | WeaponInteract::Get(void) | weapon_interact_record | override | 0 mismatches | CLEAN |
| 0x005090A4 | WeaponLevel::GetLevel(int) | weapon_rank_of_exp | override | 0 mismatches | ABI-ONLY |
| 0x0052F824 | Unit::GetWeaponExpLimit | unit_weapon_exp_limit | override (3 caches: gives up while any is cold) | 0 mismatches | GAVE-UP (cold caches) |
| 0x0052DC54 | Unit::GetWeaponExp | unit_weapon_exp | override (gives up with the limit) | 0 mismatches | GAVE-UP (cold caches) |
| 0x00534188 | Unit::GetAttack | unit_weapon_rank_attack | helper (the rank-bonus region) | 0 mismatches | not run (helper) |
| 0x00532DC4 | Unit::GetHit | unit_weapon_rank_hit | helper (the rank-bonus region) | 0 mismatches | not run (helper) |
| 0x003475BC | map::BattleInfo::CalculateDetail | triangle_side_lookup, triangle_after_reverse | helpers (cell, reversal; cache: gives up while cold) | 0 mismatches | not run (helper) |
| 0x00348FF0 | map::BattleInfo::Side::CalculateDetailHit | triangle_hit_bonus | helper (triangle part and the bool) | 0 mismatches | not run (helper) |
| 0x00349880 | map::BattleInfo::Side::CalculateDetailAttack | triangle_attack_bonus | helper (triangle part and the bool) | 0 mismatches | not run (helper) |

**Host differential test** (`python src/readable/battle/tests/triangle_diff.py`, `check_all` rows
`triangle-diff` and the slow `triangle-diff-long`): the stance test's method and ARM interpreter.
The game's code runs from extracted/text.bin, the readable C on the same made-up memory; for
helpers, the game's code region is run and what it stores is compared (for the two Side regions,
`Unit::GetHit` / `GetAttack` are stubs, and the bool they receive is compared too). Result: 13
functions x 400 cases (seed 20261111) and x 1500 cases (seed 7), 0 mismatches. `--plant` makes 18
small wrong changes to the sources one at a time (a comparison, an index, a sign, a column, a
cache test, the reversal factor, the advantaged unit, the follow-up test ...): **18 of 18 caught**.

**Waiting:**

- The writers: the stores of `CalculateDetail`, `CalculateDetailHit`, `CalculateDetailAttack`
  (project rule F-017: no readable writer until H6/H8 are green on Fates). The helpers already
  compute what they would store.
- `Unit::GetAttack` / `Unit::GetHit` as whole overrides: they call the stat functions
  (`GetStrImpl`, `GetTechImpl`, ...), which are not rewritten and fill caches of their own.
- `map::CannonCalculator::Calculate` (its own copy of the triangle), `GrowSequence::WeaponLevelUp`,
  the drawing (`WeaponLevelDrawer`), `Job::CanEquipFromSubKind`.

## 7. Tier 2 (3dsrecomp verify, 2026-11-11)

See the dated line in docs/PORT_PLAN.md for the run. Per function:

`python tools/readable/verify.py --rom "Fire Emblem Fates - Special Edition (USA).cci"` on all 28
overrides (the whole-game library build 317 s): **0 mismatches**, `readable-verify: OK (18
ABI-ONLY, 4 CLEAN, 4 GAVE-UP, 2 UNSAMPLED)`. The seven triangle overrides:

| Address | Readable | Verdict | Why |
|---|---|---|---|
| 0x001A80D4 | weapon_level_record | CLEAN | same registers and memory |
| 0x001D77B8 | weapon_interact_record | CLEAN | same registers and memory |
| 0x0019B97C | item_subkind_record | ABI-ONLY | same r0; only r1 differs (a scratch register the calling convention lets a function clobber) |
| 0x001A8090 | weapon_bonus_record | ABI-ONLY | same r0; only r1 differs |
| 0x005090A4 | weapon_rank_of_exp | ABI-ONLY | same r0; only r2, r3 and flags differ |
| 0x0052F824 | unit_weapon_exp_limit | GAVE-UP | verify's memory has every one-time cache cold, so only the fallback (the original) ran |
| 0x0052DC54 | unit_weapon_exp | GAVE-UP | the same caches, through unit_weapon_exp_limit |

None UNSAMPLED (the two UNSAMPLED of the run are the stance totals, as before). A smoke test, not
a proof: one made-up state per function. The two GAVE-UP functions stay covered by the host
comparison (section 6), which runs them with warm and cold caches. Registry statuses were not
changed (no `--update-status`), as for the stance run.
