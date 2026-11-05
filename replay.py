import sys, time, os
from engine.broadcast import Broadcaster
day = sys.argv[1] if len(sys.argv) > 1 else "2"
bc = Broadcaster(open(".webhook_url").read().strip(), "state/broadcasts")
raw = open(f"state/broadcasts/day{day}.log", encoding="utf-8").read()
posts = [p.strip() for p in raw.split("\n\n") if p.strip()]
print(f"replaying {len(posts)} posts")
for p in posts:
    bc.post(p, day + "r")
    time.sleep(1.4)
print("done")
