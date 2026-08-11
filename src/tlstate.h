/*
   File:           tlstate.h

   Contents:       The search state each thread keeps to itself.

   Mach-O resolves the address of a _Thread_local through a call to
   _tlv_get_addr, and the compiler cannot keep the result across a
   call, so a function touching ten thread-local variables pays ten
   calls -- which the profile put at the top of midgame search time,
   ahead of any of the engine's own code.  The tls-model settings that
   would turn those into a fixed offset (initial-exec, local-exec) are
   accepted and then ignored on this platform; they only bite on ELF.

   So the hot state lives in one object instead: one call resolves it
   and every member is a constant offset away.  The names are kept as
   macros so that the rest of the engine reads exactly as before.

   The functions that take a board to work on call their parameter
   IN_BOARD, because BOARD is one of the names below.
*/



#ifndef TLSTATE_H
#define TLSTATE_H



#include "bitboard.h"
#include "constant.h"



/* The basic board type. One index for each position;
   a1=11, h1=18, a8=81, h8=88. */
typedef int Board[128];


typedef struct {
  /* The position, one square per entry. */
  Board board;

  /* The same position as bitboards, indexed by colour. */
  BitBoard board_bits[3];

  /* The discs turned by the move made at each stage. */
  BitBoard flip_mask[65];

  int piece_count[3][MAX_SEARCH_DEPTH];

  /* The hash codes at each node on the way down. */
  unsigned int hash_stored1[MAX_SEARCH_DEPTH];
  unsigned int hash_stored2[MAX_SEARCH_DEPTH];

  /* The evaluation pattern indices, in black perspective. */
  unsigned short eval_pattern_index[48];

  /* The 64-bit hash key of the current position. */
  unsigned int hash1, hash2;

  /* The number of discs played from the initial position.  Must match
     the current state of the BOARD variable. */
  int disks_played;
} ThreadState;

extern _Thread_local ThreadState tls;


#define board               (tls.board)
#define board_bits          (tls.board_bits)
#define flip_mask           (tls.flip_mask)
#define piece_count         (tls.piece_count)
#define hash_stored1        (tls.hash_stored1)
#define hash_stored2        (tls.hash_stored2)
#define eval_pattern_index  (tls.eval_pattern_index)
#define hash1               (tls.hash1)
#define hash2               (tls.hash2)
#define disks_played        (tls.disks_played)



#endif  /* TLSTATE_H */
