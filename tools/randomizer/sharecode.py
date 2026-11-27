"""The randomizer page's share code (round 74, A6; docs/rando/FULL_BLOCK.md section 7).

One short text that carries every setting of the New Game page and the seed, so a player can copy it and another
player (or the same one later) can paste it and get the same game. The Rust page (zakuro `rando_page.rs`,
`share_encode` / `share_decode`, patch 0036) is the twin of this file; both are tested against the same vectors
(tests/rando_sharecode_vectors.json).

    R1FKQ-B1-7M-demo-7
    <head>-<body>-<check>-<seed>       split on the first three "-" only (a seed may hold "-")

head   "R1" (code format 1) + the game ("F" Fire Emblem Fates, "S" Seal of Flames) + the layout (2 characters)
body   every share row's value index, bit-packed (below)
check  fnv1a32(head + "-" + body + "-" + seed) & 0x3FF in 2 characters, high 5 bits first
seed   the seed text, exactly as typed (seeds are case-sensitive)

Share rows: every schema row that is not page_only and not the seed, sorted by key (hidden, fixed and game-hidden
rows too). Layout: fnv1a32 of "<key>:onoff:2", "<key>:choice:<a,b,c>", "<key>:number:<min>,<max>" joined with ";"
in share-row order, & 0x3FF, 2 characters. A code of another layout comes from another version of the randomizer
and is refused. Value index: on/off false 0 / true 1; choice: its place in the choices; number: value - min. Width
in bits: bit length of (radix - 1). Body: each share row's index bits, lowest first, in one bit list, padded with 0
to a multiple of 5; each group of 5 is one character, the group's first bit as its value's 1 bit.

Alphabet: Crockford base 32 (0-9 and A-Z without I, L, O, U). Head, body and check are read case-blind.

Python 3 standard library only. No game data: only the page's own option keys.
"""
from __future__ import annotations

import re

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
TAG = "R1"
GAMES = {"fates": "F", "seal": "S"}
GAME_NAMES = {"fates": "Fire Emblem Fates", "seal": "Seal of Flames"}
SEED_RX = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193

# the one plain sentence for each way a code is refused (the Rust page shows the same words)
MESSAGES = {
    "format": "This is not a share code.",
    "check": "This code has a typo.",
    "layout": "This code was made by another version of the randomizer.",
    "damaged": "This code is damaged.",
}


def game_message(code_game: str) -> str:
    """the sentence for a code made for the other game"""
    return f"This code is for {GAME_NAMES[code_game]}."


