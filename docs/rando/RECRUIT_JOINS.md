# Who joins where: the join spots of the 49 playable people (character shuffle research, "joins")

**For the owner.** This is the map the character shuffle needs. For each of the 49 people the randomizer
already handles, it shows the chapter file that first puts them in your army on each route, how that file does
it, the class and level they join at, and who is already with you when the routes split. Facts only: labels,
file names and person IDs read from your own extracted game files on this machine. No game text, and no code
from the public randomizers (they are GPL, so facts only, F-043). Nothing was run in the game for this.
Round 53 timeframe, 2026-11-20, host only, read-only. Nothing counts as done until the owner says ok (F-037).

How it was read (all read-only, outputs in the scratchpad only):

- `build/tables/Person.csv`, `PersonChapter.csv`, `DisposUnit.csv`, `DisposFaction.csv`, `Chapter.csv` (the
  table tools' dumps; docs/TABLES.md).
- `castle/castle_join.bin.lz` (decompressed with tools/assets/lz.py; layout from docs/CASTLE_JOIN.md).
- All 624 `Scripts/**/*.cmb` files, read by a small call reader (not tracked, scratch only). It walks the
  bytecode for "push string" (0x1C with a one-byte offset, 0x1D with a two-byte offset into the string pool at
  header +0x20), "push small number" (0x19) and "call function" (0x47 with an offset and an argument count). It
  lists each `ev::` call with the literal strings pushed before it. Strings are UTF-8 or Shift-JIS (cp932); both
  occur. It is a heuristic, not a decompiler. It shows reliably which calls a file makes and with which literal
  strings. The person a call acts on is taken from the nearest earlier `ev::UnitGetByPID` / `ev::UnitIsPID` /
  `ev::UnitGetByPIDForce`, which is only [medium].

Confidence: [high] = read straight from a table or a literal in a script; [medium] = from the call order;
[low] = an inference.

## 1. The three ways a person joins (what the files show)

1. **A placement group the chapter script puts on the player's side.** Each chapter's Dispos file
   (`GameData/Dispos/{,A/,B/,C/}<chapter>.bin.lz`) has named groups, and the chapter script places a group with
   `ev::Dispos "<group>"`. A person in `Player`, `PlayerF`/`PlayerM` or `Support01..04` on team 0 joins when that
   group is placed [high]. `PlayerF` is placed when the avatar is female (`ev::UnitIsPID "PID_プレイヤー女"` right
   before it in A002/A006/B006), and `PlayerM` when the avatar is male. C006 asks `ev::UnitPlayerIsMale`
   instead [high]. This is the Felicia / Jakob split. With a male avatar Felicia joins in A002 (`PlayerM`); with a
   female avatar Jakob joins there (`PlayerF`). The other one joins in the route's chapter 6 file.
2. **A unit placed on another side and moved over by the script.** The unit starts on team 2 (`Ally`, some
   `Support01`) or team 1 (`Enemy`, `Enemy02`, `Reinforce01`). The script then calls `ev::UnitSetBID "<belong>"`
   and `ev::UnitTransferByIndex 0`, where force 0 = the player's army [high for the calls, medium for which
   person]. This is how the talk and mid-map recruits work: Takumi A010, Nyx B009 and C015, Benny and Charlotte
   C014, Shura C015, Keaton B014, Hinoka/Azama/Setsuna A008, Oboro/Hinata A009, Reina A011, Saizo/Orochi/Reina
   C011, Mozu X001.
3. **The castle.** `castle_join.bin.lz` offers a person when three things hold: they are not in the army yet,
   one of the listed chapters is cleared, and one of the listed buildings is built (docs/CASTLE_JOIN.md) [high].
   It has six records:

   | Record | PID | Chapters (any one cleared) | Building words (any one built; -1 = none) |
   |---|---|---|---|
   | 0 | `PID_フェリシア` (Felicia) | CID_A015, CID_B015, CID_C015 | none |
   | 1 | `PID_ジョーカー` (Jakob) | CID_A015, CID_B015, CID_C015 | none |
   | 2 | `PID_イザナ` (Izana) | CID_A018, CID_B022 | 15 |
   | 3 | `PID_フウガ` (Fuga) | CID_C018 | 15 |
   | 4 | `PID_ユキムラ` (Yukimura) | CID_A022 | 43, 44, 45 |
   | 5 | `PID_フローラ` (Flora) | CID_B018, CID_C022 | 49, 47, 48 |

   Which building and level each building number stands for has not been read yet [low].

