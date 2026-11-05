import yaml
from engine.llm import LLM
from engine.memory import Memory
cfg = yaml.safe_load(open("config.yaml"))
llm = LLM(cfg["endpoints"])
print("chat:", llm.chat(1, [{"role": "user", "content": "Say exactly: hello village"}], max_tokens=20)[:80])
m = Memory("state/test.db", llm)
m.remember("Tessa", 1, 540, "Bram yelled at me at the market", 7)
print("recall:", m.recall("Tessa", "what made me upset", k=3, current_day=1))
m.adjust_affinity("Tessa", "Bram Ferrell", -6)
print("aff:", m.get_affinity("Tessa", "Bram Ferrell"))
print("OK")
