#!/usr/bin/env bash
# 剩余 PC 专项实验调度（每项启停服务前都校验模型身份，防止口径错位）
set -u
BASE="D:/Users/34919/Desktop/武研/1-AI/2-技术内参/2026/20261022端侧部署/实验-20261116-补充数据"
PY="C:/Users/34919/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

start_and_wait() {   # $1=模型文件 $2=期望文件名片段
  taskkill //F //IM llama-server.exe >/dev/null 2>&1
  sleep 2
  ( cd "C:/Users/34919/llama.cpp" && ./llama-server.exe -m "models/$1" -c 8192 \
      --port 8080 --host 127.0.0.1 -fa on --reasoning off --parallel 1 >/dev/null 2>&1 & )
  for _ in $(seq 1 600); do
    M=$(curl -s --max-time 2 http://127.0.0.1:8080/props 2>/dev/null | grep -o "$2" | head -1)
    [ -n "$M" ] && { echo "  服务确认: $2"; return 0; }
    sleep 0.5
  done
  echo "  !! 服务未就绪"; return 1
}

echo "=== 多轮对话：1.7B-Q8 / 4B-Q4 ==="
start_and_wait "Qwen3-1.7B-Q8_0.gguf" "Qwen3-1.7B-Q8_0" && (cd "$BASE" && "$PY" run_multiturn.py --model qwen3-1.7b-q8)
start_and_wait "Qwen3-4B-Instruct-2507-Q4_K_M.gguf" "Qwen3-4B-Instruct-2507-Q4_K_M" && (cd "$BASE" && "$PY" run_multiturn.py --model qwen3-4b-q4)

echo "=== 内存峰值（4 模型）==="
for m in qwen3-1.7b-q8 qwen3-1.7b-q4 qwen3-4b-q4 qwen3-4b-q8; do
  (cd "$BASE" && "$PY" bench_mem_peak.py --only $m 2>&1 | tail -1)
done

echo "=== 20 轮耐久（2 模型）==="
(cd "$BASE" && "$PY" bench_endurance.py --model qwen3-1.7b-q8 --rounds 20 --per-round 8 2>&1 | tail -3)
(cd "$BASE" && "$PY" bench_endurance.py --model qwen3-4b-q4 --rounds 20 --per-round 8 2>&1 | tail -3)

echo "=== 配置敏感性 ==="
(cd "$BASE" && "$PY" bench_config.py 2>&1 | tail -2)

echo "=== 功耗代理 ==="
(cd "$BASE" && "$PY" bench_power.py --model qwen3-1.7b-q8 --seconds 45 2>&1 | tail -2)
(cd "$BASE" && "$PY" bench_power.py --model qwen3-4b-q4 --seconds 45 2>&1 | tail -2)

taskkill //F //IM llama-server.exe >/dev/null 2>&1
echo "=== 全部专项完成 ==="
