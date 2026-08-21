#!/usr/bin/env python3
"""Train (or continue training) a blueprint strategy.

Examples:
    python3 train.py --players 4 --iters 20000
    python3 train.py --players 6 --iters 100000 --resume
"""
import argparse
import os

from pokersim.cfr import Trainer


def default_path(n):
    return os.path.join("blueprints", f"bp_{n}p.pkl")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--players", type=int, default=4, choices=[3, 4, 5, 6])
    ap.add_argument("--iters", type=int, default=20000)
    ap.add_argument("--stack", type=int, default=200)
    ap.add_argument("--sb", type=int, default=1)
    ap.add_argument("--bb", type=int, default=2)
    ap.add_argument("--out", default=None, help="output .pkl path")
    ap.add_argument("--resume", action="store_true",
                    help="continue training an existing blueprint")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--save-every", type=int, default=2000)
    args = ap.parse_args()

    path = args.out or default_path(args.players)
    if args.resume and os.path.exists(path):
        trainer = Trainer.from_saved(path, seed=args.seed)
        print(f"Resuming {path} at iteration {trainer.iters_done:,} "
              f"({len(trainer.table):,} infosets)")
    else:
        trainer = Trainer(args.players, args.stack, args.sb, args.bb, seed=args.seed)
        print(f"Training fresh {args.players}-player blueprint -> {path}")

    print(f"Running {args.iters:,} MCCFR iterations "
          f"(each = {trainer.n} traversals)...")
    trainer.run(args.iters, save_path=path, save_every=args.save_every)
    print(f"Saved {path}: {trainer.iters_done:,} total iterations, "
          f"{len(trainer.table):,} infosets.")


if __name__ == "__main__":
    main()
