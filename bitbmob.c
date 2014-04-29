/*
   File:          bitbmob.c

   Modified:      November 18, 2005

   Authors:       Gunnar Andersson (gunnar@radagast.se)
              Toshihiko Okuhara

   Contents:      Count feasible moves in the bitboard.

   This piece of software is released under the GPL.
   See the file COPYING for more information.
*/



#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

#include "bitbmob.h"
#include "bitboard.h"


void
init_mmx( void ) {
}


static BitBoard
generate_all_c( const BitBoard my_bits,     // mm7
                const BitBoard opp_bits ) { // mm6
    BitBoard moves;       // mm4
    BitBoard opp_inner_bits;  // mm5
    BitBoard flip_bits;       // mm1
    BitBoard adjacent_opp_bits;   // mm3

    opp_inner_bits.high = opp_bits.high & 0x7E7E7E7Eu;
    opp_inner_bits.low = opp_bits.low & 0x7E7E7E7Eu;

    flip_bits.high = (my_bits.high >> 1) & opp_inner_bits.high;       /* 0 m7&o6 m6&o5 .. m2&o1 0 */
    flip_bits.low = (my_bits.low >> 1) & opp_inner_bits.low;
    flip_bits.high |= (flip_bits.high >> 1) & opp_inner_bits.high;    /* 0 m7&o6 (m6&o5)|(m7&o6&o5) .. (m2&o1)|(m3&o2&o1) 0 */
    flip_bits.low |= (flip_bits.low >> 1) & opp_inner_bits.low;

    adjacent_opp_bits.high = opp_inner_bits.high & (opp_inner_bits.high >> 1);    /* 0 o7&o6 o6&o5 o5&o4 o4&o3 o3&o2 o2&o1 0 */
    adjacent_opp_bits.low = opp_inner_bits.low & (opp_inner_bits.low >> 1);
    flip_bits.high |= (flip_bits.high >> 2) & adjacent_opp_bits.high; /* 0 m7&o6 (m6&o5)|(m7&o6&o5) ..|(m7&o6&o5&o4) ..|(m6&o5&o4&o3)|(m7&o6&o5&o4&o3) .. */
    flip_bits.low |= (flip_bits.low >> 2) & adjacent_opp_bits.low;
    flip_bits.high |= (flip_bits.high >> 2) & adjacent_opp_bits.high;
    flip_bits.low |= (flip_bits.low >> 2) & adjacent_opp_bits.low;

    moves.high = flip_bits.high >> 1;
    moves.low = flip_bits.low >> 1;

    flip_bits.high = (my_bits.high << 1) & opp_inner_bits.high;
    flip_bits.low = (my_bits.low << 1) & opp_inner_bits.low;
    flip_bits.high |= (flip_bits.high << 1) & opp_inner_bits.high;
    flip_bits.low |= (flip_bits.low << 1) & opp_inner_bits.low;

    adjacent_opp_bits.high = opp_inner_bits.high & (opp_inner_bits.high << 1);
    adjacent_opp_bits.low = opp_inner_bits.low & (opp_inner_bits.low << 1);
    flip_bits.high |= (flip_bits.high << 2) & adjacent_opp_bits.high;
    flip_bits.low |= (flip_bits.low << 2) & adjacent_opp_bits.low;
    flip_bits.high |= (flip_bits.high << 2) & adjacent_opp_bits.high;
    flip_bits.low |= (flip_bits.low << 2) & adjacent_opp_bits.low;

    moves.high |= flip_bits.high << 1;
    moves.low |= flip_bits.low << 1;

    flip_bits.high = (my_bits.high >> 8) & opp_bits.high;
    flip_bits.low = ((my_bits.low >> 8) | (my_bits.high << 24)) & opp_bits.low;
    flip_bits.high |= (flip_bits.high >> 8) & opp_bits.high;
    flip_bits.low |= ((flip_bits.low >> 8) | (flip_bits.high << 24)) & opp_bits.low;

    adjacent_opp_bits.high = opp_bits.high & (opp_bits.high >> 8);
    adjacent_opp_bits.low = opp_bits.low & ((opp_bits.low >> 8) | (opp_bits.high << 24));
    flip_bits.high |= (flip_bits.high >> 16) & adjacent_opp_bits.high;
    flip_bits.low |= ((flip_bits.low >> 16) | (flip_bits.high << 16)) & adjacent_opp_bits.low;
    flip_bits.high |= (flip_bits.high >> 16) & adjacent_opp_bits.high;
    flip_bits.low |= ((flip_bits.low >> 16) | (flip_bits.high << 16)) & adjacent_opp_bits.low;

    moves.high |= flip_bits.high >> 8;
    moves.low |= (flip_bits.low >> 8) | (flip_bits.high << 24);

    flip_bits.high = ((my_bits.high << 8) | (my_bits.low >> 24)) & opp_bits.high;
    flip_bits.low = (my_bits.low << 8) & opp_bits.low;
    flip_bits.high |= ((flip_bits.high << 8) | (flip_bits.low >> 24)) & opp_bits.high;
    flip_bits.low |= (flip_bits.low << 8) & opp_bits.low;

    adjacent_opp_bits.high = opp_bits.high & ((opp_bits.high << 8) | (opp_bits.low >> 24));
    adjacent_opp_bits.low = opp_bits.low & (opp_bits.low << 8);
    flip_bits.high |= ((flip_bits.high << 16) | (flip_bits.low >> 16)) & adjacent_opp_bits.high;
    flip_bits.low |= (flip_bits.low << 16) & adjacent_opp_bits.low;
    flip_bits.high |= ((flip_bits.high << 16) | (flip_bits.low >> 16)) & adjacent_opp_bits.high;
    flip_bits.low |= (flip_bits.low << 16) & adjacent_opp_bits.low;

    moves.high |= (flip_bits.high << 8) | (flip_bits.low >> 24);
    moves.low |= flip_bits.low << 8;

    flip_bits.high = (my_bits.high >> 7) & opp_inner_bits.high;
    flip_bits.low = ((my_bits.low >> 7) | (my_bits.high << 25)) & opp_inner_bits.low;
    flip_bits.high |= (flip_bits.high >> 7) & opp_inner_bits.high;
    flip_bits.low |= ((flip_bits.low >> 7) | (flip_bits.high << 25)) & opp_inner_bits.low;

    adjacent_opp_bits.high = opp_inner_bits.high & (opp_inner_bits.high >> 7);
    adjacent_opp_bits.low = opp_inner_bits.low & ((opp_inner_bits.low >> 7) | (opp_inner_bits.high << 25));
    flip_bits.high |= (flip_bits.high >> 14) & adjacent_opp_bits.high;
    flip_bits.low |= ((flip_bits.low >> 14) | (flip_bits.high << 18)) & adjacent_opp_bits.low;
    flip_bits.high |= (flip_bits.high >> 14) & adjacent_opp_bits.high;
    flip_bits.low |= ((flip_bits.low >> 14) | (flip_bits.high << 18)) & adjacent_opp_bits.low;

    moves.high |= flip_bits.high >> 7;
    moves.low |= (flip_bits.low >> 7) | (flip_bits.high << 25);

    flip_bits.high = ((my_bits.high << 7) | (my_bits.low >> 25)) & opp_inner_bits.high;
    flip_bits.low = (my_bits.low << 7) & opp_inner_bits.low;
    flip_bits.high |= ((flip_bits.high << 7) | (flip_bits.low >> 25)) & opp_inner_bits.high;
    flip_bits.low |= (flip_bits.low << 7) & opp_inner_bits.low;

    adjacent_opp_bits.high = opp_inner_bits.high & ((opp_inner_bits.high << 7) | (opp_inner_bits.low >> 25));
    adjacent_opp_bits.low = opp_inner_bits.low & (opp_inner_bits.low << 7);
    flip_bits.high |= ((flip_bits.high << 14) | (flip_bits.low >> 18)) & adjacent_opp_bits.high;
    flip_bits.low |= (flip_bits.low << 14) & adjacent_opp_bits.low;
    flip_bits.high |= ((flip_bits.high << 14) | (flip_bits.low >> 18)) & adjacent_opp_bits.high;
    flip_bits.low |= (flip_bits.low << 14) & adjacent_opp_bits.low;

    moves.high |= (flip_bits.high << 7) | (flip_bits.low >> 25);
    moves.low |= flip_bits.low << 7;

    flip_bits.high = (my_bits.high >> 9) & opp_inner_bits.high;
    flip_bits.low = ((my_bits.low >> 9) | (my_bits.high << 23)) & opp_inner_bits.low;
    flip_bits.high |= (flip_bits.high >> 9) & opp_inner_bits.high;
    flip_bits.low |= ((flip_bits.low >> 9) | (flip_bits.high << 23)) & opp_inner_bits.low;

    adjacent_opp_bits.high = opp_inner_bits.high & (opp_inner_bits.high >> 9);
    adjacent_opp_bits.low = opp_inner_bits.low & ((opp_inner_bits.low >> 9) | (opp_inner_bits.high << 23));
    flip_bits.high |= (flip_bits.high >> 18) & adjacent_opp_bits.high;
    flip_bits.low |= ((flip_bits.low >> 18) | (flip_bits.high << 14)) & adjacent_opp_bits.low;
    flip_bits.high |= (flip_bits.high >> 18) & adjacent_opp_bits.high;
    flip_bits.low |= ((flip_bits.low >> 18) | (flip_bits.high << 14)) & adjacent_opp_bits.low;

    moves.high |= flip_bits.high >> 9;
    moves.low |= (flip_bits.low >> 9) | (flip_bits.high << 23);

    flip_bits.high = ((my_bits.high << 9) | (my_bits.low >> 23)) & opp_inner_bits.high;
    flip_bits.low = (my_bits.low << 9) & opp_inner_bits.low;
    flip_bits.high |= ((flip_bits.high << 9) | (flip_bits.low >> 23)) & opp_inner_bits.high;
    flip_bits.low |= (flip_bits.low << 9) & opp_inner_bits.low;

    adjacent_opp_bits.high = opp_inner_bits.high & ((opp_inner_bits.high << 9) | (opp_inner_bits.low >> 23));
    adjacent_opp_bits.low = opp_inner_bits.low & (opp_inner_bits.low << 9);
    flip_bits.high |= ((flip_bits.high << 18) | (flip_bits.low >> 14)) & adjacent_opp_bits.high;
    flip_bits.low |= (flip_bits.low << 18) & adjacent_opp_bits.low;
    flip_bits.high |= ((flip_bits.high << 18) | (flip_bits.low >> 14)) & adjacent_opp_bits.high;
    flip_bits.low |= (flip_bits.low << 18) & adjacent_opp_bits.low;

    moves.high |= (flip_bits.high << 9) | (flip_bits.low >> 23);
    moves.low |= flip_bits.low << 9;

    moves.high &= ~(my_bits.high | opp_bits.high);
    moves.low &= ~(my_bits.low | opp_bits.low);
    return moves;
}

int
bitboard_mobility( const BitBoard my_bits,
                   const BitBoard opp_bits ) {
    BitBoard moves;
    unsigned int count;

    moves = generate_all_c( my_bits, opp_bits );
    count = non_iterative_popcount( moves.high, moves.low );

    return count;
}


int
weighted_mobility( const BitBoard my_bits,
                   const BitBoard opp_bits ) {
    unsigned int n1, n2;
    BitBoard moves;

    moves = generate_all_c( my_bits, opp_bits );

    n1 = moves.high - ((moves.high >> 1) & 0x15555555u) + (moves.high & 0x01000000u); /* corner bonus for A1/H1/A8/H8 */
    n2 = moves.low - ((moves.low >> 1) & 0x55555515u) + (moves.low & 0x00000001u);
    n1 = (n1 & 0x33333333u) + ((n1 >> 2) & 0x33333333u);
    n2 = (n2 & 0x33333333u) + ((n2 >> 2) & 0x33333333u);
    n1 = (n1 + (n1 >> 4)) & 0x0F0F0F0Fu;
    n1 += (n2 + (n2 >> 4)) & 0x0F0F0F0Fu;

    return ((n1 * 0x01010101u) >> 24) * 128;
}
