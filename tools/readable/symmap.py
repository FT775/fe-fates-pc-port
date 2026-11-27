#!/usr/bin/env python3
"""Read the debug symbol map that ships in this game's RomFS (Fates: debug/name.StackTrace
+ debug/addr.StackTrace; the paths come from config/game.json romfs.symbol_map).

name.StackTrace is a blob of NUL-terminated demangled C++ names; addr.StackTrace is a list
of (u32 address, u32 offset into the name blob) pairs, little-endian. Thumb functions are
NOT marked with bit 0, so the address alone does not tell ARM from Thumb: a 2-aligned
address is certainly Thumb (the RVCT library's __rw::__rw_allocate at 0x0010030E), but a
4-aligned one may be Thumb too (__cxa_guard_acquire at 0x00302C6C is Thumb). Ask the code
analysis (build/cache/analysis.json code ranges) for the mode. Entries with address 0 are
padding and skipped.

Function NAMES and addresses are labels (allowed in tracked files by the repo rules);
nothing else from the map is written anywhere by this module.

    python tools/readable/symmap.py stats          counts, scopes, Thumb entries
    python tools/readable/symmap.py find REGEX     address + name of every match
    python tools/readable/symmap.py at 0xADDR      the name at (or containing) an address
    python tools/readable/symmap.py --selftest     parser on a made-up map
"""
from __future__ import annotations

import bisect
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "tools"))  # gamecfg (appended, never shadowing a same-named tool)


def strip_params(name: str) -> str:
    """Drop the trailing '(...)' (and anything after it, e.g. const), respecting <...>."""
    depth = 0
    for i, ch in enumerate(name):
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "(" and depth == 0 and i > 0:
            # 'operator()' itself: the first '(' belongs to the operator name
            if name[:i].endswith("operator") and name[i:i + 2] == "()":
                continue
            return name[:i]
    return name


def split_scope(q: str) -> list[str]:
    parts, depth, cur, i = [], 0, "", 0
    while i < len(q):
        ch = q[i]
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if depth == 0 and q.startswith("::", i):
            parts.append(cur)
            cur = ""
            i += 2
            continue
        cur += ch
        i += 1
    parts.append(cur)
    return parts


@dataclass(frozen=True)
class Sym:
    addr: int
    name: str            # demangled, e.g. "Unit::GetStr() const"

    @property
    def thumb(self) -> bool:
        """True only when the address proves it (2-aligned); False means 'unknown'."""
        return bool(self.addr & 2) and not self.addr & 1

    @property
    def qualified(self) -> str:
        """Name without the parameter list: 'Unit::GetStr'."""
        return strip_params(self.name)

    @property
    def cls(self) -> str:
        """Enclosing scope ('Unit', 'nn::fs', '' for free functions)."""
        return "::".join(split_scope(self.qualified)[:-1])

    @property
    def method(self) -> str:
        return split_scope(self.qualified)[-1]

    @property
    def params(self) -> str:
        q = self.qualified
        return self.name[len(q):]


def parse(names: bytes, addrs: bytes) -> list[Sym]:
    if len(addrs) % 8:
        raise ValueError(f"addr file size {len(addrs)} is not a multiple of 8")
    out = []
    for i in range(0, len(addrs), 8):
        a, off = struct.unpack_from("<II", addrs, i)
        if a == 0:
            continue
        if off >= len(names):
            raise ValueError(f"entry {i // 8}: name offset {off:#x} outside the name blob")
        end = names.find(b"\0", off)
        out.append(Sym(a, names[off: end if end >= 0 else len(names)].decode("utf-8", "replace")))
    out.sort(key=lambda s: s.addr)
    return out


def default_paths() -> tuple[Path, Path]:
    from gamecfg import GAME
    sm = GAME.raw["romfs"]["symbol_map"]
    base = ROOT / "extracted" / "romfs"
    return base / sm["names"], base / sm["addrs"]


_CACHE: list[Sym] | None = None


def available() -> bool:
    try:
        return all(p.is_file() for p in default_paths())
    except (KeyError, FileNotFoundError):
        return False


def load() -> list[Sym]:
    """All symbols, sorted by address (cached per process)."""
    global _CACHE
    if _CACHE is None:
        n, a = default_paths()
        if not n.is_file() or not a.is_file():
            raise FileNotFoundError(f"symbol map not found ({n}, {a}): extract the ROM first")
        _CACHE = parse(n.read_bytes(), a.read_bytes())
    return _CACHE


def by_addr(syms: list[Sym] | None = None) -> dict[int, str]:
    out: dict[int, str] = {}
    for s in syms if syms is not None else load():
        out.setdefault(s.addr, s.name)
    return out


