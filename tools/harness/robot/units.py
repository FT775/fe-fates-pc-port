import struct,sys,os
run=sys.argv[1]; d=f'build/harness/runs/{run}/'
heap=open(d+'zakuro-dump-0x30000000.bin','rb').read()
import os
if os.path.exists(d+'zakuro-dump-0x006D7000.bin'):
    g=open(d+'zakuro-dump-0x006D7000.bin','rb').read()
    pool=struct.unpack_from('<II',g,0x2F40)
    cp=struct.unpack_from('<I',g,0x198)[0]
else:
    pool=struct.unpack('<II',open(d+'zakuro-dump-0x006D9F40.bin','rb').read()); cp=None
def rd(a,n):
    o=a-0x30000000
    if 0<=o<len(heap)-n: return heap[o:o+n]
    return None
def w(a): b=rd(a,4); return struct.unpack('<I',b)[0] if b else None
def cstr(a):
    b=rd(a,40)
    return b.split(b'\0')[0].decode('shift_jis','replace') if b else '?'
print('pool',hex(pool[0]),hex(pool[1]),'cursor',struct.unpack('<ii',rd(cp,8)) if cp and rd(cp,8) else None)
for f in range(8):
    fa=pool[1]+f*12; fb=rd(fa,12)
    if not fb: continue
    u=struct.unpack('<I',fb[:4])[0]; typ=fb[8]
    n=0
    while u and n<60:
        ub=rd(u,0x140)
        if not ub: break
        per=struct.unpack('<I',ub[0x9C:0xA0])[0]; job=struct.unpack('<I',ub[0xA0:0xA4])[0]
        # guess: person has pid string ptr somewhere in first words
        pw=[w(per+i) for i in range(0,16,4)] if rd(per,16) else []
        names=[cstr(p) for p in pw if p and rd(p,4)]
        jn=[cstr(w(job+i)) for i in range(0,16,4) if rd(job,16) and w(job+i) and rd(w(job+i),4)]
        print(f'force{f} xy=({ub[0xF4]},{ub[0xF5]}) hp={ub[0xF3]} st={struct.unpack_from("<I",ub,8)[0]:08x} {names[0] if names else ""} {jn[0] if jn else ""}')
        if '-v' in sys.argv: print('   ',ub[0xC0:0x140].hex())
        u=struct.unpack('<I',ub[0x14:0x18])[0]; n+=1
if '-m' in sys.argv:
    mi=struct.unpack_from('<I',g,0x3E8)[0]; hdr=rd(mi,6); grid=rd(mi+0x808,1024)
    x0,y0,x1,y1=hdr[2],hdr[3],hdr[4],hdr[5]
    occ={}
    for f in range(3):
        fb=rd(pool[1]+f*12,12); u=struct.unpack('<I',fb[:4])[0]
        while u:
            ub=rd(u,0x140); occ[(ub[0xF4],ub[0xF5])]='CEA'[f]; u=struct.unpack('<I',ub[0x14:0x18])[0]
    print('play',x0,y0,x1,y1)
    print('    '+''.join(f'{x%100:3d}' for x in range(x0,x1)))
    for y in range(y0,y1):
        print(f'{y:3d} '+''.join((' '+occ[(x,y)]+' ') if (x,y) in occ else f'{grid[x|y<<5]:3d}' for x in range(x0,x1)))
if '-t' in sys.argv:
    tp=struct.unpack_from('<I',g,0xFEC)[0]
    tb=rd(tp,8); first,count=struct.unpack('<II',tb)
    print('tricks',count)
    t=first
    while t:
        b=rd(t,0x1C)
        if not b: break
        sp=struct.unpack_from('<I',b,0x18)[0]
        print(f'  type {b[0xC]} at ({b[8]},{b[9]}) {b[0xA]}x{b[0xB]} state {b[0x16]:#x} pos {cstr(sp) if sp else ""}')
        t=struct.unpack_from('<I',b,0)[0]
if '-g' in sys.argv:
    gp=struct.unpack_from('<I',g,0x3248)[0]
    b=rd(gp,0x40)
    print('GameUserData',hex(gp),'flags+0x28=%08x'%struct.unpack_from('<I',b,0x28)[0],'difficulty+0x2D=',b[0x2D],'route+0x2E=',b[0x2E])
if '-s' in sys.argv:  # support points: Unit+0x11C -> byte per Reliance slot (Unit::GetReliance 0x0052C260)
    fb=rd(pool[1],12); u=struct.unpack('<I',fb[:4])[0]
    while u:
        ub=rd(u,0x140); per=struct.unpack('<I',ub[0x9C:0xA0])[0]
        pw=[w(per+i) for i in range(0,16,4)] if rd(per,16) else []
        names=[cstr(p) for p in pw if p and rd(p,4)]
        sp=struct.unpack_from('<I',ub,0x11C)[0]
        pts=rd(sp,24) if sp else None
        print('support', names[0] if names else '?', 'person+48 idx', struct.unpack('<h',rd(per+48,2))[0] if rd(per,64) else None, pts.hex() if pts else None)
        u=struct.unpack('<I',ub[0x14:0x18])[0]
