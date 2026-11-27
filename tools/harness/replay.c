/* replay.exe: the offline side of the tier-4 harness (docs/HARNESS.md 3.4, 5).

   Two parts in one program:
   - a 3dsrecomp library (the capture library, or tools/harness/fakelib for
     the self-test), loaded with LoadLibrary / dlopen. It must export
     recomp_abi == 5 and recomp_entries; it runs with FE_READABLE=original
     (harness.py sets it), so every override in it forwards to its original.
   - our readable code, compiled natively into this program from
     src/readable against the stand-in overrides.h, like host_test.c (and
     with gcov when harness.py asks for coverage). Its FE_ENTRY runs in
     readable mode; RECOMP_ORIGINAL (the stand-in's fe_stub_original, defined
     below) runs the library's code for the address in r15.

   Commands (harness.py drives them; every folder must be below build/):

     replay run   --lib L --dir D [--side readable|original] [--only a,b]
                  [--probes a,b] [--wide a,b] [--out F]
         Replays every record in D/records.fecap (pages from D/pages/) twice
         on fresh private copies of its entry pages: run A = the library's
         original (fidelity gate: it must give the recorded exit registers,
         final bytes, lookups and probe calls, else UNFAITHFUL), run B = the
         readable function (or, with --side original, the library's original
         again: the original-vs-original test, which must give 0 mismatches).
         One JSON line per record to F (default stdout), then a summary line.

     replay synth --lib L --dir D [--image code.bin] [--addrs a,b|all]
                  [--calls N] [--seed S] [--probes a,b] [--guard a] [--live ab|a]
         No game needed: runs each function N times on a made-up game memory
         (the image at 0x00100000 if given, every other byte from a seeded
         generator, words often pointing into a made-up heap) through the
         real capture runtime (src/readable/core/capture.c, FE_READABLE=capture
         in this program): it records, runs A and B live and keeps EVERY
         record of the chosen functions (store mode) in D, plus D/summary.tsv.
         A dry run of what the game process does in H4a, and the record
         source of the self-test. Synth records hold made-up memory (and the
         image's bytes when --image is given): they stay under build/.

     replay list
         The native readable overrides: "0x........ name" per line.

   --probes: addresses whose code, when reached through the host's lookup,
   is noted as a probe call (callee, r0-r3) before it runs, as a harness
   probe override (FE_PROBE) would be. A capture library with real probes
   notes them through its exported fe_probe_set_sink, which is used too.

   Memory of a replay (HARNESS.md 3.4): a sparse page map from the record,
   all page tables null so every access reaches the callbacks here; a page
   outside the record is filled with 0xCD (SYNTH) and reading an unwritten
   byte of it is OUT-OF-IMAGE; a write to a page the game could not write is
   DEVICE; svc and interpret unwind the run (ESCAPED). */

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <dlfcn.h>
#include <limits.h>
#include <unistd.h>
#endif

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fe.h"
#include "replay_abi.h"

#ifdef FE_REPLAY_TRACE /* tools/harness/h6trace.c, linked into h6sample.py's trace build only */
void fe_trace_begin(void);
void fe_trace_end(FILE *out);
#endif

#define RP_BUDGET FE_CALL_BUDGET
#define RP_RETURN FE_GUEST_RETURN
#define RP_MAX_PAGES 4096u

/* ------------------------------------------------------------------------
   Small helpers */

static void *rp_xalloc(size_t n) {
    void *p = calloc(1, n ? n : 1);
    if (p == NULL) {
        fprintf(stderr, "replay: out of memory\n");
        exit(2);
    }
    return p;
}

static void *rp_grow(void *p, uint32_t *cap, uint32_t need, size_t elem) {
    if (need <= *cap)
        return p;
    uint32_t n = *cap ? *cap : 16;
    while (n < need)
        n *= 2;
    void *q = realloc(p, (size_t)n * elem);
    if (q == NULL) {
        fprintf(stderr, "replay: out of memory\n");
        exit(2);
    }
    *cap = n;
    return q;
}

static void rp_bit_set(uint8_t *bits, uint32_t i) { bits[i >> 3] = (uint8_t)(bits[i >> 3] | (1u << (i & 7))); }
static int rp_bit(const uint8_t *bits, uint32_t i) { return (bits[i >> 3] >> (i & 7)) & 1; }

/* the comma list a,b,c of hex addresses (0x optional); returns the count */
static uint32_t rp_parse_list(const char *s, uint32_t **out) {
    uint32_t n = 0, cap = 0;
    uint32_t *v = NULL;
    while (s && *s) {
        char *end;
        unsigned long a = strtoul(s, &end, 16);
        if (end != s) {
            v = rp_grow(v, &cap, n + 1, sizeof *v);
            v[n++] = (uint32_t)a;
        }
        s = strchr(end, ',');
        if (s)
            s++;
    }
    *out = v;
    return n;
}

static int rp_in_list(const uint32_t *v, uint32_t n, uint32_t a) {
    for (uint32_t i = 0; i < n; i++)
        if (v[i] == a)
            return 1;
    return 0;
}

/* refuses output folders outside this repository's build/ (records hold game
   memory), like capture.c's folder rule: no "..", and the absolute path must
   lie below the build folder this program itself was built into (the deepest
   "build" folder above replay.exe: <repo>/build/harness/...). A "build"
   component somewhere else (C:/build, another repo's build/) is refused. */
static void rp_norm(char *s) {
    for (char *c = s; *c; c++)
        if (*c == '\\')
            *c = '/';
    char *x;
    while ((x = strstr(s, "/./")) != NULL)
        memmove(x, x + 2, strlen(x + 2) + 1);
    size_t n = strlen(s);
    while (n > 1 && s[n - 1] == '/')
        s[--n] = 0;
}

static int rp_abs(const char *in, char *out, size_t n) {
#if defined(_WIN32)
    if (_fullpath(out, in, n) == NULL)
        return 0;
#else
    if (in[0] == '/') {
        if (strlen(in) >= n)
            return 0;
        strcpy(out, in);
    } else {
        if (getcwd(out, n) == NULL || strlen(out) + 1 + strlen(in) >= n)
            return 0;
        strcat(out, "/");
        strcat(out, in);
    }
#endif
    rp_norm(out);
    return 1;
}

static int rp_build_root(char *out, size_t n) {
    char exe[4096];
#if defined(_WIN32)
    DWORD k = GetModuleFileNameA(NULL, exe, sizeof exe);
    if (k == 0 || k >= sizeof exe)
        return 0;
#else
    ssize_t k = readlink("/proc/self/exe", exe, sizeof exe - 1);
    if (k <= 0)
        return 0;
    exe[k] = 0;
#endif
    if (!rp_abs(exe, out, n))
        return 0;
    char *best = NULL;
    for (char *p = out; (p = strstr(p, "/build")) != NULL; p += 6)
        if (p[6] == '/' || p[6] == 0)
            best = p + 6;
    if (best == NULL)
        return 0;
    *best = 0;
    return 1;
}

static int rp_dir_ok(const char *d) {
    char root[4096], abs[4096];
    if (d == NULL || strstr(d, "..") || !rp_build_root(root, sizeof root) || !rp_abs(d, abs, sizeof abs))
        return 0;
    size_t n = strlen(root);
#if defined(_WIN32)
    int same = _strnicmp(abs, root, n) == 0;
#else
    int same = strncmp(abs, root, n) == 0;
#endif
    return same && abs[n] == '/';
}

/* the page hash capture.c uses for pages/<hash>.pg (same function, our own
   code), so a damaged page file is found */
static uint64_t rp_mix(uint64_t x) {
    x ^= x >> 30;
    x *= 0xBF58476D1CE4E5B9ull;
    x ^= x >> 27;
    x *= 0x94D049BB133111EBull;
    return x ^ (x >> 31);
}

