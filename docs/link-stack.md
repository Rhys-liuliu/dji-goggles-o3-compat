# 链路栈静态分析：libwlm.so

目标：确认"O3 兼容性"是否存在于链路库里，以及它是怎么被表达的。

先说工具情况：本机 REA 的 Ghidra provider 不可用（`application.properties` 缺失、JDK 路径失效），
且 Windows 版 Ghidra P0 只接受 PE、不接受 ARM64 ELF；Hopper 是 macOS 专属；IDA/Kuna 未配置。
所以这里用 **pyelftools + capstone** 做符号、字符串与反汇编级分析——
能到"函数级行为"，不到"完整反编译"。

> 结论先说：`libwlm.so` 里**没有**机型兼容白名单，也没有 `o3/o4/wm1695` 之类的字符串。
> 它只做三件事：**按数字 id 认设备**、**按配置起链路**、**维护对端设备列表**。
> 兼容性判定在更上层，最终仍被 N3 的加密+签名挡住。

---

## 1. 文件事实

```text
libwlm.so   AArch64, ELF64, 405,504 B（在镜像里是稀疏文件：extent 0 覆盖块 0..82，
            extent 1 从块 95 起，中间 12 块是空洞——按顺序拼接会得到 356 KB 的残文件）
.dynsym     12,024 B → 500 个具名符号，其中 475 个 STT_FUNC（未 strip 掉动态符号）
.gnu_debugdata  1,624 B（xz）→ 内部 .symtab 再有 68 个 FUNC
.text       195,496 B
.rodata      87,688 B
```

`.gnu_debugdata` 是 Android 的 mini-debug-info：即使没有 `.symtab`，也能还原一批函数名。
本项目 `tools/ext4_read.py` 已经按**逻辑块号**落位（空洞补零），否则读出来就是残文件——
这一点也解释了为什么第一次解出来的 ELF 节头表偏移（0x402000）会超出文件长度。

## 2. 符号画像（477 个函数里挑出 47 个与链路相关）

```text
设备/身份
  wlm_get_product_model_num            取"产品型号数字"
  switch_str_to_module_id              字符串 → 模块 id（"sdr" / "lte" / "wifi" …）
  wlm_share_info_read_dev_info         读共享的"对端设备信息"
  wlm_share_info_write_dev_info_list   写对端设备列表

链路开关
  libwlm_link_channel_active / deactive
  libwlm_link_special_param_active / deactive
  libwlm_share_liveview_link_mode
  libwlm_share_data_lk_mode / cmd_lk_mode / lv_lk_mode

选路与融合
  hybrid_lte_sdr_select_strategy       SDR / LTE 混合选路
  libwlm_share_fusion_mode_bool_use_sdr / _use_lte / _use_agent

通道初始化（都是 v1/v2 各一套 = 两代链路并存）
  lv_lte_sdr_send_v1_init / lv_lte_sdr_recv_v1_init / lv_lte_sdr_recv_v2_init
  dl_lte_sdr_send_v1_init

配置
  libwlm_get_config_file_name → 实测字符串 /system/etc/wlm_cfg.json
  libwlm_print_config_info
```

## 3. 三个函数的实际行为

### 3.1 `wlm_get_product_model_num`：一次查表

```asm
00026438  adrp  x8, #0x6f000
0002643c  ldr   x8, [x8, #0xb28]     ; 取一个全局指针（GOT 重定位）
00026440  and   w9, w0, #0xff        ; 入参就是一个小整数下标
00026444  ldrb  w0, [x8, w9, uxtw]   ; 返回 table[idx] —— 单字节
00026448  ret
```

**解读**：机型身份是**一张字节表 + 下标**，不是字符串比较。
所以想"让某种眼镜被认为支持某机型"，改动点不是在这里改字符串，而是改**上层用哪个下标、
以及那张表的内容**。这也解释了为什么全盘扫不到 `wm1695` 这类字样。

### 3.2 `libwlm_link_channel_active`：按句柄偏移激活通道

```asm
0000f5ac  mov   x20, x0
0000f5b4  mov   w9, #0xb1c8
0000f5b8  add   x21, x1, x9          ; x1 + 0xb1c8：实例里的链路上下文
0000f5bc  add   x19, x2, #0xc
0000f5c0  add   x22, x2, #0x98       ; 通道参数结构
0000f5c8  adrp  x23, #0x3c000
0000f5cc  add   x23, x23, #0xeec     ; 指向 .rodata 里的字符串（日志/键名）
```

**解读**：链路激活是"给定实例 + 通道号 → 打开对应物理链路"。
没有任何"这个机型允许不允许"的判断——**它执行，不决策**。

### 3.3 `wlm_share_info_read_dev_info`：对端设备列表

函数开头就是对入参判空（`cbz x19, #…`），随后从共享内存/共享结构里读 dev_info。
配合 `wlm_share_info_read_link_mode` / `write_dev_info_list`，
可以确定这套设计是：**每个链路实例维护一张"对端设备表"**，表里有 device type、
link mode、SDR 连接状态等字段，后续按这些字段选路。

## 4. `.rodata` 里值得记的字符串

```text
/system/etc/wlm_cfg.json        ← 配置路径（与前面读到的那份 JSON 对应）
/dev/wl_venc0..3                 ← 编码器节点
/dev/wl_ion, /dev/wl_ion0..3     ← ION 内存
:%s, peer_path:%s, sock_type:%d, txbuffer_size:%d, rxbuffer_size:%d
Channel   Link Mode   Bandwidth (kbps)      ← 调试打印表头
bool_use[sdr: %d, lte: %d]                  ← 选路状态
```

全部 1,804 条可打印字符串里，`o3` / `o4` / `wm1695` / `ocusync` / `air_unit` **均为 0**。

## 5. 这意味着什么

1. **兼容性不是这张库里的一个开关**。链路库只负责"认数字 id、按配置开链路、维护对端表"。
2. 真正决定"能不能和 O3 Air Unit 通"的逻辑在**更上层**——`/bin/dji_glasses`、
   图传服务、以及 `libwlm` 之外的协商代码；它按 device type 数字做分支。
3. 因此"给 N3 加 O3"不是改一个 JSON、一个函数指针表，而是**补一套链路能力 + 让上层认这个对端**。
   这需要完整反编译（Ghidra/IDA）才能定位，而就算定位到了，N3 的固件仍然：
   `UFIE` 加密 + 加扰 + 签名 + 反回滚。

## 6. 复现

```bash
pip install pyelftools capstone
python - <<'PY'
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
e = ELFFile(open("libwlm.so","rb"))
dyn = e.get_section_by_name(".dynsym")
print([s.name for s in dyn.iter_symbols() if s["st_info"]["type"]=="STT_FUNC"][:20])
PY
```

> ⚠ 从 ext4 镜像里取 `libwlm.so` 时记得处理稀疏文件（本仓库 `tools/ext4_read.py` 已修）。

## 7. 下一步（如果要继续）

- 装好 Ghidra 或 IDA，对 `wlm_share_info_read_dev_info` 的调用方做交叉引用，
  找出"按 device type 选 link mode"的那处 `cmp`/跳表；
- 用 G3 的 `dji_glasses` 与 `libwlm` 的字符串做对照，确认 O3 相关分支的关键词；
- 但这一切**只对 G3 有效**——N3 的对应二进制是加密的，拿不到同一份东西来对比。
