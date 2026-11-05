"""World graph: locations, adjacency, clock."""
from collections import deque

class World:
    def __init__(self, cfg: dict):
        w = cfg["world"]
        self.locs = {k: str(v) for k, v in w["locations"].items()}
        self.coords = {k: list(v) for k, v in w.get("coords", {}).items()}
        self.adj = {k: set() for k in self.locs}
        self.edge_list = [tuple(e) for e in w["edges"]]
        for a, b in w["edges"]:
            self.adj[a].add(b)
            self.adj[b].add(a)
        self.events = list(cfg.get("events", []))
        self.people = []

    def path(self, a, b):
        """BFS shortest path (list of locations to step through, excluding a)."""
        if a == b:
            return []
        prev = {a: None}
        q = deque([a])
        while q:
            cur = q.popleft()
            for nb in self.adj[cur]:
                if nb not in prev:
                    prev[nb] = cur
                    if nb == b:
                        out, node = [], b
                        while node != a:
                            out.append(node)
                            node = prev[node]
                        return list(reversed(out))
                    q.append(nb)
        return []

class Clock:
    def __init__(self, tick_minutes=30, day_start="06:00", day_end="23:00"):
        self.tm = tick_minutes
        self.start = self._min(day_start)
        self.end = self._min(day_end)
        self.day = 1
        self.reset()

    @staticmethod
    def _min(s):
        h, m = s.split(":")
        return int(h) * 60 + int(m)

    def reset(self):
        self.cur = self.start

    def ticks(self):
        t = self.start
        while t < self.end:
            yield t
            t += self.tm

    @staticmethod
    def fmt(t):
        return f"{t // 60:02d}:{t % 60:02d}"
