#!/usr/bin/env python3
"""Fire Emblem Fates randomizer, track "weapons" (F-046 'build the other missing parts too'; docs/rando/WEAPONS.md).

The FE8 port's "Weapon might / hit / weight / uses", "Weapon traits" and "Better enemy weapons" chance, for Fates.
Our own code; the FE8 port (our sister project) gave the ideas. Public Fates tools were read for facts only.

What it changes (only cells of rows that already exist, table data only; every switch off = no edit at all):
  - weapon stats (Item table): might, hit, crit, avoid of every ordinary weapon (swords to tomes, the player's and
    the enemy-only ones), and the uses of staves (Fates weapons never break; only staves have uses). Each stat moves
    by up to its variance (a coin flip for the direction, then 0..variance), kept inside a bound; an original value
    outside the bound widens it, so nothing is pushed into or out of a range it already had. Staves keep their
    heal power and hit; stones (dragon / beast stones, breaths) are never changed. Prices stay.
  - weapon traits (Item table), a chance 0-100 per weapon, one trait at most: +2 to one stat while equipped,
    effective against one class group (armor, beast, dragon, flier), reverse weapon triangle, or crit +10..+20.
    "wild_traits" adds brave (strikes twice when attacking), double might on the counter, and 10% heal each turn.
    Plain weapons (no power of their own: the bronze / iron / steel sets and the like), staves, stones and
    enemy-only weapons get no trait. The item's help text stays the original (the spoiler log lists the traits).
  - better enemy weapons (DisposUnit table), a chance 0-100 per weapon an unscripted enemy carries: the weapon
    becomes a stronger ordinary weapon of the same kind and the same range that the unit's class may hold;
    upgrade_rank "same" (default, safe by the rule the enemies track already proved) keeps the rank at or below
    the old one; "next" also allows one rank up (needs a robot check first: docs/rando/WEAPONS.md section 5).
    Bosses always stay inside the rank they had. Works on top of the enemies track's own edits.

Never changed: Yato (every form), the legendary weapons (ISID_神武器), precious, can't-remove and personal weapons
(the royals', Ophelia's, the avatar's), weapons the player can never own (legal_player_weapon 0: the S-rank route
weapons, amiibo and downloadable ones), stones and breaths, and weapons an enemy drops (item flags bit 0).

Entry point for the integrate step:  plan_weapons(tables, rng, opts) -> (edits, spoiler_lines)
  tables: randolib.Facts (enough when enemy_upgrade is 0) or enemies.EnemyTables (its .f is the Facts; needed for
          enemy_upgrade). Every base value and rule comes from the tables passed in (F-047: Seal of Flames tables work
          the same way); rng: random.Random (use sub_rng(seed, opts)); opts: DEFAULT_OPTS keys plus
          "enemies_edits": the enemies track's edits (applied first; this track's DisposUnit edits name the value
          after them as "old").
  edits: Item rows {"table": "Item", "index", "label", "cells": {column: value}} (the items track's shape) and
         DisposUnit cells {"table": "DisposUnit", "file", "index", "label", "column", "old", "new"} (the enemies
         track's shape). check_weapons(tables, edits, opts) re-checks every guard from the edits alone.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "weapons"
TOOL_VERSION = "rando-weapons-v1"
STAT_COLS = ("might", "hit", "crit", "avoid", "uses")
DEFAULT_VARIANCE = {"might": 2, "hit": 10, "crit": 5, "avoid": 5, "uses": 2}      # Grok's pick (RANDO round 56)
BOUNDS = {"might": (1, 25), "hit": (40, 120), "crit": (0, 60), "avoid": (-30, 30), "uses": (1, 30)}
MAX_VARIANCE = {"might": 10, "hit": 40, "crit": 30, "avoid": 30, "uses": 10}
DEFAULT_TRAIT_CHANCE = 25
DEFAULT_OPTS = {"stats": False, "variance": None, "traits": 0, "wild_traits": False,
                "enemy_upgrade": 0, "upgrade_rank": "same", "difficulty": "normal", "boss_forge": 0}
# round 62 (F-049): "stronger" = one step on the same ladder, by the randomizer's difficulty (Grok's plan,
# docs/collab/OWNER_PICKS_R61_GROK.md). easy: +1 forge; normal: the next tier if the class (a boss: its own weapon
# rank) allows it, else +1 forge; hard: the next tier and +1 forge, else +2 forges. Weapons off every ladder (killer,
# brave, effective, the rest) only forge: +1, hard +2. The step (1/2/3) also sizes the tougher-bosses boost.
DIFFICULTIES = ("easy", "normal", "hard")
DIFFICULTY_STEP = {"easy": 1, "normal": 2, "hard": 3}
FORGE_TOP = 7                   # the game's highest forge level
FORGE_COLS = ("normal", "hard", "lunatic")   # DisposUnit item_N_forge.<game difficulty> (s8; negative = not given)
SILVER_DEBUFF = "ISID_戦闘後能力減少"     # silver weapons' "stats lower after battle": still a ladder rung
WEXP_COLS = ("sword", "lance", "axe", "dagger", "bow", "tome", "staff", "stone")   # PersonChapter weapon_exp.*
# Item flags (ISID_ ids, not game values)
KEEP_FLAGS = {"ISID_神武器", "ISID_貴重品", "ISID_外せない", "ISID_プレイヤー専用"}
NOT_PERSONAL = {"ISID_女性専用", "ISID_男性専用", "ISID_ダークマージ系専用", "ISID_敵専用"}
ENEMY_ONLY = "ISID_敵専用"
INFINITE = "ISID_無限回数"
NO_CRIT = "ISID_必殺奥義禁止"
MAGIC = "ISID_魔法武器"
EFFECTIVE_ONLY = ("ISID_非特効時威力－", "ISID_非特効時命中－")
F_BRAVE, F_REVERSE = "ISID_攻撃時2回攻撃", "ISID_3すくみ反転"
F_VENGE, F_REGEN = "ISID_反撃時武器威力2倍", "ISID_装備自動回復"
DOUBLE_MIGHT = {F_VENGE, "ISID_攻撃時武器威力2倍", "ISID_技勝利時武器威力2倍"}
TRAIT_EFFECTIVE = ("JCID_アーマー", "JCID_獣", "JCID_竜", "JCID_飛行")     # armor, beast, dragon, flier
TRAIT_STATS = ("str", "mag", "skl", "spd", "lck", "def", "res")
TRAIT_STAT_BONUS = 2
TRAIT_CRIT = (10, 15, 20)
BASE_TRAITS = ("stat", "effective", "reverse", "crit")
WILD_TRAITS = ("brave", "venge", "regen")
TRAIT_FLAG = {"reverse": F_REVERSE, "brave": F_BRAVE, "venge": F_VENGE, "regen": F_REGEN}
TRAIT_WORDS = {"stat": "+{n} {s} while equipped", "effective": "effective against {c}", "reverse": "reverse triangle",
               "crit": "crit +{n}", "brave": "brave (strikes twice when attacking)",
               "venge": "double might on the counter", "regen": "heals 10% each turn while equipped"}
CAT_WORDS = {"JCID_アーマー": "armor", "JCID_獣": "beasts", "JCID_竜": "dragons", "JCID_飛行": "fliers"}
DROP_BIT = 0x01                 # DisposUnit item_N_flags bit 0: the drop (unit::Item+0x2 bit 15, 0x8000); proven in
                                # round 64: killing the enemy gives the item to the player (docs/rando/DROP_FLAG.md)
ITEM_SLOTS = range(1, 6)
UPGRADE_MODES = ("same", "next")
UPGRADE_MARGIN = 10             # "stronger" = at least one might point (or 10 hit / crit) more, after the stat plan


class WeaponsError(R.RandoError):
    pass


def norm_opts(opts: dict | None) -> dict:
    o = dict(DEFAULT_OPTS, **{k: v for k, v in (opts or {}).items() if k in DEFAULT_OPTS})
    var = dict(DEFAULT_VARIANCE)
    for k, v in (o.get("variance") or {}).items():
        if k not in STAT_COLS:
            raise WeaponsError(f"variance: unknown stat {k!r} (use {', '.join(STAT_COLS)})")
        v = int(v)
        if not 0 <= v <= MAX_VARIANCE[k]:
            raise WeaponsError(f"variance {k}: 0..{MAX_VARIANCE[k]}")
        var[k] = v
    o["variance"] = var
    o["stats"] = bool(o["stats"])
    for k in ("traits", "enemy_upgrade"):
        v = o[k]
        if v is True:
            v = DEFAULT_TRAIT_CHANCE
        elif v is False or v is None:
            v = 0
        v = int(v)
        if not 0 <= v <= 100:
            raise WeaponsError(f"{k.replace('_', ' ')}: a chance 0..100")
        o[k] = v
    o["wild_traits"] = bool(o["wild_traits"])
    if o["upgrade_rank"] not in UPGRADE_MODES:
        raise WeaponsError("upgrade rank: same or next")
    o["difficulty"] = str(o["difficulty"]).strip().lower()
    if o["difficulty"] not in DIFFICULTIES:
        raise WeaponsError("difficulty: easy, normal or hard")
    o["boss_forge"] = int(o["boss_forge"] or 0)
    if not 0 <= o["boss_forge"] <= 3:
        raise WeaponsError("boss forge: the difficulty step 0..3")
    return o


def opts_text(o: dict) -> str:
    v = o["variance"]
    return (f"weapon stats={'on (' + ', '.join(f'{k} +/-{v[k]}' for k in STAT_COLS) + ')' if o['stats'] else 'off'}, "
            f"traits={o['traits']}%{' (wild)' if o['wild_traits'] and o['traits'] else ''}, "
            f"better enemy weapons={o['enemy_upgrade']}%" + (f" (difficulty {o['difficulty']}: one step on the ladder)"
                                                             if o["enemy_upgrade"] else "")
            + (f", boss weapons forged for difficulty step {o['boss_forge']}" if o["boss_forge"] else ""))


def sub_rng(seed: str, opts: dict | None = None) -> random.Random:
    """The track's own random stream: SHA-256 of (tool version, seed, track). The switches are not in the key: each
    draw has its own sub-stream (purpose, item or unit), so turning traits or upgrades on never moves the weapon
    stats, and another track's switches never move anything here."""
    norm_opts(opts)
    key = "\x1f".join([TOOL_VERSION, R.check_seed(seed), TRACK])
    return random.Random(int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest(), "big"))


