# Supports, pair-up partners and family (Fates), read from the code

**In plain words.** Two units who fight side by side build up **support points**; enough points
give a **support level** (C, B, A and, for some pairs, S). The level decides how much a partner
helps in Attack and Guard Stance (the bonus tables the stance batch already rewrote,
docs/STANCES.md, look the level up through `Unit::GetRelianceLevel`). An S level is a marriage or a
sworn bond, and a married parent has child units whose **family record** names their parents and
grandparents; family members support each other on fixed thresholds instead. This batch rewrites
the game's own answers to: which partners a person may support at all, how many points each level
needs, which level a pair has now and can reach, who is whose child, sibling, uncle or aunt, who is
married to whom, whether two units may trade pair-up partners, and whether the current map hands
out support points at all.

All 25 are **readers**: they store nothing (F-017, F-021: no writer, nothing armed). Gaining
points (`Unit::RelianceUp`, `AddChapterReliance`, `SetRelianceLevel`) stores, so it is not here.

Status 2026-11-14: 25 readable overrides (`src/readable/support/`), all **UNVERIFIED** in the
project's sense. Every one gives the same answers as the game's own ARM code on made-up cases,
with the same guest calls in the same order and the same unmapped reads (section 7); bugs planted
on purpose were all caught. Not yet in a live compare: round 10's integrate step rebuilds the
capture library and compares them in real play. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-14) [high unless marked]. No table values or game text are copied here: the support table
is the game's data and is only described by its shape.

---

## 1. The support table (class `Reliance`)

The game keeps one list of possible support partners per person, built when the data loads and
never changed in play. A global word (0x006D3BD0) points to 128 chains; a person's chain is chosen
by its **support id** (Person +0x30, a signed 16-bit number; a negative id means "no supports").
Each chain node holds a record and the next node; a record holds a support id, a count and that
many 12-byte **entries**. A chain can hold records of other ids (ids that share the last 7 bits);
every lookup skips those.

One entry (`Reliance`) is one possible partner:

| Part | What it is |
|---|---|
| +0 (16 bits) | the partner's person number (Person +0x24) |
| +2 (16 bits) | the slot of this pair in the support-points bytes (below) |
| +4 .. +7 | the points needed for C, B, A, S; **99** means "this pair has no such level" |
| +8 | not 0: the asking unit keeps the points itself; 0: the partner's unit keeps them |

What the game asks of it:

- **Highest reachable level** (`Reliance::GetMaxLevel` 0x005467F0): S if the S threshold is not
  99, else A if A's is not, else B, else C, else 0.
- **Level for a number of points** (`Reliance::GetLevel` 0x00546878): the highest level whose
  threshold is at most the points (a missing level needs 99, so 99 points or more would "reach"
  it; the game never gives that many [med]).
- **Can this pair reach S** (`Reliance::IsRomance` 0x005468C4): the S threshold is not 99.
- **The partner's person** (`Reliance::GetPerson` 0x005468BC): `Person::Get` of the number.
- **How many partners** (`Reliance::GetNum` 0x004F1284): the counts of the person's records added
  up; **the n-th partner** (`Reliance::Get` 0x004F10EC): counted over those records in chain order
  (the index is not checked for being negative); **the entry for a given pair**
  (`Reliance::GetFromPerson` 0x004F0FDC): the first entry whose partner number is the other
  person's number, or none. "None" is what makes two units unable to support.

## 2. Support points and level of two units

- **Points** (`Unit::GetReliance` 0x0052C260): every unit carries a pointer (Unit +0x11C) to its
  support-points bytes. The pair's points are the byte at the entry's slot, in the asking unit's
  bytes when the entry says so, else in the bytes of the partner's unit: the one unique unit of the
  partner's person number in the asking unit's side of the war (`UnitPool::GetFromPerson` with
  `Force::GetMaskSameForce`). No such unit, or no bytes: 0.
- **Level now** (`Unit::GetRelianceLevel` 0x0052F518), in this order:
  1. a parent and its child: the child's family record holds the points with each parent, and
     the level comes from fixed thresholds: **1 point = C, 5 = B, 10 = A**, never S
     (`ParentSingle::GetLevel` 0x0053B800);
  2. siblings: the same thresholds on the sibling points of the family record
     (`BrotherSingle::GetLevel` 0x0053B864);
  3. everyone else: the support table entry and the points above (`Reliance::GetLevel`).
- **Highest level** (`Unit::GetRelianceMaxLevel` 0x00530D2C): A for parent and child and for
  siblings (the game asks a three-instruction function that answers 3); else the table's highest
  level, with **S turned into A when either unit's person is a downloaded (DLC) one**.
