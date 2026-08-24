#!/usr/bin/env python3
"""Browser multiplayer: friends on phones + GTO bots, served from this Mac.

    python3 serve.py --players 4

Then everyone joins the same Wi-Fi (a hotspot works — no internet
needed) and opens the printed http://<ip>:<port> address on their phone.
Seats without a human are played by the blueprint bots.
"""
import argparse
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from pokersim.strategy import Blueprint, blueprint_exists
from pokersim.webtable import WebTable

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def pick_blueprint(n, override=None):
    """Serving prefers the small distilled file: same play strategy,
    3s load instead of ~30s and a fraction of the RAM."""
    if override:
        return override
    for name in (f"bp_{n}p.gto", f"bp_{n}p.pkl"):
        path = os.path.join("blueprints", name)
        if blueprint_exists(path):
            return path
    raise SystemExit(
        f"no blueprint for {n} players — run: python3 train.py --players {n}"
    )


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet sent; just picks a route
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def make_handler(table):
    with open(os.path.join(WEB_DIR, "index.html"), "rb") as f:
        index_html = f.read()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # keep-alive: fewer connection
                                       # setups on high-latency links

        def log_message(self, *args):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return {}

        def do_GET(self):
            url = urlparse(self.path)
            token = parse_qs(url.query).get("token", [None])[0]
            if url.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(index_html)))
                self.end_headers()
                self.wfile.write(index_html)
            elif url.path == "/state":
                self._json(table.state_for(token))
            elif url.path == "/advice":
                self._json(table.advice(token))
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            url = urlparse(self.path)
            data = self._body()
            token = data.get("token")
            if url.path == "/join":
                self._json(table.join(data.get("name"), data.get("password")))
            elif url.path == "/act":
                self._json(table.act(token, data))
            elif url.path == "/next":
                self._json(table.start_hand(token))
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--players", type=int, default=4, choices=[3, 4, 5, 6])
    ap.add_argument("--blueprint", default=None)
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("PORT", "8080")),
                    help="port to listen on (defaults to $PORT for "
                         "cloud hosts like Render)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--turn-timeout", type=int, default=45,
                    help="seconds before an absent player auto-checks/folds")
    ap.add_argument("--password", default=os.environ.get("TABLE_PASSWORD"),
                    help="require this password to join (defaults to "
                         "$TABLE_PASSWORD; empty = open table)")
    args = ap.parse_args()

    path = pick_blueprint(args.players, args.blueprint)
    print(f"Loading blueprint {path} ...")
    bp = Blueprint.load(path)
    if bp.n_players != args.players:
        raise SystemExit(f"{path} is for {bp.n_players} players")
    table = WebTable(bp, seats=args.players, seed=args.seed,
                     turn_timeout=args.turn_timeout, password=args.password)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(table))
    print(f"\n  Table ready: {args.players} seats, blinds {bp.sb}/{bp.bb}, "
          f"trained {bp.iters_done:,} iterations")
    print(f"  On phones connected to the same Wi-Fi, open:\n")
    print(f"      http://{lan_ip()}:{args.port}\n")
    print("  (macOS may ask to allow incoming connections — allow it. "
          "Ctrl-C stops the table.)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTable closed.")


if __name__ == "__main__":
    main()
