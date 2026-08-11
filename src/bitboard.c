/*
   File:          bitboard.c

   Created:       November 21, 1999

   Authors:       Gunnar Andersson (gunnar@radagast.se)
                  Toshihiko Okuhara

   Contents:      Basic bitboard manipulations
*/



#include "bitboard.h"
#include "constant.h"
#include "macros.h"



BitBoard square_mask[100];
int bit_position[100];
int square_of_bit[64];
FlipRays flip_rays[64];



/*
  NON_ITERATIVE_POPCOUNT
  Counts the number of bits set in a 64-bit integer.
*/

INLINE unsigned int REGPARM(1)
non_iterative_popcount( BitBoard b ) {
#if defined( __GNUC__ )
  /* Single hardware instruction on arm64 (cnt) and x86-64 (popcnt) */
  return __builtin_popcountll( b );
#else
  b = b - ((b >> 1) & 0x5555555555555555ull);
  b = (b & 0x3333333333333333ull) + ((b >> 2) & 0x3333333333333333ull);
  b = (b + (b >> 4)) & 0x0F0F0F0F0F0F0F0Full;
  return (b * 0x0101010101010101ull) >> 56;
#endif
}


/*
  ITERATIVE_POPCOUNT
  Counts the number of bits set in a 64-bit integer.
  Kept as a separate entry point for the callers that used to pick it
  for sparse words; both names are hardware popcounts nowadays.
*/

INLINE unsigned int REGPARM(1)
iterative_popcount( BitBoard b ) {
#if defined( __GNUC__ )
  return __builtin_popcountll( b );
#else
  unsigned int n;
  n = 0;
  for ( ; b != 0; n++, b &= (b - 1) )
    ;

  return n;
#endif
}



/*
  BIT_REVERSE_32
  Returns the bit-reverse of a 32-bit integer.
*/

unsigned int REGPARM(1)
bit_reverse_32( unsigned int val ) {
  val = ((val >>  1) & 0x55555555) | ((val <<  1) & 0xAAAAAAAA);
  val = ((val >>  2) & 0x33333333) | ((val <<  2) & 0xCCCCCCCC);
  val = ((val >>  4) & 0x0F0F0F0F) | ((val <<  4) & 0xF0F0F0F0);
  val = ((val >>  8) & 0x00FF00FF) | ((val <<  8) & 0xFF00FF00);
  val = ((val >> 16) & 0x0000FFFF) | ((val << 16) & 0xFFFF0000);

  return val;
}


/*
  SET_BITBOARDS
  Converts the vector board representation to the bitboard representation.
*/

void
set_bitboards( int *board, int side_to_move,
	       BitBoard *my_out, BitBoard *opp_out ) {
  int i, j;
  int pos;
  BitBoard mask;
  BitBoard my_bits, opp_bits;

  my_bits = 0;
  opp_bits = 0;

  mask = 1;
  for ( i = 1; i <= 8; i++ )
    for ( j = 1; j <= 8; j++, mask <<= 1 ) {
      pos = 10 * i + j;
      if ( board[pos] == side_to_move )
	my_bits |= mask;
      else if ( board[pos] == OPP( side_to_move ) )
	opp_bits |= mask;
    }

  *my_out = my_bits;
  *opp_out = opp_bits;
}



void
init_bitboard( void ) {
  int i, j, k;
  /* The rays in bit-index order: E, S, SE, SW ("down"),
     then W, N, NW, NE ("up").  Row and column steps per ray. */
  static const int dir_di[8] = { 0, 1, 1,  1,  0, -1, -1, -1 };
  static const int dir_dj[8] = { 1, 0, 1, -1, -1,  0, -1,  1 };

  for ( i = 1; i <= 8; i++ )
    for ( j = 1; j <= 8; j++ ) {
      int pos = 10 * i + j;
      int shift = 8 * (i - 1) + (j - 1);
      square_mask[pos] = 1ull << shift;
      bit_position[pos] = shift;
      square_of_bit[shift] = pos;
    }

  for ( i = 1; i <= 8; i++ )
    for ( j = 1; j <= 8; j++ ) {
      FlipRays *r = &flip_rays[8 * (i - 1) + (j - 1)];
      for ( k = 0; k < 8; k++ ) {
	BitBoard ray = 0;
	int ci = i + dir_di[k];
	int cj = j + dir_dj[k];
	while ( (ci >= 1) && (ci <= 8) && (cj >= 1) && (cj <= 8) ) {
	  ray |= 1ull << (8 * (ci - 1) + (cj - 1));
	  ci += dir_di[k];
	  cj += dir_dj[k];
	}
	if ( k < 4 )
	  r->dn[k] = ray;
	else
	  r->up[k - 4] = ray;
      }
    }
}