static void rp_page_hash(const uint8_t *p, uint32_t out[4]) {
    uint64_t a = 0x9E3779B97F4A7C15ull, b = 0xC2B2AE3D27D4EB4Full;
    for (uint32_t i = 0; i < FE_CAP_PAGE_SIZE; i += 8) {
        uint64_t w;
        memcpy(&w, p + i, 8);
        a = (a ^ w) * 0xFF51AFD7ED558CCDull;
        a ^= a >> 32;
        b = (b + w + i) * 0xC4CEB9FE1A85EC53ull;
        b ^= b >> 29;
    }
    a = rp_mix(a ^ FE_CAP_PAGE_SIZE);
    b = rp_mix(b ^ a);
    out[0] = (uint32_t)a;
    out[1] = (uint32_t)(a >> 32);
    out[2] = (uint32_t)b;
    out[3] = (uint32_t)(b >> 32);
}

/* ------------------------------------------------------------------------
   The library */

static const FeRpEntry *rp_entries;
static uint32_t rp_entry_count;
static uint32_t *rp_probe_list, rp_probe_count;

static void *rp_sym(void *lib, const char *name) {
#if defined(_WIN32)
    FARPROC f = GetProcAddress((HMODULE)lib, name);
    void *p;
    memcpy(&p, &f, sizeof p); /* data and code pointers have one size on every host we build on */
    return p;
#else
    return dlsym(lib, name);
#endif
}

static int rp_entry_cmp(const void *a, const void *b) {
    uint32_t x = ((const FeRpEntry *)a)->address, y = ((const FeRpEntry *)b)->address;
    return x < y ? -1 : x > y;
}

static Code rp_find(uint32_t address) {
    uint32_t lo = 0, hi = rp_entry_count;
    while (lo < hi) {
        uint32_t mid = lo + (hi - lo) / 2;
        if (rp_entries[mid].address < address)
            lo = mid + 1;
        else
            hi = mid;
    }
    return lo < rp_entry_count && rp_entries[lo].address == address ? rp_entries[lo].code : NULL;
}

static void rp_dll_sink(Context *ctx, uint32_t callee);

static int rp_load(const char *path) {
#if defined(_WIN32)
    void *lib = (void *)LoadLibraryA(path);
#else
    void *lib = dlopen(path, RTLD_NOW | RTLD_LOCAL);
#endif
    if (lib == NULL) {
        fprintf(stderr, "replay: cannot load %s\n", path);
        return 0;
    }
    const uint32_t *abi = rp_sym(lib, "recomp_abi");
    const uint32_t *count = rp_sym(lib, "recomp_entry_count");
    const FeRpEntry *entries = rp_sym(lib, "recomp_entries");
    if (abi == NULL || count == NULL || entries == NULL) {
        fprintf(stderr, "replay: %s does not export recomp_abi, recomp_entry_count and recomp_entries\n", path);
        return 0;
    }
    if (*abi != FE_REPLAY_RECOMP_ABI) {
        fprintf(stderr, "replay: %s has recomp_abi %u, replay.exe knows only %u\n", path, (unsigned)*abi,
                FE_REPLAY_RECOMP_ABI);
        return 0;
    }
    rp_entries = entries;
    rp_entry_count = *count;
    for (uint32_t i = 1; i < rp_entry_count; i++)
        if (entries[i - 1].address >= entries[i].address) { /* documented as sorted; never trust it */
            FeRpEntry *copy = rp_xalloc((size_t)rp_entry_count * sizeof *copy);
            memcpy(copy, entries, (size_t)rp_entry_count * sizeof *copy);
            qsort(copy, rp_entry_count, sizeof *copy, rp_entry_cmp);
            rp_entries = copy;
            break;
        }
    void *sink_sym = rp_sym(lib, "fe_probe_set_sink");
    void (*set_sink)(FeProbeSink) = NULL;
    memcpy(&set_sink, &sink_sym, sizeof set_sink);
    if (set_sink)
        set_sink(rp_dll_sink);
    return 1;
}

/* ------------------------------------------------------------------------
   Private memory of one run */

#define RP_E_SVC 0x01u
#define RP_E_INTERP 0x02u
#define RP_E_OUTSIDE 0x04u /* read an unwritten byte of a page the record does not have */
#define RP_E_DEVICE 0x08u  /* wrote a page the game had no writable pointer for */
#define RP_E_FULL 0x10u    /* too many pages */
#define RP_E_NOCODE 0x20u  /* the library has no code for an address it had to run */

typedef struct RpPage {
    uint32_t base;
    uint8_t synth, nowrite;
    uint8_t bytes[FE_CAP_PAGE_SIZE];
    uint8_t written[FE_CAP_PAGE_SIZE / 8], readb[FE_CAP_PAGE_SIZE / 8];
} RpPage;

typedef struct RpMem {
    RpPage **pages;
    uint32_t count, cap;
    uint32_t *slot, slots; /* open addressing: page number -> index + 1 */
    uint32_t escaped, outside, device;
    uint64_t reads; /* host read calls (HARNESS.md 5 rule 6) */
    FeCapNote *notes;
    uint32_t note_count, note_cap;
    FeCapLookup *lookups;
    uint32_t lookup_count, lookup_cap;
} RpMem;

static RpMem *rp_cur; /* the run in progress */

/* A run B that left the record (RP_E_OUTSIDE) and keeps reading made-up 0xCD
   bytes can walk a pointer chain without end (0xCDCDCDCD -> 0xCDCDCDCD ...):
   readable C has no budget check inside its loops. Past rp_runaway_after reads
   (set for run B only, from run A's count) replay.exe writes what it has, says
   RUNAWAY on stderr and exits RP_EXIT_RUNAWAY: a B-ESCAPED verdict that is
   deterministic, never a wall-clock timeout. A faithful run never trips it:
   it needs a read outside the record first. */
#define RP_EXIT_RUNAWAY 4
static uint64_t rp_runaway_after; /* 0 = off */
static uint32_t rp_runaway_addr;

static void rp_mem_free(RpMem *m) {
    for (uint32_t i = 0; i < m->count; i++)
        free(m->pages[i]);
    free(m->pages);
    free(m->slot);
    free(m->notes);
    free(m->lookups);
    memset(m, 0, sizeof *m);
}

static RpPage *rp_mem_find(const RpMem *m, uint32_t base) {
    if (m->slots == 0)
        return NULL;
    uint32_t at = (base >> 12) & (m->slots - 1);
    for (;; at = (at + 1) & (m->slots - 1)) {
        uint32_t v = m->slot[at];
        if (v == 0)
            return NULL;
        if (m->pages[v - 1]->base == base)
            return m->pages[v - 1];
    }
}

static void rp_mem_index(RpMem *m) {
    free(m->slot);
    m->slots = 64;
    while (m->slots < m->count * 2 + 2)
        m->slots *= 2;
    m->slot = rp_xalloc(m->slots * sizeof *m->slot);
    for (uint32_t i = 0; i < m->count; i++) {
        uint32_t at = (m->pages[i]->base >> 12) & (m->slots - 1);
        while (m->slot[at])
            at = (at + 1) & (m->slots - 1);
        m->slot[at] = i + 1;
    }
}

static RpPage *rp_mem_add(RpMem *m, uint32_t base, const uint8_t *bytes, int nowrite) {
    if (m->count >= RP_MAX_PAGES)
        return NULL;
    RpPage *p = rp_xalloc(sizeof *p);
    p->base = base;
    p->nowrite = (uint8_t)nowrite;
    if (bytes)
        memcpy(p->bytes, bytes, FE_CAP_PAGE_SIZE);
    else {
        memset(p->bytes, 0xCD, FE_CAP_PAGE_SIZE);
        p->synth = 1;
    }
    m->pages = rp_grow(m->pages, &m->cap, m->count + 1, sizeof *m->pages);
    m->pages[m->count++] = p;
    if (m->count * 2 + 2 > m->slots)
        rp_mem_index(m);
    else {
        uint32_t at = (base >> 12) & (m->slots - 1);
        while (m->slot[at])
            at = (at + 1) & (m->slots - 1);
        m->slot[at] = m->count;
    }
    return p;
}

