"""Monte-Carlo hand-strength estimation and card bucketing.

Postflop hands are abstracted to an equity bucket: estimated equity vs one
random opponent (board rolled out to the river), quantized into N_BUCKETS
bins. Preflop hands use their canonical 169-class label directly.

This is the main approximation that makes multiplayer CFR tractable in
pure Python.
"""
import random

from .cards import preflop_class
from .evaluator import evaluate

N_BUCKETS = 10
# Monte-Carlo trials per equity estimate, by number of board cards dealt.
TRIALS = {3: 28, 4: 28, 5: 44}

_cache = {}
_CACHE_MAX = 500_000


def hand_equity(hole, board, rng=None, trials=None):
    """Estimated P(win) + 0.5*P(tie) vs one random opponent hand,
    with the board rolled out to the river."""
    rng = rng or random
    trials = trials or TRIALS[len(board)]
    dead = set(hole) | set(board)
    remaining = [c for c in range(52) if c not in dead]
    need_board = 5 - len(board)
    my_base = list(hole) + list(board)
    score = 0.0
    for _ in range(trials):
        draw = rng.sample(remaining, 2 + need_board)
        opp = draw[:2]
        runout = draw[2:]
        my = evaluate(my_base + runout)
        their = evaluate(opp + list(board) + runout)
        if my > their:
            score += 1.0
        elif my == their:
            score += 0.5
    return score / trials


def bucket(hole, board, rng=None):
    """Abstraction bucket for a hand: 169-class label preflop,
    equity decile string postflop."""
    if not board:
        return preflop_class(hole)
    key = (min(hole), max(hole), tuple(sorted(board)))
    b = _cache.get(key)
    if b is None:
        eq = hand_equity(hole, board, rng)
        b = str(min(N_BUCKETS - 1, int(eq * N_BUCKETS)))
        if len(_cache) >= _CACHE_MAX:
            # flush rather than stop storing: repeats inside the current
            # traversal are the hits that matter, so keep accepting entries
            _cache.clear()
        _cache[key] = b
    return b
