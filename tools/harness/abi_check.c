/* ABI gate of the replayer (docs/HARNESS.md 3.4). Built twice by
   tools/harness/harness.py:

     -DFE_ABI_STUB -I tools/readable/stub -I tools/harness   our stand-in
     -DFE_ABI_GENERATED -I <library folder under build/>     3dsrecomp's recomp.h, read in place

   Each build prints one line per fact ("name value"); harness.py compares the
   two outputs and refuses to replay when any line differs. replay.exe is
   compiled against the stand-in and calls generated code through function
   pointers, so the layout of Context, Host and the entry table, the exit
   codes and the depth limit must be the same on both sides. Nothing of
   recomp.h is copied: it is only #included from where 3dsrecomp wrote it. */

#include <stddef.h>
#include <stdio.h>

#if defined(FE_ABI_GENERATED)
#include "recomp.h"
typedef Entry AbiEntry;
#define ABI_VERSION RECOMP_ABI
#elif defined(FE_ABI_STUB)
#include "overrides.h"
#include "replay_abi.h"
typedef FeRpEntry AbiEntry;
#define ABI_VERSION FE_STUB_RECOMP_ABI
#else
#error "build with -DFE_ABI_STUB or -DFE_ABI_GENERATED"
#endif

#define SIZE(T) printf("sizeof %s %u\n", #T, (unsigned)sizeof(T))
#define OFF(T, m) printf("offsetof %s.%s %u size %u\n", #T, #m, (unsigned)offsetof(T, m), (unsigned)sizeof(((T *)0)->m))
#define VAL(x) printf("value %s %ld\n", #x, (long)(x))

int main(void) {
    VAL(ABI_VERSION);
    SIZE(Context);
    OFF(Context, r);
    OFF(Context, n);
    OFF(Context, z);
    OFF(Context, c);
    OFF(Context, v);
    OFF(Context, q);
    OFF(Context, thumb);
    OFF(Context, ge);
    OFF(Context, exclusive);
    OFF(Context, budget);
    OFF(Context, exit);
    OFF(Context, svc);
    OFF(Context, depth);
    OFF(Context, exclusive_address);
    OFF(Context, tls);
    OFF(Context, read_pages);
    OFF(Context, write_pages);
    OFF(Context, vfp);
    OFF(Context, fpscr);
    OFF(Context, host);
    OFF(Context, user);
    SIZE(Host);
    OFF(Host, read8);
    OFF(Host, read16);
    OFF(Host, read32);
    OFF(Host, write8);
    OFF(Host, write16);
    OFF(Host, write32);
    OFF(Host, interpret);
    OFF(Host, lookup);
    OFF(Host, svc);
    SIZE(AbiEntry);
    OFF(AbiEntry, address);
    OFF(AbiEntry, code);
    SIZE(Code);
    VAL(EXIT_NONE);
    VAL(EXIT_SVC);
    VAL(EXIT_BUDGET);
    VAL(EXIT_UNWIND);
    VAL(RECOMP_DEPTH_LIMIT);
    return 0;
}
