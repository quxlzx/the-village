import yaml
from engine.llm import LLM
from engine.memory import Memory
from engine.world import World
from engine.agent import Agent

cfg = yaml.safe_load(open("config.yaml"))
personas = yaml.safe_load(open("personas.yaml"))["agents"]
llm = LLM(cfg["endpoints"])
mem = Memory("state/test2.db", llm)
world = World(cfg)
world.people = [p["name"] for p in personas]
a = Agent(personas[2], world, mem, llm)  # Tessa
b = Agent(personas[0], world, mem, llm)  # Edith
print("conversing...")
dialogue, topic = a.converse(b, 1, 600, "Maple Square", world.people)
for s, ln in dialogue:
    print(f"{s.name}: {ln}")
print("topic:", topic)
print("scoring...")
print(a.score_convo(b, dialogue, 1, 600))
print("OK")
