import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..e0.observer import RateLimiter, load_jsonl
from ..llm import Turn, is_transient, make_client, retry_after


def retrying(fn, *args, attempts: int = 6, backoff: float = 5.0):
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args)
        except Exception as exc:
            if not is_transient(exc) or attempt == attempts:
                raise
            time.sleep((retry_after(exc) or min(backoff * 2 ** (attempt - 1), 120.0)) * (1 + 0.25 * random.random()))
    raise RuntimeError("unreachable")


def append(path: Path, record: dict, lock: threading.Lock) -> None:
    with lock, path.open("a") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())


def turn_record(turn: Turn) -> dict:
    return {"text": turn.text, "calls": [c.command for c in turn.calls], "stop": turn.stop, "refused": turn.refused,
            "category": turn.meta.get("refusal_category"), "usage": turn.meta.get("usage", {})}


def run_jobs(specs: dict, jobs: list[tuple[str, str, dict]], work, out: Path, clients: dict | None = None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    errors = out.with_name(f"{out.stem}-errors.jsonl")
    done = {(r["model"], r["cell_id"]) for r in load_jsonl(out)}
    todo = [job for job in jobs if (job[0], job[1]) not in done]
    names = {name for name, _, _ in todo}
    clients = clients or {name: make_client(specs[name]) for name in names}
    limiters = {name: RateLimiter(specs.get(name, {}).get("rpm")) for name in names}
    lock = threading.Lock()
    stats = {"todo": len(todo), "done": 0, "failed": 0}

    def one(name: str, key: str, cell: dict) -> None:
        base = {"model": name, "cell_id": key, **cell}
        try:
            limiters[name].wait()
            record = retrying(work, clients[name], cell)
        except Exception as exc:
            append(errors, {**base, "error": repr(exc)}, lock)
            with lock:
                stats["failed"] += 1
            return
        append(out, {**base, **record}, lock)
        with lock:
            stats["done"] += 1

    workers = sum(specs.get(name, {}).get("workers", 4) for name in names)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for job in todo:
            pool.submit(one, *job)
    return stats
