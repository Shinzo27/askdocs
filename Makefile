# AskDocs - one entry point per documented task.
# Week 1 targets: corpus, schema, retrieval, eval, app shell.

SHELL := /bin/bash
PY := .venv/bin/python
COMPOSE := docker compose -f infra/docker-compose.yml
API_DIR := apps/api
WEB_DIR := apps/web

.DEFAULT_GOAL := help

help:  ## show this list
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- environment -----------------------------------------------------------
.venv:  ## create the virtualenv and install python deps
	python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements-dev.txt
	$(PY) -m pip install -e $(API_DIR)

doctor:  ## environment + corpus integrity; must print READY
	$(PY) scripts/doctor.py

env:  ## copy the env contract
	test -f .env || cp .env.example .env

# --- corpus ----------------------------------------------------------------
corpus:  ## fetch -> ingest -> embed -> doctor (the documented bootstrap)
	$(PY) scripts/fetch_corpus.py
	$(PY) scripts/ingest.py
	$(PY) scripts/embed.py
	$(PY) scripts/doctor.py

ingest:  ## PDFs -> section-tagged chunks
	$(PY) scripts/ingest.py

embed:  ## chunks -> vectors + embedding manifest
	$(PY) scripts/embed.py

# --- database --------------------------------------------------------------
up:  ## start Postgres (+ pgvector)
	$(COMPOSE) up -d db
	@echo "waiting for db..."; \
	for i in $$(seq 1 30); do \
		$(COMPOSE) exec -T db pg_isready -U askdocs -d askdocs >/dev/null 2>&1 && break; sleep 1; done
	@echo "db ready"

down:  ## stop the stack (keeps the volume)
	$(COMPOSE) down

migrate:  ## apply alembic migrations
	cd infra && ../$(PY) -m alembic -c alembic.ini upgrade head

load:  ## chunks + vectors -> Postgres
	$(PY) scripts/load_db.py

db: up migrate load  ## db up, migrated and loaded

psql:  ## open a psql shell
	$(COMPOSE) exec db psql -U askdocs -d askdocs

# --- services --------------------------------------------------------------
api:  ## run the API on :8000 (reload)
	cd $(API_DIR) && ../../$(PY) -m uvicorn askdocs_api.main:app --reload --port 8000

web:  ## run the app shell on :3000
	cd $(WEB_DIR) && npm run dev

# --- quality ---------------------------------------------------------------
test:  ## pytest
	cd $(API_DIR) && ../../$(PY) -m pytest -q

lint:  ## ruff
	$(PY) -m ruff check apps/api eval scripts

fmt:  ## ruff format + fix
	$(PY) -m ruff check --fix apps/api eval scripts
	$(PY) -m ruff format apps/api eval scripts

typecheck:  ## mypy (api) + tsc (web)
	cd $(API_DIR) && ../../$(PY) -m mypy askdocs_api
	cd $(WEB_DIR) && npx tsc --noEmit

# --- evaluation ------------------------------------------------------------
eval-retrieval:  ## 25-question retrieval subset: recall@10, MRR, hit rate
	$(PY) eval/retrieval_eval.py

eval-full:  ## every question with a section
	$(PY) eval/retrieval_eval.py --full

verify: doctor test eval-retrieval  ## the Week 1 gate in one command

.PHONY: help doctor .venv env corpus ingest embed up down migrate load db psql api web \
        test lint fmt typecheck eval-retrieval eval-full verify
