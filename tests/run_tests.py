#!/usr/bin/env python3
"""Self-contained test suite: python3 tests/run_tests.py"""
import itertools
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pokersim.abstraction import abstract_actions
from pokersim.cards import parse_card
from pokersim.cfr import Trainer
from pokersim.engine import FLOP, Hand
from pokersim.equity import hand_equity
from pokersim.evaluator import evaluate
from pokersim.strategy import Blueprint


def cards(text):
    return [parse_card(t) for t in text.split()]


def test_evaluator_known_hands():
    def score(text):
        return evaluate(cards(text))

    order = [
        "2c 3d 5h 9s Js Ah Kd",   # ace high
        "2c 3d 5h 9s Js 9h Kd",   # pair of nines
        "2c 3d 9c 9s Js Jh Kd",   # two pair J/9
        "2c 3d 9c 9s 9h Jh Kd",   # trips
        "2c 3d 4h 5s 6s Jh Kd",   # straight to 6
        "2c 7c 9c Jc Kc 3d 4h",   # K-high flush
        "9c 9s 9h Jd Jh 2c Kd",   # full house
        "9c 9s 9h 9d Jh 2c Kd",   # quads
        "5c 6c 7c 8c 9c 2d Kd",   # straight flush
    ]
    scores = [score(t) for t in order]
    assert scores == sorted(scores), "hand categories out of order"

    # wheel beats nothing above but is a straight; A2345 < 23456
    assert score("Ac 2d 3h 4s 5s Jh 9d") < score("2c 3d 4h 5s 6s Jh 9d")
    # kicker decides: AK vs AQ on paired board
    assert score("Ac Kd 9c 9s 5h 3d 2c") > score("Ac Qd 9c 9s 5h 3d 2c")
    # board plays: both split with same score
    b = "Ac Kc Qc Jc Tc"
    assert evaluate(cards(b + " 2d 3d")) == evaluate(cards(b + " 9h 8h"))
    # two pair uses the best two of three pairs, best remaining kicker
    assert score("9c 9d 5h 5s Kc Kd Ah") > score("9c 9d 5h 5s Kc Kd 2h")
    print("ok  evaluator known hands")


def test_evaluator_consistency():
    rng = random.Random(42)
    for _ in range(3000):
        seven = rng.sample(range(52), 7)
        direct = evaluate(seven)
        best5 = max(evaluate(list(c)) for c in itertools.combinations(seven, 5))
        assert direct == best5, f"7-card mismatch on {seven}"
    print("ok  evaluator 7-card == best 5-of-7 (3000 random)")


def build_deck(hole_texts, board_text, n):
    """Deck list such that player i receives hole_texts[i] and the board
    runs out board_text. Engine pops from the END of the list."""
    deal = []
    for t in hole_texts:
        deal.extend(cards(t))
    deal.extend(cards(board_text))
    used = set(deal)
    rest = [c for c in range(52) if c not in used]
    return rest + deal[::-1]


def test_engine_walkthrough():
    # 4 players limp to a checked-down board; verify blinds, order, pot.
    deck = build_deck(["Ac Ad", "Kc Kd", "Qc Qd", "Jc Jd"], "2c 7d 9h 3s 5s", 4)
    h = Hand(4, stack=200, deck=deck)
    assert h.to_act == 2 and h.pot() == 3
    h.apply(("c",), "c")            # UTG limps
    h.apply(("c",), "c")            # BTN limps
    h.apply(("c",), "c")            # SB completes
    assert h.street == 0            # BB still has the option
    h.apply(("c",), "c")            # BB checks
    assert h.street == FLOP and h.to_act == 0 and h.pot() == 8
    for _ in range(3):              # check flop, turn, river
        for _ in range(4):
            h.apply(("c",), "c")
    assert h.terminal
    # AA holds on 2 7 9 3 5
    assert h.payoffs[0] == 6 and sum(h.payoffs) == 0
    print("ok  engine limped walkthrough")


def test_engine_uncalled_bet():
    deck = build_deck(["Ac Ad", "Kc Kd", "Qc Qd"], "2c 7d 9h 3s 5s", 3)
    h = Hand(3, stack=200, deck=deck)
    h.apply(("r", 200), "a")        # BTN shoves
    h.apply(("f",), "f")            # SB folds
    h.apply(("f",), "f")            # BB folds
    assert h.terminal and h.payoffs == [-1, -2, 3]
    assert h.uncalled == (2, 198)   # shove minus the 2 blinds it wins
    assert h.winners_info == [(2, 5)]
    assert h.fold_street == [0, 0, None]
    print("ok  engine uncalled bet returned")


def test_dead_raises_and_showdown_refund():
    from pokersim.abstraction import abstract_actions, playable_actions

    # BB is all-in from posting the blind with 2 chips
    deck = build_deck(["Ac Ad", "Kc Kd", "Qc Qd"], "2c 7d 9h 3s 5s", 3)
    h = Hand(3, stack=[200, 2, 200], deck=deck)
    h.apply(("f",), "f")            # BTN folds
    assert h.to_act == 0            # SB vs an all-in player only
    assert any(t == "h" for t, _ in abstract_actions(h))
    assert [t for t, _ in playable_actions(h)] == ["f", "c"]
    h.apply(("c",), "c")
    assert h.terminal and h.uncalled is None
    assert h.payoffs == [2, -2, 0]  # AA beats KK for the 4-chip pot

    # same spot, but SB raises anyway: the excess must come back as a refund
    h = Hand(3, stack=[200, 2, 200], deck=build_deck(
        ["Ac Ad", "Kc Kd", "Qc Qd"], "2c 7d 9h 3s 5s", 3))
    h.apply(("f",), "f")
    h.apply(("r", 6), "h")
    assert h.terminal
    assert h.uncalled == (0, 4)
    assert h.winners_info == [(0, 4)]
    assert h.payoffs == [2, -2, 0]
    print("ok  dead raises filtered + showdown refund labeled")


