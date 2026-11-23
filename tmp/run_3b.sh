#!/bin/bash
# One isolated 3B run: unique port, PID-based kill, nothing else running.
# The two previous attempts died because another job pkill'd the shared :8000 server.
set -u
cd /Volumes/Work/projects/askdocs
export PATH=/opt/homebrew/bin:$PATH
export GENERATOR_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:3b-instruct OLLAMA_KEEP_ALIVE=30m
PORT=8124

if ! curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null; then
  nohup ollama serve > /tmp/ollama.log 2>&1 &
  for _ in $(seq 1 40); do curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null && break; sleep 2; done
fi
curl -s http://localhost:11434/api/chat -d '{"model":"qwen2.5:3b-instruct","messages":[{"role":"user","content":"hi"}],"stream":false,"options":{"num_predict":1}}' >/dev/null

( cd apps/api && exec ../../.venv/bin/python -m uvicorn askdocs_api.main:app --host 127.0.0.1 --port $PORT > /tmp/api-3b3.log 2>&1 ) &
API_PID=$!
for _ in $(seq 1 60); do curl -s --max-time 2 -o /dev/null "http://127.0.0.1:$PORT/healthz" && break; sleep 1; done
echo "api pid $API_PID health $(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$PORT/healthz")"

.venv/bin/python eval/e2e_eval.py --limit 6 --base-url "http://127.0.0.1:$PORT/api/v1" \
  --provider ollama --model "qwen2.5-3b-floor-on-isolated" 2>&1 | tail -16
echo "EXIT=$?"

pkill -P $API_PID 2>/dev/null
kill $API_PID 2>/dev/null
