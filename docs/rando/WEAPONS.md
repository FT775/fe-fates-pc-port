# Randomizer track "weapons" (weapon stats, weapon traits, better enemy weapons)

Module: `tools/randomizer/weapons.py`. Tests: `tests/test_rando_weapons.py`. Built in the randomizer track
round after F-046 ("build the other missing parts too": docs/RANDOMIZER.md listed "Weapon might / hit / weight /
uses" and "Weapon traits" as not built, and "Better enemy weapons" as on / off with no chance setting).
Host only: no game was started, no robot job, no engine build. Not wired yet (section 4).

## For the owner (plain words)

This adds the FE8 port's three weapon switches to Fates. **Weapon stats** moves each weapon's might, hit, crit
and avoid a little (default: might up to 2 up or down, hit up to 10, crit up to 5, avoid up to 5), and the uses
of staves by up to 2. Fates weapons never break and have no weight, so "uses" only means staves and there is no
weight switch. **Weapon traits** gives a weapon one extra power with a chance you pick (0-100%): +2 to one stat
while equipped, effective against armor, beasts, dragons or fliers, reverse weapon triangle, or +10 to +20 crit.
**Better enemy weapons** gives each enemy weapon a chance (0-100%) to become a stronger weapon of the same kind and
range. Yato, the legendary weapons, the royals' and other personal weapons, stones and breaths are never touched.
Plain weapons (bronze, iron, steel and the like) never get a trait. Prices stay. Every switch off = the original
game, byte for byte. Grok (creative lead) picked the defaults: small numbers, four traits, 25% when on, and the
"same rank" upgrade until a robot check proves that rank-up is safe.

## 1. Facts (from the tables and the game code notes; no game values here)

| Fact | Where it comes from |
|---|---|
| Item cells: `might` +0x1F, `hit` +0x20, `crit` +0x22, `avoid` +0x24, `dodge` +0x26, `uses` +0x1E, `range_min/max` +0x28/+0x29, `effective` +0x34 (JCID_ bits), `stat_bonus` +0x38 (s8[8], added while equipped), `flags` +0x0 (ISID_ bits) | docs/TABLES.md "Item" (high: each read by the named game function) |
| Fates weapons have `uses` 0 (they never break); only staves have uses; one staff has the "infinite uses" flag | the user's own Item table, read on the host (counted, not copied) |
| No weight cell. The closest are `speed_mod_player` / `speed_mod_enemy` (follow-up speed) and the stat bonus | docs/TABLES.md; not changed by this track |
| A staff's `might` is its heal power and its `hit` the status-staff hit; both kept | Unit::GetItemHealPower reads the heal value from the item (docs/TABLES.md) |
| The effects a trait uses are plain Item flags the game already reads for other weapons of every kind: reverse triangle (Dual weapons, Calamity Gate), brave (Brave weapons, Lightning, Snake Spirit), double might on the counter (Venge weapons, Ink Painting), heal each turn (Spirit Katana, Mikoto's Yumi) | the Item table's flag lists per kind (host read) |
| `Unit::CanItemEquip` with "check own rank" compares the unit's weapon exp with the item's rank; generic enemies' PersonChapter weapon exp is 0 for almost every carried weapon (5,696 of 5,794 in-scope carried weapons are above it), yet they wield them in the original game, so the game raises their exp from the placement (`spot::SetDisposUnitItem` reads the WeaponLevel thresholds) | docs/EQUIP_USE.md, docs/WEAPON_RANK.md, docs/TABLES.md line "WeaponLevel"; the count is a host read [med for the raise: not run live] |
| DisposUnit `item_N_flags` bit 0 marks the unit item (kept by the game for some item flags); this track treats it as "the enemy drops it" and leaves those slots alone | docs/TABLES.md DisposUnit [low for "drop"] |

## 2. What is built

`plan_weapons(tables, rng, opts) -> (edits, spoiler_lines)` and `check_weapons(tables, edits, opts) -> guards`.

| Option | Values (default) | What it does |
|---|---|---|
| `stats` | off / on (**off**) | might, hit, crit, avoid of every weapon this track may touch; uses of staves |
| `variance` | per stat (**might 2, hit 10, crit 5, avoid 5, uses 2**); 0 = that stat untouched; max 10 / 40 / 30 / 30 / 10 | the FE8 port's variance: a coin flip for the direction, then 0..variance; bounds might 1-25, hit 40-120, crit 0-60, avoid -30..30, uses 1-30, widened by an original value outside them. Weapons with the "no crit" flag (bronze) keep crit 0 |
| `traits` | chance 0-100 (**0**; `True` = 25) | one roll per weapon that may take a trait, then one trait it does not already have: +2 to one stat (str, mag, skl, spd, lck, def, res) where its bonus is 0 or less; effective against armor / beasts / dragons / fliers (only groups the Item table already uses; only when the weapon has no effectiveness); reverse triangle; crit +10/+15/+20 (only when crit is 10 or less) |
| `wild_traits` | off / on (**off**) | adds brave, double might on the counter, heal 10% each turn. Grok dropped them from the default list ("a run-winner, not a spice"; "they hurt when an enemy rolls them") |
| `enemy_upgrade` | chance 0-100 (**0**; `True` = 25) | one roll per weapon an unscripted enemy carries (the enemies track's scope: team 1, Enemy / Reinforce groups, story chapters, never Conquest 9/16 or Revelation 8/13, never named or script-named units) |
| `upgrade_rank` | same / next (**same**) | `same`: the new weapon has the same rank; `next`: up to one rank up (next-rank weapons first). Bosses always keep their rank |
| `enemies_edits` | the enemies track's edits or none | applied first; this track's DisposUnit edits name the value after them as `old` |

The upgrade's new weapon: same kind, same range (min and max), magic only if the old one was, an ordinary shop
weapon (price, `legal_player_weapon` 1, not personal / legendary / enemy-only / chapter-only / precious), not an
"effective only" weapon (Armorslayer style), one the unit's (new) class may hold, and at least one might point
stronger (power = 10 x might + hit + crit, after the stat plan). Drops, weapons the unit cannot use anyway (drops),
stones and special weapons are never changed.

Never touched by any switch: Yato in every form, the `ISID_神武器` legendaries, precious and can't-remove weapons,
personal weapons (`*専用` flags other than male / female / dark-mage-line / enemy-only), weapons the player never
owns (`legal_player_weapon` 0 and not enemy-only: the S-rank route weapons, amiibo and downloadable ones), stones
and breaths. Enemy-only weapons (Kukris and the like) get the stat changes so they stay in step with the player's,
but never a trait.

Seeds: `sub_rng(seed)` is SHA-256 of (tool version, seed, "weapons"); every draw has its own sub-stream (stat +
item, trait + item, upgrade + unit + slot), so turning traits or upgrades on never moves the weapon stats, and no
other track's switch moves anything here.

Guards (each from the edits alone): `only_allowed_cells`, `kept_items_untouched`, `stats_in_bounds_one_trait`,
`no_broken_weapons`, `enemy_upgrades_legal` (scope, chain, kind, range, rank rule, holdable, stronger, drops kept).

Real tables, seed w1 (host, counts only): stats on = 637 values on 230 weapons and staves; traits 25% = 35 weapons;
upgrades 25% = 478 of 5,055 enemy weapons (same rank) or 925 (next); every guard PASS.

| Test | What it proves |
|---|---|
| `test_off_means_no_edits`, `test_off_no_edits_real` | every switch off = no edit (existing seeds byte-identical) |
| `test_bounds_and_variance` | every stat within its variance and bound; bad options refused |
| `test_kept_items_never_touched`, `test_yato_and_legendaries_kept_real` | Yato, legendaries, personal, route S-rank, stones, infinite staff untouched; staves only uses |
| `test_traits_only_on_weapons_with_a_power` | plain weapons (incl. bows' own flier effectiveness) get none; all four default traits occur; no brave without wild |
| `test_enemy_upgrades_legal`, `test_drops_and_unusable_weapons_kept` | scope, same kind, rank rule (bosses same rank), drops kept |
| `test_on_top_of_the_enemies_track`, `..._real` | works on the enemies track's edits (classes on), chain checked |
| `test_guard_catches_bad_edits` | 14 hand-made bad edits each fail a guard |
| `test_guards_pass_many_seeds_and_options`, `test_many_seeds_all_guards` | many seeds and option mixes, every guard PASS (fake and real tables) |
| `test_mods_tool_accepts_the_folder` | the mods tool reads the Item and DisposUnit CSVs with no error |

`python tools/randomizer/weapons.py make --seed S [--stats on] [--traits N] [--wild-traits on] [--enemy-upgrade N]
[--upgrade-rank same|next] [--with-enemies on]` writes this track alone as a mod folder under
build/rando_weapons/out (inspection only; the wiring round does the real merge).

## 3. The Seal edition's and other tables (F-047)

Nothing original-only is hard-coded: every base value, rank, kind, range, price, flag and effectiveness group comes
from the tables object passed in (`randolib.Facts` or `enemies.EnemyTables`); the IDs used are ISID_ / JCID_ flag
names the game looks up by name. The effectiveness trait only offers groups the table's own Item rows already use.
The upgrade scope is the enemies track's (its chapter rules are that track's to generalise).

## 4. How to wire it (the wiring round; this track edits no shared file)

1. `rando.py` / `tracks.py`: after the items and enemies tracks, call
   `weapons.plan_weapons(enemy_tables, weapons.sub_rng(seed), dict(opts, enemies_edits=enemies_edits))` and
   `check_weapons` with the same opts; fail the seed when a guard fails.
2. Merge: Item rows (this track's cells; the items track writes other Item columns, stock), DisposUnit cells
   (apply the enemies edits first, then these; `old` must match).
3. Options: `--weapon-stats on/off`, `--weapon-variance might=2,hit=10,...`, `--weapon-traits N`,
   `--wild-traits on/off`, `--enemy-upgrade N`, `--upgrade-rank same/next`; the existing `--enemy-weapons on/off`
   stays the enemies track's gear shuffle. rules.json `tracks.modules` gets `"weapons"`.
4. In-game page (ingame.py): rows "Weapon stats" (off/on), "Weapon traits" (off/5..100%), "Better enemy weapons"
   becomes a chance (off/5..100%). RANDOMIZER.md rows "Weapon might / hit / weight / uses" and "Weapon traits" ->
   "on the page"; weight: "not in Fates (no weight cell)".
5. Spoiler: append `spoiler_lines` (stats, traits, upgrades).

## 5. What needs the core or a robot later

- **Rank-up upgrades** (`upgrade_rank next`): one robot check on an early chapter (read the upgraded enemies' weapon
  exp at Unit+0xE8 and that they attack with the new weapon, as the enemies track's robot check did) before it may
  become the default. Until then "same" ships (Grok's rule). Bosses stay inside their rank even after.
- **Help text**: the item description is text and stays the original; a trait shows only in the spoiler log. Text
  edits (a line such as "Randomizer: reverse triangle") would need the message archive writer.
- **Drop bit**: the meaning of `item_N_flags` bit 0 as "drop" is [low]; one robot read would confirm.
- **Not built, on purpose**: shop prices follow stats (Grok: no, as the FE8 port), dodge (crit avoid) variance,
  follow-up speed modifiers, magic damage, life drain, after-battle stat drops, gold steal, "leaves 1 HP".

## Credit

Ideas after the FE8 port's randomizer (our sister project; its variance rule follows the Universal FE Randomizer's
idea, MIT): no code taken. Public Fates tools: facts only. Defaults: Grok (answer kept under build/weapons_track).
