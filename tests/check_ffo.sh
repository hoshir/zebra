#!/bin/sh
#
# Solve FFO endgame test positions and compare the results against the
# published answers from http://radagast.se/othello/ffotest.html
#
# Usage (from the repository root, typically via make):
#   sh tests/check_ffo.sh [quick|full] [threads]
#
# make passes the thread count through as FFO_THREADS.
#
#   quick   : subset of fast positions (a few seconds), the default
#   full    : all of tests/ffotest.scr -- takes several minutes
#   threads : search threads per position, i.e. scrzebra's -n
#             (default: the number of processors on this machine)
#
# Positions are solved one at a time, each getting the whole machine.
# The endgame search is parallel itself now, so solving several at once
# would just make them fight over the same cores; it would also make the
# elapsed time printed for each position meaningless, and those numbers
# get quoted.
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

# Processors online.  getconf is POSIX and answers on both Linux and
# macOS; sysctl is the fallback for the BSDs that lack the getconf name.
default_threads() {
  n=$(getconf _NPROCESSORS_ONLN 2>/dev/null)
  case "$n" in
    ''|*[!0-9]*|0) n=$(sysctl -n hw.ncpu 2>/dev/null) ;;
  esac
  case "$n" in
    ''|*[!0-9]*|0) n=2 ;;
  esac
  echo "$n"
}

# ----- solve and check one position -----------------------------------
# run_position <idx> <ffo#> <black> <white> <moves>; sets `failed' on a
# mismatch.  Runs in this shell, so it can just set the variable.
run_position() {
  i=$1; ffo=$2; eblack=$3; ewhite=$4; emoves=$5

  pos_start=$(now)
  ( cd build/bin && ./scrzebra -n "$THREADS" -line 1 \
      -script ffo-pos$i.scr ffo-pos$i.out ) >/dev/null
  pos_end=$(now)
  elapsed=$(awk "BEGIN { printf \"%.1f\", $pos_end - $pos_start }")

  line=$(grep -v '^%' build/bin/ffo-pos$i.out 2>/dev/null | \
         grep -v '^[[:space:]]*$' | head -1)
  if [ -z "$line" ]; then
    echo "FAIL  FFO#$ffo: scrzebra produced no output   (${elapsed}s)"
    failed=1
    return
  fi

  black=$(echo "$line" | awk '{print $1}')
  white=$(echo "$line" | awk '{print $3}')
  move=$(echo "$line" | awk '{print $4}')
  if [ "$black" != "$eblack" ] || [ "$white" != "$ewhite" ]; then
    echo "FAIL  FFO#$ffo: score $black-$white, expected $eblack-$ewhite   (${elapsed}s)"
    failed=1
    return
  fi

  case "|$emoves|" in
    *"|$move|"*)
      echo "ok    FFO#$ffo: $black-$white $move   (${elapsed}s)" ;;
    *)
      echo "FAIL  FFO#$ffo: best move $move, expected one of $emoves   (${elapsed}s)"
      failed=1 ;;
  esac
}

# ----- main -----------------------------------------------------------

MODE=${1:-quick}
THREADS=$2
BIN=build/bin/scrzebra

if [ -z "$THREADS" ]; then
  THREADS=$(default_threads)
else
  case "$THREADS" in
    *[!0-9]*|0)
      echo "check_ffo: threads must be a positive integer" >&2
      exit 1 ;;
  esac
fi

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

if [ ! -x "$BIN" ]; then
  echo "check_ffo: $BIN not found; run 'make scrzebra' first" >&2
  exit 1
fi

if [ "$MODE" = "full" ]; then
  echo "check_ffo: solving the full FFO test suite; this takes several minutes."
fi
echo "check_ffo: one position at a time, $THREADS search thread(s) each"

# One position per line, comments stripped
POSFILE=$OUT.positions
rm -f "$OUT"
grep -v '^%' "$SCRIPT" | grep -v '^[[:space:]]*$' > "$POSFILE"

i=0
suite_start=$(now)
while read -r ffo eblack ewhite emoves; do
  i=$((i + 1))
  sed -n "${i}p" "$POSFILE" > build/bin/ffo-pos$i.scr
  run_position "$i" "$ffo" "$eblack" "$ewhite" "$emoves"
  grep -v '^%' build/bin/ffo-pos$i.out 2>/dev/null | \
    grep -v '^[[:space:]]*$' | head -1 >> "$OUT"
  rm -f build/bin/ffo-pos$i.scr build/bin/ffo-pos$i.out
done <<EOF
$EXPECTED
EOF
suite_end=$(now)
total=$(awk "BEGIN { printf \"%.1f\", $suite_end - $suite_start }")

rm -f "$POSFILE"

if [ -n "$failed" ]; then
  echo "check_ffo: FAILED   (total ${total}s)"
  exit 1
fi
echo "check_ffo: all positions PASSED   (total ${total}s)"
exit 0
