Zebra
=====

Othello program created by Gunnar Andersson

This repository has started by uploading original code, as of 2014/04/29, by Gunnar Andersson

The code in this repository has since been modified (e.g. ported to macOS,
directory structure reorganized). If you want the original files as uploaded,
get the source from the `original` tag:

```
git checkout original
```

## Parallel endgame search

`zebra` and `scrzebra` take `-n <threads>` (default 2) to search the
endgame on several threads. Once a node has searched its first move, the
remaining moves are handed to a worker pool with a null window; the ones
proved not to beat alpha are then skipped by the sequential search.
Pass `-n 1` for a purely sequential search.

Exact scores and best moves do not depend on the thread count. The tail
of the principal variation can, because the transposition table is
shared and gets filled in a different order.

Measured on an 8-core machine:

| Position | 1 thread | 8 threads |
|----------|---------:|----------:|
| FFO #45  |   12.0 s |     2.7 s |
| FFO #48  |    8.1 s |     2.0 s |
| FFO #49  |    9.9 s |     2.5 s |
| FFO #51  |   10.6 s |     3.0 s |

## Transposition table

The transposition table defaults to 256 MB (`-h 24`, $2^{24}$ = 16,777,216 entries
of 16 bytes each). Entries are grouped into 32-byte 2-entry buckets and allocated
with 64-byte hardware cacheline alignment to guarantee zero cacheline splitting.
Software prefetching (`__builtin_prefetch`) is used on hash table lookups to hide
main memory latency. Thread-safe lockless reads and writes are verified with
mathematical XOR checksums across key and payload fields. Override the size with
`-h <bits>`.

## Testing

Run the test suite with:

```
make test
```

It takes about 3-5 seconds and runs four tests:

* `tests/fliptest.c` — differential test verifying that the two
  independent disc-flipping implementations (bitboard `TestFlips_bitboard`
  and board-array `DoFlips`) agree on 50,000 random positions. The endgame
  search relies on their agreement; a divergence corrupts the flip stack
  and crashes.
* `tests/threadtest.c` — verifies the fork-join pool synchronization, job
  distribution, and single- vs multi-threaded execution.
* `tests/hashtest.c` — concurrent stress test verifying that simultaneous
  reads and writes across multiple threads in the transposition table do not
  produce torn reads (mixed keys and payloads).
* `tests/check_ffo.sh` — solves a fast subset of the FFO endgame test
  suite (`tests/ffo-quick.scr`: positions #40-#44, #46, #47 and #59) with
  `scrzebra` and checks the exact scores and best moves against the
  published answers from http://radagast.se/othello/ffotest.html
  Positions are solved one at a time, each search using one thread per
  processor. Override that with `make test FFO_THREADS=4`, or
  `sh tests/check_ffo.sh quick 4`.

The full FFO suite (`tests/ffotest.scr`, positions #40-#59) can be solved
and verified with:

```
make test-full
```

**Caveat: this takes several minutes** — about 4.8 on an 8-core arm64
Mac. Most positions solve in under 10 seconds; the tail is #55 at
roughly 1.8 minutes on its own, then #57 at under 50 seconds and #54 at just
under 35 seconds. For scale, the reference result on the author's page is 2h06m
for the whole suite on a 1.33 GHz Athlon.

Each position's result and elapsed time is printed as soon as it is
solved, and the raw results are collected in `build/ffo-full.out`.

## Benchmarking

For automated benchmarking and regression testing, `scripts/eval_candidate.py`
evaluates positions from the FFO test suite against a baseline with compact
real-time progress reporting:

```
# Fast screening test (2 positions)
./scripts/eval_candidate.py --mode screen --threads 8

# Full 19-position benchmark
./scripts/eval_candidate.py --mode full --threads 8

# Save full results to JSON
./scripts/eval_candidate.py --mode full --threads 8 --save-json results.json
```

## Evaluation Coefficient Tooling & Tuning

Tools for inspecting, verifying, and tuning Zebra's evaluation pattern coefficients (`data/coeffs2.bin`):

```bash
# Verify round-trip integrity of coeffs2.bin
./scripts/coeffs_tool.py verify-roundtrip data/coeffs2.bin

# Generate clean-room training games via parallel self-play
./scripts/generate_eval_data.py -n 500 -o positions.txt

# Run automated evaluation tuning pipeline using PyTorch (Texel loss + AdamW)
uv run ./scripts/tune_eval.py --method pytorch --generate-games 3000 --stages 7 8 9 10 -o data/coeffs2_candidate.bin
```

## Web sites

* Gunnar's website: http://radagast.se/othello/
* Original source code: http://radagast.se/othello/zebra.tar.gz


## README (ORIGINAL)
----- LICENSE -----

This piece of software is released under the GPL.
See the file COPYING for more information.

----- COMPILING -----

You need make and a C compiler, e.g. GCC, to compile Zebra.  Run "make all"
to build Zebra and some tools.  I have built Zebra using Cygwin and GCC 3.2.
Using an older or newer version of GCC should work fine.  ICC should also
work, but I have not access to it.  The inline assembly can only be used
if you run GCC, so performance will probably take a big hit if you use a
compiler that is not capable of reading GCC-style inline assembly.

----- RUNNING -----

Copy coeffs2.bin and book.bin from the directory where WZebra is installed
to the directory where Zebra and its tools are found.
"./zebra -help" describes the available options.  If you find the help text
too terse: Use the force, read the source.

