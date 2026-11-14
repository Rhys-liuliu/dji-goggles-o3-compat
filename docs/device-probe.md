# N3 真机探测记录

设备：DJI Goggles N3（产品码 `ZV300`，固件侧 `type=ZV30`）。
目的：确认是否存在**可读/可写的调试通道**（有了才谈得上"改固件支持 O3"）。

结论先给：**没有**。设备只暴露"读版本"。

---

## 1. USB 枚举

```text
VID:PID  2CA3:0020
配置串   "rndis,mass_storage,bulk,acm"
接口
  MI_00   RNDIS            → 网络 192.168.60.2/24
  MI_02   Mass Storage     → 只映射 SD 卡（"Linux File-Stor Gadget"）
  MI_03…07  class 0xFF / sub 0x43 / proto 0x01，各带一对 bulk 端点
```

Windows 上这五个厂商接口被 DJI Assistant 装了 **libusb-win32** 驱动
（设备管理器里显示为 `MI03…MI07`）。

> Python 是 64 位，而 DJI 自带的 `libusb0.dll` 是 32 位。
> 解决办法：单独下 libusb-win32 1.4.0.2 的 **amd64** 版 `libusb0.dll`，
> 用 pyusb 的 `libusb0` 后端 + `--libusb-path` 指过去。

枚举到 5 个"设备"（libusb-win32 按接口绑定，每个 MI 各自成节点），
实际是同一台设备的不同接口。

## 2. RNDIS 网络

设备固定 `192.168.60.2`，但**不发 DHCP**（Windows 只能拿到 169.254 自动地址）。
手动设 `192.168.60.1/24` 后：

```text
ping 192.168.60.2   → 通
端口扫描 21/22/23/80/443/5555/5037/8080/9000/9090 …
  21 open   "220 Hello!"         ← dji_ftpd
  其余全关
```

FTP 尝试：

```text
anonymous:anonymous@   530
root:root              530
admin:admin            530
dji:dji                530
ftp:ftp                530
```

DJI 的 FTP 凭据由 DJI Fly 连接时下发，不是通用口令。

## 3. DUML（厂商 bulk 通道）

### 找出应答的那条接口

5 个接口逐个试 `GENERAL / cmd 0x01`（空负载），interface **4** 第一个回包：

```text
TX  55 0d 04 33 0a 00 00 00 00 00 01 3c 3c
```

包结构（13 字节，DUML v1）：

```text
55             magic
0d             length（含头尾校验）
04             protocol version
33             header CRC8 (poly 0x07, init 0)
0a 00          sender    type=0x0a (PC)  index=0
00 00          receiver  type=0x00 (ANY) index=0
00 00          sequence
01             flags（请求）
00             cmd_set = GENERAL
01             cmd_id  = 0x01
3c 3c          CRC8 / 尾校验
```

### 回包

```text
55 2b 04 58 3c 0a 00 00 80 00 01 00 12
   7a 76 33 30 30 20 67 6c 20 56 65 72 2e 30 32     ← "zv300 gl Ver.02"
   00 0f 43 00 0a 0f 43 00 0a 01 00 00 c0 7c e3
```

解读：

| 项 | 值 |
|---|---|
| 型号 | `ZV300` |
| 版本串 | `zv300 gl Ver.02` |
| 版本字段 | `0x0F43`（主）、`0x000A`（次），重复两组（A/B 分区一致） |

随后每 ~0.3 s 一条 `0x82` 心跳，负载里反复出现 `ZV300`：

```text
55 4d 04 a8 bc 2a e9 03 40 00 82 5a 56 33 30 30 00 … 05 1c 00 00 … 06 00 00 …
                                              "ZV300"        (0x051c)     (0x0006)
```

### 还有什么命令可用

`GENERAL cmd 0x02 … 0x0C` 逐个发（空负载，seq 递增）：

```text
cmd 0x02..0x07, 0x09..0x0C   → 只收到 0x82 心跳，无应答
cmd 0x08                     → 无任何数据
```

也就是说这个通道**只回身份/状态查询**，没有：

- 文件读写命令
- adb / 调试模式开关
- 参数写入（`FlycParam` 那套是给飞控用的，眼镜没有）

## 4. 结论

| 可能的入口 | 结果 |
|---|---|
| FTP 21 | 有服务，凭据未知（530） |
| adb 5555 / USB adb 接口 | 不存在 |
| SSH / HTTP / 其他端口 | 关闭 |
| SD 卡 | 可读，只有媒体与 `ham_cfg_support` 这类开关文件 |
| DUML | 可读版本，无写能力 |
| UART / JTAG | 未拆机，未尝试 |

**设备在手，也只能确认"你是谁、什么版本"，摸不到系统。**
再往下就只有硬件级手段（拆机 UART/JTAG），风险与收益完全不成比例。
