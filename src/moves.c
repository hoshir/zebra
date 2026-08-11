/*
   File:              moves.c

   Created:           June 30, 1997

   Author:            Gunnar Andersson (gunnar@radagast.se)

   Contents:          The move generator.
*/



#include <stdio.h>
#include <stdlib.h>
#include "bitbmob.h"
#include "bitbtest.h"
#include "cntflip.h"
#include "constant.h"
#include "doflip.h"
#include "globals.h"
#include "hash.h"
#include "macros.h"
#include "moves.h"
#include "patterns.h"
#include "search.h"
#include "texts.h"
#include "unflip.h"



/* Global variables */

_Thread_local int disks_played;
_Thread_local int move_count[MAX_SEARCH_DEPTH];
_Thread_local int move_list[MAX_SEARCH_DEPTH][64];
int *first_flip_direction[100];
int flip_direction[100][16];   /* 100 * 9 used */
int **first_flipped_disc[100];
int *flipped_disc[100][8];
const int dir_mask[100] = {
  0,   0,   0,   0,   0,   0,   0,   0,   0,   0,
  0,  81,  81,  87,  87,  87,  87,  22,  22,   0,
  0,  81,  81,  87,  87,  87,  87,  22,  22,   0,
  0, 121, 121, 255, 255, 255, 255, 182, 182,   0,
  0, 121, 121, 255, 255, 255, 255, 182, 182,   0,
  0, 121, 121, 255, 255, 255, 255, 182, 182,   0,
  0, 121, 121, 255, 255, 255, 255, 182, 182,   0,
  0,  41,  41, 171, 171, 171, 171, 162, 162,   0,
  0,  41,  41, 171, 171, 171, 171, 162, 162,   0,
  0,   0,   0,   0,   0,   0,   0,   0,   0,   0
};
const int move_offset[8] = { 1, -1, 9, -9, 10, -10, 11, -11 };


/* Local variables */

/* The discs turned by the move made at each stage, so that
   UNMAKE_MOVE can give them back without walking the board. */
static _Thread_local BitBoard flip_mask[65];



/*
  INIT_MOVES
  Initialize the move generation subsystem.
*/

void
init_moves( void ) {
  int i, j, k;
  int pos;
  int feasible;

  for ( i = 1; i <= 8; i++ )
    for ( j = 1; j <= 8; j++ ) {
      pos = 10 * i + j;
      for ( k = 0; k <= 8; k++ )
	flip_direction[pos][k] = 0;
      feasible = 0;
      for ( k = 0; k < 8; k++ )
	if ( dir_mask[pos] & (1 << k) ) {
	  flip_direction[pos][feasible] = move_offset[k];
	  feasible++;
	}
      first_flip_direction[pos] = &flip_direction[pos][0];
    }
}


/*
   GENERATE_SPECIFIC
*/

INLINE int
generate_specific( int curr_move, int side_to_move ) {
  return AnyFlips_compact( board, curr_move, side_to_move,
			   OPP( side_to_move ) );
}


/*
   GENERATE_ALL
   Generates a list containing all the moves possible in a position.

   Every legal move comes out of one bitboard fill, so the list is
   built by walking the move order once and keeping the squares the
   fill marked.  The order is the one the caller expects; only the
   legality test changed, from an eight-direction walk of the array
   per candidate square to a lookup in the mask.
*/

INLINE void
generate_all( int side_to_move ) {
  BitBoard moves = bitboard_moves( board_bits[side_to_move],
				   board_bits[OPP( side_to_move )] );
  const int *order = sorted_move_order[disks_played];
  int count = 0;
  int i;

  for ( i = 0; i < MOVE_ORDER_SIZE; i++ ) {
    int move = order[i];
    if ( moves & square_mask[move] ) {
      move_list[disks_played][count] = move;
      count++;
    }
  }

  move_list[disks_played][count] = ILLEGAL;
  move_count[disks_played] = count;
}


/*
  COUNT_ALL
  Counts the number of moves for one player.
*/

INLINE int
count_all( int side_to_move, int empty ) {
  int move;
  int move_index;
  int mobility;
  int found_empty;

  mobility = 0;
  found_empty = 0;
  for ( move_index = 0; move_index < MOVE_ORDER_SIZE; move_index++ ) {
    move = sorted_move_order[disks_played][move_index];
    if ( board[move] == EMPTY ) {
      if ( generate_specific( move, side_to_move ) )
	mobility++;
      found_empty++;
      if ( found_empty == empty )
	return mobility;
    }
  }

  return mobility;
}


