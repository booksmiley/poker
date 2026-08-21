"""Blueprint persistence and lookup."""
import os
import pickle


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


def load_blueprint_data(path):
    with open(path, "rb") as f:
        return pickle.load(f)


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
        if node is None or len(node[1]) != n_actions:
            return None
        sums = node[1]
        total = sum(sums)
        if total <= 0.0:
            return None
        return [x / total for x in sums]
