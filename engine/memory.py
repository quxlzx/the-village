"""SQLite memory: observations + insights + embeddings + relationships."""
import sqlite3, threading, numpy as np

class Memory:
    def __init__(self, db_path, llm):
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.RLock()
        self.llm = llm
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS mem(
          id INTEGER PRIMARY KEY, agent TEXT, day INT, t INT, kind TEXT,
          text TEXT, importance INT, emb BLOB);
        CREATE TABLE IF NOT EXISTS rel(
          a TEXT, b TEXT, affinity INT DEFAULT 0, PRIMARY KEY(a,b));
        """)
        self.db.commit()

    def remember(self, agent, day, t, text, importance, kind="obs"):
        emb = np.array(self.llm.embed(text), dtype=np.float32)
        with self.lock:
            self.db.execute("INSERT INTO mem(agent,day,t,kind,text,importance,emb) VALUES(?,?,?,?,?,?,?)",
                            (agent, day, t, kind, text, importance, emb.tobytes()))
            self.db.commit()

    def recall(self, agent, query, k=6, max_age_days=14, current_day=1):
        """recency x importance x relevance retrieval."""
        with self.lock:
            rows = self.db.execute(
                "SELECT id,day,t,kind,text,importance,emb FROM mem WHERE agent=? AND day>=?",
                (agent, current_day - max_age_days)).fetchall()
        if not rows:
            return []
        q = np.array(self.llm.embed(query), dtype=np.float32)
        q /= (np.linalg.norm(q) + 1e-9)
        scored = []
        for _id, day, t, kind, text, imp, blob in rows:
            e = np.frombuffer(blob, dtype=np.float32)
            cos = float(q @ e / (np.linalg.norm(e) + 1e-9))
            recency = 1.0 / (1.0 + (current_day - day))
            score = (0.45 + 0.55 * max(cos, 0)) * (imp / 10.0) * (0.5 + 0.5 * recency)
            scored.append((score, kind, text))
        scored.sort(reverse=True)
        return [f"{'INSIGHT: ' if k2=='insight' else ''}{txt}" for _s, k2, txt in scored[:k]]

    def recent(self, agent, day=None, k=12):
        with self.lock:
            if day is None:
                rows = self.db.execute(
                    "SELECT kind,text,importance FROM mem WHERE agent=? ORDER BY id DESC LIMIT ?",
                    (agent, k)).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT kind,text,importance FROM mem WHERE agent=? AND day=? ORDER BY id DESC LIMIT ?",
                    (agent, day, k)).fetchall()
        return [t for _k, t, _i in reversed(rows)]

    def get_affinity(self, a, b):
        if a == b:
            return 0
        with self.lock:
            r = self.db.execute("SELECT affinity FROM rel WHERE a=? AND b=?", (a, b)).fetchone()
        return r[0] if r else 0

    def adjust_affinity(self, a, b, delta):
        if a == b or delta == 0:
            return
        for x, y in ((a, b), (b, a)):
            with self.lock:
                cur = self.get_affinity(x, y)
                new = max(-100, min(100, cur + delta))
                self.db.execute("INSERT INTO rel(a,b,affinity) VALUES(?,?,?) "
                                "ON CONFLICT(a,b) DO UPDATE SET affinity=?", (x, y, new, new))
                self.db.commit()

    def seed_affinity(self, a, b, val):
        with self.lock:
            for x, y in ((a, b), (b, a)):
                self.db.execute("INSERT OR IGNORE INTO rel(a,b,affinity) VALUES(?,?,?)", (x, y, val))
            self.db.commit()
