/* Basic types of the readable layer (docs/READABLE.md). */

#ifndef FE_TYPES_H
#define FE_TYPES_H

#include <stdint.h>

/* A guest (3DS) address. Guest pointers are 32-bit and live in the guest's
   memory, which the host reaches only through the page tables, so readable
   code never turns one into a host pointer. 0 is the guest's null. */
typedef uint32_t gaddr;

#endif /* FE_TYPES_H */
