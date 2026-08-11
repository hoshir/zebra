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
  THREADS_IDLE_COUNT
  How many threads are parked with nothing to do.  A hint, read without
  locking and stale the moment it is returned: it is there so that a
  search can decide whether splitting a node would buy it anything.
*/

int
threads_idle_count( void );


/*
  THREADS_RUN
  Run JOB( index, context ) for each index in [0, JOB_COUNT) and return
  once all of them have finished.  Jobs are claimed by whichever thread
  is free, so a job must not assume anything about which thread runs it
  or in what order.  The calling thread takes part rather than idling,
  which means a job runs on it too, on top of the search it is suspended
  in the middle of; it is the caller's job to keep the two from
  trampling each other.  Each worker has had init_search_thread()
  called on it.

  A job may call THREADS_RUN again.  While it waits for its own batch
  the calling thread will run jobs from any batch that has them, its own
  or another's, so nesting costs nothing but does mean a thread can be
  carried arbitrarily far from where it started before it comes back.
*/

void
threads_run( void (*job)( int index, void *context ), void *context,
	     int job_count );



#ifdef __cplusplus
}
#endif



#endif  /* THREADS_H */