def test_engine_side_pots():
    deck = build_deck(["As Ah", "Ks Kh", "Qs Qh"], "2c 3d 7c 8d 4h", 3)
    # unequal stacks: SB 50 total, BB 100 total, BTN 200
    h = Hand(3, stack=[50, 100, 200], deck=deck)
    h.apply(("r", 200), "a")        # BTN all-in 200
    h.apply(("c",), "c")            # SB calls for 50 total
    h.apply(("c",), "c")            # BB calls for 100 total
    assert h.terminal
    # AA wins main pot 150, KK wins side pot 100, BTN gets 100 back
    assert h.payoffs == [100, 0, -100], h.payoffs
    print("ok  engine side pots")


def test_engine_random_zero_sum():
    rng = random.Random(7)
    for _ in range(2000):
        n = rng.randint(3, 6)
        h = Hand(n, stack=200, rng=rng)
        while not h.terminal:
            acts = abstract_actions(h)
            tok, action = rng.choice(acts)
            h.apply(action, tok)
        assert sum(h.payoffs) == 0
        assert all(p >= -200 for p in h.payoffs)
        assert all(s >= 0 for s in h.stacks)
    print("ok  engine zero-sum over 2000 random hands")


def test_fast_evaluator_agreement():
    from pokersim import equity
    if not equity.FAST_EVAL:
        print("skip fast-evaluator agreement (phevaluator not installed)")
        return
    from pokersim.evaluator import evaluate
    rng = random.Random(5)
    for _ in range(4000):
        a = rng.sample(range(52), 7)
        b = rng.sample(range(52), 7)
        ours = (evaluate(a) > evaluate(b)) - (evaluate(a) < evaluate(b))
        fast = (equity._strength(a) > equity._strength(b)) - (
            equity._strength(a) < equity._strength(b))
        assert ours == fast, (a, b)
    print("ok  fast evaluator ordering matches pure-python (4000 pairs)")


def test_equity_sanity():
    rng = random.Random(3)
    strong = hand_equity(cards("As Ah"), cards("2c 7d 9h"), rng, trials=400)
    weak = hand_equity(cards("2s 7h"), cards("Ac Kd 9h"), rng, trials=400)
    assert strong > 0.80, strong
    assert weak < 0.40, weak
    print(f"ok  equity sanity (AA on low flop {strong:.2f}, 72o on AK9 {weak:.2f})")


def test_distilled_blueprint_roundtrip():
    from pokersim.strategy import Blueprint, load_blueprint_data, save_distilled

    tr = Trainer(3, seed=19)
    tr.run(15, log_every=0)
    tmp = tempfile.mkdtemp()
    full_path = os.path.join(tmp, "bp.pkl")
    tr.save(full_path)
    data = load_blueprint_data(full_path)
    full = Blueprint(data)

    # tiny part size forces the split-and-recombine path
    dist_path = os.path.join(tmp, "bp.gto")
    kept, files = save_distilled(dist_path, data, mass=1.0, max_part_bytes=4096)
    assert len(files) > 1 and all(".part" in f for f in files)
    dist = Blueprint.load(dist_path)
    assert dist.n_players == 3 and len(dist.table) == kept
    checked = 0
    for k, node in full.table.items():
        n = len(node[1])
        pf, pd = full.probs(k, n), dist.probs(k, n)
        if pf is None or pd is None:
            continue
        assert max(abs(a - b) for a, b in zip(pf, pd)) < 0.01
        checked += 1
    assert checked > 50
    print(f"ok  distilled blueprint round-trip ({len(files)} parts, "
          f"{checked} keys within 1%)")


def test_mini_cfr_and_blueprint():
    tr = Trainer(3, seed=11)
    tr.run(15, log_every=0)
    assert len(tr.table) > 50
    for regrets, sums in tr.table.values():
        assert all(x == x for x in regrets)  # no NaNs
        assert all(x >= 0 for x in sums)
    path = os.path.join(tempfile.mkdtemp(), "bp.pkl")
    tr.save(path)
    bp = Blueprint.load(path)
    assert bp.n_players == 3 and bp.iters_done == 15
    # every trained key yields a probability vector summing to ~1
    checked = 0
    for key, node in bp.table.items():
        pr = bp.probs(key, len(node[1]))
        if pr is not None:
            assert abs(sum(pr) - 1) < 1e-9
            checked += 1
    assert checked > 0
    print(f"ok  mini CFR run ({len(tr.table)} infosets) + blueprint round-trip")


if __name__ == "__main__":
    test_evaluator_known_hands()
    test_evaluator_consistency()
    test_engine_walkthrough()
    test_engine_uncalled_bet()
    test_dead_raises_and_showdown_refund()
    test_engine_side_pots()
    test_engine_random_zero_sum()
    test_fast_evaluator_agreement()
    test_equity_sanity()
    test_distilled_blueprint_roundtrip()
    test_mini_cfr_and_blueprint()
    print("\nall tests passed")