- **Have a support at all** (`Unit::IsReliance` 0x0052AD24): always for parent/child and siblings;
  never for an uncle or aunt with a nephew or niece who could reach S together (the game refuses
  that pair before it looks at the table); everyone else when the table has the pair.

Every one of these first asks whether both units are **unique** (the inline form of
`Unit::IsUnique`, docs/SHEET.md section 4: state bit 18 no, state bit 28 only for a download
person). Generic units and clones never support.

## 3. The family record (class `unit::Family`, Unit +0xB4)

A child unit carries a family record: two parent parts (+0x0 and +0x14; each holds the parent's
Person, that parent's two parents as "grandparents", the parent's boon and bane used by the
growth batch, and the support points with that parent at +0x10) and one sibling part (+0x28, the
points with the sibling). The growth batch already reads the growth and cap parts
(`family_grow`, `family_parent_grow`, `family_limit`, docs/GROWTH.md).

- **Which parent part is this unit** (`Family::GetParent(const Unit*)` 0x0053BECC): the part whose
  Person is the unit's, or none.
- **Grandfather / grandmother** (`Family::GetGrandFather` 0x0053BAC8, `GetGrandMother`
  0x0053BAF4): nothing unless both parents are set; then the first parent's grandparent of that
  kind, or else the second parent's.

## 4. Who is family

- **Parent and child** (`Unit::GetFamilyChildImpl` 0x005306C4, `IsFamilyParentChild` 0x00530E84):
  one unit's family record names the other's person as a parent. The unit asked about is tested
  first, so when both name each other the first wins.
- **Siblings** (`Unit::IsFamilyBrotherSister` 0x00531428): both have family records and the same
  first parent, or else the same second parent (a missing parent never matches).
- **Uncle or aunt** (`Unit::IsFamilyUncleAunt` 0x0052FA58): not parent and child, and one unit's
  grandfather is the other's first parent or its grandmother the other's second parent, checked
  one way and then the other. The game reads the family words again at every step.
- **Family** (`Unit::IsFamily` 0x0053386C): parent and child, or siblings (uncles and aunts are
  not "family" here).

## 5. Marriage

- **Could reach S** (`Unit::IsRomance` 0x005346F0): both unique, not family, and the table entry
  has an S level.
- **Married partner** (`Unit::GetMarrigePid` 0x0052E634): the first partner in the person's table
  order whose level with this unit is S; the answer is that partner's PID (Person +0x8). No such
  partner: 0. `Unit::IsMarrige` and `GetMarrigePerson` only wrap it (not in this batch).

## 6. Pair-up and the map

- **May two units trade partners** (`Unit::CanDoubleTrade` 0x0052E818): neither unit, its person
  or its class has the PersonFlag bit labelled "pair-up forbidden" (looked up by name once: a
  one-time cache, guard 0x006D99BC), at least one of them has a partner, both are on the same
  force type, and each partner present is on that force type too. The other pair-up readers
  (who may pair, the stance bonuses, the guard-stance move) are the stance batch's.
- **Does this map give support points** (`map::Situation::CanGainReliance` 0x00527EC8): only for
  forces 0 to 2, only without the map's "no support points" flag (Situation +0x4 bit 21), and only
  when that force's byte at the start of the Situation is 1, the same byte `Situation::CanDual`
  reads for stances.

## 7. Checks

