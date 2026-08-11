/*
   File:          stable.c

   Created:       March 20, 1999

   Authors:       Gunnar Andersson (gunnar@radagast.se)
                  David John Summers
                  Toshihiko Okuhara

   Contents:      Code which conservatively estimates the number of
                  stable (unflippable) discs using the concept
		  "Zardoz stability" along with edge tables.

   This piece of software is released under the GPL.
   See the file COPYING for more information.
*/



#include "porting.h"

#include <stdio.h>

#include "bitboard.h"
#include "bitbtest.h"
#include "constant.h"
#include "end.h"
#include "macros.h"
#include "patterns.h"



/* This constant is used in the DynP stuff for edge stability
   and simply denotes "value not known". */
#define  UNDETERMINED             -1

/* The maximum number of nodes to search when attempting
   a perfect stability assessment */
#define  MAX_STABILITY_NODES      10000

/* When this flag is set, the DynP tables are calculated and
   output and then the program is terminated. */
#define  DEBUG                    0

/* The squares along the border of the board. */
#define  BORDER_MASK              0xFF818181818181FFull



/* Global variables */

/* All discs determined as stable last time COUNT_STABLE was called
   for the two colors */
_Thread_local BitBoard last_black_stable, last_white_stable;



/* Local variables */

/* For each of the 3^8 edges, edge_stable[] holds an 8-bit mask
   where a bit is set if the corresponding disc can't be changed EVER. */
static short edge_stable[6561];

/* For each edge, *_stable[] holds the number of safe discs counted
   as follows: 1 for a stable corner and 2 for a stable non-corner.
   This to avoid counting corners twice. */
static unsigned char black_stable[6561], white_stable[6561];

/* A conversion table from the 2^8 edge values for one player to
   the corresponding base-3 value. */
static short base_conversion[256];

/* The base-3 indices for the edges */
static _Thread_local int edge_a1h1, edge_a8h8, edge_a1a8, edge_h1h8;

/* The fifteen diagonals in each direction, indexed by row + column
   for the SW ones (bit step 7) and row - column for the SE ones
   (bit step 9).  Built by INIT_STABLE. */
static BitBoard diag7_mask[15], diag9_mask[15];


/* Position list used in the complete stability search */

_Thread_local MoveLink stab_move_list[100];



INLINE static void
and_line_shift_64( BitBoard *target,
	           BitBoard base,
	           int shift,
	           BitBoard dir_ss ) {
  dir_ss |= (base << shift) | (base >> shift);
  *target &= dir_ss;
}

/*
  EDGE_ZARDOZ_STABLE
  Determines the bit mask for (a subset of) the stable discs in a position.
  Zardoz' algorithm + edge tables is used.
*/

INLINE static void
edge_zardoz_stable( BitBoard *ss,
		    BitBoard dd,
		    BitBoard od ) {
/* dd is the disks of the side we are looking for stable disks for
   od is the opponent
   ss are the stable disks */

  BitBoard ost, fb, lrf, udf, daf, dbf;
  BitBoard expand_ss;
  BitBoard t;
  int i;

/* ost is a simple test to see if numbers of
   stable disks have stopped increasing.

   fb is the squares which have been played
   ie either by white or black

   udf are the up-down columns that are filled, and so no vertical flips
   lrf are the left-right
   daf are the NE-SW diags filled
   dbf are the NW-SE diags filled */

/* a stable disk is a disk that has a stable disk on one
   side in each of the 4 directions
   N.B. beyond the edges is of course stable */

  fb = dd | od;

  /* A filled row protects its squares from horizontal flips; the a-
     and h-files never flip horizontally. */

  t = fb;
  t &= t >> 4;
  t &= t >> 2;
  t &= t >> 1;
  lrf = ((t & 0x0101010101010101ull) * 255) | 0x8181818181818181ull;

  /* Filled columns, by folding the rotations: afterwards a bit is set
     iff its whole column is.  Rows 1 and 8 never flip vertically. */

  t = fb;
  t &= (t >> 32) | (t << 32);
  t &= (t >> 16) | (t << 48);
  t &= (t >> 8) | (t << 56);
  udf = t | 0xFF000000000000FFull;

  /* Filled diagonals.  The border squares need no diagonal
     protection, which also covers the short diagonals. */

  daf = BORDER_MASK;
  dbf = BORDER_MASK;
  for ( i = 0; i < 15; i++ ) {
    if ( (fb & diag7_mask[i]) == diag7_mask[i] )
      daf |= diag7_mask[i];
    if ( (fb & diag9_mask[i]) == diag9_mask[i] )
      dbf |= diag9_mask[i];
  }

  *ss |= lrf & udf & daf & dbf & dd;

  if ( *ss == 0 )
    return;

  do {
    ost = *ss;

    expand_ss = lrf | (ost << 1) | (ost >> 1);
    and_line_shift_64( &expand_ss, ost, 8, udf );
    and_line_shift_64( &expand_ss, ost, 7, daf );
    and_line_shift_64( &expand_ss, ost, 9, dbf );

    *ss = ost | (expand_ss & dd);
  } while ( ost != *ss );	/* changing */
}



