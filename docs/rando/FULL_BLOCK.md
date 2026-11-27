# Round 74 contract: the shared formats of the full swap, presets and the share code

Written first in round 74 (2026-11-25 05:00, contract agent; desk work, no build, no game run). Sources:
docs/ROUND74_PLAN.md, docs/rando/FULL_SWAP_PLAN.md (2.2, 2.3, 3, 4 with their "Round 73b check" paragraphs),
docs/rando/RECRUIT_WIRE.md, docs/ASSETS.md section 4 (FaceData record), `tools/randomizer/ingame.py` (`make_patch`,
`file_entries`, `schema`, `page_answers`, `run_id`), `tools/randomizer/colours.py` (`patch_lines`),
`tools/randomizer/rando.py` (`--patch-out`), `zakuro-core/src/fates_rando.rs` (`Patch::parse`, `Kind::Face`),
`fates_rando_session.rs` (`make_run_inner`, `make_placement`), `fates_rando_chests.rs` (the svc trap and its list
file), `zakuro/src/rando_page.rs` (`parse_schema`, `RandoForm::defaults` / `set`, targets) and `pagebot.rs`.

**For the owner, in plain words.** Three helpers write code side by side in round 74 (track py, track core, track
page). This page fixes, before they start, exactly what the files they hand to each other look like, so their parts
fit. Nothing here changes the game. Every example below uses made-up names and values.

**Changing this page.** A track that must change a format re-reads this page right before the edit, changes it,
adds a dated line to the change list at the end ("2026-11-25 hh:mm track X: what changed and why"), and says so in
its result.

## 0. The rules every part keeps

