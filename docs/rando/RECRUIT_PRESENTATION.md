# Character shuffle research: how a swapped person looks, sounds and is named (area "presentation")

**For the owner.** The character shuffle puts person B in person A's join spot. The Sacred Stones port
does that by keeping A's slot and showing B in it: B's name, face and stats, with the story still working
because the story only knows the slot. Fates can do the same, and most of it is table edits the in-game
randomizer already knows how to lay. A swapped person's **menus, status screen, battle model, battle voice
and the face and name plate in conversations** can all follow the swap without touching a single event
script. Two things do not follow from tables: **names written inside the dialogue** ("Jakob, come here")
and **the short voiced lines in scenes**. These need either one engine hook (the Sacred Stones way) or
rebuilt text files. The 55 pre-rendered movies can never follow. Same-sex swaps only.

Status 2026-11-20: host research only (no game run, no build, nothing written to the game). Facts come
from our own tables, our own tools' dumps of the owner's files under `extracted/` (counts and field names
only here, no game text), the symbol map, and a scan of the code for who calls what. The public Fates
randomizers (Ignis, lashoun's script, the 2016 randomizer, Paragon) are GPL: facts and pitfalls only,
no code. Confidence: **[high]** read in code or data, **[med]** strong data evidence, **[low]** a guess to
be tested.

## 1. Where each piece of a person's identity lives

| Piece | Where the game looks it up | Keyed by | Evidence |
|---|---|---|---|
| The person (stats, class, flags, supports, joins) | `Person` row in `GameData/GameData.bin.lz` (255 rows) | `PID_` | docs/TABLES.md Person [high] |
| Name in menus, unit list, map window | Person `mpid_name` (+0x14) -> `MPID_` message | the row's pointer | `Person::GetNameWithCaptureNameIndex` reads +0x14 [high] |
| Help text | Person `mpid_help` (+0x18) | the row's pointer | `Person::GetHelp` [high] |
| Portrait on status / unit screens | Person `fid` (+0x0C) -> `FaceData` | `FID_<name>` | `FaceInstance::LoadByUnit` exists; Person +0xC is `FID_` [high for the field, med for the path] |
| Portrait in a conversation | the scene's own command `$Wm<name>|pos|` in the message file -> `TalkUtil::GetFidForWindow` turns the name into a `FID_` -> `FaceInstance::LoadByFid`, which also calls `Person::GetFromFid` (the only caller of it) | the **old person's name written in the scene** | code scan: `Person::GetFromFid` 0x449FB8 has exactly one caller, `FaceInstance::LoadByFid` [high]; name format from our dump of one chapter archive [high] |
| Name plate above lines in a conversation | `TalkWindow::GetTalkerName` -> `FaceData::GetMessName` (FaceData +0x04, an `MPID_`) | the FaceData record | code scan: 3 callers of `FaceData::GetMessName` [high]; docs/LOOK_ROBOT.md N3 (changing the name message changed the plate) [high] |
| Face pictures | `FaceData` record (`face/FaceData.bin.lz`, 452 records, labels `FSID_ST_<name>` / `FSID_BU_<name>`): package `face/face/<pkg>.arc`, hair, colour, two default expressions, layout numbers | FSID label from the name | docs/ASSETS.md section 4 [high] |
| 3D battle model (head, hair, special outfits) | `AssetTable` (`asset/ROM0..6.lz`, IS .bin). ROM3 (77 different `AID_`) and ROM4 (51) hold the per-person rows: an `AID_` condition gives `uHead_*`, `uHair_*`, a per-person anim and an ASCII key; rows with `AID_` **and** `JID_` give a person's own outfit for one class | `AID_` (+`JID_`, item `IID_`) | our dump of the asset files [high]; `BattleUnitResName::Construct(Unit, Person, ..., Job, ...)` is one of the 3 callers of `AssetTable::Find` [high] |
| Body | ROM2: class rows (`JID_`), male/female bodies; the person's female flag picks the side | `JID_` + sex | dump [high] |
| Battle voice | per-person sound groups `VOICE_<KEY>_ATTACK*/DAMAGE/CUT_IN/DEAD/WIN/...` in `sound/IRON15_sound.bcsar` (9,367 `VOICE_` names). Playable Person rows have an **empty** `voice` field (47 of 255 rows set it, all generic/captured); the asset row for the person's `AID_` carries the same ASCII key (e.g. the key next to the head/hair models), and FaceData +0x08 holds it too | probably the `AID_` asset row's key | [med]: data match, the reading code not followed |
| Voiced lines in scenes | the scene's own command `$SvpVOICE_<KEY>_EVT_nn|` per line. Clip numbers are per person (one person has 24 `EVT` clips; they mean different lines for different people) | the **old person's key written in the scene** | dump [high] |
| Map sprite | `unit/Head/<name>/`, `unit/Body/<class+sex>/`, `unit/Unique/<class>_<name>/` (code strings `unit/Head/%s/%s%s.bch.lz` ...) | a name string; whether it comes from the `AID_` or the `FID_` is **not read yet** | [low] |
| My Room (Live2D, its voices) | `live2d/`, message files `Live2D_<name>`, `.aac` streams `VOICE_<KEY>_MYROOM_*` | the name / key | file names [high]; how the room picks them: not read [low] |
| Castle lines | `castle/CastlePerson.bin`, one row per person found by `PID_`, with a voice label | `PID_` | docs/CASTLE.md [high] |
| Pre-rendered movies | `movie/*.moflex` (55 videos) | fixed pictures | [high]: cannot follow |

Scale (counted over the English message files, 1,305 archives): **12,566** `$Wm` (put a playable person's
face on screen) in 1,149 files, **66,868** `$Ws` (speaker), **14,969** voiced-line commands, and **9,790**
whole-word mentions of a playable person's English name inside dialogue text.

Event scripts (`Scripts/*.cmb`, 156 files read) name people **only** by `PID_` (826 times in 114 files)
and messages by `MID_`. They never name an `AID_`, `FID_`, face, or voice [high]. 4,253 of 9,601
placement rows (`DisposUnit`) name a main `PID_` directly [high].

**Copies of main people in chapter files.** 285 rows in 72 chapter Person files (`GameData/Person/*`) are
the chapter's own version of a main person (an early guest, an enemy before a talk, a boss): different
`PID_`, but the main person's `FID_`, `AID_` and `MPID_` [high]. A swap that only edits the 255 main rows
leaves these showing the old person.

## 2. The question: does a pure identity swap avoid rewriting scripts?

**Yes, for everything the story checks.** If A's slot keeps `PID_A` (as the Sacred Stones port keeps the
slot's pid), every join, talk, death check, support and placement still works, because they only know the
`PID_` (section 1). What must change is only what the slot **shows**. That is also why this avoids the
public tools' worst class of bugs: they rewrite scripts and placements, and a missed rewrite gives two of
one person (Revelation 8 Hayato) or a scene that waits for a person who never comes (Conquest 9, Conquest
16). Their list still has to be played (F-043), because their causes are not all known.

What a Person-row-only swap (copy B's `fid`, `aid`, `mpid_name`, `mpid_help`, growths, bases, class,
skills into A's row) does and does not cover:

| Shown where | Follows B? | Why |
|---|---|---|
| Unit list, status screen, map window, help text | yes | they read the row |
| Battle model head/hair/own outfits, battle voice | yes [med for voice] | `BattleUnitResName` gets the Person, asset rows key on its `AID_` |
| Map sprite | unknown [low] | depends on whether the head folder comes from `AID_` or `FID_` |
| Conversation face and name plate | **no** | the scene names A by name; that goes to A's FaceData (section 1) |
| Chapter copies of A (guest/enemy/boss versions) | **no** | own rows with A's `FID_`/`AID_`/`MPID_` |
| Names in dialogue, voiced lines | **no** | written in the text |

So in scenes the slot would still look and sound like A while the menus say B. Worse than either.

## 3. The cheapest correct approach: remap by label, not by row

Keep **every** `PID_`, `FID_`, `AID_` and `MPID_` reference where it is, and change what the old person's
labels **resolve to**. One permutation (A's labels show B, B's show C, ... all at once, no chains), same as
the Sacred Stones port's face map and name list:

| Step | What is edited | Effect | How it fits what we have |
|---|---|---|---|
| P1 Faces | FaceData records `FSID_ST_<A>` and `FSID_BU_<A>`: take B's package, hair, colour, default expressions and layout numbers, and B's `MPID_` | every place that asks for A's face by name or by `FID_<A>` shows B: status screen, every conversation, the name plate, chapter copies of A. `Person::GetFromFid(FID_<A>)` still finds A's slot (its `fid` is not touched), so the slot and its face agree | pointer and number cells in one IS .bin; the in-game patcher already lays label-pointer cells (docs/RANDOMIZER_INGAME.md). Open: whether FaceData is resident from boot (then it is patched like GameData at New Game) or read per use (then it needs the per-file hook that Dispos uses) |
| P2 Name in menus | Person `mpid_name` / `mpid_help` of A's slot -> B's messages, in the main row **and** the chapter copies of A | menus, map window, help, and A's guest/boss versions show B's name | GameData cells (already laid at New Game); chapter Person files need the per-file hook like Dispos (small engine addition) |
| P3 Models and battle voice | Person `aid` of A's slot -> `AID_<B>`, main row and chapter copies; **or** swap the `AID_` condition strings of the person rows in `asset/ROM3`/`ROM4` (then every `AID_<A>` user follows at once) | B's head, hair and own outfits in battle and in in-engine 3D scenes (scripts reach models only through the `PID_` -> Person -> `AID_`), B's battle voice [med] | Person cells: as P2. The asset-table way is cleaner (covers the chapter copies with no per-file hook) but needs its load moment found, as for FaceData |
| P4 Names in dialogue | whole-word replacement of every swapped English name in all message text, one pass with the permutation (no chains), plus `$SvpVOICE_<A>_...` commands of the swapped speakers removed (silent line) rather than remapped (clip numbers do not match between people) | dialogue says B's name; A's voice no longer comes out of B's face | message text changes length, so the fixed-cell patcher cannot do it. Two ways: (a) **the Sacred Stones way**, one engine hook where the game fetches a message, replacing the words on the fly (one hook covers all 1,305 files, nothing stored); (b) rebuilt message files served in place of the originals (msg.py rebuilds them at 100%), which needs a file-serving hook because the mods layer is laid at boot, before the New Game choice (docs/RANDOMIZER_INGAME.md "Why not Zakuro's mods layer"). (a) is less code and less disk |
| P5 Map sprite | after a code read of the `unit/Head/%s` path builder: nothing if it takes the `AID_` (P3 covers it), else the same label remap for `unit/Head/<name>` | B's map head | read first, then decide |

Cost guess [low]: P1 + P2 + P3 with the robot checks: about 1 round, if FaceData and the asset table turn
out to be resident (the patcher already does the rest). The per-file hook for chapter Person files: part of
that round, an engine build (owner OK needed: F-044 covers the randomizer's builds). P4 (a): about 1 round
including an engine build and a robot pass over a few scenes. P5: under an hour once read.

## 4. What will still look wrong (say so in the page's help)

- **Pre-rendered movies (55)** show the original people. No fix.
- **Story content.** B speaks A's lines and has A's supports, family, castle lines (CastlePerson is by
  `PID_`) and story role, as in the Sacred Stones port. Royals keep their story (the slot keeps its
  per-person code flags such as Takumi's, Ryoma's, Leo's, Xander's, Ophelia's).
- **Missing expressions.** Scenes ask for A's expressions by name (`$E<expression>,|`). B's face package may
  not have every one (the Jakob/Felicia portrait look found two of Jakob's with no Felicia twin). What the
  game does with a missing expression (fall back, blank, or stop) is **not known**: the first robot check
  must play a scene that asks for one. If it is not a clean fallback, P1 must use the file way of the
  portrait look (fill A's package with B's pictures, B's normal face where one is missing), which needs the
  file-serving hook.
- **Sweat/blush overlays** are placed by the record's layout numbers; P1 moves B's layout with B's pictures,
  so they should sit right (the portrait look kept A's numbers and saw small offsets).
- **Voices.** Battle voice follows (P3) [med]. Scene lines of swapped speakers go silent (P4). My Room
  (Live2D, its voices) and castle lines stay A's until their lookup is read; simplest is to say so, or to
  keep the shuffle out of My Room by leaving those people unswapped there.
- **Sex.** Bodies come from the class and the female flag, and dialogue pronouns about A are written in
  the text. Same-sex swaps only (the Sacred Stones port's default), so B's head never lands on the wrong
  body and "he/she" stays right.
- **Japanese voice option** uses the same keys; same treatment.

## 5. Who never moves (presentation reasons)

Corrin (the face is built from the avatar editor; `$Wmusername`, `PLAYER_M#/F#` keys), Kana and every
child (F-043: children off), Azura (her song scenes, Live2D and special class outfits), download/amiibo
people (`SPID_ダウンロード` flag), captured generics (`SPID_捕獲`, no own face/model). The rest of the
pool rule (route lists, fliers for the ninja maps, the Conquest 9 / 16 and Revelation 8 / 13 chapters) is
the join-spot area's job.

## 6. How to check it (robot, later, headless, recorded routes only)

1. A recorded scene with a swapped speaker: the large face, the talk window face and the name plate are
   B's; the chapter copy of A (if the chapter has one) shows B; nothing garbled.
2. A scene that asks A for an expression B does not have: note what happens (see section 4).
3. A battle with the slot: B's head/hair, B's battle voice key in the sound log.
4. Off = original: memory and saves equal to an unrandomized run (as T4).
5. With P4: a scene line names B, and the swapped speaker's voiced line is silent.

## 7. Open reads (host, cheap)

- FaceData and AssetTable load moment (resident from boot or per use): decides P1/P3's patch path.
- The `unit/Head/%s` builder's source string (`AID_` or `FID_`).
- The battle voice key's reader (asset row key or FaceData +0x08).
- What `FaceInstance::LoadByFid` uses `Person::GetFromFid`'s result for (hair colour, accessory, capture
  face are guesses).
- How My Room picks Live2D and its voices.
