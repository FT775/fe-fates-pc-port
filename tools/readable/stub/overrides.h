/* SYNTAX-CHECK STAND-IN for the "overrides.h" that `3dsrecomp build` generates.

   Written by this project from 3dsrecomp's documentation (docs/interface.md and
   docs/overrides.md, read 2026-11-09 at commit df82e6e); it is not 3dsrecomp
   code, which has no licence and is never copied here. It declares only what
   the readable layer uses, with the documented meaning, so that
   `python tools/readable/check.py` can compile src/readable/ with the host gcc
   before Rust and 3dsrecomp are installed. A real build never sees this file:
   3dsrecomp writes its own overrides.h (recomp.h plus the generated
   `original_<address>` functions) next to the generated C, and compiles the
   staged override files against that (docs/READABLE.md, "Building").

   If 3dsrecomp's interface changes (RECOMP_ABI above 5), re-read its docs and
   update this file and include/readable/fe_guest.h together. */

/* No include guard on purpose: the overrides.h 3dsrecomp generates has none,
   so including it twice must fail here too (include/readable/ guards it). */

#include <stdint.h>
#include <string.h>

#define FE_STUB_RECOMP_ABI 5 /* the interface version this stand-in describes */

typedef struct Context Context;
typedef void (*Code)(Context *);

/* the host's callbacks (interface.md, "Host callbacks") */
typedef struct Host {
    uint8_t (*read8)(Context *, uint32_t);
    uint16_t (*read16)(Context *, uint32_t);
    uint32_t (*read32)(Context *, uint32_t);
    void (*write8)(Context *, uint32_t, uint8_t);
    void (*write16)(Context *, uint32_t, uint16_t);
    void (*write32)(Context *, uint32_t, uint32_t);
    void (*interpret)(Context *, uint32_t address, uint32_t opcode);
    Code (*lookup)(Context *, uint32_t address);
    void (*svc)(Context *, uint32_t number);
} Host;

/* why code returned to the host (interface.md, "Exits") */
enum { EXIT_NONE, EXIT_SVC, EXIT_BUDGET, EXIT_UNWIND };

/* the guest CPU state the code works on (interface.md, "The context") */
struct Context {
    uint32_t r[16];
    uint8_t n, z, c, v, q, thumb, ge;
    uint8_t exclusive;
    int32_t budget;
    uint32_t exit;
    uint32_t svc;
    uint32_t depth;
    uint32_t exclusive_address;
    uint32_t tls;
    uint8_t *const *read_pages;
    uint8_t *const *write_pages;
    uint32_t *vfp;
    uint32_t *fpscr;
    const Host *host;
    void *user;
};

/* guest calls nested deeper than this unwind to the host (interface.md, "Calls") */
#define RECOMP_DEPTH_LIMIT 2048

/* memory helpers: direct page access, else the host callbacks (interface.md,
   "Memory"). Same names and arguments as the real ones; simplified bodies. */
static inline uint8_t fe_stub_page_read8(Context *ctx, uint32_t a) {
    uint8_t *page = ctx->read_pages[a >> 12];
    return page ? page[a & 0xFFF] : ctx->host->read8(ctx, a);
}
static inline uint16_t fe_stub_read16(Context *ctx, uint32_t a) { return ctx->host->read16(ctx, a); }
static inline uint32_t fe_stub_read32(Context *ctx, uint32_t a) { return ctx->host->read32(ctx, a); }
#define mem_read8(c, address) fe_stub_page_read8((c), (address))
#define mem_read16(c, address) fe_stub_read16((c), (address))
#define mem_read32(c, address) fe_stub_read32((c), (address))
#define mem_write8(c, address, value) ((c)->host->write8((c), (address), (value)))
#define mem_write16(c, address, value) ((c)->host->write16((c), (address), (value)))
#define mem_write32(c, address, value) ((c)->host->write32((c), (address), (value)))

/* overrides keep nothing in locals, so these do nothing (overrides.md) */
#define SYNC_OUT() do { } while (0)
#define SYNC_IN() do { } while (0)

/* a guest call of generated code, leaving the caller when the host must take over */
#define CALL(code) do { \
    SYNC_OUT(); \
    if (++ctx->depth > RECOMP_DEPTH_LIMIT) { ctx->depth--; ctx->exit = EXIT_UNWIND; return; } \
    code(ctx); \
    ctx->depth--; \
    if (ctx->exit) return; \
    SYNC_IN(); \
} while (0)

/* return to a guest address, switching to Thumb when bit 0 is set */
#define RETURN_TO(value) do { \
    uint32_t fe_stub_v_ = (value); \
    SYNC_OUT(); \
    ctx->thumb = fe_stub_v_ & 1u; \
    ctx->r[15] = fe_stub_v_ & (ctx->thumb ? ~1u : ~3u); \
    return; \
} while (0)

/* an override of the function at address (overrides.md, "Writing one") */
#define RECOMP_OVERRIDE(address) void override_##address(Context *ctx)

/* the generated function an override replaces. The real header defines one
   original_<address> per override; the stand-in maps them all to one
   declaration, so a mistyped address is caught by tools/readable/check.py's
   lint, not by this compile. */
void fe_stub_original(Context *ctx);
#define RECOMP_ORIGINAL(address) fe_stub_original

