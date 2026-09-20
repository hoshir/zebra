#!/usr/bin/env python3
"""parse_wthor.py - Parser for WTHOR Othello tournament databases (.wtb binary files).

Extracts game records, validates and replays move sequences on an Othello board,
and exports positions in the `tune8dbs` text format for evaluation training.

WTHOR Binary Specification:
- File Header (16 bytes):
    - Creation date: 4 bytes (century, year, month, day)
    - N1 (number of games): 4 bytes uint32 (little-endian)
    - N2 (number of player/tournament records): 2 bytes uint16 (little-endian)
    - Game year: 2 bytes uint16 (little-endian)
    - P1 (board size): 1 byte (0 or 8 for 8x8)
    - P2 (game type): 1 byte (0 for games)
    - P3 (depth/version): 1 byte
    - Reserved: 1 byte
- Game Record (68 bytes for 8x8 games):
    - Tournament ID: 2 bytes uint16 (little-endian)
    - Black Player ID: 2 bytes uint16 (little-endian)
    - White Player ID: 2 bytes uint16 (little-endian)
    - Real Score: 1 byte uint8 (Black's final disc count, 0-64)
    - Theoretical Score: 1 byte uint8 (Black's score at move 38)
    - Move List: 60 bytes (each byte: col + 10 * row, 1-indexed; 0 = no more moves)
"""

import argparse
import os
import struct
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

# Try to import OthelloBoard from scripts.generate_eval_data, with fallback
try:
    from scripts.generate_eval_data import OthelloBoard, BLACK, WHITE, EMPTY
except ImportError:
    # When running directly from within scripts/ or repo root
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from generate_eval_data import OthelloBoard, BLACK, WHITE, EMPTY


WTHOR_BASE_URL = "https://ffothello.org/wthor/base/"
WTHOR_ZIP_URL = "https://ffothello.org/wthor/base_zip/"


class WthorGame:
    """Represents a single parsed WTHOR game record."""

    def __init__(
        self,
        tournament_id: int,
        black_id: int,
        white_id: int,
        real_score: int,
        theo_score: int,
        moves: List[Tuple[int, int]],
    ):
        self.tournament_id = tournament_id
        self.black_id = black_id
        self.white_id = white_id
        self.real_score = real_score
        self.theo_score = theo_score
        self.moves = moves  # List of (row, col), 0-indexed

    @property
    def score_diff(self) -> int:
        """Score difference from Black's perspective: Black - White."""
        return 2 * self.real_score - 64


