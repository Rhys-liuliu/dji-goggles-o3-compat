#!/usr/bin/env python3
"""列出 DJI 固件包（tar）里的模块，并解析主模块的 IMaH 头。

用法:
    python imah_tar.py <package.bin> [--extract OUTDIR] [--member NAME]

要点:
    - 外层是标准 ustar：成员名、大小都是明文字段，不需要厂商工具
    - 主固件是 IMaH 容器：224 字节头 + signature_size 签名 + payload
    - enc_key 为空 && scramble_key 全 0 → payload 是明文，可以直接往下解
"""

import argparse
import os
import struct
import tarfile

IMAH_MAGIC = b"IM*H"


def parse_imah_header(blob: bytes) -> dict:
    if len(blob) < 224 or blob[:4] != IMAH_MAGIC:
        return {}
    (magic, header_version, size, reserved, header_size, sig_size,
     payload_size, target_size) = struct.unpack("<4sIIIIIII", blob[0:32])
    # 实测布局（zv902 / zv300 一致）：
    #   0x20 os/arch/compression/anti_version, 0x24 auth_alg, 0x28 auth_key,
    #   0x2C enc_key, 0x30 scramble(16B), 0x40 name(4B), 0x60 type(4B),
    #   0x64 version(u32), 0x68 date(u32, 形如 0x20240517)
    (os_id, arch, compression) = struct.unpack("<BBB", blob[32:35])
    anti_version = struct.unpack("<I", blob[32:36])[0]
    auth_alg = struct.unpack("<I", blob[36:40])[0]
    auth_key = blob[40:44]
    enc_key = blob[44:48]
    scram = blob[48:64]
    name = blob[64:68].rstrip(b"\0")
    mtype = blob[96:100].rstrip(b"\0")
    version = struct.unpack("<I", blob[100:104])[0]
    date = struct.unpack("<I", blob[104:108])[0]
    return {
        "header_version": header_version,
        "size": size,
        "header_size": header_size,
        "signature_size": sig_size,
        "payload_size": payload_size,
        "target_size": target_size,
        "os": os_id,
        "arch": arch,
        "compression": compression,
        "anti_version": anti_version,
        "auth_alg": auth_alg,
        "auth_key": auth_key.decode("latin-1"),
        "enc_key": enc_key.decode("latin-1").replace("\0", ""),
        "scrambled": any(scram),
        "name": name.decode("latin-1"),
        "type": mtype.decode("latin-1"),
        "version": version,
        "date": date,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("package")
    ap.add_argument("--extract", metavar="OUTDIR", help="把能完整读到的成员解出来")
    ap.add_argument("--member", help="只处理这个成员（默认取最大的主模块）")
    args = ap.parse_args()

    tf = tarfile.open(args.package, "r:")
    members = [m for m in tf if m.isfile()]
    print(f"{'size':>14}  {'offset':>10}  name")
    for m in members:
        print(f"{m.size:14d}  {m.offset_data:10d}  {m.name}")

    target = next((m for m in members if args.member and m.name == args.member), None)
    if target is None:
        target = max(members, key=lambda m: m.size)

    with open(args.package, "rb") as f:
        f.seek(target.offset_data)
        head = f.read(224)
    info = parse_imah_header(head)
    print(f"\n=== main module: {target.name} ===")
    if not info:
        print("not an IMaH container (or header < 224 bytes)")
    else:
        for k in ("type", "name", "version", "size", "payload_size",
                  "header_size", "signature_size", "auth_alg", "auth_key",
                  "enc_key", "scrambled", "anti_version", "date"):
            print(f"  {k:16} {info[k]}")
        if not info["enc_key"] and not info["scrambled"]:
            print("  => payload 明文可读（只签名，未加密）")
        else:
            print("  => payload 加密/加扰，需要厂商密钥")

    if args.extract:
        os.makedirs(args.extract, exist_ok=True)
        total = 0
        for m in members:
            if m.offset_data + m.size > os.path.getsize(args.package):
                print(f"  skip (truncated): {m.name}")
                continue
            data = tf.extractfile(m).read()
            dst = os.path.join(args.extract, os.path.basename(m.name))
            with open(dst, "wb") as o:
                o.write(data)
            total += len(data)
        print(f"\nextracted {len(members)} members, {total} bytes -> {args.extract}")


if __name__ == "__main__":
    main()
