#!/usr/bin/env python3
"""最小 ext4 读取器：不 mount、不需要 root，直接读镜像。

用法:
    python ext4_read.py <image> info
    python ext4_read.py <image> ls   <path> [--long]
    python ext4_read.py <image> cat  <path>
    python ext4_read.py <image> find <regex>

支持: extent 树（depth 0..n）、64bit 特性、老式直接块回退。
不支持: 加密目录、内联数据。
"""

import argparse
import re
import struct
import sys

S_IFMT = 0xF000
S_IFDIR = 0x4000


class Ext4:
    def __init__(self, path):
        self.f = open(path, "rb")
        sb = self._read(1024, 1024)
        self.inodes_count, self.blocks_count = struct.unpack("<II", sb[0:8])
        self.first_data_block = struct.unpack("<I", sb[20:24])[0]
        self.block_size = 1024 << struct.unpack("<I", sb[24:28])[0]
        self.inode_size = struct.unpack("<H", sb[88:90])[0]
        self.incompat = struct.unpack("<I", sb[96:100])[0]
        self.is64 = bool(self.incompat & 0x80)
        self.desc_size = 32
        if self.is64:
            dsz = struct.unpack("<H", sb[254:256])[0]
            if dsz >= 32:
                self.desc_size = dsz
        gd = self._read((self.first_data_block + 1) * self.block_size, self.desc_size)
        self.inode_table = struct.unpack("<I", gd[8:12])[0]
        if self.is64 and self.desc_size >= 64:
            self.inode_table |= struct.unpack("<I", gd[40:44])[0] << 32

    def _read(self, offset, size):
        self.f.seek(offset)
        return self.f.read(size)

    def inode(self, ino):
        off = self.inode_table * self.block_size + (ino - 1) * self.inode_size
        return self._read(off, self.inode_size)

    @staticmethod
    def mode_of(raw):
        return struct.unpack("<H", raw[0:2])[0]

    @staticmethod
    def size_of(raw):
        lo = struct.unpack("<I", raw[4:8])[0]
        hi = struct.unpack("<I", raw[108:112])[0]
        return lo | (hi << 32)

    def data_of(self, raw, size):
        out = bytearray()
        blk = raw[40:100]
        magic, _, _, depth = struct.unpack("<HHHH", blk[0:8])
        if magic != 0xF30A:
            for i in range(12):
                p = struct.unpack("<I", blk[i * 4:i * 4 + 4])[0]
                if p:
                    out += self._read(p * self.block_size, self.block_size)
            return bytes(out[:size])

        # 按逻辑块号落位，文件里的空洞补零（稀疏文件必须这样处理，
        # 否则第二个 extent 会被拼到第一个后面，文件被截短）
        chunks = []

        def walk(buf, d, base):
            _, cnt, _, dd = struct.unpack("<HHHH", buf[0:8])
            for i in range(cnt):
                off = 12 + i * 12
                ee_block, ee_len, hi, lo = struct.unpack("<IHHI", buf[off:off + 12])
                start = (hi << 32) | lo
                if ee_len > 32768:
                    ee_len -= 32768
                if dd == 0:
                    chunks.append((base + ee_block,
                                   self._read(start * self.block_size, ee_len * self.block_size)))
                else:
                    walk(self._read(start * self.block_size, self.block_size), dd - 1, base + ee_block)

        walk(blk, depth, 0)
        out = bytearray(size)
        for logical, data in chunks:
            off = logical * self.block_size
            out[off:off + len(data)] = data
        return bytes(out)

    def listdir(self, ino):
        raw = self.inode(ino)
        data = self.data_of(raw, self.size_of(raw))
        pos, entries = 0, []
        while pos + 8 <= len(data):
            ino2, rec_len, name_len, ftype = struct.unpack("<IHBB", data[pos:pos + 8])
            if rec_len < 8:
                break
            name = data[pos + 8:pos + 8 + name_len].decode("utf-8", "replace")
            pos += rec_len
            if name not in (".", ".."):
                entries.append((name, ftype, ino2))
        return entries

    def resolve(self, path):
        ino = 2
        for part in [p for p in path.strip("/").split("/") if p]:
            hit = next((e for e in self.listdir(ino) if e[0] == part), None)
            if hit is None:
                raise FileNotFoundError(path)
            ino = hit[2]
        return ino


def main():
    ap = argparse.ArgumentParser(description="minimal ext4 reader")
    ap.add_argument("image")
    ap.add_argument("action", choices=["info", "ls", "cat", "find"])
    ap.add_argument("arg", nargs="?", default="/")
    ap.add_argument("--long", action="store_true")
    a = ap.parse_args()

    fs = Ext4(a.image)
    if a.action == "info":
        print(f"block_size={fs.block_size} inodes={fs.inodes_count} blocks={fs.blocks_count} "
              f"inode_size={fs.inode_size} inode_table={fs.inode_table} 64bit={fs.is64}")
        return

    if a.action == "ls":
        for name, ftype, ino2 in sorted(fs.listdir(fs.resolve(a.arg)), key=lambda e: e[0]):
            if a.long:
                raw = fs.inode(ino2)
                kind = "d" if (fs.mode_of(raw) & S_IFMT) == S_IFDIR else "-"
                print(f"{kind} {fs.size_of(raw):10d}  {name}")
            else:
                print(name)
    elif a.action == "cat":
        raw = fs.inode(fs.resolve(a.arg))
        sys.stdout.buffer.write(fs.data_of(raw, fs.size_of(raw)))
    elif a.action == "find":
        rx = re.compile(a.arg, re.I)
        stack = [("", 2)]
        while stack:
            prefix, ino = stack.pop()
            for name, ftype, ino2 in fs.listdir(ino):
                path = prefix + "/" + name
                if rx.search(name):
                    print(path)
                if ftype == 2:
                    stack.append((path, ino2))


if __name__ == "__main__":
    main()
