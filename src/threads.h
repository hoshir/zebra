/*
   File:          threads.h

   Created:       August 9, 2026

   Contents:      A small fork-join worker pool for the parallel search.
*/



#ifndef THREADS_H
#define THREADS_H



#ifdef __cplusplus
extern "C" {
#endif



/*
  THREADS_INIT
  Prepare the pool for a total of COUNT search threads, the calling
  thread included; COUNT == 1 means everything runs on the caller and
  no threads are created.  Safe to call again with a different count.
*/

void
threads_init( int count );


/*
  THREADS_SHUTDOWN
  Stop and join the worker threads.
*/

void
threads_shutdown( void );


/*
  THREADS_COUNT
  The number of search threads, the calling thread included.
*/

int
threads_count( void );


/*
  THREADS_RUN
  Run JOB( index, context ) for each index in [0, JOB_COUNT) and return
  once all of them have finished.  Jobs are claimed by whichever thread
  is free, the calling thread among them, so a job must not assume
  anything about which thread runs it or in what order.  Each worker
  has had init_search_thread() called on it.
*/

void
threads_run( void (*job)( int index, void *context ), void *context,
	     int job_count );



#ifdef __cplusplus
}
#endif



#endif  /* THREADS_H */
