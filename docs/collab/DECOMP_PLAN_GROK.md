# A full decomp, for this port

**For the owner.** The PC game already runs. A decomp is a different job: writing the game's own functions as readable C. Byte-for-byte matching needs the compiler Nintendo's team used, and we do not have a public page that names that build. The useful job is the one we already started: C that behaves the same, checked by the robot, for the functions the game actually calls. Doing that for every named function is years, not a season.

Status 2026-11-19. Read: `docs/CODE.md`, `docs/READABLE.md`, `docs/SYMBOLS.md`. Public tools only. No game file opened. No code copied.

## What the words mean

1. **Byte-matching.** C that, compiled again, is the same bytes as the cartridge. Public 3DS work that does this uses ARM's own compiler, RVCT 4.0. Ocarina of Time 3D names build 821 and checks the code file. Our notes show Fates used that compiler family. They do not name the build. Without that compiler, and the flags, byte-matching is not a plan. A different compiler can be right and still not match.
2. **Behaviour-matching.** C that returns the same answers and stores the same bytes, proved by tests. This is the 266 we have. It does not need RVCT. It is what a modder can read.
3. **Readable C for what the PC port runs.** Smaller than 2. The recomp already runs the rest. This is the port. It is not a decomp.

Sources: [OoT 3D decomp](https://github.com/zeldaret/oot3d) (RVCT 4.0 build 821, code file checked), [m2c](https://github.com/matt-kempster/m2c) (ARM to C, GPL, not copied), [objdiff](https://github.com/encounter/objdiff) (ARM including 3DS, compares compiler output), [splat](https://github.com/ethteck/splat) (N64, PlayStation, PSP; not 3DS).

## What to copy from other projects

What worked is a splitter, a diff, and a matching compiler, with several people over years. splat does not split a 3DS code file. objdiff helps only if we are matching compiler output. m2c can draft ARM into C, and its readme does not list our compiler. A draft is not a proof. decomp.dev's own note says a port and a decomp are different jobs, and that a matching decomp of a game this size is measured in years. We already have the better check for our choice: the host test, the planted bugs, and the robot.

## The plan for us

Do not chase bytes. One person, helpers, and the robot. The symbol map has 27,074 names. The game-function list is 16,312. The C library and the system libraries stay as the recomp. They are not the job.

1. **Decide.** Functional C. Game functions only. A function the robot has never called waits.
2. **Take the next function from a recording, not from the top of the list.** The 266 are done. The next ones are callers those recordings already reach. No new chapter to light one up.
3. **Draft, then prove.** A lifter may write the first draft in a scratch folder. It does not enter the tree until the host test catches every planted bug that can change a stored byte, and a live compare on a route that already reaches it is clean. A draft that fails is thrown out.
4. **Batch by the file the notes already group.** Data, unit, battle, map, AI, events, save, then castle. One file at a time. A C++ class that falls into the next function, as the class lookup did, is not a batch until someone has read it.
5. **Writers stay gated.** Most of the remaining game stores. A reader-only march will stop. A writer still needs the three numbers, a written rule for the "cannot change an answer" cases, and your yes. The options writer is the one already in that queue. Do not open a second writer to go faster.
6. **The 0-bad bar stays.** A faster lift that changes a save is a failed function, not progress.

## How long

Recent rounds proved a handful of functions, with the full check. At 2 to 5 proven functions a day, the 16,312 is several years. At 10 a day, with helpers and no new chapters, it is still a few years [low]. Functions the robot never calls are most of that list. Finishing "what the recordings reach" is the honest first finish, and that count is not in the notes. Do not invent it.

The risks, in order: guessing the compiler and spending a year on bytes; Thumb functions, which our readable layer does not override; a class that falls into the next function; a writer turned on to clear a batch; a lifted draft that passes one test and changes a save on the next route.

## What you decide

1. Functional C, not byte-matching?
2. Game functions only, and the libraries stay in the recomp?
3. Only functions a recording already reaches, until that list is done?
4. Writers stay behind the existing gate, one yes each?
5. A draft that fails the host test is thrown out, not patched into the game you play?