def _stream(base: int, *parts) -> random.Random:
    key = "\x1f".join([str(base)] + [str(p) for p in parts])
    return random.Random(int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest(), "big"))


def _chapter(path: str) -> str:
    return str(path).replace("\\", "/").rsplit("/", 1)[-1].split(".", 1)[0]


def _facts(tables) -> R.Facts:
    return tables.f if hasattr(tables, "f") and isinstance(tables.f, R.Facts) else tables


# ------------------------------------------------------------------ item facts
class WeaponView:
    """Which items this track may touch, and how, from the Item table passed in."""

    def __init__(self, facts: R.Facts):
        self.f = facts
        self.staff_k, self.stone_k = facts.rules["staff_kind"], facts.rules["stone_kind"]
        cats = set()
        for it in facts.item_list:
            cats |= R.flags(it.get("effective", ""))
        self.eff_groups = [c for c in TRAIT_EFFECTIVE if c in cats]     # only groups the table already uses
        # a kind's own effectiveness (bows against fliers): on at least half of that kind's shop weapons
        self.common_eff: dict[int, set] = {}
        shop: dict[int, list] = {}
        for it in facts.item_list:
            k = facts.item_kind(it["label"])
            if k is not None and R.ival(it.get("buy_price", 0)) > 0 and R.ival(it.get("legal_player_weapon", 0)) == 1:
                shop.setdefault(k, []).append(R.flags(it.get("effective", "")))
        for k, sets in shop.items():
            self.common_eff[k] = {c for c in set().union(*sets) if 2 * sum(c in x for x in sets) >= len(sets)}

    def it(self, iid: str) -> dict:
        return self.f.items[iid]

    def flags(self, iid: str) -> set[str]:
        return R.flags(self.f.items[iid].get("flags", "")) if iid in self.f.items else set()

    def v(self, iid: str, col: str) -> int:
        return R.ival(self.f.items[iid].get(col, 0))

    def kind(self, iid: str):
        return self.f.item_kind(iid)

    def kept(self, iid: str) -> str | None:
        """Why this item is never changed by this track (None = it may be)."""
        if iid not in self.f.items or R.ival(self.f.items[iid]["index"]) == 0:
            return "not an item"
        k = self.kind(iid)
        if k is None:
            return "not a weapon or staff"
        if k == self.stone_k:
            return "stone or breath"
        fl = self.flags(iid)
        if fl & KEEP_FLAGS:
            return "Yato, legendary, precious or can't-remove weapon"
        if any("専用" in x for x in fl - NOT_PERSONAL):
            return "personal weapon"
        lpw = self.v(iid, "legal_player_weapon")
        if lpw not in (1, 2) and ENEMY_ONLY not in fl:
            return "never the player's (route S-rank, amiibo, downloadable)"
        return None

    def stat_cols(self, iid: str) -> tuple[str, ...]:
        """The stats this track may move on iid: weapons might/hit/crit/avoid; staves only their uses."""
        if self.kept(iid):
            return ()
        if self.kind(iid) == self.staff_k:
            return ("uses",) if self.v(iid, "uses") > 0 and INFINITE not in self.flags(iid) else ()
        cols = ["might", "hit", "avoid"]
        if NO_CRIT not in self.flags(iid):
            cols.insert(2, "crit")
        return tuple(cols)

    def plain(self, iid: str) -> bool:
        """No power of its own: no flag but 'no crit', no effectiveness, bought in shops, rank C or lower, crit 5 or
        less (the bronze / iron / steel sets and the like). Plain weapons get no trait."""
        fl = self.flags(iid) - {NO_CRIT}
        eff = R.flags(self.it(iid).get("effective", "")) - self.common_eff.get(self.kind(iid), set())
        return (not fl and not eff and self.v(iid, "buy_price") > 0
                and self.f.item_rank(iid) <= R.RANKS[2] and self.v(iid, "crit") <= 5)

    def trait_ok(self, iid: str) -> bool:
        return (not self.kept(iid) and self.kind(iid) not in (self.staff_k, self.stone_k)
                and ENEMY_ONLY not in self.flags(iid) and not self.plain(iid))

    def eligible_traits(self, iid: str, wild: bool) -> list[str]:
        fl = self.flags(iid)
        it = self.it(iid)
        out = []
        if any(self.v(iid, f"stat_bonus.{s}") <= 0 for s in TRAIT_STATS):
            out.append("stat")
        if not R.flags(it.get("effective", "")) and self.eff_groups:
            out.append("effective")
        if F_REVERSE not in fl:
            out.append("reverse")
        if self.v(iid, "crit") <= 10 and NO_CRIT not in fl:
            out.append("crit")
        if wild:
            if F_BRAVE not in fl:
                out.append("brave")
            if not fl & DOUBLE_MIGHT:
                out.append("venge")
            if F_REGEN not in fl:
                out.append("regen")
        return out


