/*
   File:       globals.c

   Created:    June 30, 1997

   Author:     Gunnar Andersson (gunnar@radagast.se)

   Contents:   Global state variables.
*/



#include "globals.h"


/* Global variables */

_Thread_local BitBoard board_bits[3];

_Thread_local int pv[MAX_SEARCH_DEPTH][MAX_SEARCH_DEPTH];
_Thread_local int pv_depth[MAX_SEARCH_DEPTH];
int score_sheet_row;
_Thread_local int piece_count[3][MAX_SEARCH_DEPTH];
int black_moves[60];
int white_moves[60];
_Thread_local Board board;


/*
  SET_BOARD_BITS
  Rebuild the bitboards from the array board.  Called wherever the
  array is set up other than by MAKE_MOVE -- the same places that
  resynchronise the hash code and the evaluation pattern indices.
*/

void
set_board_bits( void ) {
  int i, j;

  board_bits[BLACKSQ] = 0;
  board_bits[WHITESQ] = 0;
  board_bits[EMPTY] = 0;

  for ( i = 1; i <= 8; i++ )
    for ( j = 1; j <= 8; j++ ) {
      int pos = 10 * i + j;
      if ( board[pos] == BLACKSQ )
	board_bits[BLACKSQ] |= square_mask[pos];
      else if ( board[pos] == WHITESQ )
	board_bits[WHITESQ] |= square_mask[pos];
    }
}
