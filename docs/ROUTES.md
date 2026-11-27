# Route letters: which of A, B, C is which campaign

**In plain words.** The game keeps the files of its three campaigns in folders named A, B
and C. Until now we only guessed from file names that A is Birthright, B is Conquest and
C is Revelation (docs/DECISIONS.md F-009). The game's own code now confirms it: one byte
of the save data holds the current route (0, 1 or 2); a small function turns that number
into the folder letter (0 = A, 1 = B, 2 = C); and the "buy another route" menu, which
stores the same number in each of its three items, labels item 0 "Birthright", item 1
"Conquest" and item 2 "Revelation" in the game's English text. Everything else the code
does with the route agrees.

**Verdict: A = Birthright, B = Conquest, C = Revelation. Confidence: high.**
Re-check it on your own dump with `python tools/fates/routes.py` (prints every step,
exit 0 = confirmed; about 10 s). `config/game.json` `route_folders` was already right and
is unchanged.

Confidence tags as in the plan: **[high]** read in the code and checked by the script,
**[med]** good evidence, **[low]** a guess.

## The evidence chain

All addresses are from `config/functions.csv` (the game's own symbol map); routes.py
finds them by name and decodes the instructions itself, so it fails loudly if the code
is not what this page says.

| # | What the code does | Where | Conf. |
|---|---|---|---|
| 1 | The current route is one byte, `GameUserData+0x2E`. The script commands `RouteGet` / `RouteSet` read and write it; `RouteSet` ignores values of 3 and up. The chapter-6 script calls `RouteSet` after its route choice. | `(anon)::RouteGet` 0x3B0874, `(anon)::RouteSet` 0x3B0884 | high |
| 2 | `Route::GetDirectoryName(Route::Type)` indexes a 3-entry string table: 0 -> "A", 1 -> "B", 2 -> "C". | 0x41F1BC, table 0x62624C | high |
| 3 | Every per-route path is built with `GetDirectoryName(GameUserData+0x2E)`: `Person::Load` and `Person::Deserialize` (`GameData/Person/%s/%s.bin.lz`, falling back to `GameData/Person/%s.bin.lz`), `map::Dispos::Load` (`GameData/Dispos/...`, same fallback), `event::ScriptLoadRoute` / `ScriptFreeRoute` (`Scripts/%s/%s.cmb`), `Mess::FileLoadRoute` / `FileFreeRoute` / `IsFileExistRoute` (`m/<letter>/...`). So **the folder letter is the route byte**: route 0 reads folder A, 1 reads B, 2 reads C. | 0x44A808, 0x44A0FC, 0x39ED9C, 0x42422C, 0x424168, 0x3D1874, 0x3D179C, 0x3D1984 | high |
| 4 | The route purchase menu (`link::ec::pcsroute ... ProcFromMainMenuSequence::TopMenu`) makes three items, storing Route::Type 0, 1, 2 at item+0x38 next to the labels `MID_EC_...ルートA`, `...B`, `...C`. `TopMenu::MenuItem::BuildAttribute` passes item+0x38 to `ContentsUtil::IsOnDeviceRoute(Route::Type)`. The labels' English text (m/@E, read at run time) names Birthright, Conquest and Revelation in that order. **This ties Route::Type to the campaign names independently of any file name.** | 0x3F6AD0, 0x3F69F4 | high |
| 5 | `StaffRoll::Create` opens `GameData/StaffRollDataC.bin` when the route byte is 2 and `GameData/StaffRollDataAB.bin` otherwise: route 2 is the campaign with its own credits; 0 and 1 share theirs. | 0x503C84 | high |
| 6 | `ProcEpilogue::SettingWord` (and `ProcEpilogue::Draw`) use an extra label family ending in 透魔 only when the route byte is 2. The castle screen's per-route labels with the same word (`CastleLowerDrawer::SetupCardInfo`) are, in English, the Revelation emblem texts; the ones with 白夜 and 暗夜 are the Birthright and Conquest emblems. | 0x33C534, 0x33CEB4, 0x1FE9AC | high |
| 7 | The two sides. The castle lottery has a "white" and a "black" item (`TopMenuWhiteItem`, `TopMenuBlackItem`): the white one is unavailable on route 1, the black one on route 0, both are open on route 2. `TalkConst::GetWindowTextureRoutePath` picks `TalkWindowW` for route 0, `TalkWindowB` for route 1 and the plain window for route 2. The chapter-6 choice script (`Scripts/P006.cmb`) passes labels `..._SELECT_A`, `_B`, `_C` to `RouteBranchDialog`, whose English text is defend the white kingdom / fight with the black kingdom / refuse both, and `RouteBranchDialog` adds the third item only when `ContentsUtil::IsOwnedRoute(2)`. In the game's own text the white side is Hoshido and the black side Nohr (e.g. the butler's search-result labels `..._ルート_白` / `_黒` / `_透`). | 0x3C7060, 0x3C6DE4, 0x503FF0, 0x3ABA98 | high (consistent with 4) |
| 8 | Chapter data agrees: chapters with `route_mask` 1 are exactly the 26 `CID_Annn`, 2 the 26 `CID_Bnnn`, 4 the 26 `CID_Cnnn`; `next_chapter[r]` walked from `CID_<L>007` stays on that letter for 23 steps to `CID_ENDING` for each r. (Equal chapter counts: the counts alone cannot tell the routes apart.) | GameData.bin Chapter table | high |

