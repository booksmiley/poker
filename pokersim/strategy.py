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


def save_blueprint(path, trainer):
    data = {
        "n_players": trainer.n,
        "stack": trainer.stack,
        "sb": trainer.sb,
        "bb": trainer.bb,
        "iters_done": trainer.iters_done,
        "table": trainer.table,
    }
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


def save_distilled(path, data, mass=0.999, max_part_bytes=90 * 1024 * 1024):
    """Write a play-only blueprint: drop regrets, prune infosets outside
    the top `mass` fraction of strategy weight, quantize probabilities to
    uint8. Returns (entries_kept, file_list)."""
    table = data["table"]
    totals = sorted(t for t in (sum(n[1]) for n in table.values()) if t > 0)
    cutoff_mass = sum(totals) * (1.0 - mass)
    acc = 0.0
    thresh = 0.0
    for t in totals:
        acc += t
        if acc > cutoff_mass:
            thresh = t
            break

    packed = {}
    for key, node in table.items():
        sums = node[1]
        tot = sum(sums)
        if tot < thresh or tot <= 0:
            continue
        packed[key] = bytes(min(255, round(x / tot * 255)) for x in sums)

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
    return len(packed), files


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
