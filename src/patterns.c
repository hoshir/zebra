/*
   File:          patterns.c

   Created:       July 4, 1997

   Author:        Gunnar Andersson (gunnar@radagast.se)

   Contents:      The patterns.
*/



#include <stdio.h>
#include <stdlib.h>
#include "constant.h"
#include "display.h"
#include "globals.h"
#include "macros.h"
#include "patterns.h"
#include "unflip.h"

#if defined( __ARM_NEON )
#include <arm_neon.h>
#endif



/* Global variables */

int pow3[10] = { 1, 3, 9, 27, 81, 243, 729, 2187, 6561, 19683 };

/* Connections between the squares and the bit masks */

int row_no[100];
int row_index[100];
int col_no[100];
int col_index[100];

int color_pattern[3];

/* The patterns describing the current state of the board. */

int row_pattern[8];
int col_pattern[8];

/* Symmetry maps */

int flip8[6561];

/* Bit masks which represent dependencies between discs and patterns */

unsigned int depend_lo[100];
unsigned int depend_hi[100];

/* Bit masks that show what patterns have been modified */

unsigned int modified_lo;
unsigned int modified_hi;



/*
   TRANSFORMATION_SET_UP
   Calculate the various symmetry and color transformations.
*/

static void
transformation_setup( void ) {
  int i, j;
  int row[10];

  /* Build the pattern tables for 8*1-patterns */

  for ( i = 0; i < 8; i++ )
    row[i] = 0;

  for ( i = 0; i < 6561; i++ ) {
    /* Create the symmetry map */
    flip8[i] = 0;
    for ( j = 0; j < 8; j++ )
      flip8[i] += row[j] * pow3[7 - j];

    /* Next configuration */
    j = 0;
    do {  /* The odometer principle */
      row[j]++;
      if ( row[j] == 3 )
	row[j] = 0;
      j++;
    } while ( (row[j - 1] == 0) && (j < 8) );
  }
}


/*
  ADD_SINGLE
  Mark board position POS as depending on pattern # MASK.
*/

static void
add_single( int mask, int pos ) {
  if ( mask < 32 )
    depend_lo[pos] |= 1 << mask;
  else
    depend_hi[pos] |= 1 << (mask - 32);
}


/*
  ADD_MULTIPLE
  Mark board positions POS, POS+STEP, ..., POS+(COUNT-1)STEP as
  depending on pattern # MASK.
*/

static void
add_multiple( int mask, int pos, int count, int step ) {
  int i;

  for ( i = 0; i < count; i++ )
    add_single( mask, pos + i * step );
}


/*
  PATTERN_DEPENDENCY
  Fill the dependency masks for each square with the bit masks
  for the patterns which it depends.
  Note: The definitions of the patterns and their corresponding name
        must match the order given in endmacro.c.
*/