def bound(col: str, van: int) -> tuple[int, int]:
    lo, hi = BOUNDS[col]
    return min(lo, van), max(hi, van)


def vary(r: random.Random, value: int, var: int, col: str) -> int:
    """The FE8 port's (UFER's) variance: a coin flip for the sign, then 0..var, clamped (widened by the original)."""
    up = r.randrange(2)
    d = r.randrange(var + 1)
    n = value + d if up else value - d
    lo, hi = bound(col, value)
    return max(lo, min(hi, n))


# ------------------------------------------------------------------ the plan
def plan_weapons(tables, rng: random.Random, opts: dict | None = None):
    o = norm_opts(opts)
    facts = _facts(tables)
    wv = WeaponView(facts)
    base = rng.getrandbits(256)
    lines = [f"Weapons (track 'weapons'): {opts_text(o)}"]
    cells: dict[str, dict] = {}
    if o["stats"]:
        lines += _plan_stats(wv, base, o, cells)
    if o["traits"]:
        lines += _plan_traits(wv, base, o, cells)
    edits = [{"table": "Item", "index": R.ival(facts.items[i]["index"]), "label": i,
              "cells": {c: str(v) for c, v in sorted(cs.items())}}
             for i, cs in sorted(cells.items(), key=lambda kv: R.ival(facts.items[kv[0]]["index"]))]
    if o["enemy_upgrade"] or o["boss_forge"]:
        if not hasattr(tables, "dispos") or not hasattr(tables, "scripted"):
            raise WeaponsError("better enemy weapons needs the enemies track's tables (enemies.load_tables())")
        e, ln = _plan_upgrades(tables, wv, base, o, edits, (opts or {}).get("enemies_edits") or [],
                               (opts or {}).get("boss_rows"), (opts or {}).get("refine"))
        edits += e
        lines += ln
    return edits, lines


def _plan_stats(wv: WeaponView, base: int, o: dict, cells: dict) -> list[str]:
    f = wv.f
    n_items, n_cells = 0, 0
    lines = []
    for it in f.item_list:
        i = it["label"]
        bits = []
        for c in wv.stat_cols(i):
            var = o["variance"][c]
            if not var:
                continue
            old = wv.v(i, c)
            new = vary(_stream(base, "stat", c, i), old, var, c)
            if new != old:
                cells.setdefault(i, {})[c] = new
                bits.append(f"{c} {old}->{new}")
                n_cells += 1
        if bits:
            n_items += 1
            lines.append(f"  {f.iname(i)}: " + ", ".join(bits))
    return [f"Weapon stats: {n_cells} values changed on {n_items} weapons and staves (prices and help text stay):"] + lines


def _plan_traits(wv: WeaponView, base: int, o: dict, cells: dict) -> list[str]:
    f = wv.f
    lines = []
    for it in f.item_list:
        i = it["label"]
        if not wv.trait_ok(i):
            continue
        r = _stream(base, "trait", i)
        if r.randrange(100) >= o["traits"]:
            continue
        el = wv.eligible_traits(i, o["wild_traits"])
        if not el:
            continue
        t = r.choice(el)
        c = cells.setdefault(i, {})
        if t == "stat":
            s = r.choice([s for s in TRAIT_STATS if wv.v(i, f"stat_bonus.{s}") <= 0])
            c[f"stat_bonus.{s}"] = wv.v(i, f"stat_bonus.{s}") + TRAIT_STAT_BONUS
            word = TRAIT_WORDS[t].format(n=TRAIT_STAT_BONUS, s=s)
        elif t == "effective":
            g = r.choice(wv.eff_groups)
            c["effective"] = g
            word = TRAIT_WORDS[t].format(c=CAT_WORDS.get(g, g))
        elif t == "crit":
            n = r.choice(TRAIT_CRIT)
            c["crit"] = c.get("crit", wv.v(i, "crit")) + n
            word = TRAIT_WORDS[t].format(n=n)
        else:
            c["flags"] = "|".join([x for x in str(it.get("flags", "")).split("|") if x] + [TRAIT_FLAG[t]])
            word = TRAIT_WORDS[t]
        lines.append(f"  {f.iname(i)}: {word}")
    return [f"Weapon traits: {len(lines)} weapons got one (the in-game help text does not mention it):"] + lines