class ShareCodeError(ValueError):
    """a code that is refused: .kind is one of format, check, layout, game, damaged; str() is the sentence."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def fnv1a32(text: str) -> int:
    h = FNV_OFFSET
    for b in text.encode("utf-8"):
        h = ((h ^ b) * FNV_PRIME) & 0xFFFFFFFF
    return h


def upper_ascii(text: str) -> str:
    """a-z upper-cased, every other character kept (the Rust twin's to_ascii_uppercase)"""
    return "".join(chr(ord(c) - 32) if "a" <= c <= "z" else c for c in text)


def ten_bits(value: int) -> str:
    """value & 0x3FF as 2 characters, the high 5 bits first"""
    v = value & 0x3FF
    return ALPHABET[v >> 5] + ALPHABET[v & 31]


def share_rows(rows: list[dict]) -> list[dict]:
    """the rows a code carries: not page-only, not the seed, sorted by key (byte order)"""
    out = [r for r in rows if not r.get("page_only") and r.get("kind") != "seed" and r.get("key") != "seed"]
    return sorted(out, key=lambda r: r["key"].encode("utf-8"))


def _item(row: dict) -> str:
    kind = row["kind"]
    if kind == "onoff":
        return f"{row['key']}:onoff:2"
    if kind == "choice":
        return f"{row['key']}:choice:{','.join(row['choices'])}"
    if kind == "number":
        return f"{row['key']}:number:{row['min']},{row['max']}"
    raise ValueError(f"{row['key']}: a share row of kind {kind!r}")


def layout_text(rows: list[dict]) -> str:
    return ";".join(_item(r) for r in share_rows(rows))


def layout(rows: list[dict]) -> str:
    return ten_bits(fnv1a32(layout_text(rows)))


def radix(row: dict) -> int:
    kind = row["kind"]
    if kind == "onoff":
        return 2
    if kind == "choice":
        return max(len(row["choices"]), 1)
    return max(row["max"] - row["min"] + 1, 1)


def width(row: dict) -> int:
    return (radix(row) - 1).bit_length()


def _fits(row: dict, value) -> bool:
    kind = row["kind"]
    if kind == "onoff":
        return isinstance(value, bool)
    if kind == "choice":
        return isinstance(value, str) and value in row["choices"]
    return isinstance(value, int) and not isinstance(value, bool) and row["min"] <= value <= row["max"]


def index_of(row: dict, value) -> int:
    """a value's index in its row; a value that does not fit counts as the row's default (the page never holds
    one; the Rust twin does the same), and a default that does not fit either as 0"""
    if not _fits(row, value):
        value = row.get("default")
        if not _fits(row, value):
            return 0
    kind = row["kind"]
    if kind == "onoff":
        return 1 if value else 0
    if kind == "choice":
        return row["choices"].index(value)
    return value - row["min"]


def value_at(row: dict, index: int):
    kind = row["kind"]
    if kind == "onoff":
        return bool(index)
    if kind == "choice":
        return row["choices"][index]
    return row["min"] + index


def body_length(rows: list[dict]) -> int:
    """characters in the body for these rows"""
    bits = sum(width(r) for r in share_rows(rows))
    return (bits + 4) // 5


def encode(rows: list[dict], values: dict, seed: str, game: str = "fates") -> str:
    """the code of these form values (a missing row counts as its default) and this seed (never empty: the page
    fills an empty seed box with its proposed seed first)."""
    if not isinstance(seed, str) or not SEED_RX.fullmatch(seed):
        raise ValueError(f"not a seed the randomizer takes: {seed!r}")
    bits: list[int] = []
    for r in share_rows(rows):
        i = index_of(r, values.get(r["key"], r.get("default")))
        bits += [(i >> b) & 1 for b in range(width(r))]
    bits += [0] * (-len(bits) % 5)
    body = "".join(ALPHABET[sum(bits[k + j] << j for j in range(5))] for k in range(0, len(bits), 5))
    head = TAG + GAMES[game] + layout(rows)
    return f"{head}-{body}-{ten_bits(fnv1a32(head + '-' + body + '-' + seed))}-{seed}"


def decode(rows: list[dict], code: str, game: str = "fates") -> tuple[dict, str]:
    """(every share row's value, the seed) of a code, or ShareCodeError with its one plain sentence. Refusals in
    this order: format, check, layout, game, damaged."""
    parts = (code or "").strip().split("-", 3)
    if len(parts) != 4:
        raise ShareCodeError("format", MESSAGES["format"])
    head, body, check, seed = upper_ascii(parts[0]), upper_ascii(parts[1]), upper_ascii(parts[2]), parts[3]
    letters = {v: k for k, v in GAMES.items()}
    if not head.isascii() or len(head) != 5 or not head.startswith(TAG) or head[2] not in letters:
        raise ShareCodeError("format", MESSAGES["format"])
    if len(check.encode("utf-8")) != 2 or check != ten_bits(fnv1a32(head + "-" + body + "-" + seed)):
        raise ShareCodeError("check", MESSAGES["check"])
    if head[3:5] != layout(rows):
        raise ShareCodeError("layout", MESSAGES["layout"])
    code_game = letters[head[2]]
    if code_game != game:
        raise ShareCodeError("game", game_message(code_game))
    srows = share_rows(rows)
    bad_body = len(body.encode("utf-8")) != body_length(rows) or any(c not in ALPHABET for c in body)
    if bad_body or not SEED_RX.fullmatch(seed):
        raise ShareCodeError("damaged", MESSAGES["damaged"])
    bits = [(ALPHABET.index(c) >> j) & 1 for c in body for j in range(5)]
    pos = 0
    values = {}
    for r in srows:
        w = width(r)
        i = sum(bits[pos + b] << b for b in range(w))
        pos += w
        if i >= radix(r):
            raise ShareCodeError("damaged", MESSAGES["damaged"])
        values[r["key"]] = value_at(r, i)
    if any(bits[pos:]):
        raise ShareCodeError("damaged", MESSAGES["damaged"])
    return values, seed


def page_values(rows: list[dict], code: str, game: str = "fates") -> dict:
    """the page's form values after this code is pasted (the Rust page: the form reset to its defaults, every row
    set through RandoForm::set, the seed box set): ingame.page_restore's rules, so fixed and game-hidden rows keep
    their default and page-only switches follow the rows they drive."""
    import ingame as IG
    values, seed = decode(rows, code, game)
    return IG.page_restore(rows, dict(values, seed=seed), None if game == "fates" else game)


def page_code(rows: list[dict], values: dict, proposed: str, game: str = "fates") -> str:
    """the code the page's Share code field shows for these form values: an empty seed box gives the page's
    proposed seed"""
    seed = values.get("seed") or proposed
    return encode(rows, values, seed, game)
