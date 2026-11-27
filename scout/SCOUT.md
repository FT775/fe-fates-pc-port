# Fates scout: how much of the Awakening port would carry over

Scouting only. Nothing was built, extracted in full, or run. The .cci and the Awakening repo were read-only.
Tags: [high] = checked directly, [med] = good evidence, [guess] = judgement.
The detail notes are in this folder: container-and-code.txt, file-formats.txt, code-mapping.txt, engine-side.txt, community-docs.txt.

## 1. What Fates is on disk

- "Fire Emblem Fates - Special Edition (USA).cci": 2 GiB card, decrypted (NoCrypto). Title 0004000000179800, product code CTR-P-BFZE, internal name "Iron15" [high].
- All three routes are in one game partition. The likely mapping is A = Birthright, B = Conquest, C = Revelation, with A000-A006 as the shared prologue [med]. DLC is not on the card [high].
- Code: .text is 5.3 MB, about 1.5x Awakening, roughly 27.5k functions (Awakening has about 18.8k) [high]. A single program with no .cro modules, like Awakening [high].
- RomFS: 21,880 files, 1.8 GB (Awakening: 7,368 files, 1.1 GB). The biggest parts are sound, movies (.moflex), 3D fields, battle models, Live2D (5,637 files) [high].
- **The big find: the RomFS ships a full symbol map** (debug/name.StackTrace + addr.StackTrace): 26,122 real C++ function names with classes and signatures, for build rev 27274 (2015-11-17). Awakening has nothing like it [high].
- Upstream: Zakuro lists Fates SE USA as Playable and Recompiled. 3dsrecomp ships hints for exactly this dump (the code hash 9677F5445E8DCD01 matches) [high]. Fates also adds act, nfc (amiibo) and qtm (N3DS) services; Zakuro has them in source [med].

## 2. What carries over from Awakening

| Area | Reuse | Notes |
|---|---|---|
| ROM tools (extract_rom, ctr.py, romfs.py, BLZ) | ~100% | Ran unchanged on Fates [high] |
| Container formats: LZ13, IS .bin, message archives, CTPK | ~100% | All 2,736 .bin and all 1,328 message files round-trip byte-identical; LZ13 60/60 sampled [high] |
| .arc archives | ~95% | arc.py needs about 20 lines (data at 0x60, 0x80 member alignment) [high] |
| Textures/models (cgfx.py) | ~0% | Fates uses BCH, not CGFX. The PICA texture codecs in tex3ds.py are reusable [high] |
| Table editor framework (tablelib, gen, codeuse) | ~60-70% | Code reuses; data does not [med] |
| Table layouts (tables.csv, 307 layouts) | ~0% | Every record size changed (Person 0x238 to 0x98, Item 0x38 to 0x68, and so on) [high] |
| Mods tool (mods.py, LayeredFS install) | ~75% | Needs the title ID, the GameData/ paths and route folders made parameters [med] |
| Engine build chain (engine.py, pins, toolchain) | ~85% | Swap constants only [med] |
| PLAY launcher (play.py: saves, backups, settings) | ~85% | Swap constants; extdata ID is already read from the exheader [med] |
| Zakuro patches 0001, 0002, 0005 | ~100% | Game-agnostic [high] |
| Zakuro patches 0003, 0004 (top-screen extras, sounds) | mechanism only | New Fates UI marker tables and sound names are real research [high] |
| Harness, extras, readable staging tools | partial | Hard-coded Awakening addresses; need per-game parameters [high] |
| Library code knowledge (CTR-SDK) | ~50-58% | About half of the SDK functions are byte-identical; labels and HLE stubs carry over [med] |
| Middleware (molive) | ~90% | Exact matches [high] |
| NEX 3.8.3 and Pia | ~5% | New versions. Reuse the stub/HLE strategy, not the code [med] |
| Readable game code (281 overrides) | ~10% direct | 27 map with byte-level confidence (small AI, route, flag, config helpers); fuzzy leads could add ~8%. All big stat getters, damage formulas and most item and unit code have no counterpart [high] |

Overall: about 60-70% of the tooling and pipeline, about 25-35% of the library-level knowledge, and under 20% of the game-level readable code [guess].

A bonus in the other direction: the Fates names can label about 1,500 Awakening functions that are still called func_XXXXXXXX, through exact byte matches (e.g. func_0011C77C = nn::cx::UncompressLZ) [high that they exist, med on the yield; only unique matches are trustworthy].

## 3. What is new work

- **BCH (H3D) tool**: about 10.7k files, which is all portraits, UI, unit and battle models. This is the biggest asset gap. Community tools (SPICA forks) document the format [high].
- **Fates table layouts**: Person, Job, Item, Skill, Chapter, Belong, Terrain (per chapter), Dispos (unit record 0x8C), plus about 18 table types Awakening lacks (castle, forge, dining, arena, AI data...). Paragon's FE14 YAML gives field maps to cross-check, but it is GPL-3.0, so take facts only [high].
- **Game systems that are new or rewritten**: stance-based Attack/Guard Stance pair-up, weapon triangle and weapon data, dragon veins, the 3D castle (My Castle, castle::), Live2D petting scenes, amiibo, three route flows, child paralogues (X chapters) [med on the list, high that the code is new].
- **Fates-only formats**: Live2D (.moc, .mtn, about 440 functions of Cubism runtime; licence check needed), .aac voices (1,026), .dspadpcm.bcstm, 3D field models, .moflex movies, a new GameData header layout (pointers and counts, no labels) [high on presence].
- **Readable layer**: most of it from scratch, but with real names for every function, so it should go much faster than Awakening did [med].
- **Engine layer**: Fates UI marker tables and bottom-screen sound names for the top-screen extras [high].

