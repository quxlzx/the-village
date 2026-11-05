"""Discord webhook broadcaster + on-disk day log."""
import json, os, time, urllib.request

class Broadcaster:
    def __init__(self, webhook_url, log_dir):
        self.url = webhook_url
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

    def post(self, text, day):
        with open(os.path.join(self.log_dir, f"day{day}.log"), "a", encoding="utf-8") as f:
            f.write(text + "\n\n")
        if not self.url:
            print(text, flush=True)
            return
        body = json.dumps({"content": text[:1990]}).encode()
        req = urllib.request.Request(self.url, data=body,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "village-broadcaster/1.0"})
        for attempt in range(3):
            try:
                urllib.request.urlopen(req, timeout=15)
                return
            except Exception as e:  # noqa: BLE001
                print(f"[bc] post failed: {e}", flush=True)
                time.sleep(2 * (attempt + 1))

    def day_log(self, day):
        p = os.path.join(self.log_dir, f"day{day}.log")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [ln for ln in f.read().splitlines() if ln.strip()][:60]
