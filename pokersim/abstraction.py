"""Action abstraction and information-set keys.

The CFR-trained game restricts raises to a few pot-fraction sizes so the
tree stays tractable:

    f = fold, c = check/call, h = raise ~1/2 pot, p = raise ~pot,
    a = all-in

Sized raises are capped per street; all-in stays available. Because every
abstract raise amount is a deterministic function of the action history,
an infoset key needs only (hand bucket, history string).
"""
import math

RAISE_SIZES = [("h", 0.5), ("p", 1.0)]
MAX_RAISES_PER_STREET = 4  # preflop the big blind counts as the first

TOKEN_NAMES = {
    "f": "Fold", "c": "Check/Call", "h": "Raise ½-pot", "p": "Raise pot",
    "a": "All-in",
}

from .equity import bucket


def abstract_actions(hand):
    """Legal abstract actions for hand.to_act as [(token, engine_action)]."""
    p = hand.to_act
    acts = []
    tc = hand.to_call(p)
    if tc > 0:
        acts.append(("f", ("f",)))
    acts.append(("c", ("c",)))
    stack = hand.stacks[p]
    if stack > tc:
        allin_to = hand.street_contrib[p] + stack
        if hand.raises_this_street < MAX_RAISES_PER_STREET:
            pot_after_call = hand.pot() + tc
            seen = set()
            for tok, frac in RAISE_SIZES:
                raise_by = max(int(round(frac * pot_after_call)), hand.min_raise)
                target = hand.current_bet + raise_by
                if target >= allin_to or target in seen:
                    continue
                seen.add(target)
                acts.append((tok, ("r", target)))
        if allin_to > hand.current_bet:
            acts.append(("a", ("r", allin_to)))
    return acts


def raising_is_dead(hand, p):
    """True when no other live player could respond to a raise — betting
    more than the call amount would only be returned uncalled."""
    return all(
        hand.folded[q] or hand.allin[q] for q in range(hand.n) if q != p
    )


def playable_actions(hand):
    """Actions worth offering at the real table: abstract_actions minus
    dead raises. (Training keeps the full set so infosets stay aligned.)"""
    acts = abstract_actions(hand)
    if raising_is_dead(hand, hand.to_act):
        acts = [(t, a) for t, a in acts if a[0] != "r"]
    return acts


def infoset_key(hand, p, rng=None):
    return bucket(hand.hole[p], hand.board, rng) + "|" + hand.history_str()


def nearest_raise_token(hand, target):
    """Abstract token whose raise amount is closest (log-scale) to a custom
    raise-to amount, so off-tree human bets stay in the AI's vocabulary."""
    best_tok, best_dist = "p", float("inf")
    for tok, action in abstract_actions(hand):
        if action[0] != "r":
            continue
        d = abs(math.log(target / action[1]))
        if d < best_dist:
            best_tok, best_dist = tok, d
    return best_tok
