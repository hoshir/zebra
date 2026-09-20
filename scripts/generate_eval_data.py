#!/usr/bin/env python3
"""generate_eval_data.py - Clean-room self-play dataset generator for Zebra evaluation tuning.

Generates self-play games via Zebra engine with opening randomization,
and outputs position databases in the exact format required by `tune8dbs`:
- 32-character board bitmasks offset by ' '
- side to move indicator ('*' for Black, 'O' for White)
- stage (disc count)
- score (final disc difference: Black - White)
"""

import argparse
import concurrent.futures
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

# Directions for Othello flips: (drow, dcol)
DIRECTIONS = [
    (-1, -1), (-1, 0), (-1, 1),
    ( 0, -1),          ( 0, 1),
    ( 1, -1), ( 1, 0), ( 1, 1),
]

BLACK = 1
WHITE = 2
EMPTY = 0


class OthelloBoard:
    def __init__(self):
        self.board = [[EMPTY] * 8 for _ in range(8)]
        # Standard initial position
        # d4=W, e4=B, d5=B, e5=W
        # 0-indexed: row 3 col 3 is d4, row 3 col 4 is e4, row 4 col 3 is d5, row 4 col 4 is e5
        self.board[3][3] = WHITE
        self.board[3][4] = BLACK
        self.board[4][3] = BLACK
        self.board[4][4] = WHITE
        self.side_to_move = BLACK
        self.disc_count = 4

    def copy(self):
        b = OthelloBoard()
        b.board = [row[:] for row in self.board]
        b.side_to_move = self.side_to_move
        b.disc_count = self.disc_count
        return b

    def get_flips(self, r: int, c: int, color: int) -> List[Tuple[int, int]]:
        if self.board[r][c] != EMPTY:
            return []
        opp = WHITE if color == BLACK else BLACK
        all_flips = []
        for dr, dc in DIRECTIONS:
            flips = []
            nr, nc = r + dr, c + dc
            while 0 <= nr < 8 and 0 <= nc < 8 and self.board[nr][nc] == opp:
                flips.append((nr, nc))
                nr += dr
                nc += dc
            if 0 <= nr < 8 and 0 <= nc < 8 and self.board[nr][nc] == color and flips:
                all_flips.extend(flips)
        return all_flips

    def legal_moves(self, color: int) -> List[Tuple[int, int]]:
        moves = []
        for r in range(8):
            for c in range(8):
                if self.get_flips(r, c, color):
                    moves.append((r, c))
        return moves

    def make_move(self, r: int, c: int) -> bool:
        flips = self.get_flips(r, c, self.side_to_move)
        if not flips:
            return False
        self.board[r][c] = self.side_to_move
        for fr, fc in flips:
            self.board[fr][fc] = self.side_to_move
        self.disc_count += 1
        opp = WHITE if self.side_to_move == BLACK else BLACK

        # Next player turn (or pass if no legal moves)
        if self.legal_moves(opp):
            self.side_to_move = opp
        elif not self.legal_moves(self.side_to_move):
            # Game over
            self.side_to_move = EMPTY
        return True

    def count_discs(self) -> Tuple[int, int]:
        black_cnt = sum(row.count(BLACK) for row in self.board)
        white_cnt = sum(row.count(WHITE) for row in self.board)
        return black_cnt, white_cnt

    def to_tune8dbs_line(self, score_diff: int) -> str:
        """Format position as tune8dbs input line:
        32 chars board bitmasks, ' ', side ('*' or 'O'), ' ', stage, ' ', score
        """
        chars = []
        for r in range(8):
            b_mask = 0
            w_mask = 0
            for c in range(8):
                if self.board[r][c] == BLACK:
                    b_mask |= (1 << c)
                elif self.board[r][c] == WHITE:
                    w_mask |= (1 << c)
            # 2 chars for black mask, 2 chars for white mask
            b_hi = (b_mask >> 4) & 0x0F
            b_lo = b_mask & 0x0F
            w_hi = (w_mask >> 4) & 0x0F
            w_lo = w_mask & 0x0F
            chars.extend([chr(b_hi + 32), chr(b_lo + 32), chr(w_hi + 32), chr(w_lo + 32)])

        side_char = '*' if self.side_to_move == BLACK else 'O'
        return f"{''.join(chars)} {side_char} {self.disc_count} {score_diff}\n"


def parse_move_coord(move_str: str) -> Tuple[int, int]:
    col = ord(move_str[0].lower()) - ord('a')
    row = int(move_str[1]) - 1
    return row, col


