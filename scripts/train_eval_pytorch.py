#!/usr/bin/env python3
"""train_eval_pytorch.py - Modern PyTorch-based evaluation pattern trainer for Zebra.

Replaces legacy conjugate-gradient / MSE tuning with:
- Standard PyTorch (nn.Embedding, AdamW)
- Texel Win-Probability Sigmoid Loss (focuses updates on close, contested positions)
- Base Coefficient Anchor Regularization (preserves quality on rare patterns)
- Direct export into coeffs2.bin format via coeffs_tool.py
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset

# Add parent scripts dir to import coeffs_tool
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from coeffs_tool import PATTERN_SPECS, POW3, CoeffsFile, _MIRROR_MAPS, init_mirror_maps

# Board pattern definitions matching src/patterns.c lines 435-480
# Square coordinates: 10 * row + col (row 1..8, col 1..8)
EVAL_PATTERN_DEFS = [
    # afile2x (4 patterns, len 10)
    ("afile2x", 10, [72, 22, 81, 71, 61, 51, 41, 31, 21, 11]),
    ("afile2x", 10, [77, 27, 88, 78, 68, 58, 48, 38, 28, 18]),
    ("afile2x", 10, [27, 22, 18, 17, 16, 15, 14, 13, 12, 11]),
    ("afile2x", 10, [77, 72, 88, 87, 86, 85, 84, 83, 82, 81]),
    # bfile (4 patterns, len 8)
    ("bfile", 8, [82, 72, 62, 52, 42, 32, 22, 12]),
    ("bfile", 8, [87, 77, 67, 57, 47, 37, 27, 17]),
    ("bfile", 8, [28, 27, 26, 25, 24, 23, 22, 21]),
    ("bfile", 8, [78, 77, 76, 75, 74, 73, 72, 71]),
    # cfile (4 patterns, len 8)
    ("cfile", 8, [83, 73, 63, 53, 43, 33, 23, 13]),
    ("cfile", 8, [86, 76, 66, 56, 46, 36, 26, 16]),
    ("cfile", 8, [38, 37, 36, 35, 34, 33, 32, 31]),
    ("cfile", 8, [68, 67, 66, 65, 64, 63, 62, 61]),
    # dfile (4 patterns, len 8)
    ("dfile", 8, [84, 74, 64, 54, 44, 34, 24, 14]),
    ("dfile", 8, [85, 75, 65, 55, 45, 35, 25, 15]),
    ("dfile", 8, [48, 47, 46, 45, 44, 43, 42, 41]),
    ("dfile", 8, [58, 57, 56, 55, 54, 53, 52, 51]),
    # diag8 (2 patterns, len 8)
    ("diag8", 8, [88, 77, 66, 55, 44, 33, 22, 11]),
    ("diag8", 8, [81, 72, 63, 54, 45, 36, 27, 18]),
    # diag7 (4 patterns, len 7)
    ("diag7", 7, [78, 67, 56, 45, 34, 23, 12]),
    ("diag7", 7, [87, 76, 65, 54, 43, 32, 21]),
    ("diag7", 7, [71, 62, 53, 44, 35, 26, 17]),
    ("diag7", 7, [82, 73, 64, 55, 46, 37, 28]),
    # diag6 (4 patterns, len 6)
    ("diag6", 6, [68, 57, 46, 35, 24, 13]),
    ("diag6", 6, [86, 75, 64, 53, 42, 31]),
    ("diag6", 6, [61, 52, 43, 34, 25, 16]),
    ("diag6", 6, [83, 74, 65, 56, 47, 38]),
    # diag5 (4 patterns, len 5)
    ("diag5", 5, [58, 47, 36, 25, 14]),
    ("diag5", 5, [85, 74, 63, 52, 41]),
    ("diag5", 5, [51, 42, 33, 24, 15]),
    ("diag5", 5, [84, 75, 66, 57, 48]),
    # diag4 (4 patterns, len 4)
    ("diag4", 4, [48, 37, 26, 15]),
    ("diag4", 4, [84, 73, 62, 51]),
    ("diag4", 4, [41, 32, 23, 14]),
    ("diag4", 4, [85, 76, 67, 58]),
    # corner33 (4 patterns, len 9)
    ("corner33", 9, [33, 32, 31, 23, 22, 21, 13, 12, 11]),
    ("corner33", 9, [63, 62, 61, 73, 72, 71, 83, 82, 81]),
    ("corner33", 9, [36, 37, 38, 26, 27, 28, 16, 17, 18]),
    ("corner33", 9, [66, 67, 68, 76, 77, 78, 86, 87, 88]),
    # corner52 (8 patterns, len 10)
    ("corner52", 10, [25, 24, 23, 22, 21, 15, 14, 13, 12, 11]),
    ("corner52", 10, [75, 74, 73, 72, 71, 85, 84, 83, 82, 81]),
    ("corner52", 10, [24, 25, 26, 27, 28, 14, 15, 16, 17, 18]),
    ("corner52", 10, [74, 75, 76, 77, 78, 84, 85, 86, 87, 88]),
    ("corner52", 10, [52, 42, 32, 22, 12, 51, 41, 31, 21, 11]),
    ("corner52", 10, [57, 47, 37, 27, 17, 58, 48, 38, 28, 18]),
    ("corner52", 10, [42, 52, 62, 72, 82, 41, 51, 61, 71, 81]),
    ("corner52", 10, [47, 57, 67, 77, 87, 48, 58, 68, 78, 88]),
]

# Convert squares from 10*row+col to 0-indexed (row, col)
CONVERTED_PATTERNS = []
for name, length, sqs in EVAL_PATTERN_DEFS:
    coords = [((s // 10) - 1, (s % 10) - 1) for s in sqs]
    CONVERTED_PATTERNS.append((name, length, coords))

PATTERN_NAME_TO_SPEC = {name: (count, mirror) for name, count, mirror in PATTERN_SPECS}


def extract_features_from_board(board: List[List[int]], side_to_move: int) -> List[int]:
    """Extract canonical pattern indices for all 46 patterns from an 8x8 board.
    Board values: 0=Empty, 1=Black, 2=White.
    Trit values for pattern: BLACKSQ=0, EMPTY=1, WHITESQ=2.
    If White to move, colors are inverted: (2 - trit).
    """
    init_mirror_maps()
    indices = []
    is_white = (side_to_move == 2)

    for p_idx, (name, length, coords) in enumerate(CONVERTED_PATTERNS):
        raw_idx = 0
        for r, c in coords:
            val = board[r][c]
            # Map board value (0=Empty, 1=Black, 2=White) to trit
            if val == 0:
                trit = 1  # EMPTY
            elif val == 1:
                trit = 0  # BLACK
            else:
                trit = 2  # WHITE

            if is_white:
                trit = 2 - trit  # Color inversion for white perspective

            raw_idx = raw_idx * 3 + trit

        count, mirror_name = PATTERN_NAME_TO_SPEC[name]
        mirror_map = _MIRROR_MAPS[mirror_name]
        if mirror_map is not None:
            canonical_idx = mirror_map[raw_idx]
        else:
            canonical_idx = raw_idx
        indices.append(canonical_idx)

    return indices


class PositionDataset(Dataset):
    def __init__(self, data_file: Path, target_stage: int, stage_window: int = 4):
        self.indices_list = []
        self.scores = []
        self.parities = []

        print(f"Loading positions from {data_file} for stage {target_stage} (window ±{stage_window})...")
        with open(data_file, "r") as f:
            for line in f:
                if len(line) < 36:
                    continue
                parts = line[34:].strip().split()
                if len(parts) < 2:
                    continue
                stg = int(parts[0])
                score = int(parts[1])
                side_char = line[33]
                side_to_move = 1 if side_char == '*' else 2

                # Stage filter
                if abs(stg - target_stage) > stage_window:
                    continue

                # Parse board bitmasks (32 chars)
                board = [[0] * 8 for _ in range(8)]
                for r in range(8):
                    b_hi = ord(line[4 * r]) - 32
                    b_lo = ord(line[4 * r + 1]) - 32
                    w_hi = ord(line[4 * r + 2]) - 32
                    w_lo = ord(line[4 * r + 3]) - 32
                    b_mask = (b_hi << 4) | b_lo
                    w_mask = (w_hi << 4) | w_lo
                    for c in range(8):
                        if b_mask & (1 << c):
                            board[r][c] = 1
                        elif w_mask & (1 << c):
                            board[r][c] = 2

                feat_indices = extract_features_from_board(board, side_to_move)
                # Score is from side-to-move's perspective
                target_score = score if side_to_move == 1 else -score

                self.indices_list.append(feat_indices)
                self.scores.append(float(target_score))
                self.parities.append(1.0 if (stg % 2 == 1) else 0.0)

        print(f"Loaded {len(self.scores)} matching positions.")

    def __len__(self):
        return len(self.scores)

    def __getitem__(self, idx):
        return (
            torch.tensor(self.indices_list[idx], dtype=torch.long),
            torch.tensor(self.parities[idx], dtype=torch.float32),
            torch.tensor(self.scores[idx], dtype=torch.float32),
        )


class StageEvalModel(nn.Module):
    def __init__(self, base_stage_dict: dict, device: torch.device):
        super().__init__()
        self.device = device
        # Base weights are stored in coeffs_tool internal units (val * 2048)
        # In internal units, 512 units = 1 disc, so val / 512 = discs
        self.constant = nn.Parameter(torch.tensor(base_stage_dict["constant"] / 512.0, dtype=torch.float32))
        self.parity = nn.Parameter(torch.tensor(base_stage_dict["parity"] / 512.0, dtype=torch.float32))

        self.tables = nn.ModuleDict()
        self.base_weights = {}

        for name, count, _ in PATTERN_SPECS:
            emb = nn.Embedding(count, 1)
            init_vals = torch.tensor([x / 512.0 for x in base_stage_dict[name]], dtype=torch.float32).unsqueeze(1)
            emb.weight.data.copy_(init_vals)
            self.tables[name] = emb
            self.base_weights[name] = init_vals.clone().to(device)

        # Mapping from pattern index 0..45 to (table_name)
        self.pattern_map = [name for name, _, _ in CONVERTED_PATTERNS]

    def forward(self, indices: torch.Tensor, parity: torch.Tensor) -> torch.Tensor:
        # indices: (batch_size, 46)
        total = self.constant + self.parity * parity
        for p_idx in range(46):
            table_name = self.pattern_map[p_idx]
            p_indices = indices[:, p_idx]
            total = total + self.tables[table_name](p_indices).squeeze(1)
        return total

    def anchor_loss(self) -> torch.Tensor:
        loss = 0.0
        for name in self.tables:
            loss = loss + torch.sum((self.tables[name].weight - self.base_weights[name]) ** 2)
        return loss

    def export_weights(self) -> dict:
        """Export weights scaled back to coeffs_tool format (scaled by 2048)."""
        d = {}
        d["constant"] = int(round(self.constant.item() * 512.0))
        d["parity"] = int(round(self.parity.item() * 512.0))
        for name, count, _ in PATTERN_SPECS:
            weights = self.tables[name].weight.data.cpu().squeeze(1).numpy()
            d[name] = [int(round(float(v) * 512.0)) for v in weights]
        return d


def train_stage(
    stage_idx: int,
    stage_val: int,
    model: StageEvalModel,
    dataset: PositionDataset,
    device: torch.device,
    epochs: int = 10,
    batch_size: int = 512,
    lr: float = 1e-3,
    anchor_lambda: float = 1e-4,
    alpha: float = 0.15,
    beta: float = 0.15,
) -> StageEvalModel:
    if len(dataset) == 0:
        print(f"Skipping stage {stage_val}: no training positions.")
        return model

    model = model.to(device)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=False)
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    mse_loss = nn.MSELoss()

    print(f"\n--- Training Stage {stage_val} (index {stage_idx}) on {len(dataset)} samples ---")
    start_time = time.time()

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        total_batches = 0

        for batch_indices, batch_parity, batch_scores in loader:
            batch_indices = batch_indices.to(device)
            batch_parity = batch_parity.to(device)
            batch_scores = batch_scores.to(device)

            optimizer.zero_grad()
            preds = model(batch_indices, batch_parity)

            # Texel win probability sigmoid transformation
            pred_p = torch.sigmoid(alpha * preds)
            target_p = torch.sigmoid(beta * batch_scores)

            loss = mse_loss(pred_p, target_p)
            if anchor_lambda > 0:
                loss = loss + anchor_lambda * model.anchor_loss()

            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            total_batches += 1

        scheduler.step()
        avg_loss = total_loss / max(1, total_batches)
        print(f"Epoch {epoch:2d}/{epochs:2d} | Loss: {avg_loss:.6f} | Elapsed: {time.time() - start_time:.1f}s")

    return model


def main():
    parser = argparse.ArgumentParser(description="PyTorch training for Zebra evaluation pattern weights.")
    parser.add_argument("--positions", "-p", type=Path, required=True, help="Position dataset (tune8dbs format)")
    parser.add_argument("--base-coeffs", type=Path, default=Path("data/coeffs2.bin"), help="Base coeffs2.bin")
    parser.add_argument("--out", "-o", type=Path, default=Path("data/coeffs2_candidate.bin"), help="Output coeffs2.bin")
    parser.add_argument("--stages", type=int, nargs="+", default=[8, 9, 10], help="Stage indices to train (0-10)")
    parser.add_argument("--epochs", "-e", type=int, default=5, help="Epochs per stage")
    parser.add_argument("--batch-size", "-b", type=int, default=512, help="Batch size")
    parser.add_argument("--lr", type=float, default=2e-3, help="Learning rate")
    parser.add_argument("--anchor", type=float, default=1e-5, help="Anchor regularization weight")
    parser.add_argument("--device", type=str, default="auto", help="Device (cpu, mps, cuda, auto)")
    args = parser.parse_args()

    if args.device == "auto":
        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")
    else:
        device = torch.device(args.device)

    print(f"Using compute device: {device}")

    # Load base coefficients
    cf = CoeffsFile()
    cf.read_binary(args.base_coeffs)
    print(f"Loaded base coefficients from {args.base_coeffs} ({len(cf.stages)} stages: {cf.stages})")

    # Train each requested stage
    for stg_idx in args.stages:
        if stg_idx >= len(cf.stages):
            print(f"Warning: stage index {stg_idx} out of range, skipping")
            continue
        stg_val = cf.stages[stg_idx]
        dataset = PositionDataset(args.positions, target_stage=stg_val, stage_window=4)
        if len(dataset) == 0:
            continue

        model = StageEvalModel(cf.stage_data[stg_val], device)
        trained_model = train_stage(
            stg_idx, stg_val, model, dataset, device,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            anchor_lambda=args.anchor,
        )
        cf.stage_data[stg_val] = trained_model.export_weights()

    # Package into candidate coeffs2.bin
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cf.write_binary(args.out)
    print(f"\nSuccessfully trained and saved new coefficients to {args.out}")


if __name__ == "__main__":
    main()
