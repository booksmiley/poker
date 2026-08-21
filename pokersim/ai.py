"""Blueprint-following bot agent."""
import random

from .abstraction import abstract_actions, infoset_key, raising_is_dead


def fallback_probs(tokens):
    """Sane default for spots training never reached: mostly passive."""
    weights = {"f": 0.25, "c": 0.60, "h": 0.08, "p": 0.05, "a": 0.02}
    w = [weights.get(t, 0.05) for t in tokens]
    s = sum(w)
    return [x / s for x in w]


def spot_strategy(blueprint, hand, p, rng=None):
    """(actions, probs, trained?) for player p's current decision.

    The blueprint is queried with the full abstract action set (so trained
    tables always line up); dead raises — no live opponent could call —
    are then filtered out with the remaining mix renormalized."""
    acts = abstract_actions(hand)
    key = infoset_key(hand, p, rng)
    probs = blueprint.probs(key, len(acts))
    trained = probs is not None
    if not trained:
        probs = fallback_probs([t for t, _ in acts])
    if raising_is_dead(hand, p):
        keep = [i for i, (t, a) in enumerate(acts) if a[0] != "r"]
        acts = [acts[i] for i in keep]
        kept = [probs[i] for i in keep]
        total = sum(kept)
        probs = (
            [x / total for x in kept] if total > 0
            else [1.0 / len(kept)] * len(kept)
        )
    return acts, probs, trained


class BotAgent:
    def __init__(self, blueprint, rng=None):
        self.blueprint = blueprint
        self.rng = rng or random

    def act(self, hand):
        """Sample (token, engine_action) from the blueprint's mix."""
        acts, probs, _ = spot_strategy(self.blueprint, hand, hand.to_act, self.rng)
        r = self.rng.random()
        acc = 0.0
        for i, pr in enumerate(probs):
            acc += pr
            if r < acc:
                return acts[i]
        return acts[-1]