def planned_value(wv: WeaponView, item_cells: dict, iid: str, col: str) -> int:
    c = item_cells.get(iid, {})
    return R.ival(c[col]) if col in c else wv.v(iid, col)


def power(wv: WeaponView, item_cells: dict, iid: str) -> int:
    """How strong a weapon is for the upgrade rule: might counts ten times as much as hit or crit."""
    g = lambda col: planned_value(wv, item_cells, iid, col)  # noqa: E731
    return 10 * g("might") + g("hit") + g("crit")


def effective(wv: WeaponView, item_cells: dict, iid: str) -> set[str]:
    """The class groups a weapon is effective against, after this track's own Item cells (traits may add one)."""
    c = item_cells.get(iid, {})
    return R.flags(c["effective"] if "effective" in c else wv.it(iid).get("effective", ""))


def next_rank(rank: int) -> int:
    up = [x for x in R.RANKS if x > rank]
    return up[0] if up else rank


def upgrade_pool(t, wv: WeaponView, item_cells: dict, jid: str, fem: bool, iid: str, kind: int, rank: int,
                 boss: bool, mode: str) -> list[str]:
    """Stronger ordinary weapons for one enemy slot: same kind, same range, same magic-or-not, an ordinary shop
    weapon (not special, not 'effective only'), one the unit's class may hold, at least UPGRADE_MARGIN stronger;
    rank the old one ('same', and always for bosses) or up to the next rank ('next'; the next-rank ones first)."""
    f = wv.f
    top = rank if boss or mode == "same" else next_rank(rank)
    rmin, rmax = wv.v(iid, "range_min"), wv.v(iid, "range_max")
    magic = MAGIC in wv.flags(iid)
    p_old = power(wv, item_cells, iid)
    eff_old = effective(wv, item_cells, iid)      # Grok W1 (a): an upgrade never loses an "effective against" bonus
    out = []
    for it in f.item_list:
        c = it["label"]
        if c == iid or wv.kind(c) != kind or not rank <= f.item_rank(c) <= top or t.special_item(c):
            continue
        if wv.v(c, "legal_player_weapon") != 1 or wv.v(c, "buy_price") <= 0:
            continue
        fl = wv.flags(c)
        if any(x in fl for x in EFFECTIVE_ONLY) or (MAGIC in fl) != magic:
            continue
        if (wv.v(c, "range_min"), wv.v(c, "range_max")) != (rmin, rmax):
            continue
        if power(wv, item_cells, c) < p_old + UPGRADE_MARGIN or not t.can_hold(jid, fem, c):
            continue
        if not eff_old <= effective(wv, item_cells, c):
            continue
        out.append(c)
    hi = [c for c in out if f.item_rank(c) > rank]
    return hi or out


def _apply_chain(t, enemies_edits: list[dict]) -> dict:
    """{(file, index): row} after the enemies track's edits (checked: each edit's old value must match)."""
    by = {(d["file"], R.ival(d["index"])): d for d in t.dispos}
    rows: dict = {}
    for e in enemies_edits:
        k = (e["file"], R.ival(e["index"]))
        if e.get("table") != "DisposUnit" or k not in by:
            raise WeaponsError(f"enemies edit {k}: not a DisposUnit row")
        row = rows.setdefault(k, dict(by[k]))
        if str(row.get(e["column"], "")) != str(e["old"]):
            raise WeaponsError(f"enemies edit {k} {e['column']}: old value differs")
        row[e["column"]] = e["new"]
    return rows


def rating(wv: WeaponView, iid: str) -> int:
    """What a weapon adds to the unit's Rating on its stat page: the sum of its stat bonuses (the Rating is the sum
    of Str, Mag, Skl, Spd, Lck, Def and Res, weapon bonuses included)."""
    return sum(wv.v(iid, f"stat_bonus.{s}") for s in R.STATS if s != "hp")


def ladder_lines(wv: WeaponView) -> dict[tuple, list[str]]:
    """The one-step ladders, from the Item table passed in (F-047: no item names): per weapon sub-kind (sword,
    katana, lance, naginata, ...: Item.weapon_kind, whose ItemSubKind row carries the side), range and magic, the
    cheapest shop weapon of each of the first four ranks (E, D, C, B: bronze/brass, iron, steel, silver) that has
    no power of its own (no flag but 'no crit' and the silver 'stats lower after battle', crit 5 or less, no
    'effective against' beyond its kind's own). A line keeps only rungs of consecutive ranks whose might rises and
    whose Rating never falls; a line of one rung is no ladder."""
    try:
        return wv._ladder
    except AttributeError:
        pass
    f = wv.f
    best: dict[tuple, tuple] = {}
    for it in f.item_list:
        i = it["label"]
        k = wv.kind(i)
        if k is None or k in (wv.staff_k, wv.stone_k) or wv.kept(i) or ENEMY_ONLY in wv.flags(i):
            continue
        if wv.v(i, "legal_player_weapon") != 1 or wv.v(i, "buy_price") <= 0:
            continue
        fl = wv.flags(i)
        if fl - {NO_CRIT, SILVER_DEBUFF} or wv.v(i, "crit") > 5:
            continue
        if R.flags(it.get("effective", "")) - wv.common_eff.get(k, set()):
            continue
        rk = f.item_rank(i)
        if rk not in R.RANKS[:4]:
            continue
        key = (str(it.get("weapon_kind", "")), k, wv.v(i, "range_min"), wv.v(i, "range_max"), MAGIC in fl)
        cand = (wv.v(i, "buy_price"), R.ival(it["index"]), i)
        if (key, rk) not in best or cand < best[(key, rk)]:
            best[(key, rk)] = cand
    by: dict[tuple, list] = {}
    for (key, rk), c in best.items():
        by.setdefault(key, []).append((rk, c[2]))
    out: dict[tuple, list[str]] = {}
    for key in sorted(by):
        rungs = sorted(by[key])
        run: list[str] = []
        for rk, i in rungs:
            if run:
                prev = run[-1]
                if (next_rank(f.item_rank(prev)) != rk or wv.v(i, "might") <= wv.v(prev, "might")
                        or rating(wv, i) < rating(wv, prev)):
                    if len(run) > 1:
                        out[key + (len(out),)] = run
                    run = []
            run.append(i)
        if len(run) > 1:
            out[key + (len(out),)] = run
    wv._ladder = out
    return out