static uint8_t rp_byte(uint32_t a, int write, uint8_t value) {
    RpMem *m = rp_cur;
    RpPage *p = rp_mem_find(m, a & ~0xFFFu);
    if (p == NULL) {
        p = rp_mem_add(m, a & ~0xFFFu, NULL, 0);
        if (p == NULL) {
            m->escaped |= RP_E_FULL;
            return 0xCD;
        }
    }
    uint32_t o = a & 0xFFFu;
    if (write) {
        if (p->nowrite && !(m->escaped & RP_E_DEVICE)) {
            m->escaped |= RP_E_DEVICE;
            m->device = a;
        }
        p->bytes[o] = value;
        rp_bit_set(p->written, o);
        return value;
    }
    rp_bit_set(p->readb, o);
    if (p->synth && !rp_bit(p->written, o) && !(m->escaped & RP_E_OUTSIDE)) {
        m->escaped |= RP_E_OUTSIDE;
        m->outside = a;
    }
    return p->bytes[o];
}

static uint32_t rp_read(uint32_t a, uint32_t width) {
    uint32_t v = 0;
    rp_cur->reads++;
    if (rp_runaway_after && (rp_cur->escaped & RP_E_OUTSIDE) && rp_cur->reads > rp_runaway_after) {
        fprintf(stderr,
                "replay: RUNAWAY: run B of %08X kept reading after it left the record (first outside read "
                "%08X, %" PRIu64 " reads); stopped (B-ESCAPED)\n",
                (unsigned)rp_runaway_addr, (unsigned)rp_cur->outside, rp_cur->reads);
        fflush(NULL);
        exit(RP_EXIT_RUNAWAY);
    }
    for (uint32_t k = 0; k < width; k++)
        v |= (uint32_t)rp_byte(a + k, 0, 0) << (8 * k);
    return v;
}

static void rp_write(uint32_t a, uint32_t width, uint32_t value) {
    for (uint32_t k = 0; k < width; k++)
        rp_byte(a + k, 1, (uint8_t)(value >> (8 * k)));
}

static uint8_t rp_read8(Context *c, uint32_t a) { (void)c; return (uint8_t)rp_read(a, 1); }
static uint16_t rp_read16(Context *c, uint32_t a) { (void)c; return (uint16_t)rp_read(a, 2); }
static uint32_t rp_read32(Context *c, uint32_t a) { (void)c; return rp_read(a, 4); }
static void rp_write8(Context *c, uint32_t a, uint8_t v) { (void)c; rp_write(a, 1, v); }
static void rp_write16(Context *c, uint32_t a, uint16_t v) { (void)c; rp_write(a, 2, v); }
static void rp_write32(Context *c, uint32_t a, uint32_t v) { (void)c; rp_write(a, 4, v); }

static void rp_interpret(Context *c, uint32_t address, uint32_t opcode) {
    (void)opcode;
    rp_cur->escaped |= RP_E_INTERP;
    c->r[15] = address;
    c->exit = EXIT_UNWIND;
}

static void rp_svc(Context *c, uint32_t number) {
    (void)number;
    rp_cur->escaped |= RP_E_SVC;
    c->exit = EXIT_UNWIND;
}

static void rp_note(RpMem *m, const Context *ctx, uint32_t callee) {
    m->notes = rp_grow(m->notes, &m->note_cap, m->note_count + 1, sizeof *m->notes);
    FeCapNote *n = &m->notes[m->note_count++];
    n->callee = callee;
    n->kind = FE_CAP_KIND_PROBE;
    memcpy(n->r, ctx->r, sizeof n->r);
}

/* a probe reached through the lookup: noted, then the library's code runs */
static void rp_probe_thunk(Context *ctx) {
    uint32_t a = ctx->r[15] | ctx->thumb;
    Code code = rp_find(a);
    if (rp_cur)
        rp_note(rp_cur, ctx, a);
    if (code)
        code(ctx);
    else {
        if (rp_cur)
            rp_cur->escaped |= RP_E_NOCODE;
        ctx->exit = EXIT_UNWIND;
    }
}

static void rp_dll_sink(Context *ctx, uint32_t callee) {
    if (rp_cur)
        rp_note(rp_cur, ctx, callee);
}

static Code rp_code_for(uint32_t address) {
    Code code = rp_find(address);
    if (code && rp_in_list(rp_probe_list, rp_probe_count, address))
        return rp_probe_thunk;
    return code;
}

static Code rp_lookup(Context *c, uint32_t address) {
    (void)c;
    Code code = rp_code_for(address);
    RpMem *m = rp_cur;
    m->lookups = rp_grow(m->lookups, &m->lookup_cap, m->lookup_count + 1, sizeof *m->lookups);
    m->lookups[m->lookup_count].address = address;
    m->lookups[m->lookup_count].found = code != NULL;
    m->lookup_count++;
    return code;
}

static const Host rp_host = {rp_read8, rp_read16, rp_read32, rp_write8, rp_write16, rp_write32,
                             rp_interpret, rp_lookup, rp_svc};

/* RECOMP_ORIGINAL of the stand-in: the library's code for the address in r15 */
void fe_stub_original(Context *ctx) {
    Code code = rp_find(ctx->r[15] | ctx->thumb);
    if (code == NULL) {
        if (rp_cur)
            rp_cur->escaped |= RP_E_NOCODE;
        ctx->exit = EXIT_UNWIND;
        return;
    }
    code(ctx);
}

static const FeReplayOverride *rp_native(uint32_t address) {
    for (unsigned i = 0; i < fe_replay_override_count; i++)
        if (fe_replay_overrides[i].address == address)
            return &fe_replay_overrides[i];
    return NULL;
}

/* ------------------------------------------------------------------------
   Records */

typedef struct RpRec {
    FeCapHeader h;
    FeCapPage *pages;
    uint8_t **entry; /* bytes per page, NULL when not COPIED */
    FeCapEvent *events;
    FeCapLookup *lookups;
    FeCapNote *notes;
    char err[200];
} RpRec;

static void rp_rec_free(RpRec *r) {
    for (uint32_t i = 0; r->entry && i < r->h.page_count; i++)
        free(r->entry[i]);
    free(r->entry);
    free(r->pages);
    free(r->events);
    free(r->lookups);
    free(r->notes);
    memset(r, 0, sizeof *r);
}

static int rp_read_array(FILE *f, void **out, uint32_t count, size_t elem) {
    *out = rp_xalloc((size_t)count * elem);
    return count == 0 || fread(*out, elem, count, f) == count;
}

