/* Capture mode of the readable layer: record what a real guest function sees
   and does while the real game runs, and compare it live
   (docs/HARNESS.md 3.1, 4.4, 4.5, 5).

   Opt-in only: FE_READABLE=capture. In every other mode nothing here runs
   (except fe_probe_note, which does nothing until a replay tool registers a
   sink). In capture mode every override and every harness probe runs the
   game's original, so the game goes on exactly as in original mode; a
   sampled call is recorded on the way:

   1. ctx->read_pages, ctx->write_pages and ctx->host are saved, both page
      tables point at one all-null table and host at the recording host, so
      every guest load and store of the original (and of every generated
      callee, which gets the same ctx) reaches our callbacks.
   2. The callbacks copy each 4 KiB page on its first access, before the
      access (the page's value at function entry), keep read and write
      bitmaps, log every write in order (address, width, old, new), forward
      lookup / interpret / svc to the real host and mark the record ESCAPED
      for the last two.
   3. The three fields are put back on every way out: normal return, budget
      or svc exit, unwind, and the depth-limit refusal.

   Zakuro's callbacks reach the machine only through ctx->user, which stays
   untouched; around every forwarded callback the real fields are put back
   anyway, so the real host never sees the capture tables.

   Live comparison (the owner's storage policy, 2026-11-10: compare in the
   run, keep only what is needed for debugging): right after a valid record
   is finished, still in the same process,
   - run A replays the original on a private copy of the record's entry
     pages (all accesses go to that copy, never to the game) and must give
     the recorded exit registers, final bytes, probe calls and lookups
     (fidelity gate: otherwise UNFAITHFUL);
   - run B (overrides only) runs the readable function through the FE_ENTRY
     capture branch on another fresh copy and is compared with run A: r0,
     every final byte outside the call's dead stack, probe calls (a callee
     of run A that run B never called counts as done inline: info), escapes.
   The snapshot is then dropped. Only records with a bad verdict (MISMATCH,
   UNFAITHFUL, B-ESCAPED; at most FE_CAPTURE_KEEP per function) are written
   to disk, plus summary.tsv (one row per function: verdict, counts, path
   signatures). FE_CAPTURE_STORE=1 together with FE_CAPTURE_ONLY writes
   every record of those few functions (iterating on one failing function);
   if the session then ends with no bad verdict, the files it wrote are
   removed (records.fecap is cut back to its size before the session; page
   files that were already there stay). summary.tsv is per session: give
   each run its own folder (harness.py merges them).

   Settings (read once, on the first captured call):
     FE_CAPTURE_DIR     folder for summary.tsv, records.fecap and pages/; must
                        be below the build/ or play/ folder at the root of a
                        git checkout, with no ".." (records hold game memory).
                        Unset: compare live, write nothing.
     FE_CAPTURE_ONLY    addr,addr,... capture only these (hex, 0x optional)
     FE_CAPTURE_MAX_MB  hard cap on bytes written to disk, default 256
     FE_CAPTURE_KEEP    bad records kept per function, default 4
     FE_CAPTURE_STORE   1 = write every record (only with FE_CAPTURE_ONLY)
     FE_CAPTURE_LIVE    ab (default) = runs A and B; a = fidelity gate only
     FE_CAPTURE_GUARD   one-time guard routine (hex), default FE_GAME_GUARD_ENTRY
                        (generated fe_game.h; Fates: 0x00302C6D, Thumb): a
                        record during which it was called is tagged COLD,
                        others WARM (needs the routine to be a probe)
     FE_CAPTURE_LATE    1 (default in the game) = when run B reads a page
                        the record does not have, take it from the game's
                        memory (a "late page", HARNESS.md 5 rule 5) and add
                        it to the record; 0 = such a read is B_ESCAPED.
                        Tools that set the settings with fe_capture_configure
                        get late pages only with FeCapConfig.late = 1, so
                        synth runs keep offline = live on made-up memory.

   Host callbacks seen while records are open (lookups, interpreter steps,
   svcs, device memory accesses, and the lookups of runs A and B) are
   counted per kind and target and written to callbacks.tsv next to
   summary.tsv, so a run shows which ones the capture forwarded (Grok's
   point 4: checked, not assumed, to be free of side effects).

   Every name starts with fe_ / FE_ (see fe_guest.h). Never write the
   3dsrecomp override marker in this header (stage.py pastes it). */

#ifndef FE_CAPTURE_H
#define FE_CAPTURE_H

#include <stdint.h>
#include <stdio.h>

#if defined(_WIN32)
#define FE_EXPORT __declspec(dllexport) /* found by replay tools with GetProcAddress */
#else
#define FE_EXPORT __attribute__((visibility("default")))
#endif

/* ------------------------------------------------------------------------
   Sampling and limits */