**Host differential test:** `python src/readable/support/tests/support_diff.py` (sheet_diff's
method: r0, unmapped reads and the ordered list of guest calls with their argument registers; a
nested give-up is a mismatch). New here: **tail branches**. The game ends some functions with a
plain branch into another function. Where the target is a guest function without an override
(`Person::Get`, the two `GetMaxLevel`s), the readable code makes a guest call and the test lists
the tail branch like a call. Where the target is an override (`Unit::GetRelianceLevel`'s branches
to `Reliance::GetLevel`, `ParentSingle::GetLevel` and `BrotherSingle::GetLevel`), 3dsrecomp keeps a
copy of the target's code inside the caller's generated function. What the tier-2 build shows
(build/readable/verify_support/lib/, re-read 2026-11-15): lib/entries.c gives each of the three
entry addresses (0x00546878, 0x0053B800, 0x0053B864) to its own override, and lists the labels
inside them (0x005468B8, 0x0053B824, 0x0053B888) under f_0052F518; f_0052F518's code (code201.c)
reaches its copies with a plain `goto L_0053B800` / `goto L_0053B864` / `goto L_00546878`, never
through the dispatch. So from `GetRelianceLevel` the original never enters those overrides (other
callers, such as `GetMarrigePid`'s BL to `Reliance::GetLevel`, do enter it). A guest call would add a call the original
does not make and show up as a call-list difference in the live compare; the readable code
therefore runs their C directly, and the test runs such a tail branch on as ARM code, unlisted.
The first version of this batch made guest calls there; tier 2 showed the inlining and it was
changed before any live compare. The
made-up states hold a support table with chains of one to three records (records of another id
in the chain, empty records, odd and even counts, unmapped chain pointers), family records with
real parent / sibling / uncle relations planted between the test units, S entries planted for test
pairs, thresholds of 0, 98, 99, 100 and 255, points from -2^31 to 2^31 - 1, torn units and torn
Persons (records that stop at an offset the readers read) and unmapped pointers.

Results 2026-11-14:

| Run | Cases | Mismatches | Planted bugs |
|---|---|---|---|
| default (`--plant`, seed 20261114, 300 per function) | 7,500 | 0 | 50/50 caught |
| long (`-n 1500 --seed 7`) | 37,500 | 0 | - |
| round 11 default (`--plant`), with the one-parent cases | 7,500 | 0 | 54/54 caught |
| round 11 long (`-n 1500 --seed 7`) | 37,500 | 0 | - |
| round 11 review (`--plant`), uncle1/nephew1 x3, two more plants, whole tree | 7,500 | 0 | 56/56 caught |
| round 11 review second seed (`--seed 7`), whole tree | 7,500 | 0 | - |

Round 11 (tools-fixes): **one-parent uncle / aunt cases.** `focus_pair` gained the kinds `uncle1` and
`nephew1`: the grandparent relation is planted as before, then exactly one parent is cleared, on the
grandparent's side or on the other unit's record (the matching parent or the other one). Four new
planted bugs, one per both-parents test of `unit_is_uncle_aunt` (`has_both_parents` with `||`; the
other's second parent not asked in the grandfather branch; the other's first parent not asked in the
grandmother branch; the unit's first parent not asked at the end of the other way round): all four
caught (50, 3, 2 and 4 mismatches). With the round-10 generator and the same seed the last of them was
NOT caught (build/speed/r11-fixes/support_oldgen.log, scratch): the new cases are what catch it. Runs
on a build/ copy of the tracked sources (other helpers' untracked folders in src/readable/ break the
link step of a whole-tree build at the moment).

Round 11 review: the reviewer planted two more one-parent bugs (the other way's grandfather test without
the unit's second parent; the first way's both-parents test of the unit cut to its first parent). Both
were caught (1 and 8 mismatches at 150 cases per function). They are now in the `--plant` list, and
`uncle1` / `nephew1` come three times as often; with that they are caught by 2 and 13 mismatches. The
first of them stays a thin catch (2 cases of 150): the relation needs the grandfather path, the unit's
second parent cleared and the first way not answering first. Whole-tree runs work again (the duplicate
override is gone from the working tree).

No early give-ups. Only `unit_can_trade_partner` reads a cache; it was cold (both sides gave up at
it) in about 3 % of its cases, by design. Three planted bugs were missed on the first try and the
cases were made sharper, not the bugs dropped: an entry with no level at all (every threshold 99
or more), an unmapped chain node with a negative index (the game reads the node's record word a
second time in `Reliance::Get`), and one plant replaced because it could not change anything (the
family word read again after it was already known to be mapped).

**Tier 2** (`tools/readable/verify.py`'s pipeline with a build/ copy of the registry, HEAD's rows
plus this batch's, staging only the tracked sources plus src/readable/support/ so the other batches'
unfinished folders stay out; only this batch's 25 addresses, `build/readable/verify_support`,
below-normal priority): **21 ABI-ONLY, 1 GAVE-UP, 3 UNSAMPLED, 0 MISMATCH**.

- GAVE-UP: `unit_can_trade_partner`; verify's memory has every one-time cache cold, as in every
  earlier batch. The host test and the live compare cover it.
- UNSAMPLED: `reliance_level`, `family_parent_level`, `family_sibling_level`; verify cannot pick them
  because 3dsrecomp keeps their code inside `Unit::GetRelianceLevel`'s generated function (the tail
  branches above). Nothing compared; the host test covers them, and their other callers (for
  `reliance_level`: `GetMarrigePid`) reach their overrides in play.
- One verdict needed a classifier change (tools/readable/check.py, `nested_bound`): on the first
  build `unit_can_romance` was MISMATCH on a shadow-pass read count only, 90 against 488, with its
  readable pass equal to the interpreter and a "shadow match" logged for it and four nested overrides.
  `IsRomance` calls `IsFamily`, which calls `GetFamilyChildImpl` and `IsFamilyBrotherSister`: two
  levels of overrides, and in shadow mode each level runs its callees' original and readable code
  once more, so each level can double the count. The old rule allowed 4A (one level). The bound is
  now 2^(k+1) A with k = the number of other overrides with a logged match (each level is a distinct
  override; k capped at 5; k = 1 gives the old 4A). Six new self-test cases (64 verdict
  combinations, all pass): 488/90 with four or two nested matches passes, with one it does not, 65/8
  with two does not, a repeated match line counts once, after a give-up it is never a pass.
- **Tightened in round 11** (Grok REVIEW_2026-11-16 finding 1: with k counting every other logged
  override, a function calling many overrides side by side, one level deep, could pass with up to
  64A, enough to hide reads that are not the nested pattern). The bound now uses d, the real
  nesting depth: the longest chain from this override through other logged overrides along calls
  in the game's own code (BL / BLX / B from inside one function's range in config/functions.csv to
  the next function's start, read from extracted/text.bin; `nested_depth`). 2^(d+1) A, d at least 1
  (4A), at most 5; when a call list cannot be read (no text.bin, no function row) d = 1, so it
  fails closed. `unit_can_romance`: IsRomance -> IsFamily -> GetFamilyChildImpl / IsFamilyBrotherSister
  is d = 2, bound 8A, and 488/90 = 5.4 still passes (re-classified from the stored run: 21 ABI-ONLY,
  1 GAVE-UP, 3 UNSAMPLED as before; the stored item, move, sheet, skill, menu and growth runs show
  no MISMATCH under the new rule either). Self-test (made-up call graph): four logged overrides
  only one level deep with 90 against 488 is now a MISMATCH (it passed under the round-10 rule), 90
  against 360 (exactly 4A) passes, a depth-3 chain does not stretch to 32A (90 against 1500 fails),
  and an unreadable call list gives 4A. Planted bug: the round-10 k rule put back -> 3 of these
  verdicts wrong, caught. What a pass still does not prove: that the shadow pass read the same
  cells; only that the surplus fits the nesting the game's code allows.

## 8. Not this batch, and why

- `unit::Family::GetDualSupport` 0x0053B88C and `GetDoubleCapability` 0x0053BB20 (a child's
  stance bonus from its parents): they pass a fifth argument on the guest stack to
  `PersonEnhanceDual::GetEdit`, which `guest_call` cannot do yet (include/readable/fe_guest.h); the
  skill and sheet batches met the same limit.
- `map::DualSupportCalculator::Calculate` 0x00370AB8 and `Unit::GetRelianceScoreImpl` 0x0053114C
  (the pair-up hit / avoid / critical bonus shown in the forecast, and the score behind it): they
  store into the calculator or into the caller's stack words (writers in this project's sense).
  The per-level bonus amounts themselves are the stance batch's `PersonEnhanceDual` readers.