/*
   GAME_IN_PROGRESS
   Determines if any of the players has a valid move.
*/

int
game_in_progress( void ) {
  int black_count, white_count;

  generate_all( BLACKSQ );
  black_count = move_count[disks_played];
  generate_all( WHITESQ );
  white_count = move_count[disks_played];

  return (black_count > 0) || (white_count > 0);
}


/*
  APPLY_FLIPS
  Write the discs turned by a move into the array board, and fold them
  into the hash difference when the caller wants one.  The mask comes
  straight out of the bitboard flip test, so there is nothing to look
  up first.
*/

static INLINE void
apply_flips( BitBoard mask, int side_to_move, int update_hash,
	     unsigned int *diff1, unsigned int *diff2 ) {
  unsigned int d1 = 0, d2 = 0;

  while ( mask != 0 ) {
    int sq = square_of_bit[FIRST_BIT( mask )];
    mask &= mask - 1;
    board[sq] = side_to_move;
    if ( update_hash ) {
      d1 ^= hash_flip1[sq];
      d2 ^= hash_flip2[sq];
    }
  }

  *diff1 = d1;
  *diff2 = d2;
}


/*
  UNDO_FLIPS
  Give the discs of MASK back to the opponent, in the array board, in
  the bitboards and in the pattern indices, and empty the played
  square.  BOARD[MOVE] has already been cleared by the caller.
*/

static INLINE void
undo_flips( BitBoard mask, int side_to_move, int move ) {
  int oppcol = OPP( side_to_move );
  BitBoard m = mask;

  while ( m != 0 ) {
    int sq = square_of_bit[FIRST_BIT( m ) ];
    m &= m - 1;
    board[sq] = oppcol;
  }

  board_bits[side_to_move] &= ~(mask | square_mask[move]);
  board_bits[oppcol] |= mask;

  update_pattern_indices( side_to_move, move, mask, -1 );
}


/*
   MAKE_MOVE
   side_to_move = the side that is making the move
   move = the position giving the move

   Makes the necessary changes on the board and updates the
   counters.

   The discs to turn are found with the bitboard flip test rather than
   by walking the array board in eight directions: it is branch-free,
   and the set of turned discs falls out as a mask, which is what the
   board write, the hash difference and the pattern indices all want.
*/

INLINE int
make_move( int side_to_move, int move, int update_hash ) {
  int flipped;
  unsigned int diff1, diff2;
  BitBoard my_bits = board_bits[side_to_move];
  BitBoard opp_bits = board_bits[OPP( side_to_move )];
  BitBoard mask, new_my_bits;

  flipped = TestFlips_bitboard_to( move, my_bits, opp_bits, &new_my_bits );
  if ( flipped == 0 )
    return 0;

  /* NEW_MY_BITS is the mover's discs with the turned ones and the
     played square added, so the turned ones alone are what it gained. */
  mask = new_my_bits & ~my_bits & ~square_mask[move];

  board_bits[side_to_move] = new_my_bits;
  board_bits[OPP( side_to_move )] = opp_bits & ~mask;
  flip_mask[disks_played] = mask;

  apply_flips( mask, side_to_move, update_hash, &diff1, &diff2 );

  hash_stored1[disks_played] = hash1;
  hash_stored2[disks_played] = hash2;
  if ( update_hash ) {
    hash1 ^= diff1 ^ hash_put_value1[side_to_move][move];
    hash2 ^= diff2 ^ hash_put_value2[side_to_move][move];
  }

  board[move] = side_to_move;
  update_pattern_indices( side_to_move, move, mask, 1 );

  if ( side_to_move == BLACKSQ ) {
    piece_count[BLACKSQ][disks_played + 1] =
      piece_count[BLACKSQ][disks_played] + flipped + 1;
    piece_count[WHITESQ][disks_played + 1] =
      piece_count[WHITESQ][disks_played] - flipped;
  }
  else {  /* side_to_move == WHITESQ */
    piece_count[WHITESQ][disks_played + 1] =
      piece_count[WHITESQ][disks_played] + flipped + 1;
    piece_count[BLACKSQ][disks_played + 1] =
      piece_count[BLACKSQ][disks_played] - flipped;
  }

  disks_played++;

  return flipped;
}


