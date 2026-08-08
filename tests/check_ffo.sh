#!/bin/sh
#
# Solve a fast subset of the FFO endgame test suite and compare the
# results against the published answers from
# http://radagast.se/othello/ffotest.html
#
# Run from the repository root, typically via "make test".
# Takes roughly 5-10 seconds.

BIN=build/bin/scrzebra
SCRIPT=tests/ffo-quick.scr
OUT=build/ffo-quick.out

if [ ! -x "$BIN" ]; then
  echo "check_ffo: $BIN not found; run 'make scrzebra' first" >&2
  exit 1
fi

# scrzebra loads coeffs2.bin from the working directory
( cd build/bin && ./scrzebra -line 1 -script ../../"$SCRIPT" ../ffo-quick.out ) >/dev/null
if [ ! -f "$OUT" ]; then
  echo "check_ffo: scrzebra produced no output" >&2
  exit 1
fi

# Expected results, one row per script position:
#   FFO# <black discs> <white discs> <acceptable first moves ('|'-separated)>
# FFO #59 has three optimal moves (g8, h4, e8 all win 64-0).
EXPECTED="47 30 34 g2
40 51 13 a2
41 32 32 h4
42 35 29 g2
43 38 26 c7
44 39 25 d2
46 28 36 b3
59 64 0 g8|h4|e8"

# scrzebra copies the script's %-comments into the output file;
# the result lines are the non-comment, non-empty ones.
RESULTS=$(grep -v '^%' "$OUT" | grep -v '^[[:space:]]*$')

status=0
i=0
echo "$EXPECTED" | while read -r ffo eblack ewhite emoves; do
  i=$((i + 1))
  line=$(echo "$RESULTS" | sed -n "${i}p")
  black=$(echo "$line" | awk '{print $1}')
  white=$(echo "$line" | awk '{print $3}')
  move=$(echo "$line" | awk '{print $4}')
  if [ "$black" != "$eblack" ] || [ "$white" != "$ewhite" ]; then
    echo "FAIL  FFO#$ffo: score $black-$white, expected $eblack-$ewhite"
    status=1
  else
    case "|$emoves|" in
      *"|$move|"*)
        echo "ok    FFO#$ffo: $black-$white $move" ;;
      *)
        echo "FAIL  FFO#$ffo: best move $move, expected one of $emoves"
        status=1 ;;
    esac
  fi
  # propagate status out of the pipeline subshell via a marker file
  [ $status -ne 0 ] && touch "$OUT.failed"
done

if [ -f "$OUT.failed" ]; then
  rm -f "$OUT.failed"
  echo "check_ffo: FAILED"
  exit 1
fi
echo "check_ffo: all positions PASSED"
exit 0
