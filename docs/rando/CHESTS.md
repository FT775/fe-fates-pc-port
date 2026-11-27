# Chests, villages and talk gifts (round 70 desk work, big goal 1; track "chests")

**In plain words.** In Fates, what a chest, a village or a talk gift gives is not in the game's tables. Each
chapter's event script names the item when it hands it over. This round we read every one of those hand-overs
(read only: nothing is written), set the rules, and wrote the Python that plans a new item for each one. The
game does not use the plan yet. The swap needs one small engine hook at the moment the game hands the item over.
That hook goes in a later engine round, and it needs your OK first. Until then the new option is **off**, it is not
on the page, and every seed makes exactly the same game as before (fingerprints check: PASS, unchanged).

Status 2026-11-24, round 70 (desk work: no game run, no engine build, no script or text file written). Seal of
Flames scripts were read from the installed mod (`play/seal-of-flames/data/mods/0004000000179800/romfs/Scripts`,
over the base game's) and nothing from them is committed. Confidence: [high] = read or counted directly,
[medium] = inferred from counts and context, [low] = a guess to check.

## 1. What the scripts hand over (facts, counted)

How it was read: `tools/randomizer/chests.py` holds a small **read-only** reader for the compiled event scripts
(`Scripts/**/*.cmb`). It reads the function table (header +0x1C), the string pool (header +0x20) and each
function's event header (+8 event type, +9 argument count, +0x14 the arguments). It walks the bytecode with a
fixed operand-length table, and it lists every `ev::` call with the literal strings and numbers pushed before it.
Every function of all 624 base scripts and of Seal of Flames' 726-file layered set walks to its end (0 stopped
early) [high]. That is a heuristic call reader, not a decompiler.

How a call is sorted into a kind:

