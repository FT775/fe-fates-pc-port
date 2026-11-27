#!/usr/bin/env python3
"""Text mods (pipeline T1, docs/MODDING.md section 5): edit the game's message archives
as text files inside a mod; mods.py builds and installs them.

Standard library only. Used by tools/mods/mods.py; can also be run on its own:

    python tools/mods/textmod.py roundtrip [--romfs DIR] [--jobs N]
        every message archive anywhere in extracted/romfs/: dump to the mod text form,
        read it back as a mod file, merge, re-encode and LZ-compress the original way;
        prints "text round trip: N/N archives byte-identical" (stored, compressed bytes)
        and how many archives were found outside the message folders (expected: 0)
    python tools/mods/textmod.py dump ARCHIVE OUT.txt [--romfs DIR]
        write the mod text form of one archive (ARCHIVE = RomFS path, m/@E/GameData.bin.lz)
    python tools/mods/textmod.py archives [--romfs DIR]
        count the message archives by place (shared English, per route, common)

Where the archives are (Fates; folders from config/game.json "romfs", checked against the
extracted RomFS 2026-11-10):
    m/@E/*.bin.lz            English text shared by every route (1,239 files; GameData.bin.lz
                             = unit, class, item and skill names and descriptions)
    m/A|B|C/@E/*.bin.lz      route-only English text (A = Birthright, B = Conquest,
                             C = Revelation, config "route_folders"; 22 files each)
    m/common/*.bin.lz        text with no language folder (23 files)
1,328 in all, none anywhere else. All are LZ13 (Awakening's were LZ11); compress_like
keeps each file's own format.

Mod layout: mods/<Name>/text/<RomFS path>.txt, for example
    mods/MyMod/text/m/@E/GameData.bin.lz.txt
The file uses the format of tools/assets/msg.py (docs/ASSETS.md 3.3):
    #msgarchive 1                    first line, kept as dumped
    #name "MESS_ARCHIVE_..."         second line, kept as dumped (must match the game)
    [LABEL]                          a message label that exists in that archive
    text on ONE line                 escapes: \\n line break, \\r, \\\\, \\uXXXX
    [LABEL2] = LABEL                 alias line: LABEL2 shows LABEL's text (kept as dumped)
Only the labels whose text differs from the game count, so a mod file may hold the
whole dump or just the labels it changes. Blank lines and '#' comment lines between
entries are ignored; Windows line ends and a UTF-8 byte-order mark are accepted.

Build: the changed labels are merged into a copy of the original archive, in the
original label order; the archive is re-encoded by msg.py and LZ-compressed with
lz.compress_like (the same keep-the-original-LZ path tools/tables uses), then read back
and compared with what was asked for. Unchanged text gives back the original bytes.

Refused (errors): new labels (allowed only for a row the same mod adds, and adding rows
is not supported yet), a changed '#name', a changed or new alias line, a missing header,
text that is not on the line after its label, bad escapes, duplicate labels, a path that
is not a message archive. Warned: a change in the number of '$' characters (the
conversation control codes start with '$' [med]), characters the archive never uses
(they may be missing from the game's font), an empty message.

Nothing here holds game text: the archives are read from the user's extracted/romfs/.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import lz  # noqa: E402
import msg  # noqa: E402
from gamecfg import GAME  # noqa: E402

ROMFS = os.path.join(ROOT, "extracted", "romfs")
_RCFG = GAME.raw.get("romfs", {})
MESSAGE_DIRS: list[str] = list(_RCFG.get("message_dirs") or ["m"])      # RomFS folders with text
LANG_DIR: str = _RCFG.get("message_lang_dir", "@E")                     # English sub-folder
ROUTES: dict[str, str] = dict(_RCFG.get("route_folders") or {})         # A -> Birthright ...
COMMON_DIR: str = _RCFG.get("message_common_dir", "common")
# the archive with unit/class/item names (the Person table's name labels point into it)
NAME_ARCHIVE: str = _RCFG.get("name_archive", f"{MESSAGE_DIRS[0]}/{LANG_DIR}/GameData.bin.lz")
TEXT_DIR = "text"            # folder inside a mod
SUFFIX = ".txt"
HEADER = "#msgarchive 1"
CONTROL = "$"                # conversation control codes start with this [med]


class TextError(ValueError):
    pass


# ------------------------------------------------------------------ the original archive
class Archive:
    """One message archive from the RomFS: stored bytes, decoded entries, lookups."""

    def __init__(self, rel: str, raw: bytes):
        self.rel = rel
        self.raw = raw
        self.is_lz = lz.lz_type(raw) is not None and (rel.lower().endswith(".lz") or raw[:1] == b"\x13")
        try:
            self.dec = lz.decompress(raw) if self.is_lz else raw
        except lz.LZError as e:
            raise TextError(f"{rel}: cannot be decompressed ({e})") from None
        if not msg.is_msg(self.dec):
            raise TextError(f"{rel} is not a message archive (only message archives, the files "
                            "under m/, can have a text file)")
        self.name, self.entries, b = msg.parse(self.dec)
        # file offset of each label's message (the IS .bin data region starts at 0x20)
        self.offset = {lab: 0x20 + off for off, lab, _no in b.labels}
        self.index = {lab: i for i, (lab, _v, _a) in enumerate(self.entries)}
        self.alias_of = {lab: (v if a else None) for lab, v, a in self.entries}
        own = {lab: v for lab, v, a in self.entries if not a}
        self.text_of = {lab: (own[v] if a else v) for lab, v, a in self.entries}
        self.sharers: dict[bytes, list[bytes]] = {}
        for lab, v, a in self.entries:
            if a:
                self.sharers.setdefault(v, []).append(lab)
        self.chars = set()
        for t in own.values():
            self.chars.update(t)

    def dump(self) -> str:
        return msg.to_text(self.name, self.entries)


_CACHE: dict[tuple[str, str], Archive] = {}


def romfs_file(romfs: str, rel: str) -> str:
    return os.path.join(romfs, *rel.split("/"))


def archive(rel: str, romfs: str = ROMFS) -> Archive:
    key = (os.path.abspath(romfs), rel)
    if key not in _CACHE:
        path = romfs_file(romfs, rel)
        if not os.path.isfile(path):
            raise TextError(f"no RomFS file {rel} in {romfs} (a text file is named after the archive's "
                            f"path under extracted/romfs/ plus {SUFFIX}, for example "
                            f"{TEXT_DIR}/{NAME_ARCHIVE}{SUFFIX})")
        with open(path, "rb") as fh:
            _CACHE[key] = Archive(rel, fh.read())
    return _CACHE[key]


def clear_cache() -> None:
    _CACHE.clear()


def message_archives(romfs: str = ROMFS, everywhere: bool = False) -> list[str]:
    """RomFS paths (with '/') of every message archive, sorted. Looks in the message
    folders (config "message_dirs") unless everywhere=True (the whole RomFS)."""
    out = []
    tops = [romfs] if everywhere else [os.path.join(romfs, d) for d in MESSAGE_DIRS]
    for dp, _dn, fn in (w for t in tops for w in os.walk(t)):
        for f in fn:
            if not (f.endswith(".bin.lz") or f.endswith(".bin")):
                continue
            p = os.path.join(dp, f)
            try:
                d = msg.load(p)
            except (lz.LZError, OSError):
                continue
            if msg.is_msg(d):
                out.append(os.path.relpath(p, romfs).replace(os.sep, "/"))
    out.sort()
    return out


def archive_place(rel: str) -> str:
    """Plain-words place of a message archive: 'English (all routes)', 'English,
    Birthright route only (A)', 'common (no language folder)' or 'other'."""
    parts = rel.split("/")
    if len(parts) < 2 or parts[0] not in MESSAGE_DIRS:
        return "other"
    if parts[1] == LANG_DIR:
        return "English (all routes)"
    if parts[1] in ROUTES and len(parts) > 2 and parts[2] == LANG_DIR:
        return f"English, {ROUTES[parts[1]]} route only ({parts[1]})"
    if parts[1] == COMMON_DIR:
        return "common (no language folder)"
    return "other"


