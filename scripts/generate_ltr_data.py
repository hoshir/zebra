#!/usr/bin/env python3
"""generate_ltr_data.py - Extract Learning-to-Rank (LTR) decision samples from WTHOR .wtb databases.

Replays games from WTHOR database (e.g., WTH_2024.wtb), collects decision points
in the endgame stage (disc count 40 to 58), extracts evaluation feature indices
and parities for all legal move children, identifies the game-played move as best_idx,
and saves the dataset using torch.save to data/ltr_endgame_2024.pt.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import torch

# Add parent scripts dir to path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from parse_wthor import parse_wthor_file, WthorGame
from generate_eval_data import OthelloBoard, BLACK, WHITE, EMPTY
from train_eval_pytorch import extract_features_from_board


def disc_count_to_stage(disc_count: int) -> int:
    """Map disc count to stage [7, 8, 9, 10] matching Zebra's stage centers:
    Stage 7: ~44 discs (40..45)
    Stage 8: ~48 discs (46..49)
    Stage 9: ~52 discs (50..53)
    Stage 10: ~56 discs (54..58+)
    
    Zebra stage center guidelines / boundaries:
    - Stage 7: disc count 40..43 (approx center 44)
    - Stage 8: disc count 44..47 (approx center 48)
    - Stage 9: disc count 48..51 (approx center 52)
    - Stage 10: disc count 52..55 / 56..58 (approx center 56)
    
    Let's use exact nearest stage center matching:
    Centers: Stage 7 = 44, Stage 8 = 48, Stage 9 = 52, Stage 10 = 56.
    Distance to center:
    - disc <= 45: stage 7 (center 44)
    - 46 <= disc <= 49: stage 8 (center 48)
    - 50 <= disc <= 53: stage 9 (center 52)
    - disc >= 54: stage 10 (center 56)
    """
    if disc_count <= 45:
        return 7
    elif disc_count <= 49:
        return 8
    elif disc_count <= 53:
        return 9
    else:
        return 10


def generate_ltr_dataset(wthor_files: List[Path], max_games: Optional[int] = None, max_theo_error: int = 0) -> List[dict]:
    samples = []
    games_parsed = 0
    games_skipped_theo = 0

    for wthor_file in wthor_files:
        print(f"Parsing WTHOR file: {wthor_file}")
        for game in parse_wthor_file(wthor_file):
            if max_games is not None and games_parsed >= max_games:
                break
            
            # Filter by theoretical error if specified
            if abs(game.real_score - game.theo_score) > max_theo_error:
                games_skipped_theo += 1
                continue

            games_parsed += 1

            board = OthelloBoard()

            for r, c in game.moves:
                if board.side_to_move == EMPTY:
                    break

                disc_count = board.disc_count
                if 40 <= disc_count <= 58:
                    legal_moves = board.legal_moves(board.side_to_move)
                    if len(legal_moves) >= 2:
                        # Check if (r, c) is legal
                        if (r, c) in legal_moves:
                            best_idx = legal_moves.index((r, c))
                            
                            child_features_list = []
                            child_parities_list = []
                            
                            for m_r, m_c in legal_moves:
                                child = board.copy()
                                success = child.make_move(m_r, m_c)
                                if not success:
                                    continue
                                
                                opp_side = WHITE if board.side_to_move == BLACK else BLACK
                                child_indices = extract_features_from_board(child.board, opp_side)
                                child_parity = (child.disc_count) % 2
                                
                                child_features_list.append(child_indices)
                                child_parities_list.append(child_parity)
                            
                            if len(child_features_list) == len(legal_moves):
                                stage = disc_count_to_stage(disc_count)
                                
                                # For Stage 7, compute soft target weights and opponent mobility (proof size)
                                target_weights = None
                                if stage == 7:
                                    opp_mobilities = []
                                    for m_r, m_c in legal_moves:
                                        child = board.copy()
                                        child.make_move(m_r, m_c)
                                        opp_side = WHITE if child.side_to_move == BLACK else BLACK
                                        opp_moves = child.legal_moves(opp_side)
                                        opp_mobilities.append(len(opp_moves))
                                    
                                    inv_mob = [1.0 / (m + 1.0) for m in opp_mobilities]
                                    sum_inv = sum(inv_mob)
                                    if sum_inv > 0:
                                        target_weights = [w / sum_inv for w in inv_mob]
                                    else:
                                        target_weights = [1.0 / len(legal_moves)] * len(legal_moves)
                                
                                sample = {
                                    "stage": stage,
                                    "side": board.side_to_move,
                                    "disc_count": disc_count,
                                    "best_idx": best_idx,
                                    "child_features": child_features_list,
                                    "child_parities": child_parities_list,
                                    "target_weights": target_weights,
                                }
                                samples.append(sample)

                success = board.make_move(r, c)
                if not success:
                    break

            if games_parsed > 0 and games_parsed % 1000 == 0:
                print(f"Processed {games_parsed} valid games, collected {len(samples)} LTR samples so far...")

    print(f"Finished parsing. Parsed games: {games_parsed}, Skipped (theo error > {max_theo_error}): {games_skipped_theo}. Total LTR samples: {len(samples)}")
    return samples


def main():
    parser = argparse.ArgumentParser(description="Extract LTR decision samples from WTHOR .wtb database.")
    parser.add_argument("--wthor", "--wthor-file", dest="wthor_files", type=str, default="data/wthor/WTH_2024.wtb", help="Path or glob pattern to WTHOR .wtb file(s)")
    parser.add_argument("--out", type=Path, default=Path("data/ltr_endgame_2024.pt"), help="Output PyTorch dataset path")
    parser.add_argument("--max-games", type=int, default=None, help="Maximum games to parse")
    parser.add_argument("--stages", type=str, default="7,8,9,10", help="Comma-separated list of stages to include (e.g. 7,8)")
    parser.add_argument("--max-theo-error", type=int, default=0, help="Maximum absolute difference between real_score and theo_score (default: 0)")

    args = parser.parse_args()

    import glob
    resolved_files = []
    for pattern in args.wthor_files.split(","):
        pattern = pattern.strip()
        matches = glob.glob(pattern)
        if matches:
            resolved_files.extend([Path(m) for m in sorted(matches)])
        elif Path(pattern).exists():
            resolved_files.append(Path(pattern))

    if not resolved_files:
        print(f"Error: No WTHOR files found matching {args.wthor_files}.", file=sys.stderr)
        sys.exit(1)

    target_stages = {int(s.strip()) for s in args.stages.split(",") if s.strip()}
    samples = generate_ltr_dataset(resolved_files, args.max_games, args.max_theo_error)

    # Filter by stages
    if target_stages:
        samples = [s for s in samples if s["stage"] in target_stages]

    # Count per stage
    stage_counts = {}
    for s in samples:
        stage = s["stage"]
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    print("\n--- LTR Dataset Summary ---")
    print(f"Total samples: {len(samples)}")
    for stg in sorted(stage_counts.keys()):
        print(f"  Stage {stg}: {stage_counts[stg]} samples")

    # Ensure output dir exists
    args.out.parent.mkdir(parents=True, exist_ok=True)

    print(f"Saving dataset to {args.out} using torch.save...")
    torch.save(samples, args.out)
    print("Done!")


if __name__ == "__main__":
    main()