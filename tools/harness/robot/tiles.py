import struct,re,sys
heap=open('build/harness/runs/look/zakuro-dump-0x30000000.bin','rb').read()
B=0x30000000
locs={B+m.start():m.group()[:-1] for m in re.finditer(rb'TID_[^\0]{1,24}\0',heap)}
best=None
for i in range(0,len(heap)-0x28,4):
    p=struct.unpack_from('<I',heap,i)[0]
    if p in locs and heap[i+0xC]==0:
        k=0;names=[]
        while True:
            q=struct.unpack_from('<I',heap,i+k*0x28)[0]
            if q not in locs or heap[i+k*0x28+0xC]!=k: break
            names.append(f"{k}:{locs[q].decode('shift_jis','replace')}/c{heap[i+k*0x28+0x10]}"); k+=1
        if k>=3: print(names)
