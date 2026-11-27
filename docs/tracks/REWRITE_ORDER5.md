# Rewrite order after the six leftover readers

ELI5 / ETA: The last list is done. Few readers are still named. This is the short list the notes still call out. Two small ones can run at once, in separate folders. No new chapter. After these, what the notes still name is mostly writers.

Status 2026-11-17. `docs/tracks/REWRITE_ORDER4.md` rows 1–6 are done (rounds 21–23). Names below are copied from the notes. No address copied. No new search of the symbol list. Writers stay off until OK A (`docs/collab/WRITERS_PLAN_GROK.md`). Capture cap: 8 routes or 45 minutes. Conquest and Revelation are being played (F-031). These batches do not take a play slot.

Progress (integrate notes, not Grok's text): row 1 done round 25 (`job_female_is_female`); row 2 done round 25 as a tested helper, not an override (stop rule); row 3 done round 26 (`skill_record_by_name`, override, captured bt-ch4 22/22 match); row 5 done round 26 (`key_door_unit_can_open`, override, captured bt-ch4 19 match, 1 cold give-up). Row 4 done round 27 (`person_record_by_name`, Person::Get(const char*), override, captured bt-ch6-castle 20/20 match; Person::Get(unsigned short) is a tested helper `person_record_get`, not an override, because AIValue::GetPerson runs into it). All five rows are done.

A batch stops when the function adds nothing the tests can see, or when a read shows it stores. New files only. Do not edit `src/readable/female/`, `src/readable/class_change/`, `src/readable/unit/`, `src/readable/ai/`, or `src/readable/skill/`.

## The list

| # | What a mod would ask | Names, from the notes | Reached by | Do not |
|---|---|---|---|---|
| 1 | Is this class the female one | `Job::IsFemale`. The female note: same shape as the unit check, on the class alone, and it was not rewritten | Any preparations screen already recorded. One route | A spouse or child rule. Do not edit the female folder |
| 2 | The class record for a class number | `Job::Get`. The class-change note still calls it as a guest. Its header: reads only, walks the loaded class blocks, not rewritten | Any fight already on disk. One route | `Unit::ClassChange` and the seal stores. Do not edit the class-change folder |
| 3 | The skill record for a skill name | `EquipSkill::Get`. The class-change note: a hash lookup, still answered as a guest, not an override. Its header: reads only | A fight that already met a skill check. One route | Learning a skill, `AddEquipSkill`, and the picture |
| 4 | The person record for a person name | `Person::Get`. The growth note still lists it under guest calls left. The castle-join note: a hash lookup | A preparations or join route already recorded. One route | A join that stores the unit into the army |
| 5 | Can this unit open a door | `Unit::CanKeyDoor`. The AI note still answers it as a guest, and not as an older override. Its header: reads, one cache, not rewritten | An enemy-phase route already on disk. One route | `IsMoveNear` and `IsEnemyInsideAttackArea` (they store a move image) |

## Which two run first

**Rows 1 and 2, side by side.** Row 1 is only new files under `src/readable/job_female/`. Row 2 is only new files under `src/readable/job_record/`. They do not share a file. Both are small, both are already reached, and neither needs a chapter. Capture waits for a free slot: one route each, inside 45 minutes, and only after that batch's host test is green.

Row 1 is the class twin of a check that just landed, so it should be quick. Row 2 is what a class mod asks first. Do not start row 3 until one of those two is green. Three batches beside two plays is how the machine timed out before.

## How many readers are left [low]

Five named readers are worth a batch. That is this list. `Force::Get` is still marked not rewritten in the score note, and it is not a sixth batch: the callee note says it is one empty instruction into a pool lookup the readable code already does itself. An override of that shape was tried once (`UnitPool::Get`) and taken out, because the checker could not pick the address. Do not spend a helper on it.

Also named, and not a batch: `Unit::CanItemUse` (still blocked: it builds an object on the stack), the two script questions with no caller, the shown-hit curve and the terrain-under-a-figure reader (both floating point; readable C does not do that), and `GameUserData::Get` (one word). The forge getters are named only as a group, with no function name. None is invented here.

After this list, what the notes still name one by one is writers: the score bodies, class change, the gold change, the fight's own stores, the level-up roll. Fewer than ten named readers are left in the notes. About five are worth doing. Then the named work is writers. This is a guess from those lists, not a count of the symbol list.

## Do not start

- `Force::Get`, for the reason above.
- `AIValue::GetPerson` and `AIValue::GetJob`. The AI header says each falls into `Person::Get` or `Job::Get`. Same shape as the lookup that was taken out. Do them only after rows 2 and 4 are overrides, and stop if the checker cannot pick the address.
- `map::CannonCalculator::Calculate`. The triangle note says not rewritten. It does not say the body only reads. No recording is known to meet a cannon. Do not add a chapter to find out.
- `map::DualSupportCalculator::Calculate`. The stance note says not rewritten. "Applying" may store. Stop unless a read shows it only reads.
