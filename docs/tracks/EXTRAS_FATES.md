# Screen extras for Fates

ELI5 / ETA: This is which extra pictures and speeds are worth doing, and which published cheats we will not paste in. Nothing is built. The first look is after a switch exists, not tonight.

Status 2026-11-11. No game file opened. No code bytes copied.

## What Awakening already did

From the Awakening port's `docs/analysis/EXTRAS_USA.md`, read 2026-11-11. That file is about another game. Its addresses are not used here.

Three of its extras are small writes Zakuro applies once a frame: a wider top screen, map sprites that are not snapped to whole pixels, and faster battle pictures. Stock Zakuro can load that kind of file. The addresses were found in that game's code and checked. They are not Fates addresses.

The rest are Zakuro-side, and they only watch that game's title: the bottom screen drawn over the top one, two battle-panel styles, and a mouse pointer on the battle buttons. All three start off. They do nothing unless the layout is top-screen only. A feet builder and redrawn text were left out there, and they stay out here.

Zakuro already has, for any game: top screen only, and a 60-frame in-between picture (frame interpolation) that does not need a game address. [high, that file]

## What public pages say about Fates

| extra | public page | what it claims | use |
|---|---|---|---|
| 60 frames, without doubling the speed | Foxes, GBAtemp, 2026. https://gbatemp.net/threads/fire-emblem-3ds-games-awakening-fates-echoes-true-60-fps-patches-cheat-codes-without-speedup-all-regions.684737/ | Patches and cheat codes for Awakening, Fates, and Echoes, all regions, that do not double the speed the way older cheats did. The author tested the European copies. A later post says the Fates (USA) patch ran, and that Fates did not keep the sped-up critical portraits Awakening still had. On a real 3DS, some people reported a crash when a 3D battle loaded. The author had not tested a console, and said a console may not reach 60 and will then slow down. | a lead. Not a patch we apply |
| 60 frames, by doubling the speed | NanashiFinal13, in the GBAtemp 60-frame thread, quoted in a search of that forum, 2026-11-11 | One write makes the game run faster, about twice, and the poster says battles then show 55–60. | do not use. Twice as fast is not 60 frames |
| 16:9 / widescreen | no page opened for this note named a Fates widescreen hack. A second look the same day (a GBAtemp search for fates 16:9 or widescreen, and a GitHub code search for fates widescreen citra) also returned no such hack. The GBAtemp search page itself was unrelated posts, so that search is weak. The gap stands | — | [gap] |
| faster battle pictures, as its own code | no page opened for this note, apart from the two rows above | — | [gap] |
| Citra / Azahar | the same Foxes thread | One person got the Awakening patch working in Azahar after a reinstall, and said Fates ran too. Another build crashed on launch. | emulator reports, not a design |

The codes themselves are not copied here. A code that long, and region-specific, does not go into this repository as bytes.

## What we will do

Nothing in this list is on until a reading names the Fates site, or until it is already a Zakuro switch that does not touch game code. Off is the original game. A capture run has every extra off, same rule as the options file.

| extra | how it would be found | how it would be checked | risk |
|---|---|---|---|
| Top screen only | already in Zakuro. No Fates code | one battle and one map, top screen only. The bottom screen is gone, and the cursor still moves | none if it is Zakuro's own layout. Do not force it on |
| In-between frames | already in Zakuro's graphics settings. No Fates code | one battle. The picture is smoother and the hit still lands on the same frame as with it off | a smoother picture that skips a hit is a bug. Off if a battle desyncs |
| Faster battle pictures | the options already named: `animation_skip` and `anim_speed`. Not a pasted code | one battle, skip on, then speed up. The forecast numbers and the hit match a normal battle | skipping the picture must not skip the result. Job 12 names the function, or this stays off |
| 60 frames, real | a reading of the frame-timing sites, after the Foxes thread is used only as a list of places to look. Not by pasting the code | a battle and a map, timed. The clock and the enemy turn must not run twice as fast. A suspended battle must still resume | the old public code doubles speed. The new one is untested by us, and some console users crashed on a 3D battle. Do not ship either until a reading and a replay agree |
| 16:9 | a reading of the projection and the map camera. Awakening's sites are not a start | a map and a battle. The picture is wider, units are not cut off, and a touch still lands on the same square | a wider camera that moves the cursor onto the wrong square is a bug. No public Fates hack was found, so this waits |
| Bottom screen over the top, battle panels, touch pointer | Fates scene markers, read the way Awakening's were. The Awakening title gate must not be widened to this game on a guess | top screen only, cursor on a unit, open and close. B while it is open must not cancel the game. Panels must not show in a conversation | wrong markers draw garbage or steal the cancel button. Off until the markers are named |
| Smooth map sprites | a reading of the snap, if a map sprite is visibly snapped | a map, walk one unit. The sprite is not blurrier, and the square it stands on is unchanged | a snap removal that changes which square is occupied is a bug |
| Feet, redrawn text, a launcher that downloads someone else's build | — | — | cut. Another game's builder, or game text in the repository, or a download we do not control |

## Owner minutes

None for this file. The first look is one battle with top-screen only, about 5 minutes, after that layout is the one PLAY starts in, and not during a capture. The 60-frame and 16:9 looks wait on a reading.
