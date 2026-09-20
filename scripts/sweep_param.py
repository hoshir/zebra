#!/usr/bin/env python3
"""
scripts/sweep_param.py - Automated Multi-Value Parameter Sweeper Harness for Zebra.

Sweeps search constants, depth schedules, and heuristic thresholds across candidate values.
Runs sequential builds and benchmarks, isolates intermediate output, guarantees file restoration,
and produces a consolidated Pareto ranking table with optimal parameter recommendations.

Primary Unit of Account: Deterministic 1-thread node counts across FFO endgame positions.
Secondary Unit of Account: Multi-threaded scaling (NPS & wall-clock time).
"""

import argparse
import atexit
import json
import os
import re
import signal
import subprocess
import sys
import time


class SafeFileRestorer:
    """Guarantees target file restoration via signal traps, atexit, and try...finally."""

    def __init__(self, filepath):
        self.filepath = os.path.abspath(filepath)
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Target file not found: {self.filepath}")
        with open(self.filepath, "r", encoding="utf-8") as f:
            self.original_content = f.read()
        self.current_content = self.original_content
        self.restored = False
        self._register_handlers()

    def _register_handlers(self):
        atexit.register(self.restore)

        def _signal_handler(signum, frame):
            self.restore()
            sys.exit(128 + signum)

        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            try:
                signal.signal(sig, _signal_handler)
            except (ValueError, AttributeError):
                pass

    def apply(self, new_content):
        self.current_content = new_content
        self.restored = False
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

    def restore(self):
        if not self.restored and self.current_content != self.original_content:
            try:
                with open(self.filepath, "w", encoding="utf-8") as f:
                    f.write(self.original_content)
                self.current_content = self.original_content
                self.restored = True
            except OSError:
                pass

    def commit(self, final_content):
        """Keep the final content permanently without reverting on exit."""
        self.original_content = final_content
        self.current_content = final_content
        self.restored = True


def replace_parameter_value(content, param_name=None, new_val=None, pattern=None):
    """
    Substitutes a parameter value in file content.
    Returns (modified_content, original_val_str).
    """
    if pattern:
        regex = re.compile(pattern, re.MULTILINE)
        match = regex.search(content)
        if not match:
            raise ValueError(f"Custom pattern '{pattern}' did not match anything in file.")
        
        # If regex has groups (e.g. prefix, val, suffix)
        if regex.groups >= 3:
            orig_val = match.group(2)
            new_content = regex.sub(r"\g<1>" + str(new_val) + r"\g<3>", content, count=1)
        elif regex.groups >= 1:
            orig_val = match.group(1)
            # Replace the first group's span
            span = match.span(1)
            new_content = content[:span[0]] + str(new_val) + content[span[1]:]
        else:
            orig_val = match.group(0)
            new_content = regex.sub(str(new_val), content, count=1)
        return new_content, orig_val

    if not param_name:
        raise ValueError("Either --param or --pattern must be specified.")

    # 1. Try C/C++ macro definition: #define PARAM <val>
    macro_pattern = re.compile(
        r'^(#\s*define\s+' + re.escape(param_name) + r'\s+)([\w\d_.-]+)(.*)$',
        re.MULTILINE
    )
    matches = list(macro_pattern.finditer(content))
    if len(matches) == 1:
        orig_val = matches[0].group(2)
        new_content = macro_pattern.sub(r'\g<1>' + str(new_val) + r'\g<3>', content, count=1)
        return new_content, orig_val

    # 2. Try C/C++ variable assignment: [const/static] [type] PARAM = <val>;
    var_pattern = re.compile(
        r'(\b' + re.escape(param_name) + r'\s*=\s*)([\w\d_.-]+)(\s*;)',
        re.MULTILINE
    )
    matches = list(var_pattern.finditer(content))
    if len(matches) == 1:
        orig_val = matches[0].group(2)
        new_content = var_pattern.sub(r'\g<1>' + str(new_val) + r'\g<3>', content, count=1)
        return new_content, orig_val

    if len(matches) > 1:
        raise ValueError(f"Parameter '{param_name}' matched {len(matches)} occurrences in file. Use --pattern for precise replacement.")

    raise ValueError(f"Parameter '{param_name}' not found as #define or variable assignment in file.")


