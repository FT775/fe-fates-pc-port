"""Read-modify-write of one route's own key in the shared config files (round 8, area split).
Only bt-* / cq-* / rv-* / opt-* keys are added or changed (round 13: bt- and opt- too, so Birthright and options
helpers stop hand-editing routes.json); every other key stays as it was (the file is re-read right before the
write and written in its own style: json indent 1, UTF-8, LF). title, new-game and cheat-* keys are never written
here.
usage: splitcfg.py route NAME JSONFILE      (routes.json "routes"[NAME] = the object in JSONFILE)
       splitcfg.py marks NAME JSONFILE      (markers.json "checkpoints"[NAME] = the object in JSONFILE)
       splitcfg.py --selftest               the merge and its check on made-up files (no shared file touched)
Round 9: the bare assert became a real check (it also ran away under python -O): before the write, every top-level
key other than the section, and every other key of the section, must be unchanged, and NAME must hold exactly the
new object; otherwise nothing is written (exit 1)."""
import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
FILES = {"route": ("config/harness/routes.json", "routes"), "marks": ("config/harness/markers.json", "checkpoints")}
OWN_PREFIXES = ("bt-", "cq-", "rv-", "opt-")


def own_key(name: str) -> bool:
    """A key this tool may write: a bt-/cq-/rv-/opt- route name of letters, digits and - _ . after the prefix."""
    return (isinstance(name, str) and name.startswith(OWN_PREFIXES) and len(name) <= 64
            and all(c.isascii() and (c.isalnum() or c in "-_.") for c in name)
            and not name.endswith(OWN_PREFIXES) and ".." not in name)


class Refused(Exception):
    pass


def canon(v) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def check_only_name_changed(before: dict, after: dict, section: str, name: str, obj) -> None:
    """Raises Refused unless after = before with only section[name] set to obj."""
    if not isinstance(after, dict) or not isinstance(after.get(section), dict):
        raise Refused(f"the written text has no {section!r} object")
    tops = set(before) | set(after)
    for k in sorted(tops):
        if k == section:
            continue
        if k not in before or k not in after or canon(before[k]) != canon(after[k]):
            raise Refused(f"top-level key {k!r} would change")
    old, new = before[section], after[section]
    for k in sorted(set(old) | set(new)):
        if k == name:
            continue
        if k not in old or k not in new or canon(old[k]) != canon(new[k]):
            raise Refused(f"{section}[{k!r}] would change")
    if name not in new or canon(new[name]) != canon(obj):
        raise Refused(f"{section}[{name!r}] is not the new object after the write")


def merge(raw: str, section: str, name: str, obj) -> str:
    """The new file text: raw with section[name] = obj, checked (Refused when anything else would change)."""
    before = json.loads(raw)
    if not isinstance(before.get(section), dict):
        raise Refused(f"no {section!r} object in the file")
    d = json.loads(raw)
    d[section][name] = obj
    out = json.dumps(d, indent=1, ensure_ascii=False) + ("\n" if raw.endswith("\n") else "")
    check_only_name_changed(before, json.loads(out), section, name, obj)
    return out


def write(path: str, text: str) -> None:
    tmp = path + ".splitcfg-tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def main(argv: list[str]) -> int:
    kind, name, src = argv[:3]
    if kind not in FILES:
        print(f"unknown file {kind!r}: route or marks")
        return 2
    if not own_key(name):
        print(f"{name!r}: only {' / '.join(p + '*' for p in OWN_PREFIXES)} keys are written here (letters, digits, - _ .)")
        return 1
    path, section = FILES[kind]
    path = os.path.join(ROOT, path)
    with open(src, encoding="utf-8") as fh:
        obj = json.load(fh)
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    try:
        out = merge(raw, section, name, obj)
    except Refused as e:
        print(f"{os.path.relpath(path, ROOT)}: NOT written: {e}")
        return 1
    write(path, out)
    others = len(json.loads(raw)[section]) - (name in json.loads(raw)[section])
    print(f"{os.path.relpath(path, ROOT)}: {section}[{name}] written; {others} other keys unchanged")
    return 0


def selftest() -> int:
    fails, n = [], 0

    def ok(cond, what):
        nonlocal n
        n += 1
        print(f"  {'ok  ' if cond else 'FAIL'} {what}")
        if not cond:
            fails.append(what)

    raw = json.dumps({"_about": "x", "version": 2, "routes": {"bt-ch1": {"save": "a"}, "cq-ch7": {"save": "b"}}},
                     indent=1) + "\n"
    out = merge(raw, "routes", "cq-ch8", {"save": "c"})
    d = json.loads(out)
    ok(d["routes"]["cq-ch8"] == {"save": "c"} and d["routes"]["bt-ch1"] == {"save": "a"} and d["version"] == 2
       and out.endswith("\n"), "a new key added, the others kept")
    ok(json.loads(merge(raw, "routes", "cq-ch7", {"save": "z"}))["routes"]["cq-ch7"] == {"save": "z"}, "a key replaced")
    before = json.loads(raw)
    for what, after in (
            ("a top-level key changed", dict(json.loads(out), version=3)),
            ("a top-level key removed", {k: v for k, v in json.loads(out).items() if k != "_about"}),
            ("a top-level key added", dict(json.loads(out), extra=1)),
            ("another route changed", json.loads(out.replace('"a"', '"A"'))),
            ("another route removed", {**json.loads(out), "routes": {"cq-ch8": {"save": "c"}, "cq-ch7": {"save": "b"}}}),
            ("the new key not written", before),
            ("the section not an object", dict(before, routes=[]))):
        try:
            check_only_name_changed(before, after, "routes", "cq-ch8", {"save": "c"})
            ok(False, f"refused: {what}")
        except Refused:
            ok(True, f"refused: {what}")
    try:
        merge(json.dumps({"checkpoints": {}}), "routes", "cq-x", {})
        ok(False, "refused: a file without the section")
    except Refused:
        ok(True, "refused: a file without the section")
    # round 13: bt- and opt- keys take the same checked merge; other names are still refused
    d = json.loads(merge(raw, "routes", "bt-ch25", {"save": "d"}))
    ok(d["routes"]["bt-ch25"] == {"save": "d"} and d["routes"]["cq-ch7"] == {"save": "b"}, "a bt- key added")
    ok(json.loads(merge(raw, "routes", "bt-ch1", {"save": "e"}))["routes"]["bt-ch1"] == {"save": "e"}, "a bt- key replaced")
    ok(all(own_key(n) for n in ("bt-ch25", "cq-ch13", "rv-ch18", "opt-ch8-set", "bt-ch8-pair")), "own keys accepted")
    ok(not any(own_key(n) for n in ("title", "new-game", "cheat-family", "bt-", "opt-", "bt-a/b", "bt-..", "xbt-ch1",
                                    "bt-ch1 ", "bt-" + "x" * 70, "")), "other names refused")
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "o.json")
        with open(src, "w", encoding="utf-8") as fh:
            json.dump({"save": "x"}, fh)
        ok(main(["route", "cheat-family", src]) == 1 and main(["route", "title", src]) == 1,
           "main refuses a key outside bt-/cq-/rv-/opt- (nothing read or written)")
    print(f"splitcfg selftest: {n - len(fails)}/{n} ok")
    return 1 if fails else 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--selftest"]:
        sys.exit(selftest())
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
