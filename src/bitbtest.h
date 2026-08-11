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



extern _Thread_local BitBoard bb_flips;

/* SQ is a board coordinate, 11..88. */
int
TestFlips_bitboard( int sq, BitBoard my_bits, BitBoard opp_bits );



#endif  /* BITBTEST_H */