**Route variants of a person: the HANDOVER files.** `GameData/Person/{A,B,C}_HANDOVER.bin.lz` hold extra
Person rows (`PID_A_…`, `PID_B_…`, `PID_C_…`, numbered from 32512). Each row's `replace_index` is the main
person's number. The route's Dispos file places that row instead of the main one, so on that route the person
joins with that row's level and stats [high for the tables; medium that the joined unit then becomes the main
person, which is read from `replace_index`]. In every HANDOVER row the class is the same as in the main row.
Only the level and the stat columns differ.

| File | Row | Main person | Level (main) | Placed in |
|---|---|---|---|---|
| A_HANDOVER | `PID_A_サイラス` | Silas | 6 (6) | A007 Support02 |
| | `PID_A_カザハナ` | Hana | 4 (4) | A007 Player |
| | `PID_A_ツバキ` | Subaki | 5 (5) | A007 Player |
| | `PID_A_ユウギリ` | Reina | 1 (1) | A011 Support02 (team 2) |
| | `PID_A_ツクヨミ` | Hayato | 1 (1) | A008 Support01 |
| | `PID_A_アシュラ` | Shura | 10 (10) | A022 Support01 |
| B_HANDOVER | `PID_B_ルーナ` | Selena | 10 (10) | B010 Support01 |
| | `PID_B_ベルカ` | Beruka | 9 (9) | B010 Support01 |
| | `PID_B_スズカゼ` | Kaze | 9 (3) | B011 Support01 |
| | `PID_B_ギュンター` | Gunter | 10 (3) | B015 Player |
| | `PID_B_アシュラ` | Shura | 2 (10) | B016 Support01 |
| C_HANDOVER | `PID_C_ヒノカ` | Hinoka | 17 (8) | C016 Player |
| | `PID_C_サクラ` | Sakura | 4 (1) | C008 Support01 |
| | `PID_C_サイゾウ` | Saizo | 9 (7) | C011 Ally (team 2; row belong BID_その他) |
| | `PID_C_オロチ` | Orochi | 7 (5) | C011 Ally (team 2; row belong BID_その他) |
| | `PID_C_エリーゼ` | Elise | 7 (5) | C014 Player |
| | `PID_C_ハロルド` | Arthur | 9 (7) | C014 Player |
| | `PID_C_エルフィ` | Effie | 8 (6) | C014 Player |
| | `PID_C_ツクヨミ` | Hayato | 9 (1) | C009 Support01 (**two** placements, different items) |
| | `PID_C_ラズワルド` | Laslow | 16 (12) | C017 Support02 and Support04 |
| | `PID_C_ピエリ` | Peri | 16 (10) | C017 Support02 and Support04 |
| | `PID_C_オーディン` | Odin | 12 (5) | C017 Support02 and Support04 |
| | `PID_C_ゼロ` | Niles | 14 (8) | C017 Support02 and Support04 |
| | `PID_C_アサマ` | Azama | 13 (7) | C016 Player |
| | `PID_C_セツナ` | Setsuna | 11 (3) | C016 Player |
| | `PID_C_クリムゾン` | Scarlet | 3 (1) | C016 Player |
| | `PID_C_サイラス` | Silas | 18 (6) | C014 Support01 |

The other per-chapter Person files (`GameData/Person/<chapter>.bin.lz` and `Person/{A,B,C}/…`) hold only
chapter-only actors, such as `PID_A008_EDイベント用フウガ`. None of them is one of the 49 [high].

**Join level.** Every route join placement of the 47 people who are not the avatar has Dispos `level` 0, so the
join level is the `level` of the Person row (or of the HANDOVER row) [high for the zeros; medium that 0 means
"use the Person row"]. Non-zero Dispos levels appear only in three places: the avatar's own placements (B006 7,
C006 10), Azura's (B009 2, C006 5), and the paralogue (X) placements of people who are already in the army.

**Join items** are the placement's `item_1..5` (shown as item labels in the table below) [high].

## 2. Who is with you at the route split, and how each route's chapter 6 changes it

Shared chapters (A000 Prologue to A005, then P006, the choice scene) [high for the placements]:

