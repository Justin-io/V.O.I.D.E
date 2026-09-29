# V.O.I.D.E. API Configuration & IPC Protocol Reference

This document provides complete technical specifications for configuring LLM reasoning providers and communicating with the V.O.I.D.E. WebSocket IPC Daemon for industrial telemetry anomaly detection, data profiling, and automated triage.

---

## 1. Supported LLM Backends

V.O.I.D.E. features a direct HTTP/SSE streaming client ([APIStreamer](file:///home/justin/Desktop/V.O.I.D.E/agent/runtime/api_streamer.py)) that connects to any OpenAI-compatible `/chat/completions` endpoint without browser automation or Chromium overhead.

### 1.1 Local Ollama (Free, Private, Offline)
Run models locally with complete operational data privacy:

```bash
# 1. Start Ollama daemon
ollama serve

# 2. Pull a recommended model
ollama run llama3.1
# Or for data science and analysis:
ollama run qwen2.5-coder:7b
```

Configure `.env`:
```ini
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=llama3.1
VOIDE_LLM_PROVIDER=ollama
OPENAI_API_KEY=
```

### 1.2 OpenAI Cloud
```ini
OPENAI_API_KEY=sk-proj-your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
VOIDE_LLM_PROVIDER=openai
```

### 1.3 OpenRouter Multi-Model Gateway
Access models across providers (Claude 3.5 Sonnet, Gemini 1.5 Pro, Llama 3.3, DeepSeek) through a unified gateway:
```ini
OPENAI_API_KEY=sk-or-v1-your-key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=anthropic/claude-3.5-sonnet
VOIDE_LLM_PROVIDER=openrouter
```

### 1.4 DeepSeek API
```ini
OPENAI_API_KEY=sk-your-deepseek-key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
VOIDE_LLM_PROVIDER=deepseek
```

---

## 2. WebSocket IPC Protocol

The Python daemon listens on `ws://127.0.0.1:8766` (configurable via `$VOIDE_IPC_PORT`).

### 2.1 Connection Handshake
Upon client connection, the daemon emits an initial `HELLO` frame:
```json
{
  "type": "HELLO",
  "version": "1.0.0-linux",
  "port": 8766,
  "workspace": "/absolute/path/to/workspace"
}
```

### 2.2 Telemetry Ingestion & Anomaly Auditing Actions

#### `get_anomaly_audit`
Executes the comprehensive 8-layer multi-signal anomaly audit pipeline on a telemetry dataset:
```json
{
  "action": "get_anomaly_audit",
  "id": "req-1",
  "payload": {
    "file_path": "data/chiller_telemetry_jan2026.csv"
  }
}
```
*Response Payload*:
```json
{
  "status": "SUCCESS",
  "data": {
    "summary": {
      "row_count": 4320,
      "entities": ["CH-01", "CH-02", "CH-03"],
      "total_anomalies_detected": 14
    },
    "data_availability": { "missing_blocks": [], "coverage_gaps": [] },
    "physical_inconsistencies": [],
    "stuck_plateaus": [],
    "meter_surges": [],
    "sustained_regimes": [],
    "cross_variable_contradictions": [],
    "peer_disagreements": []
  }
}
```

#### `dataset_ingest`
Ingests a raw telemetry CSV file, generates metadata signatures, and registers the dataset:
```json
{
  "action": "dataset_ingest",
  "id": "req-2",
  "payload": {
    "file_path": "data/plant_telemetry.csv",
    "name": "Central Chiller Plant Telemetry"
  }
}
```

#### `dataset_profile`
Calculates channel-by-channel quality profiles, missing value rates, and statistical moments:
```json
{
  "action": "dataset_profile",
  "id": "req-3",
  "payload": {
    "file_path": "data/plant_telemetry.csv"
  }
}
```

#### `get_anomalies`
Retrieves registered anomaly episodes with persistence duration and severity scores:
```json
{
  "action": "get_anomalies",
  "id": "req-4",
  "payload": {
    "dataset_id": "ds-8a9f2b",
    "status": "DETECTED"
  }
}
```

#### `get_anomaly_evidence`
Retrieves quantitative observation chains, expected-vs-observed values, and evidence critic validation for a specific anomaly:
```json
{
  "action": "get_anomaly_evidence",
  "id": "req-5",
  "payload": {
    "anomaly_id": "an-d3d36240"
  }
}
```

#### `get_latest_analysis`
Fetches the latest empirical baseline regression parameters ($R^2$, $CV(RMSE)$, feature weights) and fleet residual distributions:
```json
{
  "action": "get_latest_analysis",
  "id": "req-6",
  "payload": {}
}
```

---

## 3. Autonomous Reasoning & Chat Actions

#### `chat_send`
Dispatches an analytical investigation query to the active ReAct agent:
```json
{
  "action": "chat_send",
  "id": "req-7",
  "payload": {
    "query": "Audit CH-02 energy consumption during the Jan 14-18 cold snap against peer chillers",
    "session_id": "session-uuid"
  }
}
```

#### `llm_get_config`
Fetches current runtime model parameters with secret masking:
```json
{
  "action": "llm_get_config",
  "id": "req-8",
  "payload": {}
}
```
*Response*:
```json
{
  "status": "SUCCESS",
  "config": {
    "provider": "ollama",
    "base_url": "http://localhost:11434/v1",
    "model": "llama3.1",
    "has_api_key": false,
    "masked_api_key": ""
  }
}
```

#### `llm_set_config`
Hot-swaps reasoning backend configuration dynamically without server restarts:
```json
{
  "action": "llm_set_config",
  "id": "req-9",
  "payload": {
    "provider": "openai",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o",
    "api_key": "sk-proj-..."
  }
}
```

---

## 4. Real-Time Broadcast Events

Clients receive streaming events asynchronously over the WebSocket connection:

### `CHAT_STREAM`
Emitted as incremental tokens are produced by the LLM reasoning streamer:
```json
{
  "type": "CHAT_STREAM",
  "session_id": "session-uuid",
  "delta": " persistent energy elevation of +34.2% ",
  "full_text": "Audit indicates persistent energy elevation of +34.2% on Chiller-02...",
  "done": false
}
```

### `TOOL_EXECUTED`
Emitted when an analytical tool action executes within the agent ReAct loop:
```json
{
  "type": "TOOL_EXECUTED",
  "session_id": "session-uuid",
  "tool": {
    "tool": "get_anomaly_audit",
    "path": "data/telemetry.csv",
    "status": "SUCCESS",
    "anomalies_found": 8
  }
}
```

### `DATASET_UPDATED`
Emitted when an ingestion or profiling pipeline finishes:
```json
{
  "type": "DATASET_UPDATED",
  "dataset_id": "ds-8a9f2b",
  "status": "PROFILED",
  "row_count": 4320
}
```
