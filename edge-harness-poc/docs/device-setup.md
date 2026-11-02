# 设备初始化 Checklist（每台设备一份，完成后归档到本目录）

> 对应设计文档 4.4.1。两台设备分别建档：`mid.md`（中端主力）/ `flagship.md`（旗舰对照）。

## 基础信息（D1 填写）

| 项 | 中端机（mid） | 旗舰机（flagship） |
|---|---|---|
| 型号 | **一加 Ace 2（PHK110，16GB 版）** ★实际测试机 | 待采购（12GB+，骁龙 8 Elite 档） |
| Android 版本 | 16（SDK 36） | |
| RAM/存储 | 16GB / 256GB（可用约 35GB） | |
| SoC | 骁龙 8+ Gen1（SM8475 / taro，2022 旗舰） | |

> **与计划 mid 档的偏差说明**（2026-10-22 D1 建档，adb 序列号 `2cf13583`）：
> 原计划 mid 档为 8GB RAM / 骁龙 8s Gen3 档。实际测试机为 16GB + 2022 旗舰 SoC 的
> "大内存、老旗舰"组合：① 内存余量充足，"4B-Q4 贴内存红线"的担忧大幅缓解；
> ② SoC/NPU（Hexagon，8+ Gen1）弱于 8s Gen3/8 Elite，**MNN 后端以 CPU/GPU 为主，
> NPU 后端留待 D3 专项验证，勿默认可用**；③ Android 16 很新，MNN 兼容性在 D2/D3 验证。

## 初始化步骤（D1 执行）

- [x] 开发者选项 + USB 调试开启；`adb devices` 可见（2026-10-22，序列号 `2cf13583`，授权完成）
- [ ] 关闭系统自动更新
- [ ] 关闭电池优化/后台冻结对本项目进程的影响（设置白名单）
- [ ] 固定屏幕亮度；关闭省电模式
- [ ] 安装 MNN-Chat APK（仅演示用，不承担评测）
- [x] 探测温度节点：`adb shell "cat /sys/class/thermal/thermal_zone*/type"` 与 `.../temp`，
      记录 CPU 对应的 zone 编号 →（填入下行）
  - CPU 温度节点：mid = `/sys/class/thermal/thermal_zone25/temp`（类型 `cpuss-0`，实测可读、当前 39.6°C；
    备用 `thermal_zone67` 类型 `socd` 恒返回 0，不可用。本机共 89 个热区）
- [x] 记录 dumpsys 可用性：`dumpsys meminfo` ✓ / `dumpsys batterystats` ✓ / `dumpsys thermalservice` ✓（均可用）

> 注：剩余未勾选项均为手机端手动操作（无法经 adb 远程完成），建议正式测量前由人工逐项设置。

## 测量前基线（每次正式测量执行）

- [ ] 静置降温至初始温度 ±1°C（记录基线温度）
- [ ] 电量 50–80%，插电状态全程统一（建议不插电）
- [ ] 清理后台（`adb shell am kill-all` 或重启后仅保留必要进程）
- [ ] 飞行模式开关状态与当次 run_id 一起记录（飞行模式 = 正式口径）
