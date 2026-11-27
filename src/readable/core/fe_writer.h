/* The writer gate and the writer undo log (docs/WRITERS.md; F-006 "writers
   wait", F-017).

   A readable *writer* stores guest memory on purpose (an option the player
   set, a value the game should hold). Every writer is compiled in and OFF.
   This header is the only way a readable writer may store:

   - fe_writer_begin opens a session for one writer. It refuses (returns 0,
     nothing is stored) unless ALL of these hold:
       1. the writer is armed in the table of src/readable/core/writer.c (the
          `armed` column; every writer is 0 there, and changing it is a source
          edit that needs robot H6 and the owner's OK, docs/WRITERS.md);
       2. its name is listed in the environment variable FE_WRITERS
          (comma-separated, read once);
       3. the readable layer runs in readable mode (FE_READABLE=readable).
          Shadow, capture and original mode never run a writer: begin
          refuses and counts the refusal (fe_writer_refusals).
     Nothing else is read: no registry status, no harness report, no file. A
     green report switches nothing on.
   - fe_writer_store stores 1, 2 or 4 bytes inside an open session and logs
     (address, size, old value, new value, writer id, frame, session) first.
     Outside a session it stores nothing and counts a stray store.
   - fe_writer_call runs a guest function inside an open session with every
     store it makes logged the same way (write_pages is pointed at a table of
     null pointers so each store reaches the gate's host callback, as in
     src/readable/core/undo.c).
   - fe_writer_end keeps the session's stores (keep = 1, no failure) or puts
     every old byte back, newest first.
   - fe_writer_undo_last rolls back the newest kept session exactly: only when
     every byte it changed still holds the value it stored (else nothing is
     changed and FE_WRITER_CONFLICT comes back: the game has stored since).

   Memory is bounded: FE_WRITER_LOG_MAX entries, static. When a new store does
   not fit, the oldest KEPT sessions are dropped whole (they can no longer be
   undone; fe_writer_dropped counts them); when the open session alone does
   not fit, the store is refused and the session fails (it rolls back).

   A session fails for good (every store of it is put back at its end) on: a
   store to a byte without a direct page pointer (device or host memory, or
   an undo.c frame or capture already holding write_pages), a full log, an
   svc or an escape to the interpreter inside fe_writer_call, ctx->exit set.

   One session at a time, on one Context and one host thread (an atomic flag:
   a second begin from anywhere returns 0).

   Writers are never overrides: no 3dsrecomp marker, never run by FE_ENTRY,
   by verify or by shadow mode. Tested on fakes only
   (src/readable/core/tests/writer_gate_test.py). UNVERIFIED in a game: no
   writer has run inside Fates. */

#ifndef FE_WRITER_H
#define FE_WRITER_H

#include <stdint.h>

#include "fe.h"

/* writer ids (the table in writer.c gives each its FE_WRITERS name) */
enum {
    FE_WRITER_NONE = 0,
    FE_WRITER_CONFIG_OPTIONS = 1, /* src/readable/menu/menu_config_writer.c: "config_options" */
    FE_WRITER_CONFIG_OPTIONS_HOOK = 2, /* W1, src/readable/menu/menu_options_hook.c: "config_options_hook" (the apply
                                          hook: stores nothing itself, calls config_options) */
    FE_WRITER_CONFIG_SAVE_GUARD = 3,   /* W2, src/readable/menu/menu_options_hook.c: "config_save_guard" (writes the
                                          save stream in place of GameConfigData::Serialize) */
    FE_WRITER_COUNT
};

#define FE_WRITER_LOG_MAX 8192u /* entries kept, all sessions together (about 200 KB) */

/* The gate's run totals, for the capture run summary (summary.tsv's "# writers:" line, written by
   src/readable/core/capture.c; tools/harness/parallel.py reads it into summary.json): with them "no
   writer stored anything" is read directly from a run. The array lives in src/readable/core/runtime.c,
   which every build with capture.c links, so capture.c needs no writer.c; writer.c keeps it current.
   Counts since the library loaded (fe_writer_test_reset clears them in the host tests). */
