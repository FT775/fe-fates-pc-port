# The person record for a person name (Fates): `Person::Get(const char*)`, and for a person number: `Person::Get(unsigned short)`

**In plain words.** Every character (Corrin, Azura, every generic soldier type, ...) has one fixed
record in the game data: the person record, with their name, base stats, growths, starting class and
so on. The game asks for it in two ways. Most places that start from a script or a table ask by the
person's ID label ("PID_..."): `Person::Get(const char*)`. Places that keep only the person's number
(a unit, a save, a support pair) ask by number: `Person::Get(unsigned short)`. This batch
(docs/tracks/REWRITE_ORDER5.md row 4, round 27) rewrote both lookups in readable C. They only read.
The callers (the castle-join reader, the growth, stance and support readers, and the rest of the game)
are unchanged.

- **By label** it does not search the person table: it asks the game's one big label table (the ID
  label hash table, which also holds the class, skill and item labels) and answers the record that
  table gives for the label, or 0 when the label is not there. This is the same lookup as
  `EquipSkill::Get(const char*)` (docs/SKILL_RECORD.md).
- **By number** it walks the short list of loaded blocks of person records and picks the first block
  whose numbers cover the one asked. A number no block holds does not give "nothing": it gives the
  first record of the first block. This is the shape of `Job::Get(unsigned short)`
  (docs/JOB_RECORD.md).

Status 2026-11-17 (round 27 batch `person_record`), **UNVERIFIED** in the project's sense:

- **1 readable override** (`src/readable/person_record/person_record.c`, registry row kind
  `override`, target row in config/harness/targets.csv): `person_record_by_name` (0x0044A6DC).
- **1 readable helper** (same file, registry row kind `helper`, no target row):
  `person_record_get` (0x0044A6F8). A helper, not an override, because a function before it runs on
  into it (section 2): the `Job::Get` stop rule, applied before trying.

Both give the same answers as the game's own ARM code on made-up cases (two seeds), with the same
unmapped reads and no guest call; 38/38 planted bugs are caught (20 for the label lookup, 18 for the
number lookup; section 4).

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-17) [high unless marked]. No table values or game text are copied here.

---

## 1. What they answer

**`Person::Get(const char*)`** (0x0044A6DC, 4 words and a one-word literal pool at 0x0044A6EC:
r0 the label). It moves the label to r1, loads the table's address from `G_IdentHash` (the word at
0x006DCB44) into r0 and branches (a tail `B`) into **`IdentHash::GetSurely(const char*) const`**
(0x00549484). The four words are the same as `EquipSkill::Get(const char*)`'s, so everything in
docs/SKILL_RECORD.md section 1 holds here word for word: two hashes of the label's signed bytes
(bucket `h = h * 37 + c`, key `k = k * 31 + c`, 32-bit wrap), the bucket picked with the runtime's
unsigned division (`h mod count`; with 0 buckets the runtime's division-by-zero path hands back `h`
itself), a walk of the bucket's chain comparing only the key hash on the whole word, the first match's
value (entry +0xC) answered, 0 when no entry matches or the label is null. Nothing is cached and
nothing is called, so the readable code never gives up.

The `GetSurely` step is written again in this folder as a `static` function, the same as
skill_record's. docs/SKILL_RECORD.md section 2 left it to this batch to lift that step into a shared
helper, but this batch may make new files only and may not edit src/readable/skill_record/, so the
step is copied, not shared. The two copies are tested against the same ARM code by their own host
tests; a later batch with the right to edit both folders may merge them.

**`Person::Get(unsigned short)`** (0x0044A6F8, 28 words with its one-word literal pool at
0x0044A764: r0 the person number).

```
node = *(G_PersonBlocks)                    (the word at 0x006D3B28: the first list node)
if node != 0:
  repeat:
    block = node[+0x0]                      (the block header)
    first = u16 block[+0x34]                (record 0's person number: header + 0x10 + 0x24)
    if number >= first                      (signed, the whole 32-bit register)
       and first + u16 block[+0x4] > number (the block's record count; signed):
         record = node[+0x0] + 0x10 + (number - first) * 0x98   (the node's block read again;
                                             the game computes ((i * 3) + (i << 4)) << 3)
         if record != 0: return record
         stop walking                       (an address of 0: fall back)
    node = node[+0x8]                       (the next node)
  until node == 0
return *(first node) + 0x10                 (the first block's record 0; with an empty list the
                                             block word is read from address 0)
```

