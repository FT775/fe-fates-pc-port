"""Support readout: per player-unit pair, points (Unit+0x11C[slot]) vs thresholds C/B/A/S (Reliance entry +4..+7).
Needs a look run with --dump 0x006D3000,32768."""
import struct,sys
d='build/harness/runs/%s/'%(sys.argv[1] if len(sys.argv)>1 else 'look')
heap=open(d+'zakuro-dump-0x30000000.bin','rb').read(); G=open(d+'zakuro-dump-0x006D3000.bin','rb').read()
def g32(a): return struct.unpack_from('<I',G,a-0x006D3000)[0]
def rd(a,n):
    o=a-0x30000000
    return heap[o:o+n] if 0<=o<=len(heap)-n else None
def u32(a): b=rd(a,4); return struct.unpack('<I',b)[0] if b else 0
def u16(a): b=rd(a,2); return struct.unpack('<H',b)[0] if b else 0
def name(per):
    for i in range(0,16,4):
        p=u32(per+i); b=rd(p,30) if p else None
        if b and b.startswith(b'PID_'): return b.split(bytes(1))[0].decode('shift_jis','replace')
    return '?'
pool=g32(0x006D9F40+4); tab=g32(0x006D3BD0)
units=[]; u=u32(pool)
while u:
    per=u32(u+0x9C); units.append((u,per,name(per))); u=u32(u+0x14)
def entry(pa,pb):
    idx=struct.unpack('<h',rd(pa+48,2))[0]
    if idx<0: return None
    node=u32(tab+4*(idx&127))
    while node:
        rec=u32(node)
        if u16(rec)==idx:
            n=u16(rec+2); want=u16(pb+36)
            for i in range(n):
                e=rec+4+12*i
                if u16(e)==want: return e
            return None
        node=u32(node+4)  # guess: next in bucket
    return None
for ua,pa,na in units:
    for ub,pb,nb in units:
        if ua>=ub: continue
        e=entry(pa,pb)
        if not e: continue
        slot=u16(e+2); pts=rd(u32(ua+0x11C)+slot,1)
        th=list(rd(e+4,4))
        print(f'{na} - {nb}: points {pts[0] if pts else None} thresholds C/B/A/S {th}')
