# Community scan

ELI5 / ETA: This is a look at other people's Fire Emblem and 3DS tools, to see if any of them finish our port faster. None of them replace the work already in this folder. Nothing was copied. A credit line is added only when we actually link someone's code. That is not this note.

Status 2026-11-11. Public pages and GitHub repository records only. No game file opened. No code copied.

Dates below are the repository's last push, from the GitHub record read that day, unless noted.

## What we already have, and should not replace

Our symbol list is `config/functions.csv`. A GitHub search for `fire emblem fates decomp` returned no repositories. [https://api.github.com/search/repositories?q=fire+emblem+fates+decomp, 2026-11-11, total_count 0]

The check we already use on a rewritten function is a host comparison against the original instructions, with a mismatch count. The stance batch has that, and it came back clean. No public project found here offers a Fates symbol list or a better check. Do not wait for one.

Zakuro is already the player (MIT, pin `c856685`). Do not switch the player to Citra, Azahar, or Lime3DS. Those are emulators. They do not rewrite our rules.

## Projects

| project | author | licence | last push | what it offers | how we may use it | time | risk |
|---|---|---|---|---|---|---|---|
| [Paragon](https://github.com/thane98/paragon) | thane98 | GPL-3.0 | 2026-11-09 | FE14 editor. Type files name castle lists, JobIntro, AcceShop, and ordinary tables. Still active | facts only. A checklist when a layout is stuck. Already used that way in `docs/tracks/formats/CASTLE_SHEETS.md` | days on one stuck file, not weeks on the port | copying the type files or the Rust would put GPL in our tree |
| [Mila](https://github.com/thane98/mila) | thane98 | GPL-3.0 | 2025-03-08 | Rust reader for the ordinary `.bin` and LZ, FE13–FE15 | facts only. Our table tools already read that format | none on the critical path | same GPL line |
| [Exalt](https://github.com/thane98/Exalt) | thane98 | GPL-3.0 | 2021-12-08 | script editor for 3DS Fire Emblem | facts only, and only if a chapter script must change. Not this year's map or picture work | zero now. Later, if scripts are in scope | GPL. Last code push is years old |
| [FEAT](https://github.com/SciresM/FEAT) | SciresM | GPL-2.0 | 2021-06-22 | extracts 3DS Fire Emblem archives, including text | facts only. Our text tool already round-trips | none | GPL, and it is an extractor, not a writer we lack |
| [SPICA](https://github.com/gdkchan/SPICA) | gdkchan | GPL, as already cited in `docs/tracks/formats/BCH.md` | not re-fetched | H3D / BCH picture layout | facts only. Already cited for the picture note | none. The picture writer exists | the lod-register disagreement is already in that note. Do not copy the decoder |
| [fefates-tools](https://github.com/RainThunder/fefates-tools) | RainThunder | no licence on the repository record | 2017-02-03 | Nightmare modules, and a wiki page for the ordinary `.bin` | the wiki page is a fact, already cited. Do not copy the scripts | none | no licence means do not copy. Treat as all-rights-reserved |
| [fe-awakening-recomp](https://github.com/Zelkin1/fe-awakening-recomp) | Zelkin1 | MIT | 2026-11-11 | Awakening extras on Zakuro: wider screen, overlay, battle panels | the pattern only: off by default, title-gated, no addresses copied. Already written up in `docs/tracks/EXTRAS_FATES.md` | none until Fates markers are named | copying Awakening addresses into Fates would draw garbage or steal a button |
| [FEFTwiddler](https://github.com/Soaprman/FEFTwiddler) | Soaprman | GPL-3.0 | 2018-05-14 | a save editor | facts only, and only if the death-rule flag is still unnamed after a reading of our own save code | none now | GPL. A save editor is not the port |
| [FEFEditor](https://github.com/thane98/FEFEditor) | thane98 | GPL-3.0 | 2017-08-09, and the repository is archived | the editor Paragon replaced | skip | none | archived. Paragon is the later tool |
| Foxes, 60-frame patches | Foxes, GBAtemp | not a code licence we can adopt. A forum post | 2026, thread cited in `docs/tracks/EXTRAS_FATES.md` | claims a 60-frame patch that does not double the speed | a list of places to look, after a reading. Do not paste the code | none. Pasting it would risk the wrong-speed bug | region-specific. Some console users crashed on a 3D battle. The older public code doubles speed |
| Citra, Azahar, Lime3DS | various | not fetched as a dependency | — | emulators, cheat loaders, texture packs | skip as a player. A texture pack is someone else's pictures, not our portrait tool | none | switching players throws away the recomp and the mod folder we already install into |

A search for `fire emblem fates editor` also returned an empty `saratime/FEFTwiddler` with no licence and no code (pushed 2026-07-22, size 0). Skip it. The real save editor is Soaprman's.

## Ranked

**Adopt.** Nothing from this scan. No repository here is both licence-compatible and ahead of a tool we already have. Zakuro and the Awakening extras pattern are already in use. They are not new adoptions.

**Read for facts.**

1. Paragon's FE14 type files, when a layout is stuck. GPL. Paraphrase. Do not copy.
2. RainThunder's `.bin` wiki page. Already cited.
3. Exalt's script notes, only if a chapter script is in scope later.
4. Foxes's thread, only as a list of frame-timing places, after a reading. No bytes in git.
5. Zelkin1's extras, as a shape for switches that stay off. No addresses.

**Skip.**

- FEFEditor (archived), the empty Twiddler fork, the convoy editor, Nightmare modules as code.
- Pasting any cheat or 60-frame code.
- Replacing Zakuro with Citra, Azahar, or Lime3DS.
- Waiting for a Fates decompilation. The search found none.

## What this changes in the plan

Nothing on the critical path. The December checks, the one Birthright robot, and the rewrite order stay.

Two small rules, with the evidence above:

- When a castle or script layout is stuck, read Paragon or Exalt before inventing the layout. That is days on that file, not a reason to stop the picture tool or the robot. GPL stays facts.
- Do not add a "community decomp" step. There isn't one. Keep the host comparison we already run on rewritten functions.

## Credits

Nothing in this scan is linked as code, so `CREDITS.md` does not get a new line from it. If a later patch links Zelkin1's MIT extras, or any other allowed dependency, Claude adds the credit when that code is actually used. A citation in a note is not that.
