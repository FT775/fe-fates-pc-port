# Is this class the female one (Fates): `Job::IsFemale`

**In plain words.** Some classes exist only for women (or come in a female version). When the game
builds the list of classes a unit may change into, picks a battle model's name, picks swimwear in
the hot spring, and a few more places, it asks "is this class the female one". The answer comes from
one flag bit, the PersonFlag "female", in the class record's own flag word. This batch
(docs/tracks/REWRITE_ORDER5.md row 1, round 25) rewrites that question. It stores nothing: it only
reads. It is the class-only twin of "is this unit female" (`female_unit_is_female`,
docs/FEMALE.md), which reads the class's word itself and does not call this one. The callers are
unchanged.

Status 2026-11-17 (round 25 batch `job_female`), **UNVERIFIED** in the project's sense:

- **1 readable override** (`src/readable/job_female/job_female.c`, registry and target rows added):
  `job_female_is_female`.

It gives the same answers as the game's own ARM code on made-up cases (two seeds), with the same
unmapped reads and no guest call; the planted bugs and the tier-2 result are in section 4. Live
compare: `r25-cap-job_female` (bt-ch4, library rebuilt 21:36, one route): 20 records, 19 match,
1 cold give-up, 0 bad of any kind; memory 18ca52e007f5179e, the same as earlier bt-ch4 runs; no
writer stored anything. Status stays UNVERIFIED until the owner's
call. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-17) [high unless marked]. No table values or game text are copied here: the flag's name is
an ID name (SPID_), given here in English.

---

## 1. What it decides

**`Job::IsFemale(void) const`** (0x00524AF4, 29 instructions and a literal pool of one address and
the inline ID name: r0 the class record, JobData).

```
first time only (one cache, behind a C++ guard word):
  female = 1 << index of the PersonFlag ID "female"     (guard 0x006D39AC, u64 at 0x006D3A08;
                                                          literal 0x006D3990 + 0x1C and + 0x78)

return (job.flags (+0x00, u64) & female) != 0          (1 or 0)
```

The body is instruction for instruction the shape of `Person::IsFemale` (0x0053ED90), on a different
record and with its own cache. Details that matter for matching the game exactly:

- It keeps its **own** cache. The game also has the same bit in the caches of `Unit::IsFemale`
  (0x006D9AF0) and `Person::IsFemale` (0x006D3B70); the readable code reads only its own, as the game
  does (plants that read either other cache are caught).
- The bit is a 64-bit mask: the test covers both halves of the word. An unmapped class pointer
  reads as 0: the readable code reads the same 8 bytes, so the same number of unmapped bytes.
- The answer is the game's `movne r0,#1` / `moveq r0,#0`: 1 or 0, never the raw bits.

**Callers** (every BL/BLX to 0x00524AF4 in text.bin, 21 sites, unchanged):
`ClassChangeEnumerator::Add` and `AddSlideLow`, `JobEnumeratorSecond::IsExclusion`, the
inheritance-class checks (`IsInheritJobIndex`, `JobEnumeratorParallelIndex::IsExclusion`),
`BattleUnitResName::Construct` (the battle model name), the four `Swimwear::Get`, `ProcSpa`
(hot spring), `ProcDining::ReflectDishEffect`, `castle::AngelSequence` and `castle::cut`, and
`Unit::ToPacket`.

## 2. Why it is a reader

The body's only stores are into its own cache (the `strd` after the name lookup, the first time it
runs) and its own stack (push/pop). The readable code never stores: while the guard word is cold it
gives up at entry, before it reads anything else, so the game's own code runs, calls
`PrivateSkill::Get` (0x001B7758) and the 64-bit shift (0x00300654), and fills the cache exactly as
before. Once the cache is filled the body calls nothing. Not here, and why:

- **No spouse or child rule** (Grok's row: "do not"). Nothing in the body asks about family; the
  inheritance-class callers that ask it were not edited, and no rule about who marries whom was
  guessed.
- **The female folder** (src/readable/female/) was not edited: `Unit::IsFemale` does not call
  `Job::IsFemale`, so nothing there changes.

**Reach.** Any preparations screen or fight already recorded (the battle model name asks it for
every unit in a fight; Grok: one route); the separate capture step picks it. No chapter is added.

## 3. Checks

**Host differential test:** `python src/readable/job_female/tests/job_female_diff.py`
(female_diff.py's method: the ARM interpreter src/readable/battle/tests/arm_mini.py on
extracted/text.bin against the readable C built with the host gcc; r0, unmapped reads and the
ordered list of guest calls, none expected; nested give-ups and guest writes flagged). While the
guard is cold the original reaches the guard routine before any other read (arm_mini raises "cold
guard") and the readable code must give up at entry. The made-up states are random test values,
never game data, and often outside what the game uses: unmapped class pointers (0 and others), a
record whose high flag word is on an unmapped page, cached bits in either half of the word, 0, two
bits or every bit, the words around the cache filled with junk, the other two female caches holding
the same bit or another, guard words cold or hot with other bits set.

**Planted bugs** (`--plant`, 13): the cache test dropped; the wrong guard word (`Person::IsFemale`'s,
or the next word); `Unit::IsFemale`'s cache; `Person::IsFemale`'s cache; the cache read from the
wrong offset; only the cache's low word; the class word read as 32 bits; read from the wrong offset;
read through a pointer at +0; every cached bit required; the raw bits answered; the answer inverted.

Not planted, because they cannot change an answer: the order of the two reads (the cache is always
mapped; an unmapped class read counts the same bytes in either order and gives 0 either way); the
1-or-0 form of a correct comparison.

**Tier 2** (`tools/readable/verify.py`): section 4.

## 4. Results (2026-11-17)

- Host test, seed 20261117, 300 cases, with `--plant`: **300 cases, 0 mismatches, 13/13 planted bugs
  caught**. Paths met: answered 1 (105, 2 of them with unmapped reads) and 0 (147, and 22 with
  unmapped reads); 24 cold give-ups at entry. No guest call listed on either side.
- Host test, seed 7, with `--plant`: **300 cases, 0 mismatches, 13/13 planted bugs caught**.
- Host test, seed 7, 1500 cases: **1,500 cases, 0 mismatches** (131 cold give-ups at entry; 552
  answered 1; 159 with unmapped reads).
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_job_female --only
  0x00524AF4`; library build 368 s, 60 staged files, the row 2 batch `job_record` already
  registered): **1 GAVE-UP, 0 MISMATCH** (`readable-verify: OK`). GAVE-UP: the cache is cold in
  verify's made-up memory, so the readable code gave up at entry and only the fallback ran: proves
  nothing either way (as `female_unit_is_female` and `female_person_is_female`); shadow pass:
  readable r0 = game r0. No classifier change. The library (553 MB) was deleted after the run; its
  logs are kept in build/readable/verify_job_female/.
- `python tools/readable/check.py --selftest`: readable OK (lint 298 rows 0 problems, 60 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken inputs, verify pipeline 28/28).
- `python tools/harness/gen_stubs.py --check`: OK (264 overrides, 67 guard users; the row carries the
  guard tag: the body calls the guard routine 0x00302C6C).
