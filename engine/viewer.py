#!/usr/bin/env python3
"""The Village live 2D viewer — stdlib HTTP server. Serves index.html + state/feed APIs."""
import json, os, http.server, socketserver, functools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
WEB = os.path.join(ROOT, "engine", "web")
HOST = os.environ.get("VILLAGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("VILLAGE_PORT", "8090"))

class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            with open(os.path.join(WEB, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/api/state":
            p = os.path.join(STATE, "live.json")
            if not os.path.exists(p):
                self._send(404, json.dumps({"error": "no live state yet"}))
                return
            with open(p, "rb") as f:
                self._send(200, f.read())
        elif path == "/api/feed":
            limit = 40
            if "?" in self.path:
                for kv in self.path.split("?")[1].split("&"):
                    if kv.startswith("limit="):
                        limit = min(int(kv[6:]), 200)
            day = None
            sp = os.path.join(STATE, "live.json")
            if os.path.exists(sp):
                try:
                    day = json.load(open(sp)).get("day")
                except Exception:  # noqa: BLE001
                    day = None
            if day is None:
                import glob, re
                days = [int(re.search(r"day(\d+)", f).group(1))
                        for f in glob.glob(os.path.join(STATE, "broadcasts", "day*.log"))
                        if re.search(r"day(\d+)\.log", f)]
                day = max(days) if days else 1
            p = os.path.join(STATE, "broadcasts", f"day{day}.log")
            posts = []
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    posts = [x.strip() for x in f.read().split("\n\n") if x.strip()][-limit:]
            self._send(200, json.dumps({"day": day, "posts": posts}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, fmt, *args):  # quiet
        pass

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    with Server((HOST, PORT), functools.partial(Handler)) as httpd:
        print(f"village viewer on http://{HOST}:{PORT}", flush=True)
        httpd.serve_forever()
