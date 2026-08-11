/*
   File:          bitbtest.h

   Created:       November 22, 1999
   
   Authors:       Gunnar Andersson (gunnar@radagast.se)

   Contents:
*/



#ifndef BITBTEST_H
#define BITBTEST_H



#include "bitboard.h"
#include "macros.h"
#include "tlstate.h"




/* SQ is a board coordinate, 11..88.  The mover's discs with the
   turned ones added land in BB_FLIPS, which the endgame reads back
   well after the call; callers that only want the flips of a move
   they are making must use the _TO form and keep out of that
   variable. */
int
TestFlips_bitboard( int sq, BitBoard my_bits, BitBoard opp_bits );

int
TestFlips_bitboard_to( int sq, BitBoard my_bits, BitBoard opp_bits,
		       BitBoard *new_my_bits );



#endif  /* BITBTEST_H */
