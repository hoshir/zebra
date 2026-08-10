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



BitBoard
bitboard_moves( const BitBoard my_bits,
		const BitBoard opp_bits );



int
weighted_mobility( const BitBoard my_bits,
		   const BitBoard opp_bits );



int
bitboard_mobility( const BitBoard my_bits,
		   const BitBoard opp_bits );



#endif  /* BITBMOB_H */
