#!/usr/bin/env bash
# 四模型 × 四子集全量跑测（PC 端）
# 每个模型：kill 旧服务 → 冷启动计时 → 四子集 → 内存峰值 → 换下一个
# 产物：eval/reports 下的 run 目录 + 本目录 03-内存采样 / 04-冷启动

set -u

BASE="D:/Users/34919/Desktop/武研/1-AI/2-技术内参/2026/20261022端侧部署/实验-20261116-补充数据"
HARNESS="D:/Users/34919/Desktop/武研/1-AI/2-技术内参/2026/20261022端侧部署/JSNC202611/edge-harness-poc"
LLAMA="C:/Users/34919/llama.cpp"
PY="C:/Users/34919/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
PORT=8080
EP="http://127.0.0.1:${PORT}/v1"

MODELS=(
  "Qwen3-1.7B-Q8_0.gguf:qwen3-1.7b-q8:17b-q8"
  "Qwen3-1.7B-Q4_K_M.gguf:qwen3-1.7b-q4:17b-q4"
  "Qwen3-4B-Instruct-2507-Q4_K_M.gguf:qwen3-4b-q4:4b-q4"
  "Qwen3-4B-Instruct-2507-Q8_0.gguf:qwen3-4b-q8:4b-q8"
)

MEM_CSV="$BASE/03-内存采样/rss_peak.csv"
COLD_TXT="$BASE/04-冷启动/cold_start.csv"
[[ -f "$MEM_CSV" ]] || echo "model,working_set_mb,peak_working_set_mb" > "$MEM_CSV"
[[ -f "$COLD_TXT" ]] || echo "model,load_seconds" > "$COLD_TXT"

stop_server() {
  taskkill //F //IM llama-server.exe >/dev/null 2>&1
  sleep 1
}

start_server() {   # $1=模型文件
  local mf="$1"
  ( cd "$LLAMA" && ./llama-server.exe -m "models/$mf" -c 8192 --port "$PORT" \
      --host 127.0.0.1 -fa on --reasoning off --parallel 1 \
      > "$BASE/04-冷启动/${mf%.gguf}.log" 2>&1 & )
}

wait_health() {
  for _ in $(seq 1 240); do
    if curl -s --max-time 2 "http://127.0.0.1:${PORT}/health" 2>/dev/null | grep -q '"ok"'; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

for entry in "${MODELS[@]}"; do
  IFS=':' read -r mf tag short <<< "$entry"
  echo "=== $(date +%H:%M:%S) $mf ($tag) ==="

  stop_server
  t0=$(date +%s)
  start_server "$mf"
  if ! wait_health; then
    echo "!! $mf 启动失败，跳过"
    continue
  fi
  t1=$(date +%s)
  echo "$tag,$((t1 - t0))" >> "$COLD_TXT"
  echo "   冷启动 $(($(t1 - t0)))s"

  for subset in intent faq mask tool; do
    echo "   -> $subset"
    ( cd "$HARNESS" && "$PY" eval/run_eval.py --backend openai --endpoint "$EP" \
        --subset "$subset" --model "$tag" ) 2>&1 | tail -1
  done

  mem=$(powershell -NoProfile -Command \
      "\$p = Get-Process llama-server -ErrorAction SilentlyContinue; if (\$p) { '{0:N0},{1:N0}' -f (\$p.WorkingSet64/1MB), (\$p.PeakWorkingSet64/1MB) }" 2>/dev/null | tr -d '\r')
  echo "$tag,$mem" >> "$MEM_CSV"
  echo "   内存(WS,Peak MB): $mem"
done

stop_server
echo "=== 全部完成 $(date +%H:%M:%S) ==="