Steps 2 + 3 say "folder letter = route byte"; step 4 says "route byte 0/1/2 =
Birthright/Conquest/Revelation"; steps 5-7 are independent checks that agree (route 2 is
the odd one out with its own credits and epilogues; 0 and 1 are the two kingdoms).

## Route::Type

| Value | Folder | Campaign | Side (game's own words) |
|---:|---|---|---|
| 0 | A | Birthright | the white kingdom (Hoshido) |
| 1 | B | Conquest | the black kingdom (Nohr) |
| 2 | C | Revelation | neither |

The same order is used by `Chapter.next_chapter[3]` (index = Route::Type, in
`ChapterComplete`; `required_chapter[3]` has the same shape in the data, not checked in
code), by `ContentsUtil::*Route(Route::Type)` (purchase and mount of the
route data), `Movie::GetFilePath` (`A/`, `B/`, `C/` sub-folders), `Origin::IsRoute`
and `castle::cut::GetRouteChar` (returns 'A', 'B', 'C').

## Chapter.route_mask

`Spot::Rebuild` (0x3D314C) and `Spot::UpdateSpot` (0x3D2CFC) build the world-map list
with `Chapter.route_mask & (1 << route byte)`. So **bit n set = the chapter is on route
n**: bit 0 (1) = Birthright, bit 1 (2) = Conquest, bit 2 (4) = Revelation. [high]

| Value | Records | Which |
|---:|---:|---|
| 7 | 16 | all routes: `CID_A001`-`A005`, `CID_X001`-`X006`, `CID_E000`, `CID_M001`-`M004` |
| 1 / 2 / 4 | 26 each | one route: `CID_<L>006`-`<L>028` and `CID_<L>Y01`-`<L>Y03` for L = A, B, C |
| 5 | 8 | Birthright and Revelation: `CID_X007`-`X014` |
| 6 | 8 | Conquest and Revelation: `CID_X015`-`X022` |
| 0 | 12 | never listed: `CID_NONE`, `CID_A000`, `CID_P006` (the choice), `CID_ENDING`, `CID_Z000`/`Z001`, `CID_CASTLE0`-`5` |

Note for docs/TABLES.md: chapter 6 is per route (`CID_A006` mask 1, `CID_B006` mask 2,
`CID_C006` mask 4, each with only its own `next_chapter` slot set), so the shared prologue
is A000-A005 plus the choice (`CID_P006`, mask 0); "A000-A006 the shared prologue"
there should read A000-A005. The data files under `GameData/Person/` and `Scripts/`
without a route folder are the shared ones; the loaders above try `<letter>/` first and
fall back to the root.

`ChapterComplete` (0x1B64D8) takes the next chapter as `next_chapter[route byte]` of the
current chapter. [high]

## Experience is per difficulty, not per route

The plan asked which route has the harsher experience rule. In the code, none does:
`Unit::GetExpDamage`, `GetExpDestroy`, `GetExpDance` and `GetExpRod` read
`GameUserData+0x2D` (the byte the `DifficultyGet` script command returns) to pick the
`ExpTable` row, and never the route byte. [high] A harder experience curve on one
campaign, if players see one, comes from that campaign's difficulty or from the
`ChapterSetExpMode` script command (stored in the map state, used by the castle, `M00x`
challenge maps and versus scripts, not by a route), not from a route check.

## Other code that reads the route byte

48 functions read `GameUserData+0x2E` right after `GameUserData::Get` (a scan of every
ARM function for that pair, the same test as `route_byte_loads` in routes.py). Besides the ones above: `MainSequence ... Ending` (three endings),
`ChapterTitleSequence::Create`, `CutInMachine::PushCutIn`, `ProcAcceShop::FirstAccePresent`,
`Unit::AddChapterReliance` and the support menus, `link::PlayReport::Commit`,
`SharedTexture::SetRouteFromUserData`, `event::Informal::GetRandomItem` (castle items
by route), and the castle `People` / `cut` code (`castle::cut::GetRoute`,
`InitBuildingDispos`). `GameUserData::IsRouteOrigin(Origin::Type)` falls through into
`Origin::IsRoute(route, origin)`: route 0 excludes origin 2, route 1 excludes origin 1,
route 2 excludes nothing. With the lottery (the black item sets 2), origin 1 = white
side, 2 = black side. [med] Used for arena enemies, prisoner scouting, the castle's
random food and gemstones, and the class-change list.

## What this unblocks, and what it does not

- Option keys and tests may now name routes by letter (F-009's condition is met for the
  mapping itself). Birthright = route byte 0 = folder A is the campaign of the play
  checks (F-007).
- Not checked here: menu names for the difficulty and the Casual/Classic rule (F-007
  asks for them before an option key is written), and anything on other editions (the
  single-route carts may number routes the same way; re-run routes.py on such a dump).

## Where the facts came from

The owner's dump (code.bin, the RomFS message archives and GameData.bin) and our own
code (`tools/fates/routes.py`). No community tool was used for this page; community
docs (Paragon's FE14 Chapter definitions, as cited in docs/TABLES.md) also list
next-chapter slots in Birthright/Conquest/Revelation order, which agrees.
