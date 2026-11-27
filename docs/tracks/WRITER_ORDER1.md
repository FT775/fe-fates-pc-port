# Writer order, after the readers run out

**For the owner.** OK A is a yes to a test copy, not a yes to changing the game. On that copy, the options writer is allowed to store. Your game, your saves, and the three plays running now are not that copy. Saying yes does not turn on a class change, a level-up, a shop, or an enemy's choice. The only risk is the robot's own test game: if the undo fails, that test save is thrown out. A green test still does not switch anything on. That needs a second yes, for that one writer, after the three numbers pass.

Status 2026-11-17. Read: `docs/DECISIONS.md` F-021 and F-026, `docs/OPTIONS_WIRING.md`, `docs/collab/WRITERS_PLAN_GROK.md`, and the notes that name a store. Names only from those notes. No address copied. No game file opened. This note does not ask for OK A.

Every row below stays off in the game you play. A row is not even offered until, for that writer and the functions it calls: recordings on the lines a recording reached (lines never reached are listed, not counted), the host test catches every planted bug that can change a stored byte, a person has judged the "cannot change an answer" cases on its files by a written rule, and a live compare of the routes that reach it shows zero differences (F-026, F-018). Then your OK in chat, for that writer. A cheat run is not the proof.

## The order

| # | What a mod would ask | Names, from the notes | Proof, when its turn comes | Do not |
|---|---|---|---|---|
| 1 | Remember my options | `config_write_options`. Already written, gated, off. It is the only one with a screen and a host test | The options routes already recorded. Checks T1 through T6 in the wiring note. A suspend save must be in that set. OK A is the test copy that lets this one store | The play build. Your saves. A second writer in the same test |
| 2 | Battle pictures and game speed | `Battle::SetValue`, `GameSpeed::SetValue`. The menu note: they store the bytes the screen already has | The same options routes, on the same test copy, after row 1's three numbers pass. A route whose speed or pictures change must be recorded that way. The old routes cannot be replayed at a different speed | Treating a display change as free if the fight's dice change (wiring check T7). If they change, the page must say so |
| 3 | The danger zone | `DangerPanel::SetValue`. The menu note: it stores, then rebuilds the zone | Wiring check T3, on a test route that turns the zone on. Not a real-play chain | `Danger::Update` as a writer of its own. The helper already returns who it would mark |
| 4 | A fixed level-up | `Unit::LevelUp`. The growth note: this is the roll. `GainExp` only starts the bar. `LevelUpCalculate` only copies | A route that already levelled (`bt-ch8` is the tight one). Planted bugs on the stored gains. No new chapter | The window ticks. A fixed-growth switch in the game you play |
| 5 | A class change | `Unit::ClassChange`. The class note: this is the change. `MergeSeal` and `SetSeal` store too | No route spends a seal. Do not start until a note names one that does. Do not add a chapter to find one | `ClassChangeCalculate`, `ClassChangeReflect`, and the enumerator fillers. They store. A guessed seal name |
| 6 | What one strike stores | `Side::CalculateDetail`, `CalculateDetailHit`, `CalculateDetailAttack`, `CalculateEfficacy`. The battle note: they store into the fight. The pure part is already a reader | A fight already on disk, one route, and only after rows 1–3 are green. The live compare must match the whole fight, not just the number | `RandomCalculateHit`. It advances the dice. `CalculateSimple` and `Calculate` |
| 7 | How the enemy picks | `AIThink::GetAttackScore`, `GetDestroyScore`, `GetInterferenceScore`, `GetEntrustAttackScore`, `GetEntrustHealRodScore`. The score note: they store through out-pointers and advance the random roll | Not until a read shows a helper that returns the number and does not roll. Enemy-phase routes already exist. Do not add one | `MoveTo`, `AttackTo`, and the other functions the AI note says act |
| 8 | Using an item | `Unit::ItemUse`, `Unit::Handover`. The capability note: they store. Named and left out | A route that already uses a vulnerary or trades. One route. After the level-up row, not beside it | The buy action |

## The first three after OK A

Rows 1, 2, and 3. They share the options block and the routes already recorded. Row 1 is the test OK A exists for. Rows 2 and 3 are the switches a player actually flips, proved on that same test copy, one at a time. Row 2 does not start until row 1's three numbers pass. Nothing in this three writes a unit.

## Not in the order

The shop's gold change is not named. The shop note says so. None is guessed. `Transporter::Add` and `ItemBuyMenuItem::ACall` store an item, not a price rule, and they are not a first try. The volume setters store sound. They wait behind row 2. The class-change window is a picture, not a rule.

## What stays off

- The game you play, your saves, and every real-play chain.
- Rows 4 through 8, until each has its own three numbers and its own yes.
- A cheat-track run as proof.
- The emulator rebuild. It is a different ask, and it is not this path.