# ------------------------------------------------------------------ mod text files
def mod_text_files(mod_dir: str) -> list[tuple[str, str]]:
    """[(RomFS path, file path)] for every *.txt under <mod>/text/, sorted."""
    top = os.path.join(mod_dir, TEXT_DIR)
    out = []
    if not os.path.isdir(top):
        return out
    for dp, _dn, fn in os.walk(top):
        for f in fn:
            if f.lower().endswith(SUFFIX):
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, top).replace(os.sep, "/")[:-len(SUFFIX)]
                out.append((rel, p))
    out.sort()
    return out


class Item:
    __slots__ = ("label", "alias", "value", "line")

    def __init__(self, label: bytes, alias: bool, value, line: int):
        self.label, self.alias, self.value, self.line = label, alias, value, line


def _label_bytes(s: str, where: str, errors: list[str]) -> bytes | None:
    s = s.strip()
    if not s:
        errors.append(f"{where}: empty label")
        return None
    try:
        return s.encode("cp932")
    except UnicodeError:
        errors.append(f"{where}: label {s!r} cannot be written in Shift-JIS (copy labels from the dump)")
        return None


_HEX = set("0123456789abcdefABCDEF")


def strict_unescape(s: str) -> str:
    """msg.unescape, but a \\u must have exactly four hex digits (msg.py would accept a
    short one at the end of a line and read a wrong character)."""
    i = 0
    while i < len(s):
        if s[i] == "\\":
            if s[i + 1:i + 2] == "u":
                h = s[i + 2:i + 6]
                if len(h) != 4 or not set(h) <= _HEX:
                    raise msg.MsgError(f"bad escape at {i}: {s[i:i + 6]!r}")
                i += 6
                continue
            i += 2
            continue
        i += 1
    return msg.unescape(s)