| Chapter file | Joins (group) |
|---|---|
| A000 | the avatar (`Player`); a chapter-only copy of Takumi (`PID_A000_タクミ`) is moved to the player's side for that map only |
| A001 | nobody new |
| A002 | Gunter (`Player`); Felicia (`PlayerM`, male avatar) or Jakob (`PlayerF`, female avatar) |
| A003 | nobody new. At the end its script loops over the forces and calls `ev::UnitItemPutOffAll` and `ev::UnitTransferByIndex 5`, which sets the army aside after the canyon [medium] |
| A004 | Rinkah, Kaze (`Player`) |
| A005 | Sakura, Azura (`Player`) |

So when chapter 6 starts the army is: the avatar, one servant, Rinkah, Kaze, Sakura and Azura. Gunter is gone
after A003 [medium].

| Route chapter 6 | What its script does [high for the calls, medium for who] |
|---|---|
| A006 (Birthright) | `ev::UnitExpulsionByIndex` on Gunter (a safety step, since he never comes back on this route); places `PlayerF`/`PlayerM`, so the other servant joins. Rinkah, Kaze, Sakura and Azura stay. |
| B006 (Conquest) | loops over force 3 and calls `ev::UnitItemDisposalFor006`; expels Sakura and Rinkah (they never return on Conquest); calls `ev::UnitTransferByIndex 5` (sets units aside); then the other servant joins through `PlayerF`/`PlayerM`. Kaze returns in B011 (HANDOVER L9). Azura is placed again from B009. Gunter returns in B015 (HANDOVER L10) and is expelled at the end of B015. |
| C006 (Revelation) | the same force loop and `ev::UnitTransferByIndex 5`, with no expulsion; the other servant joins through `PlayerM`/`PlayerF`. Gunter returns in C007 (`Support02`, `ev::UnitTransferByIndex 0`). Kaze and Sakura (HANDOVER L4) return in C008, Rinkah in C009. Azura is placed in C006. |

## 3. The join table (all 49)

Each route cell is the **first** non-event placement of that person (or of their HANDOVER row) on that route,
in chapter order. It reads `file group team`, then `via <row> (L)` when a HANDOVER row is placed, then the
items carried. "Shared" is A000-A005; route chapters are A/B/C006-028. X = paralogues, where the person is
normally already in the army, so those are pre-placements and not joins (except Mozu in X001).

Left out of the table: event groups (`EventNN`, cutscene actors); the opening map Z000 (high-level copies of
several royals, not a join); and the amiibo maps M001-M004 (`ev::JoinGuest` for four guest characters outside
the 49). "-" = never placed on that route.

The last column lists the join-related calls the scripts make on that person:

- `Transfer(n)` = `ev::UnitTransferByIndex n`
- `SetBID` = `ev::UnitSetBID`
- `Expel` = `ev::UnitExpulsionByIndex` (leaves the army)
- `Lost` = `ev::UnitLostByIndex`
- `NeverSortie` = `ev::UnitSetNeverSortie`

