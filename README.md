# The Village

A 2D life simulation where **12 LLM-driven villagers live, gossip, hold grudges, and generate drama** — powered entirely by local models on three consumer GPUs. No cloud APIs.

Inspired by Stanford's Generative Agents, tuned for consumer hardware and for being *fun to watch*.

![viewer](docs/viewer.png)

## What it does

- 12 personas (mayor, blacksmith, barista, merchant, journalist, ...) with personalities, homes, jobs, and seeded relationships
- Each morning every agent **plans their day** with their LLM; they walk the village graph, bump into each other, and hold **improvised conversations**
- Conversations are scored for sentiment → **affinity graph** shifts; gossip about third parties **propagates reputation**
- Every agent keeps an **episodic memory** (SQLite + embeddings, retrieved by recency × importance × relevance) and writes **nightly reflections** that become tomorrow's opinions
- Random village events (anonymous notes, peddlers, broken bridges) become shared memories everyone references for days
- A 14B **narrator** commentates each scene and writes a daily *Village Times* digest
- Everything streams to a **live 2D web viewer** and (optionally) a Discord channel

One in-world day ≈ 10 minutes of wall time on 3× RTX 30-series cards.

## Architecture

| Piece | Model | Role |
|---|---|---|
| tier1 | Qwen3-14B-Q4 | main cast + narrator |
| tier2 | Qwen3-8B-Q4 | supporting cast |
| tier3 | Qwen3-4B-Q4 | sentiment scoring |
| embed | Qwen3-Embedding-0.6B | memory retrieval |

All served by [llama.cpp](https://github.com/ggml-org/llama.cpp) `llama-server` (OpenAI-compatible, `--jinja`, flash-attn, q8_0 KV). Agents are routed to tiers by importance. Any OpenAI-compatible endpoint works — set `endpoints:` in `config.yaml`.

```
engine/
  main.py      entry: --days N --start-day D
  sim.py       tick loop: plans, movement, encounters, events, narrator, digest
  agent.py     persona prompts, day planning, dialogue, sentiment, reflection
  memory.py    SQLite episodic memory + embeddings + affinity graph
  world.py     location graph + BFS pathfinding + clock
  llm.py       httpx client, tier routing, JSON extraction
  broadcast.py Discord webhook poster (+ day logs)
  viewer.py    stdlib HTTP server for the live 2D map
  web/         canvas frontend (no framework)
```

## Setup

```bash
pip install -r requirements.txt

# download models (or point config.yaml at any GGUF endpoints you already run)
mkdir -p models && cd models
curl -L -O https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf
curl -L -O https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf
curl -L -O https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/Qwen3-Embedding-0.6B-Q8_0.gguf
```

Start four `llama-server` instances on the ports in `config.yaml` (one per tier + embedder; the embedder needs `--embedding --pooling last`). **Qwen3 thinking mode must be off** — the client already sends `chat_template_kwargs: {"enable_thinking": false}`.

```bash
python -m engine.main --days 1                 # simulate a day (logs to state/broadcasts/)
VILLAGE_WEBHOOK=<discord-webhook-url> python -m engine.main --days 1 --start-day 2
VILLAGE_HOST=0.0.0.0 python -m engine.viewer   # live 2D map at :8090
```

The SQLite memory in `state/` persists across days — the story compounds. Delete it to start a new saga.

## Tuning

`config.yaml` controls pacing (tick length, day hours, conversation caps, gossip chance), the world graph (locations, roads, coordinates), and the random event deck. `personas.yaml` is the cast: personalities, seeded affinities, and which model tier plays each role.

## License

MIT
