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
import re
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
    parser.add_argument("--method", choices=["pytorch", "cg"], default="pytorch", help="Tuning method (default: pytorch)")
    parser.add_argument("--positions", "-p", type=Path, help="Path to existing position database file")
    parser.add_argument("--generate-games", "-g", type=int, default=0, help="Generate N clean-room self-play games")
    parser.add_argument("--depth", "-d", type=int, default=2, help="Self-play depth (default: 2)")
    parser.add_argument("--workers", "-w", type=int, default=max(1, os.cpu_count() or 4), help="Worker threads")
    parser.add_argument("--base-coeffs", type=Path, default=DEFAULT_COEFFS, help="Base coeffs2.bin")
    parser.add_argument("--tune8dbs-bin", type=Path, default=DEFAULT_TUNE8DBS, help="Path to tune8dbs binary (for cg method)")
    parser.add_argument("--work-dir", type=Path, default=Path("/tmp/zebra_tune_work"), help="Work directory")
    parser.add_argument("--stages", type=int, nargs="+", default=[8, 9, 10], help="Stage indices to tune (0-10)")
    parser.add_argument("--iterations", "-i", type=int, default=5, help="Epochs or iterations per stage")
    parser.add_argument("--batch-size", "-b", type=int, default=256, help="Batch size for PyTorch training")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate for PyTorch training")
    parser.add_argument("--anchor", type=float, default=1e-5, help="Anchor regularization weight for PyTorch")
    parser.add_argument("--anchor-l1", type=float, default=0.0, help="Anchor L1 regularization weight for PyTorch (Elastic Net, default: 0.0)")
    parser.add_argument("--stage-weight-boost", type=float, default=0.5, help="Boost weight for late-game stages in PyTorch loss (default: 0.5)")
    parser.add_argument("--contested-weight", type=float, default=1.5, help="Boost weight for contested score positions (|score| <= sigma, default: 1.5)")
    parser.add_argument("--contested-sigma", type=float, default=8.0, help="Gaussian sigma for contested score weighting (default: 8.0)")
    parser.add_argument("--wthor", type=str, default=None, help="WTHOR dataset input (file path, dir path, or year(s) like '2024' or '2022,2023,2024')")
    parser.add_argument("--wthor-ratio", type=float, default=0.5, help="WTHOR mixing ratio in hybrid dataset (default: 0.5)")
    parser.add_argument("--wthor-positions", type=Path, default=None, help="Pre-extracted WTHOR positions file")
    parser.add_argument("--wthor-cache-dir", type=Path, default=Path("data/wthor"), help="Cache directory for WTHOR .wtb files and extracted positions (default: data/wthor)")
    parser.add_argument("--max-positions", type=int, default=100000, help="Max positions per stage (for cg)")
    parser.add_argument("--max-diff", type=int, default=40, help="Max score diff (for cg)")
    parser.add_argument("--python-bin", type=Path, default=Path(".venv/bin/python3"), help="Python binary with PyTorch")
    parser.add_argument("--ltr-data", type=Path, default=None, help="Optional LTR dataset path (.pt)")
    parser.add_argument("--ltr-weight", type=float, default=0.20, help="LTR loss weight (default: 0.20)")
    parser.add_argument("--ltr-temp", type=float, default=0.5, help="LTR softmax temperature (default: 0.5)")
    parser.add_argument("--out", "-o", type=Path, default=Path("data/coeffs2_candidate.bin"), help="Output candidate coeffs2.bin")
    args = parser.parse_args()

    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Prepare positions
    pos_file = args.positions
    if args.generate_games > 0 or pos_file is None:
        if pos_file is None:
            pos_file = work_dir / "generated_positions.txt"
        games = args.generate_games if args.generate_games > 0 else 500
        print(f"--- Step 1: Generating {games} clean-room selfplay games to {pos_file} ---")
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

    # Prepare WTHOR human grandmaster positions if requested
    wthor_pos_file = args.wthor_positions
    cache_dir = args.wthor_cache_dir.resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    if args.wthor is not None and wthor_pos_file is None:
        parse_script = SCRIPT_DIR / "parse_wthor.py"
        wthor_arg = args.wthor.strip()

        year_tokens = [p for p in re.split(r'[,\\s]+', wthor_arg) if p.isdigit() and len(p) == 4]
        if year_tokens and len(year_tokens) == len(re.split(r'[,\\s]+', wthor_arg)):
            years = [int(y) for y in year_tokens]
            year_tag = "_".join(str(y) for y in sorted(years)) if len(years) > 1 else str(years[0])
            cached_positions = cache_dir / f"positions_{year_tag}.txt"

            if cached_positions.exists() and cached_positions.stat().st_size > 0:
                print(f"Found cached WTHOR positions for {year_tag} at {cached_positions}, using directly.")
                wthor_pos_file = cached_positions
            else:
                wthor_pos_file = cached_positions
                all_wtb_cached = all((cache_dir / f"WTH_{y}.wtb").exists() and (cache_dir / f"WTH_{y}.wtb").stat().st_size > 16 for y in years)
                if all_wtb_cached:
                    print(f"Found all cached WTHOR binaries for {year_tag}, parsing to {wthor_pos_file} ...")
                    wtb_paths = [str(cache_dir / f"WTH_{y}.wtb") for y in years]
                    run_cmd([
                        sys.executable, str(parse_script),
                        "--input", *wtb_paths,
                        "--out", str(wthor_pos_file),
                    ])
                else:
                    print(f"Downloading WTHOR year(s) {years} to {cache_dir} and parsing to {wthor_pos_file} ...")
                    run_cmd([
                        sys.executable, str(parse_script),
                        "--download-year", *[str(y) for y in years],
                        "--cache-dir", str(cache_dir),
                        "--out", str(wthor_pos_file),
                    ])
        else:
            p = Path(wthor_arg)
            if not p.exists() and (cache_dir / p.name).exists():
                p = cache_dir / p.name

            if p.exists():
                cached_positions = cache_dir / f"positions_{p.stem}.txt"
                if cached_positions.exists() and cached_positions.stat().st_size > 0:
                    print(f"Found cached parsed positions at {cached_positions}, using directly.")
                    wthor_pos_file = cached_positions
                else:
                    wthor_pos_file = cached_positions
                    print(f"Parsing WTHOR database from {p} to {wthor_pos_file} ...")
                    run_cmd([
                        sys.executable, str(parse_script),
                        "--input", str(p),
                        "--out", str(wthor_pos_file),
                    ])
            else:
                print(f"Warning: WTHOR path {p} does not exist and not in {cache_dir}, proceeding without WTHOR data.")
                wthor_pos_file = None

    out_path = args.out.resolve()

    if args.method == "pytorch":
        print(f"\n--- Step 2: Training with PyTorch (AdamW + Texel Sigmoid Loss) ---")
        train_script = SCRIPT_DIR / "train_eval_pytorch.py"
        py_bin = args.python_bin if args.python_bin.exists() else Path(sys.executable)
        cmd = [
            str(py_bin), str(train_script),
            "--positions", str(pos_file),
            "--base-coeffs", str(args.base_coeffs),
            "--out", str(out_path),
            "--stages", *[str(s) for s in args.stages],
            "--epochs", str(args.iterations),
            "--batch-size", str(args.batch_size),
            "--lr", str(args.lr),
            "--anchor", str(args.anchor),
            "--anchor-l1", str(args.anchor_l1),
            "--stage-weight-boost", str(args.stage_weight_boost),
            "--contested-weight", str(args.contested_weight),
            "--contested-sigma", str(args.contested_sigma),
        ]
        if wthor_pos_file and wthor_pos_file.exists():
            cmd.extend([
                "--wthor-positions", str(wthor_pos_file),
                "--wthor-mix-ratio", str(args.wthor_ratio),
            ])
        if hasattr(args, "ltr_data") and args.ltr_data:
            cmd.extend(["--ltr-data", str(args.ltr_data)])
        if hasattr(args, "ltr_weight") and args.ltr_weight is not None:
            cmd.extend(["--ltr-weight", str(args.ltr_weight)])
        if hasattr(args, "ltr_temp") and args.ltr_temp is not None:
            cmd.extend(["--ltr-temp", str(args.ltr_temp)])
        run_cmd(cmd)
    else:
        # Legacy CG via tune8dbs
        coeffs_tool = SCRIPT_DIR / "coeffs_tool.py"
        print(f"--- Step 2: Exporting base coeffs from {args.base_coeffs} to {work_dir} ---")
        run_cmd([sys.executable, str(coeffs_tool), "export-tune8dbs", str(args.base_coeffs), str(work_dir)])

        option_file = work_dir / "option.txt"
        tune8dbs_bin = args.tune8dbs_bin.resolve()

        for stg_idx in args.stages:
            print(f"\n--- Tuning stage index {stg_idx} via tune8dbs ({args.iterations} iterations) ---")
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

        print(f"\n--- Packaging updated weights into {out_path} ---")
        run_cmd([sys.executable, str(coeffs_tool), "import-tune8dbs", str(work_dir), str(out_path)])

    print(f"\nTuning pipeline complete! Output candidate: {out_path}")


if __name__ == "__main__":
    main()