def next_rung(lines: dict, iid: str) -> str | None:
    for run in lines.values():
        if iid in run:
            n = run.index(iid)
            return run[n + 1] if n + 1 < len(run) else None
    return None


def on_ladder(lines: dict, iid: str) -> bool:
    return any(iid in run for run in lines.values())


def load_refine() -> dict[int, dict] | None:
    """The game's forge table (ItemRefine rows by index), read only; None when the tables are not there."""
    try:
        import gamedata as GD
        if GD.available():
            return None
        return {R.ival(r["index"]): r for r in GD._load("ItemRefine")}
    except Exception:  # noqa: BLE001
        return None


def refine_might(refine, row_ix: int, lvl: int) -> int:
    """Might the forge level lvl adds in total (ItemRefine row: plus_N.might, what unit::Item::GetPower adds);
    without the table, one point per level."""
    if not refine or lvl <= 0:
        return max(0, lvl) if not refine else 0
    row = refine.get(row_ix) or refine.get(0)
    return R.ival(row.get(f"plus_{lvl}.might", lvl)) if row else lvl


def boss_refine_row(t, wv: WeaponView, d: dict, iid: str) -> int:
    """The forge table row whose might the game adds to this boss's weapon (round 63, the game's own rule):
    Unit::SetDisposItem 003D8C38 gives every weapon of a unit whose Person.unit_kind is not 1 (enemies, bosses,
    other armies) name slot 1 (unit::Item+0x2 bits 0-6), and unit::Item::GetPower 0053B4B4 then reads the
    forge row from Item+0x49 (`unknown_49`, the second forge table) instead of Item+0x48 (`refine_index`).
    A playable person (unit_kind 1) keeps refine_index. Drop-marked weapons (name slot cleared) are never forged
    here (forgeable)."""
    p = t.pc.get(d.get("pid", "")) if hasattr(t, "pc") else None
    kind = R.ival((p or {}).get("unit_kind", 0) or 0) if p else 0
    return wv.v(iid, "refine_index") if kind == 1 else wv.v(iid, "unknown_49")


def boss_might_plan(refine, row_ix: int, cur: int, step: int) -> tuple[int, int, bool]:
    """(forge levels, might the player sees added, stopped by the forge maximum) for the tougher-bosses weapon
    part: the fewest forge levels on top of cur whose added might (the game's forge row) is at least step
    (F-049: +1 / +2 / +3 shown might for Easy / Normal / Hard). Second-table rows (row 2) add 1 might per level,
    so the levels equal the step; rows 0/1 add 2 per level, so the shown might can only be even there. When the
    forge maximum (7) stops the climb, the levels left are used and capped is True."""
    cur = max(0, cur)
    base = refine_might(refine, row_ix, cur)
    if step <= 0:
        return 0, 0, False
    for n in range(1, FORGE_TOP - cur + 1):
        add = refine_might(refine, row_ix, cur + n) - base
        if add >= step:
            return n, add, False
    n = max(0, FORGE_TOP - cur)
    return n, refine_might(refine, row_ix, cur + n) - base, True


def boss_forge_levels(refine, row_ix: int, cur: int, step: int) -> int:
    """Forge levels of boss_might_plan (kept for callers that need only the count)."""
    return boss_might_plan(refine, row_ix, cur, step)[0]


def forge_plan(o: dict, tier: bool, ladder: bool) -> int:
    """Forge levels for one upgraded slot (see DIFFICULTY_STEP's comment)."""
    d = o["difficulty"]
    if d == "easy":
        return 1
    if ladder and tier:
        return 1 if d == "hard" else 0
    return 2 if d == "hard" else 1


def boss_rank_ok(t, d: dict, iid: str) -> bool:
    """A boss keeps its stored weapon exp: the new tier only when that exp already reaches its rank."""
    p = t.pc.get(d["pid"]) if hasattr(t, "pc") else None
    k = t.f.item_kind(iid)
    if p is None or k is None or k >= len(WEXP_COLS):
        return False
    return R.ival(p.get(f"weapon_exp.{WEXP_COLS[k]}", 0) or 0) >= max(t.f.item_rank(iid), 1)


def power_might(wv: WeaponView, item_cells: dict, iid: str) -> int:
    return planned_value(wv, item_cells, iid, "might")


def slot_step(t, wv: WeaponView, lines_: dict, item_cells: dict, o: dict, d: dict, jid: str, fem: bool, boss: bool,
              iid: str) -> tuple[str, int]:
    """(new weapon, forge levels) for one upgraded slot: the next rung when the difficulty and the rank allow it."""
    lad = on_ladder(lines_, iid) and not t.special_item(iid)
    nxt = next_rung(lines_, iid) if lad and o["difficulty"] != "easy" else None
    if nxt and (not t.can_hold(jid, fem, nxt) or (boss and not boss_rank_ok(t, d, nxt))
                or power_might(wv, item_cells, nxt) <= power_might(wv, item_cells, iid)
                or rating(wv, nxt) < rating(wv, iid)):
        nxt = None
    return (nxt or iid), forge_plan(o, bool(nxt), lad)


def _boost_row(t, o: dict, d: dict, boss_rows: set) -> bool:
    ch = _chapter(d["file"])[:4]
    return bool(o["boss_forge"]) and (ch, d.get("pid", "")) in boss_rows and ch not in getattr(t, "guarded", {})


def forgeable(t, wv: WeaponView, d: dict, row: dict, s: int, jid: str, fem: bool) -> str | None:
    """The weapon in slot s when this track may upgrade or forge it, else None."""
    f = wv.f
    iid = row.get(f"item_{s}", "")
    kind = f.item_kind(iid)
    if kind is None or kind in (f.rules["stone_kind"], f.rules["staff_kind"]) or wv.kept(iid):
        return None
    if R.ival(d.get(f"item_{s}_flags", 0)) & DROP_BIT or not t.can_hold(jid, fem, iid):
        return None                          # a drop, or a weapon the unit cannot use anyway: kept
    return iid