static void
pattern_dependency( void ) {

  /* A-file+2X: a1-a8 + b2,b7 */

  add_multiple( AFILEX1, 11, 8, 10 );
  add_single( AFILEX1, 22 );
  add_single( AFILEX1, 72 );

  /* A-file+2X: h1-h8 + g2,g7 */

  add_multiple( AFILEX2, 18, 8, 10 );
  add_single( AFILEX2, 27 );
  add_single( AFILEX2, 77 );

  /* A-file+2X: a1-h1 + b2,g2 */

  add_multiple( AFILEX3, 11, 8, 1 );
  add_single( AFILEX3, 22 );
  add_single( AFILEX3, 27 );

  /* A-file+2X: a8-h8 + b7,g7 */

  add_multiple( AFILEX4, 81, 8, 1 );
  add_single( AFILEX4, 72 );
  add_single( AFILEX4, 77 );

  /* B-file: b1-b8 */

  add_multiple( BFILE1, 12, 8, 10 );

  /* B-file: g1-g8 */

  add_multiple( BFILE2, 17, 8, 10 );

  /* B-file: a2-h2 */

  add_multiple( BFILE3, 21, 8, 1 );

  /* B-file: a7-h7 */

  add_multiple( BFILE4, 71, 8, 1 );

  /* C-file: c1-c8 */

  add_multiple( CFILE1, 13, 8, 10 );

  /* C-file: f1-f8 */

  add_multiple( CFILE2, 16, 8, 10 );

  /* C-file: a3-h3 */

  add_multiple( CFILE3, 31, 8, 1 );

  /* C-file: a6-h6 */

  add_multiple( CFILE4, 61, 8, 1);

  /* D-file: d1-d8 */

  add_multiple( DFILE1, 14, 8, 10 );

  /* D-file: e1-e8 */

  add_multiple( DFILE2, 15, 8, 10 );

  /* D-file: a4-h4 */

  add_multiple( DFILE3, 41, 8, 1 );

  /* D-file: a5-h5 */

  add_multiple( DFILE4, 51, 8, 1 );

  /* Diag8: a1-h8 */

  add_multiple( DIAG8_1, 11, 8, 11 );

  /* Diag8: h1-a8 */

  add_multiple( DIAG8_2, 18, 8, 9 );

  /* Diag7: b1-h7 */

  add_multiple( DIAG7_1, 12, 7, 11 );

  /* Diag7: a2-g8 */

  add_multiple( DIAG7_2, 21, 7, 11 );

  /* Diag7: a7-g1 */

  add_multiple( DIAG7_3, 17, 7, 9 );

  /* Diag7: b8-h2 */

  add_multiple( DIAG7_4, 28, 7, 9 );

  /* Diag6: c1-h6 */

  add_multiple( DIAG6_1, 13, 6, 11 );

  /* Diag6: a3-f8 */

  add_multiple( DIAG6_2, 31, 6, 11 );

  /* Diag6: a6-f1 */

  add_multiple( DIAG6_3, 16, 6, 9 );

  /* Diag6: c8-h3 */

  add_multiple( DIAG6_4, 38, 6, 9 );

  /* Diag5: d1-h5 */

  add_multiple( DIAG5_1, 14, 5, 11 );

  /* Diag5: a4-e8 */

  add_multiple( DIAG5_2, 41, 5, 11 );

  /* Diag5: a5-e1 */

  add_multiple( DIAG5_3, 15, 5, 9 );

  /* Diag5: d8-h4 */

  add_multiple( DIAG5_4, 48, 5, 9 );

  /* Diag4: e1-h4 */

  add_multiple( DIAG4_1, 15, 4, 11 );

  /* Diag4: a5-d8 */

  add_multiple( DIAG4_2, 51, 4, 11 );

  /* Diag4: a4-d1 */

  add_multiple( DIAG4_3, 14, 4, 9 );

  /* Diag4: e8-h5 */

  add_multiple( DIAG4_4, 58, 4, 9 );

  /* Corner3x3: a1-c1 + a2-c2 + a3-c3 */

  add_multiple( CORNER33_1, 11, 3, 1 );
  add_multiple( CORNER33_1, 21, 3, 1 );
  add_multiple( CORNER33_1, 31, 3, 1 );

  /* Corner3x3: a8-c8 + a7-c7 + a6-c6 */

  add_multiple( CORNER33_2, 81, 3, 1 );
  add_multiple( CORNER33_2, 71, 3, 1 );
  add_multiple( CORNER33_2, 61, 3, 1 );

  /* Corner3x3: f1-h1 + f2-h2 + f3-h3 */

  add_multiple( CORNER33_3, 18, 3, -1 );
  add_multiple( CORNER33_3, 28, 3, -1 );
  add_multiple( CORNER33_3, 38, 3, -1 );

  /* Corner3x3: f8-h8 + f7-h7 + f6-h6 */

  add_multiple( CORNER33_4, 88, 3, -1 );
  add_multiple( CORNER33_4, 78, 3, -1 );
  add_multiple( CORNER33_4, 68, 3, -1 );

  /* Corner4x2: a1-d1 + a2-d2 */

  add_multiple( CORNER42_1, 11, 4, 1 );
  add_multiple( CORNER42_1, 21, 4, 1 );

  /* Corner4x2: a8-d8 + a7-d7 */

  add_multiple( CORNER42_2, 81, 4, 1 );
  add_multiple( CORNER42_2, 71, 4, 1 );

  /* Corner4x2: e1-h1 + e2-h2 */

  add_multiple( CORNER42_3, 18, 4, -1 );
  add_multiple( CORNER42_3, 28, 4, -1 );

  /* Corner4x2: e8-h8 + e7-h7 */

  add_multiple( CORNER42_4, 88, 4, -1 );
  add_multiple( CORNER42_4, 78, 4, -1 );

  /* Corner4x2: a1-a4 + b1-b4 */

  add_multiple( CORNER42_5, 11, 4, 10 );
  add_multiple( CORNER42_5, 12, 4, 10 );

  /* Corner4x2: h1-h4 + g1-g4 */ 

  add_multiple( CORNER42_6, 18, 4, 10 );
  add_multiple( CORNER42_6, 17, 4, 10 );

  /* Corner4x2: a8-a5 + b8-b5 */

  add_multiple( CORNER42_7, 81, 4, -10 );
  add_multiple( CORNER42_7, 82, 4, -10 );

  /* Corner4x2: h8-h5 + g8-g5 */

  add_multiple( CORNER42_8, 88, 4, -10 );
  add_multiple( CORNER42_8, 87, 4, -10 );
}