def parse_mod_text(data: bytes, where: str):
    """Read one mod text file. Returns (archive name bytes or None, [Item], errors)."""
    errors: list[str] = []
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        return None, [], [f"{where}: not UTF-8 text (byte {e.start}); save the file as UTF-8"]
    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in text.split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != HEADER:
        errors.append(f"{where} line {i + 1}: the first line must be '{HEADER}' "
                      "(keep the two header lines the dump starts with)")
        return None, [], errors
    i += 1
    if i >= len(lines) or not lines[i].startswith("#name "):
        errors.append(f"{where} line {i + 1}: the second line must be the '#name \"...\"' line from the dump")
        return None, [], errors
    try:
        name = msg.isbin.unquote(lines[i][6:])
    except (msg.isbin.BinError, ValueError) as e:
        errors.append(f"{where} line {i + 1}: bad #name line ({e})")
        return None, [], errors
    i += 1
    items: list[Item] = []
    while i < len(lines):
        ln = lines[i]
        at = f"{where} line {i + 1}"
        if not ln.strip() or ln.lstrip().startswith("#"):
            i += 1
            continue
        if not ln.startswith("["):
            errors.append(f"{at}: expected [LABEL], a blank line or a # comment; a message's text "
                          "must stay on the ONE line after its label (write a line break as \\n)")
            i += 1
            continue
        close = ln.find("]")
        if close < 0:
            errors.append(f"{at}: label line without ']'")
            i += 1
            continue
        lab = _label_bytes(ln[1:close], at, errors)
        rest = ln[close + 1:].strip()
        if rest.startswith("="):
            tgt = _label_bytes(rest[1:], at, errors)
            if lab is not None and tgt is not None:
                items.append(Item(lab, True, tgt, i + 1))
            i += 1
            continue
        if rest:
            errors.append(f"{at}: text after the label; put the text on the next line")
            i += 1
            continue
        if i + 1 >= len(lines):
            errors.append(f"{at}: label without a text line after it")
            i += 1
            continue
        try:
            val = strict_unescape(lines[i + 1])
        except (msg.MsgError, ValueError) as e:
            errors.append(f"{where} line {i + 2}: {e} (escapes are \\n, \\r, \\\\ and \\uXXXX "
                          "with four hex digits)")
            val = None
        if lab is not None and val is not None:
            items.append(Item(lab, False, val, i + 1))
        i += 2
    return name, items, errors


def _show(lab: bytes) -> str:
    return lab.decode("cp932", "backslashreplace")


