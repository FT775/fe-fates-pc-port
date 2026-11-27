# Options list v1

ELI5 / ETA: This is the full first list of switches, matched to the FE8 port where that makes sense here. Nothing is built. Turning one on does not change the game until its hook exists. That is the February–March rewrite, not December.

Status 2026-11-11. Design only. Shape from docs/tracks/STANCE_AND_REVIVE.md and the Awakening options note. FE8's list is the Sacred Stones port README (danger zone, fast-forward, unbreakable weapons, casual, growths on a button, a few bug fixes, HP bars, cheats for gold, growths, and experience). Our defaults are all off. FE8 leaves fast-forward and bug fixes on. We do not copy that.

File rules, already agreed: one `key = value` file, unknown keys stay, display never marks a save, run options are a mark per slot, off during capture, Esc menu page, changing a value does not rebuild.

| key | values | class | needs | unblocked by | risk |
|---|---|---|---|---|---|
| `growth_display` | 0 off, 1 show rates on the status screen | display | a draw path. No writer | options page exists; the draw path is the rewrite | a preview that changes a stat is a bug |
| `danger_zone` | 0 off, 1 show while a button is held | display | a draw path. Must not write the game's own zone byte | same | a poke of the game byte that is not restored sticks |
| `animation_skip` | 0 off, 1 skip the battle picture | display | the picture path. The result must still happen | same | skipping the picture must not skip the hit |
| `anim_speed` | 0 game, 1 faster picture, 2 fastest picture | display | the same picture path. Not a writer | same | FE8's fast-forward default is not ours. Default stays 0 |
| `hp_bars` | 0 off, 1 bars and a low-HP warning | display | a draw path | same | numbers on the bar must be the game's HP, not a second copy |
| `stance_forecast` | 0 off, 1 show ally strike and ally block before confirm | display | two readers, blank. Must not call either applier | one battle the robot has replayed | a forecast that fills the gauge is a bug |
| `vein_highlight` | 0 off, 1 mark a vein tile | display | a draw path | a vein has been seen | highlighting must not fire the vein |
| `support_preview` | 0 off, 1 points to the next rank | display | a reader. Must not add a point | a support has been opened | Awakening's child-stat preview is cut here (below) |
| `growth_mode` | 0 the game's roll, 1 fixed | run, mark | the growth roll and the level-up applier, blank | those hooks replay-clean, planted-bug test, undo log | the roll must still advance. Do not enable on a guessed formula |
| `casual_mode` | 0 leave the save, 1 back next chapter | run, mark, including an already-started save | the game's own death-rule flag, blank | the flag writer, both save kinds, planted-bug test, undo log | off must not rewrite the save |
| `death_rule` | 0 leave the save, 1 back next chapter, 2 back next player phase | run, mark, including an already-started save | the same flag. 1 and `casual_mode` must not both be on | same, plus a reading that names the revive value | an overlay that revives a unit the game already removed is rejected. Phoenix forces Normal in the retail game; we do not invent that drop until the flag writer exists |
| `dual_strike` | 0 the game's roll, 1 always, 2 never | run, mark | the strike applier, blank | one follow-up the robot has replayed, plus the two gates | no percent slider until the roll is read |
| `dual_guard` | 0 the game's roll, 1 always, 2 never | run, mark | the guard applier, blank | one pair the robot has replayed, plus the two gates | same |
| `exp_rate` | 0 the game's amount, 1 double, 2 none | run, mark | the experience applier, blank | that hook, plus the two gates | not per route. Experience rows are picked by the difficulty byte only (docs/tracks/rules/RULES.md) |
| `gold_rate` | 0 the game's amount, 1 double, 2 none | run, mark | the gold writer, blank | that hook, plus the two gates | a multiplier, not infinite gold. Infinite gold is a cheat and waits |
| `enemy_phase` | 0 the game's speed, 1 faster, 2 fastest | display | the enemy-turn picture path. A line that waits for a button still waits | the same picture path as `anim_speed` | must not skip a choice the game is waiting on |
| `skill_banners` | 0 off, 1 show the skill name when it activates | display | a draw path beside the battle. Must not change the roll | one skill activation the robot has replayed | a banner that fires the skill is a bug |
| `support_rate` | 0 the game's amount, 1 double, 2 none | run, mark | the support-point writer, blank | that hook, plus the two gates | must not grant a rank by itself. The conversation still needs the two units together |
| `keep_game_options` | 0 the game's defaults each new game, 1 remember animation, text speed, and the other rows of the game's own options screen | display | a side file only. Never the 3DS save | the options page can read those rows without writing the save | writing them into the save is a writer, and this key is not that |