enum {
    FE_WT_LOG = 0,       /* entries in the undo log now (fe_writer_log_count) */
    FE_WT_STORES,        /* stores made and logged, ever (a session rolled back still counts them) */
    FE_WT_RESTORED,      /* log entries put back (rollback or undo) */
    FE_WT_SESSIONS,      /* sessions opened */
    FE_WT_REFUSALS,      /* fe_writer_begin refused: a writer off (fe_writer_refusals) */
    FE_WT_MODE_REFUSALS, /* of those, refused because the mode is not readable (fe_writer_mode_refusals) */
    FE_WT_STRAY,         /* a store or call outside a session: nothing stored (fe_writer_stray_stores) */
    FE_WT_DROPPED,       /* kept sessions dropped whole from a full log (fe_writer_dropped) */
    FE_WT_COUNT
};
#define FE_WT_NAMES {"log", "stores", "restored", "sessions", "refusals", "mode_refusals", "stray", "dropped"}
extern uint32_t fe_writer_totals[FE_WT_COUNT];

/* results of fe_writer_end / fe_writer_undo_last / a writer */
enum {
    FE_WRITER_OK = 0,         /* stored (end: kept) / rolled back (undo) */
    FE_WRITER_OFF = 1,        /* the writer is off: nothing stored */
    FE_WRITER_REFUSED = 2,    /* the input was refused before any store */
    FE_WRITER_ROLLED_BACK = 3,/* a failure: every store of the session was put back */
    FE_WRITER_CONFLICT = 4,   /* undo: a byte no longer holds what was stored; nothing changed */
    FE_WRITER_NOTHING = 5     /* undo: no kept session in the log */
};

/* why a session failed (fe_writer_failure) */
enum {
    FE_WRITER_FAIL_NONE = 0,
    FE_WRITER_FAIL_HOSTMEM = 1,  /* a byte without a direct page pointer */
    FE_WRITER_FAIL_FULL = 2,     /* the open session alone fills the log */
    FE_WRITER_FAIL_SVC = 3,      /* an svc inside fe_writer_call */
    FE_WRITER_FAIL_INTERP = 4,   /* an escape to the interpreter inside fe_writer_call */
    FE_WRITER_FAIL_EXIT = 5,     /* ctx->exit was set (a guest call stopped) */
    FE_WRITER_FAIL_SIZE = 6      /* a store size other than 1, 2, 4 */
};

typedef struct FeWriterEntry {
    uint32_t address;  /* guest address */
    uint32_t size;     /* 1, 2 or 4 */
    uint32_t old_value;
    uint32_t new_value;
    uint32_t writer;   /* FE_WRITER_* id */
    uint32_t frame;    /* fe_writer_set_frame at the time of the store */
    uint32_t session;  /* numbered from 1 */
} FeWriterEntry;

/* the switch: 1 only when armed in writer.c, listed in FE_WRITERS, and the
   mode is readable. Never changes anything. */
int fe_writer_switched_on(int writer);
const char *fe_writer_name(int writer);

/* the frame number written into each entry (the caller's game frame) */
void fe_writer_set_frame(uint32_t frame);

/* a session: 1 = open; 0 = refused (off, shadow, busy, unknown id) */
int fe_writer_begin(Context *ctx, int writer);
/* 1 = stored and logged; 0 = refused (no session, the session failed, or it
   cannot be undone); the session then rolls back at its end */
int fe_writer_store(Context *ctx, gaddr address, uint32_t size, uint32_t value);
/* a guest call with every store logged; 0 and the session failed when the
   call stopped (as guest_call) */
uint32_t fe_writer_call(Context *ctx, gaddr function, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3);
/* closes the session: FE_WRITER_OK (kept) or FE_WRITER_ROLLED_BACK */
int fe_writer_end(Context *ctx, int keep);
int fe_writer_open(void);          /* 1 while a session is open */
int fe_writer_failure(void);       /* FE_WRITER_FAIL_* of the open session */

/* undo of the newest kept session (see above) */
int fe_writer_undo_last(Context *ctx);

/* the log, oldest first */
uint32_t fe_writer_log_count(void);
int fe_writer_log_entry(uint32_t index, FeWriterEntry *out);

/* counters: refused begins (off or wrong mode), begins refused in a mode
   that is not readable, stray stores, sessions dropped from a full log */
uint32_t fe_writer_refusals(void);
uint32_t fe_writer_mode_refusals(void);
uint32_t fe_writer_stray_stores(void);
uint32_t fe_writer_dropped(void);

#ifdef FE_WRITER_TESTS
/* host tests only (never defined in a library build): arm a writer, set the
   FE_WRITERS list without the environment, clear everything */
void fe_writer_test_arm(int writer, int armed);
void fe_writer_test_switches(const char *list);
void fe_writer_test_reset(void);
#endif

#endif /* FE_WRITER_H */
