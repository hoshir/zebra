#!/usr/bin/env python3
"""coeffs_tool.py - Tool to inspect, unpack, and pack Zebra's coeffs2.bin files.

Format specification derived from src/getcoeff.c, src/patterns.c, and src/magic.h:
- Compressed with gzip (zlib)
- 16-bit signed big-endian integers (">h")
- Magic header: EVAL_MAGIC1 (5358), EVAL_MAGIC2 (9793)
- stage_count (short)
- stages: stage_count - 1 shorts (last stage 60 is implicit in engine)
- Per stage:
    constant (short)
    parity (short)
    afile2x  (59049 entries, map_mirror8x2)
    bfile    (6561 entries, map_mirror8)
    cfile    (6561 entries, map_mirror8)
    dfile    (6561 entries, map_mirror8)
    diag8    (6561 entries, map_mirror8)
    diag7    (2187 entries, map_mirror7)
    diag6    (729 entries, map_mirror6)
    diag5    (243 entries, map_mirror5)
    diag4    (81 entries, map_mirror4)
    corner33 (19683 entries, map_mirror33)
    corner52 (59049 entries, no mirror)
Note: Values stored in file are 4 * (internal value in getcoeff.c).
"""

import argparse
import gzip
import json
import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

EVAL_MAGIC1 = 5358
EVAL_MAGIC2 = 9793

POW3 = [3**i for i in range(12)]

# Precomputed mirror maps (canonical index for each pattern index)
_MIRROR_MAPS: Dict[str, Optional[List[int]]] = {}


def build_odometer_patterns(n: int) -> List[List[int]]:
    """Generate all base-3 digit lists of length n in Zebra's odometer order."""
    total = POW3[n]
    row = [0] * n
    res = []
    for _ in range(total):
        res.append(list(row))
        # Odometer step: row[0] is least significant
        j = 0
        while True:
            row[j] += 1
            if row[j] == 3:
                row[j] = 0
                j += 1
                if j >= n:
                    break
            else:
                break
    return res


def init_mirror_maps():
    global _MIRROR_MAPS
    if _MIRROR_MAPS:
        return

    # Linear patterns of length n (3 to 8)
    flip_linear = {}
    for n in range(3, 9):
        patterns = build_odometer_patterns(n)
        mirror_map = [0] * POW3[n]
        flip_list = [0] * POW3[n]
        for i, row in enumerate(patterns):
            # mirror_pattern reverses the trits: row[j] * 3^(n - 1 - j)
            m = sum(row[j] * POW3[n - 1 - j] for j in range(n))
            mirror_map[i] = min(i, m)
            flip_list[i] = m
        _MIRROR_MAPS[f"mirror{n}"] = mirror_map
        flip_linear[n] = flip_list

    # 3x3 pattern: transpose
    patterns33 = build_odometer_patterns(9)
    map33 = [0] * POW3[9]
    for i, row in enumerate(patterns33):
        # row is 3x3 in order:
        # row[0], row[1], row[2]  (row 0)
        # row[3], row[4], row[5]  (row 1)
        # row[6], row[7], row[8]  (row 2)
        # Transposed row:
        # (0,3,6), (1,4,7), (2,5,8)
        m = (
            row[0] * 1
            + row[3] * 3
            + row[6] * 9
            + row[1] * 27
            + row[4] * 81
            + row[7] * 243
            + row[2] * 729
            + row[5] * 2187
            + row[8] * 6561
        )
        map33[i] = min(i, m)
    _MIRROR_MAPS["mirror33"] = map33

    # Edge 2X pattern (afile2x): 59049 entries
    # index = i + 6561 * j + 19683 * k, where i is edge (8 squares), j, k are X-squares
    flip8 = flip_linear[8]
    map8x2 = [0] * 59049
    for i in range(6561):
        for j in range(3):
            for k in range(3):
                idx = i + 6561 * j + 19683 * k
                flipped_idx = flip8[i] + 6561 * k + 19683 * j
                map8x2[idx] = min(idx, flipped_idx)
    _MIRROR_MAPS["mirror8x2"] = map8x2
    _MIRROR_MAPS["none"] = None


PATTERN_SPECS = [
    ("afile2x", 59049, "mirror8x2"),
    ("bfile", 6561, "mirror8"),
    ("cfile", 6561, "mirror8"),
    ("dfile", 6561, "mirror8"),
    ("diag8", 6561, "mirror8"),
    ("diag7", 2187, "mirror7"),
    ("diag6", 729, "mirror6"),
    ("diag5", 243, "mirror5"),
    ("diag4", 81, "mirror4"),
    ("corner33", 19683, "mirror33"),
    ("corner52", 59049, "none"),
]


