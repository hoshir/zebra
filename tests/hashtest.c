/*
   File:          hashtest.c

   Contents:      Concurrent stress test for the transposition table.

   Verifies that simultaneous reads and writes from multiple threads do
   not produce torn reads (i.e. reading a hash entry whose key matches
   the probed position but whose payload -- eval, move, draft, flags --
   belongs to a different position being written concurrently).
*/

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hash.h"
#include "macros.h"

#define NUM_THREADS            8
#define NUM_POSITIONS          128
#define ITERATIONS_PER_THREAD  500000

typedef struct {
  unsigned int h1;
  unsigned int h2;
  int eval;
  int moves[4];
  short draft;
  short flags;
} TestPos;

static TestPos test_positions[NUM_POSITIONS];
static volatile int stop_writers = 0;
static unsigned long long total_hits = 0;
static unsigned long long total_torn_reads = 0;
static pthread_mutex_t stats_lock = PTHREAD_MUTEX_INITIALIZER;

#define TEST_HASH_BITS    3

static void
init_test_positions( void ) {
  int i;
  for ( i = 0; i < NUM_POSITIONS; i++ ) {
    /* Multiple positions share the SAME bucket and SAME tag in h1,
       differing only in h2. This reproduces the exact collision mode
       where entries share the 8-bit KEY1_MASK tag but differ in key2. */
    unsigned int bucket = (unsigned int) (i % 8);
    unsigned int tag = (unsigned int) ((i / 16) & 0xFF); /* 16 positions share same tag */
    unsigned int seed = (unsigned int) ((i + 1) * 1103515245u + 12345u);

    test_positions[i].h1 = bucket | (tag << 24);
    test_positions[i].h2 = seed | 1; /* unique non-zero key2 */
    test_positions[i].eval = (int) (seed ^ 0x5A5A5A5Au);
    test_positions[i].moves[0] = (int) (seed % 64);
    test_positions[i].moves[1] = (int) ((seed >> 6) % 64);
    test_positions[i].moves[2] = (int) ((seed >> 12) % 64);
    test_positions[i].moves[3] = (int) ((seed >> 18) % 64);
    test_positions[i].draft = 10;
    test_positions[i].flags = ENDGAME_SCORE | EXACT_VALUE;
  }
}

static void *
writer_thread( void *arg ) {
  unsigned int lcg = (unsigned int) (uintptr_t) arg * 2654435761u + 1;

  while ( !stop_writers ) {
    lcg = lcg * 1103515245u + 12345u;
    int idx = (lcg >> 16) % NUM_POSITIONS;
    const TestPos *p = &test_positions[idx];

    hash1 = p->h1;
    hash2 = p->h2;

    if ( (lcg & 1) == 0 ) {
      add_hash( ENDGAME_MODE, p->eval, p->moves[0], p->flags, p->draft, 0 );
    }
    else {
      add_hash_extended( ENDGAME_MODE, p->eval, (int *) p->moves, p->flags, p->draft, 0 );
    }
  }
  return NULL;
}

static void *
reader_thread( void *arg ) {
  unsigned int lcg = (unsigned int) (uintptr_t) arg * 2654435761u + 101;
  unsigned long long hits = 0;
  unsigned long long torn = 0;
  int i;

  for ( i = 0; i < ITERATIONS_PER_THREAD; i++ ) {
    lcg = lcg * 1103515245u + 12345u;
    int idx = (lcg >> 16) % NUM_POSITIONS;
    const TestPos *p = &test_positions[idx];
    HashEntry entry;

    hash1 = p->h1;
    hash2 = p->h2;

    find_hash( &entry, ENDGAME_MODE );

    if ( entry.draft != NO_HASH_MOVE ) {
      hits++;
      /* Verify that payload matches the probed position p */
      if ( entry.eval != p->eval ||
           entry.move[0] != p->moves[0] ||
           entry.draft != p->draft ||
           (entry.flags & (ENDGAME_SCORE | EXACT_VALUE)) != (ENDGAME_SCORE | EXACT_VALUE) ) {
        torn++;
      }
    }
  }

  pthread_mutex_lock( &stats_lock );
  total_hits += hits;
  total_torn_reads += torn;
  pthread_mutex_unlock( &stats_lock );

  return NULL;
}

int
main( void ) {
  pthread_t threads[NUM_THREADS];
  int i;

  init_test_positions();
  init_hash( TEST_HASH_BITS );
  setup_hash( TRUE );

  /* Launch half writer threads and half reader threads */
  for ( i = 0; i < NUM_THREADS / 2; i++ ) {
    if ( pthread_create( &threads[i], NULL, writer_thread, (void *) (uintptr_t) (i + 1) ) != 0 ) {
      perror( "pthread_create writer" );
      return EXIT_FAILURE;
    }
  }

  for ( i = NUM_THREADS / 2; i < NUM_THREADS; i++ ) {
    if ( pthread_create( &threads[i], NULL, reader_thread, (void *) (uintptr_t) (i + 1) ) != 0 ) {
      perror( "pthread_create reader" );
      return EXIT_FAILURE;
    }
  }

  /* Wait for readers to finish their iterations */
  for ( i = NUM_THREADS / 2; i < NUM_THREADS; i++ ) {
    pthread_join( threads[i], NULL );
  }

  /* Signal writers to stop and wait for them */
  stop_writers = 1;
  for ( i = 0; i < NUM_THREADS / 2; i++ ) {
    pthread_join( threads[i], NULL );
  }

  free_hash();

  printf( "hashtest: %llu probes, %llu hits, %llu torn reads\n",
          (unsigned long long) (NUM_THREADS / 2) * ITERATIONS_PER_THREAD,
          total_hits, total_torn_reads );

  if ( total_torn_reads > 0 ) {
    printf( "FAIL  hashtest: detected %llu torn reads in concurrent hash table access\n",
            total_torn_reads );
    puts( "hashtest: FAILED" );
    return EXIT_FAILURE;
  }

  puts( "hashtest: PASSED" );
  return EXIT_SUCCESS;
}
