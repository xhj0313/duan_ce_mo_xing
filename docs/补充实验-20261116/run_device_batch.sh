#!/usr/bin/env bash
# 真机分批续跑：每批 25 条，批前探活，按 seq 自动补洞。
# 用法：bash run_device_batch.sh 192.168.100.185 faq mask tool

set -u
BASE="D:/Users/34919/Desktop/武研/1-AI/2-技术内参/2026/20261022端侧部署/实验-20261116-补充数据"
HARNESS="D:/Users/34919/Desktop/武研/1-AI/2-技术内参/2026/20261022端侧部署/JSNC202611/edge-harness-poc"
PY="C:/Users/34919/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
IP="${1:?需要设备 IP}"; shift
SUBSETS="${*:-faq mask tool}"
EP="http://${IP}:8081/v1"
BATCH=25

alive() { curl -s --max-time 4 "http://${IP}:8081/health" 2>/dev/null | grep -q 'ok'; }

total_of() {   # 非 dev 条目数
  "$PY" - "$1" <<'PY'
import json,sys
n=0
for line in open(sys.argv[1],encoding='utf-8'):
    if not line.strip(): continue
    r=json.loads(line)
    if r.get('split')=='dev': continue
    n+=1
print(n)
PY
}

for subset in $SUBSETS; do
  DS="$HARNESS/eval/datasets/${subset}.jsonl"
  TOTAL=$(total_of "$DS")
  echo "=== $subset（共 $TOTAL 条）==="
  RUN=""
  round=0
  while :; do
    round=$((round+1))
    if ! alive; then echo "  !! 设备离线，停止 $subset（已完成部分保留）"; break; fi
    if [[ -z "$RUN" ]]; then
      DONE=0
    else
      DONE=$("$PY" "$BASE/count_done.py" "$HARNESS/eval/reports/$RUN/raw.jsonl")
    fi
    if [[ "$DONE" -ge "$TOTAL" ]]; then echo "  完成 $DONE/$TOTAL"; break; fi
    echo "  第 $round 批：已有 $DONE/$TOTAL，跑 $BATCH 条 $(date +%H:%M:%S)"
    if [[ -z "$RUN" ]]; then
      OUT=$( cd "$HARNESS" && timeout 600 "$PY" eval/run_eval.py --backend openai \
          --endpoint "$EP" --subset "$subset" --model device-1.7b-q8 --device mid \
          --limit $BATCH 2>&1 | grep -o 'reports[\\/][^ ]*' | head -1 )
      RUN=$(ls -dt "$HARNESS"/eval/reports/*device-1.7b-q8_${subset}_* 2>/dev/null | head -1 | xargs -r basename)
    else
      ( cd "$HARNESS" && timeout 600 "$PY" eval/run_eval.py --backend openai \
          --endpoint "$EP" --subset "$subset" --model device-1.7b-q8 --device mid \
          --resume-run "$RUN" --limit $BATCH >/dev/null 2>&1 )
    fi
    [[ -z "$RUN" ]] && { echo "  !! 未生成 run，停止"; break; }
  done
done

echo "=== 汇总判分 ==="
for subset in $SUBSETS; do
  LATEST=$(ls -dt "$HARNESS"/eval/reports/*device-1.7b-q8_${subset}_* 2>/dev/null | head -1)
  [[ -z "$LATEST" ]] && continue
  R=$(basename "$LATEST")
  case $subset in
    intent) J="rule_judge.py --run $R" ;;
    faq)    J="faq_judge.py --run $R --mode v2" ;;
    mask)   J="mask_judge.py --run $R" ;;
    tool)   J="tool_judge.py --run $R" ;;
  esac
  ( cd "$HARNESS" && "$PY" eval/judges/$J ) > "$BASE/14-真机/$IP/${subset}_judge.txt" 2>&1
  echo "  $subset: $R"
done
echo "=== 全部结束 ==="