/* 1 = a record, 0 = end of file, -1 = damaged (r->err) */
static int rp_rec_read(FILE *f, const char *dir, RpRec *r) {
    memset(r, 0, sizeof *r);
    size_t got = fread(&r->h, 1, sizeof r->h, f);
    if (got == 0)
        return 0;
    if (got != sizeof r->h || memcmp(r->h.magic, FE_CAP_MAGIC, 8) != 0 || r->h.version != FE_CAP_VERSION ||
        r->h.header_bytes != sizeof r->h) {
        snprintf(r->err, sizeof r->err, "bad record header (magic, version %u or size)", (unsigned)r->h.version);
        return -1;
    }
    uint64_t want = sizeof r->h + (uint64_t)r->h.page_count * sizeof(FeCapPage) +
                    (uint64_t)r->h.event_count * sizeof(FeCapEvent) +
                    (uint64_t)r->h.lookup_count * sizeof(FeCapLookup) + (uint64_t)r->h.note_count * sizeof(FeCapNote);
    if (want != r->h.record_bytes || r->h.page_count > RP_MAX_PAGES) {
        snprintf(r->err, sizeof r->err, "record size %u does not match its counts", (unsigned)r->h.record_bytes);
        return -1;
    }
    if (!rp_read_array(f, (void **)&r->pages, r->h.page_count, sizeof *r->pages) ||
        !rp_read_array(f, (void **)&r->events, r->h.event_count, sizeof *r->events) ||
        !rp_read_array(f, (void **)&r->lookups, r->h.lookup_count, sizeof *r->lookups) ||
        !rp_read_array(f, (void **)&r->notes, r->h.note_count, sizeof *r->notes)) {
        snprintf(r->err, sizeof r->err, "record cut short");
        return -1;
    }
    r->entry = rp_xalloc((r->h.page_count + 1) * sizeof *r->entry);
    for (uint32_t i = 0; i < r->h.page_count; i++) {
        const FeCapPage *p = &r->pages[i];
        if (!(p->flags & FE_CAP_PAGE_COPIED))
            continue;
        char path[1400];
        snprintf(path, sizeof path, "%s/pages/%08X%08X%08X%08X.pg", dir, (unsigned)p->hash[3], (unsigned)p->hash[2],
                 (unsigned)p->hash[1], (unsigned)p->hash[0]);
        FILE *pf = fopen(path, "rb");
        r->entry[i] = rp_xalloc(FE_CAP_PAGE_SIZE);
        if (pf == NULL || fread(r->entry[i], 1, FE_CAP_PAGE_SIZE, pf) != FE_CAP_PAGE_SIZE) {
            if (pf)
                fclose(pf);
            snprintf(r->err, sizeof r->err, "page %08X: file missing or short", (unsigned)p->address);
            return 1; /* the stream is fine; this record is not replayed */
        }
        fclose(pf);
        uint32_t h[4];
        rp_page_hash(r->entry[i], h);
        if (memcmp(h, p->hash, sizeof h) != 0) {
            snprintf(r->err, sizeof r->err, "page %08X: file does not match its hash (damaged)", (unsigned)p->address);
            return 1;
        }
    }
    return 1;
}

/* ------------------------------------------------------------------------
   One run */

static uint32_t rp_vfp[32], rp_fpscr;

static void rp_regs_save(const Context *ctx, FeCapRegs *o) {
    memcpy(o->r, ctx->r, sizeof o->r);
    o->n = ctx->n;
    o->z = ctx->z;
    o->c = ctx->c;
    o->v = ctx->v;
    o->q = ctx->q;
    o->thumb = ctx->thumb;
    o->ge = ctx->ge;
    o->exclusive = ctx->exclusive;
    o->exclusive_address = ctx->exclusive_address;
    o->tls = ctx->tls;
    o->budget = ctx->budget;
    o->fpscr = *ctx->fpscr;
    memcpy(o->vfp, ctx->vfp, sizeof o->vfp);
}

static void rp_regs_load(Context *ctx, const FeCapRegs *s) {
    memcpy(ctx->r, s->r, sizeof s->r);
    ctx->n = (uint8_t)s->n;
    ctx->z = (uint8_t)s->z;
    ctx->c = (uint8_t)s->c;
    ctx->v = (uint8_t)s->v;
    ctx->q = (uint8_t)s->q;
    ctx->thumb = (uint8_t)s->thumb;
    ctx->ge = (uint8_t)s->ge;
    ctx->exclusive = (uint8_t)s->exclusive;
    ctx->exclusive_address = s->exclusive_address;
    ctx->tls = s->tls;
    *ctx->fpscr = s->fpscr;
    memcpy(ctx->vfp, s->vfp, sizeof s->vfp);
}

/* the whole register file, as the fidelity gate compares it (budget and
   tls aside); 0 when equal */
static int rp_regs_differ(const FeCapRegs *a, const FeCapRegs *b, char *d, size_t n) {
    for (int i = 0; i < 16; i++)
        if (a->r[i] != b->r[i]) {
            snprintf(d, n, "r%d %08X vs %08X", i, (unsigned)a->r[i], (unsigned)b->r[i]);
            return 1;
        }
    if (a->n != b->n || a->z != b->z || a->c != b->c || a->v != b->v || a->q != b->q || a->thumb != b->thumb ||
        a->ge != b->ge) {
        snprintf(d, n, "flags differ");
        return 1;
    }
    if (a->exclusive != b->exclusive || a->exclusive_address != b->exclusive_address) {
        snprintf(d, n, "exclusive monitor differs");
        return 1;
    }
    if (a->fpscr != b->fpscr) {
        snprintf(d, n, "fpscr %08X vs %08X", (unsigned)a->fpscr, (unsigned)b->fpscr);
        return 1;
    }
    for (int i = 0; i < 32; i++)
        if (a->vfp[i] != b->vfp[i]) {
            snprintf(d, n, "s%d %08X vs %08X", i, (unsigned)a->vfp[i], (unsigned)b->vfp[i]);
            return 1;
        }
    return 0;
}

#define RP_FPSCR_SCRATCH 0xF000009Fu /* NZCV and the cumulative exception bits: AAPCS scratch */

/* run B against run A under AAPCS (HARNESS.md 5 rule 3): r0 (and r1 for a
   64-bit result), r4-r11, sp, return pc, state, s16-s31, FPSCR control */
static int rp_abi_differ(const FeCapRegs *a, const FeCapRegs *b, int wide, char *d, size_t n) {
    static const int regs[] = {0, 1, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15};
    for (unsigned k = 0; k < sizeof regs / sizeof regs[0]; k++) {
        int i = regs[k];
        if (i == 1 && !wide)
            continue;
        if (a->r[i] != b->r[i]) {
            snprintf(d, n, "r%d: run A %08X, run B %08X", i, (unsigned)a->r[i], (unsigned)b->r[i]);
            return i == 0 ? 2 : 1;
        }
    }
    if (a->thumb != b->thumb) {
        snprintf(d, n, "state (thumb) differs");
        return 1;
    }
    for (int i = 16; i < 32; i++)
        if (a->vfp[i] != b->vfp[i]) {
            snprintf(d, n, "s%d: run A %08X, run B %08X", i, (unsigned)a->vfp[i], (unsigned)b->vfp[i]);
            return 1;
        }
    if ((a->fpscr & ~RP_FPSCR_SCRATCH) != (b->fpscr & ~RP_FPSCR_SCRATCH)) {
        snprintf(d, n, "fpscr control: run A %08X, run B %08X", (unsigned)a->fpscr, (unsigned)b->fpscr);
        return 1;
    }
    return 0;
}

static void rp_mem_from_record(RpMem *m, const RpRec *r) {
    memset(m, 0, sizeof *m);
    for (uint32_t i = 0; i < r->h.page_count; i++)
        if (r->entry[i])
            rp_mem_add(m, r->pages[i].address, r->entry[i], (r->pages[i].flags & FE_CAP_PAGE_NO_WRITE) != 0);
}

typedef struct RpRun {
    RpMem mem;
    FeCapRegs exit;
    uint32_t exit_code;
    int gave_up;
} RpRun;

/* runs code (a library entry or a native override) on a fresh copy of the
   record's entry pages */
static void rp_run(const RpRec *r, Code code, RpRun *out) {
    memset(out, 0, sizeof *out);
    rp_mem_from_record(&out->mem, r);
    static uint8_t *null_table[1u << 20];
    Context ctx;
    memset(&ctx, 0, sizeof ctx);
    ctx.vfp = rp_vfp;
    ctx.fpscr = &rp_fpscr;
    rp_regs_load(&ctx, &r->h.entry);
    ctx.budget = RP_BUDGET;
    ctx.exit = EXIT_NONE;
    ctx.depth = 1;
    ctx.read_pages = (uint8_t *const *)null_table;
    ctx.write_pages = (uint8_t *const *)null_table;
    ctx.host = &rp_host;
    rp_cur = &out->mem;
    uint32_t gave = fe_event_count(FE_EVENT_GAVE_UP, r->h.address);
    code(&ctx);
    rp_cur = NULL;
    out->gave_up = fe_event_count(FE_EVENT_GAVE_UP, r->h.address) != gave;
    out->exit_code = ctx.exit;
    rp_regs_save(&ctx, &out->exit);
}

