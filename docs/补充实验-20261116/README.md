# 实验-20261116-补充数据

对应《待补数据清单》的 PC 侧可执行项。4B 模型按要求**只在 PC 端运行**，未上真机。

## 目录

| 目录 | 对应清单项 | 内容 |
|---|---|---|
| `00-汇总/` | 全部 | 总报告（本目录 `README.md` 为索引）、口径说明、结论 |
| `01-性能与timings/` | #1 #4（速度维度） | `per_call.csv`（逐次调用）、`summary.csv`（模型×子集聚合） |
| `02-量化速度对照/` | #4 | `quant_speed.csv`：同系列 Q4 vs Q8 的 tok/s 与墙钟对照 |
| `03-内存采样/` | #9（PC 版） | `rss_peak.csv`：llama-server 进程工作集与峰值 |
| `04-冷启动/` | #10（PC 版） | `cold_warm.csv`：每模型 1 冷 + 4 热启动耗时 |
| `05-载荷审计/` | #12 | `payload_audit.csv/json`：出端文本字节数与残留 PII（按实体类型） |
| `06-变体切片/` | #7 | `variant_tagged.csv`、`variant_accuracy.csv`（启发式打标） |
| `07-拦截集/` | #8 | `guard_*.jsonl/json`：30 条恶意 + 30 条正常的拦截率与误拦率 |

## 脚本

| 脚本 | 作用 |
|---|---|
| `run_all_models.sh` | 四模型 × 四子集串行跑测（含冷启动与内存记录） |
| `summarize_perf.py` | 从 `eval/reports` 抽取 calls，生成性能 CSV |
| `audit_payload.py` | 载荷审计（金标实体比对，非正则） |
| `variant_slice.py` | 语言变体启发式打标与分项统计 |
| `build_guard_set.py` | 生成 60 条拦截/正常对照集 |
| `run_guard.py` | 跑拦截集并统计拦截率/误拦率 |
| `bench_coldstart.py` | 冷/热启动单独测量（更精确，替代 run_all_models 内的粗略记录） |

## 复现

```bash
# 1) 全量跑测（约 100 分钟，四模型）
bash run_all_models.sh

# 2) 性能汇总
python summarize_perf.py

# 3) 离线项（不占模型）
python audit_payload.py
python variant_slice.py

# 4) 冷启动（需模型空闲）
python bench_coldstart.py

# 5) 拦截集（需模型空闲）
python build_guard_set.py
python run_guard.py --model qwen3-4b-q4 --endpoint http://127.0.0.1:8080/v1
```

## 口径与注意事项

1. **prompt cache 影响**：llama-server 会复用相同前缀的 KV。同一子集内第 1 条是完整 prefill（1.7B 约 1621 token / 16 s），
   之后每条只需 prefill 增量（12–16 token）。因此：
   - `prefill_tps` 的中位数反映的是**增量 prefill**，不是模型 prefill 能力；
   - 冷启动的完整 prefill 见 `summary.csv` 的 `cold_prompt_ms` 列；
   - 报告谈"TTFT"时必须区分冷/热两种情形。
2. **±3pt 噪声纪律**仍适用，跨模型比较不得以 <3pt 差异下结论。
3. **内存为 PC 进程口径**（Windows 工作集），不等于真机可用内存；4B 的 3.5 GB 外推值仍需真机验证。
4. **变体标签为启发式**（规则匹配），非人工标注，只用于看趋势。
5. 原始逐条输出仍在 `JSNC202611/edge-harness-poc/eval/reports/20261116_*`，本目录 CSV 为其派生视图。
