# The skill record for a skill name (Fates): `EquipSkill::Get(const char*)`

**In plain words.** Every skill (Sol, Luna, Nohrian Trust, the stat seals' effects, ...) has one
fixed record in the game data: its name, help text, icon, activation stat and so on. The game's
code asks for a skill by its ID label ("SEID_..."), not by its number: 514 places in the code do
that (docs/SKILLS.md section 1). `EquipSkill::Get(const char*)` turns a label into the record. It
does not search the skill table: it asks the game's one big label table (the ID label hash table,
which also holds the class, person and item labels) and answers the record that table gives for
the label, or 0 when the label is not there. This batch (docs/tracks/REWRITE_ORDER5.md row 3,
round 26) rewrote that lookup in readable C. It only reads. The callers (the stat seal reader, the
skills batch's readers and the rest of the game) are unchanged.

Status 2026-11-17 (round 26 batch `skill_record`), **UNVERIFIED** in the project's sense:

- **1 readable override** (`src/readable/skill_record/skill_record.c`, registry row kind
  `override`, target row in config/harness/targets.csv): `skill_record_by_name` (0x001758C4).

It gives the same answers as the game's own ARM code on made-up cases (two seeds), with the same
unmapped reads and no guest call; 20/20 planted bugs are caught (section 4). Unlike `Job::Get`
(docs/JOB_RECORD.md), nothing runs on into this function, so it stays an override (section 2).

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-17) [high unless marked]. No table values or game text are copied here.

---

## 1. What it answers

**`EquipSkill::Get(const char*)`** (0x001758C4, 4 words and a one-word literal pool: r0 the label).
It moves the label to r1, loads the table's address from `G_IdentHash` (the word at 0x006DCB44,
literal at 0x001758D4) into r0 and branches (a tail `B`) into **`IdentHash::GetSurely(const char*)
const`** (0x00549484, 33 words), which does the work:

```
if label == 0: return 0
first byte = u8 label[0]
count = u32 table[+0x4]                     (how many buckets)
h = 0; k = 0
if first byte != 0:
  repeat:
    c = s8 label[i]                         (the byte, sign-extended)
    next = u8 label[i + 1]                  (the end test reads the following byte)
    k = k * 31 + c                          (the key hash; 32-bit wrap)
    h = h * 37 + c                          (the bucket hash)
  until next == 0
bucket = h mod count                        (BL 0x0012A0E4, the runtime's unsigned division;
                                             the remainder comes back in r1; with count 0 the
                                             remainder is h itself, see below)
entry = u32 (u32 table[+0x10] + 4 * bucket)
while entry != 0:
  if u32 entry[+0x4] == k: return u32 entry[+0xC]
  entry = u32 entry[+0x0]
return 0
```

Details that matter for matching the game exactly:

- **The label itself is never compared**, only its second hash `k`, on the whole word. Two labels
  with the same `k` in one bucket give the first entry's value (the host test plants an entry
  whose key differs only in its upper half, and one only in its lower half).