/* the final value of byte o of page base in a run: its own copy, else the
   record's entry byte; 0 = this side never had it */
static int rp_final(const RpRun *x, const RpRec *r, const uint32_t *rec_index, uint32_t base, uint32_t o,
                    uint8_t *v) {
    const RpPage *p = rp_mem_find(&x->mem, base);
    if (p && !(p->synth && !rp_bit(p->written, o))) {
        *v = p->bytes[o];
        return 1;
    }
    (void)rec_index;
    for (uint32_t i = 0; i < r->h.page_count; i++)
        if (r->pages[i].address == base && r->entry[i]) {
            *v = r->entry[i][o];
            return 1;
        }
    return 0;
}

static const RpRun rp_empty; /* no copy of its own: rp_final gives the entry byte */

static int rp_dead_stack(const RpRec *r, uint32_t a) {
    uint32_t sp = r->h.entry.r[13];
    return a < sp && a >= sp - FE_CAP_STACK_WINDOW;
}

static int rp_probe_notes(const FeCapNote *n, uint32_t count, FeCapNote **out) {
    uint32_t k = 0;
    *out = rp_xalloc((count + 1) * sizeof **out);
    for (uint32_t i = 0; i < count; i++)
        if (n[i].kind == FE_CAP_KIND_PROBE)
            (*out)[k++] = n[i];
    return (int)k;
}

static int rp_note_differs(const FeCapNote *a, const FeCapNote *b, uint32_t index, char *d, size_t n) {
    if (a->callee != b->callee) {
        snprintf(d, n, "probe call %u: callee %08X vs %08X", (unsigned)index, (unsigned)a->callee, (unsigned)b->callee);
        return 1;
    }
    for (int k = 0; k < 4; k++)
        if (a->r[k] != b->r[k]) {
            snprintf(d, n, "probe call %u: %08X(r%d=%08X) vs (r%d=%08X)", (unsigned)index, (unsigned)a->callee, k,
                     (unsigned)a->r[k], k, (unsigned)b->r[k]);
            return 1;
        }
    return 0;
}

/* ------------------------------------------------------------------------
   Verdicts of one record (the names of fe_capture.h, plus mismatch_regs for
   a register other than r0 under rule 3, and no_readable) */

typedef struct RpResult {
    const char *verdict;
    char detail[240];
    uint32_t mem_diffs, first_diff[8], first_count, same_value, extra_reads, inlined, unobservable;
    uint64_t a_reads, b_reads;
    uint32_t a_escaped, b_escaped, a_pages, b_pages, a_writes;
} RpResult;

static const char *rp_vname(uint32_t v) {
    static const char *const names[FE_CAP_V_COUNT] = FE_CAP_V_NAMES;
    return v < FE_CAP_V_COUNT ? names[v] : "?";
}

/* fidelity gate: 1 = run A reproduced the record */
static int rp_faithful(const RpRec *r, const RpRun *a, RpResult *res) {
    char d[160];
    if (a->exit_code != EXIT_NONE || a->mem.escaped) {
        snprintf(res->detail, sizeof res->detail, "run A stopped (exit %u, escape bits %X, outside %08X)",
                 (unsigned)a->exit_code, (unsigned)a->mem.escaped, (unsigned)a->mem.outside);
        return 0;
    }
    if (rp_regs_differ(&r->h.exit, &a->exit, d, sizeof d)) {
        snprintf(res->detail, sizeof res->detail, "exit registers, game vs run A: %s", d);
        return 0;
    }
    uint8_t final[FE_CAP_PAGE_SIZE];
    for (uint32_t i = 0; i < r->h.page_count; i++) {
        if (!r->entry[i])
            continue;
        uint32_t base = r->pages[i].address;
        memcpy(final, r->entry[i], sizeof final);
        for (uint32_t e = 0; e < r->h.event_count; e++) {
            const FeCapEvent *ev = &r->events[e];
            if ((ev->kind & 0xFFu) != FE_CAP_EV_WRITE)
                continue;
            uint32_t width = ev->kind >> 8 & 0xFFu;
            for (uint32_t k = 0; k < width && k < 4; k++)
                if (((ev->address + k) & ~0xFFFu) == base)
                    final[(ev->address + k) & 0xFFFu] = (uint8_t)(ev->new_value >> (8 * k));
        }
        const RpPage *q = rp_mem_find(&a->mem, base);
        for (uint32_t o = 0; q && o < FE_CAP_PAGE_SIZE; o++)
            if (final[o] != q->bytes[o]) {
                snprintf(res->detail, sizeof res->detail, "byte %08X: game %02X, run A %02X", (unsigned)(base + o),
                         final[o], q->bytes[o]);
                return 0;
            }
    }
    for (uint32_t i = 0; i < a->mem.count; i++)
        if (a->mem.pages[i]->synth) {
            snprintf(res->detail, sizeof res->detail, "run A wrote %08X, outside the record",
                     (unsigned)a->mem.pages[i]->base);
            return 0;
        }
    /* probe calls: the record's probe notes; override notes cannot be seen
       here (the library runs in original mode), they only count */
    FeCapNote *want;
    uint32_t nw = (uint32_t)rp_probe_notes(r->notes, r->h.note_count, &want);
    res->unobservable = r->h.note_count - nw;
    int bad = 0;
    for (uint32_t i = 0; !bad && (i < nw || i < a->mem.note_count); i++) {
        if (i >= nw || i >= a->mem.note_count) {
            snprintf(res->detail, sizeof res->detail, "probe calls, game %u vs run A %u", (unsigned)nw,
                     (unsigned)a->mem.note_count);
            bad = 1;
        } else if (rp_note_differs(&want[i], &a->mem.notes[i], i, d, sizeof d)) {
            snprintf(res->detail, sizeof res->detail, "game vs run A: %s", d);
            bad = 1;
        }
    }
    free(want);
    if (bad)
        return 0;
    if (r->h.lookup_count != a->mem.lookup_count ||
        (r->h.lookup_count && memcmp(r->lookups, a->mem.lookups, r->h.lookup_count * sizeof *r->lookups) != 0)) {
        snprintf(res->detail, sizeof res->detail, "lookups differ: game %u, run A %u", (unsigned)r->h.lookup_count,
                 (unsigned)a->mem.lookup_count);
        return 0;
    }
    return 1;
}

/* rule 1 (every byte either side wrote, outside the dead stack) and rule 2
   (same-value writes, info) */
static void rp_compare_memory(const RpRec *r, const RpRun *a, const RpRun *b, RpResult *res) {
    for (int side = 0; side < 2; side++) {
        const RpRun *x = side ? b : a, *y = side ? a : b;
        for (uint32_t i = 0; i < x->mem.count; i++) {
            const RpPage *p = x->mem.pages[i];
            const RpPage *q = rp_mem_find(&y->mem, p->base);
            for (uint32_t o = 0; o < FE_CAP_PAGE_SIZE; o++) {
                int wx = rp_bit(p->written, o), wy = q ? rp_bit(q->written, o) : 0;
                if (!wx || (side == 1 && wy))
                    continue; /* each written byte once: A's writes, then B-only writes */
                uint32_t addr = p->base + o;
                if (rp_dead_stack(r, addr))
                    continue;
                uint8_t vx = p->bytes[o], vy, entry;
                int hy = rp_final(y, r, NULL, p->base, o, &vy);
                int he = rp_final(&rp_empty, r, NULL, p->base, o, &entry);
                if (hy && vx == vy) {
                    if (!wy && he && vx == entry)
                        res->same_value++;
                    continue;
                }
                if (res->mem_diffs < 8)
                    res->first_diff[res->first_count++] = addr;
                if (res->mem_diffs == 0) {
                    uint8_t av = side ? vy : vx, bv = side ? vx : vy;
                    snprintf(res->detail, sizeof res->detail, "byte %08X: run A %02X, run B %02X%s", (unsigned)addr,
                             av, bv, hy ? "" : " (one side never had it)");
                }
                res->mem_diffs++;
            }
        }
    }
}