- **Off means original.** With look = keep (every run the owner's page can make today) there is **no `full.txt`**,
  no person-file pointer cell, no FaceData pointer cell; `patch.txt`, `plan.json`, `spoiler.txt` and the run id are
  byte-identical to today's; the `Mess::Get` word is never touched. `tools/release/fingerprints.py check` passes with
  no change listed in `config/release/seed_changes.json`.
- **No game text in git.** Names, face labels and voice keys exist only in the run folder
  (`<data>/rando/<title>/runs/<id>/`) and in the make's work folder under `build/`. Unit tests use made-up tables,
  lines and packages. The test-vector file of section 6 holds only our own option keys and made-up seeds.
- **Formats are text, one entry per line, labels as hex** (the patch and chest-list style), so the engine needs no
  JSON for anything it lays. JSON is used only for the schema (already JSON) and the test files.

## 1. Who writes and who reads (summary)

| Part | File / place | Written by | Read by |
|---|---|---|---|
| 2. Person-file label pointers | `patch.txt`, `file person` sections, `p` lines | track py (A1, A3 Python half: `ingame.file_entries` / `make_patch`) | track core (A3: `fates_rando_session` laid late; patch 0034); `ingame.apply_image` (reference apply, tests) |
| 3. Face cells | `patch.txt`, one `file face` section | track py (A1: `ingame.make_patch` from the FaceData records) | track core (existing `Kind::Face` resident path, first time with `p` cells) |
| 4. The full block | `full.txt` beside `patch.txt`, copied into the run folder | track py (A5: `recruit.py` builds it, `rando.py make --patch-out` writes it) | track core (A4: the `Mess::Get` trap, patch 0035; `make_run_inner` keeps the file); the robot (P2 judge) |
| 5. Test-only look switch | `<robot data>/rando/test-switches.json` + env `FEF_RANDO_TEST_DATA` | the robot's runner (prove phase) | track py (A7: `ingame.schema()`, `ingame.make_args`, the `--patch-out` refusal) |
| 6. Presets | `rando.py schema` top-level `presets` | track page (the presets part of `ingame.schema`, re-read before each edit) | track page (`rando_page.rs` buttons, patch 0036) |
| 7. Share code | the page's Share code field; `tools/randomizer/sharecode.py`; Rust codec in `rando_page.rs` | track page | track page; pagebot (P4) |
| 8. Shared test vectors | `tests/rando_sharecode_vectors.json` | track page | `tests/test_rando_sharecode.py` and the Rust tests in `rando_page.rs` |
| 9. Robot hooks | pagebot targets and steps | track page (`pagebot.rs`, `tools/harness/pagebot.py`) | P4 scenarios |

## 2. Label pointers in person files (`patch.txt`, patch 0034)

**Line format: unchanged.** The `p` line of `fates-rando-patch 1` is used as it is (ingame.py docstring,
`Patch::parse`):

```
file person GameData/Person/C009.bin.lz
v 1a4 05 07
p 2c8 4d5049445f4141 4d5049445f4242 g 1f3a0 2c40
p 2cc 4149445f4141 4149445f4242 g 1e990 2c58
end <count>
```

(The labels are made-up: `MPID_AA` -> `MPID_BB`, `AID_AA` -> `AID_BB`.) Fields: offset from the person file's data
start; old label text hex or `-`; new label text hex or `-`; where the new label lives (`g` = GameData's string pool,
offset from GameData's data start; `s` = this person file's own pool, offset from its data start; `-` = null); the
new label's offset or `-`; the old pointer's file value or `-`.

**When `p` lines appear in a `file person` section.**
- **Only when look = full.** `ingame.file_entries` gets a switch (name is track py's, for example
  `person_ptrs: bool`, default False). False = today's code path exactly: a label change in a person file is a
  rename in place or refused. True (only called so when the plan's `ropts.recruit_look == "full"`) = a label change
  in a `GameData/Person/**` file becomes a `p` cell, the place picked as for GameData (`g` first, then `s`); a rename
  in place is used for person files then only for a label that is in neither pool (exactly GameData's own fallback;
  track py, 05:40: such a label, for example a song name of the music track, is a plain `v` cell over the file's
  own pool bytes, laid the same late way with the file's other cells). `map/config/*.bin` keeps refusing `p` cells
  in both cases.
- Cells: `aid` (+0x10), `mpid_name` (+0x14), `mpid_help` (+0x18) of the HANDOVER rows and of the chapter copies
  (A1), plus any other label cell the shuffle changes in those files in a full run.

**How the core lays them (A3).** A person file with at least one `p` cell is laid **in memory after the game stores
it** (the `late` path placement files use; found in the Person archive list by its name, patch 0018), never in the
read. All cells of that file (its `v` cells too) go the same way, all or nothing, guarded by the old values / old
label text. A file whose guard fails is kept original with a notice, as today. A `g` target needs GameData's data
start; an `s` target the person file's own data start in memory.

## 3. Face cells (`patch.txt`, one `file face` section; P1)

The existing resident kind (`Kind::Face`, round 59 recolour), never used with pointers before:

```
file face face/FaceData.bin.lz 452
p 488 4d5049445f4141 4d5049445f4242 s 9c10 9b80
p 490 41415f706b67 42425f706b67 s 9d02 9c44
v 4a0 a0b0c000 30405000
v 4b4 00800010 00780014
end <count>
```

- The header's last word is the FaceData record count (452 Fates, 456 Seal of Flames): the guard that the resident
  file is the one the patch was made for.
- Offsets count from the file's data start = the records start - 4 (`fates_rando::resident_start`), so record `i`
  begins at `4 + i * 0x48` (the example is record 16 at 0x484: +0x04, +0x0C, +0x1C and part of the layout numbers).
- For every swapped spot A -> B (B is not A) and for each of A's records (stand `FSID_ST_*` and bust `FSID_BU_*`,
  matched to B's record of the same kind), every field below that differs between A's and B's record gets one cell:

  | Field | Offset | Cell |
  |---|---|---|
  | name plate MPID | +0x04 | `p` |
  | package | +0x0C | `p` |
  | body dir, hair dir, accessory dir | +0x10, +0x14, +0x18 | `p` (either side may be null: `-`) |
  | colour (hair tint) | +0x1C | `v`, 4 bytes |
  | two default expression names | +0x20, +0x24 | `p` |
  | layout numbers | +0x28..+0x47 | `v`, one run of the bytes that differ |

  **Never written:** +0x00 (the FSID, the label the game finds the record by) and +0x08 (the voice key: it stays
  A's; the silence list in `full.txt` handles voices).
- `p` cells in this section use **`s` only** (labels from FaceData's own pool; B's record already points at them).
  A label not in that pool = `PatchError` = the seed is refused with the plain "this seed failed a check".
- **At most one `file face` section per patch.** The recolour writes face cells only with look = keep
  (`rando._colours` returns nothing for full), so the two never meet; if a later change makes them meet, the
  writer merges them into one section with no two cells overlapping.
- The `plan.json` records `{"table": "FaceData", ..., "laid_by": "engine"}` stay as they are (format unchanged).

## 4. The full block: `full.txt` (P4 names and voices; read by the `Mess::Get` trap)

The plan's "the run patch's `full` block" is **its own file `full.txt`**, written beside `patch.txt` by
`rando.py make --patch-out` (as `nuzlocke.json` is) and copied into the run folder by `make_run_inner` (as
`chests.txt` is). Reason: `patch.txt` and its parser stay exactly as they are, and "no file" is a clear off.
**No `full.txt` = look keep = the trap is never armed.** A stale `full.txt` beside the patch is removed when look is
keep (as `nuzlocke.json`).

```
fates-rando-full 1
seed demo-7
game fates
n E 4100610072006f006e00 420061006b0065007200
n E 4300610072006c006100 44006f00720061006e00
s 4141524f4e
s 4341524c41
end 4
```

(Made-up: names "Aaron" -> "Baker", "Carla" -> "Doran"; voice keys `AARON`, `CARLA`.)

| Line | Fields | Meaning |
|---|---|---|
| `fates-rando-full 1` | format | another number = the core does not arm the trap and logs why |
| `seed <seed>` | the run seed | for people and the guard (must equal the patch's seed) |
| `game <fates\|seal>` | the game the run was made for | must equal the run's game, else not armed |
| `n <lang> <old hex> <new hex>` | text language tag (the `m/@<lang>/` folder: `E` is the only one in Fates USA and in Seal of Flames); A's display name and B's display name as **UTF-16LE bytes, no end mark** (the form the message text has in memory) | one name swap. Old names are unique per language. A pair with old == new is never written |
| `s <key hex>` | a voice key, ASCII bytes as hex (from A's FaceData +0x08) | silence: drop every `$Svp` command whose label starts with `VOICE_<key>_` |
| `off <chapter>` | a chapter id such as `C008` | `full_off_chapters`: in this chapter the trap passes all text unchanged (names AND voices). Empty in round 74 (rules.json `recruit.full_off_chapters` is `[]`) |
| `end <n>` | number of `n`, `s` and `off` lines | a cut file is refused |

Rules both sides keep:

- **Who is in it.** For every swapped spot A whose filler B is not A: one `n` line per language (A's name -> B's
  name, from the `MPID_` labels of both main Person rows through the message tools at make time) and one `s` line
  with A's voice key (if A's records have one; a key listed twice is written once). Extra `n` lines for joined
  names or nicknames come only from track py's one Grok consult and use the same line.
- **Order:** `n` lines sorted by old name length, longest first, then by bytes; `s` lines by bytes; `off` by id.
  Deterministic, so the same seed gives the same file.
- **What the trap does with one text** (the order of FULL_SWAP_PLAN 2.2): (1) commands (`$` up to the closing `|`)
  are copied unchanged, except (2) a `$Svp` command whose label starts with `VOICE_<key>_` for a listed key is
  dropped whole (from `$` through its `|`); (3) in plain text, every whole-word occurrence of an old name is
  replaced, all pairs in one pass (at each position the longest matching old name wins; replaced text is never
  scanned again, so A -> B and B -> C never chain). "Whole word": the code unit before and after is not an ASCII
  letter or digit and not in U+00C0..U+024F (so "Aaron's" becomes "Baker's"). (4) Nothing is changed and the
  original pointer is returned when the text has no listed name and no listed voice key, or the current chapter is
  on an `off` line.
- **Exact reading of (1)-(4) (track core, 2026-11-25 05:25; `fates_rando_names.rs`).**
  - **Commands** are not "`$` up to the next `|`": many have no `|` (`$k`, `$p`, `$Wa`, `$Wd`, `$Nu`), and
    `$Wm<name>|<digit>` ends in a digit. A command is `$`, then its name from this table, then its arguments
    (`p` = up to and with its `|`; `d` = digits, no `|`), longest name first: `Svp Ssp Sbs Sre` p, `Sbv Sbp Sls
    Slp Slv Srp` pp, `Ws` p, `Wm` pd, `Wa Wd Wc Wv` none, `Nu` none, `Fi Fo Fw VN VF` p, `E G` p, `k p a` none,
    `w b l c` p, `t` d. The table was counted on the English message files of the owner's game (every command but
    about twenty one-off uses). An argument with no `|` within 64 code units (before a `$` or line break) ends the
    command there; an unknown command runs to its `|` when one comes within 64 units before a `$` or line break,
    else over its letters only.
  - **A command counts as a word break** for the whole-word rule (text such as `$p<name>` starts a page with a
    name right after the command letter).
  - **Only `$Svp` (voice play) commands are dropped**; `$Ssp` and the other sound commands are kept.
  - **A text whose label starts with `MPID_` is left alone.** The label is in r7 at the trap (`Mess::Get` keeps
    it there from its entry, 0x003D1CF4). Person names and help texts are fetched through the person's own
    labels, which the patch.txt cells already point at the filler's: the unit list, the name plate and the battle
    window ask for B's own `MPID_` and get "B". Changing that again would chain B -> C whenever B's own spot is
    swapped too.
  - **The ring:** guest addresses 0x50000000-0x500FFFFF (1 MiB), mapped by the core the first time a full run arms
    the trap, pages from FCRAM's Base region (as the HLE services take theirs). Free because a 3DS process is
    never given an address at or above 0x40000000 (every region the game or Zakuro maps lies below it) and the core
    maps only when nothing is there. Each changed text takes the next free bytes (4-aligned), wrapping to the
    start, so a held result stays whole until 1 MiB of later changed text has been written. A text over 256 KiB,
    unterminated within 16,384 code units, or at an odd or unreadable address is left as it is. Call 5's fallback
    is not used.
  - **The chapter for `off` lines:** the last chapter person file the game loaded (the Person archive list
    `Person::Load` appends to), else GameUserData's current chapter; read only when the file has an `off` line.
  - `full.txt` lines are not trusted to be in order (the core sorts the names itself); a `n` line whose old name is
    listed twice for one language, or whose old and new are equal, refuses the file; a `s` key listed twice is
    read once.
- **Fast path:** a run with no `full.txt`, or a `full.txt` with no `n` line for the game's text language and no `s`
  line, never arms the trap.
- **The trap (core, A4):** a reserved `svc 0xFEC002` written over the word at `0x003D1DA8` (`add sp, sp, #80`,
  expected original word `0xE28DD050`; another word there = not armed, notice) only while a run with a non-empty
  `full.txt` is active; the original word goes back when the run ends, as round 71's chest trap does (`svc
  0xFEC001`, `ItemGain`). `0xFEC001` and `0xFEC002` are reserved; a later trap takes `0xFEC003`. Changed text goes
  into the core's own ring of buffers in guest memory (call 5's fallback if no free region is found), never into
  the game's shared message buffer and never into a message file.
- **A `full.txt` that fails to parse:** faces and menu names (the `patch.txt` cells) are still laid; the trap is not
  armed; the notice says "dialogue names kept (full.txt: <reason>)".

## 5. The robot's test-only switch for look = full (A7)

The owner's page keeps "How they look" fixed at "Keep the face" (call 1). The robot reaches look = full like this:

- The robot's runner writes `<job data folder>/rando/test-switches.json` and starts the game with the environment
  variable **`FEF_RANDO_TEST_DATA=<job data folder>`** (the same folder as `--data`). The game's child processes
  (`rando.py schema`, the make) inherit it.

  ```json
  {"format": 1, "recruit_look": "full"}
  ```

- **Read only by Python** (`ingame.py`), and honoured only when all hold: the variable is set; the folder it names,
  resolved (`os.path.realpath`), lies inside `<repo>/build/`; the file exists, is JSON with `"format": 1`. Anything
  else = no switch, silently (a broken file is logged to stderr, never an error). The owner's data folder is under
  %APPDATA%, so it can never qualify.
- **Effect with the switch:** `schema()` gives the `recruit_look` row as not fixed, choices `["keep", "full"]`,
  `choice_labels` `{"keep": "Keep the face", "full": "Full swap (robot test)"}`, default and "all" still `keep`
  ("Randomize everything" never picks it). The robot then clicks `opt:recruit_look=full` like any choice. The answer
  carries `"recruit_look": "full"`, so the run id differs from every keep run by itself. `make_args` passes
  `--recruit-look full`, and the `--patch-out` refusal for `PAGE_FIXED` rows (rando.py) lets `recruit_look` through
  only under the same switch (one helper in ingame.py, used by both).
- **Without the switch** `schema()` output is byte-identical to today's (a test compares the JSON text).

## 6. Presets in the schema (page track; patch 0036)

`rando.py schema` gains a top-level `presets` list next to `rows`; `format` stays 1 (the page ignores keys it does
not know, so the installed round-71 program is not affected).

```json
{"format": 1, "rows": [...],
 "presets": [
  {"name": "light", "label": "Light",
   "help": "Different classes and growths. Enemies, chests, and the face stay.",
   "values": {"randomizer": true}},
  {"name": "wild", "label": "Wild",
   "help": "Light, plus enemy classes and weapons, music, and who joins. Face stays.",
   "values": {"randomizer": true, "enemy_classes": true, "enemy_weapons": true, "music": "maps",
              "recruit": "route"}}]}
```

| Field | Type | Meaning |
|---|---|---|
| `name` | lowercase ASCII word | the id; pagebot target `btn:preset:<name>` |
| `label` | text | the button text |
| `help` | text | the one help line (call 3) |
| `values` | {row key: value} | only rows that exist, not `page_only`, not `seed`; each value valid for its row (a test checks) |

**A press:** every row to its default (`RandoForm::defaults`, page-only switches included), then each preset value
through `RandoForm::set` (fixed and game-hidden rows keep their rule), the seed box kept as it was, the help line
shown. Light after Wild gives exactly Light. Presets are buttons, not rows: they never enter the answer or the run id.

## 7. The share code (page track; `tools/randomizer/sharecode.py` and the Rust twin in `rando_page.rs`)

```
R1FXX-B1-DC-demo-7
```

`<head>-<body>-<check>-<seed>`, split on the first three `-` only (the seed itself may hold `-`).

| Part | Form | Meaning |
|---|---|---|
| head | `R1` + game + layout | `R1` = code format 1; game `F` (Fates) or `S` (Seal of Flames); layout = 2 characters, below |
| body | characters of the alphabet | every share row's value index, bit-packed, below |
| check | 2 characters | `fnv1a32(head + "-" + body + "-" + seed) & 0x3FF`, high 5 bits first |
| seed | the seed text | must match the seed row's pattern (`[A-Za-z0-9][A-Za-z0-9_-]{0,31}`); never empty |

- **Alphabet** (Crockford base 32, 5 bits a character): `0123456789ABCDEFGHJKMNPQRSTVWXYZ`. The head, body and check
  are read case-blind (lowercase is upper-cased first); the seed is kept exactly (seeds are case-sensitive).
- **FNV-1a 32:** offset `0x811C9DC5`, prime `0x01000193`, over UTF-8 bytes (the constants `run_id` uses).
- **Share rows** = every schema row that is not `page_only` and not the seed, **sorted by key** (byte order). Hidden,
  fixed and game-hidden rows are included, `randomizer` too.
- **Layout** = `fnv1a32(L) & 0x3FF` in 2 characters, where `L` joins, in share-row order with `;`, one item per row:
  `<key>:onoff:2`, `<key>:choice:<choices joined by ,>`, `<key>:number:<min>,<max>`. A code whose layout differs
  from the page's own is refused: "This code was made by another version of the randomizer."
- **Value index and width:** on/off: false 0, true 1 (radix 2); choice: its index in `choices`; number: value - min
  (radix max - min + 1). Width in bits = bit length of (radix - 1).
- **Body:** for each share row in order, its index's bits, lowest first, appended to one bit list; zero bits added up
  to a multiple of 5; each group of 5 becomes one character, the group's first bit as its value's 1 bit.
  Today's real schema (round 75b): 57 share rows (the hidden one-choice row `rando_version` takes 0 bits), 127 bits,
  26 body characters, layout `CE` (round 74's layout `25` codes are refused); with an 8-character seed (the
  page's proposed seeds) the code is 44 characters, with a 32-character seed 68 (counted by
  tests/test_rando_sharecode.py, track page, 2026-11-25).
- **Encode** uses the form values (a row's own value, not a driving switch's); an empty seed box is first filled with
  the page's proposed seed, so a code always carries a seed.
- **Decode** refuses, each with one plain sentence: not 4 parts / not `R1` ("This is not a share code."); bad check
  ("This code has a typo."); other layout (above); other game ("This code is for Seal of Flames." / "... for Fire
  Emblem Fates."); an index at or above its radix, or a padding bit that is not 0, or a bad seed ("This code is
  damaged."). On success: the form is reset to defaults, every row set through `RandoForm::set`, the seed box set.
  The answer then follows the existing rules (`omit_default` rows at their default are left out, fixed and
  game-hidden rows at their default), so the same code gives the same answer text and run id.
- **Reading, exactly** (track page): space around the code is ignored; only ASCII `a`-`z` are upper-cased in the
  head, body and check; a head that is not 5 ASCII characters `R1` + `F`/`S` + 2 is "not a share code"; the check
  must be 2 characters equal to the computed one ("a typo"); the body's length (in bytes) must be the rows' body
  length and every character in the alphabet, else "damaged". A value that does not fit its row is encoded as the
  row's default (the form never holds one).
- **On the page** (patch 0036): the Share code row sits under the seed row (the field shows the form's code; a seed
  the randomizer does not take gives no code and a grey Copy). A code pasted into the field (Ctrl+V, or the robot's
  paste event) is used at once; a typed one with Enter or Paste. Used: the help line says "Share code used: every
  setting and the seed come from it."; refused: its sentence, the text stays in the field, nothing changes. Copy:
  "Share code copied. The same code makes the same game." Paste with nothing typed empties the field and says
  "Press Ctrl+V to paste a share code into the box; it is used at once." (the program has no clipboard read of its
  own). The rows' help when the row is pointed at: "Share code: Copy or paste this. The same code makes the same
  game." (call 3). The presets and the Share code row show in the Esc window's Next New Game part too (`next:`).
- Worked example (made-up 3-row layout: `enemy_levels` number 0-5, `music` choice off/maps/maps+battles,
  `randomizer` on/off; `L` = `enemy_levels:number:0,5;music:choice:off,maps,maps+battles;randomizer:onoff:2`, layout
  `XX`): values enemy_levels 3, music maps, randomizer on, seed `demo-7`. Bits: 3 -> 1,1,0; 1 -> 1,0; 1 -> 1; padded
  110101 0000 -> characters 11 = `B`, 1 = `1`; check `DC`; code `R1FXX-B1-DC-demo-7`.

## 8. The shared test-vector file: `tests/rando_sharecode_vectors.json`

```json
{"format": 1,
 "alphabet": "0123456789ABCDEFGHJKMNPQRSTVWXYZ",
 "rows": [{"key": "randomizer", "kind": "onoff", "default": false},
          {"key": "seed", "kind": "seed", "default": ""},
          {"key": "music", "kind": "choice", "choices": ["off", "maps", "maps+battles"], "default": "off"},
          {"key": "enemy_levels", "kind": "number", "min": 0, "max": 5, "default": 0},
          {"key": "spoiler_log", "kind": "onoff", "default": true, "page_only": true}],
 "layout": "XX",
 "good": [{"game": "fates", "seed": "demo-7",
           "values": {"randomizer": true, "music": "maps", "enemy_levels": 3},
           "code": "R1FXX-B1-DC-demo-7"}],
 "bad": [{"game": "fates", "code": "R1FXX-B1-DD-demo-7", "error": "check"}]}
```

- Made (track page): the example above plus `layout_text`, an `about` line, a `note` on every vector, `message` (the
  sentence) on every `bad` one and `also` (other spellings of the same code: lower case, space around it) on the
  first `good` one; 4 `good` and 17 `bad` vectors covering all five error kinds.
- `rows` is a frozen copy (made-up or our own option keys; no game text), so the codecs are tested apart from the
  live schema. More `good` vectors (for example one with a long seed holding `-` and `_`, one Seal code) and `bad`
  vectors with `error` one of `format`, `check`, `layout`, `game`, `damaged` are track page's to add.
- Python: `tests/test_rando_sharecode.py` encodes every `good` and compares the text, decodes it back, and checks
  each `bad` refuses with its error kind; one more test round-trips today's live `ingame.schema()` rows.
- Rust (`rando_page.rs` tests): reads the same file at test time, found by walking up from `CARGO_MANIFEST_DIR`
  until `tests/rando_sharecode_vectors.json` exists; **not found = the test fails** with a plain message (never a
  silent skip). The same checks as Python.

## 9. Robot hooks (pagebot; page track)

- New targets in `RandoPage.targets`: `btn:preset:<name>`, `row:share` (the field), `btn:share:copy`,
  `btn:share:paste`.
- New script step `{"paste": "<text>"}`: sends an egui paste event with that text to the focused control (the robot
  clicks `row:share` first, then pastes). The page uses a pasted code at once, so no click on `btn:share:paste`
  follows (as made: track page). While the field has the focus and holds the form's code, all of it is selected, so
  the paste replaces it. `{"paste_copied": true}` pastes the text the page's last Copy put out. A paste writes an
  event `{"event": "paste", "text", "copied", "values"}` (values = the page's values before the paste).
- Log: a click event's `extra` gains `"share": "<the code the field shows>"` once the field exists; a copy writes an
  event `{"event": "copied", "text": "<code>"}` from egui's copied text.
- The Esc fit check (A9) uses the existing `next:btn:keep` target with the page drawn at 800x480; how the robot sets
  that size is track page's (a script step or the runner's screen size), written here when made. As made: the hook
  always draws into an 800 x 480 screen (`pagebot::SCREEN`), so no size step is needed; the new step
  `{"expect_target": "<target>"}` writes `{"event": "expect_target", "ok", "rect", "screen", "this_run_lines",
  "notices"}` with ok = the control is drawn wholly on that screen. Expect events gain `"note"` (the help line's note)
  and `"share"` (the field's code).
- P4's scenarios (tools/harness/pagebot.py, `--scenario presets | escfit | p4`; p4 = both in one job) and their judge
  `judge_p4` are described in docs/tests/PAGEBOT.md.

## Change list

- 2026-11-25 05:00 contract agent: first version.
- 2026-11-25 05:25 track core: section 4 gains the "Exact reading of (1)-(4)" bullet: the command table (commands
  are not "`$` up to the next `|`"), a command is a word break, only `$Svp` is dropped, texts with an `MPID_` label
  are left alone (else menu names would chain B -> C), the ring's address and size (0x50000000, 1 MiB), the chapter
  for `off` lines, and how out-of-order or doubled lines are read. No file format changed.
- 2026-11-25 05:40 track py: section 2: with `person_ptrs` a label in neither pool keeps the rename in place (a
  `v` cell over the person file's own pool, laid late with that file's other cells) instead of refusing the seed,
  so a full run with music on still makes a patch; `g` and `s` come first as written. Section 3: a swapped spot
  whose person has no FaceData record of their own gets no face cells (only counted in R9's note); on Seal of
  Flames the FaceData is read from the mod's romfs over the base (the table layer has no `face/` folder), as the
  recolour reads it. Section 4: `n` lines of equal length and bytes are ordered by language last (only `E` exists
  today). No file format changed.
- 2026-11-25 05:50 track page: section 7: the real schema's counts corrected (127 bits, not 130; 44 / 68
  characters, not 41 / 64) and its layout `25` named; "Reading, exactly" and "On the page" bullets added (ASCII-only
  upper case, byte lengths, the page's sentences, a pasted code used at once). Section 8: the extra fields the
  vector file has. Section 9: a paste needs no Paste click; `paste_copied`, `expect_target`, the paste event, the
  note and share in expect events; the hook's screen is always 800 x 480. The code format itself is unchanged
  (the worked example's `XX` and `DC` are the real values).
