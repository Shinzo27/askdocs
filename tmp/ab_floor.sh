#!/bin/bash
# A/B the RRF floor on the metric that actually gates: citation accuracy.
# Runs the same 6 questions through the real API with the floor off, then on.
set -u
cd /Volumes/Work/projects/askdocs
export PATH=/opt/homebrew/bin:$PATH
export GENERATOR_PROVIDER=ollama
export OLLAMA_MODEL=qwen2.5:1.5b-instruct

if ! curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null; then
  echo "starting ollama"
  OLLAMA_KEEP_ALIVE=30m nohup ollama serve > /tmp/ollama.log 2>&1 &
  for _ in $(seq 1 40); do
    curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null && break
    sleep 2
  done
fi
echo "warming model"
curl -s http://localhost:11434/api/chat -d '{"model":"qwen2.5:1.5b-instruct","messages":[{"role":"user","content":"hi"}],"stream":false,"options":{"num_predict":1}}' >/dev/null

run_case() {
  local floor=$1 slots=$2 tag=$3
  echo "=== case $tag: RERANK_RRF_FLOOR=$floor slots=$slots"
  ( cd apps/api && RERANK_RRF_FLOOR=$floor RERANK_FLOOR_SLOTS=$slots \
      ../../.venv/bin/python -m uvicorn askdocs_api.main:app --host 127.0.0.1 --port 8000 \
      > /tmp/api-$tag.log 2>&1 ) &
  local wrapper=$!
  for _ in $(seq 1 40); do
    curl -s --max-time 2 -o /dev/null http://127.0.0.1:8000/healthz && break
    sleep 1
  done
  .venv/bin/python eval/e2e_eval.py --limit 10 --provider ollama --model "qwen2.5-1.5b-floor-$tag" 2>&1 | tail -14
  pkill -f "uvicorn askdocs_api.main:app" ; sleep 2
  wait $wrapper 2>/dev/null
}

run_case 0 0 off
run_case 1 3 on
echo "=== done"
