"""board with level (Unit+0xF1), exp (+0xF2), raw stats (Person.base + Job.base + gain +0xC8) and items (+0x108: index:bits; weapon rank = bits 8..13). usage: bd.py RUN [-e]"""
import struct, sys
run = sys.argv[1]; d = f'build/harness/runs/{run}/'
heap = open(d + 'zakuro-dump-0x30000000.bin', 'rb').read()
g = open(d + 'zakuro-dump-0x006D7000.bin', 'rb').read()
B = 0x30000000
def rd(a, n):
    o = a - B
    return heap[o:o + n] if 0 <= o <= len(heap) - n else None
def w(a): b = rd(a, 4); return struct.unpack('<I', b)[0] if b else 0
def cstr(a):
    b = rd(a, 40); return b.split(b'\0')[0].decode('shift_jis', 'replace') if b else '?'
def nm(p):
    for i in range(0, 16, 4):
        q = w(p + i)
        if q and rd(q, 4) and rd(q, 4)[:3] in (b'PID', b'JID', b'IID'): return cstr(q)
    return '?'
pool = struct.unpack_from('<II', g, 0x2F40)
cp = struct.unpack_from('<I', g, 0x198)[0]
print('cursor', struct.unpack('<ii', rd(cp, 8)) if rd(cp, 8) else None)
forces = [0, 1, 2] if '-e' in sys.argv else [0]
for f in forces:
    u = w(pool[1] + f * 12)
    while u:
        ub = rd(u, 0x140)
        per = w(u + 0x9C); job = w(u + 0xA0)
        G = list(struct.unpack_from('<8b', ub, 0xC8))
        pb = list(struct.unpack('<8b', rd(per + 0x38, 8))); jb = list(struct.unpack('<8b', rd(job + 0x1C, 8)))
        raw = [a + b + c for a, b, c in zip(pb, jb, G)]
        items = []
        for i in range(5):
            idx, fl = struct.unpack_from('<HH', ub, 0x108 + 4 * i)
            if idx:
                items.append(f'{idx}:{fl & 0x7f}+{(fl >> 8) & 0x3f}')
        print(f'F{f} ({ub[0xF4]},{ub[0xF5]}) hp{ub[0xF3]} lv{ub[0xF1]} ex{ub[0xF2]} st{struct.unpack_from("<I",ub,8)[0]:x} {nm(per)[4:]} raw{raw} G{G} items {items}')
        u = w(u + 0x14)
