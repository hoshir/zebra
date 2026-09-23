#!/usr/bin/env python3
"""migrate_coeffs_v2.py - Migrate coeffs2.bin to V2 schema with corner10 and diamond8.

Expands 11-pattern coeffs2.bin to 13-pattern coeffs2.bin by adding zeroed entries
for corner10 (59,049 entries) and diamond8 (6,561 entries) for all stages.
"""

import argparse
import gzip
import shutil
import struct
import sys
from pathlib import Path

EVAL_MAGIC1 = 5358
EVAL_MAGIC2 = 9793

POW3 = [3**i for i in range(12)]

PATTERN_SPECS_11 = [
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

PATTERN_SPECS_12 = PATTERN_SPECS_11 + [
    ("corner10", 59049, "none"),
]

PATTERN_SPECS_13 = PATTERN_SPECS_12 + [
    ("diamond8", 6561, "none"),
]


def build_odometer_patterns(n: int):
    total = POW3[n]
    row = [0] * n
    res = []
    for _ in range(total):
        res.append(list(row))
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


def get_mirror_maps(specs):
    maps = {}
    flip_linear = {}
    for n in range(3, 9):
        patterns = build_odometer_patterns(n)
        mirror_map = [0] * POW3[n]
        flip_list = [0] * POW3[n]
        for i, row in enumerate(patterns):
            m = sum(row[j] * POW3[n - 1 - j] for j in range(n))
            mirror_map[i] = min(i, m)
            flip_list[i] = m
        maps[f"mirror{n}"] = mirror_map
        flip_linear[n] = flip_list

    patterns33 = build_odometer_patterns(9)
    map33 = [0] * POW3[9]
    for i, row in enumerate(patterns33):
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
    maps["mirror33"] = map33

    flip8 = flip_linear[8]
    map8x2 = [0] * 59049
    for i in range(6561):
        for j in range(3):
            for k in range(3):
                idx = i + 6561 * j + 19683 * k
                flipped_idx = flip8[i] + 6561 * k + 19683 * j
                map8x2[idx] = min(idx, flipped_idx)
    maps["mirror8x2"] = map8x2
    maps["none"] = None
    return maps


def read_coeffs(filepath: Path):
    with gzip.open(filepath, "rb") as f:
        buf = f.read()

    pos = 0

    def read_short():
        nonlocal pos
        val = struct.unpack_from(">h", buf, pos)[0]
        pos += 2
        return val

    def read_ushort():
        nonlocal pos
        val = struct.unpack_from(">H", buf, pos)[0]
        pos += 2
        return val

    m1 = read_ushort()
    m2 = read_ushort()
    if m1 != EVAL_MAGIC1 or m2 != EVAL_MAGIC2:
        raise ValueError(f"Invalid magic numbers: {m1}, {m2}")

    stage_count = read_short()
    num_stages = stage_count - 1
    stages = [read_short() for _ in range(num_stages)]

    rem_bytes = len(buf) - pos
    bytes_per_stage = rem_bytes // num_stages
    shorts_per_stage = bytes_per_stage // 2

    # Determine input specs
    maps11 = get_mirror_maps(PATTERN_SPECS_11)
    unique_11 = 2 + sum(sum(1 for i, m in enumerate(maps11[mt]) if m == i) if mt != "none" else cnt for _, cnt, mt in PATTERN_SPECS_11)
    maps12 = get_mirror_maps(PATTERN_SPECS_12)
    unique_12 = 2 + sum(sum(1 for i, m in enumerate(maps12[mt]) if m == i) if mt != "none" else cnt for _, cnt, mt in PATTERN_SPECS_12)

    if shorts_per_stage == unique_11:
        in_specs = PATTERN_SPECS_11
        maps = maps11
        print(f"Detected 11-pattern input format ({shorts_per_stage} shorts/stage).")
    elif shorts_per_stage == unique_12:
        in_specs = PATTERN_SPECS_12
        maps = maps12
        print(f"Detected 12-pattern input format ({shorts_per_stage} shorts/stage).")
    else:
        # Fallback to checking 13-pattern
        maps13 = get_mirror_maps(PATTERN_SPECS_13)
        unique_13 = 2 + sum(sum(1 for i, m in enumerate(maps13[mt]) if m == i) if mt != "none" else cnt for _, cnt, mt in PATTERN_SPECS_13)
        if shorts_per_stage == unique_13:
            in_specs = PATTERN_SPECS_13
            maps = maps13
            print(f"Detected 13-pattern input format ({shorts_per_stage} shorts/stage).")
        else:
            raise ValueError(f"Unexpected shorts per stage: {shorts_per_stage} (expected {unique_11}, {unique_12}, or {unique_13})")

    stage_data = {}
    for stg in stages:
        sdata = {}
        sdata["constant"] = read_short()
        sdata["parity"] = read_short()
        for name, count, mtype in in_specs:
            table = [0] * count
            mmap = maps[mtype]
            if mmap is None:
                for k in range(count):
                    table[k] = read_short()
            else:
                for k in range(count):
                    if mmap[k] == k:
                        table[k] = read_short()
                    else:
                        table[k] = table[mmap[k]]
            sdata[name] = table
        stage_data[stg] = sdata

    return stages, stage_data


def write_v2(output_path: Path, stages, stage_data):
    maps = get_mirror_maps(PATTERN_SPECS_13)
    buf = bytearray()

    def write_short(val):
        buf.extend(struct.pack(">h", int(val)))

    def write_ushort(val):
        buf.extend(struct.pack(">H", int(val)))

    write_ushort(EVAL_MAGIC1)
    write_ushort(EVAL_MAGIC2)
    write_short(len(stages) + 1)
    for stg in stages:
        write_short(stg)

    for stg in stages:
        sdata = stage_data[stg]
        write_short(sdata["constant"])
        write_short(sdata["parity"])
        for name, count, mtype in PATTERN_SPECS_13:
            table = sdata.get(name)
            if table is None:
                table = [0] * count
            mmap = maps[mtype]
            if mmap is None:
                for k in range(count):
                    write_short(table[k])
            else:
                for k in range(count):
                    if mmap[k] == k:
                        write_short(table[k])

    with gzip.open(output_path, "wb") as f:
        f.write(buf)


def main():
    parser = argparse.ArgumentParser(description="Migrate coeffs2.bin to V2 with corner10 & diamond8 zero-padding.")
    parser.add_argument("--in", dest="in_file", type=Path, default=Path("data/coeffs2.bin"), help="Input coeffs2.bin")
    parser.add_argument("--out", dest="out_file", type=Path, default=Path("data/coeffs2.bin"), help="Output coeffs2.bin")
    parser.add_argument("--backup", action="store_true", default=True, help="Create .bak backup of in_file")
    args = parser.parse_args()

    if not args.in_file.exists():
        print(f"Error: {args.in_file} does not exist.", file=sys.stderr)
        sys.exit(1)

    if args.backup and args.in_file == args.out_file:
        bak = args.in_file.with_suffix(".bin.bak")
        shutil.copyfile(args.in_file, bak)
        print(f"Backed up {args.in_file} -> {bak}")

    print(f"Reading coefficients from {args.in_file}...")
    stages, stage_data = read_coeffs(args.in_file)
    print(f"Loaded {len(stages)} stages: {stages}")

    for stg in stages:
        if "corner10" not in stage_data[stg]:
            stage_data[stg]["corner10"] = [0] * 59049
        if "diamond8" not in stage_data[stg]:
            stage_data[stg]["diamond8"] = [0] * 6561

    print(f"Writing 13-pattern coefficients with zero-padded corner10 & diamond8 to {args.out_file}...")
    write_v2(args.out_file, stages, stage_data)
    print("Migration complete successfully.")


if __name__ == "__main__":
    main()
