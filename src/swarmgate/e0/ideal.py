import math

import numpy as np

from .guards import all_guards
from .world import action_pool


class Ideal:
    def __init__(self, env_error_rate: float, reveal_rate: float):
        self.guards = all_guards()
        self.pool = action_pool()
        self.index = {a: i for i, a in enumerate(self.pool)}
        self.msg = np.array([[g.decide(a) for a in self.pool] for g in self.guards], dtype=object)
        self.D = np.array([[m is not None for m in row] for row in self.msg])
        self.is_cmd = np.array([g.basis == "command" for g in self.guards])
        n_cmd = int(self.is_cmd.sum())
        self.prior = np.where(self.is_cmd, 0.5 / n_cmd, 0.5 / (len(self.guards) - n_cmd))
        self.eps = env_error_rate
        self.reveal = reveal_rate
        signatures: dict = {}
        self.sig = np.array([signatures.setdefault(row.tobytes(), len(signatures)) for row in self.D])

    def likelihood(self, j: int, category: str, mode: str) -> np.ndarray:
        b = self.D[:, j]
        if category.startswith("deny:"):
            return (self.msg[:, j] == category[5:]).astype(float)
        if category == "deny":
            return b.astype(float)
        if category == "env":
            return np.where(b, 0.0, self.eps)
        if category == "err":
            return np.where(b, 1.0, self.eps)
        if category == "revealed":
            return np.where(b, self.reveal, 0.0)
        if mode == "fake_success":
            return np.where(b, 1.0 - self.reveal, 1.0 - self.eps)
        return np.where(b, 0.0, 1.0 - self.eps)

    def posterior(self, obs: list[tuple[int, str]], mode: str) -> np.ndarray:
        p = self.prior.copy()
        for j, category in obs:
            p = p * self.likelihood(j, category, mode)
        return p / p.sum()

    def predict(self, post: np.ndarray, actions: list[int]) -> np.ndarray:
        return post @ self.D[:, actions]

    def p_command(self, post: np.ndarray) -> float:
        return float(post[self.is_cmd].sum())

    def bits(self, post: np.ndarray, guard: int) -> float:
        same = self.sig == self.sig[guard]
        return math.log2(post[same].sum()) - math.log2(self.prior[same].sum())

    def termination_bits(self, guard: int, obs: list[tuple[int, str]], mode: str, threshold: int, delay: int, offset: int) -> float:
        idx = [j for j, _ in obs]
        n = len(idx)
        csum = np.cumsum(self.D[:, idx], axis=1)
        has = csum[:, -1] >= threshold
        first = np.where(has, np.argmax(csum >= threshold, axis=1) + 1, 0)
        seen = int(first[guard]) + offset if has[guard] else None
        if seen is not None and seen > n:
            seen = None
        if seen is None:
            lik = np.where(has, np.clip(first + delay - n, 0, delay + 1) / (delay + 1), 1.0)
        else:
            gap = seen - first
            lik = np.where(has & (gap >= 0) & (gap <= delay), 1.0 / (delay + 1), 0.0)
        base = self.posterior(obs, mode)
        updated = base * lik
        updated = updated / updated.sum()
        same = self.sig == self.sig[guard]
        return math.log2(updated[same].sum()) - math.log2(base[same].sum())
