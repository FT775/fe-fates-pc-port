#!/usr/bin/env python3
"""M2: sort-order class-membership inference for non-virtual game functions.

Writes
  config/naming/class_members.csv     func_addr,class,typeinfo_addr,confidence,evidence
  docs/analysis/M2_class_inference.md coverage numbers, method, failure cases
Scratch (not tracked): build/m2_members/  (runs.txt, gaps.csv, holdout.txt)

Inputs: config/naming/{classes,vfuncs,ctors,library}.csv, build/cache/analysis.json,
extracted/text.bin. Python 3 stdlib only; deterministic.

Idea: inside a lexically sorted stretch of .text, every function section is ordered by
its mangled name. A member of class C with nested-name prefix P is named _ZN<P>... (or
_ZNK<P>... if const). If two consecutive on-sequence anchors both belong to C, every
name between them starts with the same _ZN<P> (or _ZNK<P>), so every function between
them is a member of C, or of a type nested in C.

Steps
  1. Anchors: vfuncs.csv functions (key = owner_class, the slot owner) and ctors.csv
     ctor/dtor/deleting_dtor rows (never vtable_writer rows: those only do `new X`).
     Sort key = class prefix P (typeinfo string without the N...E wrapper).
  2. Sort verification (own code): a segmented longest-non-decreasing-subsequence DP
     over the address-ordered anchors (cost 1 per dropped anchor, LAMBDA per new run).
     Runs with >= MIN_RUN kept anchors and <= MAX_DROP dropped share are "verified".
     Dropped anchors are off-sequence and are not used as anchors.
  3. Rules, applied only inside verified runs and only to functions whose library tag
     is game (or unknown, capped at medium):
       same_class   consecutive kept anchors of the same class -> high
                    (medium if the gap holds library code, an off-sequence anchor of
                    another class, a non-funcmap anchor, or the local sort is weak)
       scope        consecutive kept anchors of different classes whose prefixes share
                    an enclosing class E (E is one of them -> medium, E encloses both
                    -> low); the function is in E's scope (E or a type nested in E)
       edge_calls   other different-class gaps: BL links to known members of A (or B)
                    and none of the other class vote; the sort spreads a vote to the
                    whole gap prefix (A tail) or suffix (B head) -> low
     (A D1-after-D0 rule was tried and dropped: no deleting dtor BL-calls the next
     function; D1 is inlined into D0.)
  4. Holdout: 5-fold test that re-runs the DP without the held-out anchors and checks
     the rules' predictions for them.
"""
import sys as _sys  # noqa: E402
if "--awakening-pass" not in _sys.argv:  # Fates: names come from the shipped symbol map
    _sys.exit("tools/m2/class_members.py is the Awakening RTTI/heuristic naming pass and still holds "
              "Awakening addresses; it would write wrong rows for Fates. Fates names come "
              "from the shipped symbol map: python tools/fates/symbols.py (docs/SYMBOLS.md).")
import bisect
import collections
import csv
import hashlib
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAMING = os.path.join(ROOT, 'config', 'naming')
OUT_CSV = os.path.join(NAMING, 'class_members.csv')
OUT_MD = os.path.join(ROOT, 'docs', 'analysis', 'M2_class_inference.md')
SCRATCH = os.path.join(ROOT, 'build', 'm2_members')
TEXT_BASE = 0x00100000

LAMBDA = 3          # DP cost of starting a new sorted run
WINDOW = 60         # DP look-back (max consecutive dropped anchors)
MIN_RUN = 30        # kept anchors for a run to count as verified
MAX_DROP = 0.10     # max dropped share inside a verified run's span
LOCAL_RADIUS = 8    # anchors on each side for the local sort check
LOCAL_MAX_DROP = 0.30
RUN_EDGE = 2        # pairs this close to a run end are capped at medium
FOLDS = 5


def hx(a):
    return '0x%08X' % a


