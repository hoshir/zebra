/*
   File:          bitbmob.c

   Authors:       Gunnar Andersson (gunnar@radagast.se)
	          Toshihiko Okuhara

   Contents:      Count feasible moves in the bitboard.

   The move generation is a fill along each of the four direction
   pairs: two masked shift-and steps pick up runs of one and two
   opponent discs, two more double the reach to cover runs up to six,
   and a final shift lands on the square beyond the run.  This is the
   same algorithm the 32-bit version implemented in split halves (and
   in MMX assembly on the Pentium, dropped along with the split
   representation).

   This piece of software is released under the GPL.
   See the file COPYING for more information.
*/



#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

#include "bitbmob.h"
#include "bitboard.h"


/* Column a and h cleared, so that +-1, +-7 and +-9 shifts do not wrap
   across the board edge.  The +-8 shifts use the unmasked discs. */
#define INNER_MASK  0x7E7E7E7E7E7E7E7Eull


static BitBoard
generate_all_c( const BitBoard my_bits,
	        const BitBoard opp_bits ) {
  BitBoard moves;
  BitBoard flip_bits;
  BitBoard adjacent_opp_bits;
  const BitBoard opp_inner_bits = opp_bits & INNER_MASK;

#define MOBILITY_PAIR( o, shift ) \
  flip_bits = (my_bits >> shift) & (o); \
  flip_bits |= (flip_bits >> shift) & (o); \
  adjacent_opp_bits = (o) & ((o) >> shift); \
  flip_bits |= (flip_bits >> (2 * shift)) & adjacent_opp_bits; \
  flip_bits |= (flip_bits >> (2 * shift)) & adjacent_opp_bits; \
  moves |= flip_bits >> shift; \
  flip_bits = (my_bits << shift) & (o); \
  flip_bits |= (flip_bits << shift) & (o); \
  adjacent_opp_bits = (o) & ((o) << shift); \
  flip_bits |= (flip_bits << (2 * shift)) & adjacent_opp_bits; \
  flip_bits |= (flip_bits << (2 * shift)) & adjacent_opp_bits; \
  moves |= flip_bits << shift

  moves = 0;
  MOBILITY_PAIR( opp_inner_bits, 1 );
  MOBILITY_PAIR( opp_bits, 8 );
  MOBILITY_PAIR( opp_inner_bits, 7 );
  MOBILITY_PAIR( opp_inner_bits, 9 );

#undef MOBILITY_PAIR

  moves &= ~(my_bits | opp_bits);
  return moves;
}


/*
  BITBOARD_MOVES
  Every square where the side to move has a legal move.  A move is
  legal exactly when it turns a disc, so this is the same set the
  array-board test produces, one square at a time.
*/

BitBoard
bitboard_moves( const BitBoard my_bits,
		const BitBoard opp_bits ) {
  return generate_all_c( my_bits, opp_bits );
}


int
bitboard_mobility( const BitBoard my_bits,
		   const BitBoard opp_bits ) {
  return non_iterative_popcount( generate_all_c( my_bits, opp_bits ) );
}


int
weighted_mobility( const BitBoard my_bits,
		   const BitBoard opp_bits ) {
  BitBoard moves = generate_all_c( my_bits, opp_bits );

  /* 128 * (#moves + #corner moves) */
  return 128 * ( non_iterative_popcount( moves ) +
		 non_iterative_popcount( moves & 0x8100000000000081ull ) );
}
