/*
   File:          bitbtest.c

   Authors:       Gunnar Andersson (gunnar@radagast.se)
	          Toshihiko Okuhara

   Contents:      Count flips and returns new_my_bits in bb_flips.

   The 32-bit implementation carried one hand-unrolled function per
   square, most of whose bulk dealt with flip lines crossing the
   boundary between the two halves of the board.  With the board in a
   single 64-bit word there is no boundary, and one branch-free routine
   working from precomputed ray masks covers every square: along each
   ray the discs between the played square and the nearest own disc are
   flipped if and only if they are all the opponent's.

   This piece of software is released under the GPL.
   See the file COPYING for more information.
*/

#include <stdlib.h>

#include "macros.h"
#include "bitboard.h"
#include "bitbtest.h"




/* The highest set bit of (b | 1) — bit 0 stands in for "none" and is
   voided by the t != 0 guard at the use site. */

static INLINE BitBoard
highest_guarded_bit( BitBoard b ) {
#if defined( __GNUC__ )
  return 0x8000000000000000ull >> __builtin_clzll( b | 1 );
#else
  BitBoard h = b | 1;
  h |= h >> 1;
  h |= h >> 2;
  h |= h >> 4;
  h |= h >> 8;
  h |= h >> 16;
  h |= h >> 32;
  return h - (h >> 1);
#endif
}


int
TestFlips_bitboard_to( int sq, BitBoard my_bits, BitBoard opp_bits,
		       BitBoard *new_my_bits ) {
  const FlipRays *r = &flip_rays[bit_position[sq]];
  BitBoard flips = 0;
  BitBoard ray, t, f;
  int i;

  for ( i = 0; i < 4; i++ ) {
    /* Towards higher bits: the flip candidates sit below the nearest
       own disc (t & -t) and above the played square. */
    ray = r->dn[i];
    t = my_bits & ray;
    f = ((t & -t) - 1) & ray;
    f &= -(BitBoard) (t != 0);
    f &= -(BitBoard) ((f & ~opp_bits) == 0);
    flips |= f;
  }

  for ( i = 0; i < 4; i++ ) {
    /* Towards lower bits: above the nearest own disc instead. */
    ray = r->up[i];
    t = my_bits & ray;
    f = ray & ~((highest_guarded_bit( t ) << 1) - 1);
    f &= -(BitBoard) (t != 0);
    f &= -(BitBoard) ((f & ~opp_bits) == 0);
    flips |= f;
  }

  *new_my_bits = my_bits | flips | square_mask[sq];

  return non_iterative_popcount( flips );
}


/*
  The endgame keeps the result in BB_FLIPS and reads it back some way
  after the call -- across a shallow midgame search, in the
  fastest-first ordering -- so anything that flips discs on the side
  must leave that variable alone and use TestFlips_bitboard_to.
*/

int
TestFlips_bitboard( int sq, BitBoard my_bits, BitBoard opp_bits ) {
  return TestFlips_bitboard_to( sq, my_bits, opp_bits, &bb_flips );
}
