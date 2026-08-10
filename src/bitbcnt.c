/*
   File:          bitbcnt.c

   Authors:       Gunnar Andersson (gunnar@radagast.se)
	          Toshihiko Okuhara

   Contents:      Count the number of discs flipped by a move when
                  every square except the one being played is occupied,
                  so everything that is not the mover's is the
                  opponent's.  The endgame leaf code uses this for the
                  last empty square.

   Works from the same precomputed ray masks as TestFlips_bitboard in
   bitbtest.c; with the board full, the all-opponent test on the run of
   discs before the nearest own disc always holds, so it is dropped.

   This piece of software is released under the GPL.
   See the file COPYING for more information.
*/

#include "macros.h"	// REGPARM
#include "bitboard.h"
#include "bitbcnt.h"


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
CountFlips_bitboard( int sq, BitBoard my_bits ) {
  const FlipRays *r = &flip_rays[bit_position[sq]];
  BitBoard flips = 0;
  BitBoard ray, t, f;
  int i;

  for ( i = 0; i < 4; i++ ) {
    ray = r->dn[i];
    t = my_bits & ray;
    f = ((t & -t) - 1) & ray;
    f &= -(BitBoard) (t != 0);
    flips |= f;
  }

  for ( i = 0; i < 4; i++ ) {
    ray = r->up[i];
    t = my_bits & ray;
    f = ray & ~((highest_guarded_bit( t ) << 1) - 1);
    f &= -(BitBoard) (t != 0);
    flips |= f;
  }

  return non_iterative_popcount( flips );
}
