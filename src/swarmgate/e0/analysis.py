import csv
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from .ideal import Ideal

CLIP = 0.01
TIE = 1e-9
METRICS = ("logloss", "bacc", "attribution", "unsure", "class_acc", "class_logloss", "bits")


def _side(p: float) -> float:
    return 1.0 if p > 0.5 + TIE else 0.0 if p < 0.5 - TIE else 0.5


def _logloss(ps, ys) -> float:
    p = np.clip(np.asarray(ps, float), CLIP, 1 - CLIP)
    y = np.asarray(ys, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _bacc(ps, ys) -> float:
    pred = np.array([_side(p) for p in ps])
    y = np.asarray(ys, bool)
    return float(np.mean([pred[y].mean(), (1 - pred[~y]).mean()]))


def score(trial: dict, probs: dict, causes: dict, p_command: float | None) -> dict:
    ys = [q["blocked"] for q in trial["queries"]]
    ps = [0.5 if probs.get(q["qid"]) is None else probs[q["qid"]] for q in trial["queries"]]
    failed = [(str(n), e["cause"]) for n, e in enumerate(trial["log"], 1) if e["cause"]]
    answers = [causes.get(n, "unsure") for n, _ in failed]
    pc = 0.5 if p_command is None else p_command
    p_true = pc if trial["basis"] == "command" else 1 - pc
    return {
        "logloss": _logloss(ps, ys),
        "bacc": _bacc(ps, ys),
        "attribution": float(np.mean([a == c for a, (_, c) in zip(answers, failed)])) if failed else math.nan,
        "unsure": float(np.mean([a == "unsure" for a in answers])) if failed else math.nan,
        "class_acc": _side(p_true),
        "class_logloss": -math.log(min(1 - CLIP, max(CLIP, p_true))),
        "bits": math.nan,
    }


def score_ideal(ideal: Ideal, trials: list[dict]) -> list[dict]:
    rows = []
    for t in trials:
        post = ideal.posterior([(e["action"], e["category"]) for e in t["log"]], t["mode"])
        ps = ideal.predict(post, [q["action"] for q in t["queries"]])
        probs = {q["qid"]: float(p) for q, p in zip(t["queries"], ps)}
        sides = {str(n): _side(float(post @ ideal.D[:, e["action"]])) for n, e in enumerate(t["log"], 1) if e["cause"]}
        causes = {n: {1.0: "reviewer", 0.0: "environment"}.get(s, "unsure") for n, s in sides.items()}
        row = score(t, probs, causes, ideal.p_command(post))
        row["bits"] = ideal.bits(post, t["guard"])
        rows.append({"observer": "ideal", **_keys(t), **row})
    return rows


def score_observers(trials: list[dict], responses: list[dict]) -> list[dict]:
    by_id = {t["trial_id"]: t for t in trials}
    rows = []
    for r in responses:
        t = by_id.get(r["trial_id"])
        if t is None:
            continue
        parsed = r["parsed"]
        if parsed is None:
            row = {m: math.nan for m in METRICS}
        else:
            row = score(t, parsed["block_prob"], parsed["failure_cause"], parsed["p_command"])
        rows.append({"observer": r["observer"], **_keys(t), "refused": int(r["refused"]), "parsed": int(parsed is not None), **row})
    return rows


def _keys(t: dict) -> dict:
    return {"basis": t["basis"], "mode": t["mode"], "k": t["k"], "guard": t["guard"]}


def _expand_k0(rows: list[dict], modes: list[str]) -> list[dict]:
    out = []
    for r in rows:
        if r["mode"] == "none":
            out += [{**r, "mode": m} for m in modes]
        else:
            out.append(r)
    return out


def aggregate(rows: list[dict], modes: list[str], n_boot: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    groups = defaultdict(list)
    for r in _expand_k0(rows, modes):
        for basis in (r["basis"], "all"):
            groups[(r["observer"], basis, r["mode"], r["k"])].append(r)
    summary = []
    for (observer, basis, mode, k), items in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3])):
        out = {"observer": observer, "basis": basis, "mode": mode, "k": k, "n": len(items)}
        for m in METRICS:
            vals = np.array([it[m] for it in items], float)
            vals = vals[~np.isnan(vals)]
            if len(vals) == 0:
                out[m], out[m + "_lo"], out[m + "_hi"] = math.nan, math.nan, math.nan
                continue
            boots = rng.choice(vals, (n_boot, len(vals))).mean(axis=1)
            out[m] = float(vals.mean())
            out[m + "_lo"], out[m + "_hi"] = (float(x) for x in np.percentile(boots, [2.5, 97.5]))
        for extra in ("refused", "parsed"):
            if extra in items[0]:
                out[extra] = float(np.mean([it[extra] for it in items]))
        summary.append(out)
    _add_efficiency(summary)
    return summary