def diff_text(van: Archive, name: bytes | None, items: list[Item], where: str,
              new_ok: frozenset | set = frozenset()):
    """Compare one parsed mod file with the original archive. A label the archive does
    not have is accepted only when it is in new_ok (the text IDs that rows the same mod
    adds use, e.g. the MIID_ name of a new item); it becomes a new message at the end.
    Returns ({label: new text}, errors, warnings, notes)."""
    changes: dict[bytes, str] = {}
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    if name is not None and name != van.name:
        errors.append(f"{where}: #name is {msg.isbin.quote(name)} but the game's archive is named "
                      f"{msg.isbin.quote(van.name)}; keep the #name line as dumped")
    seen: dict[bytes, int] = {}
    for it in items:
        at = f"{where} line {it.line}"
        if it.label in seen:
            errors.append(f"{at}: [{_show(it.label)}] appears twice (first on line {seen[it.label]})")
            continue
        seen[it.label] = it.line
        if it.label not in van.index:
            if it.label not in new_ok:
                errors.append(f"{at}: [{_show(it.label)}] is not a label of {van.rel}; new labels are "
                              "refused unless a row this mod adds uses them (for example the MIID_ name "
                              "of a new item, in " + NAME_ARCHIVE + "). Copy existing labels from the dump (mods.py text NAME ARCHIVE)")
            elif it.alias:
                errors.append(f"{at}: [{_show(it.label)}] is a new label; give it a text line, not '='")
            else:
                changes[it.label] = it.value
                odd = sorted({c for c in it.value if c not in van.chars and not (" " <= c <= "~")})
                if odd:
                    warnings.append(f"{at}: [{_show(it.label)}] uses character(s) {''.join(odd)!r} that "
                                    f"{van.rel} never uses; they may be missing from the game's font")
                if it.value == "":
                    warnings.append(f"{at}: [{_show(it.label)}] is empty")
                notes.append(f"{at}: [{_show(it.label)}] is a new message (for a row this mod adds)")
            continue
        old_alias = van.alias_of[it.label]
        if it.alias:
            if old_alias is None:
                errors.append(f"{at}: [{_show(it.label)}] is its own message in the game, not an alias; "
                              "give it a text line instead of '='")
            elif it.value != old_alias:
                errors.append(f"{at}: [{_show(it.label)}] = {_show(it.value)}: the game has "
                              f"[{_show(it.label)}] = {_show(old_alias)}; alias lines must stay as dumped "
                              "(to give it its own text, write the label and a text line)")
            continue
        old = van.text_of[it.label]
        new = it.value
        if new == old:
            continue
        changes[it.label] = new
        lab = _show(it.label)
        if old_alias is not None:
            notes.append(f"{at}: [{lab}] shared [{_show(old_alias)}]'s text; it gets its own message")
        for s in van.sharers.get(it.label, []):
            if s not in seen:
                notes.append(f"{at}: [{_show(s)}] = [{lab}] in the game, so it changes too")
        if new.count(CONTROL) != old.count(CONTROL):
            warnings.append(f"{at}: [{lab}] has {new.count(CONTROL)} '{CONTROL}' where the game has "
                            f"{old.count(CONTROL)}; '{CONTROL}' starts a conversation control code and a "
                            "broken one may crash a conversation")
        odd = sorted({c for c in new if c not in van.chars and not (" " <= c <= "~")})
        if odd:
            warnings.append(f"{at}: [{lab}] uses character(s) {''.join(odd)!r} that {van.rel} never "
                            "uses; they may be missing from the game's font")
        if new == "":
            warnings.append(f"{at}: [{lab}] is now empty")
    return changes, errors, warnings, notes


def merged_entries(van: Archive, changes: dict[bytes, str]):
    """The original entries in the original order, with the changed labels' text; labels
    the archive does not have (new messages for added rows) follow at the end, sorted."""
    out = [(lab, changes[lab], False) if lab in changes else (lab, v, a) for lab, v, a in van.entries]
    out += [(lab, changes[lab], False) for lab in sorted(changes) if lab not in van.index]
    return out


def expected_text(van: Archive, changes: dict[bytes, str], lab: bytes) -> str:
    """What a label shows after the edit: its own new text, else (an alias that was not
    given its own text) its target's new text, else the original."""
    if lab in changes:
        return changes[lab]
    tgt = van.alias_of.get(lab)
    if tgt is not None and tgt in changes:
        return changes[tgt]
    return van.text_of[lab]