| # | Name | PID | Class (Person.job) | Lv | Shared ch0-5 | Birthright (A) | Conquest (B) | Revelation (C) | Paralogue (X) | Script calls on the join (file: call) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Corrin (M) | `PID_プレイヤー男` | `JID_ダークプリンス男` | 1 | A000 Player t0 [IID_青銅の剣] | A006 Player t0 [IID_夜刀神/IID_竜石] | B006 Player t0 [IID_夜刀神/IID_竜石] | C006 Player t0 [IID_ガングレリ/IID_傷薬/IID_竜石] | X001 Player t0 [IID_竜石/IID_夜刀神/IID_霊刀] |  |
| 2 | Corrin (F) | `PID_プレイヤー女` | `JID_ダークプリンセス女` | 1 | - | - | - | - | X004 Player t0 [IID_夜刀神/IID_アーマーキラー/IID_竜石] | A005: Transfer(3) |
| 3 | Gunter | `PID_ギュンター` | `JID_グレートナイト男` | 3 | A002 Player t0 [IID_鉄の槍] | - | B015 Player t0 via `PID_B_ギュンター` (L10) [IID_鋼の槍/IID_鋼の斧/IID_手槍/IID_傷薬] | C007 Support02 t0 [IID_鋼の槍/IID_傷薬/IID_傷薬] | X001 Player t0 [IID_鋼の槍/IID_キラーランス/IID_ビーストキラー] | A006: Expel; B015: Expel; B015: NeverSortie(1); C007: Transfer(0); C007: Transfer(2); C026: NeverSortie(3,1) |
| 4 | Felicia | `PID_フェリシア` | `JID_メイド女` | 1 | A002 PlayerM t0 [IID_鉄の暗器/IID_ライブ] | A006 PlayerM t0 [IID_鉄の暗器/IID_ライブ] | B006 PlayerM t0 [IID_鉄の暗器/IID_ライブ] | C006 PlayerM t0 [IID_鉄の暗器/IID_ライブ] | X001 Player t0 [IID_鉄の暗器/IID_ライブ/IID_リライブ] |  |
| 5 | Jakob | `PID_ジョーカー` | `JID_バトラー男` | 1 | A002 PlayerF t0 [IID_鉄の暗器/IID_ライブ] | A006 PlayerF t0 [IID_鉄の暗器/IID_ライブ] | B006 PlayerF t0 [IID_鉄の暗器/IID_ライブ] | C006 PlayerF t0 [IID_鉄の暗器/IID_ライブ] | X004 Player t0 [IID_鉄の暗器/IID_ライブ/IID_夏祭/IID_春祭/IID_リライブ] |  |
| 6 | Rinkah | `PID_リンカ` | `JID_鬼人女` | 4 | A004 Player t0 [IID_青銅の金棒] | A006 Player t0 [IID_青銅の金棒] | - | C009 Player t0 [IID_青銅の金棒] | X001 Player t0 [IID_鉄の金棒] | B006: Expel; B006: Transfer(5) |
| 7 | Kaze | `PID_スズカゼ` | `JID_忍男` | 3 | A004 Player t0 [IID_鉄の手裏剣/IID_傷薬/IID_傷薬] | A006 Player t0 [IID_鉄の手裏剣] | B011 Support01 t0 via `PID_B_スズカゼ` (L9) [IID_鋼の手裏剣] | C008 Support01 t0 [IID_鉄の手裏剣] | X001 Player t0 [IID_鉄の手裏剣] | A015: Lost |
| 8 | Sakura | `PID_サクラ` | `JID_巫女女` | 1 | A005 Player t0 [IID_春祭] | A006 Player t0 [IID_春祭] | - | C008 Support01 t0 via `PID_C_サクラ` (L4) [IID_春祭] | X002 Player t0 [IID_春祭/IID_夏祭] | B006: Expel; C010: Expel |
| 9 | Azura | `PID_アクア` | `JID_歌姫女` | 1 | A005 Player t0 [IID_青銅の薙刀] | A006 Player t0 [IID_青銅の槍] | B009 Player t0 [IID_傷薬/IID_宝の鍵] | C006 Player t0 [IID_青銅の槍/IID_傷薬] | X001 Player t0 [IID_青銅の槍/IID_傷薬/IID_傷薬] | A024: Expel |
| 10 | Hana | `PID_カザハナ` | `JID_侍女` | 4 | - | A007 Player t0 via `PID_A_カザハナ` (L4) [IID_鉄の刀] | - | C008 Support01 t0 [IID_鉄の刀] | X001 Player t0 [IID_鉄の刀] |  |
| 11 | Subaki | `PID_ツバキ` | `JID_天馬武者男` | 5 | - | A007 Player t0 via `PID_A_ツバキ` (L5) [IID_鉄の薙刀] | - | C008 Support01 t0 [IID_鉄の薙刀] | X001 Player t0 [IID_鉄の薙刀] |  |
| 12 | Silas | `PID_サイラス` | `JID_ソシアルナイト男` | 6 | - | A007 Support02 t0 via `PID_A_サイラス` (L6) [IID_鋼の剣/IID_手槍] | B007 Support01 t0 [IID_鉄の剣/IID_青銅の槍] | C014 Support01 t0 via `PID_C_サイラス` (L18) [IID_手槍] | X005 Player t0 [IID_鋼の槍/IID_鉄の剣] |  |
| 13 | Saizo | `PID_サイゾウ` | `JID_忍男` | 7 | - | A007 Support03 t0 [IID_鋼の手裏剣/IID_青銅の手裏剣] | - | C011 Ally t2 via `PID_C_サイゾウ` (L9) [IID_鋼の手裏剣/IID_傷薬] | X007 Player t0 [IID_鋼の手裏剣] | C011: SetBID(BID_白夜王国軍); C011: Transfer(0) |
| 14 | Orochi | `PID_オロチ` | `JID_呪い師女` | 5 | - | A007 Support03 t0 [IID_鼠神・子] | - | C011 Ally t2 via `PID_C_オロチ` (L7) [IID_牛神・丑/IID_傷薬] | X002 Player t0 [IID_牛神・丑] | C011: SetBID(BID_白夜王国軍); C011: Transfer(0) |
| 15 | Hinoka | `PID_ヒノカ` | `JID_天馬武者女` | 8 | - | A008 Ally t2 [IID_守りの薙刀] | - | C016 Player t0 via `PID_C_ヒノカ` (L17) [IID_守りの薙刀] | X007 Player t0 [IID_守りの薙刀] | A008: SetBID(BID_白夜王国軍); A008: Transfer(0) |
| 16 | Azama | `PID_アサマ` | `JID_修験者男` | 7 | - | A008 Ally t2 [IID_夏祭] | - | C016 Player t0 via `PID_C_アサマ` (L13) [IID_春祭/IID_夏祭] | X012 Player t0 [IID_春祭] | A008: SetBID(BID_白夜王国軍); A008: Transfer(0) |
| 17 | Setsuna | `PID_セツナ` | `JID_弓使い女` | 3 | - | A008 Ally t2 [IID_鉄の和弓] | - | C016 Player t0 via `PID_C_セツナ` (L11) [IID_鋼の和弓] | X009 Player t0 [IID_鉄の和弓] | A008: SetBID(BID_白夜王国軍); A008: Transfer(0) |
| 18 | Hayato | `PID_ツクヨミ` | `JID_呪い師男` | 1 | - | A008 Support01 t0 via `PID_A_ツクヨミ` (L1) [IID_牛神・丑] | - | C009 Support01 t0 via `PID_C_ツクヨミ` (L9) [IID_牛神・丑] | X014 Player t0 [IID_牛神・丑] |  |
| 19 | Oboro | `PID_オボロ` | `JID_槍術士女` | 10 | - | A009 Support01 t2 [IID_鋼の薙刀] | - | C010 Support01 t0 [IID_鉄の薙刀] | X002 Player t0 [IID_鋼の薙刀/IID_手槍] | A009: SetBID(BID_白夜王国軍); A009: Transfer(0) |
| 20 | Hinata | `PID_ヒナタ` | `JID_侍男` | 10 | - | A009 Support01 t2 [IID_鋼の刀] | - | C010 Support01 t0 [IID_鉄の刀] | X007 Player t0 [IID_鉄の刀] | A009: SetBID(BID_白夜王国軍); A009: Transfer(0) |
| 21 | Takumi | `PID_タクミ` | `JID_弓使い男` | 11 | - | A010 Enemy02 t1 [IID_風神弓] | - | C010 Support01 t0 [IID_風神弓/IID_鉄の和弓] | X002 Player t0 [IID_風神弓/IID_鉄の和弓] | A010: SetBID(BID_その他); A010: Transfer(0); A016: NeverSortie(3,1); C016: Expel |
| 22 | Kagero | `PID_カゲロウ` | `JID_忍女` | 10 | - | A010 Support01 t0 [IID_針手裏剣/IID_力のしずく] | - | C011 Support01 t0 | X002 Player t0 [IID_鋼の手裏剣] |  |
| 23 | Reina | `PID_ユウギリ` | `JID_金鵄武者女` | 1 | - | A011 Support01 t2 [IID_鉄の和弓/IID_鋼の薙刀] | - | C011 Ally t2 [IID_鉄の薙刀/IID_傷薬] | X002 Player t0 [IID_鋼の薙刀/IID_鉄の和弓] | A011: SetBID(BID_白夜王国軍); A011: Transfer(0); C011: SetBID(BID_白夜王国軍); C011: Transfer(0) |
| 24 | Kaden | `PID_ニシキ` | `JID_妖狐男` | 14 | - | A012 Player t0 [IID_獣石] | - | C013 Player t0 [IID_獣石] | X010 Player t0 [IID_獣石] |  |
| 25 | Ryoma | `PID_リョウマ` | `JID_剣聖男` | 4 | - | A013 Support01 t0 [IID_雷神刀/IID_夏祭] | - | C016 Player t0 [IID_雷神刀/IID_マスタープルフ] | X007 Player t0 [IID_雷神刀] |  |
| 26 | Scarlet | `PID_クリムゾン` | `JID_ドラゴンマスター女` | 1 | - | A013 Support01 t0 [IID_キラーアクス] | - | C016 Player t0 via `PID_C_クリムゾン` (L3) [IID_キラーアクス/IID_手斧] | - | C018: Lost; C018: NeverSortie(3,1) |
| 27 | Shura | `PID_アシュラ` | `JID_アドベンチャラー男` | 10 | - | A022 Support01 t0 via `PID_A_アシュラ` (L10) [IID_巧者の和弓/IID_超獣石] | B016 Support01 t0 via `PID_B_アシュラ` (L2) [IID_キラーボウ/IID_リライブ] | C015 Reinforce01 t1 [IID_鋼の弓/IID_ライブ] | - | C015: SetBID(BID_その他); C015: Transfer(0) |
| 28 | Elise | `PID_エリーゼ` | `JID_ロッドナイト女` | 5 | - | - | B007 Support02 t0 [IID_ライブ/IID_フリーズ] | C014 Player t0 via `PID_C_エリーゼ` (L7) [IID_ライブ/IID_リライブ] | X015 Player t0 [IID_ライブ/IID_フリーズ/IID_七難即滅] | B012: NeverSortie(3,1) |
| 29 | Arthur | `PID_ハロルド` | `JID_アクスファイター男` | 7 | - | - | B007 Support03 t0 [IID_鉄の斧/IID_手斧] | C014 Player t0 via `PID_C_ハロルド` (L9) [IID_鉄の斧] | X016 Player t0 [IID_鉄の斧/IID_手斧/IID_青銅の斧/IID_逆金棒] |  |
| 30 | Effie | `PID_エルフィ` | `JID_アーマーナイト女` | 6 | - | - | B007 Support03 t0 [IID_鉄の槍] | C014 Player t0 via `PID_C_エルフィ` (L8) [IID_鉄の槍] | X015 Player t0 [IID_鉄の槍/IID_手槍] |  |
| 31 | Odin | `PID_オーディン` | `JID_ダークマージ男` | 5 | - | - | B008 Support01 t0 [IID_サンダー/IID_傷薬] | C017 Support02 t0 via `PID_C_オーディン` (L12) [IID_サンダー] | X015 Player t0 [IID_サンダー/IID_傷薬] |  |
| 32 | Niles | `PID_ゼロ` | `JID_シーフ男` | 8 | - | - | B008 Support01 t0 [IID_鉄の弓] | C017 Support02 t0 via `PID_C_ゼロ` (L14) [IID_鋼の弓/IID_傷薬] | X015 Player t0 [IID_鉄の弓] |  |
| 33 | Nyx | `PID_ニュクス` | `JID_ダークマージ女` | 9 | - | - | B009 Enemy t2 [IID_ファイアー/IID_フィンブル] | C015 Support01 t2 [IID_ファイアー] | X015 Player t0 [IID_ファイアー/IID_フィンブル] | B009: SetBID(BID_その他); B009: Transfer(0); C015: SetBID(BID_その他); C015: Transfer(0) |
| 34 | Camilla | `PID_カミラ` | `JID_レヴナントナイト女` | 1 | - | - | B010 Support02 t0 [IID_鋼の斧/IID_サンダー] | C012 Support01 t0 [IID_鋼の斧/IID_手斧] | X015 Player t0 [IID_鋼の斧/IID_サンダー/IID_逆金棒] |  |
| 35 | Selena | `PID_ルーナ` | `JID_マーシナリー女` | 10 | - | - | B010 Support01 t0 via `PID_B_ルーナ` (L10) [IID_鉄の剣/IID_青銅の剣/IID_傷薬] | C012 Support03 t0 [IID_鉄の剣] | - |  |
| 36 | Beruka | `PID_ベルカ` | `JID_ドラゴンナイト女` | 9 | - | - | B010 Support01 t0 via `PID_B_ベルカ` (L9) [IID_鉄の斧] | C012 Support02 t0 [IID_鉄の斧] | - |  |
| 37 | Laslow | `PID_ラズワルド` | `JID_マーシナリー男` | 12 | - | - | B012 Player t0 [IID_鋼の剣/IID_傷薬] | C017 Support02 t0 via `PID_C_ラズワルド` (L16) [IID_鋼の剣/IID_傷薬] | X021 Player t0 [IID_銀の剣/IID_鋼の剣/IID_青銅の弓] |  |
| 38 | Peri | `PID_ピエリ` | `JID_ソシアルナイト女` | 10 | - | - | B012 Player t0 [IID_鋼の槍/IID_鉄の剣] | C017 Support02 t0 via `PID_C_ピエリ` (L16) [IID_手槍/IID_鋼の槍/IID_鉄の剣] | - | B016: SetBID(BID_賊) |
| 39 | Benny | `PID_ブノワ` | `JID_アーマーナイト男` | 15 | - | - | B013 Support01 t0 [IID_鋼の槍] | C014 Enemy t1 [IID_鉄の槍] | X015 Player t0 [IID_鉄の槍/IID_鋼の槍/IID_手槍/IID_青銅の斧] | C014: SetBID(BID_暗夜王国軍); C014: Transfer(0) |
| 40 | Charlotte | `PID_シャーロッテ` | `JID_アクスファイター女` | 10 | - | - | B013 Support01 t0 [IID_鋼の斧] | C014 Enemy t1 [IID_鋼の斧] | X017 Player t0 [IID_鋼の斧/IID_手斧/IID_逆金棒/IID_青銅の斧] | C014: SetBID(BID_暗夜王国軍); C014: Transfer(0) |
| 41 | Leo | `PID_レオン` | `JID_ダークナイト男` | 2 | - | - | B014 Player t0 [IID_ブリュンヒルデ/IID_鉄の剣] | C017 Support01 t0 [IID_ブリュンヒルデ] | X016 Player t0 [IID_ブリュンヒルデ] | B026: Expel |
| 42 | Keaton | `PID_フランネル` | `JID_ガルー男` | 15 | - | - | B014 Ally t2 [IID_獣石/IID_守獣石] | C013 Player t0 [IID_獣石] | X017 Player t0 [IID_超獣石/IID_守獣石/IID_獣石] | B014: Expel; B014: SetBID(BID_その他); B014: Transfer(0) |
| 43 | Xander | `PID_マークス` | `JID_パラディン男` | 4 | - | - | B016 Player t0 [IID_ジークフリート] | C017 Support01 t0 [IID_ジークフリート] | X015 Player t0 [IID_ジークフリート/IID_傷薬] | X015: Expel |
| 44 | Izana | `PID_イザナ` | `JID_陰陽師男` | 5 | - | - | - | - | - |  |
| 45 | Fuga | `PID_フウガ` | `JID_兵法者男` | 10 | - | - | - | - | - |  |
| 46 | Yukimura | `PID_ユキムラ` | `JID_絡繰師男` | 10 | - | - | - | - | - |  |
| 47 | Flora | `PID_フローラ` | `JID_メイド女` | 5 | - | - | - | - | - |  |
| 48 | Mozu | `PID_モズメ` | `JID_村人女` | 1 | - | - | - | - | X001 Ally t2 [IID_青銅の薙刀/IID_傷薬] | X001: SetBID(BID_その他); X001: Transfer(0) |
| 71 | Anna | `PID_アンナ` | `JID_シーフ女` | 10 | - | - | - | - | - |  |

