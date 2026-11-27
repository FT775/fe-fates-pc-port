# Fates rules, for cross-checking

ELI5 / ETA: This is a short list of the game's rules, taken from public guides, so a later code reading can be checked against them. It is not a dump of the game. Where a guide hedged, or two guides disagree, the code wins. Nothing here is built.

Status 2026-11-10. Own words. No game file opened. No stat table copied.

A line is [high] when two independent pages agree, or one page states it without hedging. [med] is one page, or a page that is a stub. [low] is a preview that says it is not sure. [gap] means a page that names this game was not found, so the number is not here on purpose.

## Attack Stance and Guard Stance

A unit is in one or the other, never both. [high]

Attack Stance. An ally standing next to the attacker, not paired onto the same tile, adds a follow-up right after the attacker's first strike. The follow-up always attempts. It has its own hit roll, so it can miss. It does not fire the ally's offensive skills. It keeps the ally's weapon traits (effectiveness, a brave weapon's extra hit, a debuff on a hit). It follows only the first strike, not a later one. A pair that is in Guard Stance blocks this follow-up. [med, Fire Emblem Wiki, Attack Stance; the "always attempts" and "own hit roll" also match the Serenes preview]

The follow-up's damage is half of what that ally would deal alone. [med, wiki only. The Serenes preview says "possibly reduced" and does not give a fraction. Code wins.]

Guard Stance. The player moves next to an ally and picks the pair command. The two units occupy one tile. The unit that used the command is the support. The lead's stats go up by an amount that depends on the support's class and the support rank. Enemies can be found already paired. They do not use the command. [med, wiki Guard Stance; the command and the one-tile pair match the Serenes preview]

The pair shares one shield gauge. It starts empty, holds 10 points, and a full gauge makes the next incoming hit do no damage, including a debuff that hit would have applied. Dealing or taking a hit, even a miss, adds 2. A multi-hit skill adds 2 per hit. If the pair neither attacks nor is attacked, the gauge falls by 1 at the turn's end. [med, wiki. The Serenes preview agrees on +2 toward 10 and on a full gauge negating the hit, and it marks that part "so far it seems". The decay, the miss still counting, and the debuff block are wiki only.]

In a fight where both sides are paired, only the two leads take damage. [low, Serenes preview only]

## Weapon triangle

Three pairs, not three weapons. Sword and tome beat axe and bow. Axe and bow beat lance and dagger. Lance and dagger beat sword and tome. A pair is neutral to its partner. [med, Fire Emblem Wiki, Weapon Triangle, the Fates paragraph]

The bonus follows the attacker's weapon rank. The wiki prints an asterisk on every number and does not say what it means. Do not treat the asterisk as a second rule. [med, same table]

| rank | advantage | disadvantage |
|---|---|---|
| E, D | +5 hit | −5 hit |
| C | +10 hit | −10 hit |
| B | +1 damage, +10 hit | −1 damage, −10 hit |
| A | +1 damage, +15 hit | −1 damage, −15 hit |
| S | +2 damage, +20 hit | −2 damage, −20 hit |

A dual weapon reverses the pair's direction. [med, same page, one sentence, cut short in the copy read here. Confirm in code before an option uses it.]

## Dragon veins

One command. The unit stands on a marked tile and uses it. The tile works once. The effect is chosen by that map, not by the route: a path, a dried river, a bridge, a gust, a blight, a heal. Skirmishes do not offer the command; a map whose vein changed the ground is already in the changed state there. [med, Fire Emblem Wiki, Dragon Vein]

There is no per-route effect table to copy. A list of every chapter's vein would be a walkthrough. The cross-check is: one command, the effect lives in the map data, all three routes use that same command. Who may use it is a fixed set of units, also data, not a formula. Not copied here.

## Skill activation

A proc skill names its own rate. The rate is a stat times a small number, or the stat itself, as a percent. A skill with no percent is not a roll. [high, Serenes Forest class-skill pages, the pattern in the descriptions]

Examples of the pattern, not a skill list:

- Skill times one half of one percent. [high, Serenes, one sword skill]
- Skill times one quarter of one percent. [high, Serenes, one dagger skill]
- Skill times one and a half percent. [high, Serenes, one tome skill]
- Luck, as a percent. [high, Serenes, more than one skill]
- One class skill adds 10 percent to activation rates. Another adds 15 percent to both sides' activation rates during the fight. [high, Serenes]
- A personal skill adds 20 percent to rates that already depend on Luck. [high, Serenes personal-skill page]

The full list stays on those pages. Do not copy it into this repo. A code reading should match the pattern, then the individual rate, not a pasted table.

## Growths

A level-up rolls each stat against that unit's growth. A growth over 100 grants the extra point first and rolls the remainder. [high, Fire Emblem Wiki, Growth Rate, series-wide. Not re-checked against this game's code.]

This game's avatar adds a boon and subtracts a bane from those rates. The modifiers are added together. The page lists them; they are not copied here. [high, Serenes Forest, Hoshidan growth rates, the method. The numbers were not needed for the method.]