def read_csv(name):
    with open(os.path.join(NAMING, name), encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def prefix_of(ts):
    """Nested-name prefix P of a typeinfo string: members are _ZN<P>... / _ZNK<P>..."""
    return ts[1:-1] if ts.startswith('N') and ts.endswith('E') else ts


# ---------------------------------------------------------------- load inputs
def load():
    classes = {r['typeinfo_addr']: r for r in read_csv('classes.csv')}
    name2ti = collections.defaultdict(set)
    for ti, r in classes.items():
        name2ti[r['class']].add(ti)
    vfuncs = read_csv('vfuncs.csv')
    ctors = read_csv('ctors.csv')
    library = {int(r['func_addr'], 16): r for r in read_csv('library.csv')}
    with open(os.path.join(ROOT, 'build', 'cache', 'analysis.json'), encoding='utf-8') as f:
        funcs = sorted(json.load(f)['funcs'])
    with open(os.path.join(ROOT, 'extracted', 'text.bin'), 'rb') as f:
        text = f.read()
    return classes, name2ti, vfuncs, ctors, library, funcs, text


def build_anchors(classes, name2ti, vfuncs, ctors):
    """addr -> dict(ti, kind, strong). One class per function (vfuncs win)."""
    anchors = {}
    skipped_ambiguous = 0
    for r in vfuncs:
        f = int(r['func_addr'], 16)
        owner = r['owner_class']
        tis = name2ti.get(owner, set())
        if len(tis) == 1:
            ti = next(iter(tis))
        elif owner == r['class']:
            ti = r['typeinfo_addr']
        else:
            # repeated anonymous-namespace owner name, resolve via the row's class chain
            cands = sorted(t for t in tis if t == r['typeinfo_addr'])
            if not cands:
                skipped_ambiguous += 1
                continue
            ti = cands[0]
        prev = anchors.get(f)
        if prev is not None and prev['ti'] != ti:
            # same function with two owners should not happen; keep the first, mark weak
            prev['strong'] = False
            continue
        anchors[f] = {'ti': ti, 'kind': 'vfunc', 'strong': r['n_classes_sharing'] == '1',
                      'slot': r['slot']}
    for r in ctors:
        if r['kind'] == 'vtable_writer' or r['confidence'] == 'low':
            continue
        f = int(r['func_addr'], 16)
        if f in anchors:
            if r['kind'] in ('deleting_dtor', 'dtor'):
                anchors[f]['dtor'] = r['kind']
            continue
        anchors[f] = {'ti': r['typeinfo_addr'], 'kind': r['kind'], 'strong': True,
                      'dtor': r['kind'] if r['kind'] in ('deleting_dtor', 'dtor') else None}
    for a in anchors.values():
        a['key'] = prefix_of(classes[a['ti']]['ts_mangled'])
    return anchors, skipped_ambiguous


# ---------------------------------------------------------------- sort check
def segment(seq_keys):
    """Segmented longest non-decreasing subsequence.

    Returns (kept index list, run id per kept index)."""
    n = len(seq_keys)
    if n == 0:
        return [], {}
    dp = [0] * n
    bp = [-1] * n
    newrun = [True] * n
    for i in range(n):
        best = i + LAMBDA
        bj = -1
        nr = True
        ki = seq_keys[i]
        for j in range(max(0, i - WINDOW), i):
            c = dp[j] + (i - j - 1)
            if seq_keys[j] <= ki:
                if c < best:
                    best, bj, nr = c, j, False
            elif c + LAMBDA < best:
                best, bj, nr = c + LAMBDA, j, True
        dp[i], bp[i], newrun[i] = best, bj, nr
    end = min(range(n), key=lambda i: (dp[i] + (n - 1 - i), i))
    kept = []
    i = end
    while i != -1:
        kept.append(i)
        i = bp[i]
    kept.reverse()
    run_of = {}
    rid = -1
    for idx, i in enumerate(kept):
        if idx == 0 or newrun[i]:
            rid += 1
        run_of[i] = rid
    return kept, run_of


def make_runs(addrs, keys):
    kept, run_of = segment(keys)
    keptset = set(kept)
    runs = collections.defaultdict(list)
    for i in kept:
        runs[run_of[i]].append(i)
    out = []
    for rid in sorted(runs):
        idx = runs[rid]
        lo, hi = idx[0], idx[-1]
        drops = sum(1 for i in range(lo, hi + 1) if i not in keptset)
        share = drops / (hi - lo + 1)
        out.append({'id': rid, 'idx': idx, 'lo': addrs[lo], 'hi': addrs[hi],
                    'kept': len(idx), 'drops': drops, 'drop_share': share,
                    'verified': len(idx) >= MIN_RUN and share <= MAX_DROP,
                    'first_key': keys[lo], 'last_key': keys[hi]})
    return kept, keptset, out


# ---------------------------------------------------------------- helpers
def bl_targets(text, start, end):
    out = set()
    for a in range(start, end, 4):
        o = a - TEXT_BASE
        if o < 0 or o + 4 > len(text):
            break
        w = struct.unpack_from('<I', text, o)[0]
        if (w & 0xFF000000) == 0xEB000000:
            imm = w & 0x00FFFFFF
            if imm & 0x800000:
                imm -= 0x1000000
            out.add((a + 8 + (imm << 2)) & 0xFFFFFFFF)
    return out


class ScopeIndex:
    def __init__(self, classes):
        self.by_key = collections.defaultdict(list)
        for ti, r in classes.items():
            self.by_key[prefix_of(r['ts_mangled'])].append(ti)
        self.keys = set(self.by_key)

    @staticmethod
    def is_comp_prefix(e, k):
        return k == e or (k.startswith(e) and k[len(e)].isdigit())

    def class_prefixes(self, k):
        """All class keys that are component prefixes of k (k itself included)."""
        out = []
        for cut in range(1, len(k) + 1):
            e = k[:cut]
            if e in self.keys and self.is_comp_prefix(e, k):
                out.append(e)
        return out

    def common(self, ka, kb):
        pa = set(self.class_prefixes(ka))
        best = None
        for e in self.class_prefixes(kb):
            if e in pa and (best is None or len(e) > len(best)):
                best = e
        if best is None:
            return None
        tis = sorted(self.by_key[best])
        return best, tis


# ---------------------------------------------------------------- inference
def infer(anchors, library, funcs, text, classes, scope, graph, use_addrs=None,
          record=True):
    """Run the DP and rules. Returns (assignments, info)."""
    addrs = sorted(use_addrs if use_addrs is not None else anchors)
    keys = [anchors[a]['key'] for a in addrs]
    kept, keptset, runs = make_runs(addrs, keys)
    dropped = [addrs[i] for i in range(len(addrs)) if i not in keptset]
    func_next = {f: (funcs[i + 1] if i + 1 < len(funcs) else 0x00459B88)
                 for i, f in enumerate(funcs)}
    funcset = set(funcs)
    nonfm_anchors = sorted(a for a in addrs if a not in funcset)
    all_anchor_addrs = sorted(anchors)

    def funcs_between(lo, hi):
        i = bisect.bisect_right(funcs, lo)
        j = bisect.bisect_left(funcs, hi)
        return funcs[i:j]

    def contains_nonfm(f):
        e = func_next[f]
        i = bisect.bisect_right(nonfm_anchors, f)
        return i < len(nonfm_anchors) and nonfm_anchors[i] < e

    assign = {}      # func -> (ti, conf, evidence, rule)
    gaps = []        # scratch rows
    edge_gaps = []   # different-class gaps left for the call-vote pass
    stats = collections.Counter()

    def put(f, ti, conf, ev, rule):
        old = assign.get(f)
        rank = {'high': 3, 'medium': 2, 'low': 1}
        if old is None or rank[conf] > rank[old[1]]:
            assign[f] = (ti, conf, ev, rule)

    for run in runs:
        if not run['verified']:
            continue
        idx = run['idx']
        for p in range(len(idx) - 1):
            ia, ib = idx[p], idx[p + 1]
            a, b = addrs[ia], addrs[ib]
            A, B = anchors[a], anchors[b]
            inner = funcs_between(a, b)
            # anchors (kept or dropped) strictly inside the gap
            lo_i = bisect.bisect_right(all_anchor_addrs, a)
            hi_i = bisect.bisect_left(all_anchor_addrs, b)
            inner_anchor = set(all_anchor_addrs[lo_i:hi_i])
            offseq_other = [x for x in inner_anchor
                            if anchors[x]['ti'] != A['ti'] or anchors[x]['ti'] != B['ti']]
            libs_in_gap = [f for f in inner if f not in inner_anchor and
                           library.get(f, {}).get('library') not in ('game', 'unknown')]
            # local sort quality around the pair
            lo = max(0, ia - LOCAL_RADIUS * 2)
            hi = min(len(addrs) - 1, ib + LOCAL_RADIUS * 2)
            window = range(lo, hi + 1)
            local_drop = sum(1 for i in window if i not in keptset) / len(window)
            cands = [f for f in inner if f not in inner_anchor]
            if A['ti'] == B['ti']:
                rule = 'same_class'
                base = 'high'
                flags = []
                if libs_in_gap:
                    flags.append('lib_in_gap')
                if offseq_other:
                    flags.append('offseq_in_gap')
                if local_drop > LOCAL_MAX_DROP:
                    flags.append('local_unsorted')
                if p < RUN_EDGE or p + 1 > len(idx) - 1 - RUN_EDGE:
                    flags.append('run_edge')
                if flags:
                    base = 'medium'
                for f in cands:
                    lib = library.get(f, {}).get('library')
                    if lib not in ('game', 'unknown'):
                        stats['skip_lib_same_class'] += 1
                        continue
                    conf = base
                    fl = list(flags)
                    if lib == 'unknown':
                        conf = 'medium' if conf == 'high' else conf
                        fl.append('lib_unknown')
                    if contains_nonfm(f):
                        conf = 'medium' if conf == 'high' else conf
                        fl.append('holds_slot_func')
                    ev = 'between_class_anchors:%s-%s' % (hx(a), hx(b))
                    if fl:
                        ev += '+' + '+'.join(fl)
                    put(f, A['ti'], conf, ev, rule)
                if record:
                    gaps.append((a, b, rule, A['ti'], len(cands), len(libs_in_gap),
                                 len(offseq_other), round(local_drop, 2)))
            else:
                common = scope.common(A['key'], B['key'])
                if common is None or len(common[1]) != 1 or not cands:
                    if cands:
                        edge_gaps.append((a, b, inner, inner_anchor, local_drop))
                    if record:
                        gaps.append((a, b, 'none', '', len(cands), len(libs_in_gap),
                                     len(offseq_other), round(local_drop, 2)))
                    continue
                ekey, etis = common
                eti = etis[0]
                rule = 'scope'
                conf = 'medium' if ekey in (A['key'], B['key']) else 'low'
                flags = []
                if libs_in_gap:
                    flags.append('lib_in_gap')
                    conf = 'low'
                if local_drop > LOCAL_MAX_DROP:
                    flags.append('local_unsorted')
                    conf = 'low'
                for f in cands:
                    lib = library.get(f, {}).get('library')
                    if lib not in ('game', 'unknown'):
                        continue
                    c = conf
                    fl = list(flags)
                    if lib == 'unknown':
                        c = 'low' if c == 'medium' else c
                        fl.append('lib_unknown')
                    tag = 'enclosing' if ekey in (A['key'], B['key']) else 'common_outer'
                    ev = 'scope_%s:%s-%s' % (tag, hx(a), hx(b))
                    if fl:
                        ev += '+' + '+'.join(fl)
                    put(f, eti, c, ev, rule)
                if record:
                    gaps.append((a, b, 'scope', eti, len(cands), len(libs_in_gap),
                                 len(offseq_other), round(local_drop, 2)))
    edge_pass(anchors, library, assign, edge_gaps, graph, stats, put)
    # anchors themselves are never output rows
    for a in anchors:
        assign.pop(a, None)
    info = {'runs': runs, 'kept': kept, 'dropped': dropped, 'addrs': addrs,
            'keys': keys, 'gaps': gaps, 'stats': stats}
    return assign, info


def call_graph(funcs, text):
    """BL edges between funcmap functions: (callers, callees) dicts of sets."""
    funcset = set(funcs)
    callees = {}
    callers = collections.defaultdict(set)
    for i, f in enumerate(funcs):
        end = funcs[i + 1] if i + 1 < len(funcs) else TEXT_BASE + len(text)
        ts = {t for t in bl_targets(text, f, end) if t in funcset and t != f}
        callees[f] = ts
        for t in ts:
            callers[t].add(f)
    return callers, callees


def edge_pass(anchors, library, assign, edge_gaps, graph, stats, put):
    """Low tier for gaps between anchors of different classes A < B.

    A function in the gap linked by BL (either way) to known members of A and none of
    B votes A (and the reverse for B). The sort then forces every function between A's
    last anchor and the furthest A-voted function to be in A's scope too (same argument
    as same_class), so the A tail is the gap prefix up to the last A vote, provided no
    B-only vote, library function or other anchor comes first. The B head is the mirror
    image. A tail is not grown after a destructor anchor (dtors sort last in a class).
    Votes use anchors and same_class rows only (no chaining between edge rows)."""
    callers, callees = graph
    known = {a: v['ti'] for a, v in anchors.items()}
    for f, v in assign.items():
        if v[3] == 'same_class':
            known[f] = v[0]

    def ok_lib(f):
        return library.get(f, {}).get('library') in ('game', 'unknown')

    def vote(f, ta, tb):
        linked = callers.get(f, set()) | callees.get(f, set())
        va = sorted(x for x in linked if known.get(x) == ta)
        vb = sorted(x for x in linked if known.get(x) == tb)
        return va, vb

    for a, b, inner, inner_anchor, local_drop in edge_gaps:
        A, B = anchors[a], anchors[b]
        ta, tb = A['ti'], B['ti']
        tail_end, tail_voter = -1, None
        if not A.get('dtor'):
            for k, f in enumerate(inner):
                if f in inner_anchor or not ok_lib(f):
                    break
                va, vb = vote(f, ta, tb)
                if vb and not va:
                    break
                if va and not vb:
                    tail_end, tail_voter = k, f
        head_start, head_voter = len(inner), None
        for k in range(len(inner) - 1, -1, -1):
            f = inner[k]
            if f in inner_anchor or not ok_lib(f):
                break
            va, vb = vote(f, ta, tb)
            if va and not vb:
                break
            if vb and not va:
                head_start, head_voter = k, f
        if head_start <= tail_end:
            stats['edge_conflict'] += 1
            continue
        flag = '+local_unsorted' if local_drop > LOCAL_MAX_DROP else ''
        for k in range(tail_end + 1):
            f = inner[k]
            ev = 'edge_tail_calls:%s>%s%s' % (hx(a), hx(tail_voter), flag)
            if library[f]['library'] == 'unknown':
                ev += '+lib_unknown'
            put(f, ta, 'low', ev, 'edge_calls')
            stats['edge_tail'] += 1
        for k in range(head_start, len(inner)):
            f = inner[k]
            ev = 'edge_head_calls:%s<%s%s' % (hx(b), hx(head_voter), flag)
            if library[f]['library'] == 'unknown':
                ev += '+lib_unknown'
            put(f, tb, 'low', ev, 'edge_calls')
            stats['edge_head'] += 1


def vote_check(anchors, assign, graph):
    """Call locality on known members: for high same_class rows, how often do the
    anchors BL-linked to the function belong to the function's own class?"""
    callers, callees = graph
    known = {a: v['ti'] for a, v in anchors.items()}
    res = collections.Counter()
    for f, v in assign.items():
        if v[3] != 'same_class' or v[1] != 'high':
            continue
        linked = (callers.get(f, set()) | callees.get(f, set())) - {f}
        tis = [known[x] for x in linked if x in known]
        if not tis:
            res['no_anchor_link'] += 1
            continue
        res['with_anchor_link'] += 1
        if v[0] in tis:
            res['own_class_linked'] += 1
        if set(tis) == {v[0]}:
            res['only_own_class'] += 1
    return res


# ---------------------------------------------------------------- holdout
def holdout(anchors, library, funcs, text, classes, scope):
    """k-fold: drop a fold of anchors, rebuild runs, predict the held-out anchors."""
    addrs = sorted(anchors)
    fold = {a: int(hashlib.md5(hx(a).encode()).hexdigest(), 16) % FOLDS for a in addrs}
    res = collections.Counter()
    misses = []
    for k in range(FOLDS):
        train = [a for a in addrs if fold[a] != k]
        test = [a for a in addrs if fold[a] == k]
        keys = [anchors[a]['key'] for a in train]
        kept, keptset, runs = make_runs(train, keys)
        # map each verified run's kept anchors
        for run in runs:
            if not run['verified']:
                continue
            idx = run['idx']
            ka = [train[i] for i in idx]
            for t in test:
                if not (ka[0] < t < ka[-1]):
                    continue
                p = bisect.bisect_left(ka, t)
                A, B = anchors[ka[p - 1]], anchors[ka[p]]
                T = anchors[t]
                if A['ti'] == B['ti']:
                    ia, ib = idx[p - 1], idx[p]
                    lo = max(0, ia - LOCAL_RADIUS * 2)
                    hi = min(len(train) - 1, ib + LOCAL_RADIUS * 2)
                    ld = sum(1 for i in range(lo, hi + 1) if i not in keptset) / (hi - lo + 1)
                    edge = p - 1 < RUN_EDGE or p > len(idx) - 1 - RUN_EDGE
                    tier = 'medium' if (ld > LOCAL_MAX_DROP or edge) else 'high'
                    ok = T['ti'] == A['ti']
                    res['same_class_n'] += 1
                    res['same_class_ok'] += ok
                    res['same_class_%s_n' % tier] += 1
                    res['same_class_%s_ok' % tier] += ok
                    if not ok:
                        misses.append((t, 'same_class_' + tier, A['ti'], T['ti']))
                else:
                    c = scope.common(A['key'], B['key'])
                    if c is None or len(c[1]) != 1:
                        res['nogap_rule_n'] += 1
                        continue
                    tag = 'scope_encl' if c[0] in (A['key'], B['key']) else 'scope_outer'
                    ok = ScopeIndex.is_comp_prefix(c[0], T['key'])
                    exact = T['key'] == c[0]
                    res[tag + '_n'] += 1
                    res[tag + '_ok'] += ok
                    res[tag + '_exact'] += exact
                    if not ok:
                        misses.append((t, tag, c[1][0], T['ti']))
    return res, misses


# ---------------------------------------------------------------- main
def main():
    classes, name2ti, vfuncs, ctors, library, funcs, text = load()
    anchors, amb = build_anchors(classes, name2ti, vfuncs, ctors)
    scope = ScopeIndex(classes)
    graph = call_graph(funcs, text)
    assign, info = infer(anchors, library, funcs, text, classes, scope, graph)
    info['vote_check'] = vote_check(anchors, assign, graph)
    ho, misses = holdout(anchors, library, funcs, text, classes, scope)

    os.makedirs(SCRATCH, exist_ok=True)
    rows = []
    for f in sorted(assign):
        ti, conf, ev, rule = assign[f]
        rows.append({'func_addr': hx(f), 'class': classes[ti]['class'],
                     'typeinfo_addr': ti, 'confidence': conf, 'evidence': ev})
    with open(OUT_CSV, 'w', encoding='utf-8', newline='') as fo:
        w = csv.DictWriter(fo, fieldnames=['func_addr', 'class', 'typeinfo_addr',
                                           'confidence', 'evidence'], lineterminator='\n')
        w.writeheader()
        w.writerows(rows)

    runs = info['runs']
    addrs, keys = info['addrs'], info['keys']
    with open(os.path.join(SCRATCH, 'runs.txt'), 'w', encoding='utf-8', newline='\n') as fo:
        for r in runs:
            fo.write('%s-%s kept=%d drops=%d share=%.3f verified=%d %s .. %s\n' % (
                hx(r['lo']), hx(r['hi']), r['kept'], r['drops'], r['drop_share'],
                r['verified'], r['first_key'][:40], r['last_key'][:40]))
        fo.write('\ndropped (off-sequence) anchors:\n')
        for a in info['dropped']:
            A = anchors[a]
            fo.write('%s %s %s\n' % (hx(a), A['kind'], classes[A['ti']]['class']))
    with open(os.path.join(SCRATCH, 'gaps.csv'), 'w', encoding='utf-8', newline='') as fo:
        w = csv.writer(fo, lineterminator='\n')
        w.writerow(['anchor_a', 'anchor_b', 'rule', 'typeinfo', 'n_funcs', 'n_lib',
                    'n_offseq', 'local_drop'])
        for g in info['gaps']:
            w.writerow([hx(g[0]), hx(g[1])] + list(g[2:]))
    with open(os.path.join(SCRATCH, 'holdout.txt'), 'w', encoding='utf-8', newline='\n') as fo:
        for k in sorted(ho):
            fo.write('%s %d\n' % (k, ho[k]))
        for t, rule, pred, act in sorted(misses):
            fo.write('miss %s %s pred=%s actual=%s\n' % (hx(t), rule, classes[pred]['class'],
                                                         classes[act]['class']))

    write_report(classes, anchors, library, funcs, assign, info, ho, misses, amb)
    conf = collections.Counter(r['confidence'] for r in rows)
    print('anchors %d (ambiguous owner skipped %d)' % (len(anchors), amb))
    for r in runs:
        if r['kept'] >= 5:
            print('run %s-%s kept=%d drops=%d verified=%d' % (
                hx(r['lo']), hx(r['hi']), r['kept'], r['drops'], r['verified']))
    print('rows %d %s' % (len(rows), dict(sorted(conf.items()))))
    print('holdout', dict(sorted(ho.items())))


def write_report(classes, anchors, library, funcs, assign, info, ho, misses, amb):
    runs = info['runs']
    ver = [r for r in runs if r['verified']]
    funcset = set(funcs)
    game = [f for f in funcs if library[f]['library'] == 'game']
    unknown = [f for f in funcs if library[f]['library'] == 'unknown']
    anch_game = [f for f in game if f in anchors]

    def in_verified(f):
        return any(r['lo'] <= f <= r['hi'] for r in ver)

    game_in_ver = [f for f in game if in_verified(f)]
    by = collections.Counter()
    by_rule = collections.Counter()
    for f, (ti, conf, ev, rule) in assign.items():
        lib = library[f]['library']
        by[(lib, conf)] += 1
        by_rule[(rule, conf)] += 1
    g_h, g_m, g_l = by[('game', 'high')], by[('game', 'medium')], by[('game', 'low')]
    u_tot = sum(v for (l, c), v in by.items() if l == 'unknown')
    n_game = len(game)
    pct = lambda x, d: '%.1f%%' % (100.0 * x / d) if d else '-'
    classes_hit = len({v[0] for v in assign.values()})
    classes_hit_hm = len({v[0] for v in assign.values() if v[1] != 'low'})

    # unassigned game functions inside verified runs, by why
    why = collections.Counter()
    gap_of = {}
    for g in info['gaps']:
        a, b, rule = g[0], g[1], g[2]
        gap_of[(a, b)] = rule
    kept_addrs = []
    for r in ver:
        kept_addrs.extend(info['addrs'][i] for i in r['idx'])
    kept_addrs.sort()
    for f in game_in_ver:
        if f in anchors or f in assign:
            continue
        p = bisect.bisect_left(kept_addrs, f)
        if p == 0 or p == len(kept_addrs):
            why['outside_anchor_span'] += 1
            continue
        rule = gap_of.get((kept_addrs[p - 1], kept_addrs[p]))
        label = {'none': 'between anchors of unrelated classes, no vote',
                 'same_class': 'same-class gap but skipped',
                 'scope': 'scope gap but skipped'}.get(rule, 'between two runs')
        why[label] += 1
    # K-pass check: classes of run3-like (no dtor) runs that also occur in other runs
    run_cls = []
    for r in ver:
        s = {anchors[info['addrs'][i]]['ti'] for i in r['idx']}
        nd = sum(1 for i in r['idx'] if anchors[info['addrs'][i]].get('dtor'))
        run_cls.append((r, s, nd))
    stats = info['stats']
    gaps_same = [g for g in info['gaps'] if g[2] == 'same_class']
    sizes = sorted(g[4] for g in gaps_same)
    flagged = collections.Counter()
    for g in gaps_same:
        if g[5]:
            flagged['lib_in_gap'] += 1
        if g[6]:
            flagged['offseq_in_gap'] += 1
        if g[7] > LOCAL_MAX_DROP:
            flagged['local_unsorted'] += 1
    lib_gap_funcs = stats['skip_lib_same_class']

    L = []
    w = L.append
    w('# M2 class-membership inference from sort order')
    w('')
    w('Generated by `tools/m2/class_members.py` (re-runnable, stdlib only, deterministic).')
    w('Output: `config/naming/class_members.csv` '
      '(`func_addr,class,typeinfo_addr,confidence,evidence`). Key on `typeinfo_addr`: '
      'anonymous-namespace class names repeat. Anchor functions (vfuncs.csv, ctors.csv) '
      'are not repeated in this file. Scratch: `build/m2_members/` (runs.txt, gaps.csv, '
      'holdout.txt).')
    w('')
    w('## Coverage')
    w('')
    w('| Game functions (library.csv `game`) | Count | Share |')
    w('|---|---|---|')
    w('| total | %d | 100%% |' % n_game)
    w('| already named as anchors (vfuncs/ctors) | %d | %s |' % (len(anch_game), pct(len(anch_game), n_game)))
    w('| inside a verified sorted run | %d | %s |' % (len(game_in_ver), pct(len(game_in_ver), n_game)))
    w('| new class, high | %d | %s |' % (g_h, pct(g_h, n_game)))
    w('| new class, medium | %d | %s |' % (g_m, pct(g_m, n_game)))
    w('| new class, low | %d | %s |' % (g_l, pct(g_l, n_game)))
    w('| new class, any | %d | %s |' % (g_h + g_m + g_l, pct(g_h + g_m + g_l, n_game)))
    w('| anchor or new class (high+medium) | %d | %s |' % (
        len(anch_game) + g_h + g_m, pct(len(anch_game) + g_h + g_m, n_game)))
    w('')
    w('Also %d `unknown`-library functions got a class (capped at medium). Rows by rule:' % u_tot)
    w('')
    w('| Rule | high | medium | low |')
    w('|---|---|---|---|')
    for rule in ('same_class', 'scope', 'edge_calls'):
        w('| %s | %d | %d | %d |' % (rule, by_rule[(rule, 'high')], by_rule[(rule, 'medium')],
                                     by_rule[(rule, 'low')]))
    w('')
    w('%d classes received at least one member (%d at high or medium).' % (classes_hit, classes_hit_hm))
    w('')
    w('## Sorted runs (re-checked here)')
    w('')
    w('Anchors: %d functions (vfuncs.csv keyed by `owner_class`, plus ctors.csv '
      'ctor/dtor/deleting_dtor rows at medium or high; vtable_writer rows excluded). '
      '%d vfunc rows with an ambiguous anonymous owner were skipped. A segmented longest '
      'non-decreasing subsequence DP (cost 1 per dropped anchor, %d per new run) splits '
      'them into runs; it keeps %d and drops %d as off-sequence. A run is verified with '
      '>= %d kept anchors and <= %d%% dropped anchors in its span.' % (
          len(anchors), amb, LAMBDA, len(info['kept']), len(info['dropped']), MIN_RUN,
          int(MAX_DROP * 100)))
    w('')
    w('| Span | Kept | Dropped | Verified | dtor anchors | First key .. last key |')
    w('|---|---|---|---|---|---|')
    for r in runs:
        nd = sum(1 for i in r['idx'] if anchors[info['addrs'][i]].get('dtor'))
        w('| %s-%s | %d | %d | %s | %d | `%s` .. `%s` |' % (
            hx(r['lo']), hx(r['hi']), r['kept'], r['drops'], 'yes' if r['verified'] else 'no',
            nd, r['first_key'][:24], r['last_key'][:24]))
    w('')
    if len(run_cls) >= 2:
        w('Class overlap between verified runs (classes with anchors in both):')
        w('')
        for i in range(len(run_cls)):
            for j in range(i + 1, len(run_cls)):
                ov = len(run_cls[i][1] & run_cls[j][1])
                w('- %s-%s and %s-%s: %d' % (hx(run_cls[i][0]['lo']), hx(run_cls[i][0]['hi']),
                                             hx(run_cls[j][0]['lo']), hx(run_cls[j][0]['hi']), ov))
        w('')
    w('Reading: the two long runs each walk the whole key range once (`10...` to `9...`, '
      'byte order of the mangled name, so length prefixes sort as strings). The third '
      'verified run repeats the start of the first run\'s class order but holds no '
      'destructor anchor; it is most likely the `_ZNK` (const member) pass of a group. '
      'The rules do not depend on this: inside one run all names share one flavour, and a '
      'switch from `_ZN` to `_ZNK` restarts the key order, which the DP sees as a new run. '
      'The library code inside the long runs (NEX, SDK, Pia) is consistent with global '
      'name sorting (for example `_ZN2nn...` sorts between `_ZN28...` and `_ZN3...`). '
      'Unsorted: 0x002B0E58-0x002F1180 (short sorted bursts, pairs of tiny shared slot '
      'functions; likely COMDAT inline functions placed in object order), the tail after '
      '0x0041A73C, and everything before 0x0014DD60.')
    w('')
    w('## Rules and confidence')
    w('')
    w('| Rule (evidence tag) | Meaning | Confidence |')
    w('|---|---|---|')
    w('| `between_class_anchors:A-B` | the two neighbouring kept anchors belong to the same '
      'class C, so the name has the prefix `_ZN<C>` (or `_ZNK<C>`) | high |')
    w('| ... `+lib_in_gap` / `+offseq_in_gap` / `+local_unsorted` / `+run_edge` | the gap '
      'also holds library-tagged code or an off-sequence anchor of another class, the '
      'local window (%d anchors each side) drops > %d%% of anchors, or the pair is within '
      '%d anchors of a run end | medium |' % (LOCAL_RADIUS * 2, int(LOCAL_MAX_DROP * 100),
                                              RUN_EDGE))
    w('| ... `+lib_unknown` / `+holds_slot_func` | the function is tagged unknown, or holds '
      'a vtable-slot function that funcmap did not split | capped at medium |')
    w('| `scope_enclosing:A-B` | neighbouring anchors of C and of a type nested in C: the '
      'function is in C\'s scope (C or a type nested in C) | medium |')
    w('| `scope_common_outer:A-B` | anchors of two types nested in class E: in E\'s scope | low |')
    w('| `edge_tail_calls:A>V` | gap after the last anchor A of class C (not a destructor): '
      'V is BL-linked to known members of C and none of the next class; every function '
      'from A up to V is taken as C | low |')
    w('| `edge_head_calls:B<V` | mirror image before the first anchor B of the next class | low |')
    w('')
    w('Other functions between anchors of unrelated classes are left empty: they can hold '
      'members of either class, free functions, or classes without RTTI. A destructor '
      'anchor closes a class block: `D0Ev`/`D1Ev` sort after every named member and the '
      'constructors, and no deleting dtor BL-calls the function after it (D1 is inlined '
      'into D0), so a D1-after-D0 rule was dropped. Edge rows: %d tail, %d head, %d gaps '
      'skipped because the head and tail votes overlapped.' % (
          stats['edge_tail'], stats['edge_head'], stats['edge_conflict']))
    vc = info.get('vote_check', {})
    w('')
    w('Call locality behind the edge rule, measured on high same_class rows: %d of them '
      'are BL-linked to at least one anchor; for %d of those an anchor of their own class '
      'is among the links, and for %d all linked anchors are of their own class. The edge '
      'rule cannot exclude classes without RTTI that sort between A and B, hence low.' % (
          vc.get('with_anchor_link', 0), vc.get('own_class_linked', 0),
          vc.get('only_own_class', 0)))
    w('')
    w('## Holdout test')
    w('')
    w('%d-fold: each fold of anchors is removed, the DP is re-run on the rest, and the rule '
      'is applied to the removed anchors (they stand in for unknown functions).' % FOLDS)
    w('')
    w('| Rule | Tested | Correct | Accuracy |')
    w('|---|---|---|---|')
    for tag, label in (('same_class', 'same_class, all (class)'),
                       ('same_class_high', 'same_class, pairs that would be high'),
                       ('same_class_medium', 'same_class, pairs capped at medium (local/edge)'),
                       ('scope_encl', 'scope enclosing (in scope)'),
                       ('scope_outer', 'scope common outer (in scope)')):
        n = ho.get(tag + '_n', 0)
        ok = ho.get(tag + '_ok', 0)
        w('| %s | %d | %d | %s |' % (label, n, ok, pct(ok, n)))
    w('')
    w('The scope rule never applies here: only 5 RTTI classes are nested in another RTTI '
      'class, and none of them sit next to their enclosing class with a gap between them.')
    w('')
    w('The test is optimistic for gaps: held-out anchors always belong to RTTI classes, '
      'while real gap functions can also be free functions or members of classes without '
      'RTTI. For same_class it is fair, because the name prefix is forced by the sort.')
    w('')
    w('## Failure cases and limits')
    w('')
    w('- **Nested types without RTTI.** A same_class member may belong to a type nested in '
      'C (for example a helper struct `C::Impl`); its name still starts with C\'s prefix. '
      'The class column is then the enclosing class.')
    w('- **Library code between same-class anchors.** %d same-class gaps (of %d) contain '
      'functions tagged as a non-game library; %d such functions were skipped and the rest '
      'of those gaps were lowered to medium. In a sorted run such a function must carry '
      'C\'s prefix, so these are probably library mis-tags (feedback for '
      '`tools/m2/library_tags.py`).' % (flagged['lib_in_gap'], len(gaps_same), lib_gap_funcs))
    w('- **Off-sequence anchors.** %d anchors are off-sequence (list in '
      '`build/m2_members/runs.txt`). Most are shared slot functions whose owner (the slot '
      'LCA) is not the defining class, or identical-code-folded functions kept under '
      'another class\'s name. %d same-class gaps contain one and were lowered to medium.' % (
          len(info['dropped']), flagged['offseq_in_gap']))
    w('- **Weak local sort.** %d same-class gaps sit where more than %d%% of nearby anchors '
      'are dropped; lowered to medium.' % (flagged['local_unsorted'], int(LOCAL_MAX_DROP * 100)))
    mt = collections.Counter(m[1] for m in misses)
    w('- **Held-out misses.** %d held-out anchors were mispredicted (%s; list in '
      '`build/m2_members/holdout.txt`). The misses rated high are slot functions that sit '
      'inside another class block (in this data: 4 single-class functions, most likely '
      'identical-code folding that kept the other class copy, and 2 shared functions '
      'whose LCA owner is not the block class). The anchor label, not the sort, is off, '
      'and all of them are off-sequence in the full run. The capped ones sit at the start of the '
      'second long run, next to the unsorted zone, where the run boundary moves when '
      'anchors are removed.' % (len(misses), ', '.join('%s %d' % kv for kv in sorted(mt.items()))))
    w('- **Unassigned game functions inside verified runs** (%d):' % sum(why.values()))
    for k, v in sorted(why.items()):
        w('  - %s: %d' % (k, v))
    w('- **Unsorted areas are not attempted.** %d game functions lie outside the verified '
      'runs (0x002B0E58-0x002F1180, the tail after 0x0041A73C, the front before '
      '0x0014DD60).' % (n_game - len(game_in_ver)))
    w('- **Function boundaries** come from `build/cache/analysis.json` as given; '
      '`config/naming/boundaries.csv` was not applied. A merged or split function keeps '
      'the class of its start address.')
    if sizes:
        w('- Same-class gap sizes (functions per gap): median %d, max %d.' % (
            sizes[len(sizes) // 2], sizes[-1]))
    w('')
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, 'w', encoding='utf-8', newline='\n') as fo:
        fo.write('\n'.join(x for x in L if x is not None) + '\n')


if __name__ == '__main__':
    main()
