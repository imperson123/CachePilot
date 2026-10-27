# Roadmap

## Current 2.0 prototype

V1 Store benchmark and historical evidence retained; R³-KV scoring/action prototype; EWMA adaptive controller; deterministic scenario simulation, JSONL replay, five-view Streamlit console, shared-trace Policy Lab and tests. No online KV action is claimed.

## V2.1: serving integration

Adapters for vLLM, SGLang and LMCache; real request/KV metadata ingestion; measured prefill and retrieval cost calibration; separate replay versus live UI modes. Each adapter needs integration tests and evidence labels.

## V2.2: online actions

Execute and validate retain/offload/fetch/recompute/prefetch against a real cache tier, including capacity safety, failed fetch recovery, rate limits, and controlled A/B evaluation.

## V2.5: multimodal traces

Long-video and multimodal workloads with real model traces. The current `video_like.json` is only a temporal-locality simulation and is not a Video-LMM benchmark.

## V3.0: recoverability-aware protection

Model restore, reconstruct and recompute alternatives, with durable evidence for quality, latency, and failure behavior. Not implemented in 2.0.
