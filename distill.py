#!/usr/bin/env python3
"""Export a small play-only blueprint fit for GitHub.

Drops training regrets, prunes infosets outside the top --mass fraction
of accumulated strategy weight, quantizes probabilities to uint8, and
gzips. Files over --max-part-mb are split into .partNN chunks that the
game recombines automatically.

    python3 distill.py --players 4
    python3 play.py --players 4 --blueprint blueprints/bp_4p.gto
"""
import argparse
import os

from pokersim.strategy import load_blueprint_data, save_distilled


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--players", type=int, default=4, choices=[3, 4, 5, 6])
    ap.add_argument("--blueprint", default=None, help="full .pkl to distill")
    ap.add_argument("--out", default=None)
    ap.add_argument("--mass", type=float, default=0.999,
                    help="fraction of strategy weight to preserve")
    ap.add_argument("--max-part-mb", type=int, default=90,
                    help="split output into parts no larger than this")
    args = ap.parse_args()

    src = args.blueprint or os.path.join("blueprints", f"bp_{args.players}p.pkl")
    out = args.out or os.path.splitext(src)[0] + ".gto"
    print(f"Loading {src} ...")
    data = load_blueprint_data(src)
    if data.get("format"):
        raise SystemExit(f"{src} is already distilled")
    total = len(data["table"])
    print(f"{total:,} infosets at {data['iters_done']:,} iterations; distilling...")
    kept, files = save_distilled(
        out, data, mass=args.mass,
        max_part_bytes=args.max_part_mb * 1024 * 1024,
    )
    print(f"Kept {kept:,}/{total:,} infosets ({kept / total * 100:.0f}%).")
    for f in files:
        print(f"  {f}  ({os.path.getsize(f) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