/*
   INIT_PATTERNS
   Pre-computes some tables needed for fast pattern access.
*/   

void
init_patterns( void ) {
  int i, j;
  int pos;

  transformation_setup();

  for ( i = 1; i <= 8; i++ )
    for ( j = 1; j <= 8; j++ ) {
      pos = 10 * i + j;
      row_no[pos] = i - 1;
      row_index[pos] = j - 1;
      col_no[pos] = j - 1;
      col_index[pos] = i - 1;
    }

  pattern_dependency();
  init_pattern_dependencies();

  /* These values needed for compatibility with the old book format */

  color_pattern[BLACKSQ] = BLACK_PATTERN;
  color_pattern[WHITESQ] = WHITE_PATTERN;
}


/*
   COMPUTE_LINE_PATTERNS
   Translate the current board configuration into patterns.
*/

void
compute_line_patterns( int *in_board ) {
  int i, j;
  int pos;
  int mask;

  for ( i = 0; i < 8; i++ ) {
    row_pattern[i] = 0;
    col_pattern[i] = 0;
  }

  for ( i = 1; i <= 8; i++ )
    for ( j = 1; j <= 8; j++ ) {
      pos = 10 * i + j;
      if ( in_board[pos] == EMPTY )
	mask = EMPTY_PATTERN;
      else               
	mask = color_pattern[in_board[pos]];
      row_pattern[row_no[pos]] += mask * pow3[row_index[pos]];
      col_pattern[col_no[pos]] += mask * pow3[col_index[pos]];
    }
}


/* ------------------------------------------------------------------ */
/* Incremental evaluation pattern indices                             */
/*                                                                    */
/* pattern_evaluation() used to rebuild the base-3 index of every     */
/* pattern from the board at each leaf.  The indices are maintained   */
/* incrementally instead: a flipped disc changes one trit of each     */
/* pattern its square belongs to, so MAKE_MOVE adds the trit deltas   */
/* for the discs it turns and UNMAKE_MOVE subtracts them again.  The  */
/* indices are kept in black perspective; the white-to-move lookup    */
/* reads the coefficient tables backwards through the *_last          */
/* pointers, exactly as the evaluation always has.                    */

/* The indices are held as unsigned 16-bit lanes so that a whole move's
   worth of update is a handful of vector adds.  The largest index is
   3^10 - 1 = 59048 and the largest weight 2 * 3^9 = 39366, both inside
   the range, and the arithmetic is exact modulo 2^16: intermediate
   lanes may wrap while a move is being applied, but the value at the
   end of the update is the true one.  The count is padded to a
   multiple of eight so the tail is a whole vector. */

#define EVAL_PATTERN_COUNT   46
#define EVAL_PATTERN_SLOTS   48