/* rule 7 (info): bytes run B read that run A never read */
static uint32_t rp_extra_reads(const RpRun *a, const RpRun *b) {
    uint32_t n = 0;
    for (uint32_t i = 0; i < b->mem.count; i++) {
        const RpPage *p = b->mem.pages[i];
        const RpPage *q = rp_mem_find(&a->mem, p->base);
        for (uint32_t o = 0; o < FE_CAP_PAGE_SIZE; o++)
            n += (uint32_t)(rp_bit(p->readb, o) && !(q && rp_bit(q->readb, o)));
    }
    return n;
}

/* rule 4: every call B made must match A's list in order; A's calls of a
   callee B never called are done inline (info) */
static int rp_calls_differ(const RpRun *a, const RpRun *b, RpResult *res) {
    uint32_t na = 0, i = 0, k = 0;
    char d[160];
    for (uint32_t x = 0; x < a->mem.note_count; x++) {
        int called = 0;
        for (uint32_t j = 0; j < b->mem.note_count && !called; j++)
            called = b->mem.notes[j].callee == a->mem.notes[x].callee;
        if (called)
            na++;
        else
            res->inlined++;
    }
    for (;;) {
        while (i < a->mem.note_count) {
            int called = 0;
            for (uint32_t j = 0; j < b->mem.note_count && !called; j++)
                called = b->mem.notes[j].callee == a->mem.notes[i].callee;
            if (called)
                break;
            i++;
        }
        if (i >= a->mem.note_count || k >= b->mem.note_count)
            break;
        if (rp_note_differs(&a->mem.notes[i], &b->mem.notes[k], k, d, sizeof d)) {
            snprintf(res->detail, sizeof res->detail, "run A vs run B: %s", d);
            return 1;
        }
        i++;
        k++;
    }
    if (na != b->mem.note_count) {
        snprintf(res->detail, sizeof res->detail, "probe calls: %u vs %u (%u done inline by B)", (unsigned)na,
                 (unsigned)b->mem.note_count, (unsigned)res->inlined);
        return 1;
    }
    return 0;
}

static void rp_json_str(FILE *f, const char *s) {
    fputc('"', f);
    for (; *s; s++) {
        if (*s == '"' || *s == '\\')
            fprintf(f, "\\%c", *s);
        else if ((unsigned char)*s < 0x20)
            fprintf(f, "\\u%04x", (unsigned)(unsigned char)*s);
        else
            fputc(*s, f);
    }
    fputc('"', f);
}

typedef struct RpOpts {
    const char *lib, *dir, *side, *out, *image, *addrs, *guard, *live;
    uint32_t *only, only_count, *wide, wide_count;
    uint32_t calls, seed;
} RpOpts;

static void rp_replay_one(const RpRec *r, const RpOpts *o, RpResult *res) {
    memset(res, 0, sizeof *res);
    if (r->err[0]) {
        res->verdict = "damaged";
        snprintf(res->detail, sizeof res->detail, "%s", r->err);
        return;
    }
    uint32_t f = r->h.flags;
    if (f & FE_CAP_NOT_VALID) {
        res->verdict = f & FE_CAP_TRUNCATED              ? "truncated"
                       : f & FE_CAP_INCOMPLETE           ? "incomplete"
                       : f & (FE_CAP_ESCAPED_SVC | FE_CAP_ESCAPED_INTERP) ? "escaped"
                                                         : "hostmem";
        return;
    }
    Code orig = rp_find(r->h.address | r->h.entry.thumb);
    if (orig == NULL) {
        res->verdict = "unfaithful";
        snprintf(res->detail, sizeof res->detail, "the library has no code for %08X", (unsigned)r->h.address);
        return;
    }
    RpRun a, b;
    rp_run(r, orig, &a);
    res->a_reads = a.mem.reads;
    res->a_escaped = a.mem.escaped;
    res->a_pages = a.mem.count;
    if (!rp_faithful(r, &a, res)) {
        res->verdict = "unfaithful";
        rp_mem_free(&a.mem);
        return;
    }
    for (uint32_t e = 0; e < r->h.event_count; e++)
        res->a_writes += (r->events[e].kind & 0xFFu) == FE_CAP_EV_WRITE;
    int original_side = o->side && !strcmp(o->side, "original");
    Code bcode = orig;
    if (!original_side) {
        const FeReplayOverride *nat = rp_native(r->h.address);
        if (nat == NULL) {
            res->verdict = "faithful"; /* run A only: a probe, or not readable yet */
            rp_mem_free(&a.mem);
            return;
        }
        bcode = nat->code;
    }
    rp_runaway_after = 16u * a.mem.reads + 4000000u;
    rp_runaway_addr = r->h.address;
    rp_run(r, bcode, &b);
    rp_runaway_after = 0;
    res->b_reads = b.mem.reads;
    res->b_escaped = b.mem.escaped;
    res->b_pages = b.mem.count;
    res->extra_reads = rp_extra_reads(&a, &b);
    char d[160];
    int wide = rp_in_list(o->wide, o->wide_count, r->h.address);
    int regs = 0;
    if (b.exit_code == EXIT_NONE && !b.mem.escaped)
        regs = original_side ? rp_regs_differ(&a.exit, &b.exit, d, sizeof d)
                             : rp_abi_differ(&a.exit, &b.exit, wide, d, sizeof d);
    if (b.mem.escaped && !a.mem.escaped) {
        res->verdict = "b_escaped";
        snprintf(res->detail, sizeof res->detail, "run B escaped (bits %X, outside %08X, device %08X)",
                 (unsigned)b.mem.escaped, (unsigned)b.mem.outside, (unsigned)b.mem.device);
    } else if (b.gave_up && !original_side) {
        res->verdict = "gave_up";
    } else if (b.exit_code != EXIT_NONE) { /* safety net: FE_ENTRY turns a stop into a give-up first */
        res->verdict = "b_escaped";
        snprintf(res->detail, sizeof res->detail, "run B stopped with exit %u", (unsigned)b.exit_code);
    } else if (regs) {
        res->verdict = regs == 2 ? "mismatch_r0" : "mismatch_regs";
        snprintf(res->detail, sizeof res->detail, "%s (r0=%08X r1=%08X r2=%08X r3=%08X)", d,
                 (unsigned)r->h.entry.r[0], (unsigned)r->h.entry.r[1], (unsigned)r->h.entry.r[2],
                 (unsigned)r->h.entry.r[3]);
    } else {
        rp_compare_memory(r, &a, &b, res);
        if (res->mem_diffs)
            res->verdict = "mismatch_mem";
        else if (rp_calls_differ(&a, &b, res))
            res->verdict = "mismatch_calls";
        else {
            res->verdict = "match";
            if (res->inlined)
                snprintf(res->detail, sizeof res->detail, "%u call(s) of run A not made by run B (done inline)",
                         (unsigned)res->inlined);
        }
    }
    rp_mem_free(&a.mem);
    rp_mem_free(&b.mem);
}

