# dji-goggles-o3-compat

**Why DJI Goggles 3 can receive the O3 Air Unit and Goggles N3 cannot — and whether "make N3 support O3" is possible at all.**

An evidence-based teardown of **retail firmware plus a real device**, with every step reproducible.

> This repository **does not contain or redistribute any DJI firmware or extracted artifacts**
> (size and copyright). It ships the method, the scripts, quoted evidence and the conclusion.
> Get the firmware yourself via DJI Assistant 2.

---

## TL;DR

| Question | Answer |
|---|---|
| Why does G3 work with O3? | The 2024-07-24 firmware update added O3 Air Unit support to the Goggles 3 Android userspace. DJI's own release list: `Added support to use with DJI O3 Air Unit` |
| Why not N3? | Hardware is not the limit (same S2/E3T generation, 2T4R dual-band, O3 ⊂ O4). DJI shipped **10 firmware versions between 2024-11 and 2026-10 with zero O3 work**, while spending a release on O4 Air Unit support |
| Can it be changed? | **Not with public tooling.** Three gates: encrypted firmware (`UFIE` + scrambling), signatures + anti-rollback, and no root / adb / writable debug channel |

---

## Evidence

### 1. DJI's own release lists (parsed from the Assistant cache)

DJI Assistant 2 caches per-product version history as JSON under
`<install>\DJIEngine\DJIData\firm_cache\*.cache`.

**Goggles 3 (zv902)**

| Version | Date | Note |
|---|---|---|
| 01.00.0100 | 2024-04-07 | comms stability between goggles and RC |
| **01.00.0200** | **2024-07-24** | **Added support to use with DJI O3 Air Unit** |
| 01.00.0300 | 2024-09-05 | Added support to use with DJI Neo |

**Goggles N3 (zv300)** — 10 versions, never O3:

| Version | Date | Note |
|---|---|---|
| 01.00.0200 | 2024-11-05 | Avata 2, Neo stabilization |
| 01.00.0300 | 2025-01-07 | **O4 Air Unit / Pro** |
| 01.00.0400 | 2025-03-05 | INAV OSD for O4 |
| 01.00.0500 | 2025-07-25 | screen lock |
| 01.00.0600 | 2025-10-29 | Neo 2 |
| 01.00.0900 | 2026-03-26 | Avata 360 |
| 01.00.1000 / 1100 / 1300 | 2026-06 → 10-19 | fixes |

> Press coverage from 2024 says "v01.00.0300 added O3"; DJI's own list puts it at
> **01.00.0200 (2024-07-24)**. Same release window — 0300 was the Neo update.

### 2. Firmware container: G3 readable, N3 encrypted

Both packages are `tar → modules → IMaH → Android OTA`, but the main module differs:

| | G3 module `2805` | N3 module `2805` |
|---|---|---|
| `type` | `ZV90` | `ZV30` |
| `enc_key` | **empty** | `UFIE` |
| `scramble_key` | all zero | 16 non-zero bytes |
| `auth_alg` | 3 (signature only) | 262147 |
| payload | plaintext Android OTA | ciphertext (entropy 8.00) |

Module IDs are identical across both: `0000` (CNFG manifest) / `1403` (GFSK) /
`2803` (CPLD) / `2805` (main). Same product line, one encrypted shell.

Details: [docs/firmware-format.md](docs/firmware-format.md).

### 3. The G3 system image rebuilds into a browsable filesystem

`system.new.dat.br` + `system.transfer.list` (v4) → ext4, 1,806 entries.
The critical detail: **range ends are exclusive** (`blocks = end - start`).
Get it wrong by one and the data length no longer matches
(123,004 blocks × 4096 = 503,824,384 B — byte-exact against `system.new.dat`).

What is inside:

```text
/etc/device_table.json   device_name "E3T_ZV902", device_type "GLASS", host_type "MASTER"
/etc/wlm_cfg.json        link config: product "ZV902", soc "e3t",
                         libwlm_module_id 0x0e07, sdr_agent_host_id 0x0e00,
                         modules: ds_master / link_sw / link_state / dev_mgr / agt_mgr
/lib64/libwlm.so         the link stack itself
/bin/dji_glasses         goggles main service
/bin/dji_gfsk_agent      2.4 GHz signaling agent
/lib/modules/dji_wl.ko   wireless kernel module
OTA metadata             e3t/e3t_zv902:9/PD1A.180720.031/13497:userdebug/test-keys
```

**There is no plaintext compatibility table**: scanning the whole image for
`wm1695`, `O3AU`, `ocusync` returns nothing; `airunit` only matches protocol field
names (`FlycontrolAirUnitStatusArmFlightMode`) and UI strings. The gate lives in the
link stack, keyed by numeric device types.

See [docs/filesystem.md](docs/filesystem.md) and [docs/link-stack.md](docs/link-stack.md).

### 4. Static analysis of `libwlm.so`

`wlm_get_product_model_num` is literally a byte-table lookup:

```asm
adrp  x8, #0x6f000
ldr   x8, [x8, #0xb28]      ; relocated table pointer
and   w9, w0, #0xff
ldrb  w0, [x8, w9, uxtw]    ; return table[idx]
ret
```

