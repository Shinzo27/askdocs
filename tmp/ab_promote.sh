#!/bin/bash
# Does naming the section in the prompt order fix the 80CCE-vs-80C citation?
set -u
cd /Volumes/Work/projects/askdocs
export PATH=/opt/homebrew/bin:$PATH
export GENERATOR_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:1.5b-instruct OLLAMA_KEEP_ALIVE=30m

if ! curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null; then
  nohup ollama serve > /tmp/ollama.log 2>&1 &
  for _ in $(seq 1 40); do curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null && break; sleep 2; done
fi
curl -s http://localhost:11434/api/chat -d '{"model":"qwen2.5:1.5b-instruct","messages":[{"role":"user","content":"hi"}],"stream":false,"options":{"num_predict":1}}' >/dev/null

( cd apps/api && ../../.venv/bin/python -m uvicorn askdocs_api.main:app --host 127.0.0.1 --port 8123 > /tmp/api-promote.log 2>&1 ) &
for _ in $(seq 1 40); do curl -s --max-time 2 -o /dev/null http://127.0.0.1:8123/healthz && break; sleep 1; done
curl -s -o /dev/null -w "api %{http_code}\n" --max-time 3 http://127.0.0.1:8123/healthz

.venv/bin/python eval/e2e_eval.py --limit "${1:-6}" --base-url http://127.0.0.1:8123/api/v1 \
  --provider ollama --model "qwen2.5-1.5b-promote" 2>&1 | tail -16
pkill -f "uvicorn askdocs_api.main:app"
