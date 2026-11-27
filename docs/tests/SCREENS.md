# Screens: the unreached game functions grouped by screen (F-039 step 1, round 45)

F-039 makes playable screens the finish line: every in-scope screen below needs one labelled visit that returns,
with save then load matching. This page is the list of screens, built from the game functions the robot's
recordings have not reached yet. Host only: no play, no game run, no build. Names and addresses come from our own
symbol files; no game bytes or disassembly are tracked.

## The numbers

| | count |
|---|---|
| Game functions (`all_game_functions.csv` rows that `config/functions.csv` tags `library=game`) | 15,965 |
| Reached by the robot (round 43, `final_reached_game_functions.csv`) | 8,342 |
| **Not reached, grouped here** | **7,623** |
| of which in scope | 4,115 |
| of which out (F-008 / F-039 #2 / debug) | 3,170 |
| of which unknown (no screen found, or owner question) | 338 |

The task brief said about 7,950 unreached: that is 16,312 minus 8,342 = 7,970, but 347 of the 16,312 rows are
tagged library (SDK, zlib, Live2D runtime and so on) or unknown in `config/functions.csv`, so the game-only
unreached count is 7,623.

## How each function got its screen

1. **Name / class match** (most rows): ordered word rules on the symbol name and class, for example `ProcSpa` is the
   hot spring, `ProcJail` the prison, `link::ec` the eShop/DLC, `castle::msgdata` and `DataStore` castle visiting.
   High confidence when the class itself matches, medium when only the function name does.
2. **Call graph**: for a function no rule matched, its direct callers (counted twice) and direct callees (once)
   vote with their screens, from `build/decomp/method-b/static.pkl` (call targets only). Up to 4 passes.
   Medium when 75% or more of at least 2 votes agree, low otherwise. Generic groups (data tables, event runtime,
   script commands, battle scene, help) do not vote.
3. **Module hint** (a handful): the batch module (B4 map, B6 event, ...) when nothing else answered. Low.
4. Anything left is **engine/shared/dead**, with the reason: no direct callers and address taken (reached only
   through a virtual or function-pointer call: most of them), no callers at all (likely dead), or callers without
   a screen.

The same classifier ran over the reached functions too, so "reached already" uses the same screen names.

## One row per screen

| screen | not reached | reached already | status | reason / note | confidence (of the not-reached rows) |
|---|---|---|---|---|---|
| Castle: armory / shop (weapons, items) | 11 | 13 | in scope |  | high (9 high, 2 medium, 0 low) |
| Castle: accessory shop | 157 | 19 | in scope |  | high (146 high, 5 medium, 6 low) |
| Castle: staff/rod store (MagicCardShop) | 60 | 1 | in scope | building name is a guess from the class name | high (60 high, 0 medium, 0 low) |
| Castle: lottery shop | 5 | 16 | in scope |  | high (5 high, 0 medium, 0 low) |
| Castle: mess hall (dining) | 125 | 26 | in scope |  | high (114 high, 7 medium, 4 low) |
| Castle: arena | 57 | 2 | in scope |  | high (52 high, 3 medium, 2 low) |
| Castle: private quarters (My Room) | 117 | 15 | in scope | room menus in scope; the petting/Live2D part is out (F-008) | high (109 high, 8 medium, 0 low) |
| Castle: hot spring | 94 | 22 | in scope |  | high (91 high, 2 medium, 1 low) |
| Castle: prison | 142 | 18 | in scope |  | high (124 high, 3 medium, 15 low) |
| Castle: statue | 8 | 3 | in scope |  | medium (6 high, 2 medium, 0 low) |
| Castle: Lilith's temple | 60 | 25 | in scope |  | high (57 high, 1 medium, 2 low) |
| Castle: smithy (forge) | 17 | 52 | in scope |  | medium (10 high, 5 medium, 2 low) |
| Castle: mine / farm / resources (gemstones, food) | 31 | 31 | in scope |  | high (26 high, 5 medium, 0 low) |
| Castle: fortune teller (Fortune) | 17 | 0 | in scope |  | high (15 high, 2 medium, 0 low) |
| Castle: building placement / arrange | 87 | 92 | in scope |  | high (85 high, 2 medium, 0 low) |
| Castle: difficulty / mode change | 25 | 3 | in scope |  | high (25 high, 0 medium, 0 low) |
| Castle: menus, unit list, shared building code | 900 | 772 | in scope |  | high (789 high, 35 medium, 76 low) |
| Castle: invasion / visit battle aftermath | 56 | 0 | unknown | may be offline invasion (in) or visit battle (out); owner question | high (54 high, 0 medium, 2 low) |
| Castle: 3D renderer, people, cameras, cut scenes | 215 | 719 | out | out (F-008: Live2D/petting, 3D castle renderer, movies, amiibo stay translated code, off the finish line) | high (178 high, 24 medium, 13 low) |
| Castle visiting / castle data / messages / defense setup | 1040 | 177 | out | out (F-039 #2: online/StreetPass/DLC/SpotPass/castle visiting the port does not run) | high (1003 high, 16 medium, 21 low) |
| Supports: talk, rank-up (Reliance) | 63 | 102 | in scope |  | medium (48 high, 12 medium, 3 low) |
| Support log / Extras: museum, movie list, music, support viewer | 125 | 29 | in scope | movie playback itself is out (F-008) | high (120 high, 5 medium, 0 low) |
| Marriage / children / family | 36 | 61 | in scope |  | medium (24 high, 6 medium, 6 low) |
| Save, suspend and load (file menu, bookmark) | 72 | 193 | in scope |  | medium (41 high, 21 medium, 10 low) |
| Mid-battle save and resume (map suspend) | 21 | 39 | in scope |  | medium (2 high, 15 medium, 4 low) |
| Game over | 17 | 1 | in scope |  | medium (8 high, 9 medium, 0 low) |
| Title / new game / avatar creation / mode choice | 150 | 310 | in scope |  | high (135 high, 7 medium, 8 low) |
| Options / settings | 81 | 59 | in scope |  | medium (63 high, 6 medium, 12 low) |
| Tutorials / guide / help | 75 | 69 | in scope |  | high (72 high, 3 medium, 0 low) |
| Prep screen sub-menus (sortie: trade, convoy, equip, entrust) | 202 | 351 | in scope |  | high (188 high, 13 medium, 1 low) |
| Reclass / promotion / class intro | 73 | 120 | in scope |  | medium (51 high, 15 medium, 7 low) |
| Unit status / lists / unit viewer | 104 | 296 | in scope |  | high (84 high, 9 medium, 11 low) |
| Battle map: commands and sequences | 322 | 1391 | in scope |  | high (276 high, 11 medium, 35 low) |
| Battle map: trade / items / convoy in battle | 26 | 111 | in scope |  | medium (13 high, 12 medium, 1 low) |
| Battle map: gimmicks / traps / statues / terrain effects | 78 | 141 | in scope |  | medium (36 high, 41 medium, 1 low) |
| Battle map: dragon veins | 1 | 10 | in scope |  | medium (0 high, 1 medium, 0 low) |
| Battle map: pair up / dual | 14 | 139 | in scope |  | medium (7 high, 6 medium, 1 low) |
| Battle map: enemy AI | 87 | 164 | in scope |  | medium (58 high, 25 medium, 4 low) |
| Battle scene (animations, cameras) | 78 | 435 | in scope |  | high (69 high, 9 medium, 0 low) |
| Event script commands (chapters, talks) | 149 | 177 | in scope | called by chapter scripts; reached by playing the chapter that uses them | medium (0 high, 149 medium, 0 low) |
| Event / talk / cutscene runtime | 195 | 527 | in scope |  | high (167 high, 24 medium, 4 low) |
| Chapter flow / world map / encounters (challenge, invasion) | 130 | 237 | in scope |  | medium (86 high, 35 medium, 9 low) |
| Data tables (units, items, skills, classes) | 103 | 304 | in scope | no screen of its own; used by many | high (103 high, 0 medium, 0 low) |
| Live2D petting | 211 | 99 | out | out (F-008: Live2D/petting, 3D castle renderer, movies, amiibo stay translated code, off the finish line) | high (169 high, 20 medium, 22 low) |
| Movies (Mobiclip player) | 6 | 9 | out | out (F-008: Live2D/petting, 3D castle renderer, movies, amiibo stay translated code, off the finish line) | high (5 high, 0 medium, 1 low) |
| amiibo | 117 | 10 | out | out (F-008: Live2D/petting, 3D castle renderer, movies, amiibo stay translated code, off the finish line) | high (114 high, 3 medium, 0 low) |
| Online (multiplayer, Wi-Fi, NEX/Pia, versus) | 936 | 124 | out | out (F-039 #2: online/StreetPass/DLC/SpotPass/castle visiting the port does not run) | high (903 high, 20 medium, 13 low) |
| StreetPass | 52 | 35 | out | out (F-039 #2: online/StreetPass/DLC/SpotPass/castle visiting the port does not run) | high (47 high, 4 medium, 1 low) |
| DLC / eShop purchase | 535 | 84 | out | out (F-039 #2: online/StreetPass/DLC/SpotPass/castle visiting the port does not run) | high (510 high, 11 medium, 14 low) |
| Debug menus (dead) | 58 | 0 | out | debug-only, no player screen | high (50 high, 4 medium, 4 low) |
| engine/shared/dead | 282 | 709 | unknown | no screen found: shared engine code, system/library-like code, or never called | low (0 high, 0 medium, 282 low) |

Out reasons: F-008 keeps Live2D/petting, the 3D castle renderer, movies and amiibo as the game's own translated
code, off the finish line. F-039 #2 lists online, StreetPass, DLC (and with them SpotPass, eShop and castle
visiting) as out, not failed. Debug menus have no player screen.

## Read with care

- **Castle: menus, unit list, shared building code** (900 not reached) is the biggest in-scope group and is not one screen.
  It holds the castle top menu, building top menus, the accomplishments/bonus box, the traveler list and other
  castle menu items. Step 2 should split it by the building menu it opens before writing visits.
- **Castle visiting** includes the castle profile card, epithet/hometown and the castle message board, because they
  only feed visits and StreetPass. If the owner wants the offline parts of the card editor visited, those rows move.
- **Castle: invasion / visit battle aftermath** (`castle::AfterBattleSequence`, 56) is an owner question: it can be
  the offline castle invasion (in scope) or a visit battle (out).
- **Event script commands** (149) are the script calls (`cmvm::CmContext*`) chapters use. They are not a screen:
  they get reached by playing a chapter whose script calls them. Several chapters (cq-ch8 to 13, rv-ch10 to 26,
  bt-ch13) were not in the round 43 trace, so part of this group may already run.
- **Private quarters**: the room menus are in scope; the petting part is out. Petting rows are in "Live2D petting".
- **Staff/rod store** is a guess from the class name `ProcMagicCardShop`; the building is confirmed in step 2.
- Call-graph and module rows (low confidence) are a first guess. A few look wrong by eye (for example two
  `MI_Scout*` items voted into mid-battle save by a single caller). Step 2 corrects rows as visits confirm them.
- **Reached counts for out groups** (online 124, DLC 84, castle visiting 177) are mostly start-up and set-up code
  the game runs at boot or at the castle even when nobody goes online.

## Files

- `build/tests/screens/unreached_by_screen.csv` (gitignored): function, address, class, screen, status
  (in_scope / out / unknown), how_assigned, confidence. One row per unreached game function.
- `build/tests/screens/all_by_screen.csv`: the same for all 15,965 game functions, plus a reached column.
- `build/tests/screens/screen_summary.json`: the totals behind this table.
- `build/tests/screens/group_by_screen.py`: the script (`python build/tests/screens/group_by_screen.py`, host only,
  a few seconds). Reads `config/functions.csv`, `build/decomp/method-a/all_game_functions.csv`,
  `build/decomp/compare/final_reached_game_functions.csv`, `build/decomp/method-b/static.pkl`.

Nothing here counts as done until the owner says ok (F-037).