class CoeffsFile:
    def __init__(self):
        init_mirror_maps()
        self.stages: List[int] = []
        self.stage_data: Dict[int, dict] = {}

    def read_binary(self, filepath: Path):
        with gzip.open(filepath, "rb") as f:
            raw = f.read()

        pos = 0

        def get_word():
            nonlocal pos
            val = struct.unpack_from(">h", raw, pos)[0]
            pos += 2
            return val

        magic1 = get_word()
        magic2 = get_word()
        if magic1 != EVAL_MAGIC1 or magic2 != EVAL_MAGIC2:
            raise ValueError(f"Invalid magic: {magic1}, {magic2} (expected {EVAL_MAGIC1}, {EVAL_MAGIC2})")

        stage_count = get_word()
        self.stages = [get_word() for _ in range(stage_count - 1)]

        self.stage_data = {}
        for stg in self.stages:
            stg_dict = {}
            stg_dict["constant"] = get_word()
            stg_dict["parity"] = get_word()

            for name, count, mirror_name in PATTERN_SPECS:
                mirror = _MIRROR_MAPS[mirror_name]
                table = [0] * count
                for i in range(count):
                    if mirror is None or mirror[i] == i:
                        table[i] = get_word()
                    else:
                        table[i] = table[mirror[i]]
                stg_dict[name] = table

            self.stage_data[stg] = stg_dict

        if pos != len(raw):
            print(f"Warning: {len(raw) - pos} unread trailing bytes in {filepath}", file=sys.stderr)

    def write_binary(self, filepath: Path):
        raw_words = []
        raw_words.append(EVAL_MAGIC1)
        raw_words.append(EVAL_MAGIC2)
        raw_words.append(len(self.stages) + 1)
        for stg in self.stages:
            raw_words.append(stg)

        for stg in self.stages:
            stg_dict = self.stage_data[stg]
            raw_words.append(stg_dict["constant"])
            raw_words.append(stg_dict["parity"])

            for name, count, mirror_name in PATTERN_SPECS:
                mirror = _MIRROR_MAPS[mirror_name]
                table = stg_dict[name]
                for i in range(count):
                    if mirror is None or mirror[i] == i:
                        raw_words.append(table[i])

        payload = struct.pack(f">{len(raw_words)}h", *raw_words)
        with gzip.open(filepath, "wb", compresslevel=9) as f:
            f.write(payload)

    def info(self):
        print(f"Stages ({len(self.stages)}): {self.stages}")
        for stg in self.stages:
            d = self.stage_data[stg]
            print(f"  Stage {stg:2d}: constant={d['constant']} ({d['constant']/4:.1f}), parity={d['parity']} ({d['parity']/4:.1f})")

    def export_tune8dbs(self, out_dir: Path):
        out_dir.mkdir(parents=True, exist_ok=True)
        # Write option file
        option_path = out_dir / "option.txt"
        with open(option_path, "w") as f:
            f.write("main\n")
            f.write(f"{len(self.stages)}\n")
            f.write(" ".join(str(s) for s in self.stages) + "\n")

        for stg in self.stages:
            d = self.stage_data[stg]
            # Write main.s<stg>
            # constant, parity are stored in coeffs2 as val * 2048 (since val * 512 internal, and stored as 4 * internal)
            main_path = out_dir / f"main.s{stg}"
            with open(main_path, "w") as f:
                f.write(f"{d['constant'] / 2048.0:.8f}\n")
                f.write(f"{d['parity'] / 2048.0:.8f}\n")

            # Write each pattern .b<stg>
            for name, count, _ in PATTERN_SPECS:
                b_path = out_dir / f"{name}.b{stg}"
                vals = [x / 2048.0 for x in d[name]]
                freq = [1 if x != 0 else 0 for x in d[name]]
                with open(b_path, "wb") as f:
                    f.write(struct.pack(f"{count}f", *vals))
                    f.write(struct.pack(f"{count}i", *freq))
        print(f"Exported {len(self.stages)} stages to {out_dir}")

    def import_tune8dbs(self, in_dir: Path):
        option_path = in_dir / "option.txt"
        with open(option_path, "r") as f:
            lines = [line.strip() for line in f if line.strip()]
        prefix = lines[0]
        stage_count = int(lines[1])
        self.stages = [int(x) for x in lines[2].split()[:stage_count]]

        self.stage_data = {}
        for stg in self.stages:
            stg_dict = {}
            main_path = in_dir / f"{prefix}.s{stg}"
            with open(main_path, "r") as f:
                vals_txt = [line.strip() for line in f if line.strip()]
                stg_dict["constant"] = int(round(float(vals_txt[0]) * 2048.0))
                stg_dict["parity"] = int(round(float(vals_txt[1]) * 2048.0)) if len(vals_txt) > 1 else 0

            for name, count, mirror_name in PATTERN_SPECS:
                b_path = in_dir / f"{name}.b{stg}"
                with open(b_path, "rb") as f:
                    raw_vals = struct.unpack(f"{count}f", f.read(count * 4))
                    raw_freq = struct.unpack(f"{count}i", f.read(count * 4))
                table = [int(round(v * 2048.0)) for v in raw_vals]
                # Enforce mirror symmetry if applicable
                mirror = _MIRROR_MAPS[mirror_name]
                if mirror is not None:
                    for i in range(count):
                        if mirror[i] != i:
                            table[i] = table[mirror[i]]
                stg_dict[name] = table

            self.stage_data[stg] = stg_dict


