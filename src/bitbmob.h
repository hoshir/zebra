/*
   File:          bitbmob.h

   Created:       November 22, 1999
   
   Authors:       Gunnar Andersson (gunnar@radagast.se)

   Contents:
*/



#ifndef BITBMOB_H
#define BITBMOB_H

#include "bitboard.h"
#include "end.h"

/* Column a and h cleared, so that +-1, +-7 and +-9 shifts do not wrap
   across the board edge.  The +-8 shifts use the unmasked discs. */
#define INNER_MASK  0x7E7E7E7E7E7E7E7Eull

static INLINE BitBoard
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

static INLINE BitBoard
bitboard_moves( const BitBoard my_bits,
		const BitBoard opp_bits ) {
  return generate_all_c( my_bits, opp_bits );
}

static INLINE int
bitboard_mobility( const BitBoard my_bits,
		   const BitBoard opp_bits ) {
  return non_iterative_popcount( generate_all_c( my_bits, opp_bits ) );
}

static INLINE int
weighted_mobility( const BitBoard my_bits,
		   const BitBoard opp_bits ) {
  BitBoard moves = generate_all_c( my_bits, opp_bits );

  /* 128 * (#moves + #corner moves) */
  return 128 * ( non_iterative_popcount( moves ) +
		 non_iterative_popcount( moves & 0x8100000000000081ull ) );
}

#endif  /* BITBMOB_H */
