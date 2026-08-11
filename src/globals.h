/*
   File:           globals.h

   Created:        June 30, 1997

   Author:         Gunnar Andersson (gunnar@radagast.se)

   Contents:       Global state variables.
*/



#ifndef GLOBALS_H
#define GLOBALS_H



#include "bitboard.h"
#include "constant.h"



/* The basic board type. One index for each position;
   a1=11, h1=18, a8=81, h8=88. */
typedef int Board[128];



/* pv[n][n..<depth>] contains the principal variation from the
   node on recursion depth n on the current recursive call sequence.
   After the search, pv[0][0..<depth>] contains the principal
   variation from the root position. */
extern _Thread_local int pv[MAX_SEARCH_DEPTH][MAX_SEARCH_DEPTH];

/* pv_depth[n] contains the depth of the principal variation
   starting at level n in the call sequence.
   After the search, pv[0] holds the depth of the principal variation
   from the root position. */
extern _Thread_local int pv_depth[MAX_SEARCH_DEPTH];

/* piece_count[col][n] holds the number of disks of color col after
   n moves have been played. */
extern _Thread_local int piece_count[3][MAX_SEARCH_DEPTH];

/* These variables hold the game score. The meaning is similar
   to how a human would fill out a game score except for that
   the row counter, score_sheet_row, starts at zero. */
extern int score_sheet_row;
extern int black_moves[60];
extern int white_moves[60];

/* Holds the current board position. Updated as the search progresses,
   but all updates must be reversed when the search stops. */
extern _Thread_local Board board;

/* The same position as BOARD, one bit per square, indexed by colour.
   Maintained by MAKE_MOVE and UNMAKE_MOVE alongside the array, and
   resynchronised from it by SET_BOARD_BITS wherever the array is set
   up wholesale. */
extern _Thread_local BitBoard board_bits[3];

void
set_board_bits( void );


#endif  /* GLOBALS_H */
