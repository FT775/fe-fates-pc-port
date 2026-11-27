import sys,struct,heapq,os
sys.argv += []
run=sys.argv[4] if len(sys.argv)>4 else 'look'
d=f'build/harness/runs/{run}/'
heap=open(d+'zakuro-dump-0x30000000.bin','rb').read(); g=open(d+'zakuro-dump-0x006D7000.bin','rb').read()
rd=lambda a,n: heap[a-0x30000000:a-0x30000000+n]
mi=struct.unpack_from('<I',g,0x3E8)[0]; hdr=rd(mi,6); grid=rd(mi+0x808,1024)
cost=eval(sys.argv[1]); sx,sy=map(int,sys.argv[2].split(',')); mv=int(sys.argv[3])
pool=struct.unpack_from('<II',g,0x2F40); enemy=set()
fb=rd(pool[1]+12,12); u=struct.unpack('<I',fb[:4])[0]
while u:
    ub=rd(u,0x140); enemy.add((ub[0xF4],ub[0xF5])); u=struct.unpack('<I',ub[0x14:0x18])[0]
x0,y0,x1,y1=hdr[2],hdr[3],hdr[4],hdr[5]
dist={(sx,sy):0}; q=[(0,sx,sy)]
while q:
    c,x,y=heapq.heappop(q)
    if c>dist[(x,y)]: continue
    for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
        if not(x0<=nx<x1 and y0<=ny<y1) or (nx,ny) in enemy: continue
        k=cost.get(grid[nx|ny<<5],99); nc=c+k
        if nc<=mv and nc<dist.get((nx,ny),99): dist[(nx,ny)]=nc; heapq.heappush(q,(nc,nx,ny))
print('    '+''.join(f'{x%100:3d}' for x in range(x0,x1)))
for y in range(y0,y1):
    print(f'{y:3d} '+''.join((' E ' if (x,y) in enemy else (f' {dist[(x,y)]} ' if (x,y) in dist else '  .')) for x in range(x0,x1)))
