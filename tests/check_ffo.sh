#!/bin/sh
#
# Solve FFO endgame test positions and compare the results against the
# published answers from http://radagast.se/othello/ffotest.html
#
# Usage (from the repository root, typically via make):
#   sh tests/check_ffo.sh [quick|full] [jobs] [threads]
#
# make passes these through as FFO_JOBS and FFO_THREADS.
#
#   quick   : subset of fast positions (~5 seconds), the default
#   full    : all of tests/ffotest.scr -- takes a VERY long time
#   jobs    : how many positions to solve in parallel (default 4)
#   threads : search threads per position, i.e. scrzebra's -n
#             (default: whatever scrzebra itself defaults to)
#
# Note that the two multiply: jobs x threads processes' worth of work
# can be running at once.
#
# Positions are solved in separate scrzebra processes (they share only
# the read-only coeffs2.bin), so they can run concurrently.  A result
# line with the elapsed time is printed as soon as each position is
# solved, in completion order.
#
# Expected rows: FFO# <black discs> <white discs> <acceptable first moves>
# FFO #59 has three optimal moves (g8, h4, e8 all win 64-0); all other
# positions have a unique optimal move.

# Wall-clock time in seconds, using only the standard date utility.
# GNU date (Linux) supports nanoseconds via %N; BSD date (macOS) does
# not, in which case we fall back to whole seconds.
if date +%s.%N 2>/dev/null | grep -Eq '^[0-9]+\.[0-9]+$'; then
  now() { date +%s.%N; }
else
  now() { date +%s; }
fi

# ----- worker: solve and check one position ---------------------------
# Invoked (via xargs) as: check_ffo.sh __worker <idx> <ffo#> <black> <white> <moves>
# Inherits OUT and FFO_NFLAG from the parent through the environment.
if [ "$1" = "__worker" ]; then
  i=$2; ffo=$3; eblack=$4; ewhite=$5; emoves=$6

  pos_start=$(now)
  ( cd build/bin && ./scrzebra $FFO_NFLAG -line 1 -script ffo-pos$i.scr ffo-pos$i.out ) >/dev/null
  pos_end=$(now)
  elapsed=$(awk "BEGIN { printf \"%.1f\", $pos_end - $pos_start }")

  line=$(grep -v '^%' build/bin/ffo-pos$i.out 2>/dev/null | \
         grep -v '^[[:space:]]*$' | head -1)
  if [ -z "$line" ]; then
    echo "FAIL  FFO#$ffo: scrzebra produced no output   (${elapsed}s)"
    touch "$OUT.failed"
    exit 0
  fi

  black=$(echo "$line" | awk '{print $1}')
  white=$(echo "$line" | awk '{print $3}')
  move=$(echo "$line" | awk '{print $4}')
  if [ "$black" != "$eblack" ] || [ "$white" != "$ewhite" ]; then
    echo "FAIL  FFO#$ffo: score $black-$white, expected $eblack-$ewhite   (${elapsed}s)"
    touch "$OUT.failed"
  else
    case "|$emoves|" in
      *"|$move|"*)
        echo "ok    FFO#$ffo: $black-$white $move   (${elapsed}s)" ;;
      *)
        echo "FAIL  FFO#$ffo: best move $move, expected one of $emoves   (${elapsed}s)"
        touch "$OUT.failed" ;;
    esac
  fi
  exit 0
fi

# ----- main -----------------------------------------------------------

MODE=${1:-quick}
JOBS=${2:-4}
THREADS=$3
BIN=build/bin/scrzebra

case "$JOBS" in
  ''|*[!0-9]*|0)
    echo "check_ffo: jobs must be a positive integer" >&2
    exit 1 ;;
esac

if [ -n "$THREADS" ]; then
  case "$THREADS" in
    *[!0-9]*|0)
      echo "check_ffo: threads must be a positive integer" >&2
      exit 1 ;;
  esac
  FFO_NFLAG="-n $THREADS"
else
  FFO_NFLAG=""
fi
export FFO_NFLAG

if [ "$MODE" = "full" ]; then
  SCRIPT=tests/ffotest.scr
  OUT=build/ffo-full.out
  # tests/ffotest.scr order: #47 first, then #40-#59 in order
  # (#47 appears a second time in its natural position).
  EXPECTED="47 30 34 g2
40 51 13 a2
41 32 32 h4
42 35 29 g2
43 38 26 c7
44 39 25 d2
45 35 29 b2
46 28 36 b3
47 30 34 g2
48 18 46 f6
49 40 24 e1
50 37 27 d8
51 29 35 e2
52 32 32 a3
53 31 33 d8
54 31 33 c7
55 32 32 g6
56 31 33 h5
57 27 37 a6
58 34 30 g1
59 64 0 g8|h4|e8"
else
  SCRIPT=tests/ffo-quick.scr
  OUT=build/ffo-quick.out
  EXPECTED="47 30 34 g2
40 51 13 a2
41 32 32 h4
42 35 29 g2
43 38 26 c7
44 39 25 d2
46 28 36 b3
59 64 0 g8|h4|e8"
fi
export OUT

if [ ! -x "$BIN" ]; then
  echo "check_ffo: $BIN not found; run 'make scrzebra' first" >&2
  exit 1
fi

if [ "$MODE" = "full" ]; then
  echo "check_ffo: solving the full FFO test suite; this takes a LONG time."
fi
if [ -n "$THREADS" ]; then
  echo "check_ffo: running $JOBS position(s) in parallel, $THREADS thread(s) each"
else
  echo "check_ffo: running $JOBS position(s) in parallel"
fi

# One position per line, comments stripped
POSFILE=$OUT.positions
grep -v '^%' "$SCRIPT" | grep -v '^[[:space:]]*$' > "$POSFILE"

# Per-position script files and the worker argument list
ARGSFILE=$OUT.args
rm -f "$OUT" "$OUT.failed" "$ARGSFILE"
i=0
echo "$EXPECTED" | while read -r ffo eblack ewhite emoves; do
  i=$((i + 1))
  sed -n "${i}p" "$POSFILE" > build/bin/ffo-pos$i.scr
  echo "__worker $i $ffo $eblack $ewhite $emoves" >> "$ARGSFILE"
done

suite_start=$(now)
xargs -L1 -P "$JOBS" sh "$0" < "$ARGSFILE"
suite_end=$(now)
total=$(awk "BEGIN { printf \"%.1f\", $suite_end - $suite_start }")

# Collect raw results in position order, then clean up
n=$(wc -l < "$POSFILE")
i=0
while [ $i -lt "$n" ]; do
  i=$((i + 1))
  grep -v '^%' build/bin/ffo-pos$i.out 2>/dev/null | \
    grep -v '^[[:space:]]*$' | head -1 >> "$OUT"
  rm -f build/bin/ffo-pos$i.scr build/bin/ffo-pos$i.out
done
rm -f "$POSFILE" "$ARGSFILE"

if [ -f "$OUT.failed" ]; then
  rm -f "$OUT.failed"
  echo "check_ffo: FAILED   (total ${total}s)"
  exit 1
fi
echo "check_ffo: all positions PASSED   (total ${total}s)"
exit 0
