# Character shuffle (join order): the pitfalls, before any design

**For the owner.** This page lists what can go wrong when the randomizer moves people to other join spots,
and how each problem can be tested with saves and recordings we already have. Nothing is built here: no
code, no game run, no build. It is the checklist the design (next step) has to answer. Status 2026-11-20,
round 53 side task "pitfalls" (owner: "Yes, build it", the character shuffle).

Sources and credit. The breaks marked **[public]** were found by the public Fates randomizers: Ignis and
Paragon (thane98), the upgraded Fates randomizer (lashoun), and the 2016 GBAtemp randomizer it grew from.
They are GPL. This page takes **facts only** from their public pages (read 2026-11-20); none of their code,
patches or files. The GBAtemp thread did not open today (403), so its facts come only from
docs/collab/FATES_RANDO_RESEARCH_GROK.md. Facts marked **[ours]** come from our own tables (read with
tools/randomizer/gamedata.py on the owner's own extracted files) and from our robot recordings
(config/harness/routes.json). Nothing here contains game text or game numbers.

## 1. What a swap has to carry (the FE8 port's lesson)

The FE8 port's Recruitment (FE8 port docs/port/PLAYING.md, "Recruitment"; port/reforged/reforged_rando_recruit.c)
keeps each join **spot** as it is, keyed by the spot's character id, so every script, talk and check that names
that id still works. What changes is *who the spot is*: the name in every text, the portrait, the stats
(own class matched to the spot's tier, own stats levelled to the spot's level), weapon ranks, battle colours.
The lords and Myrrh never move; men fill men's spots unless "Cross-gender" is on; spots whose story fights need
something (a melee hit, a ranged hit, a flier) are filled first with someone who has it.

For Fates the same approach maps onto the Person row **[ours]**: each person row holds its own portrait id
(`fid`), model id (`aid`) and name text id (`mpid_name`) beside the class, stats, skills and flags. So a spot
can be made to *look and read* like another person by giving its row the other person's ids, without moving
any script. What that does **not** reach (not traced, each needs its own check):

- Names written literally inside dialogue text (rather than looked up from the person's name id). The FE8
  port replaces names in every decoded text; Fates would need the same on its message archives.
- Voices. A spot keeps the voice lines of the person it was.
- 3D story scenes. The 2016 randomizer rewrote dialogue **and** 3D scenes for a swap **[public]**; whether a
  scene picks its model from the Person row or names a model itself is not traced.
- Support conversations, S ranks and children (section 4).

## 2. The known breaks [public], and what our data adds

| # | Break | What the public tools say | What we know [ours] | Guard idea for the design |
|---|---|---|---|---|
| 1 | **Revelation 8: two Hayatos** | Hayato is not replaced, so two of him can be recruited. Comes from the original 2016 randomizer | Hayato has **no player placement row in Revelation 8** (his first player row is Revelation 10). He joins by the chapter's script, not by a map placement. Five more in-scope people have **no player placement row at all**: Izana, Fuga, Yukimura, Flora, Anna. A shuffle that only rewrites map placements misses all six | A swap is keyed on the person id (FE8 style), never on placement rows, so a script join brings the new person too. Test: after Revelation 8, the army holds the spot's person once and the person who filled it once |
| 2 | **Conquest 9: Nyx talk crash** | Talking to Nyx crashes; break the wall near her first | Nyx stands on the green team in Conquest 9 (and in Revelation 15) and joins by Corrin's talk. Our original-game recording cq-ch9 talks to her on turn 3 **before** breaking the wall, with no crash. So the crash belongs to the randomized game | Do not move or edit the talk. The swapped person takes Nyx's id; the talk stays Nyx's talk. Test exactly the order the crash needs: talk before the wall |
| 3 | **Conquest 16: the spare prompt freezes** | The game freezes after the prompt to spare Shura. Their workaround removes that chapter's script (no reward, route playable) | Shura is the enemy in Revelation 15 and a player in Revelation 26; in Conquest 16 he is the hidden boss revealed by talking to the four green lancers (cq-ch16 route, turn 21) | Never delete or rename a chapter script to "fix" it (F-043 already says so). Keep Shura out of the pool until Conquest 16's prompt has been run in a randomized game |
| 4 | **Revelation 13: obstacles invisible** | No fix known; cause not stated | The start pocket is shut by rubble that has to be carried away (Sakura's Grab in rv-ch13). Kaden and Keaton join at this chapter's start | Look at the rubble on turn 1 of a randomized Revelation 13 (a picture before any fight, so the recording still fits) |
| 5 | **Ninja maps need a flier** | Revelation 11 and Birthright 10: the ninja village door cannot be reached without a flier; they moved one tile | Same map in both chapters (rv-ch11 notes it is Birthright 10's map). **Slice 1 already has this risk**: class changes can leave a route without a flier, and no guard checks fliers (docs/RANDOMIZER.md section 3, "Not checked") | A "flier per route before Birthright 10 / Revelation 11" guard, for the shuffle **and** for slice 1. Never move a map tile |
| 6 | Chapter 2 phantom unit | An immobile unit can appear near the top left; kill it last | Not seen in our randomized robot runs up to Chapter 2's first move (round 47 / 49) | Watch Chapter 2's unit list in the shuffle's robot test |
| 7 | Fresh game only | Using the randomizer on an existing save or branch is unstable | Our in-game page already applies only at a New Game, and a load keeps the save's own seed (round 51, T5) | Same rule: the shuffle is decided at New Game and kept with the save |
| 8 | Route-specific spots | Revelation levels are only right with the Revelation route chosen | Each person row has a `support_route` value: Hoshido people share one value, Nohr people another, Corrin, Felicia, Jakob and a few others a third, and Gunter, Izana, Fuga and Yukimura each a value of their own (meaning not traced) | Level and join spot per route; never copy one route's spot onto another |
| 9 | Language | The files must match the game's language (North American English is not European English) | Our names come from the owner's own files | No change: we read the owner's files |
| 10 | Join items | Without the join-order step, people keep vanilla weapons they cannot use | Slice 1 already swaps carried weapons for the new class | Keep that step after the shuffle, on the spot's placements |

## 3. People who must not move (or need care)

From our tables and recordings **[ours]**, plus the public tools' choices **[public]**:

- **Corrin.** The lord: the story, the dragonstone, every route. The male and female Corrin are two person rows;
  the placements use the male row. Never in the pool (as FE8's lords).
- **Azura.** The singer, in every route, story-critical (already kept in slice 1). Never in the pool.
- **The eight royals.** Ryoma, Takumi, Hinoka, Sakura (Hoshido) and Xander, Leo, Camilla, Elise (Nohr) carry the
  dragon-vein flag, and four of them have personal legendary weapons tied to their person flag (slice 1's
  `--keep-royals`). Revelation 12 was crossed with Sakura's and Takumi's veins in rv-ch12 (Corrin also has a
  vein, so the map can still be crossed, slower). Royals also appear on other routes in story roles. First
  version: royals stay out of the pool.
- **People who appear before they join, under the same id.** In our placements the same person id stands on the
  green or enemy team first: Hinoka, Azama, Setsuna (Birthright 8), Oboro, Hinata (Birthright 9), Takumi (enemy,
  Birthright 10), Reina (Birthright 11, Revelation 11), Nyx (Conquest 9, Revelation 15), Leo and Keaton
  (Conquest 14), Gunter (Conquest 15), Benny and Charlotte (enemy, Revelation 14), Shura (enemy, Revelation 15),
  Mozu (a side chapter). With FE8-style spots the swapped person also *looks* like the enemy or ally in those
  scenes, which is what the player expects; but each of these joins is a talk, a visit or a script event, which
  is where the public crashes are (Nyx, Shura). Each needs its own test before it is shuffled.
- **People who leave and come back.** Gunter is on the map in the shared Chapters 2-3, then gone until his
  route brings him back (rows again in Conquest 15 and from Revelation 7). A spot that leaves by story takes
  its filler with it. Story deaths and departures are in chapter scripts, which our tables do not type yet:
  the design must not assume a filler survives where the spot's person leaves.
- **Units that must survive.** Corrin falling loses the game. Other chapter loss rules are in chapter scripts
  (not traced); escort/defend chapters keep their target ids, and with FE8-style spots the target keeps its id.
- **Out of scope already** (slice 1 rules): children, bond (logbook) units, capture-only people, downloadable
  and enemy-only people, Mozu's special class. Anna is in scope in slice 1 but has no placement row.

## 4. Supports, marriage, children

- **Who can support whom** is stored per person (support lists after the Person block; not typed by our table
  tools yet, docs/TABLES.md "Not done yet"). With FE8-style spots, a spot keeps its own list: the filler gets
  the spot's partners and conversations, shown with the filler's name and face.
- **Gender.** S ranks and marriage depend on the pair's genders (the public upgraded script had to add a
  same-sex patch so everyone could marry **[public]**). A woman in a man's spot would inherit a man's S-rank
  partners. First version: **same gender only** (as the FE8 port's default), cross-gender a later yes.
- **Corrin's supports** are their own list (including the siblings and Azura), and Corrin never moves; the
  partners in it are spots, so they read as their fillers.
- **Children.** Each child row points to its parent through the family index (Kana, Shigure and the others
  have one set **[ours]**); a child's growth is averaged with its parent's, and its side chapter opens from
  the parent's S rank. Children stay off (F-043 #4), but their **parents are spots**: a shuffled parent changes
  what the child inherits. The design has to say whether a child inherits from the spot's data (what the game
  will do) or is left alone.
- **Partner and Friendship seals** list classes from the spouse and the best friend (docs/CLASS_CHANGE.md),
  so they follow the spot's data too.

## 5. What our existing guards need

Slice 1's guards (docs/RANDOMIZER.md section 3) work per route from the people placed on the player's team in
that route's chapters. With FE8-style spots the route membership does not change (it is keyed by the spot's
id), but the class, skills and flags in each spot do. So after a shuffle, re-run on the spot's **new** data:

- **Staff user per route:** a class with staff rank in some spot of that route.
- **Door opener per route:** the lock skill in the spot's personal skills (Kaze, Saizo, Niles and the thieves
  have it) or in the new class's skills. If personal skills travel with the filler, the door openers move.
- **Dragon-vein user per route:** a person flag. If flags travel with the filler, vein users move; royals stay
  out of the pool in the first version, so this stays as now.
- **New guard, also for slice 1:** a **flier** on Birthright and on Revelation before their ninja-village
  chapter (Birthright 10, Revelation 11).
- **Enemy guard chapters** (Conquest 9, 16, Revelation 8, 13: tools/randomizer/enemies.py) stay untouched by the
  enemy part; the shuffle adds its own guard on the same four.
- **The placement hook:** round 50 found that a chapter's units are made in the same frame its placements load
  (fixed in round 51). Join-spot data written to the Person table is applied at New Game, before any unit is
  made, as slice 1 already is.

## 6. Testing each guarded chapter with recordings we already have

All of these saves are in `build/harness/saves/` and the routes in `config/harness/routes.json`. Every one was
made in the original game, so **a join that already happened is already in the save**: to test a join, the
run has to start from the save *before* the join chapter and play that chapter in the randomized game. Our
recorded presses only fit until the first fight that goes differently (round 47: they held up to the first
move of Chapter 2, a battle was not tried). So:

| Chapter | Route (start save) | What fits on recorded presses | What does not |
|---|---|---|---|
| Revelation 13, obstacles | rv-ch13 (rv-ch12-clear) | Turn 1 picture of the rubble; Kaden and Keaton joining at the start, read from memory | the rest of the chapter |
| Conquest 9, Nyx talk | cq-ch9 (cq-ch8-clear); the chain is in build/speed/r9-cq9 | The talk is on turn 3, before the wall: likely reachable if turns 1-2 have no fight that changes. To be checked on the chain's frames | if an enemy phase goes differently, the talk is missed |
| Revelation 9, Rinkah joins at the start | rv-ch9 (rv-ch8-clear) | the join, read at the start | |
| Revelation 11, ninja map and Saizo talk | rv-ch11 (rv-ch10-clear) | the start; the talk is on turn 4 after fights: unlikely to fit | the door (needs the whole map) |
| Birthright 10, ninja map | bt-ch10 (bt-ch9-clear) | the start | the door |
| Revelation 8, Hayato | rv-ch8 (starts at rv-ch6-clear, plays 7 and 8) | the start of Revelation 7 | Hayato joins at the end of a 20-turn battle: the presses will not fit |
| Conquest 16, spare prompt | cq-ch16 (cq-ch15-clear), chain build/speed/cq16 | the start | the prompt comes on turn 21 |
| Chapter 2, phantom unit | bt-ch2 (bt-ch1-clear) | unit list at the first move (rounds 47 and 49 already read it, no phantom) | |

For Revelation 8, Conquest 16, and the two ninja doors, a run that *reaches* the event needs either new
play (not allowed in this round), or the cheat track the owner allowed for "does it run" checks (F-030: "the
purpose of the tests is to make sure it RUNS") with a declared poke such as finishing the battle. That needs
the owner's yes for this use; it is not assumed here.

## 7. Short list for the design step

1. Spots keyed by person id (FE8 style), never by placement rows: fixes the Hayato class of bug and keeps talks.
2. Out of the pool at first: Corrin, Azura, the eight royals, Shura, Nyx (until Conquest 9 is tested), Mozu,
   children and the other out-of-scope people.
3. Same gender only; cross-gender later.
4. Re-run the route guards on the new spot data, and add the flier guard (useful to slice 1 today).
5. Never edit or remove chapter scripts or map tiles.
6. Robot tests on the table in section 6; the far-away events only with the owner's yes for a cheat poke.
7. Not reached by a Person-row swap and needing their own answer: names inside dialogue text, voices, 3D scenes.
