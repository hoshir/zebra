/*
   File:          test_hole_parity.c
   Contents:      Unit tests and microbenchmark for bitboard 4-way flood-fill and hole parity detection.
*/

#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>
#include "bitboard.h"

static double get_time_ns( void ) {
  struct timeval tv;
  gettimeofday( &tv, NULL );
  return (double)tv.tv_sec * 1e9 + (double)tv.tv_usec * 1e3;
}

static void test_single_isolated_hole( void ) {
  printf( "Running Test 1: Single isolated hole...\n" );

  /* Single cell at a1 (bit 0) -> size 1 (odd) */
  {
    BitBoard mask = 1ull << 0;
    HoleParityInfo info;
    compute_hole_parity( mask, &info );
    if ( info.count != 1 || info.regions[0].size != 1 || info.regions[0].parity != 1 ||
         info.odd_parity_mask != mask || info.even_parity_mask != 0 ) {
      fprintf( stderr, "FAIL: Single cell odd test failed (count=%d, size=%u, parity=%d, odd_mask=%llx)\n",
               info.count, info.regions[0].size, info.regions[0].parity, info.odd_parity_mask );
      exit( 1 );
    }
  }

  /* 2x2 block at a1,a2,b1,b2 (bits 0, 1, 8, 9) -> size 4 (even) */
  {
    BitBoard mask = (1ull << 0) | (1ull << 1) | (1ull << 8) | (1ull << 9);
    HoleParityInfo info;
    compute_hole_parity( mask, &info );
    if ( info.count != 1 || info.regions[0].size != 4 || info.regions[0].parity != 0 ||
         info.odd_parity_mask != 0 || info.even_parity_mask != mask ) {
      fprintf( stderr, "FAIL: 2x2 block even test failed (count=%d, size=%u, parity=%d, even_mask=%llx)\n",
               info.count, info.regions[0].size, info.regions[0].parity, info.even_parity_mask );
      exit( 1 );
    }
  }

  printf( "Test 1 PASSED.\n" );
}

static void test_multiple_disconnected_holes( void ) {
  printf( "Running Test 2: Multiple disconnected holes...\n" );

  /* Hole 1: single cell at a1 (bit 0, size 1, odd)
     Hole 2: 2x2 block at h7,h8,g7,g8 (bits 62, 63, 54, 55, size 4, even) */
  BitBoard hole1 = 1ull << 0;
  BitBoard hole2 = (1ull << 62) | (1ull << 63) | (1ull << 54) | (1ull << 55);
  BitBoard mask = hole1 | hole2;
  HoleParityInfo info;
  compute_hole_parity( mask, &info );

  if ( info.count != 2 ) {
    fprintf( stderr, "FAIL: Expected 2 regions, got %d\n", info.count );
    exit( 1 );
  }

  if ( info.total_odd_regions != 1 || info.total_even_regions != 1 ||
       info.odd_parity_mask != hole1 || info.even_parity_mask != hole2 ) {
    fprintf( stderr, "FAIL: Expected 1 odd and 1 even region, got odd=%d, even=%d\n",
             info.total_odd_regions, info.total_even_regions );
    exit( 1 );
  }

  printf( "Test 2 PASSED.\n" );
}

static void test_quadrant_bridging_holes( void ) {
  printf( "Running Test 3: Holes bridging quadrant boundaries...\n" );

  /* Center 2x2 block spanning across columns 4-5, rows 4-5 (d4, d5, e4, e5)
     d4 = row 4, col 4 -> bit 8*(3)+3 = 27
     d5 = row 5, col 4 -> bit 8*(4)+3 = 35
     e4 = row 4, col 5 -> bit 8*(3)+4 = 28
     e5 = row 5, col 5 -> bit 8*(4)+4 = 36 */
  BitBoard mask = (1ull << 27) | (1ull << 35) | (1ull << 28) | (1ull << 36);
  HoleParityInfo info;
  compute_hole_parity( mask, &info );

  if ( info.count != 1 || info.regions[0].size != 4 || info.regions[0].parity != 0 ||
       info.odd_parity_mask != 0 || info.even_parity_mask != mask ) {
    fprintf( stderr, "FAIL: Quadrant bridging test failed (count=%d, size=%u)\n",
             info.count, info.regions[0].size );
    exit( 1 );
  }

  printf( "Test 3 PASSED.\n" );
}

static void test_diagonal_separation( void ) {
  printf( "Running Test 4: Diagonal-only adjacency separation...\n" );

  /* Two cells diagonally touching: a1 (bit 0) and b2 (bit 9).
     In 4-way flood fill, they must remain disconnected into 2 separate regions. */
  BitBoard mask = (1ull << 0) | (1ull << 9);
  HoleParityInfo info;
  compute_hole_parity( mask, &info );

  if ( info.count != 2 ) {
    fprintf( stderr, "FAIL: Expected 2 disconnected regions for diagonal adjacency, got %d\n", info.count );
    exit( 1 );
  }

  if ( info.regions[0].size != 1 || info.regions[1].size != 1 ||
       info.odd_parity_mask != mask || info.even_parity_mask != 0 ) {
    fprintf( stderr, "FAIL: Expected size 1 for both regions\n" );
    exit( 1 );
  }

  printf( "Test 4 PASSED.\n" );
}

static void test_microbenchmark( void ) {
  printf( "Running Test 5: Microbenchmark (1,000,000 runs)...\n" );

  /* Complex mask with 3 disconnected holes of varying sizes */
  BitBoard mask = (1ull << 0) | (1ull << 1) | /* 2 (even) */
                  (1ull << 28) | (1ull << 29) | (1ull << 36) | /* 3 (odd) */
                  (1ull << 63); /* 1 (odd) */

  HoleParityInfo info;
  int runs = 1000000;
  double start = get_time_ns();

  for ( int i = 0; i < runs; i++ ) {
    compute_hole_parity( mask, &info );
  }

  double end = get_time_ns();
  double total_ns = end - start;
  double ns_per_call = total_ns / (double)runs;

  printf( "Microbenchmark results:\n" );
  printf( "  Total time for %d runs: %.2f ms\n", runs, total_ns / 1e6 );
  printf( "  Latency per call: %.2f ns\n", ns_per_call );

  printf( "Test 5 PASSED.\n" );
}

int main( void ) {
  printf( "=== Hole Parity Unit Test & Microbenchmark Suite ===\n" );
  init_bitboard();

  test_single_isolated_hole();
  test_multiple_disconnected_holes();
  test_quadrant_bridging_holes();
  test_diagonal_separation();
  test_microbenchmark();

  printf( "=== ALL TESTS PASSED SUCCESSFULLY ===\n" );
  return 0;
}