/*
  COUNT_EDGE_STABLE
  Returns the number of stable edge discs for COLOR.
  Side effect: The edge indices are calculated. They are needed
  by COUNT_STABLE below.
*/

int
count_edge_stable( int color,
		   BitBoard col_bits,
		   BitBoard opp_bits ) {
  unsigned int col_mask, opp_mask, ix_a1a8, ix_h1h8, ix_a1h1, ix_a8h8;

  col_mask = ((col_bits & 0x0101010101010101ull) * 0x0102040810204080ull) >> 56;
  opp_mask = ((opp_bits & 0x0101010101010101ull) * 0x0102040810204080ull) >> 56;
  ix_a1a8 = base_conversion[col_mask] - base_conversion[opp_mask];

  col_mask = (((col_bits >> 7) & 0x0101010101010101ull) * 0x0102040810204080ull) >> 56;
  opp_mask = (((opp_bits >> 7) & 0x0101010101010101ull) * 0x0102040810204080ull) >> 56;
  ix_h1h8 = base_conversion[col_mask] - base_conversion[opp_mask];

  ix_a1h1 = base_conversion[col_bits & 255] - base_conversion[opp_bits & 255];

  ix_a8h8 = base_conversion[col_bits >> 56] - base_conversion[opp_bits >> 56];

  if ( color == BLACKSQ ) {
    edge_a1h1 = 3280 * EMPTY - ix_a1h1;
    edge_a8h8 = 3280 * EMPTY - ix_a8h8;
    edge_a1a8 = 3280 * EMPTY - ix_a1a8;
    edge_h1h8 = 3280 * EMPTY - ix_h1h8;

    return (unsigned char)(black_stable[edge_a1h1] + black_stable[edge_a1a8]
      + black_stable[edge_a8h8] + black_stable[edge_h1h8]) / 2;

  } else {
    edge_a1h1 = 3280 * EMPTY + ix_a1h1;
    edge_a8h8 = 3280 * EMPTY + ix_a8h8;
    edge_a1a8 = 3280 * EMPTY + ix_a1a8;
    edge_h1h8 = 3280 * EMPTY + ix_h1h8;

    return (unsigned char)(white_stable[edge_a1h1] + white_stable[edge_a1a8]
      + white_stable[edge_a8h8] + white_stable[edge_h1h8]) / 2;
  }
}



/*
  COUNT_STABLE
  Returns the number of stable discs for COLOR.
  Side effect: last_black_stable or last_white_stable is modified.
  Note: COUNT_EDGE_STABLE must have been called immediately
        before this function is called *or you lose big*.
*/

int
count_stable( int color,
	      BitBoard col_bits,
	      BitBoard opp_bits ) {
  unsigned int t;
  BitBoard col_stable;
  BitBoard common_stable;

  /* Stable edge discs */

  common_stable = edge_stable[edge_a1h1];

  common_stable |= ((BitBoard) edge_stable[edge_a8h8]) << 56;

  t = edge_stable[edge_a1a8];
  common_stable |= (BitBoard) (((t & 0x0F) * 0x00204081u) & 0x01010101u);
  common_stable |= ((BitBoard) (((t >> 4) * 0x00204081u) & 0x01010101u)) << 32;

  t = edge_stable[edge_h1h8];
  common_stable |= (BitBoard) (((t & 0x0F) * 0x10204080u) & 0x80808080u);
  common_stable |= ((BitBoard) (((t >> 4) * 0x10204080u) & 0x80808080u)) << 32;

  /* Expand the stable edge discs into a full set of stable discs */

  col_stable = col_bits & common_stable;
  edge_zardoz_stable( &col_stable, col_bits, opp_bits );
  if ( color == BLACKSQ )
    last_black_stable = col_stable;
  else
    last_white_stable = col_stable;

  if ( col_stable != 0 )
    return non_iterative_popcount( col_stable );
  else
    return 0;
}



