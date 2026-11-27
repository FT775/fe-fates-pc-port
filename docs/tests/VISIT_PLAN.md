# Visit plan: the playable screens, in order (F-039 step 2, round 45)

**For the owner.** This page joins [SCREENS.md](SCREENS.md) (the not-yet-reached game functions grouped by screen)
and [HUBS.md](HUBS.md) (where each screen visit can start) into one plan for the scripted visits. Host only: no game,
no robot, no build was run to write it. Nothing here counts as done until the owner says ok (F-037).

**Read F-040 first.** After F-039 was approved, the owner said "go lean" (F-040, 2026-11-19): F-039's full
screen-by-screen testing shrinks to a quick check of the main screens. So this page has two parts: the **lean quick
check** (what the next round should do, 8 visits) and the **full list** (all 33 menu screens, kept for reference and
for any screen the owner or the robot later finds broken).

## The count that defines "every playable screen"

| | screens |
|---|---|
| Menu screens, one visit each (the HUBS.md table rows, without the owner question) | 33 |
| Battle map (with its parts: commands, trade/items, pair up, gimmicks, dragon veins, AI, battle scene, event talks) | 1 |
| **Every playable screen** | **34** (35 if the owner puts the castle invasion aftermath in scope) |
| Already opened on screen by an existing route from a packed save | 17 (16 menu screens + the battle map) |
| Already passed as an F-039 visit (labelled visit that returns, save then load matching) | 0 |
| Left to visit | 33 menu screens (16 copy presses from an existing route, 13 need a short new walk, 2 need a declared cheat poke, 2 need new real play); the battle map is passed by the existing chapter routes staying 0 bad |

Not screens, so not counted: **Data tables** (103 not reached; used by every screen, no screen of its own) and
**Event script commands** (149; reached by playing the chapter whose script calls them). Both stay with the weekly
replay / chapter routes. The battle-map parts are reached by playing chapters, not by a menu visit: the 77 packed
chapter saves and the existing routes cover them.

How SCREENS.md rows map to the 33 menu screens: HUBS.md splits three SCREENS rows in two (Prep sub-menus into
sub-menus plus trade/convoy, Title into title plus avatar creation, Chapter flow into world map plus challenge maps),
so 30 SCREENS in-scope screen rows give 33 visits. The "not reached" number of a split row is shared by its halves.

## The lean quick check (next round: 8 visits, F-040)

The main screens a player passes in every playthrough, all from saves and presses we already have (HUBS.md [high]).
8 kept routes is also the F-039 #5 weekly cap.

| # | Visit | Hub (packed save) | Copy presses from | Frames (both halves) [low] | Not reached here |
|---|---|---|---|---|---|
| 1 | Castle top menu: each item once | `bt-ch9-clear` | any castle route | 7,000 | 900 (shared building code) |
| 2 | World map: move over each entry, back | `bt-ch9-clear` | every chapter route | 6,000 | 130 (shared with challenge maps) |
| 3 | Unit status / lists: each page | `bt-ch8-support` | `bt-ch8-options` | 6,900 | 104 |
| 4 | Preparations: each sub-menu once, Inventory > Trade / Convoy | `bt-ch8-support` | `bt-ch8-support`, `bt-ch6-castle` | about 10,000 (one route for both) | 202 |
| 5 | Options: every line, DOWN only | `bt-ch8-support` | `bt-ch8-options` | 6,900 | 81 |
| 6 | Title / new game: difficulty and mode lists, each A then B back | `new-game-empty` | `new-game` | about 8,000 | 150 (with avatar creation) |
| 7 | Save then load (castle save, title > Continue) | `bt-ch9-clear` | every chapter route | 9,500 | 72 |
| 8 | Mid-battle save and resume | `bt-ch8-support` | `opt-t5-bsave-base` + `opt-ch8-reload` style reload | 9,800 | 21 |

Robot time [low], at 0.006 s a frame on 6 lanes plus about 18 s of Python per run: about 64,000 frames = 6.4 min
plus 16 runs x 18 s = 4.8 min, so **about 11 min for one copy, 22 min for the two copies** (determinism check).
New code needed first: the small save-then-load compare script (save, load, save again: the two saves' files equal
byte for byte, and `markers.game_state` equal before and after; HUBS.md watchdog table). The battle map is already
opened by every chapter route and needs no new visit.

