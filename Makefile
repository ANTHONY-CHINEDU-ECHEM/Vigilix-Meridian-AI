# Vigilix Meridian: reproducible build of data, models, evaluation and interface.
PY ?= python3

.PHONY: install data kb index train evaluate evaluate_blind export web all serve test test_web docker clean

install:
	$(PY) -m pip install -e ".[dev]"
	cd frontend && npm ci

data:            ## download every public source with checksums
	$(PY) scripts/download_data.py

kb:              ## dictionaries, FAERS scores, knowledge graph, passage corpus
	$(PY) scripts/build_kb.py

index:           ## BM25, word2vec, SIF and the dual encoder
	$(PY) scripts/build_index.py

train:           ## reranker (full and lexical), claim verifier, adverse event extractor
	$(PY) scripts/train_models.py

evaluate:        ## all evaluations on the development questions, reports and figures
	$(PY) scripts/run_evaluation.py

evaluate_blind:  ## score the frozen blind question set as well (run once)
	$(PY) scripts/run_evaluation.py --blind

export:          ## offline browser bundle in frontend/public/data
	$(PY) scripts/export_demo.py

web:             ## production build of the React interface
	cd frontend && npm run build

all: data kb index train evaluate export web

serve:
	uvicorn vigilix.api.main:app --host 0.0.0.0 --port 8000

test:
	$(PY) -m pytest -q
	cd frontend && npx vitest run

docker:
	docker compose -f deploy/compose.yml up --build

clean:
	rm -rf data/processed data/artifacts frontend/dist frontend/public/data
