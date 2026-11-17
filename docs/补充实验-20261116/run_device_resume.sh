#!/usr/bin/env bash
# 真机续跑：只跑剩余子集（intent 已完成，不重跑）
# 用法：bash run_device_resume.sh 192.168.100.185 faq mask tool

set -u
BASE="D:/Users/34919/Desktop/武研/1-AI/2-技术内参/2026/20261022端侧部署/实验-20261116-补充数据"
HARNESS="D:/Users/34919/Desktop/武研/1-AI/2-技术内参/2026/20261022端侧部署/JSNC202611/edge-harness-poc"
PY="C:/Users/34919/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
IP="${1:?需要设备 IP}"
shift
SUBSETS="${*:-faq mask tool}"
EP="http://${IP}:8081/v1"

if ! curl -s --max-time 3 "http://${IP}:8081/health" | grep -q ok; then
  echo "设备无响应，中止"; exit 1
fi
SLOTS=$(curl -s --max-time 3 "http://${IP}:8081/props" | grep -o '"total_slots":[0-9]*' | cut -d: -f2)
echo "=== 设备 $IP | total_slots=$SLOTS ==="
[[ "$SLOTS" != "1" ]] && { echo "!! 不是单槽，中止（数据会不可比）"; exit 1; }

OUT="$BASE/14-真机/$IP"
mkdir -p "$OUT"

for subset in $SUBSETS; do
  echo "--- $subset $(date +%H:%M:%S) ---"
  ( cd "$HARNESS" && "$PY" eval/run_eval.py --backend openai --endpoint "$EP" \
      --subset "$subset" --model "device-1.7b-q8" --device mid ) 2>&1 | tail -2
done

echo "=== 判分 ==="
for subset in $SUBSETS; do
  LATEST=$(ls -dt "$HARNESS"/eval/reports/*device-1.7b-q8_${subset}_* 2>/dev/null | head -1)
  [[ -z "$LATEST" ]] && { echo "  $subset 无 run"; continue; }
  R=$(basename "$LATEST")
  case $subset in
    intent) J="rule_judge.py --run $R" ;;
    faq)    J="faq_judge.py --run $R --mode v2" ;;
    mask)   J="mask_judge.py --run $R" ;;
    tool)   J="tool_judge.py --run $R" ;;
  esac
  ( cd "$HARNESS" && "$PY" eval/judges/$J ) > "$OUT/${subset}_judge.txt" 2>&1
  echo "  $subset -> $R 已判分"
done
echo "=== 完成 ==="
