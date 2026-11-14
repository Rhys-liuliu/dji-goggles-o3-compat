# 固件容器结构：G3 vs N3

两代眼镜的固件是**同一套容器格式**，差异只在主模块是否加密。

## 分层

```
<产品>_dji_system.bin                 ← 外层 tar（ustar，128 字节头 + 512 字节块）
├── zv902.cfg.sig                     ← 配置清单模块（IMaH / type=CNFG / name=0000）
├── zv902_2803_<ver>_<date>.pro.fw.sig ← CPLD
├── zv902_1403_<ver>_<date>.pro.fw.sig ← GFSK（2.4G 信令射频）
└── zv902_2805_<ver>_<date>.ar0.pro.fw.sig ← 主固件
        └── IMaH 头 (224B) + 签名 + payload
                └── payload = ZIP（Android block-OTA 包）
```

外层 tar 是标准 ustar：文件名字段直接可读（`zv902.cfg.sig`），
大小字段是 11 位八进制（`0000666` 这类），不用猜格式。

## IMaH 头（主固件 2805）

`dji_imah_fwsig.py --version` 之类工具能直接打印；关键字段：

| 偏移 | 字段 | G3 `zv902` 2805 | N3 `zv300` 2805 |
|---|---|---|---|
| 0x00 | magic | `IM*H` | `IM*H` |
| 0x04 | header_version | 2 | 2 |
| 0x08 | size | 239,181,216 | ~295,949,920 |
| 0x18 | header_size | 224 | 224 |
| 0x1C | signature_size | 384 | 384 |
| 0x20 | payload_size | 239,180,608 | 295,949,312 |
| 0x28 | auth_alg | 3 | 262147 |
| 0x2C | auth_key | `PRAK` | `PRAK` |
| 0x34 | enc_key | **`\0\0\0\0`（空）** | **`UFIE`** |
| 0x38 | scramble_key | 全 0 | 16 字节非零 |
| 0x50 | name | `2805` | `2805` |
| 0x58 | type | `ZV90` | `ZV30` |

`enc_key` 为空、`scramble_key` 全 0 时，payload **原样可读**；N3 两者都非空，
payload 熵实测 8.00，且 `dji_imah_fwsig.py` 用公开的 `UFIE-2021-08` 等密钥校验失败
（`Decrypted chunks checksum verification failed`）——说明 2024+ 已换钥匙。

## 模块清单（cfg 是明文 XML）

`zv902.cfg.sig` 解出来就是一份 XML，可直接读：

```xml
<?xml version="1.0" encoding="utf-8"?>
<dji>
  <device id="zv902">
    <firmware formal="01.00.0200">
      <release version="01.00.0200" antirollback="0" from="2024/05/28" ...>
        <module id="2805" version="10.00.20.69" name="ZV902_E3T" upgrade_order="1"
                size="239181216" md5="2da526600a9224fd459a3771eede7ec0"
                md5_unsign="4475eb9765525b43bb97d4bf91f11fd6">…fw.sig</module>
        <module id="1403" version="48.00.00.80" name="ZV902_GFSK" …/>
        <module id="2803" version="22.11.11.52" name="CPLD" …/>
      </release>
    </firmware>
  </device>
</dji>
```

要点：

- `name="ZV902_E3T"` —— 主固件绑定的 SoC 平台是 **E3T**
- `antirollback="0"` —— 这一版没有反回滚限制
- 每个模块都带 `md5`（签名包）与 `md5_unsign`（解签名后），可用于校验自己的解包结果

> 注意：cfg 里只有"怎么升级"，没有"支持哪些机型"。兼容性白名单不在这里。

## Android OTA 层

主固件 payload 头 4 字节是 `50 4b 03 04`（ZIP）。条目：

```text
system.patch.dat        0            ← 0 字节 = 全量包，非增量
vendor.patch.dat        0
META-INF/com/android/metadata
META-INF/com/google/android/update-binary
META-INF/com/google/android/updater-script
bootarea.img            1.17 MB
normal.img              31.8 MB
scp.img                 97 KB
tos.img                 515 KB
system.new.dat.br       185.8 MB
system.transfer.list
vendor.new.dat.br       19.7 MB
vendor.transfer.list
compatibility.zip       VINTF 清单（4 份 XML）
```

`metadata` 原文（G3 v01.00.0200）：

```text
ota-type=BLOCK
post-build=e3t/e3t_zv902/e3t_zv902:9/PD1A.180720.031/13497:userdebug/test-keys
pre-device=e3t_zv902
post-sdk-level=28
```

`userdebug` + `test-keys` 说明这是**开发版签名**的 Android 9 构建。

## 结论

- 容器格式、模块划分、升级顺序两代一致 → 是同一条产品线的裁剪，不是两套东西
- 唯一的结构性差异：**主固件是否加密**
- 因此"研究 G3 得出的兼容性结论"在原理上可以迁移到 N3，
  但**没法把代码搬进去**——N3 的镜像连读都读不到