static int cmd_run(const RpOpts *o) {
    char path[1400];
    snprintf(path, sizeof path, "%s/records.fecap", o->dir);
    FILE *f = fopen(path, "rb");
    if (f == NULL) {
        fprintf(stderr, "replay: no %s\n", path);
        return 3;
    }
    FILE *out = stdout;
    if (o->out && !(out = fopen(o->out, "w"))) {
        fprintf(stderr, "replay: cannot write %s\n", o->out);
        return 2;
    }
    uint32_t total = 0, counts[16] = {0};
    static const char *const kinds[] = {"match", "mismatch_r0", "mismatch_regs", "mismatch_mem", "mismatch_calls",
                                        "gave_up", "b_escaped", "faithful", "unfaithful", "incomplete",
                                        "escaped", "hostmem", "truncated", "damaged", NULL};
    for (;;) {
        RpRec r;
        int st = rp_rec_read(f, o->dir, &r);
        if (st == 0)
            break;
        if (st < 0) {
            fprintf(stderr, "replay: %s: %s; stopping\n", path, r.err);
            rp_rec_free(&r);
            counts[13]++;
            total++;
            break;
        }
        if (o->only_count && !rp_in_list(o->only, o->only_count, r.h.address)) {
            rp_rec_free(&r);
            continue;
        }
        RpResult res;
#ifdef FE_REPLAY_TRACE
        fe_trace_begin(); /* h6sample.py's trace build only: which readable blocks run B reaches */
#endif
        rp_replay_one(&r, o, &res);
        total++;
        for (int k = 0; kinds[k]; k++)
            if (!strcmp(kinds[k], res.verdict))
                counts[k]++;
        fprintf(out, "{\"address\":\"0x%08X\",\"kind\":\"%s\",\"call\":%u,\"sequence\":%u,\"flags\":%u,"
                     "\"cold\":%d,\"signature\":\"%08X\",\"live\":\"%s\",\"verdict\":\"%s\",\"detail\":",
                (unsigned)r.h.address, r.h.kind == FE_CAP_KIND_PROBE ? "probe" : "override", (unsigned)r.h.call_number,
                (unsigned)r.h.sequence, (unsigned)r.h.flags, (r.h.flags & FE_CAP_COLD) != 0, (unsigned)r.h.signature,
                rp_vname(r.h.verdict), res.verdict);
        rp_json_str(out, res.detail);
        fprintf(out, ",\"r0\":\"%08X\",\"mem_diffs\":%u,\"first_diffs\":[", (unsigned)r.h.exit.r[0],
                (unsigned)res.mem_diffs);
        for (uint32_t k = 0; k < res.first_count; k++)
            fprintf(out, "%s\"%08X\"", k ? "," : "", (unsigned)res.first_diff[k]);
        fprintf(out, "],\"same_value\":%u,\"extra_reads\":%u,\"inlined\":%u,\"unobservable_notes\":%u,"
                     "\"a_reads\":%" PRIu64 ",\"b_reads\":%" PRIu64 ",\"a_writes\":%u,\"a_pages\":%u,\"b_pages\":%u",
                (unsigned)res.same_value, (unsigned)res.extra_reads, (unsigned)res.inlined, (unsigned)res.unobservable,
                res.a_reads, res.b_reads, (unsigned)res.a_writes, (unsigned)res.a_pages, (unsigned)res.b_pages);
#ifdef FE_REPLAY_TRACE
        fe_trace_end(out); /* ,"path":"<hash>"[,"blocks":[...]]: the blocks only the first time a path is seen */
#endif
        fputs("}\n", out);
        rp_rec_free(&r);
    }
    fclose(f);
    if (out != stdout)
        fclose(out);
    printf("replay: %u record(s), side %s:", (unsigned)total, o->side ? o->side : "readable");
    for (int k = 0; kinds[k]; k++)
        printf(" %s %u%s", kinds[k], (unsigned)counts[k], kinds[k + 1] ? "," : "\n");
    return 0;
}

/* ------------------------------------------------------------------------
   synth: a made-up game memory and the real capture runtime */

#define SG_HEAP 0x08000000u
#define SG_HEAP_SIZE 0x01000000u
#define SG_STACK 0x0FF00000u
#define SG_STACK_SIZE 0x00100000u
#define SG_SP 0x0FFF8000u
#define SG_TLS 0x0FF80000u

static uint8_t **sg_read, **sg_write;
static uint64_t sg_state;