Not placed by any chapter file:

- **Izana, Fuga, Yukimura, Flora**: castle joins only (section 1, castle_join records 2-5) [high]. The files
  read here show **no Birthright or Conquest join for Fuga**. Castle record 3 names only CID_C018, and Fuga's
  Birthright appearances are chapter-only actors such as `PID_A008_EDイベント用フウガ`. They also show no
  Revelation or Conquest path for Yukimura, and no Birthright path for Flora. If Fuga can be recruited on
  Birthright in the real game, that join is somewhere not read here: a cutscene file in another format, or the
  game's code [low]. Check this before the shuffle treats Fuga as a Birthright spot.
- **Anna** (`PID_アンナ`): no placement, script or castle record on the cartridge [high]. She probably comes from
  downloadable content outside these files [low].
- **Corrin (F)** (`PID_プレイヤー女`): the female avatar row. The shared and route placements use
  `PID_プレイヤー男`, and the game swaps in the player's own avatar [medium]. `PID_プレイヤー女` itself is placed
  only in X004 [high].

## 4. Forced, locked and route-only people

**Forced, so never shuffle (story roles)** [high for the flags and calls]:

- The avatar (both rows): flags `SPID_主人公` + `SPID_プレイヤー`, placed in every chapter; the randomizer already
  keeps them. Their join spot (A000) is the start of the game, not a shuffle slot.