def build_archive(van: Archive, changes: dict[bytes, str]) -> bytes:
    """Re-encode and compress like the original; then read the result back and check it
    holds exactly the requested text for every label (raises TextError otherwise)."""
    entries = merged_entries(van, changes)
    dec = msg.build_bytes(van.name, entries)
    out = lz.compress_like(dec, van.raw) if van.is_lz else dec
    if van.is_lz and (lz.lz_type(out) != lz.lz_type(van.raw)):
        raise TextError(f"{van.rel}: rebuilt file is not in the original LZ format")
    back = lz.decompress(out) if van.is_lz else out
    if back != dec:
        raise TextError(f"{van.rel}: the compressed file does not decompress to the built archive")
    name, got, _b = msg.parse(back)
    want = {lab: expected_text(van, changes, lab) for lab in van.index}
    want.update({lab: v for lab, v in changes.items() if lab not in van.index})
    own = {lab: v for lab, v, a in got if not a}
    have = {lab: (own[v] if a else v) for lab, v, a in got}
    if name != van.name or [e[0] for e in got] != [e[0] for e in entries] or have != want:
        bad = [_show(lab) for lab in want if have.get(lab) != want[lab]]
        raise TextError(f"{van.rel}: the rebuilt archive does not read back as the edit ({bad[:5]})")
    return out


# ------------------------------------------------------------------ round trip
def roundtrip_one(args) -> tuple[str, bool, str]:
    """Dump -> mod text -> parse -> merge -> build; must give back the stored bytes."""
    rel, romfs = args
    try:
        with open(romfs_file(romfs, rel), "rb") as fh:
            van = Archive(rel, fh.read())
        name, items, errors = parse_mod_text(van.dump().encode("utf-8"), rel)
        if errors:
            return rel, False, errors[0]
        changes, errors, _w, _n = diff_text(van, name, items, rel)
        if errors or changes:
            return rel, False, (errors or [f"{len(changes)} label(s) read back changed"])[0]
        out = build_archive(van, {})
        return rel, out == van.raw, "" if out == van.raw else "rebuilt bytes differ"
    except (TextError, msg.MsgError, lz.LZError, ValueError, OSError) as e:
        return rel, False, str(e)


def roundtrip_all(romfs: str = ROMFS, jobs: int | None = None,
                  everywhere: bool = True) -> tuple[int, int, list[str]]:
    from concurrent.futures import ProcessPoolExecutor
    rels = message_archives(romfs, everywhere=everywhere)
    fails = []
    ok = 0
    jobs = jobs or max(1, (os.cpu_count() or 2) - 1)
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for rel, good, info in ex.map(roundtrip_one, [(r, romfs) for r in rels], chunksize=8):
            ok += good
            if not good:
                fails.append(f"{rel}: {info}")
    return ok, len(rels), fails


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("roundtrip", "dump", "archives"))
    ap.add_argument("archive", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--romfs", default=ROMFS)
    ap.add_argument("--jobs", type=int)
    a = ap.parse_args(argv)
    if a.cmd == "dump":
        if not (a.archive and a.out):
            ap.error("dump needs ARCHIVE and OUT")
        try:
            text = archive(a.archive.replace("\\", "/"), a.romfs).dump()
        except TextError as e:
            print(f"ERROR: {e}")
            return 1
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return 0
    if not os.path.isdir(a.romfs):
        print(f"ERROR: no {a.romfs} (python tools/assets/romfs.py; it reads the .cci in roms/)")
        return 1
    if a.cmd == "archives":
        places: dict[str, list[str]] = {}
        for rel in message_archives(a.romfs):
            places.setdefault(archive_place(rel), []).append(rel)
        for place, rels in sorted(places.items()):
            folders = sorted({r.rsplit("/", 1)[0] for r in rels})
            print(f"{len(rels):5}  {place}: {', '.join(f + '/' for f in folders)}")
        print(f"{sum(map(len, places.values()))} message archives; names of units, classes and "
              f"items are in {NAME_ARCHIVE}")
        return 0
    ok, n, fails = roundtrip_all(a.romfs, a.jobs)
    for f in fails[:20]:
        print("FAIL", f)
    print(f"text round trip: {ok}/{n} archives byte-identical")
    found = message_archives(a.romfs, everywhere=True)
    outside = [r for r in found if archive_place(r) == "other"]
    print(f"message archives outside the message folders ({', '.join(MESSAGE_DIRS)}/{LANG_DIR}, "
          f"routes, {COMMON_DIR}): {len(outside)}" + (f" ({', '.join(outside[:5])})" if outside else ""))
    return 0 if ok == n and n else 1


if __name__ == "__main__":
    sys.exit(main())
