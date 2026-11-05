"""Villager agents: planning, conversation, reflection."""
import random, re
from .llm import extract_json

PALETTE = ["#e74c3c", "#3498db", "#2ecc71", "#f1c40f", "#9b59b6", "#1abc9c",
           "#e67e22", "#ecf0f1", "#e91e63", "#00bcd4", "#8bc34a", "#a1887f"]

class Agent:
    def __init__(self, spec, world, mem, llm, idx=0):
        self.name = spec["name"]
        self.tier = spec["tier"]
        self.role = spec["role"]
        self.personality = spec["personality"]
        self.home = spec["home"]
        self.work = spec["work"]
        self.age = spec.get("age", 30)
        self.color = PALETTE[idx % len(PALETTE)]
        self.world, self.mem, self.llm = world, mem, llm
        self.loc = self.home
        self.plan = []          # list of (start_min, loc, act)
        self.path = []          # queued steps
        self.busy_until = -1    # tick time until which agent is mid-activity
        self.act = "sleeping"
        self.conv_with = None   # other agent name during a conversation
        self.last_talk = {}     # other_name -> day

    # ---------- persona prompt ----------
    def persona_block(self):
        return (f"You are {self.name}, age {self.age}, {self.role}. "
                f"Personality: {self.personality}. You live in a small village.")

    def rel_block(self, others):
        lines = []
        for o in others:
            a = self.mem.get_affinity(self.name, o)
            if a:
                mood = "strongly dislike" if a < -30 else "dislike" if a < -10 else \
                       "like" if a > 10 else "strongly like" if a > 30 else "feel neutral about"
                lines.append(f"- {o}: you {mood} them (score {a}).")
        return "\n".join(lines) if lines else "- (no strong feelings about anyone yet)"

    # ---------- morning plan ----------
    def make_plan(self, day, t0, locs):
        insights = self.mem.recall(self.name, "what matters to me, my plans, my grudges", k=5, current_day=day)
        yest = self.mem.recent(self.name, day=day - 1, k=6)
        user = (f"Yesterday you experienced:\n" + "\n".join(f"- {m}" for m in yest) +
                f"\n\nYour current thoughts:\n" + "\n".join(f"- {m}" for m in insights) +
                f"\n\nToday is village day {day}. Pick 4 to 6 activities for your day "
                f"between {t0} and 23:00. Locations available: {', '.join(locs)}. "
                f"You live at {self.home} and work at {self.work}. "
                f"Reply ONLY with JSON: [{{\"at\":\"HH:MM\",\"loc\":\"Location\",\"act\":\"short activity\"}}]")
        out = self.llm.chat(self.tier, [
            {"role": "system", "content": self.persona_block() + "\nPlan your day realistically; travel on foot."},
            {"role": "user", "content": user}], temperature=0.8, max_tokens=400)
        data = extract_json(out)
        plan = []
        if isinstance(data, list):
            for item in data:
                try:
                    at = item["at"]
                    h, m = at.split(":")
                    mins = int(h) * 60 + int(m)
                    loc = item["loc"]
                    if loc not in self.world.locs:
                        loc = random.choice(list(self.world.locs))
                    plan.append((mins, loc, str(item.get("act", "wander"))[:60]))
                except Exception:  # noqa: BLE001
                    continue
        if not plan:
            plan = [(9 * 60, self.work, "work"), (19 * 60, self.home, "relax at home")]
        self.plan = sorted(plan)

    def target_for(self, minute):
        """Where should I be at this time per plan."""
        target, act = self.home, "rest at home"
        for mins, loc, a in self.plan:
            if minute >= mins:
                target, act = loc, a
        return target, act

    # ---------- conversation ----------
    def converse(self, other, day, t, scene_desc, people, gossip_chance=0.35):
        """Generate a dialogue between self and other. Returns list of (speaker, line)."""
        topic = None
        if random.random() < gossip_chance:
            known = [n for n in people if n not in (self.name, other.name)]
            if known:
                topic = random.choice(known)
        aff = self.mem.get_affinity(self.name, other.name)
        topic_line = (f"\nSECRETLY steer the talk toward {topic} (you have opinions about them)."
                      if topic else "\nTalk about whatever is on your mind.")
        hist_a = "\n".join(f"- {m}" for m in self.mem.recall(self.name, f"my relationship with {other.name} and recent events", k=4, current_day=day))
        hist_b = "\n".join(f"- {m}" for m in other.mem.recall(other.name, f"my relationship with {self.name} and recent events", k=4, current_day=day))
        dialogue = []
        starter = random.choice([self, other])
        others = {self: other, other: self}
        for turn_i in range(4):
            speaker = starter if turn_i % 2 == 0 else others[starter]
            listener = others[speaker]
            sysmsg = (speaker.persona_block() +
                      f"\nYou are at {scene_desc}, talking with {listener.name} ({listener.role})."
                      f"\nYour relationship with them:\n{speaker.rel_block([listener.name])}"
                      f"\nWhat you remember about them:\n{hist_a if speaker is self else hist_b}"
                      + topic_line +
                      "\nStay in character. Reply with ONE short spoken line (max 20 words), no quotes, no narration.")
            convo_txt = "\n".join(f"{s.name}: {ln}" for s, ln in dialogue) or "(the conversation is just starting)"
            line = speaker.llm.chat(speaker.tier, [
                {"role": "system", "content": sysmsg},
                {"role": "user", "content": f"The conversation so far:\n{convo_txt}\n\nYour turn. Say your next line."}],
                temperature=1.0, max_tokens=80).strip().strip('"')
            # small models sometimes prefix their own name; strip it
            first = speaker.name.split()[0]
            line = re.sub(rf"^{re.escape(speaker.name)}\s*[:,\-–]?\s*", "", line)
            line = re.sub(rf"^{re.escape(first)}\s*[:,\-–]\s*", "", line)
            dialogue.append((speaker, line[:160]))
        return dialogue, topic

    def score_convo(self, other, dialogue, day, t):
        """Self-assessment of the conversation -> memory + affinity delta."""
        convo_txt = "\n".join(f"{s.name}: {ln}" for s, ln in dialogue)
        out = self.llm.chat(3, [
            {"role": "system", "content": self.persona_block()},
            {"role": "user", "content":
                f"You just had this conversation with {other.name}:\n{convo_txt}\n\n"
                "Reply ONLY with JSON: {\"summary\":\"one sentence: what happened and how you feel\","
                "\"sentiment\":integer -2..2 how you now feel about them,"
                "\"about\":\"name of a third person discussed, or null\"}"}],
            temperature=0.4, max_tokens=160)
        data = extract_json(out) or {}
        summary = str(data.get("summary", f"had a conversation with {other.name}"))[:200]
        try:
            sent = max(-2, min(2, int(data.get("sentiment", 0))))
        except Exception:  # noqa: BLE001
            sent = 0
        about = data.get("about")
        self.mem.remember(self.name, day, t, f"I talked with {other.name}: {summary}",
                          importance=5 + abs(sent) * 2)
        self.mem.adjust_affinity(self.name, other.name, sent * 6)
        # gossip transfer: your sentiment leaks onto people you talk about
        if about and str(about).lower() not in ("null", "none", "") and about in self.world.people:
            self.mem.remember(self.name, day, t, f"I discussed {about} with {other.name}.", importance=4)
            self.mem.adjust_affinity(self.name, about, sent * 3)
        self.last_talk[other.name] = day
        return summary, sent

    # ---------- reflection ----------
    def reflect(self, day):
        todays = self.mem.recent(self.name, day=day, k=14)
        if not todays:
            return
        out = self.llm.chat(self.tier, [
            {"role": "system", "content": self.persona_block()},
            {"role": "user", "content":
                "Today you experienced:\n" + "\n".join(f"- {m}" for m in todays) +
                "\n\nWrite 2 short realizations/insights you now hold (opinions, grudges, plans, worries). "
                "Reply ONLY with JSON: [\"insight 1\",\"insight 2\"]"}],
            temperature=0.7, max_tokens=250)
        data = extract_json(out)
        if isinstance(data, list):
            for ins in data[:2]:
                ins = str(ins)[:200]
                if ins:
                    self.mem.remember(self.name, day, 23 * 60, ins, importance=8, kind="insight")
