# Rewrite order after the named readers ran out

ELI5 / ETA: The last list is used up. This is the short list of leftover readers the notes already name. Nothing is rewritten here. A name that is not in a note is not in this list.

Status 2026-11-17. This list is used up (rows 1–4 and 6 done; row 5 still blocked). Next readers: `docs/tracks/REWRITE_ORDER4.md`.

A batch stops when a new function adds no behavior the tests can see. One large function can be the whole batch. Do not pad it with a window.

What a later randomizer would need to read, from a public editor rather than from memory: Paragon edits this game's tables as one ROM. It is GPL. Do not copy it. These batches are the runtime readers those table changes would pass through, where a note already names the function. [https://github.com/thane98/paragon]

## The list

| # | What a mod would ask | Names, from the notes | Reached by | Do not |
|---|---|---|---|---|
| 1 | May this unit hold or use this item | `Unit::CanItemEquip`, `Unit::CanItemUse`. The item note left both out as too large (about 3,300 and 3,100 bytes). One function is a batch | One preparations screen and one fight already recorded. Capture cap: 8 routes or 45 minutes, then stop (`docs/collab/DELAYS_R14_GROK.md`). Do not add a chapter | The buy action, and any function that stores the item |
| 2 | What a staff does, and how far a weapon reaches | `Unit::GetRodHealPower`, `GetInterferenceRodHit`, `GetInterferenceRodAvoid`, `Unit::GetRangeO`. The item note says round 11's five-argument call lifts the old stack limit for the rod readers. Read that call before starting. If it still cannot pass the extra word, stop | Routes whose last coverage met a staff or a range caller, at most 8. "Fight routes already on disk" is not a capture list. If none used a staff, write "not here". Do not add a map | `GetSimplePower`. A damage switch is still not this |
| 3 | The stat getter a class change would pass through | `Unit::GetCapabilityImpl`, `GetCapabilityRating`, `GetNoWeaknessCapabilityRating`. The sheet note says the call cannot pass the stack word. The item note says the five-argument call may lift that. Read the call. If the limit is still there, this batch does not start | The status sheet and every fight already call the stats. A new chapter is not required | Anything that stores a stat. `Unit::ClassChange` and `MergeSeal` stay writers |
| 4 | What the shop window greys out | `ItemBuyMenuItem::IsPriceDisable`, `GetStock`, `GetBuySellMax`. Named in the shop note and left out of that batch. The gold writer is still unnamed. Do not invent it | The five shop routes the shop-price batch already recorded, plus the cheat forge route | `ItemBuyMenuItem::ACall`, `Transporter::Add`, and any draw function |
| 5 | Two script questions with no caller | `UnitGetWeakness`, `UnitTstEnhance`. The battle note says no direct call, only a chapter script could use them, and none is named. Do not start until a note names the script that calls one | None yet. Do not play a chapter to find one | A guessed script name |
| 6 | The weapon-rank line on the unit screen | `GameInfoViewer::GetWeaponLevelKind`. Named and not looked at. Low value. Do this last, or skip it if the round is full | A unit screen already opened (`bt-ch8-options` opened Units). Do not add a chapter | The rank-up window, and `AddWeaponExp` |

## What this list does not do

- Chapter talk, status, or capture. No name in the notes. Batches 8, 9, and 10 of the old list stay closed.
- The parked attack scores, `MoveTo`, `AttackTo`, and the other functions the AI note says act.
- A child, a capture, a seal spent, or a Conquest or Revelation chapter, to light a line up.
- A third batch in a round where one of the first two is still red.

## When it can start

Batch 1 is the equip check, on a preparations screen already recorded. Batch 3 waits on a reading of the five-argument call. Batch 5 does not start.
