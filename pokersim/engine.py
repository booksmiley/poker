"""No-Limit Hold'em hand engine for 3-6 players, integer chips.

Position convention (no separate button index): seat 0 = SB, seat 1 = BB,
..., seat n-1 = BTN. Preflop action starts at seat 2 (UTG); postflop at
seat 0. Callers rotate which position the human occupies between hands.

Actions passed to apply():
    ('f',)        fold
    ('c',)        check or call (calls all-in for less automatically)
    ('r', X)      raise TO a street-contribution of X (all-in if X uses
                  the whole stack)

Simplification vs. casino rules: any all-in raise reopens the action even
if it is below the minimum raise.
"""
import random

from .cards import new_deck
from .evaluator import evaluate

PREFLOP, FLOP, TURN, RIVER = 0, 1, 2, 3
STREET_NAMES = ["Preflop", "Flop", "Turn", "River"]


class Hand:
    def __init__(self, n_players, stack=200, sb=1, bb=2, rng=None, deck=None):
        assert 3 <= n_players <= 6, "supported table sizes: 3-6 players"
        self.n = n_players
        self.sb_amt, self.bb_amt = sb, bb
        self.rng = rng or random
        self.deck = deck[:] if deck is not None else new_deck(self.rng)
        self.hole = [[self.deck.pop(), self.deck.pop()] for _ in range(n_players)]
        self.board = []
        if isinstance(stack, (list, tuple)):
            assert len(stack) == n_players and all(s > 0 for s in stack)
            self.stacks = [int(s) for s in stack]
        else:
            self.stacks = [stack] * n_players
        self.contrib = [0] * n_players
        self.street_contrib = [0] * n_players
        self.folded = [False] * n_players
        self.fold_street = [None] * n_players   # street index when folded
        self.allin = [False] * n_players
        self.street = PREFLOP
        self.history = []          # abstract action tokens, '/' between streets
        self.terminal = False
        self.payoffs = None        # net chips per player once terminal
        self.winners_info = None   # [(player, amount)] for display
        self.uncalled = None       # (player, refunded amount) once terminal

        self._pay(0, min(sb, self.stacks[0]))
        self._pay(1, min(bb, self.stacks[1]))
        self.current_bet = bb
        self.min_raise = bb
        self.raises_this_street = 1  # the blind counts toward the cap
        self.acted = [False] * n_players
        self.to_act = 2 % n_players

    # ---- helpers ------------------------------------------------------
    def _pay(self, p, amount):
        amount = min(amount, self.stacks[p])
        self.stacks[p] -= amount
        self.contrib[p] += amount
        self.street_contrib[p] += amount
        if self.stacks[p] == 0:
            self.allin[p] = True

    def pot(self):
        return sum(self.contrib)

    def to_call(self, p):
        return min(self.current_bet - self.street_contrib[p], self.stacks[p])

    def active_players(self):
        return [p for p in range(self.n) if not self.folded[p]]

    def can_act(self, p):
        return not self.folded[p] and not self.allin[p]

    def clone(self):
        h = object.__new__(Hand)
        h.n, h.sb_amt, h.bb_amt, h.rng = self.n, self.sb_amt, self.bb_amt, self.rng
        h.deck = self.deck[:]
        h.hole = self.hole  # never mutated after the deal
        h.board = self.board[:]
        h.stacks = self.stacks[:]
        h.contrib = self.contrib[:]
        h.street_contrib = self.street_contrib[:]
        h.folded = self.folded[:]
        h.fold_street = self.fold_street[:]
        h.allin = self.allin[:]
        h.street = self.street
        h.history = self.history[:]
        h.terminal = self.terminal
        h.payoffs = self.payoffs
        h.winners_info = self.winners_info
        h.current_bet = self.current_bet
        h.min_raise = self.min_raise
        h.raises_this_street = self.raises_this_street
        h.acted = self.acted[:]
        h.to_act = self.to_act
        return h

    def history_str(self):
        return "".join(self.history)

    # ---- actions ------------------------------------------------------
    def apply(self, action, token):
        """Apply an action for self.to_act and advance the game."""
        assert not self.terminal
        p = self.to_act
        kind = action[0]
        if kind == "f":
            assert self.to_call(p) > 0, "cannot fold when checking is free"
            self.folded[p] = True
            self.fold_street[p] = self.street
        elif kind == "c":
            self._pay(p, self.to_call(p))
        elif kind == "r":
            target = min(action[1], self.street_contrib[p] + self.stacks[p])
            assert target > self.current_bet, "raise must exceed current bet"
            self._pay(p, target - self.street_contrib[p])
            self.min_raise = target - self.current_bet
            self.current_bet = target
            self.raises_this_street += 1
            for q in range(self.n):
                if q != p:
                    self.acted[q] = False
        else:
            raise ValueError(action)
        self.acted[p] = True
        self.history.append(token)
        self._advance(p)

    def _needs_action(self, p):
        return self.can_act(p) and (
            not self.acted[p] or self.street_contrib[p] < self.current_bet
        )

    def _advance(self, last):
        if len(self.active_players()) == 1:
            self._settle()
            return
        for i in range(1, self.n + 1):
            q = (last + i) % self.n
            if self._needs_action(q):
                self.to_act = q
                return
        self._next_street()

    def _next_street(self):
        while True:
            if self.street == RIVER:
                self._settle()
                return
            self.street += 1
            self.history.append("/")
            self.board.extend(
                self.deck.pop() for _ in range(3 if self.street == FLOP else 1)
            )
            self.street_contrib = [0] * self.n
            self.current_bet = 0
            self.min_raise = self.bb_amt
            self.raises_this_street = 0
            self.acted = [False] * self.n
            actors = [p for p in range(self.n) if self.can_act(p)]
            if len(actors) >= 2:
                self.to_act = actors[0]
                return
            # betting is over for good: run the board out

    # ---- showdown / settlement ---------------------------------------
    def _settle(self):
        self.terminal = True
        self.to_act = None
        # return the uncalled portion of the largest bet before building pots
        self.uncalled = None
        by_contrib = sorted(range(self.n), key=lambda p: self.contrib[p])
        top = by_contrib[-1]
        refund = self.contrib[top] - self.contrib[by_contrib[-2]]
        if refund > 0:
            self.contrib[top] -= refund
            self.stacks[top] += refund
            if self.allin[top]:
                self.allin[top] = False
            self.uncalled = (top, refund)
        net = [-c for c in self.contrib]
        active = self.active_players()
        if len(active) == 1:
            w = active[0]
            net[w] += self.pot()
            self.payoffs = net
            self.winners_info = [(w, self.pot())]
            return
        while len(self.board) < 5:
            self.board.append(self.deck.pop())
        scores = {p: evaluate(self.hole[p] + self.board) for p in active}
        won = [0] * self.n
        levels = sorted({c for c in self.contrib if c > 0})
        prev = 0
        for level in levels:
            amount = sum(min(c, level) - min(c, prev) for c in self.contrib)
            eligible = [p for p in active if self.contrib[p] >= level]
            if not eligible:  # everyone at this level folded: refund
                for p in range(self.n):
                    won[p] += min(self.contrib[p], level) - min(self.contrib[p], prev)
            else:
                best = max(scores[p] for p in eligible)
                winners = [p for p in eligible if scores[p] == best]
                share, rem = divmod(amount, len(winners))
                for j, p in enumerate(sorted(winners)):
                    won[p] += share + (1 if j < rem else 0)
            prev = level
        self.payoffs = [net[p] + won[p] for p in range(self.n)]
        self.winners_info = [(p, won[p]) for p in range(self.n) if won[p] > 0]
        self.showdown_scores = scores
