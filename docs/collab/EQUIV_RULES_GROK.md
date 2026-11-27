# A rule for the judgement pile

**For the owner.** These are planted changes the checker still misses. A class is a label, not a pardon. F-026 says a script never marks one on its own. This note is the written rule you can approve, one class at a time. After you approve one class, a script may mark only that class. It may not mark the rest.

Status 2026-11-18. Read: `docs/harness/H6_THREE.md` (the 237, by class), `docs/DECISIONS.md` F-026, and the later status lines that say 237 plus 70 unsorted. The 70 are not split in those lines. An older note splits 36 of them, and says some can change an answer. The other 34 are not classed here. No count below is a promise.

## Approve in this order

1. **Gives up, and nothing else.** 15 of the 237. The note says the readable code only gives up more, or later, and never stores a wrong answer. A script may mark this class. It clears about 15 [low]. None of the classed 36 are this kind.

2. **A give-up that returns a number nobody uses.** 17 of the 237. The note says the original code answers instead, so the planted return is thrown away. A script may mark this class. About 17 [low]. None of the classed 36 are this kind.

3. **Compared with a value that cannot occur.** 7 of the 237. A pointer of 1, or a number too big for the field. A script may mark this class. About 7 [low].

Those three are the only ones a script can mark with no extra look. Together that is about 39 of the 237 [low]. The 70 are not in that 39.

4. **Plus and minus on a field at offset 0.** 29 of the 237, and 12 of the classed 36. Same address only if that offset is still 0. A script may mark one after it reads the constant and the constant is 0. If the constant is not 0, it stays for a person. Up to 29, plus up to 12, if every constant is 0 [low].

5. **An extra word on a call that takes no words.** 12 of the 237, and 4 of the classed 36. The note names `Map::Get` with no arguments. A script may mark one only when the call is that one. About 12, plus about 4 [low].

Stop there. Do not approve a sixth class in the same yes.

## Stays for a person

- **A compare moved by one.** 80 of the 237, and 5 of the classed 36. Both sides match only at that exact boundary. A script does not know the boundary. A host case that already hits it may be shown to you. It does not clear the class.
- **Two arguments swapped.** 17 of the 237, and 5 of the classed 36. One of the 36 swaps a support and a rank, and that can change an answer. No swap is marked by a script.
- **A constant made one bigger, a clamp widened, a start value changed, an early return used.** 26, 12, 8, 7, and 6 of the 237. Each needs the callee read. Not a script.
- **The one leftover, and the 4 leftovers in the 36.** A person. One is a child-unit line no recording reaches.
- **The 70, until classed.** Sorting them into the classes above is allowed. Marking them is not, until you have approved that class. The 34 that are not in the older split of 36 are not guessed here.

## What a script must not do

It must not mark all 237 at once. It must not mark a case the approved class does not name. It must not mark a case the note already says can change an answer. It must not add the cleared count into the headline percent. A cleared case leaves the judgement pile. It does not turn a writer on.
