# 发布用文案（可直接粘贴）

三份：Reddit / rcgroups（英文），中文社区一段。
建议标题统一用「结论 + 证据类型」，别用问句。

---

## 1) Reddit — r/DJI 或 r/fpv

**Title**

```
Why Goggles 3 supports the O3 Air Unit but Goggles N3 doesn't — firmware-level teardown
```

**Body**

```
Short version: Goggles 3 got O3 support in firmware 01.00.0200 (2024-07-24) — DJI's own
release list says "Added support to use with DJI O3 Air Unit". Goggles N3 has shipped ten
firmware versions between 2024-11 and 2026-10 and never mentions O3, while spending one
release on O4 Air Unit support.

It is not a radio limitation. N3 is 2T4R dual-band like G3, same S2/E3T family, and O3
(2T2R, 2.4/5.8, 40 MHz / 50 Mbps) is a strict subset of O4 (2T4R, 60 MHz / 60 Mbps). N3 even
refuses Mini 4 Pro — an O4 aircraft — which tells you the compatibility list is deliberately
narrow.

The interesting part is what the firmware looks like. G3's main module is signed but NOT
encrypted (empty enc_key, zero scramble key), so it unpacks into an Android 9 OTA
(userdebug / test-keys, device e3t_zv902). N3's identical module 2805 is UFIE-encrypted with
scrambling, and the public key set stops at 2021.

So "just port O3 to N3" hits three walls at once: the decision logic lives in compiled link
binaries (libwlm maps product identity through a byte-table lookup — no whitelist string
anywhere), the image is encrypted, and flashing needs a signature bypass plus root, which N3
doesn't have (no adb, no shell, FTP requires DJI-issued credentials; the DUML vendor channel
only answers version queries → "zv300 gl Ver.02").

Write-up, tools (IMaH parser, sdat2img v4, minimal ext4 reader, DUML probe) and the raw
evidence are here — no firmware is redistributed:
https://github.com/Rhys-liuliu/dji-goggles-o3-compat

Happy to be corrected by anyone with a decompiler and more patience than me.
```

---

## 2) rcgroups / INTOFPV（更技术）

**Title**

```
Goggles 3 vs N3 — O3 compatibility is firmware, not RF: firmware structure + DUML probe
```

**Body**

```
Pulled both retail packages and did the boring part properly.

Containers are the same shape on both goggles: outer tar → cfg (0000/CNFG, plaintext XML
manifest) / CPLD (2803) / GFSK (1403) / main (2805). Main module is IMaH v2.

Difference is one field:

  G3  2805: enc_key = <empty>, scramble = 0x00 * 16, auth_alg = 3        -> payload is a ZIP
  N3  2805: enc_key = UFIE,    scramble = 16 random bytes, alg = 262147  -> entropy 8.0

G3's payload is a block OTA (Android 9, e3t_zv902, userdebug/test-keys). Rebuilt the ext4
from system.new.dat + transfer list v4 — note the range ends are EXCLUSIVE; 123,004 blocks
× 4096 = 503,824,384 B matches system.new.dat byte for byte. Get that wrong and the inode
table reads as zeros.

Inside: /etc/wlm_cfg.json (product ZV902, soc e3t, module ids 0x0e07/0x0e00/0x0e04...),
libwlm.so, dji_glasses, dji_gfsk_agent, dji_wl.ko. No O3/O4/wm1695 string anywhere in 654 MB,
and libwlm's own symbol table shows why: wlm_get_product_model_num is a byte-table lookup
(ldrb w0,[x8,w9]), and the library only maps strings→module ids, opens channels, and keeps a
shared peer dev-info list. It executes; it doesn't gate.

On the device side (N3, 2CA3:0020): RNDIS 192.168.60.2 (no DHCP, poke it with 192.168.60.1),
only FTP 21 open and it 530s everything; mass storage is the SD card only. The vendor bulk
interfaces answer DUML — GENERAL/0x01 returns "zv300 gl Ver.02" (0x0F43 / 0x000A), then just
0x82 heartbeats. cmd 0x02..0x0C: no replies. No adb, no shell, no writes.

Repo with the tools and the byte-level evidence (no firmware): 
https://github.com/Rhys-liuliu/dji-goggles-o3-compat
```

---

## 3) 中文社区（贴吧 / B站专栏 / 知乎）

**标题**

```
拆了两版固件之后：G3 能收 O3、N3 不能，差的到底是什么
```

**正文**

```
结论先说：不是射频问题，是固件问题，而且 N3 这条路被加密+签名堵死了。

1）时间线可查。DJI Assistant 会把每个产品的版本历史缓存在本机，
   G3 的清单里 01.00.0200（2024-07-24）写着 "Added support to use with DJI O3 Air Unit"；
   N3 从 2024-11 到 2026-10 一共 10 个版本，一次没提 O3，中间还专门做了一个 O4 Air Unit。

2）硬件不背锅。N3 是 2T4R 双频、和 G3 同代 S2/E3T 平台，而 O3（2T2R、40MHz、50Mbps）
   本来就是 O4（2T4R、60MHz、60Mbps）的子集。N3 连同为 O4 的 Mini 4 Pro 都不支持，
   说明它的兼容名单是刻意收窄的。

3）固件层面差一个字段。两代的主模块都是 2805/IMaH，但：
   G3：enc_key 为空、scramble 全零 → 只签名，payload 能直接解成 Android 9 OTA；
   N3：enc_key=UFIE、16 字节加扰 → 熵 8.00，公开密钥库最新只到 2021，解不开。

4）G3 解出来的东西：system 分区 654MB 的 ext4（1806 个文件），
   /etc/wlm_cfg.json 是链路配置，libwlm.so 是链路库。
   全盘扫 wm1695 / O3AU / ocusync：0 命中。
   反汇编 libwlm 的 wlm_get_product_model_num，发现机型身份是一次"字节表查表"——
   兼容判定根本不在这层，它是按数字 device_type 在上层做的。

5）真机 N3 也试过了：只有 FTP 21（所有常见口令 530）、SD 卡可读、
   DUML 厂商通道能对话但只回 "zv300 gl Ver.02" 和心跳，没有 adb、没有 shell、不能写。

所以"让 N3 收 O3"要同时过三关：拿到 G3 的实现（得反编译）、写进 N3（固件加密）、
刷进去（签名+反回滚、无 root）。三样全缺。现实解：买 G3，或把机上的 O3 换成 O4 Air Unit。

工具和逐字节证据都放这儿了（不含任何固件）：
https://github.com/Rhys-liuliu/dji-goggles-o3-compat
```

---

## 发布小贴士

- Reddit 首发选 r/DJI（人多）或 r/fpv（懂行）；两边不要同一天连发，容易被判 spam。
- 标题别写 "DJI 骗钱 / 阉割"这类词，容易被删；用"结论 + 证据"的写法更容易被版主留存。
- 帖子里只贴仓库链接，不要贴固件下载地址（DDD 的链接也别贴，容易被判定为分发）。
- 有人质疑时，直接引 `evidence/` 里的 hexdump 和 release-notes JSON，最有说服力。