Personal growth and class growth are published as separate tables. The cross-check is that a displayed growth is the sum, plus the avatar's boon and bane when the unit is the avatar. [med, those tables exist as separate pages. This note did not add a row by hand.]

## Children

A child is recruited from a side map after one parent reaches the highest support rank, and after chapter 6 of whichever route. The child is optional. [high, Fire Emblem Wiki, Child Character, the Fates section]

The level formula, rewritten from Serenes Forest's base-stats page. "Personal" means the shown stat minus the class base. Call C the child's own absolute base plus (levels above 10) times the child's full growth. Then:

shown stat = class base + C + parent bonus

parent bonus = (father's personal minus C, or 0 if that is negative, plus the same for the mother) divided by 4

The bonus cannot exceed (C / 10) + 2, rounded down. [high, Serenes Forest, the formula as printed on the Revelation and Conquest base-stats pages]

A community post found one child's stats that did not match a reading of that same formula, and traced part of the gap to the game rounding twice (once at the pre-promotion level, once after the seal). [med, Serenes Forest forum, one save. Code wins over both the page and the post.]

How the child's growth rate itself is built from the two parents was not on the page that printed this formula. It is not guessed here. [gap]

## Hit, avoid, critical, damage

No page read for this note both names this game and states these formulas. A calculations page at a Fates address returned another game's formulas. Those numbers are not used. [gap]

Do not cross-check code against a formula this note does not contain. When a page that names this game is found, add the line here before anyone treats a number as the rule.

## Death rules

Three of them. [high, Fire Emblem Wiki, Phoenix Mode]

- Classic: a defeated unit is gone.
- Casual: a defeated unit is out for the rest of the battle and returns next chapter. The page defines this by contrast with the third rule.
- The revive-next-turn rule: the unit is out until the next player turn starts, then returns at full health.

The revive-next-turn rule can only sit on Normal. Choosing it while on a harder difficulty drops the difficulty to Normal. A save that started on Classic and is switched to it cannot go back to Classic. It can be switched to Casual. [high, same page]

That last pair of limits is the game's own flag, not a switch we invent. The options note already refuses an overlay. These limits are why.

## Routes, experience, gold

Birthright can train between chapters. Conquest cannot. That is a difference in what fights exist, not in how a fight pays. [high, Serenes Forest, Separate Versions, for the training split. Code, 2026-11-10, for the pay.]

Experience rows are picked by the difficulty byte only. There is no route-dependent experience rule. Do not cross-check a Birthright-versus-Conquest experience formula. There isn't one. [high, code, Claude's step 4 reading. The tables were not copied here.]

Revelation sits between the two in difficulty, and is meant to be played last. [high, Serenes Forest, Separate Versions]

A later interview summary adds: Birthright enemies often have no skills even on the highest difficulty; Conquest enemies have skills, including enemy-only ones on the highest difficulty; Revelation has the between-chapter fights and enemies a bit weaker than Conquest. [med, Fire Emblem Wiki, citing a 4Gamer interview. The interview itself was not opened.]

On the Conquest side, the only between-chapter experience map named by the guide is a paid map. A paid map is also the named way to grind gold. Story battles still give experience, on the difficulty's row, not a route row. [high, Serenes Forest, the Europe DLC maps page, for the maps. Code, for which row.]

No gold-per-kill formula was on a page that names this game, and the code reading did not state one. Not guessed. [gap]

## What this sheet is for

A code reading that disagrees with a [high] line should say so in the inbox, with the function name, not a pasted dump. A [gap] is not a license to fill in the usual number from another Fire Emblem. A [med] or [low] line is a hint, not a test oracle.

## Sources

Read 2026-11-10.

- https://serenesforest.net/fire-emblem-fates/pre/attack-guard-stance/
- https://fireemblem.fandom.com/wiki/Attack_Stance
- https://fireemblem.fandom.com/wiki/Guard_Stance
- https://fireemblem.fandom.com/wiki/Weapon_Triangle
- https://fireemblem.fandom.com/wiki/Dragon_Vein
- https://serenesforest.net/fire-emblem-fates/hoshidan-classes/class-skills/
- https://serenesforest.net/fire-emblem-fates/hoshidan-characters/personal-skills/
- https://serenesforest.net/fire-emblem-fates/hoshidan-characters/growth-rates/
- https://fireemblem.fandom.com/wiki/Growth_Rate
- https://fireemblem.fandom.com/wiki/Child_Character
- https://serenesforest.net/fire-emblem-fates/revelation/character-base-stats/ (formula only; the stat rows were not copied)
- https://forums.serenesforest.net/tags/data/ (one post on the child formula)
- https://fireemblem.fandom.com/wiki/Phoenix_Mode
- https://serenesforest.net/fire-emblem-fates/pre/separate-versions/
- https://fireemblem.fandom.com/wiki/Fire_Emblem_Fates
- https://serenesforest.net/fire-emblem-fates/miscellaneous/downloadable-content/europe/maps/
