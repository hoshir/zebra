/*
   File:          threads.c

   Created:       August 9, 2026

   Contents:      A small fork-join worker pool for the parallel search.

                  The pool is deliberately minimal: the caller hands in
                  a job function and a job count, and every thread --
                  the caller included -- claims jobs off a shared
                  counter until they run out.  That keeps the work
                  balanced without a queue, and it means a search can
                  fall back to running everything on the calling thread
                  simply by asking for one thread.

                  Several batches can be in flight at once.  A thread
                  running a job may start a batch of its own, and a
                  thread with nothing left to do in its own batch helps
                  with whichever other batch still has work; without
                  that, the threads that finished early would sit idle
                  until the longest job of the batch came back, which is
                  where most of the parallel search's efficiency went.
*/



#include <pthread.h>
#include <stdlib.h>

#include "constant.h"
#include "search.h"
#include "threads.h"



#define MAX_THREADS               64

/* Batches in flight at once.  One per thread would be enough for the
   nesting the search actually does; the rest is slack. */
#define MAX_BATCHES               (2 * MAX_THREADS)



typedef struct {
  void (*job)( int index, void *context );
  void *context;
  int job_count;
  int next_job;        /* first job not yet claimed */
  int outstanding;     /* jobs neither finished nor abandoned */
  int active;
  int depth;           /* nesting level of the thread that started it */
  unsigned int seq;    /* creation order, to break ties between equals */
} Batch;


typedef struct {
  pthread_mutex_t lock;
  pthread_cond_t change;   /* a batch appeared, or a job finished */
  int shutting_down;
} PoolState;



/* Local variables */

static PoolState pool;
static Batch batch[MAX_BATCHES];
static unsigned int batch_seq;
static pthread_t worker[MAX_THREADS];
static int thread_count = 1;
static int worker_count;   /* threads in worker[], i.e. thread_count - 1 */
static int pool_created;
static _Thread_local int is_worker;

/* Threads parked with no work to do.  Read without the lock by
   threads_idle_count, which only wants a hint. */
static volatile int idle_count;

/* How deep in the batch nesting this thread currently is: zero outside
   any job, and one more than the depth of the batch whose job it is
   running.  A batch inherits the level of the thread that started it,
   and helpers prefer the deepest work they can find, so that an inner
   batch is cleared before the outer one it is holding up. */
static _Thread_local int nesting;

/* Where the workers leave the nodes they searched.  Each thread counts
   into its own NODES, so a worker's share used to be dropped on the
   floor when its batch ended and the reported totals were the calling
   thread's alone -- which made the node count at one thread and the
   node count at eight incomparable, and hid how much extra work the
   parallel search was doing.  Written under the pool lock. */
static CounterType pooled_nodes;



/*
  CLAIM_ONE
  Run a single job off the deepest batch that still has one, or off ONLY
  if that is not NULL.  Called with the lock held; releases it while the
  job runs.  Returns FALSE when there was nothing to claim, in which
  case the lock was never dropped and the caller may park on
  POOL.CHANGE without racing.

  ONLY is how a thread suspended in the middle of its own search takes
  part without wrecking it.  The search keeps a good deal of state
  indexed by ply -- move lists, hash keys, flip masks -- which a job
  starting from a different node overwrites from its own ply downwards.
  A job of the batch this thread is waiting on starts at exactly the
  node the thread is suspended at, so it writes only below the frames
  that are live; any other job may not.  A parked worker is inside no
  search at all and so has nothing to protect: those are the threads
  that carry a nested batch.
*/

static int
claim_one( Batch *only ) {
  Batch *pick = NULL;
  int i, index, saved_nesting;

  if ( only != NULL ) {
    if ( only->next_job >= only->job_count )
      return FALSE;
    pick = only;
  }
  else {
    for ( i = 0; i < MAX_BATCHES; i++ ) {
      Batch *b = &batch[i];
      if ( !b->active || (b->next_job >= b->job_count) )
	continue;
      if ( (pick == NULL) || (b->depth > pick->depth) ||
	   ((b->depth == pick->depth) && (b->seq > pick->seq)) )
	pick = b;
    }
    if ( pick == NULL )
      return FALSE;
  }

  index = pick->next_job++;
  saved_nesting = nesting;
  nesting = pick->depth + 1;
  pthread_mutex_unlock( &pool.lock );
  pick->job( index, pick->context );
  pthread_mutex_lock( &pool.lock );
  nesting = saved_nesting;

  /* A worker owns no total of its own, so hand the nodes over here
     rather than at the end of the batch: with batches overlapping there
     is no single point where the worker is between them. */
  if ( is_worker ) {
    add_counter( &pooled_nodes, &nodes );
    reset_counter( &nodes );
  }

  if ( --pick->outstanding == 0 )
    pthread_cond_broadcast( &pool.change );

  return TRUE;
}


