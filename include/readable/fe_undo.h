/* The undo log (docs/HARNESS.md H8 groundwork, docs/tracks/WRITER_HOOKS.md
   "The undo log", docs/READABLE.md "The undo log").

   DISABLED: nothing calls it yet. No FE_READABLE mode, no FE_ENTRY and no
   readable function opens a frame, so the shipped behaviour is unchanged.
   It exists so that a future writer hook can give up after it has stored,
   and the game still sees every byte as it was. Tested on a fake guest only
   (tools/readable/tests/undo_test.c).

   How it works. fe_undo_begin swaps two fields of the Context: write_pages
   becomes a table of null pointers, so every guest store reaches a host
   callback, and host becomes the undo host. read_pages stays real, so reads
   cost nothing and see the stores already made. The undo host's store
   callback appends the old byte of every byte it changes to one ordered log,
   then writes the new byte into the real page. fe_undo_end either keeps the
   stores or puts the old bytes back, newest first.

   Frames. One frame per nesting level (a writer that calls a writer), in a
   static stack, for one Context on one host thread. A second Context or
   thread cannot open a frame while one is open: fe_undo_begin returns 0 and
   the caller gives up before any store (runs the original).
   - An inner frame that keeps its stores merges them into its parent: the
     log entries stay, they now belong to the parent. Only the outermost
     frame truly commits (drops the log).
   - An inner frame that gives up restores only its own bytes.

   Giving up for good (the whole stack fails, every open frame must roll
   back; ctx->exit is set to EXIT_UNWIND so the guest code stops):
   - an svc: it is never forwarded. A thread switch inside it could change the
     bytes, so nothing may be rolled back after one;
   - a store to a page with no direct pointer (device or host memory): the
     store is dropped, it cannot be undone;
   - an escape to the interpreter: it is never forwarded (its stores would
     not be logged);
   - the log is full: the store that does not fit is dropped (never
     truncated: the older entries stay and are restored).
   fe_undo_end also rolls back when ctx->exit is set on the way out (budget,
   unwind, depth, a guest call that came back somewhere else).

   Every way out of the outermost frame puts write_pages and host back as
   they were at its begin (or as the host switched them inside a forwarded
   callback). read_pages is never changed.

   Under capture. A frame opened while capture.c is recording sees capture's
   null write table as the "real" one, so the first store gives up with
   FE_UNDO_FAIL_HOSTMEM: a writer can never commit while a capture is open
   (safe: the bytes are put back and the original runs). A capture of
   writers (H6/H8) must take that into account.

   Cost while unused. The core build stages every src/readable/core file, so
   this file is compiled into the readable and capture-library builds as
   dead code: about 576 KB of static log (FE_UNDO_MAX_BYTES host pointers
   plus old bytes). The 8 MB null table is allocated on the first
   fe_undo_begin only, so never today. */

#ifndef FE_UNDO_H
#define FE_UNDO_H

#include <stdint.h>

#include "fe.h"

#define FE_UNDO_MAX_DEPTH 32      /* nested frames */
#define FE_UNDO_MAX_BYTES 65536u  /* bytes logged at once, all frames together */

/* why the stack failed (fe_undo_failure) */
enum {
    FE_UNDO_OK = 0,
    FE_UNDO_FAIL_SVC = 1,       /* an svc was refused */
    FE_UNDO_FAIL_HOSTMEM = 2,   /* a store to a page without a direct pointer was dropped */
    FE_UNDO_FAIL_INTERP = 3,    /* an escape to the interpreter was refused */
    FE_UNDO_FAIL_OVERFLOW = 4   /* the log was full */
};

/* Opens a frame. 1 = open; 0 = cannot (another Context or thread holds the
   log, FE_UNDO_MAX_DEPTH frames are open, the null table could not be
   allocated, or the stack has already failed): the caller must give up before
   it stores anything. */
int fe_undo_begin(Context *ctx);

/* Closes the innermost frame. keep = 1 keeps its stores (merged into the
   parent, or committed when it is the outermost frame); keep = 0 restores
   them. The stores are restored anyway when ctx->exit is set or the stack has
   failed. Returns 1 when the stores were kept, 0 when they were restored.
   ctx->exit is left as it is: the caller decides what runs next. */
int fe_undo_end(Context *ctx, int keep);

int fe_undo_depth(void);          /* open frames (0 = the log is not in use) */
uint32_t fe_undo_logged(void);    /* bytes in the log now */
int fe_undo_failure(void);        /* FE_UNDO_OK or why the open stack failed */

/* tests only: a smaller log (0 = FE_UNDO_MAX_BYTES); refused while a frame is open */
int fe_undo_set_limit(uint32_t bytes);

#endif /* FE_UNDO_H */
