# The randomizer page

**For the owner.** The page should read like a menu, not a lab notebook. A switch says what changes in the game. Two rows that do the same job become one. An old seed still means the same game, under the old name, even if the page no longer shows that name.

Status 2026-11-20. Public tools for what fans expect: [Ignis](https://github.com/thane98/ignis), [the upgraded script](https://github.com/lashoun/upgraded-fefates-randomizer), [the 2016 thread](https://gbatemp.net/threads/wip-fire-emblem-fates-randomizer.452268/). No code copied.

## The page

**Basics**

| Key | Label | What the player reads |
|---|---|---|
| randomizer | Randomizer | On uses the switches below. Off is the original game. Default off, so a normal start is unchanged. |
| seed | Seed | The same seed and the same switches make the same game. You can send the seed. Default is a new one each time. |
| difficulty | Difficulty | Easy, Normal, or Hard. This sets how much stronger enemy weapons and bosses get. Default Normal. |
| spoiler_log | Spoiler log | On writes a list of what changed, next to that seed. Default on, so a surprise is a choice. |

A **Randomize everything** button is not a seed. It turns the safe switches on. It does not turn on a full identity swap, Nuzlocke, or children.

**Characters**

| Key | Label | What the player reads |
|---|---|---|
| recruit | Who joins where | Off: nobody moves. Route: people swap spots inside this story. Any: any story, and join levels can be wrong. Default off. |
| recruit_look | How they look | Keep: the face and the lines stay. Full is grey until the scene swap exists. Default keep. |
| recruit_class | Their class | Own: they keep their class. Slot: they take the class of the spot. Default own. |
| recruit_stats | Their stats | Fit the spot: their stats are levelled to that chapter. Slot: they take that spot's stats. Default fit the spot. |
| keep_royals | Royals keep class | On: Corrin, Azura, and the royal a chapter is named for stay that class. Default on. |
| personal_skills | Personal skills | Keep, swap between people, or a random skill they can have. Default keep. |
| children | Children | On: a child's class, growths, and one skill change. Parents stay. Grey on Seal: that story has no children. Default off. |

**Classes**

| Key | Label | What the player reads |
|---|---|---|
| classes | Classes | On: people can start in another class they are allowed to be. Default on. |
| trees | Class trees | Own side, or any side. Default own side, so a Hoshidan does not start as a Nohrian class. |
| assign_evenly | Spread classes | On: fewer people share the same class. Default off. |
| promotions | Promotion choices | On: the two Master Seal choices are shuffled inside the same rank. Default off. |
| promotion_sides | Promotion side | Own side, or any. Default own. An old seed that said any stays any. |
| reclass | Heart Seal classes | Keep, or a random class that seal can already offer. Default keep. |

**Growths and stats**

| Key | Label | What the player reads |
|---|---|---|
| growths | Growths | On: growth percents change. Default on. Select on the stat page shows them. |
| growth_mode | How growths change | Share the total, nudge each, or roll new ones. Default share the total. |
| growth_variance | How far growths move | A percent. Default 30. The total of each stat still ends between 20 and 100. |
| adjust_hp | HP grows more | On: HP gets a larger share. Default off. |
| join_stats | Join stats | On: the stats someone joins with can change. Default on. |
| bases_mode | How join stats change | Share the total, or nudge each. Default share the total. |
| base_variance | How far stats move | A small number. Default 5. |
| scale_to_level | Fit the chapter | On: a later join is scaled to that chapter's level. Default on. |
| class_growths | Class growths | Off, or each class growth moves a little. Default off. |
| class_growth_variance | Class growth step | In steps of 5. Default 10. A stat that was 0 stays 0. |
| class_bases | Class bases | Off, or each class stat moves a little. Default off. |
| class_base_variance | Class base step | Default 2. |
| class_move | Class movement | Off, 1 farther, or 2 farther. Nobody moves less, so enemies can still reach you. Default off. |

**Items and shops**

| Key | Label | What the player reads |
|---|---|---|
| starting_items | Starting items | On: what someone joins holding can change, if they can still equip it. Default off. |
| shops | Shops | On: shop stock can change. Default off. |
| shop_sides | Shop sides | Own side, or both. Default own. |
| rewards | Castle rewards | On: a castle prize can be another item. Default off. |
| weapon_stats | Weapon stats | On: might, hit, crit, avoid, and staff uses move a little. Price does not. Default off. |
| weapon_traits | Special powers | The percent chance a weapon gains one power. Default 0, which is off. |
| wild_traits | Wild powers | On: brave, a counter blow, or a heal can be rolled. Default off. These are strong. |

**Enemies and bosses**

| Key | Label | What the player reads |
|---|---|---|
| enemy_classes | Enemy classes | On: a generic enemy can be another class of the same kind of weapon. Default off. |
| boss_classes | Boss classes | On: a boss with no story role can change class, same rank. Named bosses stay. Default off. |
| enemy_trees | Enemy trees | Own side, or any. Default own. |
| enemy_weapons | Enemy weapons | On: an enemy's weapon is swapped for another of the same kind. Default off. |
| enemy_growths | Enemies grow faster | Off, a flat add, or more for classes that already grow fast. Default off. |
| enemy_buff | Extra enemy growth | A percent. Default 10. Used only if the row above is on. |
| enemy_levels | Enemy levels | How many extra levels. Default 0. |
| tougher_bosses | Tougher bosses | On: bosses gain health and might from Difficulty. The person you recruit later is not changed. Default off. |
| enemy_drops | Enemy drops | The percent chance an enemy holds a drop, in steps of 5. Default 0. |

**Extras**

| Key | Label | What the player reads |
|---|---|---|
| music | Music | Off, map themes, or maps and battle themes. Story scenes and sung songs stay. Default off. |
| nuzlocke | Nuzlocke | On: a death stays dead after a reset. Classic is locked. A lost chapter can be restarted. Default off. |
| recruits | Who counts | All who join. One per chapter is grey: a story ally cannot be told from a recruit. |

## What comes off the page

| Old key | Becomes | Old seeds |
|---|---|---|
| growth_mode slice1 | growths on, mode share-the-total | The old name still runs the old shuffle. The page does not say slice1. |
| bases_mode slice1 | join stats on, mode share-the-total | Same. |
| growth_min, growth_max | Removed | Ignored. Totals are clamped to 20–100. |
| upgrade_rank, enemy_upgrade | difficulty | A seed with chance 0 does not rank weapons up. |
| boss_stats, boss_max_boost, boss_variance | tougher_bosses | Off stays off. On uses 10% health and 1 might, times 1, 2, or 3. |
| promotions off/on as two words | one switch | Off stays off. |
| recruit_look full | grey | Old seeds that said full wait for the scene round. They do not half-swap. |

## What fans use that we do not have yet

| Idea | Add? | Why | Hard? |
|---|---|---|---|
| Preset buttons | Later | A Classic and a Chaos button save clicks. Not a new rule. | Page only |
| Spoiler log | Yes | Ignis and the upgraded script both leave a list. Players share it with the seed. | Already written |
| Randomize everything | Yes | One button. It must not turn on the dangerous rows. | Page only |
| Portraits and names | No, until the scene round | A painted face already failed. The full swap brings the real picture. | Needs the game |
| Random supports | No | Supports in this game are unfinished in Seal, and a random pair can open a child map. | Needs the game |
| Map edits | No | A moved tile is how a door becomes unreachable. | Tables, high risk |
| Dragon Vein users | No | Removing the last one stops a map. We already keep one. | Already a guard |
| Stat boosters, EXP, gold | Later | Fans use them. They are not why a seed is fun. | Tables, or the game |
| Weapon ranks | No | A rank the class cannot hold is a stuck unit. | Tables |
| Accessories | No | Not what the public Fates tools sell. | Tables |
| Same seed | Already | Say it on the Seed row. Do not add a switch. | Done |

## Do these first

1. Take the leftover rows off the page, and keep the old names underneath so a seed does not change.
2. Clamp every total growth to 20–100, and stop showing min and max.
3. Let Difficulty be the only knob for stronger weapons and tougher bosses.
4. Add the spoiler log switch and the Randomize-everything button.
5. Leave full identity, one-recruit, and Seal children grey, with the reason on the row.
