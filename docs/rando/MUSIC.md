# Randomizer track: music (round 55, F-046)

**For the owner.** This track makes each chapter play a different song from the game's own music. One switch,
**Random music**: off, maps, or maps + battles. **Maps:** each chapter's map song is a random pick from the
game's 18 map songs. In Fates each map song comes with its own battle version (the "(Storm)" / "(Fire)" songs in
the Sound Room), and the game fades between the two, so a new map song also brings its own fight music. **Maps +
battles:** bosses and other named enemies also get a random boss song in place of theirs. In one chapter, units
that shared a song still share one. One seed always gives the same songs. Story scenes keep their own music. The
battle-preparations song, the three final-chapter songs, jingles, voices and sound effects are never changed.
With the switch off nothing changes (old seeds stay byte-identical). All of this is done in the game's data
files: no engine build is needed. Status 2026-11-20: the module and its tests are done (21 tests pass), and a
demo mod passes the mods tool's checks. It is not yet on the in-game page and has had no robot check (the next
integrate round). Nothing counts as done until the owner says ok (F-037). This is our own code, modelled on the
FE8 port's "Random music". No public Fates tool randomizes music.

## 1. How it is called

`tools/randomizer/music.py` (this track's only module):

    plan_music(tables, rng, opts) -> (edits, spoiler_lines)
    run_guards(tables, edits, opts) -> {guard name: {"ok", "detail"}}
    edits_to_files(tables, edits) -> {"romfs/map/config/<CID>.bin": bytes, "tables/PersonChapter.csv": bytes}

- `tables`: a `MusicTables` (`load_tables()` reads the user's own RomFS, read only; the tests build made-up ones).
- `rng`: the run seed text (or a `random.Random`). The track takes its own sub-seed from it (sha256 of tool,
  seed, "music"), then one stream per (purpose, chapter file, cell). No other track's draws move.
- `opts`: `{"music": "off" | "maps" | "maps+battles"}`. The default is `off`, which gives no edits and no files.
  The maps part of a seed is the same whether battles are on or not.

Command line (writes only under `build/`; refuses `mods/` and %APPDATA%/%LOCALAPPDATA%):

    python tools/randomizer/music.py inventory          each chapter's songs, the two pools, what is kept and why
    python tools/randomizer/music.py make --seed S [--music maps|maps+battles] [--out build/rando55/music]

## 2. Where the game picks its music (facts)

Read from the user's own RomFS and the game code's symbol names and listing (local, not tracked):

| What | Where it is chosen | Reader in the code |
|---|---|---|
| Chapter map song | `map/config/<chapter>.bin` (118 files, one per chapter, named like the CID): a one-row sheet `マップ設定` ("map settings") that describes itself. Fields: `自軍BGM` (player_bgm: the map song), `自軍BGMその2` (player_bgm_2: the song after a scene switches it; only C017 has one), `進撃BGM` (advance_bgm: the battle-preparations / base song, `STRM_SYS_BASE_*`, plus a few event songs), then two bytes (BGM switch effect, volume-only) and a pad | `map::sound::Setup` (003998C4) reads field 0. When the flag `S_BMapBGM切り替え` is set (script command `ev::BMapBGMChnageFlagOn`) and field 0 is playing, it switches to field 1. `SetBattleInfo` and `OnFadeInMap` read the two bytes |
| Fight music in normal battles | the map song's own stream: each `STRM_MAP_*` file has 5 channels (map version + battle version), and every one has a `STRM_BTL_*` name in the Sound Room list (`m/@E/Bgm.bin.lz`) | `map::sound::setTrackVolume` fades between the channels |
| Boss / named-unit fight music | `Person` / `PersonChapter.combat_music` (+0x88): 152 units in 98 of the 117 chapter files have one (15 different `STRM_BOSS_*`); no resident Person row has one | `map::sound::SetBattleInfo` (003977DC) reads the unit's Person row +0x88 (it also tests the Leader flag `SPID_リーダー`; that branch is not fully traced) |
| Castle-invasion boss songs | **code**: five `STRM_BOSS_*` labels written inside `SetBattleInfo`, picked by the castle's state | not changed (would need the core) |
| My Castle jukebox song | **code**: `castle::JukeBox::GetBgmLabel` (the player's own pick) | not changed (it is the player's choice) |
| Event scene music | `Scripts/*.cmb`: `ev::BGMPlay "STRM_EVT_..."` etc. (284 script files use it) | not changed |

Story cues: no script command waits for a song to end. The script command names have no BGM wait, only
BGMPlay/Stop/Volume, RBGMPlay/Effect, BMapBGMResume, BMapBGMChnageFlagOn and Enable/DisableBGMCommandPG, so
no scene can hang on a changed song. Scenes that name a map song themselves (the opening battles of chapter 6 on
each route play `STRM_MAP_E3`; the four amiibo maps play `STRM_MAP_ET`) still play that song in the scene; the
map then uses the chapter's new song.

Stream layouts (the channel count in each `.bcstm` INFO block): every `STRM_MAP_*` has 5 channels. Every
`STRM_BOSS_*` and the three finale songs `STRM_MAPEX_*` have 3 channels: one version, no battle version.

## 3. The pools (read from the tables, not a hand-made list)

- **Map pool**: every label that a map config already uses as a map song, that is a `STRM_MAP_*` name, that the
  sound archive (`sound/IRON15_sound.bcsar`) names, and whose stream has the usual map layout. Today that is 18
  songs: A1-A4, B1-B5, C1, C1R (the reversed prologue song), C2, C3, E1, E2, E3, ET, F2. `STRM_MAP_F1` exists but no
  chapter uses it, so it is left out.
- **Battle pool**: every label already used as `combat_music`, by the same rules. Today that is 15 songs: A1-A3,
  B1-B4, C1-C3, E1, and the four amiibo boss songs (Marth, Ike, Lucina, Robin), which the game itself uses on the
  amiibo maps. They count as the game's own boss songs. If the owner would rather keep them on their own maps,
  that is a one-line rule in `pools()`.
- **Kept**: the finale songs (`STRM_MAPEX_*`, chapter 28 of each route), any config whose sheet does not match
  the field list above (none today), and empty fields. A chapter or unit with no song never gets one.

## 4. Cells written

- `MapConfig` (not a registered table; written as whole files under the mod's `romfs/map/config/`): only
  `player_bgm` and `player_bgm_2`. The file is rebuilt from the game's own bytes with the same string-pool rule
  (`tools/tables/tablelib.rebuild`). A rebuild with no change is byte-identical for all 118 files. `advance_bgm`,
  the two bytes and everything else stay as they are.
- `PersonChapter.combat_music` (the mod's `tables/PersonChapter.csv`: file, index, label, combat_music), only for
  rows that already have a song. `Person.combat_music` would go to `tables/Person.csv` the same way, but no
  resident row has one.

A demo (seed `demo55`, maps + battles) changes 100 map-song cells (99 chapters plus C017's after-switch song) and 152 boss songs (252 cells). Every guard passes,
and `mods.py compute` accepts the folder with no errors.

## 5. Guards (each has a test in tests/test_rando_music.py)

1. Off makes no edits.
2. Only the map-song cells and `combat_music` are written. No battle songs are written in `maps` mode.
3. The old values match the game's tables, and a unit with no song never gets one.
4. Only music labels of the right role (map songs for maps, boss songs for battles) that the sound archive names.
   Never jingles, fanfares, voices, system, event, movie or sound-effect tracks.
5. A new song has the same stream layout (channel count) as the one it replaces, so the map/battle fade still has
   its channels.
6. Every chapter that had a map song still has one, and none gains one.
7. In one chapter file, the same old boss song becomes the same new one for every unit.
8. (Round 59, FITS rule) A new song name is never longer than the name it replaces. The in-game core (engine round
   E1, patch 0016) writes the new name over the old one inside the chapter's own file, which has no room to grow, so
   this rule holds on every path: the same seed plays the same music from the in-game page, PLAY RANDOMIZED and the
   command line. Grok's pick (docs/collab/E1_MUSIC_GROK.md, choice A). Effect: the reversed prologue song
   (STRM_MAP_C1R, 12 letters) stays on the Prologue; the four amiibo boss songs (13-16 letters) only replace each
   other; the other 17 map songs and 11 boss songs shuffle as before. Music seeds made before round 59 change.

Also tested: same seed gives the same edits; different seeds give different edits; a rebuilt file reads back
with the new song and the old prep song; files with an unknown layout are kept; real data over 15 seeds × 2 modes.

## 6. For the integrate round (not done here, by the file-ownership rule)

- `tracks.py` / `rando.py` / `ingame.py`: add the option `music: off | maps | maps+battles` (page default: off).
  Call `plan_music(..., seed, o)` and `run_guards`, then merge `edits_to_files` into the run's mod. The romfs files
  are new paths. `tables/PersonChapter.csv` is new unless another track also writes PersonChapter: then merge
  by (file, index) and refuse a cell that two tracks write.
- The robot check (one headless run, own data folder under build/): start a chapter with a changed song, then read
  `map::sound`'s current song name (the 6 × 65-byte name slots at the object `D_006D7F38`+8 points to; the slot `Setup` fills with type 1 should be the map song). Also check one boss fight's song. Not run this round (host only).

## 7. What would need the game core later (engine work, owner OK then)

- The castle-invasion boss songs and anything else whose label is written in the code. The smallest hook: in
  `map::sound::anonymous_namespace::TSound::SetName(name, type)`, swap the name through a small table that the
  randomizer writes beside the save. That one hook would also cover all the table songs at run time.
- The Sound Room / jukebox unlock. The list comes from `GameData/Museum.bin.lz` and `castle::JukeBox::Update`. We
  did not trace whether hearing a song unlocks it (the FE8 port had to guard that). If it does, a random pick could
  unlock a late song early. Checking this is part of the robot round.
- Event scene music (`STRM_EVT_*`) is not shuffled on purpose: it carries the story's mood.