def parse_candidate_values(args):
    """Parse candidate values from --values or --range arguments."""
    values = []
    if args.values:
        for item in args.values:
            for part in str(item).split(","):
                part = part.strip()
                if part:
                    values.append(part)
    elif args.range:
        r = args.range
        if len(r) == 2:
            start, end = r
            step = 1 if start <= end else -1
        elif len(r) == 3:
            start, end, step = r
        else:
            raise ValueError("--range requires 2 or 3 arguments: start end [step]")

        # Check if integer or float range
        if isinstance(start, int) and isinstance(end, int) and isinstance(step, int):
            if step > 0:
                cur = start
                while cur <= end:
                    values.append(str(cur))
                    cur += step
            else:
                cur = start
                while cur >= end:
                    values.append(str(cur))
                    cur += step
        else:
            cur = float(start)
            end_f = float(end)
            step_f = float(step)
            if step_f > 0:
                while cur <= end_f + 1e-9:
                    values.append(f"{cur:g}")
                    cur += step_f
            else:
                while cur >= end_f - 1e-9:
                    values.append(f"{cur:g}")
                    cur += step_f

    if not values:
        raise ValueError("No candidate values specified. Use --values or --range.")

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for v in values:
        if v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


def run_candidate_evaluation(repo_root, eval_script, mode, threads, hash_bits, skip_tests):
    """
    Executes eval_candidate.py in a subprocess and parses JSON output.
    Returns: dict with evaluation results or error details.
    """
    cmd = [
        sys.executable,
        eval_script,
        "--mode", mode,
        "--threads", str(threads),
        "--hash-bits", str(hash_bits),
        "--format", "json",
        "--quiet",
    ]
    if skip_tests:
        cmd.append("--skip-tests")

    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if not stdout:
            return {
                "success": False,
                "status": "BUILD_ERROR",
                "error": f"Process produced no output. Exit code: {proc.returncode}. Stderr: {stderr[:300]}",
                "total_nodes": None,
                "total_time": None,
                "raw": None
            }

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return {
                "success": False,
                "status": "PARSE_ERROR",
                "error": f"Failed to parse JSON output: {stdout[:300]}",
                "total_nodes": None,
                "total_time": None,
                "raw": None
            }

        tests_passed = data.get("tests_passed", False)
        all_correct = data.get("all_correct", False)
        verdict = data.get("verdict", "UNKNOWN")

        # Extract total nodes and time
        totals = data.get("totals") or {}
        tot_nodes = totals.get("total_nodes")
        tot_time = totals.get("total_time")

        if tot_nodes is None and "results" in data and isinstance(data["results"], dict):
            tot_nodes = sum(r.get("nodes", 0) for r in data["results"].values() if isinstance(r, dict) and "nodes" in r)
        if tot_time is None and "results" in data and isinstance(data["results"], dict):
            tot_time = round(sum(r.get("time_sec", 0.0) for r in data["results"].values() if isinstance(r, dict) and "time_sec" in r), 2)

        if not tests_passed:
            status = "TEST_FAILED"
            success = False
        elif not all_correct:
            status = "MISMATCH"
            success = False
        else:
            status = "PASS"
            success = True

        return {
            "success": success,
            "status": status,
            "verdict": verdict,
            "reason": data.get("reason"),
            "total_nodes": tot_nodes,
            "total_time": tot_time,
            "raw": data,
            "error": data.get("reason") if not success else None
        }

    except Exception as e:
        return {
            "success": False,
            "status": "EXEC_ERROR",
            "error": str(e),
            "total_nodes": None,
            "total_time": None,
            "raw": None
        }