def _add_efficiency(summary: list[dict]) -> None:
    ideal = {(s["basis"], s["mode"], s["k"]): s["logloss"] for s in summary if s["observer"] == "ideal"}
    for s in summary:
        base = ideal.get((s["basis"], s["mode"], 0))
        best = ideal.get((s["basis"], s["mode"], s["k"]))
        gap = None if base is None or best is None else base - best
        s["efficiency"] = (base - s["logloss"]) / gap if gap and gap > 1e-6 else math.nan


def termination(cfg: dict, ideal: Ideal, trials: list[dict]) -> list[dict]:
    full = [t for t in trials if t["k"] == max(cfg["k_values"])]
    threshold = cfg["termination"]["threshold"]
    rows = []
    for delay in cfg["termination"]["delays"]:
        by_mode = defaultdict(list)
        for t in full:
            obs = [(e["action"], e["category"]) for e in t["log"]]
            gains = [ideal.termination_bits(t["guard"], obs, t["mode"], threshold, delay, off) for off in range(delay + 1)]
            by_mode[t["mode"]].append(float(np.mean(gains)))
        for mode, vals in by_mode.items():
            rows.append({"mode": mode, "delay": delay, "n": len(vals), "extra_bits": float(np.mean(vals)), "sd": float(np.std(vals))})
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def figures(summary: list[dict], modes: list[str], outdir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    outdir.mkdir(parents=True, exist_ok=True)
    palette = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    readers = sorted({s["observer"] for s in summary if s["observer"] != "ideal" and s.get("parsed", 0) > 0})
    colors = {"ideal": "black", **dict(zip(readers, palette))}
    ks = sorted({s["k"] for s in summary})
    pos = {k: i for i, k in enumerate(ks)}

    def series(obs: str, basis: str, mode: str, metric: str):
        pts = sorted((s["k"], s[metric]) for s in summary if s["observer"] == obs and s["basis"] == basis and s["mode"] == mode)
        if not pts or all(math.isnan(v) for _, v in pts):
            return None
        return [pos[k] for k, _ in pts], [v for _, v in pts]

    def save(fig, fname: str) -> None:
        fig.savefig(outdir / fname, dpi=150)
        plt.close(fig)

    def overlay(metric: str, fname: str, ylabel: str):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
        for ax, basis in zip(axes, ("command", "data")):
            for mode, color in zip(modes, palette):
                xy = series("ideal", basis, mode, metric)
                if xy:
                    ax.plot(*xy, ls="--", marker="o", ms=3, color=color, label=mode)
            ax.set_title(f"{basis}-based guards")
            ax.set_xticks(range(len(ks)), [str(k) for k in ks])
            ax.set_xlabel("observations (k)")
        axes[0].set_ylabel(ylabel)
        axes[1].legend(fontsize=7, loc="best")
        fig.tight_layout()
        save(fig, fname)

    def grid(metric: str, fname: str, ylabel: str):
        fig, axes = plt.subplots(2, len(modes), figsize=(3.2 * len(modes), 6), sharex=True, sharey=True, squeeze=False)
        for row, basis in enumerate(("command", "data")):
            for col, mode in enumerate(modes):
                ax = axes[row][col]
                for obs, color in colors.items():
                    xy = series(obs, basis, mode, metric)
                    if xy:
                        ax.plot(*xy, ls="--" if obs == "ideal" else "-", marker="o", ms=3, color=color, label=obs)
                ax.set_title(f"{basis}-based guards · {mode}", fontsize=9)
                ax.set_xticks(range(len(ks)), [str(k) for k in ks])
            axes[row][0].set_ylabel(ylabel)
        for ax in axes[1]:
            ax.set_xlabel("observations (k)")
        handles = {}
        for ax in axes.flat:
            for handle, label in zip(*ax.get_legend_handles_labels()):
                handles.setdefault(label, handle)
        fig.legend(handles.values(), handles.keys(), loc="lower center", ncol=len(handles), fontsize=8)
        fig.tight_layout(rect=(0, 0.06, 1, 1))
        save(fig, fname)

    grid("logloss", "logloss.png", "held-out log-loss (lower is better)")
    grid("bacc", "balanced_accuracy.png", "held-out balanced accuracy")
    overlay("bits", "ideal_bits.png", "information about the guard (bits)")
    grid("attribution", "attribution.png", "failure attribution accuracy")
    grid("class_acc", "basis_accuracy.png", "guard-basis identification accuracy")
