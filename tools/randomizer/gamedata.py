"""Loads the tables slice 1 needs from the user's own extracted RomFS, through the existing table tools
(tools/tables via tools/mods/mods.py: the same codecs and cells as tools/tables/dump.py). Read only.
Game values never leave the user's own folders (the mod folder and spoiler log are written under build/ or a
play profile, both outside git)."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
sys.path.insert(0, HERE)
import mods as M  # noqa: E402
import randolib as R  # noqa: E402


def _load(name: str, only_first: bool = False) -> list[dict]:
    reg = M.reg()
    t = reg[name]
    cd = M.codec(name)
    head = cd.columns()
    rows = []
    files = t.files()[:1] if only_first else t.files()
    for rel in files:
        c = M.T.container(rel)
        start, count = M.T.locate(t, c)
        labels = M.T.record_labels(t, c, start, count)
        rows += [dict(zip(head, cd.decode(c, i, start + i * t.size, labels[i]))) for i in range(count)]
    return rows


def available() -> str | None:
    """None when the user's RomFS and the table layouts are there, else why not."""
    return M.tables_status()


def load_facts(rules: dict | None = None, names: bool = True) -> R.Facts:
    why = available()
    if why:
        raise R.RandoError(f"the game's tables are not available: {why}")
    nm = {}
    if names:
        try:
            van = M.TX.archive(M.NAME_ARCHIVE, M.ROMFS)
            for lab, _v, a in van.entries:
                if not a:
                    nm[lab.decode("cp932", "replace")] = van.text_of[lab]
        except Exception:  # noqa: BLE001  (names only make the spoiler log nicer)
            nm = {}
    return R.Facts(_load("Person", only_first=True), _load("Job"), _load("Item"), _load("ItemSubKind"),
                   _load("DisposUnit"), rules or R.load_rules(), nm, handover=load_handover())


# the route-variant Person rows (PersonChapter layout; slice 1's route-variant join fix, RECRUIT_WIRE section 4)
HANDOVER_RX = ("GameData/Person/A_HANDOVER.bin.lz", "GameData/Person/B_HANDOVER.bin.lz",
               "GameData/Person/C_HANDOVER.bin.lz")


def load_handover(rels=HANDOVER_RX) -> list[dict]:
    """The HANDOVER rows with their "file" (a story without route variants has none: [])."""
    t = M.reg()["PersonChapter"]
    cd = M.codec("PersonChapter")
    head = cd.columns()
    rows = []
    for rel in rels:
        if rel not in t.files():
            continue
        c = M.T.container(rel)
        start, count = M.T.locate(t, c)
        labels = M.T.record_labels(t, c, start, count)
        rows += [dict(zip(head, cd.decode(c, i, start + i * t.size, labels[i]))) for i in range(count)]
    return rows