- `Unit::IsRelianceUp` 0x0052DD78, `IsRelianceTalk` 0x0052EA38, `GetChapterReliance` 0x005305C8,
  `GetChapterRelianceRank` 0x00531580: larger readers of the support-conversation and
  per-chapter limits; a good next batch.
- `ParentSingle::GetMaxLevel` / `BrotherSingle::GetMaxLevel` (8 bytes each, "answer 3"),
  `Unit::GetFamilyChild` (a 4-byte no-op that falls into `GetFamilyChildImpl`), `Unit::IsMarrige`,
  `GetMarrigePerson`: too small to be worth an override; the readable code calls the first two.

## 9. Where these will be met (live compare)

`Unit::GetRelianceLevel` is asked in every fight with a pair-up or an adjacent ally: the stance
readers called it 303 times over the round-9 capture runs (their callback counts). Each such call
runs `GetFamilyChildImpl`, `IsFamilyBrotherSister`, `Reliance::GetFromPerson`, `Unit::GetReliance`
and `Reliance::GetLevel` (and the family parts for child units) [high: the code path; med: that the
round-10 routes reach each one]. `CanGainReliance` runs after every fight; `CanDoubleTrade` when
the unit menu is built for a unit next to a pair; `IsReliance`, `GetRelianceMaxLevel` and
`GetMarrigePid` on the support and status screens and in My Castle. Child units and families appear
only after the child paralogues (none of the current routes [med]): the family readers will probably
be met only on cheat routes, as `family_grow` was.
