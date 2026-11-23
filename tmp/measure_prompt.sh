#!/bin/bash
# Does the floor actually grow the prompt? Measure prompt tokens directly instead
# of inferring latency from a noisy p95.
set -u
cd /Volumes/Work/projects/askdocs
export PATH=/opt/homebrew/bin:$PATH
export GENERATOR_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:1.5b-instruct OLLAMA_KEEP_ALIVE=30m

ask() {
  curl -s -N --max-time 240 http://127.0.0.1:8000/api/v1/ask \
    -H 'content-type: application/json' \
    -d "{\"question\": \"$1\"}" \
  | grep -o '"prompt_tokens":[0-9]*\|"contexts":[0-9]*\|"sources":[0-9]*\|"total_tokens":[0-9]*' | sort -u | tr '\n' ' '
}

for floor in 0 1; do
  echo "=== RERANK_RRF_FLOOR=$floor"
  ( cd apps/api && RERANK_RRF_FLOOR=$floor ../../.venv/bin/python -m uvicorn askdocs_api.main:app \
      --host 127.0.0.1 --port 8000 > /tmp/api-tok-$floor.log 2>&1 ) &
  for _ in $(seq 1 40); do curl -s --max-time 2 -o /dev/null http://127.0.0.1:8000/healthz && break; sleep 1; done
  echo -n "80C tuition: "; ask "What is the deduction limit for tuition fees under section 80C?"
  echo
  echo -n "80E loan:    "; ask "Is interest on an education loan deductible under section 80E?"
  echo
  pkill -f "uvicorn askdocs_api.main:app"; sleep 3
done