#define FE_CAP_FIRST 16           /* every call up to this one is sampled ... */
#define FE_CAP_PER_ADDRESS 48     /* ... then calls 32, 64, 128 ...; at most this many records */
#define FE_CAP_MAX_DEPTH 4        /* nested records (a captured call inside a captured call) */
#define FE_CAP_TRACKED 8192       /* addresses counted (own table, not runtime.c's fe_counts) */
#define FE_CAP_MAX_PAGES 1024     /* pages per record (4 MiB) before it is TRUNCATED */
#define FE_CAP_MAX_EVENTS (1u << 20)
#define FE_CAP_MAX_LOOKUPS (1u << 14)
#define FE_CAP_MAX_NOTES (1u << 14)
#define FE_CAP_MAX_SIGNATURES 16  /* distinct path signatures remembered per function */
#define FE_CAP_DEFAULT_MAX_MB 256u
#define FE_CAP_DEFAULT_KEEP 4u
#include "fe_game.h" /* generated: this game's guard routine (config/readable/addresses.json) */
#define FE_CAP_DEFAULT_GUARD FE_GAME_GUARD_ENTRY
/* bytes below the entry sp that count as the call's own dead stack when run
   B is compared with run A (frames of the call and its callees) [med] */
#define FE_CAP_STACK_WINDOW 0x10000u

/* ------------------------------------------------------------------------
   Record format (.fecap). Every field is a little-endian 32-bit word, so the
   structs have no padding and are written as they are. records.fecap is the
   records one after another; each starts with FeCapHeader, then page_count
   FeCapPage, event_count FeCapEvent, lookup_count FeCapLookup, note_count
   FeCapNote. Page bytes (4096 each, the value at the record's entry) are
   stored once per session in pages/<32 hex digits of hash>.pg. */

#define FE_CAP_MAGIC "FECAP1\r\n" /* 8 bytes, no terminator stored */
#define FE_CAP_VERSION 2u
#define FE_CAP_PAGE_SIZE 4096u

/* record flags */
#define FE_CAP_VALID 0x0001u          /* complete, no escape, no host memory, not truncated */
#define FE_CAP_INCOMPLETE 0x0002u     /* the original stopped inside (budget, svc, unwind) */
#define FE_CAP_ESCAPED_SVC 0x0004u    /* an svc ran inside: system memory changed unseen */
#define FE_CAP_ESCAPED_INTERP 0x0008u /* the interpreter ran inside: accesses unseen */
#define FE_CAP_HOSTMEM_R 0x0010u      /* read a page the real host handles itself (device) */
#define FE_CAP_HOSTMEM_W 0x0020u      /* wrote a page with no writable pointer */
#define FE_CAP_TRUNCATED 0x0040u      /* a per-record cap was hit: logs are not whole */
#define FE_CAP_NESTED 0x0080u         /* recorded inside another record */
#define FE_CAP_COLD 0x0100u           /* the one-time guard routine ran: cold cache path */
#define FE_CAP_NOT_VALID (FE_CAP_INCOMPLETE | FE_CAP_ESCAPED_SVC | FE_CAP_ESCAPED_INTERP | \
                          FE_CAP_HOSTMEM_R | FE_CAP_HOSTMEM_W | FE_CAP_TRUNCATED)

/* what was captured: an FE_ENTRY override or an FE_PROBE */
enum { FE_CAP_KIND_OVERRIDE = 0, FE_CAP_KIND_PROBE = 1 };
/* FeCapNote.kind in runs A and B only (never in a stored record; HARNESS.md 5
   rule 4): bits 0-7 the kind, bits 8-12 the callee's argument registers
   (FE_CAP_ARGS_KNOWN | bit n for r_n, found by FE_ENTRY; 0 = not known, as for
   probes), bits 16-31 how many noted calls were open (0 = a call the run made
   itself). fe_capture_call takes the argument bits in bits 8-12 of its kind. */
#define FE_CAP_ARGS_KNOWN 0x10u
/* r_n while FE_ENTRY finds the bits: far apart, so FE_ARG(n) + a small number is no marker */
#define FE_CAP_ARG_MARK_OF(n) (0xFEA7A000u + (uint32_t)(n) * 0x00100011u)
#define FE_CAP_NOTE_ARGS(kind) (((kind) >> 8) & 0x1Fu)
#define FE_CAP_NOTE_NEST(kind) ((kind) >> 16)

