# Options list v3

ELI5 / ETA: Four of the switches are already in the game. Turning one on is storing a value the game already reads, which is still a writer, so it stays off until the safety net exists. The rest are listed as display or as a change to the fight. Nothing is hooked.

Status 2026-11-14. v1 file rules still hold (`docs/tracks/OPTIONS_V1.md`). Every port default is 0: off means the save's own options, not a second copy. A display switch never marks a save. A switch that changes results is a run switch and waits on the two gates.

`docs/MENUS.md` section 5 names only `IsDetailBattle` for the picture. The code also uses `IsDetailSupport` for a support or a dance (`docs/collab/reviews/REVIEW_2026-11-14.md`). A wiring of `animation_skip` must set both, or a support fight stays on the picture.

## Built in — no new rule, only a stored byte

The game already has the byte. Applying our value is a writer (F-017). The readers exist. None of these are enabled.

| key | player sees | default | changes results? |
|---|---|---|---|
| `danger_zone` | the enemy's reach, the game's own drawing | 0, leave the save | no. Display. `Update` and `Add` stay the game's |
| `hp_bars` | bars on the map | 0 | no. Display |
| `animation_skip` | the map instead of the battle picture | 0 | not proven. The dice of a fight on the skip path were not read (`docs/MENUS.md`). A support or a dance is the other check |
| `anim_speed` | faster map movement | 0 | no dice found. It does move every later button on a frame-timed route. A route must be recorded at one speed |
| `enemy_phase` | the game has a skip byte. What it skips was not read | 0 | unverified. Do not treat it as display until that reading |

`keep_game_options` is not a game switch. The block is already in every save. A side file may remember it. Putting it back after a load is a writer. Default 0.

## New code — from OPTIONS_V2

| key | kind | player sees | default | changes results? |
|---|---|---|---|---|
| `forecast_hit` | new, reader | shown hit and crit | 0 | no |
| `forecast_strikes` | new, reader | 1 or 2 strikes | 0 | no |
| `triangle_hint` | new, reader | advantage, and whether the rank bonus is kept | 0 | no |
| `vein_who` | new, reader | whether this unit may use a vein | 0 | no |
| `vein_highlight` | new, reader | marks. Must not fire the vein | 0 | no |
| `gauge_display` | new, reader | the gauge points the helper would leave | 0 | no. Must not call `CalculateDual` |
| `stance_forecast` | new, reader | ally strike and block before confirm | 0 | no |
| `growth_display` | new, reader | growth rates on the status screen | 0 | no |
| `support_preview` | new, reader | points to the next rank | 0 | no |
| `skill_banners` | new, reader | a skill name when it activates | 0 | no. Must not call the picture |
| `growth_mode` | new, writer | fixed growths | 0 | yes. The seed and the level still advance |
| `exp_rate` | new, writer | double or no experience | 0 | yes. Not `GainExp` |
| `gold_rate` | new, writer | double or no gold | 0 | yes. Not infinite |
| `dual_strike`, `dual_guard` | new, writers | always or never | 0 | yes |
| `support_rate` | new, writer | double or no support points | 0 | yes. Does not grant a rank by itself |
| `casual_mode`, `death_rule` | new, writers | who comes back | 0 | yes. The two must not both be on |

## What players ask for, and what is cheap

Cited, not a poll. Unverified as "most asked": these are the requests the pages name, not a count.

- 60 frames without the game running twice as fast. The old public codes double the speed. A later thread claims a patch that does not, and some console users crashed in a 3D battle. [GBAtemp, Foxes, https://gbatemp.net/threads/fire-emblem-3ds-games-awakening-fates-echoes-true-60-fps-patches-cheat-codes-without-speedup-all-regions.684737/, read 2026-11-14; the older doubled-speed warning is already in `docs/tracks/EXTRAS_FATES.md`] Do not paste those codes. Zakuro already has in-between frames, and they stay off. This is not the game's speed byte.
- Faster battles, a top screen only, and a higher resolution are features of the Awakening port, not a Fates vote. [https://github.com/Zelkin1/fe-awakening-recomp, read 2026-11-14] Faster battles is the closest public ask to `animation_skip` and `anim_speed`. Those two are the cheap ones: the game already has the bytes. They are still writers, and `anim_speed` breaks a frame-timed route.
- Danger zone, HP bars, and growths on a button are on the Sacred Stones port's list, already used for v1. Fates already has the first two as options. Growths on a button is `growth_display`, a reader, and it is the cheap new one.

Cheap, in order: leave the four built-in bytes alone until the writer gate exists; then `growth_display` and the five forecast readers from v2. Not cheap: 60 frames, experience, gold, the stance rolls, and a death rule.
