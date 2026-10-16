---
title: Vigilix Meridian
emoji: 💊
colorFrom: gray
colorTo: yellow
sdk: docker
app_port: 8000
---

Vigilix Meridian on a Hugging Face Space. Copy the repository root into the Space and use `deploy/Dockerfile` as the Space Dockerfile; the image builds the knowledge base and models during the build step. Set `VIGILIX_LLM_PROVIDER=extractive` unless an Ollama endpoint is reachable from the Space.
