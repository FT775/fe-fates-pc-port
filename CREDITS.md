# Thank you

This port stands on other people's work. Each entry says what we used and how. Code is used only
where the licence allows it; GPL projects were read for facts (offsets, field meanings, format
notes), never copied. New entries are added whenever a project or page actually helps (owner's rule,
2026-11-11; kept by Claude and Grok).

## Software we build on

| Project | Author | Licence | How we use it |
|---|---|---|---|
| [Zakuro](https://github.com/fearkov/zakuro) | fearkov | MIT | The 3DS runtime the port runs on; our patches in `patches/zakuro/` |
| [3dsrecomp](https://github.com/fearkov/3dsrecomp) | fearkov | none (no licence file; not included; fetched at a pin for your own build) | Used unmodified: recompiles the game's code for the PC; its bundled hints cover this exact dump. `tools/readable/stub` restates 3dsrecomp's documented interface (some declaration lines match) so syntax checks run without it; no 3dsrecomp program code is included. |
| [fe-awakening-recomp](https://github.com/Zelkin1/fe-awakening-recomp) | Zelkin1 | MIT | Reference for the Awakening extras and Zakuro patches our tooling grew from |

## Facts and documentation

| Source | Author(s) | What it helped with |
|---|---|---|
| [Paragon](https://github.com/thane98/paragon), [mila](https://github.com/thane98/mila) | thane98 | FE14 field maps and sheet types, cross-checked as facts (GPL: not copied) |
| [fefates-tools wiki](https://github.com/RainThunder/fefates-tools/wiki) | RainThunder | The IS .bin file format notes |
| [SPICA](https://github.com/gdkchan/SPICA) | gdkchan | BCH (H3D) format facts for the picture tool |
| [3dbrew](https://www.3dbrew.org/) | 3dbrew contributors | GPU registers, BCSTM, Mobiclip, system calls |
| [Serenes Forest](https://serenesforest.net/) | Serenes Forest staff and forum | Fates rules, stats, stances, versions, DLC lists |
| [Fire Emblem Wiki](https://fireemblem.fandom.com/) | Fandom contributors | Stances, weapon triangle, dragon veins, growth rules |
| Fates 60 fps / cheat thread on [GBAtemp](https://gbatemp.net/threads/fire-emblem-3ds-games-awakening-fates-echoes-true-60-fps-patches-cheat-codes-without-speedup-all-regions.684737/) | thread authors | Screen-extras research |
| [Live2D licence pages](https://www.live2d.com/en/sdk/license/) | Live2D Inc. | Why the petting scenes stay the game's own code |

## Fan mods (not included)

Seal of Flames by Laz14 (https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0) is a separate fan mod. The mod is never included.

## People

- The owner, for the idea, the ROM dump, the in-game checks and the patience.
- Grok (xAI, via Hermes Agent): creative lead and tactician: plans, reviews, rules and format research.
