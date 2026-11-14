# 从 OTA 到可浏览的文件系统

G3 的 `system.new.dat.br` 解压后不是裸 ext4，而是**区块增量格式**：
`system.transfer.list` 给出"哪些块写什么"，`system.new.dat` 是顺序排列的块数据。
这一步错了，后面全是垃圾。

## transfer list v4 的坑：end 是**独占**

文件头 4 行：

```text
4                  # 版本
126156             # 头里记的块数（不是分区大小！）
0                  # stash
0
erase 6,680,2018,66049,69120,129155,157974
new 6,0,46,50,168,2530,3390
…
```

每条命令：`<cmd> <count>,<v1>,<v2>,…`，`count` 是后面数字的个数，
数字两两成对 `(start, end)`，**块数 = end - start**（end 独占）。

校准方法（别猜，直接对长度）：

```text
0100: 123,004 块 × 4096 = 503,824,384 B ≡ system.new.dat 实际大小  ✅
0200: 123,364 块 × 4096 = 505,298,944 B ≡ 实际大小                 ✅
```

如果按"end 包含"算，会多出几千块 → 读出短读（short read）、
镜像里 inode 表全零、ext4 superblock magic 有但目录是空的。
我第一次就是这么踩的。

## 重建结果

```text
system_0200.img   654,311,424 B   magic 0xEF53   sb_blocks 158,486   1,806 条目
vendor_0200.img   150,994,944 B   magic 0xEF53   sb_blocks  36,864
```

## 最小 ext4 读取器（不需要 root / mount）

纯 Python 就够，路径：

```text
superblock @1024
  ├ s_log_block_size(24) → block_size = 1024 << x
  ├ s_inode_size(88)
  └ s_feature_incompat(96) → 是否 64bit
group descriptor table @ (first_data_block+1) × block_size
  ├ bg_inode_table_lo(+8)  [+hi(+40) 若 64bit]
inode 表 = bg_inode_table × block_size + (ino-1) × inode_size
  ├ i_mode(0) i_size_lo(4) i_size_hi(108)
  └ i_block(40..100) → extent header magic 0xF30A
```

目录项：`inode(4) rec_len(2) name_len(1) type(1) name`，顺序扫。
文件：extent 树，depth=0 时直接 `(ee_start, ee_len)` 读块。

`tools/ext4_read.py` 实现了 `ls / cat / find`，够用来做这类固件排查。

## 读出来的东西

```text
/etc/device_table.json   device_name "E3T_ZV902", device_type "GLASS",
                         host_type "MASTER", rndis0_ip "192.168.60.2"
/etc/wlm_cfg.json        24,536 B，无线链路模块配置
/lib64/libwlm.so         356,352 B  链路主体
/lib64/libwlm_liveview.so / libwlm_log.so
/lib64/lib_hal_vtx.so    16,384 B   编码 HAL（不是链路）
/bin/dji_glasses         282,624 B  眼镜主服务
/bin/dji_gfsk_agent      2.4G 信令 agent
/bin/dji_fw_verify       固件校验
/lib/modules/dji_wl.ko, dji_codec_pm.ko, dji_hevc_enc.ko
/lib64/libdji_sec.so, libdji_secure.so, libdji_fw_verify_util.so
```

`/etc/wlm_cfg.json` 的 `common` 段（原文）：

```json
{
  "common": {
    "version": 4,
    "product": "ZV902",
    "soc": "e3t",
    "libwlm_module_id": "0x0e07",
    "role": "master",
    "sdr_enable": 1,  "sdr_agent_host_id": "0x0e00",
    "lte_enable": 1,  "lte_agent_host_id": "0x0e06",
    "wifi_enable": 1, "wifi_agent_host_id": "0x1b00",
    "local_router_host_id": "0x1c01",
    "peer_wlm_host_id": "0x0907",
    "local_wlm_host_id": "0x0e07",
    "sdrs_agent_host_id": "0x0e04",
    "enable_modules": { "dev_mgr": 1, "agt_mgr": 1, "link_sw": 1,
                        "link_state": 1, "cmd_fusion": 1, … }
  }
}
```

这是"链路怎么跑"的配置，**不是"支持哪些机型"的表**。

## 负结果（同样重要）

对整镜像（654 MB）做 UTF-8 与 UTF-16 扫描：

| 关键词 | 命中 |
|---|---|
| `wm1695`（O3 Air Unit 产品码） | **0** |
| `O3AU` / `O3_AU` / `ocusync` | **0** |
| `airunit` | 仅 `FlycontrolAirUnitStatusArmFlightMode`（协议字段名）与 `DuFormatSDMenuAirUnitFormatSD…`（UI 菜单） |
| `tkgs` | 0 |

`lib_hal_vtx.so` 里也全是编码器断言（`vtx_hal_convert_to_drv_param`），不是兼容表。

结论：**兼容性判定不在任何明文配置里**，而是在链路栈（`libwlm.so` / `dji_glasses`）
的二进制逻辑中，按**数字 device_type** 走——G3 侧 `dbus_pc.json` 里 peer 就是
`"dev_type":"0x12"` 这种数字码，而不是字符串。

想进一步定位，需要的是对 `libwlm.so` 做静态逆向（找 device_type 的比较分支），
而不是改 JSON。
