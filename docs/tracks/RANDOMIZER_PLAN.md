# A Fates randomizer, planned now, built later

**For the owner.** This is a plan for after the port is finished. Nothing here is built. A full randomizer changes who people are, what they grow into, and what they hold. It does not rewrite the rules. The public tools already edit the tables. Our job later is to keep the game finishable, and to check the result with the readers we already have. Writers stay off until you say yes to each one.

Status 2026-11-17. Public tools only. No code copied. No game file opened. Paragon is GPL. Do not copy it. [https://github.com/thane98/paragon](https://github.com/thane98/paragon)

## What the public tools actually do

Paragon edits a whole Fates ROM (it calls the game FE14), not one file at a time, so a change in one table can be seen in the others. You describe an editor in a text file and it builds the screen. It is a toolkit, not a one-button randomizer. The Fates randomizer that people run writes a list, and you apply the personal skills by hand in Paragon. [https://github.com/lashoun/upgraded-fefates-randomizer](https://github.com/lashoun/upgraded-fefates-randomizer) That script says it improves an older work-in-progress randomizer. [https://gbatemp.net/threads/wip-fire-emblem-fates-randomizer.452268/](https://gbatemp.net/threads/wip-fire-emblem-fates-randomizer.452268/)

FEBuilder is the same idea for the old handheld games: class, person, item, map, support, and shop editors, then a playtest. It does not open Fates. It is here as the shape, not as a source to port. It is also GPL. Do not copy it. [https://github.com/laqieer/FEBuilderGBA](https://github.com/laqieer/FEBuilderGBA)

## What a full one usually changes

Ranked by what those tools already do, and by what would break a run if it were wrong.

| # | What changes | Tables, as the tools describe them | Our notes | Built only after |
|---|---|---|---|---|
| 1 | Who is which class, and whether that class may hold the weapon | Classes, and the class's weapon list. Our notes call the class table Job | `Job::Get`, `Job::CanEquipFromSubKind`, `Job::IsFemale`, `Job::IsHigh` (already a reader). `Unit::ClassChange` is the writer and stays off | The port is finished. No new class rows |
| 2 | How fast someone grows, and the stats they join with | Characters plus classes. A public script spreads bases and growths, then scales them to the level of the spot they join | Growth readers already written. `Unit::LevelUp` is the roll and stays a writer. The preview helper returns what the roll would store and does not store | A table edit, checked by the growth host test. Not a new roll |
| 3 | What an item does, and who may hold it | Items. Might, hit, uses, and who may equip | Item readers, `Unit::CanItemEquip`. `Unit::CanItemUse` is still blocked. Do not start it for this | The equip check on a preparations screen already recorded |
| 4 | Which skills a person has | Skills, and the person's skill list. The public script prints a suggestion. A person still types it into Paragon | `Unit::IsEquipSkill`, `EquipSkill::Get`. Learning a skill is a writer | Skills stay on people who already have skill slots. No new skill rows |
| 5 | Where someone joins, and at what level | The chapter's unit list, not a new person. The public script can keep the face and still change the class | No join function is named in our notes. Do not invent one. The castle join scene stores, and it stays off | Swap existing people into existing spots. Do not add a person |
| 6 | What the enemy brings | The same unit list, enemy side, plus class and item | AI permission readers. The score bodies store and stay parked | Enemy gear is a table edit. Do not rewrite how the enemy thinks |
| 7 | Shop stock and prices | Shop tables, and the item's price. The gold change itself is not named in our notes | Shop price and greying readers. `ItemBuyMenuItem::ACall` is the buy, and it stores | Prices as a table edit. Do not invent a gold writer |
| 8 | Who can support whom | Supports. A separate public patch widens who can marry. That patch is not this randomizer | Support readers. The stance note's apply step may store. Do not start it | Pairs that already have a slot. No new child to open a chapter |
| 9 | Children | The child list and the parent's last equipped skill. A public option turns children off entirely | No child reader has a route. Do not play a chapter to find one | Last. Off until a route exists |
| 10 | Maps | Placement and terrain. Our port already turns those into spreadsheets | Map tools, not a runtime writer. A vein user still has to be able to use a vein | One tile or one moved unit, seen in game, before any random map |

## Pitfalls the public tools already guard

- A class the person cannot be. The public script refuses a promoted person in a class it cannot apply, and it has a switch so a download class is not locked to one gender. Our `Job::IsFemale` and `Unit::IsFemale` are the checks. A random class that fails them will not equip, or will not be offered.
- A staff user replaced by a fighter. The script has a switch to stop that. A map that needs a heal or a freeze then has nobody who can do it.
- A door or a chest and nobody who can open it. The script keeps that skill on the replacements for the two people who usually have it. Our `Unit::CanKeyDoor` is the check, once that reader exists.
- A story that needs a particular person. The singer, the two lords, and anyone a vein calls. Public guides for the late maps tell you to bring someone who can use a vein. If the randomizer removes the last one, the map does not end. Keep at least one vein user on those maps. [https://www.thonky.com/fire-emblem-fates/chapter-21-eternal-stairway](https://www.thonky.com/fire-emblem-fates/chapter-21-eternal-stairway)
- A flier the map assumes. The upgraded script changes one tile on two ninja maps because the door could not be reached without a flier. Do not randomize away the last flier on a map that has no other path.
- The wrong route's join levels. The script asks which story you are playing, and says Revelation levels are wrong if you do not. A Birthright list is not a Conquest list.
- The face and the person disagree. The script can change the class and the stats and leave the model. Do that first. A swapped face is a later phase.
- Children and the ending. The script can ban children. Do that until a child route exists. It also tried to allow a save on the endings and said that was not tested. Do not count on it. Our notes already say those endings have no save.
- Personal skills are a hand edit. The script does not write them into the ROM. Paragon does. Our randomizer should not pretend a printed list is applied.

## Build order, after the port

1. **Tables only.** Class, growth, and bases, on rows that already exist. No new person, no new class, no writer. The growth host test and one in-game look are the proof.
2. **Items and skills,** same rule. The equip check and the skill check must still agree with the game.
3. **Join spots.** Existing people, existing chapters, the safety list above turned on. One story first. Birthright, because that route is the one we have played through.
4. **Enemies and shops.** Gear and prices. Not AI. Not gold.
5. **Supports, then children, then maps.** Each one waits until a route already meets it. A random map is last, and only after one edited tile has been seen in the game.

Nothing in this list turns a writer on, adds a person, or copies a public tool.
