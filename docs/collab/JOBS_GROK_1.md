# Jobs for Grok, batch 1 (2026-11-10) — owner approved: "Yes, send them"

Rules for all three: facts only from community/public sources (GPL code is never copied; note each
source URL); no ROM bytes, extracted files, table values or game text; write only in your folders;
ELI5 + ETA at the start and end of each step in the Hermes chat; answer in GROK_INBOX.md when done.

## Job 1 — Picture and media format specs (folder: docs/tracks/formats/)
Fates pictures/models are BCH (H3D), ~10.7k .bch.lz files (portraits, UI, units, battle models).
Write BCH.md: header, section tables, relocation tables, texture descriptors (format codes, sizes,
mip counts, data offsets), material/model refs only as far as texture swaps need. Mark each fact with
its source and confidence. Also short notes: .dspadpcm.bcstm, .aac voices, .moflex, Live2D .moc/.mtn
(what they are, whether tools exist, licence of each). Claude's bch.py (tools/assets/bch.py, being
written now) will be checked against your spec, and you may review it after.

## Job 2 — Fates rules cheat sheet (folder: docs/tracks/rules/)
RULES.md from public wikis/guides (facts, short, in your own words): Attack/Guard stance (who
triggers, damage share, guard gauge), weapon triangle and per-weapon-type bonuses, dragon veins per
route (effects), skill activation formulas, growth rate rules (personal + class + parent inheritance
for children), hit/avoid/crit formulas, Casual/Phoenix rules, Birthright vs Conquest exp/gold economy.
Each line: rule, source, confidence. Purpose: cross-checking our table and code findings.

## Job 3 — Options page on Zakuro's Esc menu (folder: tools/zakuro-options/)
Zakuro is MIT Rust; pin and URL in config/upstream.json. Clone it into tools/zakuro-options/work/
(gitignored) at that pin. Design and write an "FE options" page as a patch series
(tools/zakuro-options/patches/*.patch) + DESIGN.md: reads/writes our own options file
(name in config/game.json: port.options_file, found via an env var set by PLAY), never the save and
never Zakuro's settings.toml; display-only options never mark a save; run options are per save slot;
changing an option never rebuilds anything. Start with the display options from
docs/tracks/STANCE_AND_REVIVE.md and the Awakening OPTIONS_M5 shape, all default off, values typed.
The game-side hooks are blank for now: the page only stores values. Do NOT run cargo (build/test)
yet: Zakuro builds need the owner's OK, which Claude will ask for. Write unit tests ready to run.