The link library maps strings to module ids (`switch_str_to_module_id`), opens
channels (`libwlm_link_channel_active`) and maintains a shared peer list
(`wlm_share_info_read_dev_info`). It **executes** link policy — it does not decide
which aircraft a goggle may talk to. No product whitelist anywhere in it.

### 5. Real N3 probing: identity only

With an N3 attached (`2CA3:0020`):

| Channel | Result |
|---|---|
| RNDIS `192.168.60.2` | pings, only port 21 open |
| FTP 21 | `220 Hello!`, anonymous and common credentials → `530` |
| USB mass storage | SD card only |
| adb (5555) / SSH / HTTP | closed; no adb interface on USB |
| **DUML (vendor bulk)** | **one-way broadcast only** — writes produce no reply; interfaces 3/5/6/7 reject writes |

DUML broadcast on interface 4 (EP `0x04`/`0x85`, cmd `0x82`, ~0.3 s interval):

```text
55 2b 04 58 3c 0a 00 00 80 00 01 00 12
  7a 76 33 30 30 20 67 6c 20 56 65 72 2e 30 32     ← "zv300 gl Ver.02"
  00 0f 43 00 0a 0f 43 00 0a 01 00 00 c0 7c e3
```

Model `ZV300`, version string `zv300 gl Ver.02`. Sweeping `GENERAL 0x02…0x0C`
yields only `0x82` heartbeat broadcasts — no file access, no adb toggle, no writes.

Details: [docs/device-probe.md](docs/device-probe.md).

---

## Verdict: three gates

1. **Obtain G3's O3 implementation** — G3 firmware is readable, but the decision logic is
   compiled into binaries and needs a decompiler
2. **Write it into N3** — N3's main module is `UFIE`-encrypted with scrambling; public key
   sets stop at 2021 and 2024+ packages fail checksum verification
3. **Flash it** — signature + anti-rollback, no root, no adb, no writable channel

All three are missing → **not feasible with public means**.

Practical options: **buy Goggles 3 for O3**, or **swap the air unit to O4** (officially
supported by N3).

---

## Reproduce

```bash
pip install pycryptodome brotli pyusb pyelftools capstone

# 1. container structure + IMaH header
python tools/imah_tar.py V01.00.0200_zv902_dji_system.bin

# 2. rebuild ext4 (brotli first, then transfer-list v4 with end-exclusive ranges)
python -c "import brotli;open('system.new.dat','wb').write(brotli.decompress(open('system.new.dat.br','rb').read()))"
python tools/sdat2img_v4.py system.transfer.list system.new.dat system.img

# 3. browse without mounting (sparse-file safe)
python tools/ext4_read.py system.img ls /
python tools/ext4_read.py system.img cat /etc/wlm_cfg.json

# 4. DUML against a real device (64-bit libusb0.dll required)
python tools/duml_probe.py --dll C:\path\to\libusb0.dll --iface 4
```

---

## Layout

```text
docs/firmware-format.md   container layers and the G3/N3 difference (with hexdumps)
docs/filesystem.md        transfer-list pitfalls, file inventory, wlm_cfg excerpt
docs/link-stack.md        libwlm.so: symbols, disassembly, what it does and does not gate
docs/n3-followup.md       digging further into N3: plaintext GFSK firmware, all six UFIE keys fail
docs/debug-surface.md     debug surface: ro.debuggable=1, root services, TBIE-encrypted boot chain, SD switches
docs/device-probe.md      USB / RNDIS / FTP / DUML session logs
docs/assets/compat.svg    one-page comparison diagram
docs/announcement.md      ready-to-paste posts (EN for Reddit/rcgroups, plus a Chinese version)
evidence/                 raw evidence: release-note JSON, header hexdumps, symbol table, DUML log
tools/imah_tar.py         tar members + IMaH header parser
tools/sdat2img_v4.py      Android block-OTA transfer list v4 → ext4
tools/ext4_read.py        minimal ext4 reader (ls / cat / find, sparse-safe)
tools/duml_probe.py       DUML handshake and command sweep
```

中文版: [README.md](README.md)

---

## Notes

- Scope: interoperability research on hardware I own and its publicly distributed firmware.
- No firmware, keys, or signature-bypass code is included.
- No writes were performed on the device; all probing was read-only.
- Not affiliated with DJI. `DJI`, `Goggles`, `O3/O4 Air Unit` are trademarks of SZ DJI Technology.

## References

- [DJI Goggles N3 specs](https://www.dji.com/cn/goggles-n3/specs)
- [Goggles 3 firmware v01.00.0300 notes](https://droneland.be/blog/dji-goggles-3-firmware-update-25-07-2024)
- [O3 vs O4 transmission (2T2R → 2T4R, 60 MHz / 60 Mbps)](https://www.heliguy.com/blogs/knowledge-base/compared-to-the-o3-video-transmission-of-dji-avata-what-are-the-improvements-of-the-o4-video-transmission-of-dji-avata-2/)
- [Goggles N3 teardown (4 antennas, S2/E3T platform)](https://greyarro.ws/t/dji-goggles-n3-rumours-leaks-gossip-and-general-discussion/85405/51)
- [dji-firmware-tools](https://github.com/o-gs/dji-firmware-tools)
- [DankDroneDownloader](https://github.com/cs2000/DankDroneDownloader)
