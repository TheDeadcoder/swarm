import random

from .feedback import draw, is_failure, observe
from .ideal import Ideal


def _pick(rng: random.Random, preferred: list[int], fallback: list[int], n: int) -> list[int]:
    chosen = rng.sample(preferred, min(n, len(preferred)))
    rest = [i for i in fallback if i not in set(chosen)]
    return chosen + rng.sample(rest, n - len(chosen))


def build(cfg: dict, ideal: Ideal) -> list[dict]:
    rng = random.Random(cfg["seed"])
    pool = ideal.pool
    prior_pred = ideal.prior @ ideal.D
    informative = {i for i, p in enumerate(prior_pred) if 0.15 <= p <= 0.85}
    by_basis = {b: [i for i, g in enumerate(ideal.guards) if g.basis == b] for b in ("command", "data")}
    chosen = [g for b in ("command", "data") for g in rng.sample(by_basis[b], cfg["n_guards_per_class"])]

    trials = []
    for gi in chosen:
        blocked = ideal.D[gi]
        all_blocked = [i for i in range(len(pool)) if blocked[i]]
        all_allowed = [i for i in range(len(pool)) if not blocked[i]]
        half = cfg["n_queries"] // 2
        queries = _pick(rng, [i for i in all_blocked if i in informative], all_blocked, half)
        queries += _pick(rng, [i for i in all_allowed if i in informative], all_allowed, cfg["n_queries"] - half)
        rng.shuffle(queries)
        used = set(queries)
        rest_blocked = [i for i in all_blocked if i not in used]
        rest_allowed = [i for i in all_allowed if i not in used]
        n_block = rng.randint(cfg["min_blocked_probes"], min(cfg["probe_len"] - cfg["min_allowed_probes"], len(rest_blocked)))
        probes = rng.sample(rest_blocked, n_block) + rng.sample(rest_allowed, cfg["probe_len"] - n_block)
        rng.shuffle(probes)
        draws = [draw(rng, cfg["env_error_rate"], cfg["reveal_rate"]) for _ in probes]
        query_records = [
            {"qid": f"q{n + 1}", "action": j, "command": pool[j].command, "blocked": bool(blocked[j])}
            for n, j in enumerate(queries)
        ]
        base = {"guard": gi, "basis": ideal.guards[gi].basis, "queries": query_records}
        trials.append({"trial_id": f"g{gi:03d}-none-k00", "mode": "none", "k": 0, "log": [], **base})
        for mode in cfg["modes"]:
            log = []
            for j, d in zip(probes, draws):
                category, text = observe(pool[j], ideal.msg[gi, j], mode, d)
                cause = ("reviewer" if blocked[j] else "environment") if is_failure(category) else None
                log.append({"action": j, "command": pool[j].command, "response": text, "category": category, "cause": cause})
            for k in cfg["k_values"]:
                if k > 0:
                    trials.append({"trial_id": f"g{gi:03d}-{mode}-k{k:02d}", "mode": mode, "k": k, "log": log[:k], **base})
    return trials
