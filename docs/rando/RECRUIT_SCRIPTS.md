# Character shuffle research: where the game names a character outside the Person table

**In plain words.** A character shuffle means one character takes another one's place where they join (in the
FE8 port this is called Recruitment). This page counts every place in the game files that names a character by
their ID, outside the main Person table. It sorts the places into two groups. The first group must be rewritten,
or the game can freeze or the character never joins. The second group is only flavour: it shows the wrong face
or a line meant for someone else, but nothing breaks.

The answer: if each join spot **keeps its ID and only changes who it is** (face, model, name, voice, stats,
class, skills: the way the FE8 port does it), **none** of the script, map or castle references below needs a
rewrite, and nothing found here can crash or softlock. What is left is flavour. In dialogue, the old character's
portrait and name box still show, because a dialogue line names the face directly, not by ID. If the IDs are
moved around instead (the way the public tools do it), about 2,300 references in about 260 files all have to
change together. That is how the public tools ended up with their known bugs.

Status 2026-11-20, round 53 side job "scripts" (host only: no game runs, no builds). Read only from the owner's
own extracted RomFS with throw-away scanners in the session scratchpad (not tracked). No game text, no table
values and no code from the GPL tools are copied here. Only counts, ID kinds and format facts. Character
names are the usual English names. Confidence: [high] = counted or read directly, [medium] = inferred from
names or structure, [low] = a guess to check.

"Playable" below means the 49 people that slice 1 works on (`randolib.Facts.in_scope`: the player army, minus
children, bond units, capture-only, downloadable and enemy-only rows). Corrin (both) and Azura are in that set,
but every plan keeps them fixed.

---

## 1. Totals at a glance

| Where | Files | References to a playable ID | People named | Must change if IDs move? | Must change if the spot keeps its ID? |
|---|---:|---:|---:|---|---|
| Event scripts `Scripts/**/*.cmb` (chapter scripts) | 89 of 113 | 552 (286 event arguments + 266 in code) | 49 | yes | no |
| Event scripts: terrain, system, 3D cutscene (`bev/`), amiibo | 4 of 511 | 7 | 4 | yes (small) | no |
| Map placements `GameData/Dispos/**` (DisposUnit.pid) | 103 | 1,497 placements | 49 | yes | no |
| Chapter people `GameData/Person/<chapter>` and `<route>/<chapter>` | 53 | 194 strings (not a decoded field; see 4.3) | 43 | yes | no |
| Route handover `GameData/Person/{A,B,C}_HANDOVER` | 3 | 27 (A 6, B 5, C 16) | 27 | yes | no |
| `GameData.bin` (Person table itself + a second, undecoded list) | 1 | 49 + 51 | 49 | yes | no |
| Castle join list `castle/castle_join.bin.lz` (docs/CASTLE_JOIN.md) | 1 | 6 | 6 | yes | no |
| Castle buildings `castle/castle_building.bin.lz` | 1 | 49 | 49 | flavour | no |
| Preset visitor castles `castle/preset/unit/*.bin.lz` | 13 | 130 (10 each) | 10 | flavour | no |
| Portrait records `face/FaceData.bin.lz` | 1 | 47 | 47 | no (they belong to the face) | no |
| Chapter dialogue `m/**/<chapter>` (speaker codes, by face name) | 102 archives | 5,384 portrait (`$Wm`) + 11,643 name-box (`$Ws`) codes in 2,101 messages | 47 | yes, to follow the swap | flavour (old face shows) |
| Support conversations `m/@E/<person>_<partner>` | 441 with a playable first name | 3,222 `$Wm` + 27,191 `$Ws` | 47 | no (they belong to the person) | flavour |
| Death and retreat quotes (one archive each) | 2 | 47 + 47 messages | 47 | no (they belong to the person) | flavour |
| Endings `m/@E/Ending` | 1 | 194 labels name a playable person | | no (they belong to the person) | flavour |
| Castle talk, daily events, My Room greetings, Live2D (69 archives) | ~600 | about 9,700 labels, 980 `$Wm` | 38 | no (they belong to the person) | flavour |

The ID total that would have to move together: about 552 + 7 + 1,497 + 194 + 27 + 51 + 6 = **about 2,330
references in about 265 files**, plus the chapter dialogue codes, if dialogue is to follow. [high for the counts]

