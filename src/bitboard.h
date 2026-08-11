/*
   File:          bitboard.h

   Created:       November 21, 1999

   Author:        Gunnar Andersson (gunnar@radagast.se)
                  Toshihiko Okuhara

   Contents:      The bitboard is a single 64-bit word.  Bit 0 is a1,
                  bit 7 is h1 and bit 63 is h8: the bit for row i,
                  column j (both 1-based) is 8*(i-1) + (j-1).
*/



#ifndef BITBOARD_H
#define BITBOARD_H

#include "macros.h"


typedef unsigned long long BitBoard;


/* The operation macros predate the 64-bit representation, when every
   one of them took two statements.  Kept so their call sites read the
   same as they always have. */

#define APPLY_NOT( a )          ((a) = ~(a))

#define APPLY_XOR( a, b )       ((a) ^= (b))

#define APPLY_OR( a, b )        ((a) |= (b))

#define APPLY_AND( a, b )       ((a) &= (b))

#define APPLY_ANDNOT( a, b )    ((a) &= ~(b))

#define FULL_XOR( a, b, c )     ((a) = (b) ^ (c))

#define FULL_OR( a, b, c )      ((a) = (b) | (c))

#define FULL_AND( a, b, c )     ((a) = (b) & (c))

#define FULL_ANDNOT( a, b, c )  ((a) = (b) & ~(c))

#define CLEAR( a )              ((a) = 0)


extern BitBoard square_mask[100];

/* Conversion from a board coordinate (11..88) to the bit index. */
extern int bit_position[100];

/* The squares a flip line through a given square can run over,
   one mask per ray.  The "down" rays run towards higher bit indices
   (E, S, SE, SW), the "up" rays towards lower ones (W, N, NW, NE). */

typedef struct {
  BitBoard dn[4];
  BitBoard up[4];
} FlipRays;

extern FlipRays flip_rays[64];



unsigned int REGPARM(1)
non_iterative_popcount( BitBoard b );

unsigned int REGPARM(1)
iterative_popcount( BitBoard b );

unsigned int REGPARM(1)
bit_reverse_32( unsigned int val );

void
set_bitboards( int *board, int side_to_move,
	       BitBoard *my_out, BitBoard *opp_out );

void
init_bitboard( void );



#endif  /* BITBOARD_H */