static const struct {
  short len;
  short squares[10];   /* most significant trit first */
} eval_pattern[EVAL_PATTERN_COUNT] = {
  { 10, { 72, 22, 81, 71, 61, 51, 41, 31, 21, 11 } },	/* afile2x */
  { 10, { 77, 27, 88, 78, 68, 58, 48, 38, 28, 18 } },	/* afile2x */
  { 10, { 27, 22, 18, 17, 16, 15, 14, 13, 12, 11 } },	/* afile2x */
  { 10, { 77, 72, 88, 87, 86, 85, 84, 83, 82, 81 } },	/* afile2x */
  { 8, { 82, 72, 62, 52, 42, 32, 22, 12,  0,  0 } },	/* bfile */
  { 8, { 87, 77, 67, 57, 47, 37, 27, 17,  0,  0 } },	/* bfile */
  { 8, { 28, 27, 26, 25, 24, 23, 22, 21,  0,  0 } },	/* bfile */
  { 8, { 78, 77, 76, 75, 74, 73, 72, 71,  0,  0 } },	/* bfile */
  { 8, { 83, 73, 63, 53, 43, 33, 23, 13,  0,  0 } },	/* cfile */
  { 8, { 86, 76, 66, 56, 46, 36, 26, 16,  0,  0 } },	/* cfile */
  { 8, { 38, 37, 36, 35, 34, 33, 32, 31,  0,  0 } },	/* cfile */
  { 8, { 68, 67, 66, 65, 64, 63, 62, 61,  0,  0 } },	/* cfile */
  { 8, { 84, 74, 64, 54, 44, 34, 24, 14,  0,  0 } },	/* dfile */
  { 8, { 85, 75, 65, 55, 45, 35, 25, 15,  0,  0 } },	/* dfile */
  { 8, { 48, 47, 46, 45, 44, 43, 42, 41,  0,  0 } },	/* dfile */
  { 8, { 58, 57, 56, 55, 54, 53, 52, 51,  0,  0 } },	/* dfile */
  { 8, { 88, 77, 66, 55, 44, 33, 22, 11,  0,  0 } },	/* diag8 */
  { 8, { 81, 72, 63, 54, 45, 36, 27, 18,  0,  0 } },	/* diag8 */
  { 7, { 78, 67, 56, 45, 34, 23, 12,  0,  0,  0 } },	/* diag7 */
  { 7, { 87, 76, 65, 54, 43, 32, 21,  0,  0,  0 } },	/* diag7 */
  { 7, { 71, 62, 53, 44, 35, 26, 17,  0,  0,  0 } },	/* diag7 */
  { 7, { 82, 73, 64, 55, 46, 37, 28,  0,  0,  0 } },	/* diag7 */
  { 6, { 68, 57, 46, 35, 24, 13,  0,  0,  0,  0 } },	/* diag6 */
  { 6, { 86, 75, 64, 53, 42, 31,  0,  0,  0,  0 } },	/* diag6 */
  { 6, { 61, 52, 43, 34, 25, 16,  0,  0,  0,  0 } },	/* diag6 */
  { 6, { 83, 74, 65, 56, 47, 38,  0,  0,  0,  0 } },	/* diag6 */
  { 5, { 58, 47, 36, 25, 14,  0,  0,  0,  0,  0 } },	/* diag5 */
  { 5, { 85, 74, 63, 52, 41,  0,  0,  0,  0,  0 } },	/* diag5 */
  { 5, { 51, 42, 33, 24, 15,  0,  0,  0,  0,  0 } },	/* diag5 */
  { 5, { 84, 75, 66, 57, 48,  0,  0,  0,  0,  0 } },	/* diag5 */
  { 4, { 48, 37, 26, 15,  0,  0,  0,  0,  0,  0 } },	/* diag4 */
  { 4, { 84, 73, 62, 51,  0,  0,  0,  0,  0,  0 } },	/* diag4 */
  { 4, { 41, 32, 23, 14,  0,  0,  0,  0,  0,  0 } },	/* diag4 */
  { 4, { 85, 76, 67, 58,  0,  0,  0,  0,  0,  0 } },	/* diag4 */
  { 9, { 33, 32, 31, 23, 22, 21, 13, 12, 11,  0 } },	/* corner33 */
  { 9, { 63, 62, 61, 73, 72, 71, 83, 82, 81,  0 } },	/* corner33 */
  { 9, { 36, 37, 38, 26, 27, 28, 16, 17, 18,  0 } },	/* corner33 */
  { 9, { 66, 67, 68, 76, 77, 78, 86, 87, 88,  0 } },	/* corner33 */
  { 10, { 25, 24, 23, 22, 21, 15, 14, 13, 12, 11 } },	/* corner52 */
  { 10, { 75, 74, 73, 72, 71, 85, 84, 83, 82, 81 } },	/* corner52 */
  { 10, { 24, 25, 26, 27, 28, 14, 15, 16, 17, 18 } },	/* corner52 */
  { 10, { 74, 75, 76, 77, 78, 84, 85, 86, 87, 88 } },	/* corner52 */
  { 10, { 52, 42, 32, 22, 12, 51, 41, 31, 21, 11 } },	/* corner52 */
  { 10, { 57, 47, 37, 27, 17, 58, 48, 38, 28, 18 } },	/* corner52 */
  { 10, { 42, 52, 62, 72, 82, 41, 51, 61, 71, 81 } },	/* corner52 */
  { 10, { 47, 57, 67, 77, 87, 48, 58, 68, 78, 88 } },	/* corner52 */
};