/* verdict of one record (docs/HARNESS.md 5, "Verdicts") */
enum {
    FE_CAP_V_NONE = 0,       /* not decided (never stored) */
    FE_CAP_V_MATCH,          /* run B = run A */
    FE_CAP_V_MISMATCH_R0,    /* run B returned another r0 */
    FE_CAP_V_MISMATCH_MEM,   /* a final byte differs outside the dead stack */
    FE_CAP_V_MISMATCH_CALLS, /* the probe calls differ */
    FE_CAP_V_GAVE_UP,        /* the readable function gave up on this record */
    FE_CAP_V_B_ESCAPED,      /* run B hit svc, the interpreter or memory outside the record */
    FE_CAP_V_FAITHFUL,       /* run A only (probes, FE_CAPTURE_LIVE=a): A reproduced the record */
    FE_CAP_V_UNFAITHFUL,     /* run A did not reproduce the record: excluded */
    FE_CAP_V_INCOMPLETE,     /* the original stopped inside: not replayed */
    FE_CAP_V_ESCAPED,        /* an svc or the interpreter ran inside: not replayed */
    FE_CAP_V_HOSTMEM,        /* device memory was touched: not replayed */
    FE_CAP_V_TRUNCATED,      /* a per-record cap was hit: not replayed */
    FE_CAP_V_COUNT
};
#define FE_CAP_V_NAMES {"none", "match", "mismatch_r0", "mismatch_mem", "mismatch_calls", "gave_up", \
                        "b_escaped", "faithful", "unfaithful", "incomplete", "escaped", "hostmem", "truncated"}

typedef struct FeCapRegs {
    uint32_t r[16];
    uint32_t n, z, c, v, q, thumb, ge, exclusive;
    uint32_t exclusive_address, tls;
    int32_t budget;
    uint32_t fpscr;
    uint32_t vfp[32];
} FeCapRegs;

typedef struct FeCapHeader {
    char magic[8];
    uint32_t version, header_bytes, record_bytes; /* record_bytes: the whole record */
    uint32_t address, kind, call_number, sequence, depth, flags, exit_code;
    uint32_t verdict, signature; /* FE_CAP_V_*; path signature of run A (0 = none) */
    uint32_t page_count, event_count, lookup_count, note_count;
    FeCapRegs entry, exit;
} FeCapHeader;

/* page flags */
#define FE_CAP_PAGE_COPIED 0x1u   /* entry bytes stored (hash names the .pg file) */
#define FE_CAP_PAGE_HOSTMEM 0x2u  /* no readable pointer: no bytes, accesses went to the host */
#define FE_CAP_PAGE_NO_WRITE 0x4u /* no writable pointer in the real game */
#define FE_CAP_PAGE_LATE 0x8u     /* added for run B: a page the call never touched, read from the game
                                     right after the call (its value at entry); no read or write bits */

typedef struct FeCapPage {
    uint32_t address; /* page base */
    uint32_t flags;
    uint32_t hash[4]; /* of the entry bytes; zero when not COPIED */
    uint8_t read_bits[FE_CAP_PAGE_SIZE / 8];  /* bit i = byte i was read */
    uint8_t write_bits[FE_CAP_PAGE_SIZE / 8]; /* bit i = byte i was written */
} FeCapPage;

/* event kinds (low byte of FeCapEvent.kind; width in bytes in the next byte) */
#define FE_CAP_EV_WRITE 1u         /* old = value before, new = value written */
#define FE_CAP_EV_HOST_READ 2u     /* a read of a host-handled page: new = value read */
#define FE_CAP_EV_HOSTMEM 0x10000u /* flag: the access went to the real host's callback */

typedef struct FeCapEvent {
    uint32_t kind, address, old_value, new_value;
} FeCapEvent;

typedef struct FeCapLookup {
    uint32_t address, found;
} FeCapLookup;

typedef struct FeCapNote { /* a call of an override or probe inside the record */
    uint32_t callee, kind, r[4];
} FeCapNote;

_Static_assert(sizeof(FeCapRegs) == 60 * 4, "FeCapRegs must have no padding");
_Static_assert(sizeof(FeCapHeader) == 8 + 16 * 4 + 2 * sizeof(FeCapRegs), "FeCapHeader must have no padding");
_Static_assert(sizeof(FeCapPage) == 24 + FE_CAP_PAGE_SIZE / 4, "FeCapPage must have no padding");

/* ------------------------------------------------------------------------
   Entry points (src/readable/core/capture.c) */

/* FE_ENTRY's and FE_PROBE's capture branch: runs original (with the depth
   check of 3dsrecomp's CALL, so depth and exits behave as in original mode),
   recording it when this call is sampled. Returns 1 when a faithful record
   of an override waits for run B: the caller then calls
   fe_capture_b_begin, the readable function, and fe_capture_b_end. */
int fe_capture_call(Context *ctx, uint32_t address, Code original, int kind);
/* run B: 1 = ctx now holds the record's entry registers on a fresh copy of
   its pages, call the readable function; 0 = skip it. */
int fe_capture_b_begin(Context *ctx);
/* compares run B (result = the readable function's r0; a give-up is read
   from ctx->exit) with run A, and puts the game's state back exactly. */
void fe_capture_b_end(Context *ctx, uint32_t result);

