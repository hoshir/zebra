#!/usr/bin/env python3
"""tune_eval.py - Automated evaluation coefficient tuning pipeline for Zebra.

Orchestrates:
1. Exporting base coeffs from data/coeffs2.bin into tune8dbs directory
2. (Optional) Generating clean-room self-play positions via generate_eval_data.py
3. Running `tune8dbs` on specified stages (e.g. stages 7..10 for endgame, or all stages)
4. Importing the updated weights and packaging them into a candidate coeffs2.bin
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_COEFFS = REPO_ROOT / "data" / "coeffs2.bin"
DEFAULT_TUNE8DBS = REPO_ROOT / "build" / "bin" / "tune8dbs"


def run_cmd(cmd: List[str], cwd: Optional[Path] = None):
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description="Run Zebra evaluation pattern tuning pipeline.")
    parser.add_argument("--positions", "-p", type=Path, help="Path to existing position database file")
    parser.add_argument("--generate-games", "-g", type=int, default=0, help="Generate N clean-room self-play games")
    parser.add_argument("--depth", "-d", type=int, default=2, help="Self-play depth (default: 2)")
    parser.add_argument("--workers", "-w", type=int, default=max(1, os.cpu_count() or 4), help="Worker threads")
    parser.add_argument("--base-coeffs", type=Path, default=DEFAULT_COEFFS, help="Base coeffs2.bin")
    parser.add_argument("--tune8dbs-bin", type=Path, default=DEFAULT_TUNE8DBS, help="Path to tune8dbs binary")
    parser.add_argument("--work-dir", type=Path, default=Path("/tmp/zebra_tune_work"), help="Work directory")
    parser.add_argument("--stages", type=int, nargs="+", default=[7, 8, 9, 10], help="Stage indices to tune (0-10)")
    parser.add_argument("--iterations", "-i", type=int, default=20, help="Iterations per stage in tune8dbs")
    parser.add_argument("--max-positions", type=int, default=100000, help="Max positions per stage")
    parser.add_argument("--max-diff", type=int, default=40, help="Max score diff (filters extreme blowouts)")
    parser.add_argument("--out", "-o", type=Path, default=Path("data/coeffs2_candidate.bin"), help="Output candidate coeffs2.bin")
    args = parser.parse_args()

    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Export base coeffs
    coeffs_tool = SCRIPT_DIR / "coeffs_tool.py"
    print(f"--- Step 1: Exporting base coeffs from {args.base_coeffs} to {work_dir} ---")
    run_cmd([sys.executable, str(coeffs_tool), "export-tune8dbs", str(args.base_coeffs), str(work_dir)])

    # 2. Prepare positions
    pos_file = args.positions
    if args.generate_games > 0 or pos_file is None:
        if pos_file is None:
            pos_file = work_dir / "generated_positions.txt"
        games = args.generate_games if args.generate_games > 0 else 500
        print(f"--- Step 2: Generating {games} clean-room selfplay games to {pos_file} ---")
        gen_script = SCRIPT_DIR / "generate_eval_data.py"
        run_cmd([
            sys.executable, str(gen_script),
            "--out", str(pos_file),
            "--num-games", str(games),
            "--depth", str(args.depth),
            "--workers", str(args.workers),
        ])
    else:
        pos_file = pos_file.resolve()

    print(f"Using position database: {pos_file}")

    # 3. Run tune8dbs for each requested stage
    option_file = work_dir / "option.txt"
    tune8dbs_bin = args.tune8dbs_bin.resolve()

    for stg_idx in args.stages:
        print(f"\n--- Step 3: Tuning stage index {stg_idx} ({args.iterations} iterations) ---")
        cmd = [
            str(tune8dbs_bin),
            str(pos_file),
            str(option_file),
            str(stg_idx),
            str(args.max_positions),
            str(args.iterations),
            str(args.max_diff),
        ]
        run_cmd(cmd, cwd=work_dir)

    # 4. Import back into candidate coeffs2.bin
    out_path = args.out.resolve()
    print(f"\n--- Step 4: Packaging updated weights into {out_path} ---")
    run_cmd([sys.executable, str(coeffs_tool), "import-tune8dbs", str(work_dir), str(out_path)])
    print(f"Tuning pipeline complete! Output candidate: {out_path}")


if __name__ == "__main__":
    main()