def containing(addr: int, syms: list[Sym] | None = None) -> Sym | None:
    syms = syms if syms is not None else load()
    keys = [s.addr for s in syms]
    i = bisect.bisect_right(keys, addr) - 1
    return syms[i] if i >= 0 else None


def find(pattern: str, syms: list[Sym] | None = None) -> list[Sym]:
    rx = re.compile(pattern)
    return [s for s in (syms if syms is not None else load()) if rx.search(s.name)]


def unique(name: str, syms: list[Sym] | None = None) -> int:
    """Address of the one symbol whose full name equals `name` exactly, else LookupError.
    Used to resolve per-game addresses by name (config/readable/addresses.json)."""
    hits = sorted({s.addr for s in (syms if syms is not None else load()) if s.name == name})
    if len(hits) != 1:
        raise LookupError(f"{name!r}: {len(hits)} matches in the symbol map")
    return hits[0]


C_IDENT = re.compile(r"[^A-Za-z0-9_]+")


def c_name(sym: Sym) -> str:
    """A C identifier from a demangled name: 'Unit::GetStr() const' -> 'Unit__GetStr'.
    Template arguments and operators are flattened; callers add _XXXXXXXX on collisions."""
    q = sym.qualified.replace("::", "__").replace("operator", "op")
    q = C_IDENT.sub("_", q)
    q = re.sub(r"_{3,}", "__", q).strip("_")
    if not q or q[0].isdigit():
        q = "f_" + q
    return q


# ----------------------------------------------------------------------------- selftest
def selftest() -> int:
    fails = 0

    def check(cond, what):
        nonlocal fails
        fails += not cond
        print(f"  {'ok  ' if cond else 'FAIL'} {what}")

    names = (b"Unit::GetStr() const\0nn::fs::Open(const char*,int)\0"
             b"std::vector<int, A<B> >::push_back(const int&)\0operator new(unsigned int)\0free_fn\0"
             b"X::operator()(int)\0")
    offs = [names.index(t) for t in (b"Unit", b"nn::", b"std::", b"operator new", b"free_fn", b"X::")]
    addrs = struct.pack("<8I", 0x00100010, offs[0], 0x00100002, offs[1], 0x00100100, offs[2], 0, 0) + \
        struct.pack("<6I", 0x00100200, offs[3], 0x00100300, offs[4], 0x00100400, offs[5])
    syms = parse(names, addrs)
    check(len(syms) == 6 and syms[0].addr == 0x00100002, "sorted, address-0 padding skipped")
    check(syms[0].thumb and not syms[1].thumb, "2-aligned entry is Thumb")
    u = next(s for s in syms if s.addr == 0x00100010)
    check(u.qualified == "Unit::GetStr" and u.cls == "Unit" and u.method == "GetStr"
          and u.params == "() const", f"Unit::GetStr split ({u.cls!r}, {u.method!r}, {u.params!r})")
    v = next(s for s in syms if s.addr == 0x00100100)
    check(v.cls == "std::vector<int, A<B> >" and v.method == "push_back", f"template scope ({v.cls!r})")
    o = next(s for s in syms if s.addr == 0x00100200)
    check(o.qualified == "operator new" and c_name(o) == "op_new", f"operator name ({o.qualified!r}, {c_name(o)!r})")
    x = next(s for s in syms if s.addr == 0x00100400)
    check(x.qualified == "X::operator()" and x.method == "operator()", f"operator() ({x.qualified!r})")
    check(c_name(u) == "Unit__GetStr" and c_name(v) == "std__vector_int_A_B__push_back", f"c_name ({c_name(v)})")
    check(containing(0x00100150, syms).addr == 0x00100100, "containing")
    check(unique("free_fn", syms) == 0x00100300, "unique by exact name")
    for what, fn in (("unique raises on no match", lambda: unique("nothing", syms)),
                     ("bad addr size refused", lambda: parse(names, b"\0" * 7)),
                     ("name offset past the blob refused", lambda: parse(names, struct.pack("<II", 4, 10 ** 6)))):
        try:
            fn()
            check(False, what)
        except (LookupError, ValueError):
            check(True, what)
    print(f"symmap selftest: {'OK' if not fails else f'{fails} failure(s)'}")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    if not argv or argv[0] == "stats":
        syms = load()
        thumb = sum(s.thumb for s in syms)
        scopes = {s.cls for s in syms if s.cls}
        print(f"{len(syms)} symbols, {len(by_addr(syms))} distinct addresses, {thumb} certainly Thumb (2-aligned), {len(scopes)} scopes")
        return 0
    if argv[0] == "find" and len(argv) == 2:
        for s in find(argv[1]):
            print(f"0x{s.addr:08X} {s.name}")
        return 0
    if argv[0] == "at" and len(argv) == 2:
        s = containing(int(argv[1], 16))
        print(f"0x{s.addr:08X} {s.name}" if s else "-")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
