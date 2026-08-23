"""Blueprint persistence and lookup.

Two on-disk formats:

- Full trainer state (``bp_4p.pkl``): plain pickle with regrets and
  strategy sums. Large; supports resuming training. Kept out of git.
- Distilled play blueprint (``bp_4p.gto``): gzip-compressed pickle with
  only quantized average-strategy bytes per infoset — ~10x smaller,
  loads faster, cannot resume training. If bigger than a size cap it is
  written as ``bp_4p.gto.part00``, ``.part01``, ... and the loader
  transparently concatenates the parts (GitHub rejects files >100MB).
"""
import glob
import gzip
import os
import pickle

DIST_FORMAT = "gto-dist-1"


def trainer_data(trainer):
    return {
        "n_players": trainer.n,
        "stack": trainer.stack,
        "sb": trainer.sb,
        "bb": trainer.bb,
        "iters_done": trainer.iters_done,
        "table": trainer.table,
    }


def save_blueprint(path, trainer):
    data = trainer_data(trainer)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)


def blueprint_exists(path):
    return os.path.exists(path) or bool(glob.glob(path + ".part*"))


def _read_blob(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    parts = sorted(glob.glob(path + ".part*"))
    if parts:
        return b"".join(open(p, "rb").read() for p in parts)
    raise FileNotFoundError(path)


def load_blueprint_data(path):
    blob = _read_blob(path)
    if blob[:2] == b"\x1f\x8b":  # gzip magic: distilled format
        blob = gzip.decompress(blob)
    return pickle.loads(blob)


def save_distilled(path, data, mass=0.999, max_part_bytes=90 * 1024 * 1024,
                   max_entries=None):
    """Write a play-only blueprint: drop regrets, prune infosets outside
    the top `mass` fraction of strategy weight (and, if `max_entries` is
    set, keep at most that many highest-weight entries — used to fit small
    servers), quantize probabilities to uint8.
    Returns (entries_kept, file_list, mass_fraction_kept)."""
    table = data["table"]
    totals = sorted(t for t in (sum(n[1]) for n in table.values()) if t > 0)
    grand_total = sum(totals)
    cutoff_mass = grand_total * (1.0 - mass)
    acc = 0.0
    thresh = 0.0
    for t in totals:
        acc += t
        if acc > cutoff_mass:
            thresh = t
            break
    tie_budget = None
    if max_entries and max_entries < len(totals):
        import bisect
        thresh = max(thresh, totals[-max_entries])
        # entries strictly above the threshold all fit; entries exactly AT
        # it may be tied — keep only as many of those as the cap allows
        above = len(totals) - bisect.bisect_right(totals, thresh)
        tie_budget = max_entries - above

    packed = {}
    mass_kept = 0.0
    for key, node in table.items():
        sums = node[1]
        tot = sum(sums)
        if tot < thresh or tot <= 0:
            continue
        if tot == thresh and tie_budget is not None:
            if tie_budget <= 0:
                continue
            tie_budget -= 1
        packed[key] = bytes(min(255, round(x / tot * 255)) for x in sums)
        mass_kept += tot

    out = {
        "format": DIST_FORMAT,
        "n_players": data["n_players"],
        "stack": data["stack"],
        "sb": data["sb"],
        "bb": data["bb"],
        "iters_done": data["iters_done"],
        "table": packed,
    }
    blob = gzip.compress(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL), 6)

    # clear any stale single-file/part layout, then write the new one
    for old in [path] + glob.glob(path + ".part*"):
        if os.path.exists(old):
            os.remove(old)
    files = []
    if len(blob) <= max_part_bytes:
        with open(path, "wb") as f:
            f.write(blob)
        files.append(path)
    else:
        for i in range(0, len(blob), max_part_bytes):
            part = f"{path}.part{i // max_part_bytes:02d}"
            with open(part, "wb") as f:
                f.write(blob[i:i + max_part_bytes])
            files.append(part)
    return len(packed), files, (mass_kept / grand_total if grand_total else 0.0)


class Blueprint:
    """Read-only average-strategy view of a trained table."""

    def __init__(self, data):
        self.n_players = data["n_players"]
        self.stack = data["stack"]
        self.sb = data["sb"]
        self.bb = data["bb"]
        self.iters_done = data["iters_done"]
        self.table = data["table"]

    @classmethod
    def load(cls, path):
        return cls(load_blueprint_data(path))

    def probs(self, key, n_actions):
        """Average strategy at an infoset, or None if never trained."""
        node = self.table.get(key)
        if node is None:
            return None
        if isinstance(node, bytes):  # distilled: quantized uint8 weights
            if len(node) != n_actions:
                return None
            total = sum(node)
            return [b / total for b in node] if total else None
        if len(node[1]) != n_actions:
            return None
        sums = node[1]
        total = sum(sums)
        if total <= 0.0:
            return None
        return [x / total for x in sums]
