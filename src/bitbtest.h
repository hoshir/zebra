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



extern BitBoard bb_flips;

extern int (REGPARM(2) * const TestFlips_bitboard[78])(unsigned int, unsigned int, unsigned int, unsigned int);



#endif  /* BITBTEST_H */