/* The trit weight of every square in every pattern, laid out densely
   so that one square's contribution to all 46 indices is six vectors.
   A square belongs to eight patterns at the most, so the rows are
   mostly zero; the zero lanes cost nothing but make the update
   branch-free and free of the scattered read-modify-writes that the
   sparse form needed.  The doubled table serves the flipped discs,
   whose trit moves by two. */

static unsigned short pattern_weight[64][EVAL_PATTERN_SLOTS];
static unsigned short pattern_weight2[64][EVAL_PATTERN_SLOTS];


void
init_pattern_dependencies( void ) {
  int p, i, sq;

  for ( sq = 0; sq < 64; sq++ )
    for ( p = 0; p < EVAL_PATTERN_SLOTS; p++ ) {
      pattern_weight[sq][p] = 0;
      pattern_weight2[sq][p] = 0;
    }

  for ( p = 0; p < EVAL_PATTERN_COUNT; p++ )
    for ( i = 0; i < eval_pattern[p].len; i++ ) {
      unsigned short w = (unsigned short)
	pow3[eval_pattern[p].len - 1 - i];
      /* Indexed by bit number, so that the rows the flipped discs
	 need are reached straight from the flip mask. */
      sq = bit_position[eval_pattern[p].squares[i]];
      pattern_weight[sq][p] = w;
      pattern_weight2[sq][p] = 2 * w;
    }
}


/*
  DETERMINE_PATTERN_INDICES
  Recompute all indices from the board; the incremental updates keep
  them current from here on.
*/

void
determine_pattern_indices( void ) {
  int p, i, index;

  for ( p = 0; p < EVAL_PATTERN_COUNT; p++ ) {
    index = 0;
    for ( i = 0; i < eval_pattern[p].len; i++ )
      index = 3 * index + board[eval_pattern[p].squares[i]];
    eval_pattern_index[p] = (unsigned short) index;
  }
  for ( p = EVAL_PATTERN_COUNT; p < EVAL_PATTERN_SLOTS; p++ )
    eval_pattern_index[p] = 0;
}


/*
  UPDATE_PATTERN_INDICES
  Apply (DIR = 1) or take back (DIR = -1) the index changes of a move:
  the played square goes from EMPTY to COLOR and the FLIPPED entries
  on top of the flip stack go from the opponent to COLOR.  Called by
  MAKE_MOVE while the flipped discs are still on the stack.

  Trits are the board values, BLACKSQ 0, EMPTY 1, WHITESQ 2, so playing
  black lowers a trit and playing white raises it; taking the move back
  reverses that.  Every square of the move therefore moves the indices
  in the same direction, and the whole update is one sign applied to a
  few rows of the weight tables.
*/

