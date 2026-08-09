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
| FFO #45  |   11.9 s |     3.3 s |
| FFO #48  |    7.0 s |     2.3 s |
| FFO #49  |    9.6 s |     3.6 s |
| FFO #51  |   10.7 s |     4.0 s |

## Testing

Run the test suite with:

```
make test
```

It takes about 5-10 seconds and runs two tests:

* `tests/fliptest.c` — differential test verifying that the two
  independent disc-flipping implementations (bitboard `TestFlips_bitboard`
  and board-array `DoFlips`) agree on 50,000 random positions. The endgame
  search relies on their agreement; a divergence corrupts the flip stack
  and crashes.
* `tests/check_ffo.sh` — solves a fast subset of the FFO endgame test
  suite (`tests/ffo-quick.scr`: positions #40-#44, #46, #47 and #59) with
  `scrzebra` and checks the exact scores and best moves against the
  published answers from http://radagast.se/othello/ffotest.html
  Positions are solved in parallel (4 at a time by default) and each
  position's search can use several threads: `make test FFO_JOBS=8
  FFO_THREADS=2`, or `sh tests/check_ffo.sh quick 8 2`. The two
  multiply, so keep their product near the core count. `FFO_THREADS`
  defaults to whatever `scrzebra` itself defaults to.

The full FFO suite (`tests/ffotest.scr`, positions #40-#59) can be solved
and verified with:

```
make test-full
```

**Caveat: this takes several minutes** — about 7 on an 8-core arm64 Mac
with the default `FFO_JOBS=4 FFO_THREADS=2`. Most positions solve in
under 15 seconds; the tail is #55 at roughly 6.5 minutes on its own,
then #54 and #57 at a little over 2 minutes each. For scale, the
reference result on the author's page is 2h06m for the whole suite on a
1.33 GHz Athlon.

Positions run in parallel (default 4, e.g. `make test-full FFO_JOBS=8`
to change it), each position's result and elapsed time is printed as
soon as it is solved, and the raw results are collected in
`build/ffo-full.out`.

## Web sites

* Gunner's website: http://radagast.se/othello/
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

