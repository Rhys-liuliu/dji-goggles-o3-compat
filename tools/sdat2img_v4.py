#!/usr/bin/env python3
"""Android block-OTA（transfer list v4）→ ext4 镜像。

用法:
    python sdat2img_v4.py system.transfer.list system.new.dat system.img

关键点（踩过坑）:
    - 头 4 行: 版本 / 头里的块数 / stash / 0
    - 之后每行: "<cmd> <count>,<v1>,<v2>,..."
      count = 后面数字的个数，数字两两成对 (start, end)
    - **end 是独占的**：块数 = end - start
      校验方法: sum(new 块数) * 4096 必须等于 system.new.dat 的实际大小
    - cmd: new(带数据) / erase / zero / trim

做成 end 包含会多算几千块，结果是镜像里 inode 表全零、目录读不出来。
"""

import os
import sys

BLOCK = 4096


def parse_transfer_list(path):
    lines = [ln.strip() for ln in open(path, "r", encoding="utf-8", errors="replace") if ln.strip()]
    version = int(lines[0])
    if version != 4:
        print(f"warning: transfer list version {version}, 本脚本按 v4 处理", file=sys.stderr)
    cmds = []
    for line in lines[4:]:
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        cmd = parts[0]
        nums = [int(x) for x in parts[1].split(",")]
        vals = nums[1:]
        pairs = [(vals[i], vals[i + 1]) for i in range(0, len(vals), 2)]
        cmds.append((cmd, pairs))
    return version, cmds


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    tl_path, dat_path, out_path = sys.argv[1:4]

    version, cmds = parse_transfer_list(tl_path)
    need = sum((b - a) for cmd, pairs in cmds if cmd == "new" for a, b in pairs) * BLOCK
    have = os.path.getsize(dat_path)
    print(f"v{version}: new-data 需要 {need} B, 实际 {have} B")
    if need != have:
        print("  ⚠ 不相等 → 区间语义可能不是 end 独占，或数据被截断", file=sys.stderr)

    max_block = max(b for _, pairs in cmds for _, b in pairs)
    src = open(dat_path, "rb")
    written = 0
    with open(out_path, "wb") as out:
        out.truncate(max_block * BLOCK)
        for cmd, pairs in cmds:
            if cmd == "new":
                for a, b in pairs:
                    size = (b - a) * BLOCK
                    if size <= 0:
                        continue
                    chunk = src.read(size)
                    out.seek(a * BLOCK)
                    out.write(chunk)
                    written += len(chunk)
            elif cmd in ("erase", "zero"):
                for a, b in pairs:
                    if b > a:
                        out.seek(a * BLOCK)
                        out.write(b"\x00" * ((b - a) * BLOCK))
    src.close()

    with open(out_path, "rb") as f:
        f.seek(1024 + 56)
        magic = f.read(2)
    print(f"写入 {written} B -> {out_path} ({os.path.getsize(out_path)} B), "
          f"ext4 magic @1080 = {magic.hex()} {'✅' if magic[::-1] == b'\x53\xef' else '❌'}")


if __name__ == "__main__":
    main()