---

## 2. Two ways to shuffle, and which places each one has to touch

**Way A: the spot keeps its ID and changes who it is** (the FE8 port's way. Its recruit code says the slot
"keeps its pid, so every event script, talk and check that names it still works"). Only the slot's Person row is
rewritten: `fid` (face), `aid` (model), `mpid_name`, `mpid_help`, `voice`, `combat_music`, the female flag
and `body_type`, plus class, stats, growths and skills, which slice 1 already writes. Every script, map and
castle reference in section 1 still points to a row that exists. The unit is on the map where the script
expects it, so nothing can crash or softlock because of a missing unit. Maps, menus, the stat screen and
battle all read the face through `Person.fid` (`FaceInstance::LoadByUnit` reads it and skips the `FID_`
prefix) [high], so they follow the swap with no extra work.
What does **not** follow (flavour): dialogue portraits and name boxes (section 5), supports, death and retreat
quotes, endings and castle lines. These stay the slot's original character's, with that character's face inside
the dialogue. Making them follow needs a runtime face and name swap at the point where the game draws them.
That is what the FE8 port hooks (`GetPortraitData` and the text decoder). In Fates the matching places are
`FaceDataManager::GetFaceData(const char*, ...)` and the name plate (`TalkCodeFactory::ChangeNamePlate`)
[medium]. That would be an engine build and needs the owner's OK. It is not part of "a schema row appears
without an engine build".