def _plan_upgrades(t, wv: WeaponView, base: int, o: dict, item_edits: list[dict], enemies_edits: list[dict],
                   boss_rows=None, refine=None):
    f = wv.f
    item_cells = {e["label"]: e["cells"] for e in item_edits}
    rows = _apply_chain(t, enemies_edits)
    lines_ = ladder_lines(wv)
    boss_rows = {(str(a)[:4], b) for a, b in (boss_rows or ())}
    edits, lines = [], []
    rolls = forged = tiers = boss_n = 0
    for d in t.dispos:
        if t.out_of_scope(d):
            continue
        k = (d["file"], R.ival(d["index"]))
        ch = _chapter(d["file"])
        scripted = t.scripted(d)
        boost = _boost_row(t, o, d, boss_rows)
        if scripted and not boost:
            continue
        row = rows.get(k, d)
        old_job = t.unit_job(d)
        if old_job is None or old_job not in f.jobs:
            continue
        jid = row.get("jid") or old_job
        fem = f.female(f.jobs[old_job])
        boss = t.is_boss(d)
        for s in ITEM_SLOTS:
            iid = forgeable(t, wv, d, row, s, jid, fem)
            if iid is None:
                continue
            new, n = iid, 0
            if o["enemy_upgrade"] and not scripted:
                rolls += 1
                r = _stream(base, "upgrade", d["file"], k[1], s)
                if r.randrange(100) < o["enemy_upgrade"]:
                    new, n = slot_step(t, wv, lines_, item_cells, o, d, jid, fem, boss, iid)
                    tiers += new != iid
            cur = [R.ival(d.get(f"item_{s}_forge.{c}", 0) or 0) for c in FORGE_COLS]
            brow = boss_refine_row(t, wv, d, new) if boost else 0
            bn, badd, bcap = (boss_might_plan(refine, brow, max([0] + cur) + n, o["boss_forge"]) if boost
                              else (0, 0, False))
            if new == iid and n == 0 and bn == 0:
                if boost and bcap:
                    lines.append(f"  {ch} unit {k[1]} slot {s}: {f.iname(new)} already at the forge maximum 7: "
                                 "no tougher-boss might added")
                continue
            bits = []
            if new != iid:
                edits.append({"table": "DisposUnit", "file": d["file"], "index": k[1], "label": d.get("label", ""),
                              "column": f"item_{s}", "old": iid, "new": new})
                bits.append(f"{f.iname(iid)} -> {f.iname(new)}")
            moved = False
            for c, v in zip(FORGE_COLS, cur):
                if v < 0:
                    continue                 # not given on that game difficulty: left alone
                nv = min(FORGE_TOP, v + n + bn)
                if nv != v:
                    moved = True
                    edits.append({"table": "DisposUnit", "file": d["file"], "index": k[1], "label": d.get("label", ""),
                                  "column": f"item_{s}_forge.{c}", "old": str(d.get(f"item_{s}_forge.{c}", "0")),
                                  "new": str(nv)})
            if moved:
                forged += 1
                boss_n += bool(bn)
                bits.append(f"forge +{n + bn}" + (f" (tougher boss +{bn}: might +{badd} shown"
                                                  + (", stopped by the forge maximum 7" if bcap else "")
                                                  + (f", +{o['boss_forge']} wanted, this weapon's forge steps"
                                                     f" give {badd}" if not bcap and badd != o["boss_forge"] else "")
                                                  + ")" if bn else ""))
            if bits:
                lines.append(f"  {ch} unit {k[1]}{' (boss)' if boss else ''} slot {s}: " + ", ".join(bits))
    head = [f"Better enemy weapons ({o['difficulty']}): {tiers} moved one tier up their ladder, {forged} slots forged "
            f"({boss_n} of them boss weapons: tougher bosses), {rolls} enemy weapons rolled at {o['enemy_upgrade']}%; "
            "drops, Yato, legendary and personal weapons, staves and stones kept:"]
    return edits, head + lines


# ------------------------------------------------------------------ guards (from the edits alone)
ITEM_COLS = set(STAT_COLS) | {"flags", "effective"} | {f"stat_bonus.{s}" for s in R.STATS}


