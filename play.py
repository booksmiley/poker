#!/usr/bin/env python3
"""Play No-Limit Hold'em against approximate-GTO bots in the shell.

Examples:
    python3 play.py --players 4
    python3 play.py --players 6 --blueprint blueprints/bp_6p.pkl
"""
import argparse
import os

from pokersim.cfr import Trainer
from pokersim.cli import run_session
from pokersim.strategy import Blueprint, blueprint_exists


def default_path(n):
    """Prefer the distilled .gto — it plays the same strategy (<1%
    quantization error) but loads in seconds instead of a minute once the
    full training checkpoint grows large. Pass --blueprint for the .pkl."""
    dist = os.path.join("blueprints", f"bp_{n}p.gto")
    full = os.path.join("blueprints", f"bp_{n}p.pkl")
    if blueprint_exists(dist):
        return dist
    return full


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--players", type=int, default=4, choices=[3, 4, 5, 6])
    ap.add_argument("--blueprint", default=None, help="trained .pkl path")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--hands", type=int, default=None,
                    help="stop after this many hands (default: play until quit)")
    ap.add_argument("--ui", choices=["table", "text"], default="table",
                    help="table = round-table view (default), text = scrolling log")
    ap.add_argument("--reset-stacks", action="store_true",
                    help="reset every stack to the buy-in each hand "
                         "(matches training conditions exactly)")
    ap.add_argument("--auto-train-iters", type=int, default=3000,
                    help="if no blueprint exists, quick-train this many iterations")
    args = ap.parse_args()

    path = args.blueprint or default_path(args.players)
    if not blueprint_exists(path):
        print(f"No blueprint at {path} — quick-training "
              f"{args.auto_train_iters:,} iterations first.")
        print("(For stronger bots, run e.g. "
              f"`python3 train.py --players {args.players} --iters 50000`.)")
        trainer = Trainer(args.players, seed=args.seed)
        trainer.run(args.auto_train_iters, save_path=path)
        print(f"Saved starter blueprint to {path}.\n")

    bp = Blueprint.load(path)
    if bp.n_players != args.players and args.blueprint is None:
        raise SystemExit(f"{path} is for {bp.n_players} players")
    run_session(bp, seed=args.seed, max_hands=args.hands, ui=args.ui,
                persistent=not args.reset_stacks)


if __name__ == "__main__":
    main()
