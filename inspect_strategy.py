#!/usr/bin/env python3
"""Peek inside a trained blueprint.

Show the strategy at one spot (hand class + action history):
    python3 inspect_strategy.py --key "AA|"        # UTG first decision
    python3 inspect_strategy.py --key "AKs|p"      # facing a pot-size open

Show a 13x13 preflop chart of the dominant action for a betting history:
    python3 inspect_strategy.py --chart ""         # UTG first in
    python3 inspect_strategy.py --chart "ff"       # folded to SB (4-max)

History tokens: f fold, c check/call, h half-pot raise, p pot raise,
a all-in, / next street.
"""
import argparse
import os

from pokersim.cards import RANK_CHARS
from pokersim.strategy import Blueprint

ACTION_ORDER = "fchpa"  # for display only


def spot_report(bp, key):
    node = bp.table.get(key)
    if node is None:
        print(f"'{key}' was never reached in training")
        return
    probs = bp.probs(key, len(node[1]))
    if probs is None:
        print(f"'{key}' has no accumulated strategy yet")
        return
    print(f"{key}  ({sum(node[1]):.0f} strategy weight)")
    for i, pr in enumerate(probs):
        bar = "█" * int(round(pr * 30))
        print(f"  action {i}: {pr * 100:5.1f}%  {bar}")
    print("(action order matches the legal-action list: fold, check/call,")
    print(" then raise sizes small->large, all-in last)")


def dominant_char(bp, key):
    node = bp.table.get(key)
    if node is None:
        return "."
    probs = bp.probs(key, len(node[1]))
    if probs is None:
        return "."
    # rebuild token order: f only if facing a bet; preflop always is
    n = len(probs)
    tokens = ["f", "c", "h", "p", "a"][:n] if n >= 2 else ["c"]
    best = max(range(n), key=lambda i: probs[i])
    return tokens[best].upper()


def chart(bp, history):
    print(f"Dominant preflop action after history '{history}'")
    print("(F fold, C call, H half-pot raise, P pot raise, A all-in, . unseen)\n")
    ranks = RANK_CHARS[::-1]  # A first
    print("     " + "  ".join(ranks))
    for i, r1 in enumerate(ranks):
        row = []
        for j, r2 in enumerate(ranks):
            if i == j:
                label = r1 + r2
            elif i < j:
                label = r1 + r2 + "s"   # upper triangle: suited
            else:
                label = r2 + r1 + "o"   # lower triangle: offsuit
            row.append(dominant_char(bp, label + "|" + history))
        print(f"  {r1}  " + "  ".join(row))
    print("\nupper triangle = suited, lower = offsuit, diagonal = pairs")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--blueprint", default=os.path.join("blueprints", "bp_4p.pkl"))
    ap.add_argument("--key", default=None)
    ap.add_argument("--chart", default=None, metavar="HISTORY")
    args = ap.parse_args()

    bp = Blueprint.load(args.blueprint)
    print(f"{args.blueprint}: {bp.n_players} players, "
          f"{bp.iters_done:,} iterations, {len(bp.table):,} infosets\n")
    if args.key is not None:
        spot_report(bp, args.key)
    if args.chart is not None:
        chart(bp, args.chart)
    if args.key is None and args.chart is None:
        chart(bp, "")


if __name__ == "__main__":
    main()