/*
  STABILITY_SEARCH
  Searches the subtree rooted at the current position and tries to
  find variations in which the discs in CANDIDATE_BITS are
  flipped. Aborts if all those discs are stable in the subtree.
*/

static void
stability_search( BitBoard my_bits,
		  BitBoard opp_bits,
		  int side_to_move,
		  BitBoard *candidate_bits,
		  int max_depth,
		  int last_was_pass,
		  int *stability_nodes ) {
  int sq, old_sq;
  int mobility;
  BitBoard black_bits, white_bits;
  BitBoard new_my_bits, new_opp_bits;
  BitBoard all_stable_bits;

  (*stability_nodes)++;
  if ( *stability_nodes > MAX_STABILITY_NODES )
    return;

  if ( max_depth >= 3 ) {
    if ( side_to_move == BLACKSQ ) {
      black_bits = my_bits;
      white_bits = opp_bits;
    }
    else {
      black_bits = opp_bits;
      white_bits = my_bits;
    }
    CLEAR( all_stable_bits );
    (void) count_edge_stable( BLACKSQ, black_bits, white_bits );
    if ( *candidate_bits & black_bits ) {
      (void) count_stable( BLACKSQ, black_bits, white_bits );
      APPLY_OR( all_stable_bits, last_black_stable );
    }
    if ( *candidate_bits & white_bits ) {
      (void) count_stable( WHITESQ, white_bits, black_bits );
      APPLY_OR( all_stable_bits, last_white_stable );
    }
    if ( (*candidate_bits & ~all_stable_bits) == 0 )
      return;
  }

  mobility = 0;
  for ( old_sq = END_MOVE_LIST_HEAD, sq = stab_move_list[old_sq].succ;
	sq != END_MOVE_LIST_TAIL;
	old_sq = sq, sq = stab_move_list[sq].succ ) {
    if ( TestFlips_bitboard( sq, my_bits, opp_bits ) ) {
      new_my_bits = bb_flips;
      APPLY_ANDNOT( bb_flips, my_bits );
      APPLY_ANDNOT( (*candidate_bits), bb_flips );
      if ( max_depth > 1 ) {
        FULL_ANDNOT( new_opp_bits, opp_bits, bb_flips );
	stab_move_list[old_sq].succ = stab_move_list[sq].succ;
	stability_search( new_opp_bits, new_my_bits, OPP( side_to_move ),
			  candidate_bits, max_depth - 1, FALSE,
			  stability_nodes );
	stab_move_list[old_sq].succ = sq;
      }
      mobility++;
    }
  }

  if ( (mobility == 0) && !last_was_pass )
    stability_search( opp_bits, my_bits, OPP( side_to_move ),
		      candidate_bits, max_depth, TRUE, stability_nodes );
}



/*
  COMPLETE_STABILITY_SEARCH
  Tries to compute all stable discs by search the entire game tree.
  The actual work is performed by STABILITY_SEARCH above.
*/

static void
complete_stability_search( int *board,
			   int side_to_move,
			   BitBoard *stable_bits ) {
  int i, j;
  int empties;
  int shallow_depth;
  int stability_nodes;
  int abort;
  BitBoard my_bits, opp_bits;
  BitBoard all_bits, candidate_bits;
  BitBoard test_bits;

  /* Prepare the move list */

  int last_sq = END_MOVE_LIST_HEAD;
  for ( i = 0; i < 60; i++ ) {
    int sq = position_list[i];
    if ( board[sq] == EMPTY ) {
      stab_move_list[last_sq].succ = sq;
      stab_move_list[sq].pred = last_sq;
      last_sq = sq;
    }
  }
  stab_move_list[last_sq].succ = END_MOVE_LIST_TAIL;

  empties = 0;
  for ( i = 1; i <= 8; i++ )
    for ( j = 1; j <= 8; j++ )
      if ( board[10 * i + j] == EMPTY )
	empties++;

  /* Prepare the bitmaps for the stability search */

  set_bitboards( board, side_to_move, &my_bits, &opp_bits );

  FULL_OR( all_bits, my_bits, opp_bits );

  FULL_ANDNOT( candidate_bits, all_bits, (*stable_bits) );

  /* Search all potentially stable discs for at most 4 plies
     to weed out those easily flippable */

  stability_nodes = 0;
  shallow_depth = 4;
  stability_search( my_bits, opp_bits, side_to_move, &candidate_bits,
		    MIN( empties, shallow_depth ), FALSE, &stability_nodes );

  /* Scan through the rest of the discs one at a time until the
     maximum number of stability nodes is exceeded. Hopefully
     a subset of the stable discs is found also if this happens. */

  abort = FALSE;
  for ( i = 1; (i <= 8) && !abort; i++ )
    for ( j = 1; (j <= 8) && !abort; j++ ) {
      int sq = 10 * i + j;
      test_bits = square_mask[sq];
      if ( test_bits & candidate_bits ) {
	stability_search( my_bits, opp_bits, side_to_move, &test_bits,
			  empties, FALSE, &stability_nodes );
	abort = (stability_nodes > MAX_STABILITY_NODES);
	if ( !abort ) {
	  if ( test_bits != 0 )
	    *stable_bits |= test_bits;
	}
      }
    }
}