def parse_wthor_file(file_path: Path) -> Iterator[WthorGame]:
    """Parse a .wtb binary file and yield WthorGame instances."""
    with open(file_path, "rb") as f:
        header = f.read(16)
        if len(header) < 16:
            raise ValueError(f"File {file_path} is too small to contain a WTHOR header.")

        # Unpack header
        _, n_games, _, _, board_size, game_type, _, _ = struct.unpack("<4s I H H B B B B", header)

        if board_size not in (0, 8):
            raise ValueError(f"Unsupported board size {board_size} (only 8x8 Othello is supported).")

        # Read records
        RECORD_SIZE = 68
        for _ in range(n_games):
            record = f.read(RECORD_SIZE)
            if len(record) < RECORD_SIZE:
                break

            tour_id, black_id, white_id, real_score, theo_score, move_bytes = struct.unpack(
                "<H H H B B 60s", record
            )

            moves = []
            for b in move_bytes:
                if b == 0:
                    break
                row = (b // 10) - 1
                col = (b % 10) - 1
                if 0 <= row < 8 and 0 <= col < 8:
                    moves.append((row, col))
                else:
                    # Invalid move encoding encountered
                    break

            yield WthorGame(
                tournament_id=tour_id,
                black_id=black_id,
                white_id=white_id,
                real_score=real_score,
                theo_score=theo_score,
                moves=moves,
            )


def replay_game_to_positions(
    game: WthorGame,
    min_disc_count: int = 16,
    max_disc_count: int = 58,
) -> List[str]:
    """Replay moves on an OthelloBoard and serialize intermediate states to tune8dbs lines."""
    board = OthelloBoard()
    lines = []
    score_diff = game.score_diff

    for r, c in game.moves:
        if board.side_to_move == EMPTY:
            break

        # Save position if within targeted stage window
        if min_disc_count <= board.disc_count <= max_disc_count:
            lines.append(board.to_tune8dbs_line(score_diff))

        # Apply move
        success = board.make_move(r, c)
        if not success:
            # Illegal move encountered in record; halt replay for this game
            break

    return lines


import ssl


def _open_url(url: str):
    """Open URL handling potential macOS SSL certificate issues."""
    try:
        return urllib.request.urlopen(url)
    except urllib.error.URLError:
        ctx = ssl._create_unverified_context()
        return urllib.request.urlopen(url, context=ctx)


def _download_file(url: str, dest: Path):
    """Download a remote URL to dest path."""
    with _open_url(url) as response, open(dest, "wb") as out_file:
        out_file.write(response.read())


def download_wthor_year(year: int, dest_dir: Path) -> Path:
    """Download WTHOR database for a given year to dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    wtb_file = dest_dir / f"WTH_{year}.wtb"
    if wtb_file.exists():
        print(f"File {wtb_file} already exists, skipping download.")
        return wtb_file

    wtb_url = f"{WTHOR_BASE_URL}WTH_{year}.wtb"
    zip_url = f"{WTHOR_ZIP_URL}WTH_{year}.ZIP"

    # Try downloading .wtb directly first
    try:
        print(f"Downloading {wtb_url} ...")
        _download_file(wtb_url, wtb_file)
        if wtb_file.stat().st_size > 16:
            return wtb_file
    except Exception as e:
        print(f"Direct .wtb download failed ({e}), trying .ZIP archive...")

    # Try downloading .ZIP archive
    zip_file = dest_dir / f"WTH_{year}.ZIP"
    try:
        print(f"Downloading {zip_url} ...")
        _download_file(zip_url, zip_file)
        with zipfile.ZipFile(zip_file, "r") as zf:
            for name in zf.namelist():
                if name.lower().endswith(".wtb"):
                    zf.extract(name, dest_dir)
                    extracted = dest_dir / name
                    if extracted != wtb_file and extracted.exists():
                        extracted.rename(wtb_file)
                    print(f"Extracted {wtb_file} from {zip_file}")
                    return wtb_file
    except Exception as e:
        raise RuntimeError(f"Failed to download WTHOR database for year {year}: {e}")

    return wtb_file


def run_self_test():
    """Run self-test using a synthetic WTHOR .wtb record."""
    print("Running WTHOR parser self-test...")
    # Construct a synthetic 16-byte header for 1 game of 8x8
    header = struct.pack("<4s I H H B B B B", b"\x20\x24\x01\x01", 1, 1, 2024, 8, 0, 22, 0)
    # Construct a valid opening move sequence:
    # 1. c4 (row 4, col 3 -> 43)
    # 2. c3 (row 3, col 3 -> 33)
    # 3. d3 (row 3, col 4 -> 34)
    # 4. c5 (row 5, col 3 -> 53)
    moves = bytearray([43, 33, 34, 53] + [0] * 56)
    # Real score = 34 (Black +4 diff: 34 - 30)
    record = struct.pack("<H H H B B 60s", 101, 1001, 1002, 34, 34, bytes(moves))

    synthetic_wtb = header + record
    test_path = Path("/tmp/test_wthor_synth.wtb")
    test_path.write_bytes(synthetic_wtb)

    games = list(parse_wthor_file(test_path))
    assert len(games) == 1, f"Expected 1 game, got {len(games)}"
    g = games[0]
    assert g.tournament_id == 101
    assert g.black_id == 1001
    assert g.white_id == 1002
    assert g.real_score == 34
    assert g.score_diff == 4
    assert len(g.moves) == 4
    assert g.moves[0] == (3, 2)  # c4 is row 3, col 2 (0-indexed)
    assert g.moves[1] == (2, 2)  # c3 is row 2, col 2
    assert g.moves[2] == (2, 3)  # d3 is row 2, col 3
    assert g.moves[3] == (4, 2)  # c5 is row 4, col 2

    # Replay positions (allowing disc counts from 4 upwards)
    positions = replay_game_to_positions(g, min_disc_count=4, max_disc_count=10)
    assert len(positions) == 4, f"Expected 4 positions, got {len(positions)}"
    for line in positions:
        assert len(line) >= 36
        assert line[32] == " "
        assert line[33] in ("*", "O")

    test_path.unlink(missing_ok=True)
    print("Self-test PASSED successfully!")


def main():
    parser = argparse.ArgumentParser(description="Parse WTHOR tournament database files into tune8dbs format.")
    parser.add_argument("--input", "-i", type=Path, nargs="*", help="Path(s) to .wtb file(s) or directory containing them")
    parser.add_argument("--out", "-o", type=Path, default=Path("data/wthor_positions.txt"), help="Output tune8dbs file")
    parser.add_argument("--download-year", type=int, nargs="*", help="Year(s) to download from FFO WTHOR archive (e.g. 2024)")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/wthor"), help="Directory to cache downloaded .wtb files")
    parser.add_argument("--min-disc-count", type=int, default=16, help="Minimum disc count to sample (default: 16)")
    parser.add_argument("--max-disc-count", type=int, default=58, help="Maximum disc count to sample (default: 58)")
    parser.add_argument("--max-games", type=int, default=None, help="Maximum games to parse")
    parser.add_argument("--test", action="store_true", help="Run internal parser self-test")
    args = parser.parse_args()

    if args.test:
        run_self_test()
        return

    # Collect input files
    wtb_files: List[Path] = []
    if args.download_year:
        for y in args.download_year:
            wtb_files.append(download_wthor_year(y, args.cache_dir))

    if args.input:
        for inp in args.input:
            p = inp.resolve()
            if p.is_dir():
                wtb_files.extend(sorted(p.glob("*.wtb")))
                wtb_files.extend(sorted(p.glob("*.WTB")))
            elif p.is_file():
                wtb_files.append(p)

    if not wtb_files:
        print("No input .wtb files specified. Use --input or --download-year (or --test).")
        sys.exit(1)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    total_games = 0
    total_positions = 0
    inconsistencies = 0

    print(f"Parsing {len(wtb_files)} WTHOR file(s) -> {args.out} ...")
    with open(args.out, "w") as out_f:
        for wtb in wtb_files:
            print(f"Processing {wtb.name} ...")
            try:
                for game in parse_wthor_file(wtb):
                    if args.max_games is not None and total_games >= args.max_games:
                        break

                    pos_lines = replay_game_to_positions(
                        game,
                        min_disc_count=args.min_disc_count,
                        max_disc_count=args.max_disc_count,
                    )
                    if len(pos_lines) < len(game.moves) and len(pos_lines) == 0:
                        inconsistencies += 1

                    for line in pos_lines:
                        out_f.write(line)
                        total_positions += 1

                    total_games += 1
            except Exception as e:
                print(f"Error processing {wtb}: {e}")

            if args.max_games is not None and total_games >= args.max_games:
                break

    print(
        f"\nDone! Extracted {total_positions} positions from {total_games} games "
        f"(skipped/inconsistent: {inconsistencies}) to {args.out}"
    )


if __name__ == "__main__":
    main()
