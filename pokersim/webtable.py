"""Server-side table for the browser multiplayer game (serve.py).

Humans join with a session token and take seats; GTO bots fill the rest.
All mutation happens under one lock. The game advances lazily: every
state poll calls tick(), which plays one due bot action (paced by
bot_delay) and enforces human turn timeouts — no background threads.
"""
import random
import threading
import time
import secrets
from collections import deque

from .abstraction import nearest_raise_token, playable_actions
from .ai import BotAgent, spot_strategy
from .cards import card_str, cards_str
from .cli import POSITION_NAMES, action_label, describe_action, player_status
from .engine import Hand
from .equity import hand_equity
from .evaluator import category_name, evaluate

STREET_LABELS = ["Preflop", "Flop", "Turn", "River"]


def card_codes(cards):
    return [card_str(c, pretty=False) for c in cards]


class WebTable:
    def __init__(self, blueprint, seats=4, seed=None, turn_timeout=45,
                 bot_delay=0.9, idle_timeout=120, password=None,
                 next_hand_timeout=30):
        assert 3 <= seats <= 6
        self.bp = blueprint
        self.password = password or None
        self.n = seats
        self.rng = random.Random(seed)
        self.bot = BotAgent(blueprint, self.rng)
        self.lock = threading.RLock()
        self.turn_timeout = turn_timeout
        self.bot_delay = bot_delay
        self.idle_timeout = idle_timeout
        self.next_hand_timeout = next_hand_timeout
        self.buyin = blueprint.stack

        # persistent players (index = identity); bots fill non-human slots
        self.players = [self._fresh_bot(i) for i in range(seats)]
        self.tokens = {}          # token -> player index
        self.pending = []         # (token, name) waiting for next hand
        self.phase = "lobby"      # lobby | hand | showdown
        self.hand = None
        self.hand_no = 0
        self.seat_of = None       # player index -> seat
        self.player_at = None     # seat -> player index
        self.log = deque(maxlen=14)
        self.result = None
        self.turn_deadline = None
        self.next_hand_ready = set()
        self.next_hand_deadline = None
        self.last_bot_act = 0.0
        self.seq = 0

    def _fresh_bot(self, i):
        return {"kind": "bot", "name": f"Bot{i + 1}", "chips": self.buyin,
                "last_seen": None}

    def _bump(self):
        self.seq += 1

    # ---- membership ---------------------------------------------------
    def join(self, name, password=None):
        name = (name or "Player").strip()[:12] or "Player"
        with self.lock:
            if self.password and password != self.password:
                return {"error": "wrong table password"}
            token = secrets.token_hex(8)
            if self.phase == "hand":
                if len(self.tokens) + len(self.pending) >= self.n:
                    return {"error": "table is full"}
                self.pending.append((token, name))
                self._bump()
                return {"token": token, "pending": True}
            idx = self._seat_human(token, name)
            if idx is None:
                return {"error": "table is full"}
            self._bump()
            return {"token": token, "pending": False}

    def _seat_human(self, token, name):
        for i, p in enumerate(self.players):
            if p["kind"] == "bot":
                self.players[i] = {"kind": "human", "name": name,
                                   "chips": self.buyin, "last_seen": time.time()}
                self.tokens[token] = i
                self.log.append(f"{name} joined the table")
                return i
        return None

    def _prune_idle(self):
        now = time.time()
        for token, idx in list(self.tokens.items()):
            p = self.players[idx]
            if now - (p["last_seen"] or now) > self.idle_timeout:
                self.log.append(f"{p['name']} left (idle) — a bot takes over")
                self.players[idx] = self._fresh_bot(idx)
                del self.tokens[token]
                self.next_hand_ready.discard(token)
                self._bump()

    # ---- hand lifecycle ----------------------------------------------
    def start_hand(self, token):
        with self.lock:
            if self.phase == "hand":
                return {"error": "hand already running"}
            self._prune_idle()
            if token not in self.tokens and \
                    not any(t == token for t, _ in self.pending):
                return {"error": "join first"}
            if self.phase == "showdown":
                self.next_hand_ready.add(token)
                if self.next_hand_deadline is None:
                    self.next_hand_deadline = (time.time()
                                               + self.next_hand_timeout)
                if not self._all_humans_ready():
                    self._bump()
                    return {"ok": True, "waiting": True}
            return self._deal_hand()

    def _human_tokens(self):
        """Tokens that can ready up, including players joining next hand."""
        return set(self.tokens) | {token for token, _ in self.pending}

    def _all_humans_ready(self):
        humans = self._human_tokens()
        return bool(humans) and humans <= self.next_hand_ready

    def _deal_hand(self):
        for tok, name in self.pending:
            idx = self._seat_human(tok, name)
            if idx is None:
                break
        self.pending = [(t, nm) for t, nm in self.pending
                        if t not in self.tokens]
        if not self.tokens:
            self.next_hand_ready.clear()
            self.next_hand_deadline = None
            return {"error": "join first"}
        for i, p in enumerate(self.players):
            if p["chips"] <= 0:
                p["chips"] += self.buyin
                self.log.append(f"{p['name']} rebuys for {self.buyin}")
        self.hand_no += 1
        k = self.hand_no - 1
        self.seat_of = [(self.n - 1 - i - k) % self.n
                        for i in range(self.n)]
        self.player_at = [0] * self.n
        for i, s in enumerate(self.seat_of):
            self.player_at[s] = i
        stacks = [self.players[self.player_at[s]]["chips"]
                  for s in range(self.n)]
        self.hand = Hand(self.n, stacks, self.bp.sb, self.bp.bb,
                         rng=self.rng)
        self.result = None
        self.next_hand_ready.clear()
        self.next_hand_deadline = None
        self.log.append(f"— Hand #{self.hand_no} —")
        self.phase = "hand"
        self.last_bot_act = time.time()
        self._arm_deadline()
        self._bump()
        return {"ok": True}

    def reset_table(self, token):
        """Abort play and restore a fresh lobby without ejecting humans."""
        with self.lock:
            idx = self.tokens.get(token)
            if idx is None:
                return {"error": "not seated"}
            reset_by = self.players[idx]["name"]
            for p in self.players:
                p["chips"] = self.buyin
            self.phase = "lobby"
            self.hand = None
            self.hand_no = 0
            self.seat_of = None
            self.player_at = None
            self.result = None
            self.turn_deadline = None
            self.next_hand_ready.clear()
            self.next_hand_deadline = None
            self.last_bot_act = 0.0
            self.log.clear()
            self.log.append(f"{reset_by} stopped play and reset the table")
            self._bump()
            return {"ok": True}

    def _seat_name(self, s):
        p = self.players[self.player_at[s]]
        return f"{p['name']}·{POSITION_NAMES[self.n][s]}"

    def _arm_deadline(self):
        h = self.hand
        if h and not h.terminal and \
                self.players[self.player_at[h.to_act]]["kind"] == "human":
            self.turn_deadline = time.time() + self.turn_timeout
        else:
            self.turn_deadline = None

    def _apply(self, seat, token_id, action, suffix=""):
        desc = describe_action(self.hand, seat, token_id, action,
                               self.hand.to_call(seat))
        self.hand.apply(action, token_id)
        self.log.append(f"{self._seat_name(seat)} {desc}{suffix}")
        self.last_bot_act = time.time()
        self._arm_deadline()
        if self.hand.terminal:
            self._finish()
        self._bump()

    def tick(self):
        with self.lock:
            if self.phase != "hand" or self.hand.terminal:
                if self.phase != "hand":
                    self._prune_idle()
                if self.phase == "showdown" and \
                        self.next_hand_deadline is not None and \
                        time.time() >= self.next_hand_deadline:
                    self._deal_hand()
                return
            seat = self.hand.to_act
            player = self.players[self.player_at[seat]]
            now = time.time()
            if player["kind"] == "bot":
                if now - self.last_bot_act >= self.bot_delay:
                    tok, action = self.bot.act(self.hand)
                    self._apply(seat, tok, action)
            elif self.turn_deadline and now > self.turn_deadline:
                if self.hand.to_call(seat) == 0:
                    self._apply(seat, "c", ("c",), " (timed out)")
                else:
                    self._apply(seat, "f", ("f",), " (timed out)")

    def _finish(self):
        h = self.hand
        for s in range(self.n):
            self.players[self.player_at[s]]["chips"] += h.payoffs[s]
        reveal = [{"seat": s, "name": self._seat_name(s),
                   "cards": card_codes(h.hole[s]),
                   "status": player_status(h, s)} for s in range(self.n)]
        winners = [{"name": self._seat_name(s), "amount": a}
                   for s, a in h.winners_info]
        uncalled = None
        if h.uncalled:
            uncalled = {"name": self._seat_name(h.uncalled[0]),
                        "amount": h.uncalled[1]}
        self.result = {"reveal": reveal, "winners": winners,
                       "uncalled": uncalled,
                       "net": {str(s): h.payoffs[s] for s in range(self.n)}}
        self.phase = "showdown"
        self.turn_deadline = None
        self.next_hand_ready.clear()
        self.next_hand_deadline = None

    # ---- human actions ------------------------------------------------
    def act(self, token, data):
        with self.lock:
            if token not in self.tokens:
                return {"error": "not seated"}
            if self.phase != "hand" or self.hand.terminal:
                return {"error": "no hand running"}
            idx = self.tokens[token]
            seat = self.hand.to_act
            if self.player_at[seat] != idx:
                return {"error": "not your turn"}
            acts = dict((t, a) for t, a in playable_actions(self.hand))
            choice = data.get("action")
            if choice in acts:
                self._apply(seat, choice, acts[choice])
                return {"ok": True}
            if "raise_to" in data and any(a[0] == "r" for a in acts.values()):
                try:
                    target = int(data["raise_to"])
                except (TypeError, ValueError):
                    return {"error": "bad amount"}
                h = self.hand
                max_to = h.street_contrib[seat] + h.stacks[seat]
                min_to = min(h.current_bet + h.min_raise, max_to)
                if target >= max_to:
                    target = max_to
                elif target < min_to:
                    return {"error": f"minimum raise is to {min_to}"}
                tok = nearest_raise_token(h, target)
                self._apply(seat, tok, ("r", target))
                return {"ok": True}
            return {"error": "illegal action"}

    # ---- views --------------------------------------------------------
    def state_for(self, token):
        self.tick()
        with self.lock:
            idx = self.tokens.get(token)
            if idx is not None:
                self.players[idx]["last_seen"] = time.time()
            h = self.hand
            state = {
                "seq": self.seq,
                "phase": self.phase,
                "hand_no": self.hand_no,
                "seats_total": self.n,
                "log": list(self.log),
                "you": {"seated": idx is not None,
                        "pending": any(t == token for t, _ in self.pending)},
                "needs_password": bool(self.password),
                "players": [{"name": p["name"], "chips": p["chips"],
                             "is_bot": p["kind"] == "bot",
                             "you": i == idx}
                            for i, p in enumerate(self.players)],
            }
            if self.phase == "showdown":
                humans = self._human_tokens()
                state["next_hand"] = {
                    "ready": len(humans & self.next_hand_ready),
                    "total": len(humans),
                    "you_ready": token in self.next_hand_ready,
                    "deadline": (max(0, round(self.next_hand_deadline
                                              - time.time()))
                                 if self.next_hand_deadline is not None
                                 else None),
                }
            if h is None:
                return state
            reveal_all = self.phase == "showdown"
            my_seat = self.seat_of[idx] if idx is not None else None
            seats = []
            for s in range(self.n):
                p = self.players[self.player_at[s]]
                show = reveal_all or s == my_seat
                seats.append({
                    "seat": s,
                    "name": p["name"],
                    "position": POSITION_NAMES[self.n][s],
                    "chips": h.stacks[s],
                    "bet": h.street_contrib[s],
                    "folded": h.folded[s],
                    "fold_street": (STREET_LABELS[h.fold_street[s]].lower()
                                    if h.folded[s] else None),
                    "allin": h.allin[s],
                    "committed": h.contrib[s],
                    "is_bot": p["kind"] == "bot",
                    "you": s == my_seat,
                    "to_act": (not h.terminal and h.to_act == s),
                    "cards": card_codes(h.hole[s]) if show else None,
                })
            state.update({
                "street": STREET_LABELS[h.street],
                "board": card_codes(h.board),
                "pot": h.pot(),
                "seats": seats,
                "result": self.result,
            })
            if my_seat is not None:
                you = state["you"]
                you["seat"] = my_seat
                you["cards"] = card_codes(h.hole[my_seat])
                you["net"] = h.payoffs[my_seat] if h.terminal else None
                if h.board:
                    you["hand_so_far"] = category_name(
                        evaluate(h.hole[my_seat] + h.board))
                if not h.terminal and h.to_act == my_seat:
                    tc = h.to_call(my_seat)
                    acts = playable_actions(h)
                    you["is_turn"] = True
                    you["to_call"] = tc
                    you["pot_odds"] = (round(tc / (h.pot() + tc) * 100)
                                       if tc else None)
                    you["deadline"] = (max(0, round(self.turn_deadline
                                                    - time.time()))
                                       if self.turn_deadline else None)
                    you["actions"] = [
                        {"id": t, "label": action_label(h, my_seat, t, a)}
                        for t, a in acts]
                    if any(a[0] == "r" for _, a in acts):
                        max_to = h.street_contrib[my_seat] + h.stacks[my_seat]
                        you["raise_min"] = min(h.current_bet + h.min_raise,
                                               max_to)
                        you["raise_max"] = max_to
            return state

    def advice(self, token):
        with self.lock:
            idx = self.tokens.get(token)
            if idx is None or self.phase != "hand" or self.hand.terminal:
                return {"error": "no decision to advise on"}
            seat = self.seat_of[idx]
            if self.hand.to_act != seat:
                return {"error": "not your turn"}
            acts, probs, trained = spot_strategy(self.bp, self.hand, seat,
                                                 self.rng)
            items = sorted(
                ({"label": action_label(self.hand, seat, t, a),
                  "pct": round(p * 100, 1)}
                 for (t, a), p in zip(acts, probs)),
                key=lambda x: -x["pct"])
            out = {"mix": items, "trained": trained,
                   "cards": cards_str(self.hand.hole[seat])}
            if self.hand.board:
                eq = hand_equity(self.hand.hole[seat], self.hand.board,
                                 self.rng, trials=300)
                out["equity"] = round(eq * 100)
            return out
