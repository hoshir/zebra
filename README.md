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

The full FFO suite (`data/ffotest.scr`, positions #40-#59) can be solved
and verified with:

```
make test-full
```

**Caveat: this takes a very long time — expect multiple hours.** The
reference result on the author's page is 2h06m for the whole suite (on a
1.33 GHz Athlon); modern machines are faster but the hardest positions
(#53-#58) still take from many minutes up to hours each. Each position's
result and elapsed time is printed as soon as it is solved, and the raw
results are appended to `build/ffo-full.out`.

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