def replay_game_to_positions(move_str: str, final_diff: int) -> List[str]:
    """Replays move string (e.g. 'f5d6c3...') and generates tune8dbs position lines."""
    board = OthelloBoard()
    lines = []
    # Moves are pairs of characters
    i = 0
    while i + 1 < len(move_str):
        m_str = move_str[i:i+2]
        i += 2
        r, c = parse_move_coord(m_str)

        # Before making the move, record current position if midgame
        if 4 <= board.disc_count <= 60 and board.side_to_move != EMPTY:
            lines.append(board.to_tune8dbs_line(final_diff))

        success = board.make_move(r, c)
        if not success:
            break

    return lines


def run_zebra_selfplay_batch(
    zebra_bin: Path,
    coeffs_dir: Path,
    openings: List[str],
    games_per_batch: int,
    depth: int = 2,
    random_prefix_len: int = 4,
) -> List[str]:
    """Run batch of selfplay games with Zebra CLI and return tune8dbs position lines."""
    positions = []
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".log", delete=False) as log_f:
        log_path = Path(log_f.name)

    try:
        # Pick opening or random moves
        for _ in range(games_per_batch):
            # Select random opening from list
            if openings and random.random() < 0.7:
                seq = random.choice(openings)
            else:
                # Generate random legal moves prefix
                b = OthelloBoard()
                seq_moves = []
                for _ in range(random_prefix_len):
                    legals = b.legal_moves(b.side_to_move)
                    if not legals:
                        break
                    mr, mc = random.choice(legals)
                    b.make_move(mr, mc)
                    seq_moves.append(f"{chr(ord('a') + mc)}{mr + 1}")
                seq = "".join(seq_moves)

            cmd = [
                str(zebra_bin),
                "-seq", seq,
                "-l", str(depth), str(depth),
                "-repeat", "1",
                "-e", "0",
                "-log", str(log_path),
            ]
            subprocess.run(cmd, cwd=coeffs_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

        # Parse generated log
        if log_path.exists():
            with open(log_path, "r") as f:
                lines = f.readlines()
            # Log format:
            # # date
            # #     B - W
            # moves...
            curr_score = None
            for line in lines:
                line = line.strip()
                if line.startswith("#"):
                    parts = line[1:].strip().split("-")
                    if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                        b_score = int(parts[0].strip())
                        w_score = int(parts[1].strip())
                        curr_score = b_score - w_score
                elif line and not line.startswith("#") and curr_score is not None:
                    moves = line
                    positions.extend(replay_game_to_positions(moves, curr_score))
                    curr_score = None
    finally:
        if log_path.exists():
            log_path.unlink()

    return positions


def load_openings(openings_path: Path) -> List[str]:
    if not openings_path.exists():
        return []
    openings = []
    with open(openings_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.isdigit():
                continue
            parts = line.split()
            if parts and len(parts[0]) >= 4 and len(parts[0]) % 2 == 0:
                openings.append(parts[0])
    return openings


def main():
    parser = argparse.ArgumentParser(description="Generate clean-room training positions via Zebra self-play.")
    parser.add_argument("--out", "-o", type=Path, required=True, help="Output position database file")
    parser.add_argument("--num-games", "-n", type=int, default=500, help="Number of self-play games to play")
    parser.add_argument("--depth", "-d", type=int, default=2, help="Self-play search depth (default: 2)")
    parser.add_argument("--workers", "-w", type=int, default=max(1, os.cpu_count() or 4), help="Parallel worker threads")
    parser.add_argument("--openings", type=Path, default=Path("data/openings.txt"), help="Path to openings.txt")
    parser.add_argument("--zebra-bin", type=Path, default=Path("build/bin/zebra"), help="Path to zebra binary")
    parser.add_argument("--coeffs-dir", type=Path, default=Path("build/bin"), help="Working dir where coeffs2.bin exists")
    args = parser.parse_args()

    openings = load_openings(args.openings)
    print(f"Loaded {len(openings)} openings from {args.openings}")
    print(f"Generating {args.num_games} self-play games using {args.workers} workers at depth {args.depth}...")

    games_per_worker = max(1, args.num_games // args.workers)
    all_positions = []

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = []
        for _ in range(args.workers):
            f = executor.submit(
                run_zebra_selfplay_batch,
                args.zebra_bin.resolve(),
                args.coeffs_dir.resolve(),
                openings,
                games_per_worker,
                args.depth,
            )
            futures.append(f)

        done_cnt = 0
        for f in concurrent.futures.as_completed(futures):
            batch_pos = f.result()
            all_positions.extend(batch_pos)
            done_cnt += games_per_worker
            print(f"Progress: ~{done_cnt}/{args.num_games} games ({len(all_positions)} positions)")

    # Write positions to output file
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.writelines(all_positions)

    print(f"Successfully wrote {len(all_positions)} positions to {args.out}")


if __name__ == "__main__":
    main()
