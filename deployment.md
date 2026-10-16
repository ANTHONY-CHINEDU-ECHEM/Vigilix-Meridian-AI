# Deployment

## Local

```
make install
make all          # download, knowledge base, index, models, evaluation, browser bundle, interface (about 30 minutes on 2 CPU cores)
ollama pull llama3.1:8b   # optional; any Ollama chat model works
make serve        # http://localhost:8000, API documentation at /docs
```

Without Ollama the service uses the extractive composer, which writes answers from verbatim evidence sentences. With Ollama it writes with the local model and still verifies every sentence.

## Docker with a local model

```
docker compose -f deploy/compose.yml up --build
```

The compose file starts an Ollama container, pulls the model named by `VIGILIX_LLM_MODEL` and builds the Vigilix image, which downloads the data and trains every model during the build (`BUILD_DATA=1`). To reuse a prebuilt `data/` folder, build with `--build-arg BUILD_DATA=0` and mount it at `/app/data`.

## Inside a hospital network

Everything runs on local hardware: no request leaves the host, no external model API is called and every model trains on CPU from public data. Recommended settings:

* `VIGILIX_LLM_PROVIDER=ollama` with a model approved by the local information governance team, or `extractive` where no model is approved.
* `VIGILIX_AUDIT_DB` on a backed up volume; the audit table is append only.
* `VIGILIX_CORS_ORIGINS` restricted to the intranet host name.
* A reverse proxy for TLS and single sign on in front of port 8000.

## Offline browser demo

`make export` writes the bundle (about 19 MB, gzip compressed) to `frontend/public/data`, and `make web` builds the interface into `frontend/dist`. Serving `frontend/dist` from any static host (GitHub Pages through `.github/workflows/pages.yml`, or a Claude artifact) runs the whole system in the visitor's browser. Append `?engine=browser` to force the browser engine when a server is also reachable. For hosts that refuse binary or gzip files, run `python scripts/export_demo.py --text_assets` after `make web`: every compressed file in `frontend/dist/data` is rewritten as base64 text, which the engine loads automatically when the binary file is missing. The hosted demo uses this form.

## Hugging Face Space

Copy the repository into a Docker Space and use `deploy/Dockerfile`; see `deploy/hf_space/README.md`.