## 4. Engine parameterization list

Move these into one config/game.json (or a small games table) read by every tool [med on the shape]:

- tools/engine/engine.py: TITLE_ID / TITLE_HEX, PROGRAM_NAME, PACKAGE, PORT_DIR, env names (FEA_PORT_DIR, FEA_GAME_DIR), DEFAULT_ROM, the check_rom title test and its message, the src/main.rs title check, hints_file() name, selftest fixtures.
- tools/play/play.py: TITLE_ID, PRODUCT_CODE (CTR-P-BFZE), ROM_SIZE (same 2 GiB), ROM_SHA256 (owner records the new one), GAME, SHORTCUT_NAME, STANDALONE_NAME, env names (FEA_PLAY_DIR, FEA_HARNESS_DIR), DEFAULT_CONFIG rom path, CAPTURE_LIB name, user-facing strings.
- Zakuro patch 0003: turn game_ui::for_game into a list with one entry per title (keep the per-title gate).
- Zakuro patch 0004: menus gate, settings tests, BOTTOM_SCREEN_SOUNDS keyed per title (Fates archive is sound/IRON15_sound.bcsar; sound names unverified [guess]).
- tools/harness/{build,harness,headless}.py: LIB_NAME, TITLE, guard address.
- tools/mods/mods.py: title ID, data/ to GameData/, route folders, help text, Awakening-only checks.
- tools/extras/usa_extras.py, tools/readable/stage.py: addresses per game.
- tools/analysis/funcmap.py and fingerprint.py: segment constants and output paths as arguments.
- tools/assets (romfs.py, survey.py, roundtrip_all.py): ROMFS path, product-code check, extension classes.

## 5. Risks

- The symbol map is for rev 27274. It lines up with 25,653 of 27,324 function starts, but spot-check names before back-porting them to Awakening [med].
- A game update .cia changes the code hash, and then the bundled 3dsrecomp hints no longer apply. Refuse updates, as the Awakening harness does [high].
- BCH is about half of all files. A byte-identical BCH rebuild may be harder than the CGFX texture swap was [med].
- Table meanings (columns, flags, any growth obfuscation) need code evidence from Fates; that is a full re-run of the TABLES.md method [high].
- N3DS flags and new services (qtm, nfc) may hit runtime paths Awakening never used [med].
- Live2D needs a renderer on PC and a Cubism licence check [high that it is needed].
- Route-letter mapping is inferred from file names, not checked in code [med].
- Community tools are GPL. Copying code would make the port GPL; take facts only [high].
- Engine builds were never run from this repo's chain for Fates; the owner's recompile was outside it [high].
- Other Fates editions (Birthright/Conquest carts, other regions) have different title IDs and no bundled hints [guess on IDs].

## 6. Effort estimate, relative to Awakening [guess unless stated]

- **(a) Plays as a PC port**: about 0.2-0.3x of Awakening's effort. Upstream already supports the dump and the build chain carries over; the work is the constants refactor, a new ROM hash, and checking N3DS-only services. The top-screen extras add maybe 0.3x of what they cost for Awakening, because the UI tables are new.
- **(b) Moddable finish line (FE8-style)**: about 1.0-1.3x of Awakening. Messages and text mods work on day one. Against that: a new BCH tool, every table layout re-derived, ~1.5x the code, three routes, and new systems. The free symbol map is the main thing that keeps this from being 1.5-2x.
- **(c) Owner minutes**: about 0.5-0.8x of Awakening. Same manual steps (record the ROM hash, a few in-game checks per milestone), but most naming is given and decomp.me hand-compiles should be needed less because names and signatures are known.

## 7. Recommended first steps when Fates starts

1. Finish Awakening first (D-013), then do the per-game config refactor inside the Awakening repo, so Awakening keeps passing its tests with config/game.json.
2. Back-port Fates names to Awakening: import the symbol map, match unique byte-identical functions, spot-check 20, and add the names to the Awakening registry. This pays off for both games.
3. Create the Fates repo from the shared tooling; record the ROM SHA-256; extract; run funcmap with Fates constants and load all 26k symbols into the function registry.
4. Get "plays as a PC port": engine build with Fates constants, PLAY launcher, refuse updates, a headless boot check.
5. Text mods first (messages already round-trip), then the arc.py fix, then a BCH tool for portraits and UI.
6. Re-derive the core tables (Person, Job, Item, Skill, Chapter, Dispos) from Fates code, cross-checked against the community field maps as facts.
7. Readable batches in the Awakening order (stats, battle, items, map, AI, menus), using the real names, then the Fates-only systems (stances, castle, routes).

> Note (2026-11-10, integration): the Awakening port's `tools/tables/codeuse.py` (named in the table-editor row above) was not carried over. Its Fates replacement is `tools/tables/evidence.py`, which reads offsets from the functions the game's own symbol map names (docs/TABLES.md). The scout text above is kept as written.