def format_text_table(ranked_candidates, baseline_val, param_name, target_file, mode, threads, hash_bits):
    """Formats clean plain-text summary and Pareto ranking table."""
    lines = []
    lines.append(f"Parameter Sweep Summary: {param_name} in {target_file}")
    lines.append(f"Settings: mode={mode}, threads={threads}, hash_bits={hash_bits}")
    
    b_cand = next((c for c in ranked_candidates if str(c["value"]) == str(baseline_val)), None)
    if b_cand and b_cand.get("total_nodes"):
        lines.append(f"Baseline: {baseline_val} ({b_cand['total_nodes']:,} nodes, {b_cand['total_time']:.1f}s)")
    elif baseline_val:
        lines.append(f"Baseline: {baseline_val}")
    lines.append("")

    header = f"  {'Rank':<5} {'Value':<10} {'Nodes':>14} {'Node Δ':>9}   {'Time':>14}   {'Status':<16}"
    sep = "  " + "-" * (len(header) - 2)
    lines.append(header)
    lines.append(sep)

    for c in ranked_candidates:
        rank_str = str(c["rank"]) if c["rank"] is not None else "-"
        val_str = str(c["value"])
        if c.get("total_nodes") is not None:
            nodes_str = f"{c['total_nodes']:,}"
            if c.get("is_baseline"):
                node_delta_str = "baseline"
            elif c.get("node_delta_pct") is not None:
                sign = "+" if c["node_delta_pct"] > 0 else ""
                node_delta_str = f"{sign}{c['node_delta_pct']:.2f}%"
            else:
                node_delta_str = "-"
        else:
            nodes_str = "-"
            node_delta_str = "-"

        if c.get("total_time") is not None:
            t_str = f"{c['total_time']:.1f}s"
            if c.get("is_baseline"):
                t_delta_str = "baseline"
            elif c.get("time_delta_pct") is not None:
                sign = "+" if c["time_delta_pct"] > 0 else ""
                t_delta_str = f"({sign}{c['time_delta_pct']:.1f}%)"
            else:
                t_delta_str = ""
            time_col = f"{t_str:>6} {t_delta_str:>7}"
        else:
            time_col = f"{'-':>14}"

        status_str = c["display_status"]
        lines.append(
            f"  {rank_str:<5} {val_str:<10} {nodes_str:>14} {node_delta_str:>9}   {time_col}   {status_str:<16}"
        )

    lines.append(sep)

    # Recommendation
    best_cand = next((c for c in ranked_candidates if c["rank"] == 1), None)
    if best_cand:
        if best_cand.get("is_baseline"):
            lines.append(f"Recommendation: Current baseline ({baseline_val}) is optimal. No change needed.")
        elif best_cand.get("node_delta_pct") is not None and best_cand["node_delta_pct"] < 0:
            sign = "" if best_cand["node_delta_pct"] >= 0 else ""
            lines.append(
                f"Recommendation: Optimal parameter value is '{best_cand['value']}' "
                f"({best_cand['node_delta_pct']:.2f}% nodes vs baseline {baseline_val})."
            )
        else:
            lines.append(f"Recommendation: Optimal parameter value is '{best_cand['value']}'.")
    else:
        lines.append("Recommendation: No candidate passed verification.")

    return "\n".join(lines)


