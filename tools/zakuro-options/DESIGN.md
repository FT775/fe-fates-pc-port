# FE options page on Zakuro's Esc menu

ELI5 / ETA: This is the design for a page on the pause menu. It saves switches to a small file. It does not change the game by itself. Four of the switches are settings the game already has; a later piece of the port copies them into the game after a load (docs/OPTIONS_WIRING.md). Nothing was built. Building waits on your OK.

Status 2026-11-13. Design and two patches. No cargo was run. Neither patch was applied to the real engine (`engine/zakuro`); both were checked with `git apply --check` on a scratch copy of the pin's files.

## What it is

Zakuro at pin `c856685cc867bc6d4ac0f765844ca037ae735941` (v0.2.32, MIT). The clone is `tools/zakuro-options/work/`, gitignored (it has 0001 applied). The changes are:

- `patches/0001-fe-options-page.patch`: the page, the file, the mark (2026-11-10).
- `patches/0002-game-option-lines.patch`: on top of 0001. Moves `danger_zone` and `animation_skip` out of the checkboxes and adds a section "The game's own options" with four choosers (`danger_zone`, `hp_bars`, `animation_skip`, `anim_speed`). Each has "The game's choice" (0) first. Tests added.

Esc, then **FE options**. The game stays paused while the page is open, the same way Settings does. Under "The game's own options" the page has two help lines: "Used from the next save load. Your saves keep the game's own setting." and "After loading a save state, load a save once before saving." (docs/OPTIONS_WIRING.md section 5, Zakuro save states).

The page reads and writes our file only:

- `FE_OPTIONS`, or `FEF_OPTIONS` if the first is unset. PLAY is meant to set one of those to the path of `fe14-options.txt` (`port.options_file` in config/game.json).
- PLAY does not set either for play yet (F-010). Until it does, the page says so and writes nothing. PLAY's capture sessions drop both variables, so a capture never sees an options file (tests/test_play.py).
- It never opens Zakuro's `settings.toml`. It never reads or writes a 3DS save. Changing a switch does not rebuild anything.

## The switches

All default 0. 0 means the original game.

The game's own options (patch 0002). These are lines of the game's own options screen (docs/MENUS.md, the `GameConfigData` block, stored in every save). 0 is "The game's choice": nothing is written. A number picks one of the game's own values:

| key | 1 | 2 | 3 | game byte |
|---|---|---|---|---|
| `danger_zone` | Drawn, the game's first style | No effect (the game cannot hide the zone) | | +0xE: 1 -> 0, 2 -> not touched (round 38, OK A T3: every game value draws the zone; docs/OPTIONS_WIRING.md section 1) |
| `hp_bars` | Shown | Hidden | | +0x16: 1 -> 1, 2 -> 0 |
| `animation_skip` | Skipped: fights, supports and dances play on the map | Shown, by the game's own rule (see below) | | +0x8: 1 -> 0, 2 -> 1 |
| `anim_speed` | Always fast | Fast while A is held | Never fast | +0xC: 1 -> 1, 2 -> 2, 3 -> 0 |

`anim_speed` is the game's map movement speed. A faster battle picture is not a game switch and is not on the page. A value past the list's end is 0.

`animation_skip` is one byte that the game reads in two places (docs/MENUS.md sections 2 and 3): `IsDetailBattle` for a fight and `IsDetailSupport` for a support or a dance (the battle sequence picks `IsDetailSupport` when its flags bit 2 is set; `map::SequenceDance::Create` asks it too). So value 1 ("Skipped", byte 0) puts fights, supports and dances on the map. Value 2 (byte 1) is **not** "every fight shown": it asks for the picture, and then the game's own rules still apply, as on its own screen: holding L flips one fight, a unit with the "never" flag stays on the map, and a support or dance shows the picture only when the game's own support-picture switch (option word bit 1) is on. The page's label says "Shown, by the game's own rule" for that reason. The byte's values 2 .. 4 (picture for some armies or units only) are not offered.

How a value would reach the game: the readable library's hook W1 runs right after the game's own save load (`GameConfigData::Deserialize`) or game reset (`Reset`), only when the call is on the global block (`this == *G_GameConfig`, so never on the versus copy every suspend save makes, never at the boot `Reset` that runs before the pointer is stored) and never while a `Serialize` is running, and hands the lines set here to the writers stage's `config_write_options` (gate name `config_options`), which sets them the way the game's own screen does; W2 (the game's `Serialize`, rewritten, again for the global block only) keeps the game's own value in every save, suspend saves included. All of it is off behind the writer gate (armed in source, listed in `FE_WRITERS`, readable mode). A change on the page counts from the next load or game reset. A change on the game's own screen wins until then. Details, fail-closed rules, robot tests: docs/OPTIONS_WIRING.md. Nothing in this folder applies anything.

Display, a checkbox, never in the mark (new drawing code, not built):

- `stance_forecast`
- `growth_display`
- `vein_highlight`

Run, a 0–2 slider, saved for the save slot showing in the pause menu (1–9), and not applied:

- `dual_strike` — game's roll, always, never
- `dual_guard` — game's roll, always, never
- `death_rule` — leave the save, back next chapter, back next turn

The hooks that would make the display and run switches do something are blank.

## Files

`fe14-options.txt`, once a value is not the default. A missing file of all zeros is left missing, so the file is not created until something changes. Writes are a temp file, then a rename. A line this page does not own is kept. A file written by 0001 still reads: its `danger_zone = 1` is now "Drawn", its `animation_skip = 1` "Skipped".

`fe14-options.txt.mark`, next to that file, only if a run switch is not zero. One block per slot. Display keys and the game's own lines are not in it. An all-zero slot is dropped. There is no fingerprint yet: the slot number is Zakuro's slot, not a checksum of the save. The fingerprint waits on the save writer.

The readable library would read `fe14-options.txt` with the same rules as `parse` (a bad value is 0, an unknown line is ignored, the last of two equal keys wins). One list of test lines is meant to be shared by both.

## Tests

In `crates/zakuro/src/fe_options.rs`, under `#[cfg(test)]`. They check: a missing file is all off, a bad value stays off, values are capped, an unknown line is kept, the mark is per slot, a display key does not land in the mark; with 0002 also: a game line takes its list's length and fails to "the game's choice", and a game line never lands in the mark.

Not run. The owner said the Zakuro build is already a solid recomp (2026-11-10). Do not build Zakuro to run these. Run them only if Zakuro is being built for some other reason:

```
cargo test -p zakuro fe_options
```

from `tools/zakuro-options/work`, after the patches are applied. Do not run that until the owner says a Zakuro build is OK.

## Applying

From a clean checkout of the pin:

```
git apply tools/zakuro-options/patches/0001-fe-options-page.patch
git apply tools/zakuro-options/patches/0002-game-option-lines.patch
```

0001 adds `fe_options.rs` and a button plus a window in the existing menu. 0002 changes those two files only. Neither touches `settings.rs`. Undo: `git apply -R` in the reverse order (checked: 0002 reverses cleanly).

These patches are not in the port's patch series (`patches/zakuro/`, F-005). Putting them into the play build is the owner's build OK B in docs/OPTIONS_WIRING.md section 10.