## The full list, in order (most not-reached functions per minute of visit first)

Minutes = robot run time of the visit and its reload half at the rates above (frames x 0.006 s + 18 s Python per
run), one copy. The real work is finding the presses (HUBS.md: about 3 to 6 visits an evening). Hub: **have** = an
existing route already opens it (copy its presses); **walk** = existing save, short new walk; **look** = probably an
existing late save, but one look at its Build list first; **poke** = new hub from a declared cheat-track poke (F-019,
a `cheat-*` visit, never a parent); **real play** = no save has it.

| # | Screen | Not reached | Visits | Hub (packed save) | Frames [low] | Minutes | Per minute | Hub status |
|---|---|---|---|---|---|---|---|---|
| 1 | Castle: menus, unit list, shared building code | 900 | 1 | `bt-ch9-clear` | 7,000 | 1.3 | 692 | have (the 900 must be split by building menu; many rows fall to the building visits below) |
| 2 | World map (chapter flow) | 130 (shared) | 1 | `bt-ch9-clear` | 6,000 | 1.2 | 108 | have |
| 3 | Extras / support log (museum, music, support viewer; movie playback out) | 125 | 1 | `bt-ch26-clear` or `new-game-empty` | 6,000 | 1.2 | 104 | walk |
| 4 | Accessory shop | 157 | 1 | `bt-ch9-clear` (build it in the visit) | 12,000 | 1.8 | 87 | walk |
| 5 | Prison (empty menu) | 142 | 1 | `bt-ch9-clear` (build it) | 11,000 | 1.7 | 84 | walk (a prisoner needs a Capture: new play [low]) |
| 6 | Unit status / lists / unit viewer | 104 | 1 | `bt-ch8-support` | 6,900 | 1.3 | 81 | have |
| 7 | Private quarters (My Room; petting out) | 117 | 1 | `bt-ch9-clear` | 9,000 | 1.5 | 78 | walk |
| 8 | Prep sub-menus + prep trade/convoy | 202 | 2 | `bt-ch8-support` | 14,500 | 2.6 | 76 | have |
| 9 | Mess hall | 125 | 1 | `bt-ch9-clear` (build it) | 12,000 | 1.8 | 69 | walk [low: a meal may need food stock] |
| 10 | Building placement / move / remove | 87 | 1 | `bt-ch8-clear`, `bt-ch9-clear` | 7,000 | 1.3 | 67 | have |
| 11 | Options / settings | 81 | 1 | `bt-ch8-support` | 6,900 | 1.3 | 63 | have |
| 12 | Title / new game / mode + avatar creation | 150 | 2 | `new-game-empty` | 13,000 | 2.5 | 60 | have |
| 13 | Tutorials / guide | 75 | 1 | `bt-ch8-support` | 7,000 | 1.3 | 58 | walk |
| 14 | Hot spring | 94 | 1 | `bt-ch19-clear` .. `bt-ch26-clear` [low] | 11,000 | 1.7 | 55 | look |
| 15 | Reclass / promotion | 73 | 1 | `bt-ch10-clear` (Master Seals, confirmed); `rv-ch26-clear` Heart Seal [low, not confirmed in that save] | 7,500 | 1.4 | 54 | walk |
| 16 | Save, suspend and load | 72 | 1 | `bt-ch9-clear` | 9,500 | 1.6 | 46 | have (single-player bookmark: open question) |
| 17 | Supports C to A | 63 | 1 | `bt-ch8-support`, `bt-ch19-clear` | 8,000 | 1.4 | 45 | have |
| 18 | Lilith's temple | 60 | 1 | `cq-ch15-clear` / `cq-ch16-clear` | 10,000 | 1.6 | 38 | walk [low: which save has the menu] |
| 19 | Staff / rod store (MagicCardShop) | 60 | 1 | `bt-castle-shop`, `cq-ch10-clear` | 10,500 | 1.6 | 36 | have |
| 20 | Arena | 57 | 1 | `bt-ch9-clear` (build it) | 14,000 | 2.0 | 28 | walk |
| 21 | Marriage / S support | 36 | 1 | `bt-ch19-clear` + support-value poke | 9,000 | 1.5 | 24 | **poke** |
| 22 | Castle difficulty / mode change | 25 | 1 | any castle save [low] | 6,000 | 1.2 | 21 | look (B, never Yes) |
| 23 | Mine / farm springs | 31 | 1 | `bt-ch19-clear`+ [low] | 11,000 | 1.7 | 18 | look |
| 24 | Mid-battle save and resume | 21 | 1 | `bt-ch8-support` | 9,800 | 1.6 | 13 | have |
| 25 | Game over | 17 | 1 | `bt-ch8-support` + Corrin HP 1 poke | 7,000 | 1.3 | 13 | **poke** |
| 26 | Smithy (forge) | 17 | 1 | `bt-castle-ore`, `bt-castle-forge` | 10,000 | 1.6 | 11 | have |
| 27 | Armory / shop | 11 | 1 | `bt-ch6-clear`, `bt-castle-forge` | 12,000 | 1.8 | 6 | have |
| 28 | Statue | 8 | 1 | `bt-ch9-clear` (build it) | 9,000 | 1.5 | 5 | walk |
| 29 | Lottery shop | 5 | 1 | `bt-castle-ore` | 9,000 | 1.5 | 3 | have (fixed clock: same prize every time) |
| 30 | Fortune teller | 17 | - | none known | - | - | - | **real play** [low: not on any build list seen yet] |
| 31 | Challenge maps | (shared with #2) | - | none known | - | - | - | **real play** [low: look at a late world map first] |

Totals for rows 1 to 29: **31 visits, about 272,000 frames, about 46 min of robot time for one copy** (about 92 min
for two copies), covering about 3,045 of the 4,115 in-scope not-reached functions by screen name (the real gain will
be lower: many rows sit behind choices a single visit does not make). At the F-039 #5 cap of 8 kept routes a week
that is 4 weeks; HUBS.md's 3 to 6 visits an evening gives 5 to 10 evenings of finding presses. **Under F-040 only the
lean quick check above is planned**; the rest is done only if a screen is found broken.

One short look route comes before rows 14, 22, 23 and 30: open the Build list on `bt-ch19-clear` .. `bt-ch26-clear`
and the world-map list on a late Birthright and Revelation save (HUBS.md open points 1 and 2).

## Out (not failed, not on the finish line)

| Group | Not reached | Reason |
|---|---|---|
| Online (multiplayer, Wi-Fi, versus) | 936 | F-039 #2: the port does not run it |
| Castle visiting / castle data / messages / defense setup | 1,040 | F-039 #2 (castle visiting, profile card, message board, StreetPass feed) |
| DLC / eShop purchase | 535 | F-039 #2 |
| StreetPass | 52 | F-039 #2 |
| Castle 3D renderer, people, cameras, cut scenes | 215 | F-008: stays the game's own translated code |
| Live2D petting | 211 | F-008 |
| amiibo | 117 | F-008 |
| Movies (Mobiclip player) | 6 | F-008 |
| Debug menus | 58 | no player screen |
| **Total out** | **3,170** | |

Unknown, not counted either way: castle invasion aftermath (`castle::AfterBattleSequence`, 56; owner question) and
engine/shared/dead (282; mostly reached only through virtual calls).

## Questions and caveats for the owner

1. Castle invasion aftermath (56): offline invasion (in) or visit battle (out)?
2. `castle::anonymous_namespace::ProcAccessory` is counted as castle visiting (out); it may be an offline accessory
   screen. Same question as 1, one line.
3. Some camera classes used outside the castle (`UnitViewerCamera` 12 rows, `FixedCamera`, `HeadCamera`,
   `SideCamera`) were put in the castle 3D renderer (out) by name; the unit viewer is in scope, so a few in-scope rows
   may hide there. The unit-list visit (#6) will show it.
4. Caller/callee-vote rows are first guesses (for example `HomeButton::CloseApplication` voted into save/load, a
   sound stop voted into castle menus). The "not reached" counts above inherit that.
5. Game over and S support need cheat-track visits with declared pokes (Corrin HP 1; one pair's support value at
   Unit +0x11C); the poke paths are not checked yet. Under F-040 they are not planned.

## Counted time (F-027)

This integrate step: cap 15 min, host only, used about 12 min.
