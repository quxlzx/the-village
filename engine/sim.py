"""The tick loop: movement, encounters, conversations, events, narrator."""
import json, os, random, time
from concurrent.futures import ThreadPoolExecutor
from .world import World, Clock
from .agent import Agent
from .llm import extract_json

class Sim:
    def __init__(self, cfg, personas, llm, mem, broadcaster, state_dir):
        self.cfg = cfg
        self.llm, self.mem, self.bc = llm, mem, broadcaster
        self.world = World(cfg)
        self.clock = Clock(cfg["pacing"]["tick_minutes"], cfg["pacing"]["day_start"], cfg["pacing"]["day_end"])
        self.agents = [Agent(p, self.world, mem, llm, idx=i) for i, p in enumerate(personas)]
        self.world.people = [a.name for a in self.agents]
        self.by_name = {a.name: a for a in self.agents}
        self.pacing = cfg["pacing"]
        self.state_dir = state_dir

    # ---------- live snapshot for the 2D viewer ----------
    def snapshot(self, day, t):
        agents = []
        for a in self.agents:
            affs = sorted(((o, self.mem.get_affinity(a.name, o)) for o in self.world.people if o != a.name),
                          key=lambda x: -abs(x[1]))[:4]
            agents.append({"name": a.name, "role": a.role, "personality": a.personality,
                           "loc": a.loc, "act": a.act, "color": a.color, "tier": a.tier,
                           "with": a.conv_with, "aff": [[n, s] for n, s in affs if s]})
        snap = {"day": day, "time": t, "ts": time.time(),
                "map": {"locs": {k: {"desc": v, "xy": self.world.coords.get(k, [600, 400])}
                                 for k, v in self.world.locs.items()},
                        "edges": [list(e) for e in self.world.edge_list]},
                "agents": agents}
        tmp = os.path.join(self.state_dir, "live.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(self.state_dir, "live.json"))

    # ---------- narrator ----------
    def narrate(self, scene, day, t):
        try:
            out = self.llm.chat(1, [
                {"role": "system", "content":
                    "You are the wry, warm narrator of a village life reality show. "
                    "One punchy sentence of scene-setting or commentary. Max 25 words. No quotes."},
                {"role": "user", "content": scene}], temperature=1.0, max_tokens=60).strip()
            line = out[:200]
        except Exception:  # noqa: BLE001
            line = ""
        if line:
            self.bc.post(f"🎙️ {Clock.fmt(t)} — {line}", day)
        return line

    # ---------- one day ----------
    def run_day(self, day):
        t0 = self.clock.start
        self.bc.post(f"☀️ **Village Day {day} begins.**", day)
        self.snapshot(day, t0)
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(lambda a: a.make_plan(day, self.cfg["pacing"]["day_start"], list(self.world.locs)), self.agents))
        # morning scene
        self.narrate(f"Morning in the village. {random.choice(self.agents).name} opens the day.", day, t0)
        # 1-2 random events today
        todays_events = random.sample(self.world.events, k=random.choice([1, 1, 2]))
        fired = set()
        convo_count = 0
        for t in self.clock.ticks():
            # fire an event mid-morning or mid-afternoon
            if todays_events and t not in fired and (t == 10 * 60 or t == 15 * 60):
                ev = todays_events.pop(0)
                fired.add(t)
                loc = random.choice(list(self.world.locs))
                for a in self.agents:
                    self.mem.remember(a.name, day, t, f"The whole village noticed: {ev}.", importance=7)
                self.bc.post(f"⚡ **Event** {Clock.fmt(t)} — {ev.capitalize()}", day)
                self.narrate(f"A village-wide event just happened: {ev}. Wherever they are, everyone notices.", day, t)
            # movement toward plan targets
            for a in self.agents:
                if t < a.busy_until:
                    continue
                target, act = a.target_for(t)
                if a.loc != target:
                    step = self.world.path(a.loc, target)
                    if step:
                        a.loc = step[0]
                        a.act = f"walking to {target}"
                else:
                    a.act = act
            # encounters -> conversations (parallel across endpoints)
            if convo_count < 14:  # daily cap keeps wall-time sane
                pairs = self.find_pairs(day, t)
                if pairs:
                    with ThreadPoolExecutor(max_workers=2) as ex:
                        for _fut in ex.map(lambda pr: self.run_convo(pr[0], pr[1], day, t), pairs):
                            convo_count += 1
            self.snapshot(day, t)
        # evening: reflections
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(lambda a: a.reflect(day), self.agents))
        self.digest(day)

    def find_pairs(self, day, t):
        """Same-location pairs likely to talk; cap per tick."""
        by_loc = {}
        for a in self.agents:
            if a.busy_until >= t:
                continue
            by_loc.setdefault(a.loc, []).append(a)
        pairs = []
        for _loc, group in by_loc.items():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    aff = self.mem.get_affinity(a.name, b.name)
                    recency = abs(day - a.last_talk.get(b.name, -7))
                    chance = self.pacing["convo_chance_base"] + min(abs(aff), 60) / 200 - (0.25 if recency <= 1 else 0)
                    if random.random() < chance:
                        pairs.append((a, b))
        random.shuffle(pairs)
        return pairs[: self.pacing["max_convos_per_tick"]]

    def run_convo(self, a, b, day, t):
        a.busy_until = b.busy_until = t + self.pacing["tick_minutes"]
        a.conv_with = b.name
        b.conv_with = a.name
        self.snapshot(day, t)
        scene = f"{a.loc} ({self.world.locs[a.loc]})"
        gossip_pool = self.world.people
        try:
            dialogue, topic = a.converse(b, day, t, scene, gossip_pool, self.pacing["gossip_chance"])
        except Exception as e:  # noqa: BLE001
            print(f"[convo fail] {a.name}-{b.name}: {type(e).__name__}: {e}", flush=True)
            return
        lines = "\n".join(f"**{s.name}:** {ln}" for s, ln in dialogue)
        self.bc.post(f"📍 {Clock.fmt(t)} · **{a.loc}** · {a.name} 💬 {b.name}\n{lines}", day)
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_a = ex.submit(a.score_convo, b, dialogue, day, t)
            fut_b = ex.submit(b.score_convo, a, dialogue, day, t)
            sa, _ = fut_a.result()
            sb, _ = fut_b.result()
        if topic:
            self.narrate(f"{a.name} and {b.name} were at {a.loc}, and the talk turned to {topic}. "
                         f"(A: {sa}) (B: {sb})", day, t)
        else:
            self.narrate(f"{a.name} and {b.name} talked at {a.loc}. (A: {sa}) (B: {sb})", day, t)
        a.busy_until = b.busy_until = -1
        a.conv_with = b.conv_with = None
        self.snapshot(day, t)

    def digest(self, day):
        scenes = self.bc.day_log(day)
        try:
            out = self.llm.chat(1, [
                {"role": "system", "content":
                    "You write THE VILLAGE TIMES, a 4-bullet daily digest of village drama. "
                    "Witty, a little gossipy. Max 15 words per bullet. Start with a title line."},
                {"role": "user", "content": "Today's scenes and events:\n" + "\n".join(scenes)}],
                temperature=0.9, max_tokens=400)
        except Exception:  # noqa: BLE001
            out = ""
        if out:
            self.bc.post(f"📰 **THE VILLAGE TIMES — Day {day}**\n{out}", day)
        self.bc.post(f"🌙 Day {day} ends. The villagers sleep on it.", day)
