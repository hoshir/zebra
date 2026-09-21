#!/usr/bin/env python3
"""
scripts/bench_midgame_smp.py - Multi-thread midgame scaling benchmarks for Zebra.
"""

import argparse
import os
import re
import sys
import tempfile
import subprocess
import time

# 4 diverse midgame positions (depth 12 or 14, 40-50 empty squares)
POSITIONS = [
    ("----------XO------XX-----XXXXO----XXXX----OOX--------X---------- O", "Mimura variation II"),
    ("----------XX-----OXXO---OXOXOO--OOXXO---OXXX-------------------- O", "Bat Kling Continuation"),
    ("----------XXO-----XXOO---XXXOO---XXXOO-----OOO----O-O----------- X", "Rotating Flat"),
    ("------------------X-O----OOOO----OOXXX--OXOXXX----O------------- X", "Tiger Stephenson Continuation"),
]

def run_scrzebra(repo_root, positions, threads, midgame_depth, hash_bits=22):
    bin_dir = os.path.join(repo_root, "build", "bin")
    scrzebra_bin = os.path.join(bin_dir, "scrzebra")
    
    # Write positions to a temp input file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".in", delete=False) as in_f:
        temp_in_path = in_f.name
        for pos, _ in positions:
            in_f.write(pos + "\n")
            
    temp_out_path = temp_in_path + ".out"
    
    cmd = [
        scrzebra_bin,
        "-mid", str(midgame_depth),
        "-n", str(threads),
        "-h", str(hash_bits),
        "-e", "0",
        "-script", temp_in_path,
        temp_out_path
    ]
    
    # Run with cwd=bin_dir so coeffs2.bin can be loaded
    start_time = time.perf_counter()
    res = subprocess.run(cmd, cwd=bin_dir, capture_output=True, text=True)
    end_time = time.perf_counter()
    duration = end_time - start_time
    
    # Cleanup temp files
    if os.path.exists(temp_in_path):
        try:
            os.remove(temp_in_path)
        except OSError:
            pass
    if os.path.exists(temp_out_path):
        try:
            os.remove(temp_out_path)
        except OSError:
            pass
        
    if res.returncode != 0:
        raise RuntimeError(f"scrzebra failed with exit code {res.returncode}. stderr: {res.stderr}")
        
    stdout = res.stdout
    
    # Parse total nodes from stdout
    nodes_match = re.search(r"Total nodes:\s+([0-9]+)", stdout)
    if not nodes_match:
        raise RuntimeError(f"Could not parse total nodes from stdout: {stdout}")
    total_nodes = int(nodes_match.group(1))
    
    return {
        "nodes": total_nodes,
        "time": duration,
        "nps": total_nodes / duration if duration > 0 else 0
    }

def main():
    parser = argparse.ArgumentParser(description="Multi-thread midgame scaling benchmarks for Zebra")
    parser.add_argument("--depth", type=int, default=12, choices=[12, 14, 16, 18], help="Midgame depth to run (default: 12)")
    parser.add_argument("--hash-bits", type=int, default=22, help="Hash bits (default: 22)")
    args = parser.parse_args()
    
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    print("==================================================")
    print(" Zebra Midgame Multi-Thread Scaling Benchmark")
    print("==================================================")
    print(f"Loaded {len(POSITIONS)} diverse midgame positions.")
    for idx, (pos, desc) in enumerate(POSITIONS, 1):
        empty_squares = pos.split()[0].count('-')
        print(f"  {idx}. {desc}: {empty_squares} empty squares")
    print()
    
    # Test 1-thread determinism
    print(f"Verifying 1-thread determinism (at depth {args.depth})...")
    run1 = run_scrzebra(repo_root, POSITIONS, threads=1, midgame_depth=args.depth, hash_bits=args.hash_bits)
    run2 = run_scrzebra(repo_root, POSITIONS, threads=1, midgame_depth=args.depth, hash_bits=args.hash_bits)
    
    if run1["nodes"] != run2["nodes"]:
        print(f"ERROR: 1-thread runs are NOT deterministic!")
        print(f"Run 1 nodes: {run1['nodes']}")
        print(f"Run 2 nodes: {run2['nodes']}")
        sys.exit(1)
    
    print(f"SUCCESS: 1-thread determinism verified. Nodes: {run1['nodes']:,}\n")
    
    # Benchmark threads
    thread_counts = [1, 2, 4, 8]
    results = {}
    
    print(f"Running scaling benchmarks (depth {args.depth})...")
    for t in thread_counts:
        print(f"  Running on {t} thread(s)...")
        results[t] = run_scrzebra(repo_root, POSITIONS, threads=t, midgame_depth=args.depth, hash_bits=args.hash_bits)
        print(f"    Completed: Time = {results[t]['time']:.3f}s, Nodes = {results[t]['nodes']:,}, NPS = {results[t]['nps']:,.0f}")
        
    t1_time = results[1]["time"]
    t1_nps = results[1]["nps"]
    
    print(f"\nBenchmark Results (Midgame Depth {args.depth}):")
    print()
    
    # Build Markdown table
    md_table = []
    md_table.append("| Threads | Time (s) | Speedup | Total Nodes | NPS | NPS Scaling |")
    md_table.append("|---------|----------|---------|-------------|-----|-------------|")
    
    for t in thread_counts:
        res = results[t]
        speedup = t1_time / res["time"] if res["time"] > 0 else 0
        nps_scal = res["nps"] / t1_nps if t1_nps > 0 else 0
        
        md_table.append(
            f"| {t} | {res['time']:.3f}s | {speedup:.2f}x | {res['nodes']:,} | {res['nps']:,.0f} | {nps_scal:.2f}x |"
        )
        
    table_str = "\n".join(md_table)
    print(table_str)
    print()
    
if __name__ == "__main__":
    main()