The same details as `Job::Get` (docs/JOB_RECORD.md section 1), with the person block's offsets: the
compares are signed 32-bit on the whole register (a plant cutting the number to 16 bits is caught);
the fallback reads the first node's block, not the last walked; an empty list reads the block word
from address 0; a record address of 0 (only on made-up memory: a block at 0xFFFFFF58) falls back; the
second read of the node's block word in the in-range path is made too.

## 2. Why they are readers, and whether their addresses can be checked

`Person::Get(const char*)` stores nothing; `IdentHash::GetSurely` and the runtime's division store
nothing but their own stack pushes (docs/SKILL_RECORD.md section 2). `Person::Get(unsigned short)`
has no stack frame, no push and no store (loads, compares, arithmetic, branches, `bx lr`). The label
table and the person blocks are filled by the loading code, not here.

**`Person::Get(const char*)`: no fall-through, so an override.** The word before 0x0044A6DC
(0x0044A6D8) is the literal 0x006DCB44 of `Person::DeserializePointer`, whose last instruction is a
`pop {r4, pc}` at 0x0044A6C4 followed by its literal pool; nothing runs on into 0x0044A6DC. 148 `BL`
and 4 tail `B` reach it, all by its address (a scan of the ARM branch words in the code; Thumb `BLX`
not counted). This is the shape of `EquipSkill::Get(const char*)`, which tier 2 picked on its own
(docs/SKILL_RECORD.md section 4). Tier 2 was run for this address too (section 4).

**`Person::Get(unsigned short)`: a fall-through, so a helper.** `AIValue::GetPerson`
(0x0044A6F0, two words: `ldrh r0, [r0]` and a no-op) runs on into 0x0044A6F8 instead of calling it,
and `Person::DeserializePointer` also ends one path with a tail `B` to it (0x0044A6A0). This is the
shape tier 2 could not pick for `UnitPool::Get` and `Job::Get` (docs/MOVE.md section 6,
docs/JOB_RECORD.md section 2: NOT-RUN, 0 functions in both passes). The stop rule says an override
whose address the checker cannot pick is not kept, and the AI header and REWRITE_ORDER5's "Do not
start" list say the same of `AIValue::GetPerson`. So this batch did not try it as an override (no
scratch library spent on a known NOT-RUN): it is a helper from the start, with no override marker and
no target row. The game keeps running its own `Person::Get(unsigned short)`; readable code that needs
a person record by number may call `person_record_get` directly. 89 `BL` and 3 tail `B` reach it,
plus the fall-through. Turning it into an override later needs the same tier-2 way to check a
fall-through target that `Job::Get` needs; that is the owner's or the classifier owner's call.

**Callers** (not edited). The castle-join reader (src/readable/castle_join/, guest call
`CJ_PersonGet`) calls 0x0044A6DC through `guest_call`, which now reaches this override; its host test
answers that call from a table and was rerun unchanged (section 4). The growth, stance and support
readers call 0x0044A6F8 (`GROW_PersonGet`, `GUEST_PersonGet`, `SUP_PersonGet`) through `guest_call`;
with no override those calls still run the game's own code, so nothing changes for them.

**Not here** (Grok's row: "do not"): a join that stores the unit into the army (the castle join
itself, `Unit::Create` and the army stores), the loading of the label table and of the person
blocks, `Person::GetFromFid` / `GetFromNoPrefix` / `GetArchive` (other lookups, not named), and
`AIValue::GetPerson` (REWRITE_ORDER5: only after rows 2 and 4 are overrides; row 2 and this row's
number lookup are helpers, so it stays off).

**Reach.** Grok's row: a preparations or join route already recorded, one route. The capture step
owns that (this batch builds no capture library and runs no robot game). Only the label lookup has an
override entry, so only `person_record_by_name` can be captured; the helper records nothing.

## 3. Checks

**Host differential test:** `python src/readable/person_record/tests/person_record_diff.py` (the
method of the skill_record and job_record tests: the ARM interpreter
src/readable/battle/tests/arm_mini.py runs the game's ARM code from extracted/text.bin, `GetSurely`,
the runtime's division and its division-by-zero path included, against the readable C built with the
host gcc; the override through its override entry, the helper called directly with the game's
argument register; compared are r0, unmapped reads and the ordered list of guest calls, none
expected; nested give-ups and guest writes flagged). The made-up states are random test values,
never game data: for the label lookup, the skill_record test's states with "PID_" labels; for the
number lookup, the job_record test's states with the person block's offsets (section 1).

