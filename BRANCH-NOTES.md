# 分支说明：feature/xhj

本分支是一次完整的上传快照，包含**代码 + 全部实验数据 + 全部分析文档**，用于复现与审计。

## 一、目录结构

```
docs/                              分析文档（42 份评测记录 + 6 份汇总）
  ├─ 分析-…端侧智能体验证工程.md      立项分析与阈值定义
  ├─ 总结-…harness优化阶段报告.md     阶段总结（采纳项/否决项/方法论）
  ├─ 实验汇总-JSNC202611.md          按指标展开的演进表与总账
  ├─ 真机两次全量对比-JSNC202611.md   11-03 vs 11-11 真机逐项对比
  ├─ 评测-01 / 评测-02               首轮四子集与真机验证报告
  └─ 评测记录/                       42 份单条实验记录（自动生成，可追溯到 run_id）

edge-harness-poc/
  ├─ harness/                        pipeline、prompts（含 intent_compact.j2）、adapter
  ├─ registry/                       意图注册表 + 15 张知识卡 + 工具定义
  ├─ eval/
  │   ├─ datasets/                   四套测试集（intent 910 / mask 800 / faq 91 / tool 30）
  │   ├─ judges/                     判分器（rule / faq v0-v4 / mask / tool）
  │   └─ reports/                    60 次运行的原始输出与判分结果（强制入库，供审计）
  ├─ experiments/
  │   ├─ results.jsonl               实验台账（append-only，含 commit/endpoint/run_id）
  │   ├─ schemes.yaml                方案池（26 个：动机/假设/风险/结论）
  │   ├─ run_experiment.py           登记实验 + 自动生成记录文档
  │   ├─ guardrails.py               回归护栏（7 组零模型调用断言）
  │   └─ export_summary.py           从台账导出汇总 md
  └─ tests/                          22 个单测
```

## 二、关键数字（当前 harness，PC 环境）

| 指标 | 阈值 | 1.7B | 4B-2507 |
|---|---|---|---|
| 脱敏 精度 P | ≥0.90 | 0.961 | 0.938 |
| 脱敏 召回 R | ≥0.95 | 0.961 | 0.957 |
| 工具 A/B/C/D | 0.8/0.8/1.0 | 1.0/0.875/1.0/1.0 | 1.0/1.0/1.0/1.0 |
| 意图 OOS 拒识 | ≥0.85 | 0.923 | 0.962 |
| 意图 macro-F1 | ≥0.90 | 0.866 | 0.899 |
| FAQ 信息点命中 | ≥0.80 | 0.606（v2）/ 0.654（v3） | 0.788（v2）/ 0.827（v3） |

> FAQ 有 v2（规则判分，默认）与 v3（LLM 证据化复核）两套口径，v3 系统性高 4-8pt。

## 三、复现方式

```bash
cd edge-harness-poc
python -m pytest tests/ -q          # 22 个单测
python experiments/guardrails.py    # 7 项回归断言（零模型调用）

# 启动本地模型服务（llama.cpp + GGUF），再跑任意子集：
python eval/run_eval.py --backend openai --endpoint http://127.0.0.1:8080/v1 --subset faq
python eval/judges/faq_judge.py --run <run_id> --mode v2
```

## 四、说明

1. `eval/reports/` 在项目 `.gitignore` 中被列为生成产物；本分支**强制入库**作为实验证据快照，
   后续新增运行不会自动纳入（需要时用 `git add -f`）。
2. 测试集为合成数据（LLM 改写扩增 + 人工抽检 + 盲标 κ≥0.8），**不含任何真实客户信息**；
   规范见 `edge-harness-poc/eval/datasets/README.md`。
3. 模型权重（*.gguf）不入库，需按 README 自行下载。
