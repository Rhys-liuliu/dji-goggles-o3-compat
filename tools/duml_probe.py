#!/usr/bin/env python3
"""和 DJI 眼镜/飞机对话：DUML over USB bulk。

用法:
    python duml_probe.py --dll C:\\path\\libusb0.dll --iface 4
    python duml_probe.py --dll … --iface 4 --sweep 0x02 0x0c

依赖:
    pip install pyusb
    Windows 需要 64 位 libusb0.dll（libusb-win32 1.4.0.2 amd64），
    因为 DJI Assistant 自带的那个是 32 位，和 64 位 Python 不兼容。

说明:
    - 设备 VID 0x2CA3，厂商接口 class 0xFF / sub 0x43 / proto 0x01
    - 每个接口在 libusb-win32 下是独立节点，需要 --iface 指定
    - 眼镜（ZV300）只回身份/状态：GENERAL/0x01 返回版本串，其余无应答
"""

import argparse
import sys
import time

import usb.core
import usb.util
import usb.backend.libusb0 as l0

VID = 0x2CA3
CRC8_POLY = 0x07


def crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ CRC8_POLY) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def packet(seq: int, cmd_id: int, payload: bytes = b"",
           cmd_set: int = 0x00, sender=(0x0A, 0), receiver=(0x00, 0)) -> bytes:
    """DUML v1: 55 | len | ver=04 | hdr_crc | sender(2) | receiver(2) | seq(2) | flags | set | id | payload | crc"""
    body = bytes([sender[0], sender[1], receiver[0], receiver[1],
                  seq & 0xFF, (seq >> 8) & 0xFF, 0x00, cmd_set, cmd_id]) + payload
    head = bytes([0x55, (len(body) + 1) & 0xFF, 0x04])
    head += bytes([crc8(head)])
    return head + body + bytes([crc8(head + body)])


def printable(blob: bytes) -> str:
    return "".join(chr(c) if 32 <= c < 127 else "." for c in blob)


def find_interface(backend, iface):
    for dev in usb.core.find(idVendor=VID, find_all=True, backend=backend):
        for cfg in dev:
            for intf in cfg:
                if intf.bInterfaceNumber == iface:
                    return dev, intf
    return None, None


def main():
    ap = argparse.ArgumentParser(description="DUML probe")
    ap.add_argument("--dll", required=True, help="64-bit libusb0.dll 路径")
    ap.add_argument("--iface", type=int, default=4, help="厂商 bulk 接口号")
    ap.add_argument("--out-ep", type=lambda s: int(s, 0), default=0x04)
    ap.add_argument("--in-ep", type=lambda s: int(s, 0), default=0x85)
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--sweep", nargs=2, type=lambda s: int(s, 0), metavar=("FROM", "TO"),
                    help="扫一段 GENERAL cmd_id（只发空负载）")
    a = ap.parse_args()

    backend = l0.get_backend(find_library=lambda _: a.dll)
    if backend is None:
        print("libusb0 backend 加载失败：确认是 64 位 DLL", file=sys.stderr)
        sys.exit(1)

    dev, intf = find_interface(backend, a.iface)
    if dev is None:
        print(f"没找到 interface {a.iface}", file=sys.stderr)
        sys.exit(1)
    print(f"device addr={dev.address} interface={a.iface}")
    usb.util.claim_interface(dev, a.iface)

    def exchange(pkt, wait):
        dev.write(a.out_ep, pkt, timeout=1000)
        got, end = [], time.time() + wait
        while time.time() < end:
            try:
                got.append(dev.read(a.in_ep, 4096, timeout=200).tobytes())
            except Exception:
                pass
        return got

    try:
        if a.sweep:
            lo, hi = a.sweep
            for cmd in range(lo, hi + 1):
                replies = exchange(packet(cmd, cmd), 0.7)
                joined = b"".join(replies)
                print(f"cmd 0x{cmd:02x}: {len(replies)} pkt  {printable(joined)[:100]}")
        else:
            pkt = packet(0, 0x01)
            print("TX:", pkt.hex(" "))
            for r in exchange(pkt, a.timeout):
                print("RX:", r.hex(" "))
                print("    ascii:", printable(r))
    finally:
        usb.util.release_interface(dev, a.iface)


if __name__ == "__main__":
    main()
