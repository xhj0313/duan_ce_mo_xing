#!/usr/bin/env bash
# 拦截集批量跑测：对指定模型启动服务 → 跑 60 条 guard → 关闭
# 用法：bash run_guard_all.sh qwen3-1.7b-q8 qwen3-4b-q4

set -u
BASE="D:/Users/34919/Desktop/武研/1-AI/2-技术内参/2026/20261022端侧部署/实验-20261116-补充数据"
LLAMA="C:/Users/34919/llama.cpp"
PY="C:/Users/34919/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
PORT=8080

declare -A FILES=(
  [qwen3-1.7b-q8]="Qwen3-1.7B-Q8_0.gguf"
  [qwen3-1.7b-q4]="Qwen3-1.7B-Q4_K_M.gguf"
  [qwen3-4b-q4]="Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
  [qwen3-4b-q8]="Qwen3-4B-Instruct-2507-Q8_0.gguf"
)

for tag in "$@"; do
  mf="${FILES[$tag]}"
  echo "=== $(date +%H:%M:%S) $tag ==="
  taskkill //F //IM llama-server.exe >/dev/null 2>&1
  sleep 1
  ( cd "$LLAMA" && ./llama-server.exe -m "models/$mf" -c 8192 --port "$PORT" \
      --host 127.0.0.1 -fa on --reasoning off --parallel 1 >/dev/null 2>&1 & )

  ok=0
  for _ in $(seq 1 400); do
    if curl -s --max-time 1 "http://127.0.0.1:${PORT}/health" 2>/dev/null | grep -q '"ok"'; then
      ok=1; break
    fi
    sleep 0.1
  done
  if [[ "$ok" != "1" ]]; then echo "  !! 启动失败"; continue; fi

  ( cd "$BASE" && "$PY" run_guard.py --model "$tag" --endpoint "http://127.0.0.1:${PORT}/v1" )
done

taskkill //F //IM llama-server.exe >/dev/null 2>&1
echo "=== guard 完成 ==="
