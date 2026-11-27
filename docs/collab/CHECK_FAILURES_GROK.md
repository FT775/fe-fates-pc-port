# Why five chapters failed the check

**For the owner.** Two Revelation chapters got stuck on one randomized seed each. The unrandomized game passed them. Three Seal of Flames chapters fail the battle-save reload every time, randomizer off included. That second failure matches a warning the author already printed. I could not find public names for those three Seal chapters.

Status 2026-11-20. Public pages only. No game file opened.

Sources: [chapter list](https://fireemblemwiki.org/wiki/List_of_chapters_in_Fire_Emblem_Fates), [Frozen Sea](https://fireemblemwiki.org/wiki/Frozen_Sea), [Frozen Sea, Thonky](https://www.thonky.com/fire-emblem-fates/chapter-12-frozen-sea), [The Vallite King](https://fireemblemwiki.org/wiki/The_Vallite_King), [Vallite King, Gamer Guides](https://www.gamerguides.com/fire-emblem-fates-revelation/guide/main-campaign/chapters-21-28/chapter-26-the-vallite-king), [Seal of Flames](https://gamebanana.com/mods/656034). The trailer does not name chapters. [Trailer](https://www.youtube.com/watch?v=ULnFh8notDQ).

## Which chapters

**C012 is Revelation 12, Frozen Sea.** Win by defeating the boss on the northeast ship. Your army starts stuck on ships. Enemies can climb aboard. Fliers can cross the ice. At turn 6, veins rise so the others can walk off. The public count is a set army plus a wave, not an endless one. [Wiki](https://fireemblemwiki.org/wiki/Frozen_Sea), [Thonky](https://www.thonky.com/fire-emblem-fates/chapter-12-frozen-sea).

**C026 is Revelation 26, The Vallite King.** Win by defeating the boss in an open throne room. New enemies do not stop. Veins freeze the pools they come from, for a while. Two people carry a ward that heals and helps them dodge, and the ward follows them. [Wiki](https://fireemblemwiki.org/wiki/The_Vallite_King), [Gamer Guides](https://www.gamerguides.com/fire-emblem-fates-revelation/guide/main-campaign/chapters-21-28/chapter-26-the-vallite-king).

**R021, R023, and Y004** are not named on the public page or in the trailer. R, S, and Y are the mod's own prefixes, not Birthright, Conquest, or Revelation. I will not guess the titles.

## Why the enemy phase did not come back

Both Revelation failures were one seed of three, with everything randomized, and the same chapters passed with the randomizer off. That is not a chapter that always hangs.

Frozen Sea can run long if the new classes are fliers or staff users. Fliers ignore the ships. Staff users heal instead of finishing a fight. The robot waited about 6300 frames and gave up. A long turn looks like a hang.

The Vallite King is the stronger case. Reinforcements do not stop. A seed that turns those spawns into staff users, or into fliers who keep moving, can fill the wait without the player phase ever returning. The veins that stop the spawns are not used if the robot only waits.

Not the likely cause: fog, an auto-battle, or a script that never hands back. Those would fail with the randomizer off too. They did not.

**Check:** rerun that one seed with a longer wait, and count enemy actions. If the player phase returns, the robot stopped too soon. If the enemies are still acting after the longer wait, the seed made a turn that does not end. Do not call it a port bug until that count is written down.

## Why the Seal reload disagrees

The author's page says mid-battle saves and bookmarks may not load. Use a save state, and save between chapters. These three fail with the randomizer off, so our randomizer is not the cause. The other Seal chapters passed after the inner-name fix, so this is not that bug again.

A reload whose unit list changed is what that warning describes: a unit the chapter creates, removes, or joins after the save is not the same list when the save comes back. R023's person file sitting under the Revelation person folder is a clue that this chapter reused another route's people. It is not proof. I found no comment that names these three ids.

**Check:** on a randomizer-off run, write down which unit is missing or extra after the reload. If it is a unit the chapter adds by event, this is the mod's save, and the author's warning already covers it. If the same units are present and only our compare says they differ, it is our check. Do not patch the mod to force the save.

## The guess

| Chapter | Guess | Prove it by |
|---|---|---|
| Frozen Sea | A long enemy turn on a bad seed. Expected. | A longer wait, and a count of enemy actions |
| The Vallite King | Endless spawns plus a staff or flier seed. Expected. | The same count. If they never stop, the seed is the finding |
| The three Seal chapters | The mod's mid-battle save, which the author already warned about | Which unit id changed. Event unit: mod. Same units: our check |
