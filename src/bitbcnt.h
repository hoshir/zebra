/*
   File:          bitbcnt.h

   Created:       November 22, 1999
   
   Authors:       Gunnar Andersson (gunnar@radagast.se)

   Contents:
*/



#ifndef BITBCNT_H
#define BITBCNT_H



#include "bitboard.h"
#include "macros.h"



/* SQ is a board coordinate, 11..88.  Every square but SQ is assumed
   occupied: whatever is not in MY_BITS belongs to the opponent. */
int
CountFlips_bitboard( int sq, BitBoard my_bits );



#endif  /* BITBCNT_H */