/*
  WORKER_MAIN
  Take jobs from whatever batch has them, and park when none do.
*/

static void *
worker_main( void *arg ) {
  (void) arg;
  is_worker = TRUE;
  init_search_thread();

  pthread_mutex_lock( &pool.lock );
  while ( !pool.shutting_down )
    if ( !claim_one( NULL ) ) {
      idle_count++;
      pthread_cond_wait( &pool.change, &pool.lock );
      idle_count--;
    }
  pthread_mutex_unlock( &pool.lock );

  return NULL;
}



void
threads_init( int count ) {
  int i;

  if ( count < 1 )
    count = 1;
  if ( count > MAX_THREADS )
    count = MAX_THREADS;
  if ( pool_created && (count == thread_count) )
    return;

  threads_shutdown();

  thread_count = count;
  worker_count = count - 1;
  if ( worker_count == 0 ) {
    pool_created = TRUE;
    return;
  }

  pthread_mutex_init( &pool.lock, NULL );
  pthread_cond_init( &pool.change, NULL );
  pool.shutting_down = FALSE;
  idle_count = 0;
  batch_seq = 0;
  for ( i = 0; i < MAX_BATCHES; i++ )
    batch[i].active = FALSE;

  for ( i = 0; i < worker_count; i++ )
    if ( pthread_create( &worker[i], NULL, worker_main, NULL ) != 0 ) {
      /* Carry on with however many threads we did get */
      worker_count = i;
      thread_count = i + 1;
      break;
    }
  pool_created = TRUE;
}


void
threads_shutdown( void ) {
  int i;

  if ( !pool_created )
    return;
  if ( worker_count > 0 ) {
    pthread_mutex_lock( &pool.lock );
    pool.shutting_down = TRUE;
    pthread_cond_broadcast( &pool.change );
    pthread_mutex_unlock( &pool.lock );

    for ( i = 0; i < worker_count; i++ )
      pthread_join( worker[i], NULL );

    pthread_cond_destroy( &pool.change );
    pthread_mutex_destroy( &pool.lock );
  }
  worker_count = 0;
  thread_count = 1;
  pool_created = FALSE;
}


int
threads_count( void ) {
  return thread_count;
}


int
threads_idle_count( void ) {
  return idle_count;
}


void
threads_run( void (*job)( int index, void *context ), void *context,
	     int job_count ) {
  Batch *mine = NULL;
  int i;

  if ( job_count <= 0 )
    return;

  if ( worker_count == 0 ) {  /* Single-threaded: just run them here */
    for ( i = 0; i < job_count; i++ )
      job( i, context );
    return;
  }

  pthread_mutex_lock( &pool.lock );

  for ( i = 0; i < MAX_BATCHES; i++ )
    if ( !batch[i].active ) {
      mine = &batch[i];
      break;
    }
  if ( mine == NULL ) {  /* Out of slots: run the jobs here and now */
    pthread_mutex_unlock( &pool.lock );
    for ( i = 0; i < job_count; i++ )
      job( i, context );
    return;
  }

  mine->job = job;
  mine->context = context;
  mine->job_count = job_count;
  mine->next_job = 0;
  mine->outstanding = job_count;
  mine->depth = nesting;
  mine->seq = batch_seq++;
  mine->active = TRUE;
  pthread_cond_broadcast( &pool.change );

  /* The caller helps with its own batch rather than idling -- see
     claim_one for why it may not help with anyone else's -- which also
     means a batch always finishes even if no other thread ever looks at
     it, so nesting cannot deadlock.  It is up to the caller to put its
     own search state back afterwards, since a job overwrites the state
     it was using. */
  while ( mine->outstanding > 0 )
    if ( !claim_one( mine ) ) {
      idle_count++;
      pthread_cond_wait( &pool.change, &pool.lock );
      idle_count--;
    }

  mine->active = FALSE;

  /* Fold what the workers did into this thread's count, so that every
     place that already reports NODES reports the whole batch. */
  add_counter( &nodes, &pooled_nodes );
  reset_counter( &pooled_nodes );

  pthread_mutex_unlock( &pool.lock );
}