def check_weapons(tables, edits: list[dict], opts: dict | None = None) -> dict:
    o = norm_opts(opts)
    f = _facts(tables)
    wv = WeaponView(f)
    out: dict[str, dict] = {}

    def g(name, bad, info=None):
        out[name] = {"ok": not bad, "detail": bad[:50] + (info or [])}

    items_ed = [e for e in edits if e.get("table") == "Item"]
    disp_ed = [e for e in edits if e.get("table") == "DisposUnit"]
    # 1. only allowed tables, rows and cells
    bad = []
    seen = set()
    for e in edits:
        if e.get("table") not in ("Item", "DisposUnit"):
            bad.append(f"table {e.get('table')}")
            continue
        if e["table"] == "Item":
            it = f.items.get(e["label"])
            if it is None or R.ival(it["index"]) != R.ival(e["index"]):
                bad.append(f"Item {e['label']}: no such row")
            elif set(e["cells"]) - ITEM_COLS:
                bad.append(f"Item {e['label']}: cells {sorted(set(e['cells']) - ITEM_COLS)}")
            if e["label"] in seen:
                bad.append(f"Item {e['label']}: two edits")
            seen.add(e["label"])
        elif e["column"] not in {f"item_{s}" for s in ITEM_SLOTS} | {f"item_{s}_forge.{c}" for s in ITEM_SLOTS
                                                                     for c in FORGE_COLS}:
            bad.append(f"DisposUnit {e['file']} #{e['index']}: column {e['column']}")
    if not o["stats"] and not o["traits"] and items_ed:
        bad.append("Item edits with weapon stats and traits off")
    if not o["enemy_upgrade"] and not o["boss_forge"] and disp_ed:
        bad.append("DisposUnit edits with better enemy weapons off")
    g("only_allowed_cells", bad)
    # 2. kept items untouched; staves only uses; stones never
    bad = []
    for e in items_ed:
        i = e["label"]
        if i not in f.items:
            continue
        why = wv.kept(i)
        if why:
            bad.append(f"{f.iname(i)}: {why}, must stay")
        elif wv.kind(i) == wv.staff_k and set(e["cells"]) - {"uses"}:
            bad.append(f"{f.iname(i)}: a staff may only change its uses")
    g("kept_items_untouched", bad)
    # 3. stats inside their bounds and variance; one trait at most, only on weapons that may take one
    bad = []
    for e in items_ed:
        i = e["label"]
        if i not in f.items or wv.kept(i):
            continue
        c = e["cells"]
        traits = []
        for col in STAT_COLS:
            if col not in c:
                continue
            van, new = wv.v(i, col), R.ival(c[col])
            var = o["variance"][col] if o["stats"] and col in wv.stat_cols(i) else 0
            lo, hi = bound(col, van)
            if col == "crit" and new - van > var:          # a crit trait on top
                traits.append("crit")
                if NO_CRIT in wv.flags(i) or van > 10 or new - van > var + max(TRAIT_CRIT):
                    bad.append(f"{f.iname(i)}: crit {van}->{new}")
                continue
            if abs(new - van) > var or not lo <= new <= hi:
                bad.append(f"{f.iname(i)}: {col} {van}->{new} (variance {var}, bound {lo}..{hi})")
        for s in R.STATS:
            col = f"stat_bonus.{s}"
            if col in c:
                traits.append("stat")
                if s not in TRAIT_STATS or R.ival(c[col]) - wv.v(i, col) != TRAIT_STAT_BONUS or wv.v(i, col) > 0:
                    bad.append(f"{f.iname(i)}: {col} {wv.v(i, col)}->{c[col]}")
        if "effective" in c:
            traits.append("effective")
            if R.flags(f.items[i].get("effective", "")) or c["effective"] not in wv.eff_groups:
                bad.append(f"{f.iname(i)}: effective -> {c['effective']}")
        if "flags" in c:
            old, new = wv.flags(i), R.flags(c["flags"])
            added = new - old
            allowed = {TRAIT_FLAG[t] for t in (BASE_TRAITS + (WILD_TRAITS if o["wild_traits"] else ())) if t in TRAIT_FLAG}
            if not old <= new or len(added) != 1 or not added <= allowed:
                bad.append(f"{f.iname(i)}: flags lost or wrong ones added ({sorted(old - new)} / {sorted(added)})")
            traits.append("flag")
        if traits and not o["traits"]:
            bad.append(f"{f.iname(i)}: a trait with traits off")
        if len(traits) > 1:
            bad.append(f"{f.iname(i)}: {len(traits)} traits")
        if traits and not wv.trait_ok(i):
            bad.append(f"{f.iname(i)}: may not take a trait (plain, staff, stone or enemy-only)")
    g("stats_in_bounds_one_trait", bad)
    # 4. no weapon left broken: might >= 0, hit > 0, uses >= 1 for staves that had uses, ranges / rank / kind kept
    bad = []
    for e in items_ed:
        i = e["label"]
        if i not in f.items:
            continue
        c = e["cells"]
        if R.ival(c.get("might", wv.v(i, "might"))) < 0 or (wv.kind(i) != wv.staff_k and R.ival(c.get("hit", wv.v(i, "hit"))) <= 0):
            bad.append(f"{f.iname(i)}: might or hit out of range")
        if wv.v(i, "uses") > 0 and R.ival(c.get("uses", 1)) < 1:
            bad.append(f"{f.iname(i)}: no uses left")
    g("no_broken_weapons", bad)
    # 5. enemy upgrades (round 62, F-049): one step on the ladder by the difficulty, no sidegrade by the game's
    #    Rating, forges inside 0..7, story units only for the tougher-bosses forge, drops and kept weapons untouched
    bad, info = [], []
    t = tables
    if disp_ed:
        if not hasattr(t, "dispos"):
            bad.append("DisposUnit edits without the enemies track's tables")
        else:
            try:
                rows = _apply_chain(t, (opts or {}).get("enemies_edits") or [])
            except WeaponsError as ex:
                rows = {}
                bad.append(str(ex))
            by = {(d["file"], R.ival(d["index"])): d for d in t.dispos}
            item_cells = {e["label"]: e["cells"] for e in items_ed}
            lines_ = ladder_lines(wv)
            boss_rows = {(str(a)[:4], b) for a, b in ((opts or {}).get("boss_rows") or ())}
            refine = (opts or {}).get("refine")
            done = set()
            slots: dict[tuple, dict] = {}
            for e in disp_ed:
                k = (e["file"], R.ival(e["index"]))
                if (k, e["column"]) in done:
                    bad.append(f"{k} {e['column']}: two edits")
                done.add((k, e["column"]))
                s = int(e["column"].split("_")[1])
                slots.setdefault((k, s), {})[e["column"]] = e
            tiers = forges = 0
            for (k, s), cols in sorted(slots.items()):
                d = by.get(k)
                if d is None:
                    bad.append(f"{k}: no such row")
                    continue
                if t.out_of_scope(d):
                    bad.append(f"{k}: {t.out_of_scope(d)}")
                    continue
                scripted = t.scripted(d)
                boost = _boost_row(t, o, d, boss_rows)
                if scripted and not boost:
                    bad.append(f"{k}: {scripted}")
                    continue
                row = rows.get(k, d)
                old_job = t.unit_job(d)
                jid = row.get("jid") or old_job
                fem = f.female(f.jobs[old_job])
                boss = t.is_boss(d)
                old = row.get(f"item_{s}", "")
                if forgeable(t, wv, d, row, s, jid, fem) is None:
                    bad.append(f"{k} slot {s}: {old or 'empty'} may not be upgraded or forged (drop, kept, staff, stone)")
                    continue
                ie = cols.get(f"item_{s}")
                new = old
                if ie is not None:
                    if str(ie["old"]) != str(old):
                        bad.append(f"{k} slot {s}: old value is not the value after the enemies track")
                    new = ie["new"]
                    if scripted or not o["enemy_upgrade"]:
                        bad.append(f"{k} slot {s}: a weapon changed on a story unit or with upgrades off")
                    if o["difficulty"] == "easy":
                        bad.append(f"{k} slot {s}: a new tier on Easy (forge only)")
                    if next_rung(lines_, old) != new or t.special_item(old):
                        bad.append(f"{k} slot {s}: {old} -> {new} is not one step up the same ladder")
                    if not t.can_hold(jid, fem, new):
                        bad.append(f"{k} slot {s}: {new} cannot be held by {jid}")
                    if boss and not boss_rank_ok(t, d, new):
                        bad.append(f"{k} slot {s}: {new} is above the boss's own weapon rank")
                    if rating(wv, new) < rating(wv, old):
                        bad.append(f"{k} slot {s}: {old} -> {new} lowers the Rating (a sidegrade)")
                    if power_might(wv, item_cells, new) <= power_might(wv, item_cells, old):
                        bad.append(f"{k} slot {s}: {new} has no more might than {old} (a sidegrade)")
                    if not effective(wv, item_cells, old) <= effective(wv, item_cells, new):
                        bad.append(f"{k} slot {s}: {old} -> {new} loses an 'effective against' bonus")
                    tiers += 1
                tier = new != old
                lad = on_ladder(lines_, old) and not t.special_item(old)
                if tier:
                    ns = [forge_plan(o, True, lad)]
                elif o["enemy_upgrade"] and not scripted:
                    ns = [0, forge_plan(o, False, lad)]     # the roll missed, or hit with no tier possible
                else:
                    ns = [0]
                cur = [R.ival(d.get(f"item_{s}_forge.{c}", 0) or 0) for c in FORGE_COLS]
                got = []
                for c, v in zip(FORGE_COLS, cur):
                    col = f"item_{s}_forge.{c}"
                    if col in cols and str(cols[col]["old"]) != str(d.get(col, "0")):
                        bad.append(f"{k} {col}: old value differs")
                    got.append(R.ival(cols[col]["new"]) if col in cols else v)
                wants = []
                for n_up in ns:
                    bn = (boss_forge_levels(refine, boss_refine_row(t, wv, d, new), max([0] + cur) + n_up,
                                            o["boss_forge"]) if boost else 0)
                    wants.append([v if v < 0 else min(FORGE_TOP, v + n_up + bn) for v in cur])
                if got not in wants or any(x > FORGE_TOP for x in got):
                    bad.append(f"{k} slot {s} forge: {cur} -> {got}, the {o['difficulty']} rule gives one of {wants}")
                forges += any(c != f"item_{s}" for c in cols)
            info.append(f"{tiers} tier steps, {forges} forged slots ({o['difficulty']})")
    g("enemy_upgrades_legal", bad, info)
    return out