/*
   MAKE_MOVE_NO_HASH
   side_to_move = the side that is making the move
   move = the position giving the move

   Makes the necessary changes on the board. Note that the hash table
   is not updated - the move has to be unmade using UNMAKE_MOVE_NO_HASH().
*/


INLINE int
make_move_no_hash( int side_to_move, int move ) {
  int flipped;
  unsigned int diff1, diff2;
  BitBoard my_bits = board_bits[side_to_move];
  BitBoard opp_bits = board_bits[OPP( side_to_move )];
  BitBoard mask, new_my_bits;

  flipped = TestFlips_bitboard_to( move, my_bits, opp_bits, &new_my_bits );
  if ( flipped == 0 )
    return 0;

  mask = new_my_bits & ~my_bits & ~square_mask[move];

  board_bits[side_to_move] = new_my_bits;
  board_bits[OPP( side_to_move )] = opp_bits & ~mask;
  flip_mask[disks_played] = mask;

  apply_flips( mask, side_to_move, FALSE, &diff1, &diff2 );

  board[move] = side_to_move;
  update_pattern_indices( side_to_move, move, mask, 1 );

#if 1
  if ( side_to_move == BLACKSQ ) {
    piece_count[BLACKSQ][disks_played + 1] =
      piece_count[BLACKSQ][disks_played] + flipped + 1;
    piece_count[WHITESQ][disks_played + 1] =
      piece_count[WHITESQ][disks_played] - flipped;
  }
  else {  /* side_to_move == WHITESQ */
    piece_count[WHITESQ][disks_played + 1] =
      piece_count[WHITESQ][disks_played] + flipped + 1;
    piece_count[BLACKSQ][disks_played + 1] =
      piece_count[BLACKSQ][disks_played] - flipped;
  }
#else
  piece_count[side_to_move][disks_played + 1] =
    piece_count[side_to_move][disks_played] + flipped + 1;
  piece_count[OPP( side_to_move )][disks_played + 1] =
    piece_count[OPP( side_to_move )][disks_played] - flipped;
#endif
  disks_played++;

  return flipped;
}


/*
  UNMAKE_MOVE
  Takes back a move.
*/

INLINE void
unmake_move( int side_to_move, int move ) {
  board[move] = EMPTY;

  disks_played--;

  hash1 = hash_stored1[disks_played];
  hash2 = hash_stored2[disks_played];

  undo_flips( flip_mask[disks_played], side_to_move, move );
}


/*
  UNMAKE_MOVE_NO_HASH
  Takes back a move. Only to be called when the move was made without
  updating hash table, preferrable through MAKE_MOVE_NO_HASH().
*/

INLINE void
unmake_move_no_hash( int side_to_move, int move ) {
  board[move] = EMPTY;

  disks_played--;

  undo_flips( flip_mask[disks_played], side_to_move, move );
}


/*
   VALID_MOVE
   Determines if a move is legal.
*/

int
valid_move( int move, int side_to_move ) {
  int i, pos, count;

  if ( (move < 11) || (move > 88) || (board[move] != EMPTY) )
    return FALSE;

  for ( i = 0; i < 8; i++ )
    if ( dir_mask[move] & (1 << i) ) {
      for ( pos = move + move_offset[i], count = 0;
	    board[pos] == OPP( side_to_move ); pos += move_offset[i], count++ )
	;
      if ( board[pos] == side_to_move ) {
	if ( count >= 1 )
	  return TRUE;
      }
    }

  return FALSE;
}



/*
   GET_MOVE
   Prompts the user to enter a move and checks if the move is legal.
*/

int
get_move( int side_to_move ) {
  char buffer[255];
  int ready = 0;
  int curr_move;

  while ( !ready ) {
    if ( side_to_move == BLACKSQ )
      printf( "%s: ", BLACK_PROMPT );
    else
      printf( "%s: ", WHITE_PROMPT );
    scanf( "%s", buffer );
    curr_move = atoi( buffer );
    ready = valid_move( curr_move, side_to_move );
    if ( !ready ) {
      curr_move = (buffer[0] - 'a' + 1) + 10 * (buffer[1] - '0');
      ready = valid_move( curr_move, side_to_move );
    }
  }

  return curr_move;
}