- **Bytes are signed** in both hashes (`ldrsb`): a label with bytes of 0x80 and above (a UTF-8
  label such as the second shield skill's, docs/SKILLS.md) hashes differently from the unsigned
  reading. A planted unsigned read is caught.
- **The reads of the label**: the first byte once (as unsigned) before the loop, then for each
  byte the byte as signed and the next byte as unsigned. The readable code makes the same reads,
  so a label that runs into unmapped memory counts the same unmapped bytes on both sides (an
  unmapped byte reads 0 and ends the label).
- **The division is unsigned** (the runtime's `.text_udiv`, 0x0012A0E4): a planted signed
  remainder is caught on bucket hashes with the top bit set.
- **A table with 0 buckets** does not stop anything: the runtime's division goes to its
  division-by-zero path (0x002FFC28: `push {r0, lr}`, `movs r0, #0`, `BL 0x0013F8B4`,
  `pop {r1, pc}`), and this build's division-by-zero handler is a no-op and a return
  (0x0013F8B4 `nop`, 0x0013F8B8 `__rt_div0`: `bx lr`). So the quotient is 0 and the remainder is
  the dividend: **the bucket is the bucket hash itself**, and the lookup goes on with it. The
  readable code answers the same way (`count != 0 ? h % count : h`). The game's table is filled at
  load time and is not expected to have 0 buckets in play [med: read from the shape of the code,
  not checked in a recording]; the first try of this batch gave up there instead, and tier 2 showed
  the extra reads of that give-up (section 4).
- **The table pointer is not checked** for 0 (neither function does): a null table reads its count
  from address 4 (unmapped, so 0 buckets: the case above) and its bucket array from address 0x10.
- **A null label** answers 0 before anything but the table word is read.
- Nothing is cached and no guest function is called, so the readable code **never gives up**. The
  division is ordinary arithmetic in C.

**`EquipSkill::Get(short)`** (0x001758E4, the record by number) is a different function, already
readable as `skill_record` (src/readable/skill/skill_has.c, not edited).

## 2. Why it is a reader, and whether its address can be checked

The four words of `EquipSkill::Get(const char*)` store nothing. `IdentHash::GetSurely` pushes four
registers on its own stack and stores nothing else; `.text_udiv` stores nothing on its normal
paths, and its division-by-zero path only pushes two words on its own stack and calls the no-op
handler. The table is filled by the loading code, not here.

**No fall-through into 0x001758C4.** The word before it (0x001758C0) is the literal pool of
`EquipSkill::GetCommonNum` (`bx lr` at 0x001758BC, then the literal 0x006D3C5C), so no function
runs on into it: 508 `BL` and 6 tail `B` reach it, all by its address (a scan of the ARM branch
words in the code). This is not the `UnitPool::Get` / `Job::Get` shape (docs/MOVE.md section 6,
docs/JOB_RECORD.md section 2), so the override is kept. Tier 2 checked the address on its own
(section 4).

**`IdentHash::GetSurely` is not overridden**, and that is on purpose: `UniqueArchiveObject::
GetSurely` (0x0054947C, two words: a load and a no-op) runs on into 0x00549484, the shape tier 2
could not pick for `UnitPool::Get` and `Job::Get`. Its body is rewritten here only as a `static`
step of `skill_record_by_name`; the game keeps its own `GetSurely` for its 37 other branch sites
(among them `Person::Get(const char*)` and `Job::Get(const char*)`, docs/CASTLE_JOIN.md and
docs/JOB_RECORD.md section 1).
The person batch (REWRITE_ORDER5 row 4, `Person::Get`, also a branch into `GetSurely`) may lift
that static step into a shared helper; that is its call.

**Callers** (not edited): the stat seal reader `battle_seal_effect`
(src/readable/class_change/, its guest call `CC_EquipSkillGet`) and the skills batch's readers
(src/readable/skill/, `SKILL_EquipSkillByName`) call 0x001758C4 through `guest_call`, which now
reaches this override. Their host tests answer that call from a table and were rerun unchanged
(section 4).

**Not here** (Grok's row: "do not"): learning a skill, `Unit::AddEquipSkill`, the skill picture,
and the loading of the label table.

**Reach.** Grok's row: a fight that already met a skill check, one route. The capture step owns
that (this batch builds no capture library and runs no robot game).

## 3. Checks

**Host differential test:** `python src/readable/skill_record/tests/skill_record_diff.py` (the
method of src/readable/job_female/tests/job_female_diff.py: the ARM interpreter
src/readable/battle/tests/arm_mini.py runs the game's ARM code from extracted/text.bin,
`GetSurely` and the runtime's division included, against the readable C override built with the
host gcc; compared are r0, unmapped reads and the ordered list of guest calls, none expected;
nested give-ups and guest writes flagged). The division-by-zero path runs in arm_mini as the game
runs it (nothing is stubbed); with 0 buckets the made-up entries are placed in the bucket the
remainder-is-the-dividend rule picks, so a 0-bucket table also finds entries. The made-up states are random test values, never game data: made-up labels (empty, one
byte, "SEID_" and other prefixes, up to 34 bytes, with bytes of 0x80 and above), hashed the game's
way into 1 to 300 buckets (sometimes 0, 1, 0x10000, 0x80000000, 0xFFFFFFFF or any 32-bit count,
with at most 0x400 bucket words mapped), decoys in front of the real entry differing only in the
key's upper or lower half, a second entry with the same key behind it, junk and unmapped bucket
words, unmapped last links, a null or unmapped table pointer, and labels asked that are held, not
held, null, unmapped, inside another label, or running to the end of a mapped page with no end
byte.

**Planted bugs** (`--plant`, 20): the wrong table word; the wrong offset of the count, the bucket
array, the next link, the key and the value; either hash multiplier swapped; the label's bytes
unsigned; the null-label test dropped; the empty-label test dropped; the bucket picked with the
key hash, or with a signed remainder; the wrong bucket word size; only a chain's first entry
asked; the key compared on 16 bits; the last match answered instead of the first; the entry's
address answered instead of its value; with 0 buckets, the remainder taken as 0, or the lookup
answering 0.

Not planted, because they cannot change an answer: the order of the first byte's read and the
count's read (an unmapped read counts the same bytes in any order); reading the table word inside
or outside the hash step (it is read once either way).

**Tier 2** (`tools/readable/verify.py`): section 4.

## 4. Results (2026-11-17)

- Host test, seed 20261117, 300 cases, with `--plant`: **300 cases, 0 mismatches, 20/20 planted
  bugs caught**. Paths met: entry found 205 (200 plain, 2 with 0 buckets, 2 with unmapped reads, 1 with
  unmapped reads and 0 buckets; recounted by the round 26 review and integrate),
  no entry 27 (+35 with unmapped reads, +19 with a null or unmapped table), null label 14. No
  guest call, no give-up.
- Host test, seed 7, with `--plant`: **300 cases, 0 mismatches, 20/20 planted bugs caught**.
- Host test, seed 7, 1500 cases: **1,500 cases, 0 mismatches** (entry found 1,026, 19 of them
  with 0 buckets; null label 100; a null or unmapped table 103).
- Tier 2, first try (the 0-bucket case then gave up): `python tools/readable/verify.py --out
  build/readable/verify_skill_record --only 0x001758C4` (library build 352 s): **1 MISMATCH**,
  "13 faults against 18". Verify picked the address (1 function in both passes, registers equal).
  Its made-up state has 0 buckets; the readable code gave up after 5 unmapped reads and the
  original then ran (13), so the recompiled side counted 18. Reading the runtime showed the
  division by 0 just returns (section 1), so the give-up was not needed: it was taken out and the
  host tests rerun (above). No classifier was changed.
- Tier 2, second try: the same command (library build 441 s): **1 ABI-ONLY, 0 MISMATCH**
  (`readable-verify: OK (1 ABI-ONLY)`). Readable pass: r0 equal (0), the same unmapped reads, only
  r1, r2, r3, lr and the dead stack below sp differ (scratch registers, the ABI-ONLY shape). Shadow
  pass: 1 function, 0 mismatched (no shadow match line logged). Verify's made-up state has 0
  buckets and meets the not-found path only: a smoke test, not a proof; the host test is the
  evidence.
- `python tools/readable/check.py --selftest`: readable OK (lint 300 rows 0 problems, 62 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken inputs, verify pipeline
  28/28). The row count includes round 26's other batch (key_door), which was in the tree.
- `python tools/harness/gen_stubs.py --check`: OK (265 overrides, 68 guard users; the same note).
- Callers' host tests unchanged: `class_change_diff.py` 1,500 cases, 0 mismatches;
  `skill_diff.py` 5,100 cases, 0 mismatches.

Logs of these runs were kept under build/readable/skill_record/logs/ (gitignored); the first
tier-2 try's logs in its verify_try1/ folder. Each scratch verify library was deleted after its
logs were kept.
