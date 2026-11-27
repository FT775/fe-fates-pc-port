# Portrait colour

**For the owner.** Do not recolour the portraits. The first try bleached faces. Battle hair is faint, and that is still the safe signal. When the full swap arrives, the new person brings their own picture. A second paint job on the old picture is wasted, and it can ruin a face.

Status 2026-11-20. Read: `docs/collab/COLOUR_RULE_GROK.md`, the round 59 colour note as you described it. Public tools only. No picture was edited here.

## Is it worth it?

Not for the keep-the-face look. That look is supposed to keep the old face. Painting new hair onto it fights the look, and the later full swap replaces the picture anyway.

What other games do is not the same job. The GBA editors shuffle a small colour table, because those portraits are stored that way. [FEBuilder](https://github.com/laqieer/FEBuilderGBA) is that kind of tool, and it is GPL. Do not copy it. It does not open Fates.

Fates named adults have the hair baked into the picture. Only Corrin and the children have a hair layer the game tints. [Paragon](https://github.com/thane98/paragon) edits tables. [FEAT](https://github.com/RainThunder/FEAT) unpacks archives. Neither is an automatic hair paint, and both are GPL. Fan portrait changes that I could confirm are a whole new picture, drawn by a person, not a hue shift. Ignis either keeps the model or swaps the person. It does not advertise a safe automatic portrait recolour.

A player will notice a swap in the fight if the hair number changed, and on the status page if the face is actually the new person. They will not reliably notice a faint hair tint under a hit flash. Setsuna already showed that.

## If it is tried later

The only reliable method is a hair mask, drawn once per person, checked by eye, then a hue shift inside that mask. Near-black lines and skin stay put. A dark-to-light swap also needs a lightness curve, or the lines bleach again. That is dozens of masks, not a round.

Borrowing the children's tint layer does not work for named adults. They do not have that layer.

A whole-picture shift is what already failed. Do not repeat it.

## Map sprites

Skip them. At map size the hair is a few pixels. The same shift can stain armour, as Silas showed. The battle model is the picture that matters.

## The question

May portrait and map recolour stay dropped, and the full swap later use each person's own pictures instead?