/*
  GET_STABLE
  Determines what discs on BOARD are stable with SIDE_TO_MOVE to play next.
  The stability status of all squares (black, white and empty)
  is returned in the boolean vector IS_STABLE.
*/

void
get_stable( int *board,
	    int side_to_move,
	    int *is_stable ) {
  int i, j;
  BitBoard mask;
  BitBoard black_bits, white_bits, all_stable;

  set_bitboards( board, BLACKSQ, &black_bits, &white_bits );

  for ( i = 0; i < 100; i++ )
    is_stable[i] = FALSE;

  if ( (black_bits == 0) || (white_bits == 0) )
    for ( i = 1; i <= 8; i++ )
      for ( j = 1; j <= 8; j++ )
	is_stable[10 * i + j] = TRUE;
  else {  /* Nobody wiped out */
    (void) count_edge_stable( BLACKSQ, black_bits, white_bits );
    (void) count_stable( BLACKSQ, black_bits, white_bits );
    (void) count_stable( WHITESQ, white_bits, black_bits );

    FULL_OR( all_stable, last_black_stable, last_white_stable );

    complete_stability_search( board, side_to_move, &all_stable );

    for ( i = 1, mask = 1; i <= 8; i++ )
      for ( j = 1; j <= 8; j++, mask <<= 1 )
	if ( all_stable & mask )
	  is_stable[10 * i + j] = TRUE;
  }
}



#if DEBUG
/*
  DISPLAY_ROW
  Display an edge configuration and highlight the stable discs.
*/

static void
display_row( int pattern ) {
  int i;
  int mask = edge_stable[pattern];
  int temp = pattern;

  for ( i = 0; i < 8; i++ ) {
    switch ( temp % 3) {
    case EMPTY:
      putchar( '-' );
      break;
    case BLACKSQ:
      if ( mask & (1 << i) )
	putchar( 'X' );
      else
	putchar( 'x' );
      break;
    case WHITESQ:
      if ( mask & (1 << i) )
	putchar( 'O' );
      else
	putchar( 'o' );
    }
    temp /= 3;
  }
#ifdef TEXT_BASED
  printf( "     pattern %4d   black %2d   white %2d\n", pattern,
	  black_stable[pattern], white_stable[pattern] );
#endif
}
#endif



/*
  RECURSIVE_FIND_STABLE
  Returns a bit mask describing the set of stable discs in the
  edge PATTERN. When a bit mask is calculated, it's stored in
  a table so that any particular bit mask only is generated once.
*/