def format_markdown_table(ranked_candidates, baseline_val, param_name, target_file, mode, threads, hash_bits):
    """Formats markdown table for documentation and PR descriptions."""
    md = []
    md.append(f"### Parameter Sweep Summary: `{param_name}` (`{target_file}`)\n")
    md.append(f"- **Mode:** `{mode}` | **Threads:** {threads} | **Hash Bits:** {hash_bits}")
    
    b_cand = next((c for c in ranked_candidates if str(c["value"]) == str(baseline_val)), None)
    if b_cand and b_cand.get("total_nodes"):
        md.append(f"- **Baseline Value:** `{baseline_val}` ({b_cand['total_nodes']:,} nodes, {b_cand['total_time']:.1f}s)\n")
    elif baseline_val:
        md.append(f"- **Baseline Value:** `{baseline_val}`\n")

    md.append("| Rank | Value | Total Nodes | Node Δ | Time (s) | Time Δ | Status |")
    md.append("| :---: | :---: | :---: | :---: | :---: | :---: | :--- |")

    for c in ranked_candidates:
        rank_str = str(c["rank"]) if c["rank"] is not None else "-"
        is_best = (c["rank"] == 1)
        val_str = f"**{c['value']}**" if is_best else f"`{c['value']}`"

        if c.get("total_nodes") is not None:
            nodes_str = f"{c['total_nodes']:,}"
            if c.get("is_baseline"):
                node_delta_str = "baseline"
            elif c.get("node_delta_pct") is not None:
                sign = "+" if c["node_delta_pct"] > 0 else ""
                node_delta_str = f"{sign}{c['node_delta_pct']:.2f}%"
                if is_best and c["node_delta_pct"] < 0:
                    node_delta_str = f"**{node_delta_str}**"
            else:
                node_delta_str = "-"
        else:
            nodes_str = "-"
            node_delta_str = "-"

        if c.get("total_time") is not None:
            time_sec_str = f"{c['total_time']:.1f}"
            if c.get("is_baseline"):
                time_delta_str = "baseline"
            elif c.get("time_delta_pct") is not None:
                sign = "+" if c["time_delta_pct"] > 0 else ""
                time_delta_str = f"{sign}{c['time_delta_pct']:.1f}%"
            else:
                time_delta_str = "-"
        else:
            time_sec_str = "-"
            time_delta_str = "-"

        status_str = c["display_status"]
        md.append(f"| {rank_str} | {val_str} | {nodes_str} | {node_delta_str} | {time_sec_str} | {time_delta_str} | {status_str} |")

    md.append("")
    best_cand = next((c for c in ranked_candidates if c["rank"] == 1), None)
    if best_cand:
        if best_cand.get("is_baseline"):
            md.append(f"**Recommendation:** Current baseline (`{baseline_val}`) is optimal. No change needed.")
        elif best_cand.get("node_delta_pct") is not None and best_cand["node_delta_pct"] < 0:
            md.append(
                f"**Recommendation:** Optimal candidate value is `{best_cand['value']}` "
                f"({best_cand['node_delta_pct']:.2f}% nodes vs baseline `{baseline_val}`)."
            )
        else:
            md.append(f"**Recommendation:** Optimal candidate value is `{best_cand['value']}`.")
    else:
        md.append("**Recommendation:** No candidate passed verification.")

    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(
        description="Automated Parameter Sweeper Harness for Zebra Search Optimization."
    )
    parser.add_argument(
        "--file", "-f",
        required=True,
        help="Target source file to modify (e.g. 'src/end.c')."
    )
    parser.add_argument(
        "--param", "-p",
        help="Parameter / macro / variable name to sweep (e.g. 'DEPTH_THREE_SEARCH')."
    )
    parser.add_argument(
        "--pattern",
        help="Custom regex pattern for parameter replacement (overrides --param)."
    )
    parser.add_argument(
        "--values", "-v",
        nargs="+",
        help="Candidate values to sweep (comma- or space-separated list)."
    )
    parser.add_argument(
        "--range", "-r",
        nargs="+",
        type=float,
        help="Range of values: start end [step] (e.g. --range 16 20 1)."
    )
    parser.add_argument(
        "--mode",
        choices=["screen", "full"],
        default="screen",
        help="Evaluation mode: 'screen' (default, ~15-20s, FFO #45 & #50) or 'full' (all 19 positions)."
    )
    parser.add_argument(
        "--threads", "-t",
        default="1",
        help="Search threads (default: 1 for deterministic node counts)."
    )
    parser.add_argument(
        "--hash-bits",
        type=int,
        default=22,
        help="Transposition table size in bits (default: 22 / 64 MB)."
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip 'make -s test' during evaluations to accelerate sweeps."
    )
    parser.add_argument(
        "--baseline-value",
        help="Explicit baseline value to compare deltas against (defaults to original value in file)."
    )
    parser.add_argument(
        "--apply-best",
        action="store_true",
        help="Permanently modify target file with best performing candidate value on completion."
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json"],
        default="text",
        help="Output format: 'text' (default), 'markdown', or 'json'."
    )
    parser.add_argument(
        "--save-json",
        help="Save consolidated sweep results to specified JSON file."
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress real-time per-candidate progress lines."
    )

    args = parser.parse_args()

    # Convert range floats to int if whole numbers
    if args.range:
        int_compatible = all(x.is_integer() for x in args.range)
        if int_compatible:
            args.range = [int(x) for x in args.range]

    # Resolve repo root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    eval_script = os.path.join(script_dir, "eval_candidate.py")

    target_file = os.path.abspath(args.file if os.path.isabs(args.file) else os.path.join(repo_root, args.file))
    rel_target_file = os.path.relpath(target_file, repo_root)

    # Initialize file restorer
    restorer = SafeFileRestorer(target_file)

    try:
        # Determine candidate values
        candidate_values = parse_candidate_values(args)

        # Detect original value
        _, original_val = replace_parameter_value(
            restorer.original_content,
            param_name=args.param,
            new_val=candidate_values[0],
            pattern=args.pattern
        )

        baseline_val = args.baseline_value if args.baseline_value is not None else str(original_val).strip()

        # If baseline value not in candidates, include it at the beginning so delta can be computed
        all_eval_values = list(candidate_values)
        if baseline_val not in all_eval_values:
            all_eval_values.insert(0, baseline_val)

        total_runs = len(all_eval_values)
        param_label = args.param or args.pattern

        if not args.quiet:
            sys.stderr.write(
                f"Starting sweep for '{param_label}' in {rel_target_file} "
                f"({total_runs} candidates, mode={args.mode}, threads={args.threads}, hash_bits={args.hash_bits})\n"
            )
            sys.stderr.flush()

        results_by_val = {}
        best_content_to_apply = None

        # Sweep execution loop
        for idx, val in enumerate(all_eval_values, 1):
            # Substitute parameter
            new_content, _ = replace_parameter_value(
                restorer.original_content,
                param_name=args.param,
                new_val=val,
                pattern=args.pattern
            )
            restorer.apply(new_content)

            if not args.quiet:
                is_base_tag = " (baseline)" if str(val) == str(baseline_val) else ""
                sys.stderr.write(f"[{idx:2d}/{total_runs:2d}] Evaluating {param_label} = {val}{is_base_tag} ...\n")
                sys.stderr.flush()

            start_t = time.time()
            eval_res = run_candidate_evaluation(
                repo_root=repo_root,
                eval_script=eval_script,
                mode=args.mode,
                threads=args.threads,
                hash_bits=args.hash_bits,
                skip_tests=args.skip_tests
            )
            elapsed_t = time.time() - start_t

            eval_res["value"] = val
            eval_res["is_baseline"] = (str(val) == str(baseline_val))
            eval_res["modified_content"] = new_content
            results_by_val[str(val)] = eval_res

            if not args.quiet:
                if eval_res["success"]:
                    nodes_m = eval_res["total_nodes"] / 1e6 if eval_res["total_nodes"] else 0.0
                    sys.stderr.write(
                        f"[{idx:2d}/{total_runs:2d}] {param_label} = {val}: "
                        f"{eval_res['status']} | {nodes_m:.1f}M nodes, {eval_res['total_time']:.2f}s ({elapsed_t:.1f}s total)\n"
                    )
                else:
                    sys.stderr.write(
                        f"[{idx:2d}/{total_runs:2d}] {param_label} = {val}: "
                        f"FAILED ({eval_res['status']}: {eval_res.get('error')})\n"
                    )
                sys.stderr.flush()

        # Compute deltas relative to baseline
        baseline_res = results_by_val.get(str(baseline_val))
        b_nodes = baseline_res.get("total_nodes") if (baseline_res and baseline_res.get("success")) else None
        b_time = baseline_res.get("total_time") if (baseline_res and baseline_res.get("success")) else None

        for val_str, res in results_by_val.items():
            if res.get("success") and b_nodes and res.get("total_nodes"):
                res["node_delta_pct"] = round(((res["total_nodes"] - b_nodes) / b_nodes) * 100.0, 2)
            else:
                res["node_delta_pct"] = None

            if res.get("success") and b_time and res.get("total_time"):
                res["time_delta_pct"] = round(((res["total_time"] - b_time) / b_time) * 100.0, 2)
            else:
                res["time_delta_pct"] = None

        # Pareto Ranking
        valid_candidates = [r for r in results_by_val.values() if r.get("success")]
        invalid_candidates = [r for r in results_by_val.values() if not r.get("success")]

        # Sort valid candidates primarily by total_nodes (asc), secondarily by total_time (asc)
        valid_candidates.sort(key=lambda r: (r.get("total_nodes", float("inf")), r.get("total_time", float("inf"))))

        ranked_list = []
        for rank, cand in enumerate(valid_candidates, 1):
            cand["rank"] = rank
            if rank == 1:
                if cand.get("is_baseline"):
                    cand["display_status"] = "PASS (BASELINE / OPTIMAL)"
                else:
                    cand["display_status"] = "PASS (OPTIMAL)"
                best_content_to_apply = cand["modified_content"]
            elif cand.get("is_baseline"):
                cand["display_status"] = "PASS (BASELINE)"
            else:
                cand["display_status"] = "PASS"
            ranked_list.append(cand)

        for cand in invalid_candidates:
            cand["rank"] = None
            cand["display_status"] = cand.get("status", "FAILED")
            ranked_list.append(cand)

        # Output Generation
        output_data = {
            "parameter": param_label,
            "target_file": rel_target_file,
            "baseline_value": baseline_val,
            "mode": args.mode,
            "threads": args.threads,
            "hash_bits": args.hash_bits,
            "skip_tests": args.skip_tests,
            "candidates": [
                {
                    "rank": c.get("rank"),
                    "value": c["value"],
                    "is_baseline": c.get("is_baseline", False),
                    "status": c.get("status"),
                    "display_status": c.get("display_status"),
                    "total_nodes": c.get("total_nodes"),
                    "node_delta_pct": c.get("node_delta_pct"),
                    "total_time": c.get("total_time"),
                    "time_delta_pct": c.get("time_delta_pct"),
                    "error": c.get("error")
                }
                for c in ranked_list
            ],
            "optimal_value": valid_candidates[0]["value"] if valid_candidates else None
        }

        if args.save_json:
            os.makedirs(os.path.dirname(os.path.abspath(args.save_json)), exist_ok=True)
            with open(args.save_json, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2)

        if args.format == "json":
            print(json.dumps(output_data, indent=2))
        elif args.format == "markdown":
            print(format_markdown_table(
                ranked_list, baseline_val, param_label, rel_target_file,
                args.mode, args.threads, args.hash_bits
            ))
        else:  # text
            print(format_text_table(
                ranked_list, baseline_val, param_label, rel_target_file,
                args.mode, args.threads, args.hash_bits
            ))

        # Handle --apply-best
        if args.apply_best and best_content_to_apply:
            restorer.commit(best_content_to_apply)
            if not args.quiet:
                sys.stderr.write(f"\nApplied optimal parameter value ({valid_candidates[0]['value']}) to {rel_target_file}\n")

    finally:
        # Guarantee restoration unless explicitly committed by --apply-best
        restorer.restore()


if __name__ == "__main__":
    main()