/* FE_PROBE outside capture mode: tells a replay tool's sink about the call
   (callee, r0-r3 are in ctx). Does nothing while no sink is registered. */
void fe_probe_note(Context *ctx, uint32_t address);
typedef void (*FeProbeSink)(Context *ctx, uint32_t callee);
FE_EXPORT void fe_probe_set_sink(FeProbeSink sink);

/* sampling rule: is call number n (1-based) of an address sampled? */
int fe_capture_sampled(uint32_t n);

/* kinds of host callbacks counted in callbacks.tsv (FeCapStats.callbacks) */
enum {
    FE_CAP_CB_LOOKUP = 0,    /* lookup forwarded while recording (key: target address) */
    FE_CAP_CB_LOOKUP_MISS,   /* ... that found no code */
    FE_CAP_CB_INTERPRET,     /* interpreter step forwarded (key: address); the record is ESCAPED */
    FE_CAP_CB_SVC,           /* svc forwarded (key: svc number); the record is ESCAPED */
    FE_CAP_CB_HOST_READ,     /* read of a page the host handles (key: page) */
    FE_CAP_CB_HOST_WRITE,    /* write to a page the host handles (key: page) */
    FE_CAP_CB_REPLAY_LOOKUP, /* lookup forwarded from run A or run B (key: target address) */
    FE_CAP_CB_KINDS
};
#define FE_CAP_CB_NAMES {"lookup", "lookup_miss", "interpret", "svc", "host_read", "host_write", "replay_lookup"}
#define FE_CAP_CB_TRACKED 4096 /* distinct (kind, key) pairs listed in callbacks.tsv */

typedef struct FeCapStats {
    uint32_t calls, sampled, busy_skips, untracked;
    uint32_t records_written, records_dropped, pages_written, pages_deduped;
    uint32_t calls_inlined; /* run A callee calls run B did not make (info, HARNESS.md 5 rule 4) */
    uint32_t late_pages;    /* pages run B read that the call never touched, taken from the game */
    uint32_t callbacks[FE_CAP_CB_KINDS]; /* host callbacks seen, by FE_CAP_CB_* */
    uint64_t bytes_written;
    uint32_t verdicts[FE_CAP_V_COUNT];
} FeCapStats;
void fe_capture_stats(FeCapStats *out);

/* per function (one row of summary.tsv) */
typedef struct FeCapFnStats {
    uint32_t address, kind, calls, records;
    uint32_t verdicts[FE_CAP_V_COUNT];
    uint32_t cold, warm, deep, kept, signature_count;
    uint32_t signatures[FE_CAP_MAX_SIGNATURES], signature_hits[FE_CAP_MAX_SIGNATURES];
    const char *verdict; /* REPLAY-CLEAN | SHALLOW | PARTIAL | MISMATCH | A-CLEAN | UNFAITHFUL | NO-DATA */
} FeCapFnStats;
/* 0 when the address was never seen in capture mode */
int fe_capture_fn_stats(uint32_t address, FeCapFnStats *out);

/* the last finished record (tests and debug tools) */
typedef struct FeCapInfo {
    uint32_t address, kind, call_number, sequence, depth, flags, exit_code, verdict, signature;
    uint32_t page_count, event_count, lookup_count, note_count, stored;
    char detail[160]; /* first difference, for bad verdicts */
} FeCapInfo;
void fe_capture_last(FeCapInfo *out);

/* tests and tools: set the settings instead of the environment. NULL = read
   the environment again; zero fields = defaults. */
enum { FE_CAP_LIVE_AB = 0, FE_CAP_LIVE_A = 1 };
/* store: 0 off, 1 every record (removed at the end when all passed), FE_CAP_STORE_KEEP every
   record, never removed (FE_CAPTURE_STORE=keep) */
enum { FE_CAP_STORE_KEEP = 2 };
typedef struct FeCapConfig {
    const char *dir, *only;
    uint32_t max_mb, keep, guard, max_pages;
    int store, live;
    uint64_t max_bytes; /* tests: overrides max_mb when not 0 */
    int late;           /* 1 = late pages for run B (zero = off here, unlike FE_CAPTURE_LATE) */
} FeCapConfig;
void fe_capture_configure(const FeCapConfig *config);
/* forget everything (frees memory, closes files, clears counts); never call
   it while a call is being captured */
void fe_capture_reset(void);
/* writes summary.tsv and flushes records.fecap (also every 256 records) */
void fe_capture_flush(void);
/* end of session (also at exit): flush, and in store mode (not FE_CAP_STORE_KEEP)
   with no bad verdict remove the files this session wrote */
void fe_capture_finish(void);

/* src/readable/core/runtime.c: the readable layer's log (FE_READABLE_LOG or stderr) */
FILE *fe_log_stream(void);

#endif /* FE_CAPTURE_H */
