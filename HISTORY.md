# What has been tried

A record of the performance work on this fork: what landed, what was
measured and rejected, what the engine turned out to be doing, and what
is worth trying next. The rejected experiments are the larger half and
the more useful one — several of them look obviously right on paper.

Numbers are from an Apple M2 (4 performance + 4 efficiency cores,
16 GB). Endgame node counts at **one thread are exact and
deterministic**, so they are the unit of account throughout; wall-clock
times are noisier and are quoted only where several runs agree.

## Landed

| PR | What | Effect |
|---|---|---|
| [#14](https://github.com/hoshir/zebra/pull/14) | Parallel endgame search (YBWC) | the fork-join pool and the first split |
| [#20](https://github.com/hoshir/zebra/pull/20) | The board as a single 64-bit word | replaced the 32+32 split representation; one branch-free flip routine replaced 2400 lines of per-square code |
| [#21](https://github.com/hoshir/zebra/pull/21) | Incremental evaluation, bitboard moves in the midgame | the 46 pattern indices are maintained by make/unmake instead of rebuilt |
| [#22](https://github.com/hoshir/zebra/pull/22) | The hot thread-local state in one object | one `_tlv_get_addr` call per access instead of one per variable |
| [#23](https://github.com/hoshir/zebra/pull/23) | The board into that object too | |
| [#24](https://github.com/hoshir/zebra/pull/24) | `CountFlips_bitboard` covered by fliptest | it had **no** coverage and was silently wrong |
| [#25](https://github.com/hoshir/zebra/pull/25) | The endgame's state into that object | |
| [#26](https://github.com/hoshir/zebra/pull/26) | Count the nodes the workers searched | worker nodes were dropped on the floor, which made 1-thread and 8-thread counts incomparable |
| [#27](https://github.com/hoshir/zebra/pull/27) | Let a split node split again | **FFO #42–#58: 407.1s → 302.4s (−26%)**, no position slower |
| [#28](https://github.com/hoshir/zebra/pull/28) | Filled diagonals without a loop | identical node counts, −1.2% |

#20–#23 together took the midgame from 7.9M to about 11.9M nps.

### #27 in more detail

The endgame split at the root of a subtree and handed the siblings to
the pool, but nothing inside a job could split further, so threads that
finished early sat idle until the longest job returned.

Who may help with which batch is deliberately asymmetric, and that is
the whole correctness argument. The search keeps state indexed by ply —
move lists, hash keys, flip masks — which a job starting from a
different node overwrites from its own ply downwards. So a thread
suspended in its own search may only run jobs of the batch it is
waiting on, which start at exactly the node it is suspended at; a
parked worker is inside no search and has nothing to protect, so it
takes work from anywhere. A first version that let everyone help
everyone segfaulted immediately.

Nesting on its own **lost**: FFO #58 went from 25s to 96s with six times
the nodes, because a batch searches every sibling including the ones a
cutoff would have spared. It only became a win once a batch could be
abandoned as soon as one of its moves reached beta.

## Tried and rejected

| Idea | Result |
|---|---|
| NEON mobility | within noise; kept on a local `neon-mobility` bookmark, deliberately not rebased forward |
| Scalar incremental evaluation accumulator | lost |
| Dispatching split jobs in move order | +6.5% |
| Sweeping `PARALLEL_SPLIT_DEPTH` (10/12/14/16) | completely flat — the constant cannot change the number of concurrent jobs, only where splitting starts |
| Nested splitting without cancellation | FFO #58 25s → 96s |
| Capping a batch to the number of idle threads | worse — it dispatches the best-ordered moves, which are exactly the ones that fail high and get discarded |
| Extending the specialised solvers to five empties | naive version +38% nodes on #48 (it drops parity ordering); a faithful version with identical node counts gained 0.8% for ~130 lines duplicating `solve_parity` |
| Transposition table 4 MB → 1 GB | flat on 24–25 empty positions (but see below) |
| Refitting the evaluation coefficients | flat on 24–25 empty positions (but see below) |

## What the engine turned out to be doing

These cost measurements to establish and are worth more than any single
change.

**The evaluation is the endgame's move ordering.** Replacing it with an
information-free one (all pattern coefficients zero) costs **74x** the
nodes on FFO #41 and **869x** on #44. It reaches the endgame through the
shallow `tree_search` that `end_tree_search` uses for fastest-first
ordering — not a minor input.

**The exact pass is where the endgame's time goes.** FFO #45 at one
thread: 29.6M nodes cumulative at 95% selectivity, 58.9M at 98%, 100.7M
at 99%, **470.1M** exact. The selective passes are 21% of the total, and
MPC by definition cannot touch the exact pass, which already starts
from the right window. So MPC calibration is capped at about 21% for
exact solving.

**The transposition table covers a small minority of nodes.**
`HASH_DEPTH` is `LOW_LEVEL_DEPTH + 1` = 9, so nothing at nine empties or
fewer touches the table, and that is where the bulk of the nodes are.

**Ordering matters far more than bookkeeping in the shallow solvers.**
Dropping parity ordering at five empties costs 38% more nodes on #48.
The profile that attributes ~41% of time to the shallow solvers is time
in the search, not in the list handling around it.

**Zebra's stability bound is weak, not under-used.** Attempting the
cutoff at every node instead of only above `stability_threshold[]`
changes FFO #44 by 0.1% — the bound `64 - 2 * count_stable` rarely
beats alpha at all on 24–25 empty positions.

**Node counting is comparable with Edax.** Edax builds with
`COUNT_NODES 7` and counts the one-empty children inside
`board_solve_2`, exactly as `solve_two_empty` does here. The node gap is
real, not a difference in convention.

## Where the gap to Egaroucid is

Published figures, FFO #40–#59 on a Core i9-13900K: Egaroucid 7.8.0
takes 20.2s over 14.59G nodes; Edax v3 takes 23.1s over 27.53G. This
fork takes 302.4s over 49.47G for #42–#58 on an 8-thread M2.

Decomposing the 15x against Egaroucid: **3.4x is node count** and 4.4x
is throughput, and the throughput term is almost entirely hardware —
32 threads against 8. Per-thread throughput is within about 10%, on a
chip clocked considerably lower.

The instructive row is Edax: on the same machine it reaches 1.6x
Egaroucid's nps and is still slower, because it searches 1.9x the
nodes. **This class of engine is not won on speed per node.** Our node
count sits at 1.8x Edax and 3.4x Egaroucid — the same kind of gap that
separates those two.

**The 3.4x has not been attributed.** Five candidates were measured and
none is the main term. That is itself a finding: it suggests the gap is
spread thin rather than sitting in one place.

## Ideas worth trying

Ordered by measured evidence, not by appeal.

**1. Refit the evaluation coefficients.** Already measured: FFO #50
drops from 2.04G to ~1.70G nodes at one thread, **−17%**, with correct
scores; held-out prediction error improves 12–18% on every stage.
`tools/patdump.c` and `tools/patfit.c` do the work and are verified end
to end — decoding `coeffs2.bin` and summing the coefficients at
patdump's indices reproduces `pattern_evaluation()` exactly, and
re-encoding round-trips byte for byte. **Blocked on a permission
question, not a technical one:** the training data is published for free
use in one's own Othello AI with redistribution prohibited, and whether
fitted coefficients may ship in this repository is the data author's
call.

**2. Lower `stability_threshold[]`.** FFO #50: **−19% nodes, −11%
time**. But FFO #54 gains nothing and loses 1.6% of its time, so this
needs a wide measurement before it is committed to — it has the same
shape as the nested-split experiment, which averaged well while hiding a
4x worst case.

**3. Size the transposition table for the machine.** FFO #54: 4 MB →
256 MB is **−23% nodes, −12% time**. Deliberately deferred: the optimum
depends on cache size, so it is not a portable win and wants either a
runtime default derived from the machine or an explicit setting.

**4. Endgame-specific move ordering.** The highest ceiling, since
ordering is worth two to three orders of magnitude, and the least
specified. Zebra reuses the midgame evaluation through a shallow
search; modern engines carry ordering machinery of their own — mobility,
potential mobility, corner stability. What is actually missing has not
been identified, so start with a diagnostic: does a deeper `pre_depth`
reduce nodes? If yes, ordering is not saturated and is worth investing
in; if no, the depth of lookahead is not the constraint and the missing
piece is a different signal.

**5. MPC calibration.** Last, because its ceiling is measured at ~21%
and its statistics are fitted to the current evaluation — so it should
follow a coefficient refit rather than precede it.

## How to measure here

Two habits caught real bugs that the test suite did not, and one
mistake was made three times.

**Node counts at one thread are the gate.** Correct FFO scores prove
nothing about a search change: an exact solver returns the right answer
however badly it is ordered. Two behaviour bugs passed `make test` and
the full FFO suite and were caught only by comparing node counts — a
`make_move` that clobbered the global `bb_flips` (1.3M → 10.9M nodes on
#59) and a `CountFlips_bitboard` that lost overlapping bits.

**Diagnose on deep positions.** FFO #41/#44/#45 (24–25 empties) report
"this lever is dead" for three separate levers that are worth 17–23% on
#50 and #54 (26–28 empties). Ordering quality compounds with depth, and
the gap being chased lives in the deep positions. The cost — 50–150s per
position per configuration — is exactly what tempts you back to the
quick ones.

**`make` does not rebuild when only `CFLAGS` change.** A `-D` parameter
sweep silently reuses the first binary for every configuration after the
first. Identical node counts across supposedly different builds are a
build bug until proven otherwise, not a finding.
