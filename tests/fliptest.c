/*
   File:          fliptest.c

   Contents:      Differential test of the two disc-flipping
                  implementations.

   Zebra maintains two independent move implementations: the bitboard
   one (TestFlips_bitboard in bitbtest.c, used by the endgame search to
   test move legality) and the board-array one (DoFlips in doflip.c,
   used by make_move to actually play the move).  The endgame search
   assumes they always agree: end_tree_search validates a move with the
   former and executes it with the latter, ignoring the return value of
   make_move.  If they ever disagree, make_move silently does nothing
   while the matching unmake_move still pops the global flip stack,
   corrupting it and eventually crashing.

   This happened for real: the bitboard code contained a signed-overflow
   idiom (-(int)0x80000000) that modern compilers on arm64 optimize into
   the wrong answer, so every flip line terminating on h4/h8 was missed.

   This test throws random positions at both implementations and fails
   on any square where the flip counts differ.
*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "constant.h"
#include "globals.h"
#include "bitboard.h"
#include "bitbmob.h"
#include "bitbtest.h"
#include "doflip.h"
#include "unflip.h"

#define DEFAULT_TRIALS  50000
#define MAX_REPORTED    5

static void
print_pos( int side_to_move ) {
  int i, j;

  printf( "side_to_move=%s\n",
	  (side_to_move == BLACKSQ) ? "BLACK(*)" : "WHITE(O)" );
  for ( i = 1; i <= 8; i++ ) {
    for ( j = 1; j <= 8; j++ ) {
      int s = board[10 * i + j];
      putchar( (s == BLACKSQ) ? '*' : (s == WHITESQ) ? 'O' : '.' );
    }
    putchar( '\n' );
  }
}

int
main( int argc, char *argv[] ) {
  /* Default to a fresh seed each run; pass it as the first argument
     to reproduce a reported failure. */
  long seed = (argc > 1) ? atol( argv[1] ) : (long) time( NULL );
  int trials = (argc > 2) ? atoi( argv[2] ) : DEFAULT_TRIALS;
  int trial, i, j, sq;
  int mismatches = 0;
  Board saved;

  srand( (unsigned int) seed );

  /* DoFlips pushes onto the global flip stack, so the stack pointer has
     to be set up first; the engine does this from game_init().  The
     bitboard side needs its ray masks, normally built there too. */
  init_flip_stack();
  init_bitboard();

  for ( trial = 0; (trial < trials) && (mismatches < MAX_REPORTED);
	trial++ ) {
    int side_to_move = (rand() & 1) ? BLACKSQ : WHITESQ;
    int fill = 20 + rand() % 75;   /* percent nonempty */
    BitBoard my_bits, opp_bits;
    BitBoard legal = 0;

    for ( i = 0; i < 128; i++ )
      board[i] = OUTSIDE;
    for ( i = 1; i <= 8; i++ )
      for ( j = 1; j <= 8; j++ ) {
	sq = 10 * i + j;
	if ( rand() % 100 < fill )
	  board[sq] = (rand() & 1) ? BLACKSQ : WHITESQ;
	else
	  board[sq] = EMPTY;
      }

    set_bitboards( board, side_to_move, &my_bits, &opp_bits );
    memcpy( saved, board, sizeof( Board ) );

    for ( i = 1; i <= 8; i++ )
      for ( j = 1; j <= 8; j++ ) {
	int bb_count, do_count;
	int **stack_before;

	sq = 10 * i + j;
	if ( board[sq] != EMPTY )
	  continue;

	bb_count = TestFlips_bitboard( sq, my_bits, opp_bits );
	stack_before = flip_stack;
	do_count = DoFlips_no_hash( sq, side_to_move );

	/* Undo the board mutation made by DoFlips */
	memcpy( board, saved, sizeof( Board ) );
	flip_stack = stack_before;

	if ( bb_count != 0 )
	  legal |= square_mask[sq];

	if ( bb_count != do_count ) {
	  printf( "MISMATCH trial=%d sq=%c%d: "
		  "TestFlips_bitboard=%d DoFlips=%d\n",
		  trial, 'a' + j - 1, i, bb_count, do_count );
	  print_pos( side_to_move );
	  printf( "my_bits=%016llx opp_bits=%016llx\n\n",
		  my_bits, opp_bits );
	  mismatches++;
	}
      }

    /* The move generator gets the same set in one fill; generate_all()
       relies on that instead of testing squares one at a time. */
    if ( bitboard_moves( my_bits, opp_bits ) != legal ) {
      printf( "MOVE MISMATCH trial=%d: bitboard_moves=%016llx expected=%016llx\n",
	      trial, bitboard_moves( my_bits, opp_bits ), legal );
      print_pos( side_to_move );
      mismatches++;
    }
  }

  if ( mismatches == 0 ) {
    printf( "fliptest: PASSED (%d random positions, seed %ld)\n",
	    trials, seed );
    return EXIT_SUCCESS;
  }
  printf( "fliptest: FAILED with %d mismatches (seed %ld)\n",
	  mismatches, seed );
  return EXIT_FAILURE;
}
