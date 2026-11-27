# Rewrite order after the leftover list

ELI5 / ETA: The last short list is used up. This is the next handful of readers the notes already name. Nothing is rewritten here. Two of them can run at once, in separate folders. No new chapter.

Status 2026-11-17. All six rows are done (rounds 21–23). Next readers: `docs/tracks/REWRITE_ORDER5.md`. Few remain.

A batch stops when a new function adds no behavior the tests can see, or when a read of the body shows it stores. New files only. Do not edit `src/readable/equip_use/`, `src/readable/battle/`, `src/readable/ai_score/`, `src/readable/menu/`, or `src/readable/unit/`.

What a later randomizer would need to read, from a public editor rather than from memory: Paragon edits this game's tables as one ROM. It is GPL. Do not copy it. [https://github.com/thane98/paragon]

## The list

| # | What a mod would ask | Names, from the notes | Reached by | Do not |
|---|---|---|---|---|
| 1 | How hard does this one strike hit | `Side::GetSimplePower`. The formula note calls it a const reader, long, and the next candidate. Skills, the half-damage skin, and terrain are inside it | Any fight already on disk. Capture one, not all of them | `CalculateDetail`, `CalculateSimple`, and the other stores. `GetSimpleTimes` is already a reader. Not a damage switch |
| 2 | May this class hold this kind of weapon | `Job::CanEquipFromSubKind`. The equip note and its header both say not rewritten. It was read: a one-time cache, nothing else | A preparations or fight route that already met the equip check. One route | The buy action, `Unit::ItemEquip`, and `CanItemUse` (still blocked: it builds an object on the stack) |
| 3 | Is this unit, or this person, female | `Unit::IsFemale` (equip note: not rewritten, cache only). `Person::IsFemale` (growth note: still a guest call). If a note has since made either an override, skip that one | Any preparations screen already recorded. One route | A guessed spouse or child rule. Do not add a chapter to meet a child |
| 4 | May this staff be used on that unit | `Rod::CanUseTarget`. The score note and its header: a reader, stores only into its own caches, about 2,200 bytes, not rewritten | A route whose last coverage met a staff. At most 8. If none did, write "not here" | `AttackTo`, the score bodies, and `Random::GetValue` |
| 5 | Does this carried item add its bonus | `Unit::IsItemEnhanceHave`. The battle note left it as too big (about 2,500 bytes, 12 caches), not as a store. Read the body first. If it stores, stop | A fight already on disk. One route | A new map to meet one bow. The forge window |
| 6 | How loud are the four volume lines | The four `Volume*::GetValue`. The menu note: not rewritten, they scale the byte. The setters stay writers | An options screen already recorded (`bt-ch8-options` or an `opt-*` route). One route | `SetValue`, `Deserialize`, and the options writer |

## Which two run first

**Rows 1 and 2, side by side.** They do not share a file if row 1 is only new files under `src/readable/strike/` and row 2 is only new files under `src/readable/who_holds/`. Row 1 is what a modder asks first. Row 2 is small and already reached, so the round still finishes a batch if the strike reader runs long. Do not start row 3 until row 2 is green: it would be the same kind of work in a second folder, and two small ones plus the strike reader is a third batch.

Capture waits until a play slot is free. Six game copies at once, nothing heavy beside a capture. One route each, inside the 45-minute cap. No capture while that batch's host test still misses a planted bug.

## Do not start

- `UnitGetWeakness`, `UnitTstEnhance`. Still no caller in the notes.
- `Unit::CanItemUse`. The equip note says the tools cannot write it yet.
- `Force::Get`. Named, and it only reads, but the score header says it is one empty instruction into a pool lookup. Not worth a batch while the three plays are running.
- The parked score bodies, `MoveTo`, `AttackTo`, class-change stores, and the gold writer. Those are writers.