# ------------------------------------------------------------------ output (inspection only; the wiring merges)
def edits_to_files(facts: R.Facts, edits: list[dict], dispos: list[dict] | None = None) -> dict[str, bytes]:
    """CSV files for this track's edits alone (Item rows: the changed columns, unchanged ones from the table;
    DisposUnit rows: the five item cells after the edits)."""
    import csv
    import io
    files: dict[str, bytes] = {}

    def put(rel, rows):
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        files[rel] = ("﻿" + buf.getvalue()).encode("utf-8")
    ie = [e for e in edits if e["table"] == "Item"]
    if ie:
        cols = sorted({c for e in ie for c in e["cells"]})
        rows = [["index", "label"] + cols]
        for e in sorted(ie, key=lambda e: e["index"]):
            it = facts.items[e["label"]]
            rows.append([str(e["index"]), e["label"]] + [e["cells"].get(c, it.get(c, "")) for c in cols])
        put("tables/Item.csv", rows)
    de = [e for e in edits if e["table"] == "DisposUnit"]
    if de:
        by = {(d["file"], R.ival(d["index"])): d for d in (dispos or [])}
        cur: dict = {}
        for e in de:
            k = (e["file"], e["index"])
            row = cur.setdefault(k, {f"item_{s}": by[k].get(f"item_{s}", "") for s in ITEM_SLOTS})
            row[e["column"]] = e["new"]
        rows = [["file", "index", "label"] + [f"item_{s}" for s in ITEM_SLOTS]]
        for k in sorted(cur):
            rows.append([k[0], str(k[1]), by[k].get("label", "")] + [cur[k][f"item_{s}"] for s in ITEM_SLOTS])
        put("tables/DisposUnit.csv", rows)
    return files


def cmd_make(a) -> int:
    """This track alone (on top of the enemies track's gear edits when asked) as one mod folder, for inspection."""
    import enemies as E
    t = E.load_tables()
    opts = {"stats": a.stats, "traits": a.traits, "wild_traits": a.wild_traits, "enemy_upgrade": a.enemy_upgrade,
            "upgrade_rank": a.upgrade_rank}
    enemies_edits = []
    if a.with_enemies:
        eo = dict(E.DEFAULT_OPTS)
        enemies_edits, _ = E.plan_enemies(t, E.track_rng(a.seed, eo), eo)
    full = dict(opts, enemies_edits=enemies_edits)
    edits, lines = plan_weapons(t, sub_rng(a.seed, opts), full)
    guards = check_weapons(t, edits, full)
    chain = enemies_edits + [e for e in edits if e["table"] == "DisposUnit"]
    files = edits_to_files(t.f, [e for e in edits if e["table"] == "Item"] + chain, t.dispos)
    name = f"Randomizer weapons {R.check_seed(a.seed)}"
    files["mod.json"] = (json.dumps({"name": name, "description": f"Track 'weapons' ({TOOL_VERSION}) alone, seed "
                                     f"{a.seed}: {opts_text(norm_opts(opts))}.",
                                     "enabled": True, "order": 100, "override": False,
                                     "randomizer": {"weapons": {"tool": TOOL_VERSION, "opts": opts}}},
                                    indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    gl = ["", "Weapons guards:"] + [f"  {'PASS' if v['ok'] else 'FAIL'} {k}" + "".join(f"\n       {d}" for d in v["detail"][:8])
                                    for k, v in guards.items()]
    files["spoiler.txt"] = ("\n".join(lines + gl) + "\n").encode("utf-8")
    out = os.path.join(os.path.abspath(a.out), name.replace(" ", "_"))
    R.write_mod(files, out)
    print(f"made {out}: {len(edits)} edits")
    for k, v in guards.items():
        print(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
    return 0 if all(v["ok"] for v in guards.values()) else 2


def _onoff(v: str) -> bool:
    v = v.strip().lower()
    if v in ("on", "yes", "1", "true"):
        return True
    if v in ("off", "no", "0", "false"):
        return False
    raise ValueError("on or off")


def main(argv=None) -> int:
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make", help="this track alone as one mod folder (inspection)")
    p.add_argument("--seed", required=True)
    p.add_argument("--stats", type=_onoff, default=False)
    p.add_argument("--traits", type=int, default=0, help="chance 0-100")
    p.add_argument("--wild-traits", dest="wild_traits", type=_onoff, default=False)
    p.add_argument("--enemy-upgrade", dest="enemy_upgrade", type=int, default=0, help="chance 0-100")
    p.add_argument("--upgrade-rank", dest="upgrade_rank", choices=UPGRADE_MODES, default="same")
    p.add_argument("--with-enemies", dest="with_enemies", type=_onoff, default=False,
                   help="apply the enemies track's default gear plan first")
    p.add_argument("--out", default=os.path.join(ROOT, "build", "rando_weapons", "out"))
    a = ap.parse_args(argv)
    try:
        return cmd_make(a)
    except R.RandoError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
