"""External-sampling Monte-Carlo CFR over the abstracted hold'em game.

Each iteration deals one fresh hand per traversing player. At the
traverser's decision nodes every abstract action is explored; everyone
else samples from their current regret-matched strategy. Average
strategies use linear weighting (iteration t counts t times), which
speeds up convergence.

Multiplayer caveat: CFR is only guaranteed to reach a Nash equilibrium in
two-player zero-sum games. For 3+ players this produces a strong
approximate equilibrium in practice (the same approach as Pluribus's
blueprint), which is the accepted practical meaning of "GTO bot" at a
multiway table.
"""
import random
import time

from .abstraction import abstract_actions, infoset_key
from .engine import Hand
from .strategy import load_blueprint_data, save_blueprint


def regret_matching(regrets):
    pos = [r if r > 0.0 else 0.0 for r in regrets]
    s = sum(pos)
    if s <= 0.0:
        return [1.0 / len(regrets)] * len(regrets)
    return [x / s for x in pos]


class Trainer:
    def __init__(self, n_players, stack=200, sb=1, bb=2, seed=None):
        self.n = n_players
        self.stack, self.sb, self.bb = stack, sb, bb
        self.rng = random.Random(seed)
        self.table = {}   # key -> [regrets, weighted strategy sums]
        self.iters_done = 0

    @classmethod
    def from_saved(cls, path, seed=None):
        data = load_blueprint_data(path)
        tr = cls(data["n_players"], data["stack"], data["sb"], data["bb"], seed)
        tr.table = data["table"]
        tr.iters_done = data["iters_done"]
        return tr

    # ---- core recursion ----------------------------------------------
    def _node(self, key, n_actions):
        node = self.table.get(key)
        if node is None:
            node = [[0.0] * n_actions, [0.0] * n_actions]
            self.table[key] = node
        return node

    def _traverse(self, hand, traverser, weight):
        if hand.terminal:
            return hand.payoffs[traverser]
        p = hand.to_act
        acts = abstract_actions(hand)
        key = infoset_key(hand, p, self.rng)
        node = self._node(key, len(acts))
        sigma = regret_matching(node[0])

        if p == traverser:
            utils = []
            node_util = 0.0
            for i, (tok, action) in enumerate(acts):
                nxt = hand.clone()
                nxt.apply(action, tok)
                u = self._traverse(nxt, traverser, weight)
                utils.append(u)
                node_util += sigma[i] * u
            regrets = node[0]
            for i in range(len(acts)):
                regrets[i] += utils[i] - node_util
            return node_util

        # opponent node: accumulate average strategy, sample one action
        sums = node[1]
        for i in range(len(acts)):
            sums[i] += weight * sigma[i]
        r = self.rng.random()
        acc = 0.0
        idx = len(acts) - 1
        for i, s in enumerate(sigma):
            acc += s
            if r < acc:
                idx = i
                break
        tok, action = acts[idx]
        hand.apply(action, tok)  # hand is owned by this branch
        return self._traverse(hand, traverser, weight)

    # ---- training loop -----------------------------------------------
    DISCOUNT_EVERY = 1000

    def _discount(self, t):
        """Linear-CFR style discount: early (noisy) regrets and strategy
        weight decay relative to later iterations."""
        factor = t / (t + self.DISCOUNT_EVERY)
        for regrets, sums in self.table.values():
            for i in range(len(regrets)):
                regrets[i] *= factor
                sums[i] *= factor

    def run(self, iters, log_every=200, save_path=None, save_every=2000):
        start = time.time()
        first = self.iters_done + 1
        for t in range(first, first + iters):
            for traverser in range(self.n):
                hand = Hand(self.n, self.stack, self.sb, self.bb, rng=self.rng)
                self._traverse(hand, traverser, float(t))
            self.iters_done = t
            if t % self.DISCOUNT_EVERY == 0:
                self._discount(t)
            done = t - first + 1
            if log_every and done % log_every == 0:
                rate = done / (time.time() - start)
                print(
                    f"  iter {t:>7}  |  {len(self.table):>8,} infosets"
                    f"  |  {rate:5.1f} it/s"
                )
            if save_path and save_every and done % save_every == 0:
                self.save(save_path)
        if save_path:
            self.save(save_path)

    def save(self, path):
        save_blueprint(path, self)