static int
recursive_find_stable( int pattern ) {
  int i, j;
  int new_pattern;
  int stable;
  int temp;
  int row[8], stored_row[8];

  if ( edge_stable[pattern] != UNDETERMINED )
    return edge_stable[pattern];

  temp = pattern;
  for ( i = 0; i < 8; i++, temp /= 3 )
    row[i] = temp % 3;

  /* All positions stable unless proved otherwise. */

  stable = 255;

  /* Play out the 8 different moves and AND together the stability masks. */

  for ( j = 0; j < 8; j++ )
    stored_row[j] = row[j];

  for ( i = 0; i < 8; i++ ) {

    /* Make sure we work with the original configuration */

    for ( j = 0; j < 8; j++ )
      row[j] = stored_row[j];

    if ( row[i] == EMPTY ) {  /* Empty ==> playable! */

      /* Mark the empty square as unstable and store position */

      stable &= ~(1 << i);

      /* Play out a black move */

      row[i] = BLACKSQ;
      if ( i >= 2 ) {
	j = i - 1;
	while ( (j >= 1) && (row[j] == WHITESQ) )
	  j--;
	if ( row[j] == BLACKSQ )
	  for ( j++; j < i; j++ ) {
	    row[j] = BLACKSQ;
	    stable &= ~(1 << j);
	  }
      }
      if ( i <= 5 ) {
	j = i + 1;
	while ( (j <= 6) && (row[j] == WHITESQ) )
	  j++;
	if ( row[j] == BLACKSQ )
	  for ( j--; j > i; j-- ) {
	    row[j] = BLACKSQ;
	    stable &= ~(1 << j);
	  }
      }
      new_pattern = 0;
      for ( j = 0; j < 8; j++ )
	new_pattern += pow3[j] * row[j];
      stable &= recursive_find_stable( new_pattern );

      /* Restore position */

      for ( j = 0; j < 8; j++ )
	row[j] = stored_row[j];

      /* Play out a white move */

      row[i] = WHITESQ;
      if ( i >= 2 ) {
	j = i - 1;
	while ( (j >= 1) && (row[j] == BLACKSQ) )
	  j--;
	if ( row[j] == WHITESQ )
	  for ( j++; j < i; j++ ) {
	    row[j] = WHITESQ;
	    stable &= ~(1 << j);
	  }
      }
      if ( i <= 5 ) {
	j = i + 1;
	while ( (j <= 6) && (row[j] == BLACKSQ) )
	  j++;
	if ( row[j] == WHITESQ )
	  for ( j--; j > i; j-- ) {
	    row[j] = WHITESQ;
	    stable &= ~(1 << j);
	  }
      }
      new_pattern = 0;
      for ( j = 0; j < 8; j++ )
	new_pattern += pow3[j] * row[j];
      stable &= recursive_find_stable( new_pattern );
    }
  }

  /* Store and return */

  edge_stable[pattern] = stable;

  return stable;
}



/*
  COUNT_COLOR_STABLE
  Determines the number of stable discs for each of the edge configurations
  for the two colors. This is done using the following convention:
  - a stable corner disc gives stability of 1
  - a stable non-corner disc gives stability of 2
  This way the stability values for the four edges can be added together
  without any risk for double-counting.
*/

static void
count_color_stable( void ) {
  int i, j;
  int pattern;
  int row[8];
  static const int stable_incr[8] = { 1, 2, 2, 2, 2, 2, 2, 1};

  for ( i = 0; i < 8; i++ )
    row[i] = 0;

  for ( pattern = 0; pattern < 6561; pattern++ ) {
    black_stable[pattern] = 0;
    white_stable[pattern] = 0;
    for ( j = 0; j < 8; j++ )
      if ( edge_stable[pattern] & (1 << j) ) {
	if ( row[j] == BLACKSQ ) {
	  black_stable[pattern] += stable_incr[j];
	}
	else if ( row[j] == WHITESQ ) {
	  white_stable[pattern] += stable_incr[j];
	}
      }

    /* Next configuration */
    i = 0;
    do {  /* The odometer principle */
      row[i]++;
      if (row[i] == 3)
	row[i] = 0;
      i++;
    } while ( (row[i - 1] == 0) && (i < 8) );
  }
}



/*
  INIT_STABLE
  Build the table containing the stability masks for all edge
  configurations. This is done using dynamic programming.
*/

void
init_stable( void ) {
  int i, j;

  for ( i = 0; i < 15; i++ ) {
    diag7_mask[i] = 0;
    diag9_mask[i] = 0;
  }
  for ( i = 0; i < 8; i++ )
    for ( j = 0; j < 8; j++ ) {
      diag7_mask[i + j] |= 1ull << (8 * i + j);
      diag9_mask[i - j + 7] |= 1ull << (8 * i + j);
    }

  for ( i = 0; i < 256; i++ ) {
    base_conversion[i] = 0;
    for ( j = 0; j < 8; j++ )
      if ( i & (1 << j) )
	base_conversion[i] += pow3[j];
  }

  for ( i = 0; i < 6561; i++ )
    edge_stable[i] = UNDETERMINED;
  for ( i = 0; i < 6561; i++ )
    if ( edge_stable[i] == UNDETERMINED )
      (void) recursive_find_stable( i );
  count_color_stable();
#if DEBUG
  for ( i = 0; i < 6561; i++ )
    display_row( i );
  exit( 1 );
#endif
}