void
update_pattern_indices( int color, int move, BitBoard flipped, int dir ) {
  /* EVAL_PATTERN_INDEX is thread-local; resolve it once. */
  unsigned short *pi = eval_pattern_index;
  const int subtract = ((color == BLACKSQ) == (dir > 0));

#if defined( __ARM_NEON )

#define APPLY_ROW( op, table, sq )				\
  {								\
    const unsigned short *w = (table)[sq];			\
    p0 = op( p0, vld1q_u16( w      ) );				\
    p1 = op( p1, vld1q_u16( w +  8 ) );				\
    p2 = op( p2, vld1q_u16( w + 16 ) );				\
    p3 = op( p3, vld1q_u16( w + 24 ) );				\
    p4 = op( p4, vld1q_u16( w + 32 ) );				\
    p5 = op( p5, vld1q_u16( w + 40 ) );				\
  }

#define APPLY_MASK( op )					\
  {								\
    BitBoard m = flipped;					\
    while ( m != 0 ) {						\
      APPLY_ROW( op, pattern_weight2, FIRST_BIT( m ) );		\
      m &= m - 1;						\
    }								\
    APPLY_ROW( op, pattern_weight, bit_position[move] );	\
  }

  {
    uint16x8_t p0 = vld1q_u16( pi      );
    uint16x8_t p1 = vld1q_u16( pi +  8 );
    uint16x8_t p2 = vld1q_u16( pi + 16 );
    uint16x8_t p3 = vld1q_u16( pi + 24 );
    uint16x8_t p4 = vld1q_u16( pi + 32 );
    uint16x8_t p5 = vld1q_u16( pi + 40 );

    if ( subtract )
      APPLY_MASK( vsubq_u16 )
    else
      APPLY_MASK( vaddq_u16 )

    vst1q_u16( pi,      p0 );
    vst1q_u16( pi +  8, p1 );
    vst1q_u16( pi + 16, p2 );
    vst1q_u16( pi + 24, p3 );
    vst1q_u16( pi + 32, p4 );
    vst1q_u16( pi + 40, p5 );
  }

#undef APPLY_MASK
#undef APPLY_ROW

#else

  {
    int j;
    BitBoard m;

    if ( subtract ) {
      for ( m = flipped; m != 0; m &= m - 1 ) {
	const unsigned short *w = pattern_weight2[FIRST_BIT( m )];
	for ( j = 0; j < EVAL_PATTERN_SLOTS; j++ )
	  pi[j] -= w[j];
      }
      for ( j = 0; j < EVAL_PATTERN_SLOTS; j++ )
	pi[j] -= pattern_weight[bit_position[move]][j];
    }
    else {
      for ( m = flipped; m != 0; m &= m - 1 ) {
	const unsigned short *w = pattern_weight2[FIRST_BIT( m )];
	for ( j = 0; j < EVAL_PATTERN_SLOTS; j++ )
	  pi[j] += w[j];
      }
      for ( j = 0; j < EVAL_PATTERN_SLOTS; j++ )
	pi[j] += pattern_weight[bit_position[move]][j];
    }
  }

#endif
}


/*
  VERIFY_PATTERN_INDICES
  Compare the incrementally maintained indices against a recomputation
  from the board.  Debug builds call this from pattern_evaluation().
*/

void
verify_pattern_indices( void ) {
  int p, i, index;

  for ( p = 0; p < EVAL_PATTERN_COUNT; p++ ) {
    index = 0;
    for ( i = 0; i < eval_pattern[p].len; i++ )
      index = 3 * index + board[eval_pattern[p].squares[i]];
    if ( index != (int) eval_pattern_index[p] ) {
      fprintf( stderr, "pattern %d: incremental %d != recomputed %d\n",
	       p, (int) eval_pattern_index[p], index );
      abort();
    }
  }
}
