# 原始证据

这里放**可核对的原始材料**，都能与 `docs/` 里的结论一一对应。
全部是文本/元数据，**不含任何固件二进制**。

| 文件 | 来源 | 说明 |
|---|---|---|
| `release-notes-goggles3.json` | DJI Assistant 2 缓存 `firm_cache/2b3054…cache` | G3 官方版本历史：`01.00.0200`（2024-07-24）为 `Added support to use with DJI O3 Air Unit` |
| `release-notes-goggles-n3.json` | 同上 `firm_cache/b37d03…cache` | N3 十个版本，**零 O3 条目**；`01.00.0300` 加的是 O4 Air Unit |
| `imah_header_hexdump.txt` | G3 `2805` 头 + N3 `2805` 头，各 224 B | 逐字节对比：差异集中在 `0x2C enc_key` 与 `0x30..0x3F scramble_key` |
| `libwlm_symbols.txt` | `libwlm.so` 的 `.dynsym` + `.gnu_debugdata/.symtab` | 477 + 68 个函数符号及地址；`wlm_get_product_model_num` 等可直接定位 |
| `duml_session.log` | 真机 N3，interface 4，EP `0x04`/`0x85` | 完整 TX/RX hex、`zv300 gl Ver.02` 回包、0x82 广播、命令扫描结果 |
| `wlm_cfg-goggles3.json` | G3 `/system/etc/wlm_cfg.json` | 24.5 KB 链路配置原文（模块 id、SDR/LTE/WiFi host id、启用模块表） |

## 复现这些文件

```bash
# 版本历史：装 DJI Assistant 2，连一次对应设备，缓存即生成
ls "<install>/DJIEngine/DJIData/firm_cache/"

# 头对比
python tools/imah_tar.py V01.00.0200_zv902_dji_system.bin

# 符号表
pip install pyelftools
python -c "from elftools.elf.elffile import ELFFile; \
e=ELFFile(open('libwlm.so','rb')); \
print(len([s for s in e.get_section_by_name('.dynsym').iter_symbols() \
           if s['st_info']['type']=='STT_FUNC']))"

# DUML
python tools/duml_probe.py --dll C:\path\libusb0.dll --iface 4
```

## 说明

- 版本历史 JSON 是 DJI Assistant 自己缓存在本机的**发布元数据**（版本号、日期、变更说明），
  不是固件本体；
- `libwlm_symbols.txt` 是符号名与地址，不含代码字节；
- `wlm_cfg-goggles3.json` 是设备 `system` 分区里的**运行时配置**，用于说明链路模块结构；
  如果你所在司法辖区对厂商配置文件的再分发有疑虑，请只引用不复制。
