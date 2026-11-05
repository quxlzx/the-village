"""OpenAI-compatible client with per-agent tier routing."""
import httpx, json, time, re

class LLM:
    def __init__(self, endpoints: dict, timeout: float = 240.0):
        self.clients = {k: httpx.Client(base_url=v, timeout=timeout) for k, v in endpoints.items()}

    def chat(self, tier, messages, temperature=0.9, max_tokens=300, seed=None, top_p=0.95):
        tier = f"tier{tier}" if isinstance(tier, int) else tier
        body = {"model": "m", "messages": messages, "temperature": temperature,
                "max_tokens": max_tokens, "top_p": top_p,
                "chat_template_kwargs": {"enable_thinking": False}}
        if seed is not None:
            body["seed"] = seed
        last = None
        for attempt in range(3):
            try:
                r = self.clients[tier].post("/v1/chat/completions", json=body)
                r.raise_for_status()
                msg = r.json()["choices"][0]["message"]
                return msg.get("content") or msg.get("reasoning_content") or ""
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"llm tier={tier} failed: {last}")

    def embed(self, text):
        r = self.clients["embed"].post("/v1/embeddings", json={"model": "m", "input": [text[:2000]]})
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


def extract_json(text):
    """Best-effort JSON extraction from small-model output."""
    if not text:
        return None
    # strip code fences
    text = re.sub(r"```(json)?", "", text)
    # try whole
    for candidate in _candidates(text):
        try:
            return json.loads(candidate)
        except Exception:  # noqa: BLE001
            continue
    return None


def _candidates(text):
    text = text.strip()
    yield text
    # first balanced {...} or [...]
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    yield text[start:i + 1]
                    break
