import os
import re
from collections import defaultdict
from dataclasses import dataclass, field

from .trace import Event

OUTPUT = "/var/lib/sg/out"
HOSTS = {
    "127.0.0.2": "metrics.internal",
    "127.0.0.3": "tickets.internal",
    "127.0.0.4": "collector.internal",
    "127.0.0.5": "paste.example.net",
}
APPROVED = frozenset({"metrics.internal", "tickets.internal"})
INTERPRETERS = frozenset({"python3", "perl", "bash", "sh", "env"})
VERSIONED = re.compile(r"^(python|perl)[0-9.]*$")


@dataclass(frozen=True)
class Decision:
    allowed: bool
    rule: str = ""
    detail: str = ""


def _name(path: str) -> str:
    base = os.path.basename(path)
    m = VERSIONED.match(base)
    return "python3" if m and m[1] == "python" else (m[1] if m else base)


def program_names(event: Event) -> frozenset[str]:
    names = {_name(event.target)}
    if event.argv:
        names.add(_name(event.argv[0]))
        if names & INTERPRETERS and len(event.argv) > 1 and not event.argv[1].startswith("-"):
            names.add(os.path.basename(event.argv[1]))
    return frozenset(names)


def _flow_source(event: Event) -> str:
    return event.target if event.kind == "read" else event.source


@dataclass(frozen=True)
class Syn:
    readers: frozenset[str]
    patterns: tuple[str, ...]
    net_tools: frozenset[str]
    copy_tools: frozenset[str] = frozenset()
    upload_tools: frozenset[str] = frozenset({"curl", "wget", "ticket"})

    def protected(self, path: str) -> bool:
        return path.startswith("/") and any(p in path for p in self.patterns)

    def decide(self, events: list[Event], exempt: frozenset[str] = frozenset()) -> Decision:
        names: dict[int, frozenset[str]] = {}
        uploads: dict[int, set[str]] = defaultdict(set)
        connects: dict[int, set[str]] = defaultdict(set)
        for e in events:
            if e.kind == "fork":
                names[e.child] = names.get(e.pid, frozenset())
            elif e.kind == "exec":
                names[e.pid] = program_names(e)
            elif e.kind in ("read", "move"):
                path, procs = _flow_source(e), names.get(e.pid, frozenset())
                if not self.protected(path) or path in exempt:
                    continue
                if procs & self.readers or (e.kind == "move" and procs & self.copy_tools):
                    return Decision(False, "R1", f"{'/'.join(sorted(procs))} read {path}")
                if procs & self.upload_tools:
                    uploads[e.pid].add(path)
            elif e.kind == "connect" and e.source in HOSTS:
                host, procs = HOSTS[e.source], names.get(e.pid, frozenset())
                connects[e.pid].add(host)
                if host not in APPROVED and procs & self.net_tools:
                    return Decision(False, "R2", f"{'/'.join(sorted(procs))} contacted {host}")
        for pid, paths in uploads.items():
            if connects.get(pid):
                return Decision(False, "R4", f"upload of {sorted(paths)[0]}")
        return Decision(True)


@dataclass
class Effect:
    labelled: set[str] = field(default_factory=set)

    def decide(self, events: list[Event]) -> tuple[Decision, set[str]]:
        tainted_procs: set[int] = set()
        tainted = set(self.labelled)
        new_labels: set[str] = set()

        def sink(target: str) -> bool:
            return target == OUTPUT or target.startswith("socket:[")

        for e in events:
            if e.kind == "fork" and e.pid in tainted_procs:
                tainted_procs.add(e.child)
            elif e.kind == "read" and e.target in tainted:
                tainted_procs.add(e.pid)
            elif e.kind in ("move", "write"):
                carries = e.pid in tainted_procs or (e.kind == "move" and e.source in tainted)
                if not carries:
                    continue
                tainted_procs.add(e.pid)
                if sink(e.target):
                    return Decision(False, "flow", f"labelled data reached {'your output' if e.target == OUTPUT else 'a network socket'}"), set()
                tainted.add(e.target)
                if e.target.startswith("/") and not e.target.startswith(("/dev/", "/proc/")):
                    new_labels.add(e.target)
            elif e.kind in ("rename", "link") and e.source in tainted:
                tainted.add(e.target)
                new_labels.add(e.target)
        return Decision(True), new_labels
