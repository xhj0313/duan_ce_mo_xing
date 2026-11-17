#!/usr/bin/env bash
# 真机测试一键脚本（手机上线后运行；本脚本本身不会启动真机服务）
#
# 前置条件（需在 Termux 里手工做一次）：
#   cd ~/llama.cpp
#   ./llama-server -m models/Qwen3-1.7B-Q8_0.gguf -c 4096 \
#       --host 0.0.0.0 --port 8081 -fa on --reasoning off --parallel 1
#   注意：真机必须 --host 0.0.0.0，否则 PC 连不上；--parallel 1 是硬约束。
#
# 用法：
#   bash run_device.sh 192.168.100.185        # 指定 IP
#   bash run_device.sh                         # 自动扫历史 IP
#
# 产物：14-真机/<IP>/ 下每子集独立 run；不覆盖 PC 数据。

set -u
BASE="D:/Users/34919/Desktop/武研/1-AI/2-技术内参/2026/20261022端侧部署/实验-20261116-补充数据"
HARNESS="D:/Users/34919/Desktop/武研/1-AI/2-技术内参/2026/20261022端侧部署/JSNC202611/edge-harness-poc"
PY="C:/Users/34919/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
PORT=8081
HISTORY_IPS="192.168.100.185 192.168.104.33 192.168.100.252"

probe() {   # $1=ip -> 0 if /health ok
  curl -s --max-time 3 "http://$1:${PORT}/health" 2>/dev/null | grep -q '"ok"'
}

IP="${1:-}"
if [[ -z "$IP" ]]; then
  echo "=== 扫描历史真机端点 :$PORT ==="
  for c in $HISTORY_IPS; do
    if probe "$c"; then IP="$c"; echo "  命中 $c"; break; fi
    echo "  $c 无响应"
  done
fi
[[ -z "$IP" ]] && { echo "未找到在线设备。请在手机 Termux 启动 llama-server 后重试，或传入正确 IP。"; exit 1; }

EP="http://${IP}:${PORT}/v1"
echo "=== 设备 $IP ==="
MODEL=$(curl -s --max-time 3 "http://${IP}:${PORT}/props" 2>/dev/null | grep -o '"model_path":"[^"]*"' | head -1)
echo "  模型: $MODEL"
echo "  提示：真机应只跑 1.7B-Q8（4B 按要求仅 PC）"

OUT="$BASE/14-真机/$IP"
mkdir -p "$OUT"

for subset in intent faq mask tool; do
  echo "  -> $subset"
  ( cd "$HARNESS" && "$PY" eval/run_eval.py --backend openai --endpoint "$EP" \
      --subset "$subset" --model "device-1.7b-q8" --device mid ) 2>&1 | tail -1
done

echo "=== 判分（按子集分别取最新 run）==="
for subset in intent faq mask tool; do
  LATEST=$(ls -dt "$HARNESS"/eval/reports/*device-1.7b-q8_${subset}_* 2>/dev/null | head -1)
  [[ -z "$LATEST" ]] && { echo "  $subset 无 run，跳过"; continue; }
  R=$(basename "$LATEST")
  echo "  $subset -> $R"
  case $subset in
    intent) J="rule_judge.py --run $R" ;;
    faq)    J="faq_judge.py --run $R --mode v2" ;;
    mask)   J="mask_judge.py --run $R" ;;
    tool)   J="tool_judge.py --run $R" ;;
  esac
  ( cd "$HARNESS" && "$PY" eval/judges/$J ) > "$OUT/${subset}_judge.txt" 2>&1
done
echo "=== 完成，产物在 $OUT ==="
echo "注：真机 timings 需 adapter_openai.py 已保留 calls 字段（本轮已改）；内存/温升需另跑 dumpsys。"
