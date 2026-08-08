#!/bin/sh
#
# Solve FFO endgame test positions and compare the results against the
# published answers from http://radagast.se/othello/ffotest.html
#
# Usage (from the repository root, typically via make):
#   sh tests/check_ffo.sh          # quick subset (~5-10 seconds)
#   sh tests/check_ffo.sh full     # all of data/ffotest.scr (takes HOURS)
#
# Each position is solved in its own scrzebra invocation so that the
# elapsed time per position can be reported.
#
# Expected rows: FFO# <black discs> <white discs> <acceptable first moves>
# FFO #59 has three optimal moves (g8, h4, e8 all win 64-0); all other
# positions have a unique optimal move.

MODE=${1:-quick}
BIN=build/bin/scrzebra

if [ "$MODE" = "full" ]; then
  SCRIPT=data/ffotest.scr
  OUT=build/ffo-full.out
  # data/ffotest.scr order: #47 first, then #40-#59 in order
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
  echo "check_ffo: solving the full FFO test suite; this takes a LONG time."
  echo "check_ffo: each position is reported as soon as it is solved."
fi

now() {
  perl -MTime::HiRes=time -e 'printf "%.2f\n", time'
}

# One position per line, comments stripped
POSFILE=$OUT.positions
grep -v '^%' "$SCRIPT" | grep -v '^[[:space:]]*$' > "$POSFILE"

rm -f "$OUT" "$OUT.failed"
suite_start=$(now)
i=0
echo "$EXPECTED" | while read -r ffo eblack ewhite emoves; do
  i=$((i + 1))
  sed -n "${i}p" "$POSFILE" > build/bin/ffo-current.scr

  pos_start=$(now)
  ( cd build/bin && ./scrzebra -line 1 -script ffo-current.scr ffo-current.out ) >/dev/null
  pos_end=$(now)
  elapsed=$(awk "BEGIN { printf \"%.1f\", $pos_end - $pos_start }")

  line=$(grep -v '^%' build/bin/ffo-current.out 2>/dev/null | \
         grep -v '^[[:space:]]*$' | head -1)
  if [ -z "$line" ]; then
    echo "FAIL  FFO#$ffo: scrzebra produced no output   (${elapsed}s)"
    touch "$OUT.failed"
    continue
  fi
  echo "$line" >> "$OUT"

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
done
suite_end=$(now)
total=$(awk "BEGIN { printf \"%.1f\", $suite_end - $suite_start }")

rm -f build/bin/ffo-current.scr build/bin/ffo-current.out "$POSFILE"

if [ -f "$OUT.failed" ]; then
  rm -f "$OUT.failed"
  echo "check_ffo: FAILED   (total ${total}s)"
  exit 1
fi
echo "check_ffo: all positions PASSED   (total ${total}s)"
exit 0