- Azura: present on all three routes and removed by script in A024 (`Expel`). Cutscene scripts name her often:
  19 script files reference `PID_アクア`, more than anyone else. Keep her fixed.
- Route royals (legendary weapons, dragon-vein flag `SPID_竜脈`): Ryoma, Takumi, Hinoka, Sakura (Hoshido) and
  Xander, Leo, Camilla, Elise (Nohr).
- Scripted exits that act on a person's own PID [high for the calls, medium for which person]:
  - Takumi: `Expel` x4 in C016, `NeverSortie` in A016
  - Leo: `Expel` in B026
  - Xander: `Expel` in X015
  - Elise: `NeverSortie` in B012
  - Kaze: `Lost` in A015
  - Scarlet: `Lost` and `NeverSortie` in C018
  - Gunter: `Expel` in A006 and B015, `NeverSortie` in B015 and C026
  - Sakura: `Expel` in B006 and C010

  If a shuffle moves one of these people to another spot, these calls must still act on the right unit.
  Otherwise those people stay fixed.

**Already in the army when the routes split**: the avatar, the servant (Felicia or Jakob), Rinkah, Kaze,
Sakura and Azura (section 2). On Conquest, Sakura and Rinkah leave at B006 and never return; Kaze returns in
B011.

**Route-only people** (placed on one or two routes only) [high]:

| Available on | People |
|---|---|
| Birthright + Revelation only | Rinkah, Sakura, Hana, Subaki, Saizo, Orochi, Hinoka, Azama, Setsuna, Hayato, Oboro, Hinata, Takumi, Kagero, Reina, Kaden, Ryoma, Scarlet |
| Conquest + Revelation only | Gunter (back from B015 / C007), Elise, Arthur, Effie, Odin, Niles, Nyx, Camilla, Selena, Beruka, Laslow, Peri, Benny, Charlotte, Leo, Keaton, Xander |
| All three routes | the avatar, Felicia, Jakob, Kaze, Azura, Silas, Shura |
| Castle only | Izana (A018 / B022), Fuga (C018), Yukimura (A022), Flora (B018 / C022) |
| Paralogue only | Mozu (X001: team 2, then `SetBID` + `Transfer(0)`) |
| None found | Anna |

So join spots are route-specific, and the shuffle has to be decided per route: Birthright spots, Conquest spots
and Revelation spots. On Revelation many people have two join rows: the main Person row (used on Birthright or
Conquest) and a HANDOVER row (used on Revelation). Both must point at the same new person.

## 5. The public tools' known breaks, located in these files (facts, not fixes)

| Pitfall (docs/collab/FATES_RANDO_RESEARCH_GROK.md) | What these files show at that spot |
|---|---|
| Conquest 9: the Nyx talk | B009 places Nyx in group `Enemy` on **team 2**. The script calls `ev::UnitSetBID "BID_その他"` and `ev::UnitTransferByIndex 0` on `PID_ニュクス` [high for the calls]. The scripts name her PID as a literal, so a person shuffled into this spot also needs that literal changed. |
| Conquest 16: the spare prompt | In B016, Peri (`PID_ピエリ`) is the context for `ev::UnitRecreate "PID_B016_ボス" 1` and `ev::UnitSetBID "BID_賊"`. Shura's Conquest HANDOVER row is in B016 `Support01` [medium]. |
| Revelation "8": two Hayatos | C009 places `PID_C_ツクヨミ` (Hayato's Revelation row) **twice** in `Support01`: two entries with different items [high]. Only one of them can be placed per play. A swap that changes one entry and not the other gives two different people. |
| Revelation 13: invisible obstacles | C013 places Kaden and Keaton in `Player` (both beast units, flag `SPID_ラグズ`) [high]; the map is `Btl_RuinsCityAmuse`. What turns invisible is not in the tables read here [low]. |
| Ninja maps needing a flier | not a join fact; out of scope here. |

## 6. What this means for the shuffle design (input for the design step, not decided here)

- A "join spot" = (route, chapter file, Dispos group, the PID literal in that placement), plus any script call
  in that chapter that names that PID.
- Without a script rewriter, the safe shuffle edits only the Person rows (who the PID *is*: class, stats,
  name/portrait fields). It leaves the Dispos PIDs and the scripts alone. This is probably also the FE8 port's
  approach (the person record is swapped and the scenes keep their slots) [low until the design step checks the
  FE8 port's Recruitment code].
- Each HANDOVER row must be swapped together with its main row (Revelation joins at higher levels).
- People with scripted exits (section 4), Azura and the avatar either stay fixed or have their exits move with
  them.
- The castle joins (Izana, Fuga, Yukimura, Flora) and Mozu's paralogue are separate small pools.
