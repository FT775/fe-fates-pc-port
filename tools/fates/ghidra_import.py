# Ghidra script (Jython 2.7): import build/symbols_full.tsv into the open program.
# @category FatesPort
#
# Run tools/export_symbols.py first, load extracted/code.bin as raw ARM v6 little endian
# at the .text base from config/game.json, then run this from the Script Manager and pick
# build/symbols_full.tsv. For every row it:
#   * sets TMode=1 at Thumb starts (mode THUMB) so Ghidra disassembles them as Thumb,
#   * creates the function (or renames the existing one),
#   * puts it in the C++ namespace path of its qualified name (A::B::f -> namespace A::B),
#   * stores the full demangled signature and the library tag as a plate comment.
# Status: written against the Ghidra 10/11 FlatProgramAPI; NOT yet run in Ghidra by us.
from ghidra.program.model.symbol import SourceType
from ghidra.app.util import NamespaceUtils
from java.math import BigInteger


def split_scope(q):
    depth = 0
    last = -1
    i = 0
    while i < len(q):
        if q.startswith("operator", i) and depth == 0 and (i == 0 or q[i - 1] in ":~ _"):
            break
        c = q[i]
        if c in "<(":
            depth += 1
        elif c in ">)":
            depth -= 1
        elif c == ":" and depth == 0 and q.startswith("::", i):
            last = i
            i += 2
            continue
        i += 1
    if last < 0:
        return "", q
    return q[:last], q[last + 2:]


f = askFile("symbols_full.tsv from tools/export_symbols.py", "Import")
tmode = currentProgram.getRegister("TMode")
st = currentProgram.getSymbolTable()
n = 0
for line in open(f.getAbsolutePath()):
    if line.startswith("addr\t"):
        continue
    p = line.rstrip("\n").split("\t")
    if len(p) < 7:
        continue
    addr = toAddr(int(p[0], 16))
    mode, lib, name, qual, sig = p[2], p[3], p[4], p[5], p[6]
    if mode == "THUMB" and tmode is not None:
        currentProgram.getProgramContext().setValue(tmode, addr, addr, BigInteger.ONE)
    scope, base = split_scope(qual) if sig else ("", name)
    ns = None
    if scope:
        try:
            ns = NamespaceUtils.createNamespaceHierarchy(scope, None, currentProgram,
                                                         SourceType.IMPORTED)
        except Exception:
            ns = None
    fn = getFunctionAt(addr)
    if fn is None:
        disassemble(addr)
        fn = createFunction(addr, base if ns else name)
    if fn is not None:
        try:
            fn.setName(base if ns else name, SourceType.IMPORTED)
            if ns is not None:
                fn.setParentNamespace(ns)
        except Exception:
            fn.setName(name, SourceType.IMPORTED)
        setPlateComment(addr, (sig or name) + "\n[" + lib + "]")
    n += 1
print("imported %d symbols" % n)