def main():
    parser = argparse.ArgumentParser(description="Zebra coeffs2.bin inspection and pack/unpack tool.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    info_parser = subparsers.add_parser("info", help="Print summary information about coeffs file")
    info_parser.add_argument("file", type=Path, help="Path to coeffs2.bin")

    verify_parser = subparsers.add_parser("verify-roundtrip", help="Verify roundtrip pack/unpack against original")
    verify_parser.add_argument("file", type=Path, help="Path to coeffs2.bin")
    verify_parser.add_argument("--tmp-out", type=Path, default=Path("/tmp/coeffs_repacked.bin"), help="Temporary output path")

    export_parser = subparsers.add_parser("export-tune8dbs", help="Export coeffs2.bin to tune8dbs .b* and main.s* files")
    export_parser.add_argument("file", type=Path, help="Path to coeffs2.bin")
    export_parser.add_argument("out_dir", type=Path, help="Output directory")

    import_parser = subparsers.add_parser("import-tune8dbs", help="Import tune8dbs .b* and main.s* files into coeffs2.bin")
    import_parser.add_argument("in_dir", type=Path, help="Input directory")
    import_parser.add_argument("out_file", type=Path, help="Output coeffs2.bin path")

    args = parser.parse_args()

    if args.command == "info":
        cf = CoeffsFile()
        cf.read_binary(args.file)
        cf.info()

    elif args.command == "verify-roundtrip":
        cf1 = CoeffsFile()
        cf1.read_binary(args.file)
        cf1.info()
        cf1.write_binary(args.tmp_out)

        cf2 = CoeffsFile()
        cf2.read_binary(args.tmp_out)

        # Check equivalence
        assert cf1.stages == cf2.stages, "Stages mismatch"
        for stg in cf1.stages:
            d1 = cf1.stage_data[stg]
            d2 = cf2.stage_data[stg]
            assert d1["constant"] == d2["constant"], f"Stage {stg} constant mismatch"
            assert d1["parity"] == d2["parity"], f"Stage {stg} parity mismatch"
            for name, count, _ in PATTERN_SPECS:
                assert d1[name] == d2[name], f"Stage {stg} {name} mismatch"

        # Compare decompressed bytes directly
        with gzip.open(args.file, "rb") as f:
            b1 = f.read()
        with gzip.open(args.tmp_out, "rb") as f:
            b2 = f.read()
        assert b1 == b2, f"Decompressed bytes mismatch! (len1={len(b1)}, len2={len(b2)})"
        print(f"SUCCESS: 100% exact byte-for-byte decompressed match ({len(b1)} bytes)!")

    elif args.command == "export-tune8dbs":
        cf = CoeffsFile()
        cf.read_binary(args.file)
        cf.export_tune8dbs(args.out_dir)

    elif args.command == "import-tune8dbs":
        cf = CoeffsFile()
        cf.import_tune8dbs(args.in_dir)
        cf.write_binary(args.out_file)
        print(f"Successfully packaged {len(cf.stages)} stages to {args.out_file}")


if __name__ == "__main__":
    main()