Every row defaults to 0. Off is the original game. FE8 leaves fast-forward and its bug fixes on. We do not copy that.

## From the FE8 Helpers and Game fixes pages

Read 2026-11-11 from the Sacred Stones port's `docs/port/PLAYING.md` (Helpers, Game fixes, and the settings-file key list). Added above when the same idea has a Fates system to hook. The rest:

- Whole-game fast-forward, and its sound. If Zakuro already has a speed key, do not add a second one. `anim_speed` and `enemy_phase` are the picture paths, not a second emulator speed.
- True hit. FE8's forecast shows one number and rolls another. No reading here shows Fates does that. Do not copy the key. Add it only if a reading shows the forecast and the roll disagree.
- Arena odds. FE8 shows the opponent before the wager. No reading here shows Fates hides that. Same rule: add it only after a reading.
- Convoy from any unit's menu. Fates already opens the convoy in the castle. A map-menu convoy is a new rule, not a helper. It waits until the castle convoy has been opened once, and it would be a run key if it is added.
- Rewind to the start of the turn. FE8 uses a save the game already writes each turn. No reading here shows Fates writes that save. Do not build a second save system for this list.
- Skip skirmishes. That removes fights. Birthright's between-chapter fights are the route difference the rules sheet already names. Not a display helper. Not in v1.
- Ruin floor select, Myrrh's look, and a second game's classes. Another game. No Fates equivalent.
- Faster supports is `support_rate`, above. Not a separate key.
- Remembering the game's own options screen is `keep_game_options`, above. It does not write the 3DS save.
- Option sets (three saved bundles). After the page exists. A file beside the options file, not a new hook. Not needed to turn one switch on.
- Window size, scaling, smoothing, fullscreen, and key rebinding. Those are the emulator's, not the game's. Zakuro already has a settings file. Do not put them in `fe14-options.txt`.

Game fixes, all cut for v1:

- Early-kill experience, promoted-enemy levels, healers targeting full HP, canto after a cancelled trade, a weapon that backfires at high luck, one chapter's staff drop, a character's personal buff, late joiners' weapon ranks, armed dancers, a third promotion class. Each is a named FE8 chapter, character, or rule. No reading here shows the same result in Fates. A fix is a later row, after a reading names the Fates case. Do not copy the key.
- Pair Up, class skills, and personal skills. Those are already this game's rules. An option that adds them would invent a second copy.
- Smarter enemies. A new AI, not a fix. After both finish lines, if it is asked for.

## Cut, and why

- Unbreakable weapons. FE8 has weapon uses. No reading here has shown a uses field. An option that stops breakage has nothing to hook. If a later reading finds a uses counter, add the key then.
- Experience or gold per route. The code picks experience by difficulty, not by route. A per-route key would invent a split the game does not have. Gold has no per-route formula on a page that names this game.
- FE8's named bug fixes (a freeze, a softlock). Those are another game. No Fates bug is named yet. A fix is a later row, after a reading, not a copied key.
- Fast-forward left on, and bug fixes left on. FE8's defaults. Ours stay off so off is the original game.
- Child-stat preview, route picker, petting scenes, castle renderer, amiibo. Already out. Castle tables may become spreadsheets. That is data, not a switch.
- Randomizer. After both finish lines.
- A percent slider for stance rates. The scale is unread.

## Owner minutes

None for this file. The first look is the display switches, about 5 minutes, after a draw path exists, and not in the capture session. The run keys are not in that look.
