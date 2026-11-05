#!/usr/bin/env python3
"""The Village — generative agents sim on 3 GPUs. Usage: python -m engine.main --days 1"""
import argparse, os, sys, time, yaml
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.llm import LLM
from engine.memory import Memory
from engine.sim import Sim
from engine.broadcast import Broadcaster

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--personas", default="personas.yaml")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--start-day", type=int, default=1)
    ap.add_argument("--webhook", default=os.environ.get("VILLAGE_WEBHOOK", ""))
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = yaml.safe_load(open(os.path.join(root, args.config)))
    personas = yaml.safe_load(open(os.path.join(root, args.personas)))["agents"]
    rels = yaml.safe_load(open(os.path.join(root, args.personas))).get("relationships", [])

    os.makedirs(os.path.join(root, "state"), exist_ok=True)
    llm = LLM(cfg["endpoints"])
    mem = Memory(os.path.join(root, "state", "village.db"), llm)
    for a, b, v in rels:
        mem.seed_affinity(a, b, v)

    bc = Broadcaster(args.webhook, os.path.join(root, "state", "broadcasts"))
    sim = Sim(cfg, personas, llm, mem, bc, os.path.join(root, "state"))

    for i in range(args.days):
        day = args.start_day + i
        t0 = time.time()
        sim.run_day(day)
        print(f"[done] day {day} in {time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    main()
