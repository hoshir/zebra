/*
   File:          threadtest.c

   Contents:      Sanity check for the fork-join worker pool.

   Verifies that every job in a batch runs exactly once, that batches
   can be issued back to back, that work is actually spread over more
   than one thread, and that asking for a single thread still runs
   everything.  A pool that silently drops or double-runs jobs would
   corrupt a parallel search in ways that are painful to debug from the
   search side, so it is worth pinning down here.
*/

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "threads.h"

#define JOB_COUNT   400

static int ran[JOB_COUNT];
static pthread_t runner[JOB_COUNT];

static volatile unsigned int sink;

static void
count_job( int index, void *context ) {
  unsigned int i, x = index;

  (void) context;
  /* Enough work that a batch cannot be swallowed whole by whichever
     worker happens to wake up first -- otherwise the check below that
     the work really is spread out would be a coin toss. */
  for ( i = 0; i < 200000; i++ )
    x = x * 1103515245u + 12345u;
  sink = x;

  ran[index]++;
  runner[index] = pthread_self();
}

static int
run_batch( const char *label, int threads, int expect_parallel ) {
  int i, distinct = 0;
  pthread_t seen[8];

  memset( ran, 0, sizeof( ran ) );
  memset( runner, 0, sizeof( runner ) );

  threads_init( threads );
  if ( threads_count() < 1 ) {
    printf( "FAIL  %s: threads_count() = %d\n", label, threads_count() );
    return 1;
  }
  threads_run( count_job, NULL, JOB_COUNT );

  for ( i = 0; i < JOB_COUNT; i++ )
    if ( ran[i] != 1 ) {
      printf( "FAIL  %s: job %d ran %d times\n", label, i, ran[i] );
      return 1;
    }

  for ( i = 0; i < JOB_COUNT; i++ ) {
    int j, known = 0;
    for ( j = 0; j < distinct; j++ )
      if ( pthread_equal( seen[j], runner[i] ) )
	known = 1;
    if ( !known && (distinct < 8) )
      seen[distinct++] = runner[i];
  }

  if ( expect_parallel && (distinct < 2) ) {
    printf( "FAIL  %s: all %d jobs ran on one thread\n", label, JOB_COUNT );
    return 1;
  }
  printf( "ok    %s: %d jobs, %d thread(s)\n", label, JOB_COUNT, distinct );
  return 0;
}

int
main( void ) {
  int status = 0;

  status |= run_batch( "single thread", 1, 0 );
  status |= run_batch( "four threads", 4, 1 );
  status |= run_batch( "four threads again", 4, 1 );
  status |= run_batch( "back to single", 1, 0 );
  threads_shutdown();

  puts( status ? "threadtest: FAILED" : "threadtest: PASSED" );
  return status ? EXIT_FAILURE : EXIT_SUCCESS;
}
