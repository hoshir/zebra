#!/usr/bin/env python3
"""
scripts/eval_candidate.py - Automated Evaluation and Benchmarking Harness for Zebra.

Designed for autonomous optimization agents.
Evaluates algorithmic efficiency, correctness, and multi-core scaling
without overfitting to specific host CPU or memory architectures.

Primary Unit of Account: Deterministic 1-thread node counts across FFO endgame positions.
Secondary Unit of Account: Multi-threaded scaling (NPS & wall-clock time).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time

class HeartbeatMonitor:
    """Emits periodic heartbeats on long-running tasks without terminal spam."""
    def __init__(self, message_fn, interval=8.0):
        self.message_fn = message_fn
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread:
            self.stop_event.set()
            self.thread.join(timeout=1.0)

    def _run(self):
        start_time = time.time()
        while not self.stop_event.wait(self.interval):
            elapsed = int(time.time() - start_time)
            self.message_fn(elapsed)


# Complete 19 FFO positions (FFO #40 - #59)
# Format: (name, board_string, expected_black, expected_white, list_of_valid_first_moves)
FFO_POSITIONS = [
    ("FFO #40", "O--OOOOX-OOOOOOXOOXXOOOXOOXOOOXXOOOOOOXX---OOOOX----O--X-------- X", 51, 13, ["a2"]),
    ("FFO #41", "-OOOOO----OOOOX--OOOOOO-XXXXXOO--XXOOX--OOXOXX----OXXO---OOO--O- X", 32, 32, ["h4"]),
    ("FFO #42", "--OOO-------XX-OOOOOOXOO-OOOOXOOX-OOOXXO---OOXOO---OOOXO--OOOO-- X", 35, 29, ["g2"]),
    ("FFO #43", "--XXXXX---XXXX---OOOXX---OOXXXX--OOXXXO-OOOOXOO----XOX----XXXXX- O", 38, 26, ["c7"]),
    ("FFO #44", "--O-X-O---O-XO-O-OOXXXOOOOOOXXXOOOOOXX--XXOOXO----XXXX-----XXX-- O", 39, 25, ["d2"]),
    ("FFO #45", "---XXXX-X-XXXO--XXOXOO--XXXOXO--XXOXXO---OXXXOO-O-OOOO------OO-- X", 35, 29, ["b2"]),
    ("FFO #46", "---XXX----OOOX----OOOXX--OOOOXXX--OOOOXX--OXOXXX--XXOO---XXXX-O- X", 28, 36, ["b3"]),
    ("FFO #47", "-OOOOO----OOOO---OOOOX--XXXXXX---OXOOX--OOOXOX----OOXX----XXXX-- O", 30, 34, ["g2"]),
    ("FFO #48", "-----X--X-XXX---XXXXOO--XOXOOXX-XOOXXX--XOOXX-----OOOX---XXXXXX- O", 18, 46, ["f6"]),
    ("FFO #49", "--OX-O----XXOO--OOOOOXX-OOOOOX--OOOXOXX-OOOOXX-----OOX----X-O--- X", 40, 24, ["e1"]),
    ("FFO #50", "----X-----XXX----OOOXOOO-OOOXOOO-OXOXOXO-OOXXOOO--OOXO----O--O-- X", 37, 27, ["d8"]),
    ("FFO #51", "----O-X------X-----XXXO-OXXXXXOO-XXOOXOOXXOXXXOO--OOOO-O----OO-- O", 29, 35, ["e2"]),
    ("FFO #52", "---X-------OX--X--XOOXXXXXXOXXXXXXXOOXXXXXXOOOXX--XO---X-------- O", 32, 32, ["a3"]),
    ("FFO #53", "----OO-----OOO---XXXXOOO--XXOOXO-XXXXXOO--OOOXOO--X-OX-O-----X-- X", 31, 33, ["d8"]),
    ("FFO #54", "--OOO---XXOO----XXXXOOOOXXXXOX--XXXOXX--XXOOO------OOO-----O---- X", 31, 33, ["c7"]),
    ("FFO #55", "--------X-X------XXXXOOOOOXOXX--OOOXXXX-OOXXXX--O-OOOX-----OO--- O", 32, 32, ["g6"]),
    ("FFO #56", "--XXXXX---XXXX---OOOXX---OOXOX---OXXXXX-OOOOOXO----OXX---------- O", 31, 33, ["h5"]),
    ("FFO #57", "-------------------XXOOO--XXXOOO--XXOXOO-OOOXXXO--OXOO-O-OOOOO-- X", 27, 37, ["a6"]),
    ("FFO #58", "--XOOO----OOO----OOOXOO--OOOOXO--OXOXXX-OOXXXX----X-XX---------- X", 34, 30, ["g1"]),
    ("FFO #59", "-----------------------O--OOOOO---OOOOOXOOOOXXXX--XXOOXX--XX-O-X X", 64, 0, ["g8", "h4", "e8"]),
]

# Screening set: representative mid-depth (#45) and deep (#50) positions (~15-20s on 1 thread)
SCREENING_NAMES = {"FFO #45", "FFO #50"}


def get_default_threads():
    """Detect available physical/logical cores, defaulting safely to 4 if indeterminate."""
    count = os.cpu_count()
    return count if count and count > 0 else 4


def run_test_suite(repo_root):
    """Run `make test` to verify zero test regressions."""
    res = subprocess.run(
        ["make", "test"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    passed = (res.returncode == 0) and ("check_ffo: all positions PASSED" in res.stdout)
    return passed, res.stdout + res.stderr


def solve_position(repo_root, pos_str, threads, hash_bits):
    """
    Solve a single position using build/bin/scrzebra.
    Returns: dict with (success, score_black, score_white, first_move, nodes, time_sec, nps, error_msg)
    """
    bin_dir = os.path.join(repo_root, "build", "bin")
    scrzebra = os.path.join(bin_dir, "scrzebra")
    if not os.path.exists(scrzebra):
        return {"success": False, "error": f"Binary {scrzebra} does not exist. Run 'make' first."}

    out_file = f"eval_tmp_{os.getpid()}_{time.time_ns()}.out"
    out_path = os.path.join(bin_dir, out_file)

    cmd = [
        "./scrzebra",
        "-n", str(threads),
        "-h", str(hash_bits),
        "-e", "0",
        "-line", "1",
        "-script", "/dev/stdin",
        out_file
    ]

    try:
        p = subprocess.Popen(
            cmd,
            cwd=bin_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = p.communicate(input=pos_str + "\n")

        # Parse stdout metrics
        time_match = re.search(r"Total time:\s+([0-9.]+)\s+s", stdout)
        nodes_match = re.search(r"Total nodes:\s+([0-9]+)", stdout)
        nps_match = re.search(r"Average speed:\s+([0-9]+)\s+nps", stdout)

        time_sec = float(time_match.group(1)) if time_match else None
        nodes = int(nodes_match.group(1)) if nodes_match else None
        nps = int(nps_match.group(1)) if nps_match else None

        # Parse output file for score and move
        score_black = None
        score_white = None
        first_move = None

        if os.path.exists(out_path):
            with open(out_path, "r") as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith("%")]
            try:
                os.remove(out_path)
            except OSError:
                pass

            if lines:
                parts = lines[0].split()
                if len(parts) >= 4 and parts[1] == "-":
                    try:
                        score_black = int(parts[0])
                        score_white = int(parts[2])
                        first_move = parts[3]
                    except ValueError:
                        pass

        if nodes is None or time_sec is None or score_black is None:
            return {
                "success": False,
                "error": f"Failed to parse scrzebra output. stdout: {stdout[:300]}, stderr: {stderr[:300]}"
            }

        return {
            "success": True,
            "score_black": score_black,
            "score_white": score_white,
            "first_move": first_move,
            "nodes": nodes,
            "time_sec": time_sec,
            "nps": nps if nps else int(nodes / time_sec if time_sec > 0 else 0),
            "error": None
        }

    except Exception as e:
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except OSError:
                pass
        return {"success": False, "error": str(e)}


def evaluate_suite(repo_root, positions, threads, hash_bits, verbose=False, baseline_results=None, progress="compact", quiet=None):
    """Evaluate a set of positions and verify correctness with real-time progress."""
    if quiet is True:
        progress = "none"

    results = {}
    all_correct = True
    total_positions = len(positions)
    suite_start = time.time()

    if progress == "dots":
        sys.stderr.write(f"Solving {total_positions} positions (threads={threads}, -h {hash_bits}): ")
        sys.stderr.flush()

    for idx, (name, board, exp_b, exp_w, valid_moves) in enumerate(positions, 1):
        base_info = ""
        if baseline_results and name in baseline_results:
            b_sec = baseline_results[name].get("time_sec")
            if b_sec is not None:
                base_info = f" [baseline ~{b_sec:.1f}s]"

        monitor = None
        if progress == "compact":
            def on_heartbeat(elapsed_pos):
                sys.stderr.write(f"     ... {name} still running ({elapsed_pos}s elapsed){base_info}\n")
                sys.stderr.flush()
            monitor = HeartbeatMonitor(on_heartbeat, interval=8.0)
            monitor.start()

        try:
            res = solve_position(repo_root, board, threads, hash_bits)
        finally:
            if monitor:
                monitor.stop()

        if not res["success"]:
            all_correct = False
            results[name] = {"correct": False, "error": res["error"]}
            if progress == "compact":
                sys.stderr.write(f"[{idx:2d}/{total_positions:2d}] {name}: FAILED ({res['error']})\n")
                sys.stderr.flush()
            elif progress == "dots":
                sys.stderr.write("F")
                sys.stderr.flush()
            continue

        score_ok = (res["score_black"] == exp_b) and (res["score_white"] == exp_w)
        move_ok = res["first_move"] in valid_moves
        is_correct = score_ok and move_ok
        if not is_correct:
            all_correct = False

        status_str = "PASS" if is_correct else "MISMATCH"
        delta_str = ""
        if baseline_results and name in baseline_results and is_correct:
            b_nodes = baseline_results[name].get("nodes", 0)
            b_time = baseline_results[name].get("time_sec", 0.0)
            if b_nodes > 0:
                n_delta = ((res["nodes"] - b_nodes) / b_nodes) * 100.0
                t_delta = ((res["time_sec"] - b_time) / b_time) * 100.0 if b_time > 0 else 0.0
                n_sign = "+" if n_delta > 0 else ""
                t_sign = "+" if t_delta > 0 else ""
                delta_str = f" | vs base: {n_sign}{n_delta:.2f}% nodes, {t_sign}{t_delta:.1f}% time"

        nodes_m = res["nodes"] / 1e6
        elapsed = int(time.time() - suite_start)

        if progress == "compact":
            sys.stderr.write(
                f"[{idx:2d}/{total_positions:2d}] {name}: {status_str} {res['score_black']}-{res['score_white']} {res['first_move']} "
                f"({res['time_sec']:.2f}s, {nodes_m:.1f}M nodes{delta_str}) [elapsed: {elapsed}s]\n"
            )
            sys.stderr.flush()
        elif progress == "dots":
            sys.stderr.write("." if is_correct else "X")
            sys.stderr.flush()

        results[name] = {
            "correct": is_correct,
            "score": f"{res['score_black']}-{res['score_white']}",
            "expected_score": f"{exp_b}-{exp_w}",
            "move": res["first_move"],
            "expected_moves": valid_moves,
            "nodes": res["nodes"],
            "time_sec": res["time_sec"],
            "nps": res["nps"],
            "error": None if is_correct else f"Mismatch: got {res['score_black']}-{res['score_white']} {res['first_move']}"
        }

    if progress == "dots":
        total_time = int(time.time() - suite_start)
        sys.stderr.write(f" done ({total_time}s)\n")
        sys.stderr.flush()

    return results, all_correct


def compare_with_baseline(candidate_results, baseline_results):
    """Compute per-position and aggregate deltas against baseline."""
    comparison = {}
    tot_cand_nodes = 0
    tot_base_nodes = 0
    tot_cand_time = 0.0
    tot_base_time = 0.0

    for name, cand in candidate_results.items():
        if name not in baseline_results:
            continue
        base = baseline_results[name]
        if not cand.get("correct") or not base.get("correct"):
            continue

        c_nodes = cand["nodes"]
        b_nodes = base["nodes"]
        c_time = cand["time_sec"]
        b_time = base["time_sec"]

        tot_cand_nodes += c_nodes
        tot_base_nodes += b_nodes
        tot_cand_time += c_time
        tot_base_time += b_time

        node_delta_pct = ((c_nodes - b_nodes) / b_nodes * 100.0) if b_nodes > 0 else 0.0
        time_delta_pct = ((c_time - b_time) / b_time * 100.0) if b_time > 0 else 0.0

        comparison[name] = {
            "candidate_nodes": c_nodes,
            "baseline_nodes": b_nodes,
            "node_delta_pct": round(node_delta_pct, 2),
            "candidate_time": c_time,
            "baseline_time": b_time,
            "time_delta_pct": round(time_delta_pct, 2),
        }

    tot_node_delta_pct = (
        round((tot_cand_nodes - tot_base_nodes) / tot_base_nodes * 100.0, 2)
        if tot_base_nodes > 0 else 0.0
    )
    tot_time_delta_pct = (
        round((tot_cand_time - tot_base_time) / tot_base_time * 100.0, 2)
        if tot_base_time > 0 else 0.0
    )

    summary = {
        "total_candidate_nodes": tot_cand_nodes,
        "total_baseline_nodes": tot_base_nodes,
        "total_node_delta_pct": tot_node_delta_pct,
        "total_candidate_time": round(tot_cand_time, 2),
        "total_baseline_time": round(tot_base_time, 2),
        "total_time_delta_pct": tot_time_delta_pct,
    }

    return comparison, summary


def generate_text_table(comparison, summary, mode, threads, hash_bits):
    """Format clean, plain-text summary table optimized for terminal width (< 68 chars)."""
    lines = []
    lines.append(f"Benchmark ({mode.upper()}, threads={threads}, hash_bits={hash_bits}):")
    header = f"  {'Pos':<7} {'Candidate':>14} {'Baseline':>14} {'Node Δ':>9}   {'Time':>14}"
    sep = "  " + "-" * (len(header) - 2)
    lines.append(header)
    lines.append(sep)

    for name, d in sorted(comparison.items()):
        node_sign = "+" if d["node_delta_pct"] > 0 else ""
        time_sign = "+" if d["time_delta_pct"] > 0 else ""
        t_cand = f"{d['candidate_time']:.1f}s"
        t_delta = f"({time_sign}{d['time_delta_pct']:.1f}%)"
        time_str = f"{t_cand:>6} {t_delta:>7}"
        lines.append(
            f"  {name:<7} {d['candidate_nodes']:>14,} {d['baseline_nodes']:>14,} "
            f"{node_sign}{d['node_delta_pct']:>7.2f}%   {time_str}"
        )

    lines.append(sep)
    tot_node_sign = "+" if summary["total_node_delta_pct"] > 0 else ""
    tot_time_sign = "+" if summary["total_time_delta_pct"] > 0 else ""
    tot_t_cand = f"{summary['total_candidate_time']:.1f}s"
    tot_t_delta = f"({tot_time_sign}{summary['total_time_delta_pct']:.1f}%)"
    tot_time_str = f"{tot_t_cand:>6} {tot_t_delta:>7}"
    lines.append(
        f"  {'TOTAL':<7} {summary['total_candidate_nodes']:>14,} {summary['total_baseline_nodes']:>14,} "
        f"{tot_node_sign}{summary['total_node_delta_pct']:>7.2f}%   {tot_time_str}"
    )
    return "\n".join(lines)


def generate_markdown_table(comparison, summary, mode, threads, hash_bits):
    """Format human-readable markdown table for PR or logs (compact width for 80-col terminals)."""
    md = []
    md.append(f"### Evaluation Benchmark ({mode.upper()} mode, threads={threads}, hash_bits={hash_bits})\n")
    md.append("| Pos | Baseline | Candidate | Node Δ | Time (s) | Time Δ |")
    md.append("| :--- | :---: | :---: | :---: | :---: | :---: |")

    for name, d in sorted(comparison.items()):
        node_sign = "+" if d["node_delta_pct"] > 0 else ""
        time_sign = "+" if d["time_delta_pct"] > 0 else ""
        md.append(
            f"| {name} | {d['baseline_nodes']:,} | {d['candidate_nodes']:,} | "
            f"{node_sign}{d['node_delta_pct']:.2f}% | "
            f"{d['baseline_time']:.1f} → {d['candidate_time']:.1f} | "
            f"{time_sign}{d['time_delta_pct']:.2f}% |"
        )

    tot_node_sign = "+" if summary["total_node_delta_pct"] > 0 else ""
    tot_time_sign = "+" if summary["total_time_delta_pct"] > 0 else ""
    md.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
    md.append(
        f"| TOTAL | {summary['total_baseline_nodes']:,} | {summary['total_candidate_nodes']:,} | "
        f"{tot_node_sign}{summary['total_node_delta_pct']:.2f}% | "
        f"{summary['total_baseline_time']:.1f} → {summary['total_candidate_time']:.1f} | "
        f"{tot_time_sign}{summary['total_time_delta_pct']:.2f}% |"
    )
    return "\n".join(md)


def determine_verdict(mode, test_passed, all_correct, summary):
    """
    Automated decision engine for agents:
    - REJECT_CORRECTNESS: make test failed or any FFO score/move mismatch.
    - REJECT_REGRESSION: deterministic node counts grew by more than +0.5%.
    - NEEDS_FULL: screen mode passed with notable node reduction (< -0.5%); needs full 19-position verification.
    - ACCEPT: full mode passed with notable node reduction (< -0.5%) and no correctness issues.
    - NEUTRAL: node counts within [-0.5%, +0.5%].
    """
    if not test_passed or not all_correct:
        return "REJECT_CORRECTNESS", "Correctness check failed (test suite or FFO score mismatch)."

    if summary is None:
        return "ACCEPT_NO_BASELINE", "All correctness checks passed (no baseline comparison provided)."

    node_delta = summary["total_node_delta_pct"]

    if node_delta > 0.5:
        return (
            "REJECT_REGRESSION",
            f"Deterministic node count regressed by {node_delta:+.2f}% (> +0.5% tolerance)."
        )

    if node_delta < -0.5:
        if mode == "screen":
            return (
                "NEEDS_FULL",
                f"Screening showed promising node reduction ({node_delta:+.2f}%). Proceed to --mode full."
            )
        else:
            return (
                "ACCEPT",
                f"Full suite confirmed node reduction of {node_delta:+.2f}% with correct evaluations."
            )

    return (
        "NEUTRAL",
        f"Node counts remained virtually unchanged ({node_delta:+.2f}% within [-0.5%, +0.5%])."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Automated Evaluation & Benchmarking Harness for Zebra Optimization Agents."
    )
    parser.add_argument(
        "--mode",
        choices=["screen", "full"],
        default="screen",
        help="Evaluation mode: 'screen' (~15-20s, FFO #45 & #50) or 'full' (all 19 positions)."
    )
    parser.add_argument(
        "--threads",
        default="1",
        help="Search threads: 'auto' (os.cpu_count()) or integer (default: 1 for deterministic benchmarking)."
    )
    parser.add_argument(
        "--hash-bits",
        type=int,
        default=22,
        help="Transposition table bits (default: 22 / 64 MB, portable size)."
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip 'make test' unit verification step."
    )
    parser.add_argument(
        "--baseline",
        type=str,
        default=None,
        help="Path to baseline JSON file for comparison."
    )
    parser.add_argument(
        "--save-baseline",
        type=str,
        default=None,
        help="Save evaluation results to specified JSON file as a new baseline."
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json", "both"],
        default="text",
        help="Output format: 'text' (default, clean terminal table), 'markdown', 'json', or 'both'."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print extra debug output during evaluation."
    )
    parser.add_argument(
        "--progress",
        choices=["compact", "dots", "none"],
        default="compact",
        help="Progress display mode: 'compact' (default, 1 line per position), 'dots', or 'none'."
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress real-time progress output (equivalent to --progress none)."
    )

    args = parser.parse_args()

    # Determine root directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)

    threads = get_default_threads() if args.threads == "auto" else int(args.threads)
    progress = "none" if args.quiet else args.progress

    # 1. Verification of unit tests
    test_passed = True
    test_output = ""
    if not args.skip_tests:
        if progress != "none":
            sys.stderr.write("Running unit test suite ('make test')...\n")
            sys.stderr.flush()
        test_start = time.time()
        test_passed, test_output = run_test_suite(repo_root)
        test_elapsed = time.time() - test_start
        if not test_passed:
            sys.stderr.write(f"Unit tests failed ({test_elapsed:.1f}s):\n{test_output[-500:]}\n")
            sys.stderr.flush()
        elif progress != "none":
            sys.stderr.write(f"Unit tests PASSED ({test_elapsed:.1f}s)\n")
            sys.stderr.flush()

    # 2. Select positions
    if args.mode == "screen":
        target_positions = [p for p in FFO_POSITIONS if p[0] in SCREENING_NAMES]
    else:
        target_positions = FFO_POSITIONS

    # 3. Handle baseline loading before evaluation so live deltas can be shown
    baseline_data = None
    baseline_path = args.baseline
    if baseline_path is None:
        std_path = os.path.join(script_dir, "baselines", f"master_{args.mode}_t{threads}_h{args.hash_bits}.json")
        if os.path.exists(std_path):
            baseline_path = std_path

    if baseline_path and os.path.exists(baseline_path):
        try:
            with open(baseline_path, "r") as f:
                baseline_data = json.load(f)
        except Exception as e:
            if args.verbose:
                sys.stderr.write(f"Warning: Failed to load baseline from {baseline_path}: {e}\n")

    baseline_results = baseline_data.get("results") if (baseline_data and "results" in baseline_data) else None

    # 4. Evaluate target positions with live progress
    candidate_results, all_correct = evaluate_suite(
        repo_root, target_positions, threads, args.hash_bits,
        verbose=args.verbose, baseline_results=baseline_results, progress=progress
    )

    comparison = None
    summary = None
    if baseline_data and "results" in baseline_data:
        comparison, summary = compare_with_baseline(candidate_results, baseline_data["results"])

    # 5. Determine automated verdict
    verdict, reason = determine_verdict(args.mode, test_passed, all_correct, summary)

    # 6. Save baseline if requested
    if args.save_baseline:
        os.makedirs(os.path.dirname(os.path.abspath(args.save_baseline)), exist_ok=True)
        payload = {
            "mode": args.mode,
            "threads": threads,
            "hash_bits": args.hash_bits,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "results": candidate_results
        }
        with open(args.save_baseline, "w") as f:
            json.dump(payload, f, indent=2)
        if args.verbose:
            sys.stderr.write(f"Baseline saved to {args.save_baseline}\n")

    # 7. Format Output
    output_obj = {
        "verdict": verdict,
        "reason": reason,
        "tests_passed": test_passed,
        "all_correct": all_correct,
        "mode": args.mode,
        "threads": threads,
        "hash_bits": args.hash_bits,
        "summary": summary,
        "comparison": comparison,
        "results": candidate_results
    }

    if comparison and summary:
        if args.format == "text":
            print(generate_text_table(comparison, summary, args.mode, threads, args.hash_bits))
            print()
            print(f"Verdict: {verdict} — {reason}")
        elif args.format in ("markdown", "both"):
            markdown_str = generate_markdown_table(comparison, summary, args.mode, threads, args.hash_bits)
            print(markdown_str)
            print()
            print(f"**Verdict:** `{verdict}` — {reason}")
    else:
        if args.format in ("markdown", "both"):
            print(f"**Verdict:** `{verdict}` — {reason}")
        else:
            print(f"Verdict: {verdict} — {reason}")

    if args.format in ("json", "both"):
        if args.format == "both":
            print("\n--- JSON Output ---")
        print(json.dumps(output_obj, indent=2))

    # Exit code: 0 for ACCEPT / NEEDS_FULL / NEUTRAL / ACCEPT_NO_BASELINE; 1 for REJECT_*
    if verdict.startswith("REJECT"):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