**Way B: move the IDs** (the public tools' way: the new person's ID is written into the old one's places).
Every "yes" row in the "if IDs move" column must change in step. A missed place leaves the old character on the
map, or two copies of one character, or a talk that never fires. The event scripts are the hard part. A
script names a character through its own string table, and the code reaches those strings by byte offsets.
Some offsets are only one byte, so they reach only the first 256 bytes of the table (section 3.1). Japanese
IDs differ in length, so replacing one changes every offset after it. The whole table and every
offset in the code must be rebuilt. The public tools' known breaks match the places Way B has to get right
(section 6).

**Recommendation (for the design step):** Way A, data only, as the first build. It needs no script, map or
dialogue rewrites and has no crash path from this survey. The dialogue showing the old face is a known flavour gap,
stated on the page. A later engine-build "faces and names follow" switch would close it, the way FE8 does.

---

## 3. Event scripts (`Scripts/`, 624 `.cmb` files)

### 3.1 Format facts used for the count (read here, Awakening-family `cmb`) [high]

- Header: magic `cmb`, then at +0x1C the offset of the event list (u32 pointers, ending with 0), and at +0x20
  the offset of the string table (NUL-ended cp932 strings).
- Event record: +0 self, +4 code start, +8 event type (u8), +9 argument count (u8), +0xC index, +0x10 name
  pointer (helper functions), +0x14 pointer to the arguments (s32 each). An argument that equals a string's
  offset is a string, for example a character ID.
- Code: `1C nn` pushes the string at table+nn (one byte). `1D hh ll` pushes the string at table+hhll (two
  bytes, big-endian). `47 hh ll nn` calls the built-in named by the string at hhll (`ev::...`) with nn
  arguments. `46 nn` calls a helper defined in the same script. `19`/`1A` push small numbers. `54` returns.
- The counts link each pushed ID to the next built-in call. That is exact for a simple call, and close enough
  for counting by kind.

### 3.2 Files

| Kind | Files | Naming a playable person | References |
|---|---:|---:|---:|
| Chapter scripts (`A000`-`A006`, `A/A007`-`A028`, `B/`, `C/`, `P006`, `M001`-`M004`, `X001`-`X022`, `Z000`/`Z001`, `?Y0n`) | 113 | 89 | 552 |
| `*_Terrain.cmb` | 108 | 2 | 2 |
| System (`Castle`, `Command`, `Encount`, `GameOver`, `Versus`) | 5 | 1 (`Command`: Corrin) | 3 |
| `bev/` 3D story cutscenes | 394 | 1 | 2 |
| `amiibo/` | 4 | 0 | 0 |

The 394 3D cutscene scripts almost never name a character ID. They name models and scenes by asset name.
So a shuffle never touches them, and they keep showing the original character (flavour). [high for the count,
medium for "by asset name"]

### 3.3 Event types that carry a character ID as an argument [high for counts, medium for the meaning]

| Type | Meaning (from its arguments and the built-ins it calls) | All | With a playable ID | Swap needs |
|---|---|---:|---:|---|
| 0x17 | **Talk command** between two units (ID, ID): the "Talk" on the map. 33 of them move a unit into the army (`UnitGetByPID` + `UnitTransferByIndex`) or give an item | 48 | 44 | Way B: both IDs, or the recruit never happens (a lost recruit, or worse in Conquest 9) |
| 0x18 | **Battle conversation**: a boss or story enemy against a named attacker (any = -1) | 336 | 173 (in 169 the playable person is the attacker) | flavour: the line plays for the slot |
| 0x1B | **Defeat event**: a line when that unit falls (side 0/1/2) | 222 | 31 (12 ally, 11 player, 8 enemy side) | flavour, except the guarded chapters (section 6) |
| 0x1D | Visit / pick event tied to a unit (prologue tutorials) | 19 | 12 (Corrin only, and chapter-local people) | none: Corrin is fixed |
| 0x20 | Test map event (Z000) | 1 | 1 | none |

### 3.4 Built-ins that receive a playable ID in code (266 pushes)

| Built-in | Pushes | What it does with it | Swap needs |
|---|---:|---|---|
| `ev::UnitGetByPID` | 164 | gets the unit, then moves it, changes its army (`UnitSetBID`, 32 calls in all scripts), points the camera, plays an effect, checks it is alive | **must find the unit**. Way A: always does. Way B: every one rewritten, or the event acts on no unit (a softlock risk in scripted joins and leaves) |
| arguments to script helpers (`46 nn`) | 94 | same, inside a helper | as above |
| `ev::UnitIsPID` | 12 | a branch on who did something: Corrin in A002, A003, A005, A006, B006, X002, Command; Azura and Gunter in B015; Rinkah and Sakura in B006 | flavour, except the B015 Gunter story (keep Gunter fixed) |
| `ev::UnitIsMotherPID` | 2 | child paralogue checks (X014: Corrin; `bev/X013_ED1`: Selena) | children are off (F-043 #4). Way A keeps the parent tied to the slot |
| `ev::UnitGetByPIDForce` | 1 | B015 Gunter, even when he is not deployed | keep Gunter fixed |

Other built-ins that move people: `ev::Dispos` 1,081 calls (places a named group), `ev::PersonLoad` 138,
`ev::UnitTransferByIndex` 90, `ev::JoinGuest` 4, `ev::ForceUnitTransfer` 2, `ev::UnitRecreate` 1 (B016's
hidden boss), `ev::UnitIsDoubleChild` 8, `ev::ChapterSetInvalidGainReliance` 2, `ev::UnitGetRelianceLevel` 1.

### 3.5 Scripted joins and story moves (the "Zero/Kaze style" recruits)

The script hands these people to the army (`UnitTransferByIndex` / `JoinGuest` / `ForceUnitTransfer` on a
unit it got by ID). There are 37 (chapter, person) pairs, not counting Corrin [high]:

| Chapter | People |
|---|---|
| Birthright 8, 9, 10, 11 | Azama, Hinoka, Setsuna; Hinata, Hinoka, Oboro, Sakura; Azura, Takumi; Reina |
| Birthright 13, 19, 20, 21, 27 | Hinoka; Hinoka; Azura, Hinoka, Ryoma, Sakura; Felicia, Hinoka, Jakob, Ryoma; Azura, Hinoka |
| Conquest 9, 14 | Nyx; Keaton |
| Revelation 7, 10, 11, 14, 15, 21 | Gunter; Gunter; Orochi, Reina, Saizo; Benny, Charlotte; Nyx, Shura; Gunter, Xander |
| Paralogues X001, X015 | Mozu; Xander |

The Talk-command recruits (type 0x17 with a transfer) are among them: Birthright 8 Hinoka, Birthright 9
Hinata/Oboro, Birthright 11 Reina, Conquest 9 Nyx, Conquest 14 Keaton, Revelation 11 Saizo, Revelation 14
Benny/Charlotte, Revelation 15 Nyx/Shura, Paralogue 1 Mozu. Most other people join by being placed in a
chapter's player group (section 4.1), not by script.

---

## 4. Tables and other files

### 4.1 Map placements (Dispos) [high]

1,497 placements of playable people in 103 Dispos files. By side and group:

| Side | Group | Placements |
|---|---|---:|
| player (0) | `Player` | 1,145 |
| player (0) | `Event` (story groups the script places) | 295 |
| player (0) | `Support` | 30 |
| player (0) | `PlayerM` / `PlayerF` (the two Corrins) | 10 |
| other (1 enemy, 2 ally) | `Enemy`, `Reinforce`, `Ally`, `Event`, `Support` | 17 |

People who first stand on another side and join later: Azama, Hinata, Hinoka, Oboro, Setsuna (Birthright 8-9),
Takumi (Birthright 10), Reina (Birthright 11, Revelation 11), Leo and Keaton (Conquest 14), Gunter (Conquest
15), Nyx (Conquest 9, Revelation 15), Benny and Charlotte (Revelation 14), Shura (Revelation 15), Mozu
(Paralogue 1). Way A: nothing to change, though the spot's class needs (a flier where only fliers stand) belong
to the spot (section 6). Way B: every placement, in every difficulty row.

### 4.2 Route handover

`GameData/Person/A_HANDOVER`, `B_HANDOVER` and `C_HANDOVER` hold the route-start copies of the people who carry
over into a route (6, 5 and 16 people). Revelation's list is the longest and includes Hayato. [high for the
counts] The copies have their own IDs, and the playable ID sits in the same string pool as a link [medium].
Way B must rewrite these along with the scripts and maps. If only one of them is rewritten, the result is two
of one person or a missing one. That may be what is behind the public tools' Revelation 8 double Hayato
[low: not tested].

### 4.3 Chapter people (`GameData/Person/**`)

None of the 1,595 chapter Person rows uses a playable ID as its own ID [high]. The playable ID string still
appears 194 times in 53 of those files, outside the decoded fields. It is probably the same link to the main
person as in 4.2 [medium]. Way B: must be rewritten too. Way A: nothing.

### 4.4 `GameData.bin`

There are 100 playable ID strings: the 49 Person rows, plus a second copy of 47 of them with no direct pointer.
That copy is in a block the tables tool does not decode yet (docs/TABLES.md "Not done yet": the support
(Reliance) lists after the Person block) [high for the count, low for what the block is]. Supports are tied
to the person's index through `Person.support_index` (+0x84) and `support_id` (+0x30) [low, Paragon field names].
Way A keeps the slot's supports, partners and S-rank options. That is why Way A should keep the female flag
the same by default (men fill men's spots), as FE8's "Cross-gender: off" does. Otherwise the marriage and
S-rank options (gender-locked in the lists) would pair the wrong sexes, and the child paralogues
(`UnitIsMotherPID`) would follow the slot.

### 4.5 Castle

| File | Count | What | Swap needs |
|---|---:|---|---|
| `castle/castle_join.bin.lz` | 6 people | who can come to the castle and ask to join, when that person is not yet in the army (docs/CASTLE_JOIN.md) | Way B: rewrite. Way A: nothing (the slot's join scene with the new face) |
| `castle/castle_building.bin.lz` | 49 | one building record per person | flavour |
| `castle/preset/unit/*.bin.lz` | 13 files x 10 | the units standing in the preset visitor castles | flavour |
| `face/FaceData.bin.lz` | 47 | portrait records that also name their person | none (they belong to the face, and Way A swaps the face ID) |

---

## 5. Dialogue and message archives (`m/`)

Dialogue names its speakers with control codes inside the message text: `$Wm<face name>|<place>` opens a
portrait window, and `$Ws<face name>|` makes that window the speaker. The name is the face name (the
person's ID or face ID without the prefix), not the ID itself. So a Person row swap (Way A) does not change
it [high for the codes, medium for "face name, not ID": `TalkCodeFactory::WindowMake(const char*, int)`,
`FaceDataManager::GetFaceData(const char*, ...)`]. Voice lines are `$Sv` cues named per person, and they
would also stay the original person's.

| Archives | What | Playable portrait / speaker codes | Who they belong to | Swap needs |
|---|---|---|---|---|
| 102 chapter archives (`m/@E/<chapter>`, `m/<route>/@E/<chapter>`) | story dialogue, including each join scene | 5,384 / 11,643 in 2,101 messages | the spot (the chapter) | to follow the swap, rewrite these codes (and the names in the text) or hook the face and name at run time. Flavour if not |
| 441 `<playable>_<partner>` archives (+598 for other people, mostly children) | support conversations | 3,222 / 27,191 | the person (by the slot's ID in Way A) | none |
| the death and the retreat archives | one message per person (47 + 47) | 47 + 47 | the person | none |
| `Ending` | 194 labels by person or pair | | the person | none |
| `Join` | 6 messages | 6 | castle joiners | flavour |
| castle talk, daily events, My Room greetings, Live2D (69) | castle life | 982 / 7,101 | the person | none |

---

## 6. What a swap must still guard (crash, softlock or a lost recruit)

| Place | Why | Way A | Way B |
|---|---|---|---|
| Talk recruits (type 0x17 + transfer, 13 people, section 3.5) | the Talk must exist between the right two units | safe (same IDs) | rewrite both IDs in the event and the placement |
| `UnitGetByPID` before a transfer, a side change or a leave (164 + 94 pushes) | a missing unit means the event acts on nothing | safe | every one rewritten with its placement |
| Conquest 9 (Nyx Talk, 3 `UnitGetByPID` + a Talk + a defeat event) | public tools: talking before the wall breaks can crash | safe if Nyx's spot keeps its ID. Do not move the Talk | the riskiest single chapter |
| Conquest 16 (B016: `UnitRecreate` of the hidden boss, one Peri lookup) | public tools: the spare prompt can freeze | safe. Do not edit the script | do not edit the script |
| Revelation 8 (C008 names only Gunter in code. Hayato arrives through `C_HANDOVER`, section 4.2) | public tools: two Hayatos | safe | handover, maps and scripts must change together |
| Revelation 13 (C013: battle conversations for Camilla, Saizo, Kagero, the Corrins) | public tools: invisible obstacles | safe (only flavour lines name people here) | test before calling it done |
| Ninja maps and other "only a flier can stand here" spots | the spot is unreachable without a flier | the spot keeps its need: give it a flier, as FE8 does for its fliers' places | same |
| Story leaves and returns: Gunter (Conquest 15 `UnitGetByPIDForce`, Revelation 7, 10, 21), the B006 checks for Rinkah and Sakura, the Corrins, Azura | scripted leaves, returns and branches | keep Corrin, Azura and Gunter fixed (Gunter's story moves happen across chapters). The rest is flavour | same, and more to rewrite |
| Gender (female flag) | `PlayerM`/`PlayerF` groups (Corrin only), support and S-rank lists, child paralogues | keep men in men's spots by default | same |
| Children | `UnitIsMotherPID`, `UnitIsDoubleChild`, paralogue unlocks | children stay out (F-043 #4) | same |
| Models (`aid`) | the fill's model must exist for the class the spot is in | keep the person's own class (FE8 "Recruit class: Own") or check that the model exists before writing `aid`. The public tools' "keep the face until scenes are ready" warning applies to scenes, not to maps | same |

Flavour that can stay (no crash): battle conversations (173), defeat lines (31), `UnitIsPID` branches other
than Gunter's, 3D cutscenes, supports, death and retreat quotes, endings, castle buildings, preset visitor
castles, castle talk, Live2D, and all dialogue portraits, names and voices in Way A.

---

## 7. How this was counted (to repeat it)

Read only, from `extracted/romfs` through the repo's own readers (`tools/randomizer/gamedata.py` for Person,
DisposUnit, DisposFaction and PersonChapter, `tools/mods/textmod.py` for the message archives and its `lz`
for the `.lz` files), plus a small `cmb` reader written for this page from the format facts in 3.1. The
scanners were scratch files in the session scratchpad. Nothing was run in the game and nothing was built.
The randomizer's own `enemies.py script_pids` already does a simpler version (a raw `PID_` string search per
chapter). The 3.1 reader adds the event types and the built-ins that receive each ID.