| Kind | How it is told | Confidence |
|---|---|---|
| chest | the call sits in a map tile event (event type 0x15) whose 5th argument is 10 (the tile event's own x, y come with it) | [medium] kind number from counts and context; [high] that the item is a literal of that event |
| village | a map tile event whose 5th argument is 1 | [medium] |
| talk | a talk event (event type 0x17: two person ids; e.g. Corrin talking to Hinoka in A004 gives a Concoction) | [high] for the A004 case |
| event | any other function (opening, ending, turn events, named sub-scripts): story gifts, paralogue rewards | [high] |
| gold | `ev::GoldGain`, `GoldGainSilent`, `GoldGain2` (money, not an item) | [high] |

The handlers that give items: `ev::ItemGain` (all chests, villages and talk gifts use this one),
`ev::ItemGainSilent`, `ev::ItemGainNoSound`, `ev::ItemGainMessageOnly(NoSound)` (story only: the Yato upgrades,
Ganglari, Draconic Rage, B016's bows, X022's keys), `ev::ItemReplaceForYatonokami` (Yato upgrades) and
`ev::ItemGetRandom` (My Castle's random visits, `Z000`) [high].

### Counts per path (story chapters; a path counts the shared prologue chapters too)

| Path | chest | village | talk | event | gold | of these, changeable (chest + village + talk) |
|---|---:|---:|---:|---:|---:|---:|
| Birthright | 19 | 8 | 2 | 8 | 1 | 20 |
| Conquest | 26 | 7 | 2 | 12 | 7 | 21 |
| Revelation | 44 | 5 | 2 | 10 | 2 | 35 |
| Paralogues (X001-X022; several are route-only) | 5 | 4 | 0 | 21 | 1 | 6 |
| **Fates, all 624 scripts** | 96 | 28 | 2 | 43 | 12 | 76 slots (181 calls in all; 143 are `ev::ItemGain`; 39 chapters have a chest or village) |
| Seal of Flames path (shared + `C006` + R/S/Y chapters it reaches) | 41 | 6 | 4 | 15 | 2 | 36 |
| Seal: other chapters it reaches (A/B chapters on required links) | 23 | 10 | 0 | 4 | 6 | 23 |
| Seal: paralogues | 4 | 0 | 0 | 16 | 0 | 2 |
| **Seal of Flames, 726 layered scripts** | 137 | 33 | 4 | 59 | 13 | 61 slots (246 calls in all; 200 `ev::ItemGain`; 55 chapters with a chest or village) |

(Seal chapters the story never reaches, 115 calls, are out of scope, like the enemy tracks' `scope.story_file`.)
The full lists (chapter, script file, call index, function, handler, kind, item id or `variable`, tile x/y) are in
`build/r70/chests/calls_fates.json` and `calls_seal.json` (gitignored; remake with
`python tools/randomizer/chests.py list --game fates|seal --out build/r70/chests/calls_<game>.json`).

A slot is one (chapter, original item) pair. Two calls in one chapter share a slot when they hand over the same
item: `A004` (the Hinoka talk, one call for each Corrin) and `B026` (one chest, two branches) [high].

## 2. The rules

1. **Only `ev::ItemGain` calls of the kinds chest, village and talk change** (option `chest_kinds`, default all
   three). Event gifts (story scenes, paralogue rewards) stay in the first version: they are the scenes the
   story names, and a few (X020's Missiletainn, X021's rewards) belong to a person.
2. **Story and key items never change and are never placed.** The list in `chests.STORY_ITEMS`: Yato and all six
   of its forms, Ganglari, Corrin's Dragonstone, Draconic Rage, Missiletainn, the door and chest keys. Also every
   item the items track will not place (`items.ItemView.placeable`: precious, chapter-only, divine, can't-remove,
   key, instant-gold, enemy-only, downloadable or personal flags). That keeps the gold bags (3000G-20000G), Boots,
   the legendary weapons in chests (Excalibur, Aurgelmir, Bifröst) where they are. (The Seal mod's Siegfried,
   Brynhildr, Fujin Yumi and Raijinto are event gifts, so rule 1 keeps them anyway.)
3. **Same band, like the castle rewards** (`items.ItemView.band`): a weapon becomes a weapon of the same type and
   rank, a staff a staff of the same rank (healing or not), an item one of the same sort. Stones and seals have no
   band, so Master, Heart and Partner Seals, Dragonstone+ and Beaststone+ stay.
4. **No repeat inside one chapter**, when the band has room. Another item than the original is picked whenever one
   fits.
5. **Deterministic per seed.** The track's own sub-seed is SHA-256(tool version, seed, "chests", its options). Each
   slot draws from its own stream (chapter, original item), so turning another track on never moves a chest.
6. **Every path and story** (F-047): the module reads the scripts of whatever RomFS view it is given (base, or base
   + mod) and takes its scope and routes from the passed rules (`rules.json` / `seal_rules.json`). No chapter list
   is hard-coded.

Guards (`check_chests`, all green on 12 Fates seeds in the tests and on the Seal seed `c70s`):
`only_changeable_calls`, `story_and_key_items_kept`, `same_band`, `no_repeat_in_chapter`,
`one_entry_per_chapter_item`.

## 3. Where the game hands the item over (the engine lookup point)

| What | Where | Confidence |
|---|---|---|
| The script name `ev::ItemGain` is bound to `anonymous_namespace::ItemGain(cmvm::CmContext*, int, const char*)` at **0x003B0768** (104 bytes) | the registration code's literal pool at 0x0042B62C holds 0x003B0768 followed by the string `ev::ItemGain` | [high] |
| What it does | `push`; keeps ctx (r5), the unit argument (r6) and **the IID string (r4 = r2)**; `Item::IsExist(iid)` 0x003D1108, stop if 0; `UnitPool::Get` 0x004F6174; `unit::Item::New(item, iid)` 0x00419880 builds the item from the same string; `map::SequenceHelper::ItemGain(proc, unit, item, 1)` 0x00361124 adds it to the unit (or the convoy: `Transporter::Add`) and shows the "got" window | [high] (code read on the host) |
| A chest | `map::ProcSequence::TreasureBox` 0x0037ECC8 uses a key or Locktouch, finds the tile event at the unit's place (`map::trick::Enumerator`) and runs it (`event::Poke::Trigger`). The tile event is the script function that calls `ev::ItemGain` | [high] |
| The other handlers | `ItemGainSilent` 0x003A94A4 and `ItemGainNoSound` 0x003AA52C have the same shape. Only story calls use them, so the hook leaves them alone | [high] |

**The hook (design only, no build this round).** One entry hook on `anonymous_namespace::ItemGain` 0x003B0768.
At entry, r2 is a pointer to the IID string in the script's string pool. The hook reads it, looks up
(current chapter, IID) in the run's chest table, and, when found, sets r2 to the address of the **new item's own
IID string in the resident Item table** (GameData, which `fates_rando` already finds in memory). Then the original
function runs unchanged. `Item::IsExist` and `unit::Item::New` both read the new string, so the window, the sound
and the convoy rule all behave as for a normal gift. No guest memory is allocated, and no script byte is changed.

- **New file:** `crates/zakuro-core/src/fates_rando_chests.rs` (patch 0031 or the round's next number): the
  table `{chapter: {orig IID: new IID}}` (`chests.engine_table`), read from the run's plan.json `chests` list by
  `fates_rando_file` when a run starts or a save is read, and `on_item_gain(ctx)` that does the swap. The chapter
  comes from the chapter placement file the session last served (`fates_rando_session` already sees each
  `GameData/Dispos/<chapter>` read), checked against GameUserData's current chapter.
- **How the hook is entered (pick in the engine round):** (a) Zakuro's existing code-change path: while a run with
  a non-empty chest table is active, write a reserved `svc` word over the first instruction at 0x003B0768.
  `recompiled::Library::check` then marks that one function stale, and the interpreter runs it, the way
  `cheats.rs` handles a cheat that changes code. The `svc` handler in `kernel/svc.rs` calls
  `fates_rando_chests::on_item_gain`, carries out the replaced `push {r3-r7, lr}` itself and carries on at +4. The
  original word goes back when the run ends or a non-randomized save loads, so **off = the original game, memory
  identical**. Or (b) a 3dsrecomp override (`RECOMP_OVERRIDE(0x003B0768)` in `src/readable/event/`, which calls
  `RECOMP_ORIGINAL`). Overrides are opt-in and unverified in this port (docs/ENGINE.md section 6.3), and they
  would need a host import. Default: **(a)**.
- **Ruled out:** rewriting the IID literal in the served `.cmb` file (patch 0016's in-place string-pool way). It is
  a script writer, which the owner's rule forbids. A longer IID would not fit either, and a 1-byte pool offset
  (opcode 0x1C) cannot point past 255.
- **Batch:** this track put it in the round 74 engine batch, beside the message hook, unless the round 71 header
  pulls it forward. The round 71 header does pull it forward (docs/ROUND71_PLAN.md item A1), because the roadmap
  promises chests and villages in round 71. Estimate (not counted) for the engine part: about 60 min of code and
  tests, plus the batch's builds.

## 4. The Python (this round)

`tools/randomizer/chests.py` (new track module; not imported by `tracks.py`, so nothing else changes):

| Function | What |
|---|---|
| `read_cmb(bytes)` / `calls_in(rel, bytes)` / `scan(dirs)` | the read-only reader and the call list (later dirs lay over earlier ones: base, then the mod) |
| `counts(rows, rules)` | the table in section 1 |
| `plan_chests(facts, rows, seed, opts)` | the entries: `{chapter, kind, orig, new, calls: [[file, call]...], x, y}`; `opts["chests"]` defaults to `"off"` → `([], [])` |
| `check_chests(facts, rows, entries)` | the guards of section 2 |
| `add_to_plan(plan, entries)` | writes `plan["chests"]` only when there are entries (off = the plan byte for byte the same) |
| `engine_table(entries)` | `{chapter: {orig: new}}`, what the hook reads |
| `judge_gain(...)` | the robot's judge (section 5) |

Commands: `python tools/randomizer/chests.py counts|list|plan [--game seal] [--seed S] [--out build/...]` (outputs only
under `build/`). Tests: `tests/test_rando_chests.py`, 18 tests (a made-up script built in the test, the items
track's made-up tables, the judge, and real data when the RomFS is there: every script walks to its end, counts,
12 seeds through every guard, no story item planned). Wiring it into `tracks.py` (a `chests` key kept out of
mod.json while off, like `W1_KEYS`) and the page row come with the engine hook, so a page option never exists
without the hook behind it.

## 5. The chest judge for rcheck (coded, pure)

`rcheck.judge_chest(chests, chapter, orig, before, after, num2iid, convoy_before, convoy_after, x, y)`: the opening
unit's item slots and the convoy are read before and after the open. The gained items become IIDs (`items_gained`
+ `num2iid`), and `chests.judge_gain` compares them with plan.json:

- the chest is found by its tile (x, y) or else by (chapter, original item);
- want = the planned new item, or the original when the chest is not in the plan (an off run must give the
  original: that is the "off = original" proof);
- pass only when exactly one item was gained and it is the wanted one; "the original item came" is named apart
  (the hook was not active).

Selftest: 5 new cases in `rcheck.py --selftest` (107/107). Robot use in the engine round: one chest and one village
on each path, through existing routes and replays only (no new play): Birthright `A007` chest (Armorslayer slot),
Conquest `B010` village, Revelation `C007` chest. The robot opens each one in its own headless test game with the
run's plan, then once with randomizer off. A SEEN picture of the "got" window is taken for each.

## 6. Open points

- Kind numbers 10 = chest and 1 = village are [medium]: read from counts and from where they sit. The robot proof
  in the engine round settles them.
- `ev::ItemGain`'s first argument: `MindGetUnit` (the acting unit) for chests and villages, 0 for event gifts
  (likely the convoy or the army leader) [medium]. It does not matter to the hook.
- Gold chests stay gold (they are items with the instant-gold flag). Turning gold into items, or items into gold, is
  a possible later option.
- Event gifts (paralogue rewards, story scenes) could become a separate switch later, with their own keep list.

## 7. Round 71: built (code and unit tests; the build and the robot proof are the round's later steps)

**In plain words.** The page has a new row, **Chest and village items** (Items and shops, off by default). With it on,
the make plans a new item for every chest, village and talk gift and writes a small list next to the run. When the
game hands one of those items over, the engine's new chest hook gives the planned item instead. With the row off
nothing is written, nothing in the game changes, and every old seed keeps its run id (fingerprints check: PASS, all
6 keys the same).

| Part | What | Where |
|---|---|---|
| The hook | patch 0031, new `crates/zakuro-core/src/fates_rando_chests.rs`; registered in `lib.rs`, `kernel/svc.rs` (svc 0xFEC001 -> `on_svc`) and `fates_rando_session.rs` (`Session::chests`, the frame call, `chests.txt` kept with the run) | section 3's design (a), as planned |
| The list | `chests.txt`: `fates-rando-chests 1`, `seed <seed>`, `c <chapter> <original IID hex> <new IID hex> <new IID offset hex>`, `end <n>`; labels as the game's cp932 bytes; the offset from GameData's data start (patch.txt's `g` base) | `chests.engine_list` / `parse_engine_list`; Rust `Table::parse` (same rules, same test list) |
| The wiring | `tracks.py` option `chests` (in `LATE_KEYS` and `INGAME_ONLY`: not a PLAY RANDOMIZED option), `rando.py --chests off|on`, page row `chests` with `omit_default` (left out of the answer, the run id and the make flags while off); "Randomize everything" keeps it off for now | `tools/randomizer/tracks.py`, `rando.py`, `ingame.py` |
| A new keep rule | a slot whose item a KEPT `ev::ItemGain` gift of the same chapter also hands over is kept (the hook only knows chapter + item); none in Fates or Seal of Flames today | `chests.hook_shared` |
| Kind numbers | **settled [high]**: every tile event of kind 10 stands on a treasure chest tile (`TID_宝箱`, `TID_闇／宝箱`: Fates 93, Seal 134), every one of kind 1 on a village tile (`TID_村`, `TID_村（足跡）`: Fates 25, Seal 30), read from each chapter's own terrain file | `python tools/randomizer/chests.py kinds [--game seal]` (exit 0 = all on their terrain); test `test_kinds_10_and_1_sit_on_chest_and_village_tiles` |

How the hook decides (all must hold, else the original item is given): the list's run is active; the IID at r2 is
listed for the chapter of the placement file the game holds; GameUserData's current chapter (when readable) is the
same; the new IID's label text is at GameData + the listed offset. Off, the hook only reads ItemGain's first word once
a frame; the original word goes back when the run ends. Robot proof (round 71 P1): `rcheck.judge_chest`, row on and
off, one chapter per path from existing recordings.