One addition to both earlier tests: arm_mini maps extracted/text.bin for every read, but the C
driver's memory holds only the made-up state. A made-up pointer that sends a data read into the
game's code (for example a table with 0 buckets, whose bucket word is then read at `4 * h`) would
then read code bytes on the ARM side and an unmapped 0 on the C side: a test artifact, not a
difference of the function (in the game the code is mapped for both). The first 300-case run met
exactly one such case ("16 faults against 12": the bucket word at 0x003B24EC). The test now draws
such a case again and prints how many it drew again (1 in 300 on seed 20261117; data reads within
4 KB of the instruction making them, the literal pools, are not counted). The skill_record test has
the same exposure but did not meet it on its seeds; that is noted for the integrate step, not changed
here (another folder).

**Planted bugs** (`--plant`, 38). Label lookup (20, the skill_record list): the wrong table word;
the wrong offset of the count, the bucket array, the next link, the key and the value; either hash
multiplier swapped; the label's bytes unsigned; the null-label test dropped; the empty-label test
dropped; the bucket picked with the key hash, or with a signed remainder; the wrong bucket word
size; only a chain's first entry asked; the key compared on 16 bits; the last match answered instead
of the first; the entry's address answered instead of its value; with 0 buckets, the remainder taken
as 0, or the lookup answering 0. Number lookup (18, the job_record list): the wrong list word; the
empty-list test dropped; the lower range test off by one, or unsigned; the upper range test off by
one; the count ignored; the number cut to 16 bits; the wrong offset of the count, of the first
number, of the next link, of the records; the wrong record size; the index not taken from the first
number; a record address of 0 answered; the fallback answering 0, the first node's pointer itself,
or the last node's block; only the first block asked.

Not planted, because they cannot change an answer: the order of the reads (an unmapped read counts
the same bytes in any order); reading the table word inside or outside the hash step; the upper range
test unsigned (reached only with 0 <= first <= number); dropping the second read of the node's block
word (docs/JOB_RECORD.md section 3 gives the reasons, which hold here unchanged).

**Tier 2** (`tools/readable/verify.py --only 0x0044A6DC`): section 4. Not run for the helper (tier 2
does not run helpers).

## 4. Results (2026-11-17)

- Host test, seed 20261117, 300 cases of each function, with `--plant`: **600 cases, 0 mismatches,
  38/38 planted bugs caught**. Label lookup: entry found 212 (3 with 0 buckets, 2 with unmapped
  reads), no entry 18 (+51 with unmapped reads, 23 of them with a null or unmapped table), null label
  19; 1 state drawn again. Number lookup: a record of the first to the fifth listed block 122,
  no block holds it (fallback) 144, empty list 20, record address wraps to 0 (fallback) 14.
  No guest call, no give-up.
- Host test, seed 7, with `--plant`: **600 cases, 0 mismatches, 38/38 planted bugs caught**.
- Host test, seed 7, `-n 1500`: **3,000 cases, 0 mismatches** (label lookup: entry found 1,042, 23
  of them with 0 buckets, null label 79, a null or unmapped table 98; number lookup: wrap to 0 56,
  empty list 77).
- Tier 2 (the override only): `python tools/readable/verify.py --out
  build/readable/verify_person_record --only 0x0044A6DC` (library build 347 s, run at below-normal
  priority): **1 ABI-ONLY, 0 MISMATCH** (`readable-verify: OK (1 ABI-ONLY)`). Verify picked the
  address (its own entry-table row, `override_0x0044A6DC`). Readable pass: r0 equal, the same
  unmapped reads; only r1, r2, r3, r12, lr, the Z and V flags and the dead stack below sp differ
  (scratch registers and flags, the ABI-ONLY shape). Shadow pass: "shadow match (1 so far, 0
  mismatches)", readable r0 = game r0; "12 faults against 24" is the benign shadow shape (both sides
  run, so the unmapped reads double). As with skill_record, verify's made-up state meets only the
  not-found path: a smoke test, not a proof; the host test is the evidence. No classifier was changed.
- `python tools/readable/check.py --selftest`: readable OK (lint 302 rows 0 problems, 63 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken inputs, verify pipeline 28/28).
- `python tools/harness/gen_stubs.py --check`: OK (266 overrides, 68 guard users).
- Caller's host test unchanged: `castle_join_diff.py -n 1500 --seed 7`: 1,500 cases, 0 mismatches.

Logs of these runs are kept under build/readable/person_record/logs/ (gitignored). The scratch verify
library was deleted after its logs were kept.