static uint64_t sg_next(void) {
    uint64_t z = (sg_state += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

/* a made-up word: often a pointer into the heap, often a small number */
static uint32_t sg_word(void) {
    uint64_t v = sg_next();
    switch (v & 7) {
    case 0: case 1: case 2:
        return SG_HEAP + ((uint32_t)(v >> 8) % SG_HEAP_SIZE & ~3u);
    case 3: case 4:
        return (uint32_t)(v >> 8) % 16u;
    case 5:
        return (uint32_t)(v >> 8) % 256u;
    case 6:
        return (uint32_t)0 - (uint32_t)(v >> 8) % 16u;
    default:
        return (uint32_t)(v >> 32);
    }
}

static void sg_region(uint32_t base, uint32_t size, const uint8_t *image, uint32_t image_size, int writable) {
    uint8_t *mem = rp_xalloc(size);
    for (uint32_t i = 0; i + 4 <= size; i += 4) {
        uint32_t w = sg_word();
        memcpy(mem + i, &w, 4);
    }
    if (image)
        memcpy(mem, image, image_size < size ? image_size : size);
    for (uint32_t p = 0; p < size; p += FE_CAP_PAGE_SIZE) {
        sg_read[(base + p) >> 12] = mem + p;
        sg_write[(base + p) >> 12] = writable ? mem + p : NULL;
    }
}

/* the host of the made-up game: pages without a pointer read 0 and drop
   writes (device memory); svc does nothing; the interpreter stops */
static uint8_t sg_read8(Context *c, uint32_t a) { (void)c; (void)a; return 0; }
static uint16_t sg_read16(Context *c, uint32_t a) { (void)c; (void)a; return 0; }
static uint32_t sg_read32(Context *c, uint32_t a) { (void)c; (void)a; return 0; }
static void sg_write8(Context *c, uint32_t a, uint8_t v) { (void)c; (void)a; (void)v; }
static void sg_write16(Context *c, uint32_t a, uint16_t v) { (void)c; (void)a; (void)v; }
static void sg_write32(Context *c, uint32_t a, uint32_t v) { (void)c; (void)a; (void)v; }
static void sg_interpret(Context *c, uint32_t address, uint32_t opcode) {
    (void)opcode;
    c->r[15] = address;
    c->exit = EXIT_UNWIND;
}
static void sg_svc(Context *c, uint32_t number) { (void)c; (void)number; }

/* a probe reached through the lookup in the made-up game: FE_PROBE's
   capture branch, as a probe override in the capture library runs it */
static void sg_probe_thunk(Context *ctx) {
    uint32_t a = ctx->r[15] | ctx->thumb;
    Code code = rp_find(a);
    if (code == NULL) {
        ctx->exit = EXIT_UNWIND;
        return;
    }
    (void)fe_capture_call(ctx, a, code, FE_CAP_KIND_PROBE);
}

static Code sg_lookup(Context *c, uint32_t address) {
    (void)c;
    Code code = rp_find(address);
    if (code && rp_in_list(rp_probe_list, rp_probe_count, address))
        return sg_probe_thunk;
    return code;
}

static const Host sg_host = {sg_read8, sg_read16, sg_read32, sg_write8, sg_write16, sg_write32,
                             sg_interpret, sg_lookup, sg_svc};

/* an argument: r0 is mostly an object (this, or a struct pointer), the
   others a mix */
static uint32_t sg_arg(int k) {
    uint64_t v = sg_next();
    if (k == 0 && (v & 0x300) != 0)
        return SG_HEAP + ((uint32_t)(v >> 16) % SG_HEAP_SIZE & ~3u);
    switch (v & 7) {
    case 0: case 1: case 2: case 3:
        return SG_HEAP + ((uint32_t)(v >> 8) % SG_HEAP_SIZE & ~3u);
    case 4: case 5:
        return (uint32_t)(v >> 8) % 16u;
    case 6:
        return (uint32_t)(v >> 8) % 256u;
    default:
        return (uint32_t)(v >> 32);
    }
}

static int cmd_synth(const RpOpts *o) {
    uint32_t *addrs = NULL, n = 0;
    if (o->addrs == NULL || !strcmp(o->addrs, "all")) {
        n = fe_replay_override_count;
        addrs = rp_xalloc((n + 1) * sizeof *addrs);
        for (uint32_t i = 0; i < n; i++)
            addrs[i] = fe_replay_overrides[i].address;
    } else {
        n = rp_parse_list(o->addrs, &addrs);
    }
    if (n == 0) {
        fprintf(stderr, "replay synth: no addresses\n");
        return 2;
    }
    uint8_t *image = NULL;
    uint32_t image_size = 0;
    if (o->image) {
        FILE *f = fopen(o->image, "rb");
        if (f == NULL) {
            fprintf(stderr, "replay synth: cannot read %s\n", o->image);
            return 3;
        }
        fseek(f, 0, SEEK_END);
        image_size = (uint32_t)ftell(f);
        fseek(f, 0, SEEK_SET);
        image = rp_xalloc(image_size);
        if (fread(image, 1, image_size, f) != image_size) {
            fclose(f);
            fprintf(stderr, "replay synth: short read of %s\n", o->image);
            return 3;
        }
        fclose(f);
    }
    sg_state = 0x5EED0000ull + o->seed;
    sg_read = rp_xalloc((1u << 20) * sizeof *sg_read);
    sg_write = rp_xalloc((1u << 20) * sizeof *sg_write);
    uint32_t low = image ? ((image_size + 0xFFFFFu) & ~0xFFFFFu) + 0x200000u : 0x00200000u;
    if (image) {
        sg_region(0x00100000u, low, image, image_size, 1); /* section bounds unknown here: all writable */
    } else { /* made-up layout (fakelib): read-only data below 0x00180000 */
        sg_region(0x00100000u, 0x00080000u, NULL, 0, 0);
        sg_region(0x00180000u, low - 0x00080000u, NULL, 0, 1);
    }
    sg_region(SG_HEAP, SG_HEAP_SIZE, NULL, 0, 1);
    sg_region(SG_STACK, SG_STACK_SIZE, NULL, 0, 1);

    /* the capture runtime: store every record of these functions */
    char only[4096];
    size_t used = 0;
    only[0] = 0;
    for (uint32_t i = 0; i < n && used + 10 < sizeof only; i++)
        used += (size_t)snprintf(only + used, sizeof only - used, "%s%08X", i ? "," : "", (unsigned)addrs[i]);
    FeCapConfig cfg;
    memset(&cfg, 0, sizeof cfg);
    cfg.dir = o->dir;
    cfg.only = only;
    cfg.store = 1;
    cfg.live = o->live && !strcmp(o->live, "a") ? FE_CAP_LIVE_A : FE_CAP_LIVE_AB;
    cfg.guard = o->guard ? (uint32_t)strtoul(o->guard, NULL, 16) : 0;
    fe_capture_configure(&cfg);
    fe_force_mode(FE_MODE_CAPTURE);

    static uint32_t vfp[32], fpscr;
    uint32_t calls = o->calls ? o->calls : 12;
    for (uint32_t c = 0; c < calls; c++)
        for (uint32_t i = 0; i < n; i++) {
            uint32_t a = addrs[i];
            Context ctx;
            memset(&ctx, 0, sizeof ctx);
            for (int k = 0; k < 4; k++)
                ctx.r[k] = sg_arg(k);
            for (int k = 4; k < 13; k++)
                ctx.r[k] = sg_word();
            for (int k = 0; k < 32; k++)
                vfp[k] = (uint32_t)sg_next();
            fpscr = 0x03000000u; /* round to nearest, flush to zero, default NaN: the 3DS default */
            ctx.r[13] = SG_SP;
            ctx.r[14] = RP_RETURN;
            ctx.r[15] = a & ~1u;
            ctx.thumb = (uint8_t)(a & 1u);
            ctx.tls = SG_TLS;
            ctx.budget = RP_BUDGET;
            ctx.depth = 1;
            ctx.vfp = vfp;
            ctx.fpscr = &fpscr;
            ctx.read_pages = (uint8_t *const *)sg_read;
            ctx.write_pages = (uint8_t *const *)sg_write;
            ctx.host = &sg_host;
            const FeReplayOverride *nat = rp_native(a);
            if (nat)
                nat->code(&ctx); /* FE_ENTRY's capture branch: original, record, runs A and B */
            else if (rp_find(a))
                (void)fe_capture_call(&ctx, a, fe_stub_original, FE_CAP_KIND_PROBE);
        }
    FeCapStats st;
    fe_capture_stats(&st);
    fe_capture_flush();
    printf("synth: %u function(s) x %u call(s): %u sampled, %u record(s) written, %u page file(s), %" PRIu64
           " bytes;",
           (unsigned)n, (unsigned)calls, (unsigned)st.sampled, (unsigned)st.records_written, (unsigned)st.pages_written,
           st.bytes_written);
    for (int v = 1; v < FE_CAP_V_COUNT; v++)
        printf(" %s %u%s", rp_vname((uint32_t)v), (unsigned)st.verdicts[v], v + 1 < FE_CAP_V_COUNT ? "," : "\n");
    /* the working set is the point of synth: keep it (reset closes the
       files without store mode's clean-up, which is for real sessions) */
    fe_capture_reset();
    return 0;
}

/* ------------------------------------------------------------------------ */

static int usage(void) {
    fprintf(stderr, "usage: replay run|synth|list [options] (see tools/harness/replay.c)\n");
    return 2;
}

int main(int argc, char **argv) {
    if (argc < 2)
        return usage();
    const char *cmd = argv[1];
    if (!strcmp(cmd, "list")) {
        for (unsigned i = 0; i < fe_replay_override_count; i++)
            printf("0x%08X %s\n", (unsigned)fe_replay_overrides[i].address, fe_replay_overrides[i].name);
        return 0;
    }
    RpOpts o;
    memset(&o, 0, sizeof o);
    const char *probes = NULL;
    for (int i = 2; i < argc; i++) {
        const char *k = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (v == NULL)
            return usage();
        i++;
        if (!strcmp(k, "--lib"))
            o.lib = v;
        else if (!strcmp(k, "--dir"))
            o.dir = v;
        else if (!strcmp(k, "--side"))
            o.side = v;
        else if (!strcmp(k, "--out"))
            o.out = v;
        else if (!strcmp(k, "--only"))
            o.only_count = rp_parse_list(v, &o.only);
        else if (!strcmp(k, "--wide"))
            o.wide_count = rp_parse_list(v, &o.wide);
        else if (!strcmp(k, "--probes"))
            probes = v;
        else if (!strcmp(k, "--image"))
            o.image = v;
        else if (!strcmp(k, "--addrs"))
            o.addrs = v;
        else if (!strcmp(k, "--calls"))
            o.calls = (uint32_t)strtoul(v, NULL, 10);
        else if (!strcmp(k, "--seed"))
            o.seed = (uint32_t)strtoul(v, NULL, 10);
        else if (!strcmp(k, "--guard"))
            o.guard = v;
        else if (!strcmp(k, "--live"))
            o.live = v;
        else
            return usage();
    }
    if (o.lib == NULL || o.dir == NULL)
        return usage();
    if (!rp_dir_ok(o.dir) || (o.out && !rp_dir_ok(o.out))) {
        fprintf(stderr, "replay: %s refused: folders and files must be below build/ (records hold game memory)\n",
                o.dir);
        return 2;
    }
    if (o.side && strcmp(o.side, "readable") && strcmp(o.side, "original"))
        return usage();
    rp_probe_count = rp_parse_list(probes, &rp_probe_list);
    if (!rp_load(o.lib))
        return 3;
    if (!strcmp(cmd, "run")) {
        fe_force_mode(FE_MODE_READABLE); /* this program's FE_ENTRY; the library reads FE_READABLE=original */
        return cmd_run(&o);
    }
    if (!strcmp(cmd, "synth"))
        return cmd_synth(&o);
    return usage();
}
