# SAT-SA developer shortcuts. Windows users: run these through Git Bash or use the
# equivalent commands in README.md.

PY ?= python
VENV ?= .venv
BIN := $(VENV)/Scripts
ifeq ($(OS),)
BIN := $(VENV)/bin
endif
SATSA := $(BIN)/satsa
PIP := $(BIN)/pip
PYTEST := $(BIN)/pytest
PERIODS ?= 2026-01 2026-02 2026-03 2026-04 2026-05 2026-06

.PHONY: venv install test lint init-db seed ingest train run demo api ui build up wheels clean

venv:
	$(PY) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

test:
	$(PYTEST)

lint:
	$(BIN)/ruff check satsa simulator validation tests

init-db:
	$(SATSA) init-db

seed:
	$(SATSA) seed

ingest:
	$(SATSA) ingest data/synthetic

train:
	$(SATSA) train --periods 2026-01 2026-02 2026-03 --promote

run:
	for p in $(PERIODS); do $(SATSA) run $$p; done

# Full offline demo from a clean checkout: schema -> synthetic data -> ingest -> train -> score.
demo: init-db seed ingest train run
	@echo "Demo data ready. Start the API with 'make api' and open http://localhost:8000"

api:
	$(BIN)/uvicorn satsa.api.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	cd dashboard && npm run dev

build:
	docker compose build

up:
	docker compose up

# Vendor every wheel so the image can be built with --network none.
wheels:
	mkdir -p wheels
	$(PIP) download -d wheels ".[dev]"

clean:
	rm -rf data/satsa.duckdb data/satsa.duckdb.wal reports/* logs/* .pytest_cache
