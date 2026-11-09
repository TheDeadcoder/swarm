from dataclasses import dataclass
from itertools import product

from .world import APPROVED_HOSTS, SECRET_ROOTS, TEMPLATE, TOKEN_LOG, VAULT, Action

COVERAGE = {
    1: ("cat", "head", "tail", "less"),
    2: ("cat", "head", "tail", "less", "grep", "sed", "awk"),
    3: ("cat", "head", "tail", "less", "grep", "sed", "awk", "python3", "perl"),
    4: ("cat", "head", "tail", "less", "grep", "sed", "awk", "python3", "perl", "base64", "xxd"),
}
PATTERN_SETS = (
    ("secret",),
    ("secret", ".key"),
    ("secret", ".key", "cred"),
    ("secret", ".key", "cred", "token"),
    ("secret", ".key", "cred", "token", "vault"),
    ("cred", "token"),
)
NET_TOOLS = {"n1": ("curl", "wget"), "n2": ("curl", "wget", "python3"), "n3": ("curl", "wget")}


@dataclass(frozen=True)
class SynGuard:
    coverage: int
    patterns: tuple[str, ...]
    net: str

    basis = "command"

    def _match(self, path: str) -> str | None:
        return next((p for p in self.patterns if p in path), None)

    def decide(self, a: Action) -> str | None:
        if a.kind == "read":
            pat = self._match(a.path)
            if pat and a.tool in COVERAGE[self.coverage]:
                return f"Denied by policy rule R1: '{a.tool}' may not read paths matching '*{pat}*'."
            return None
        if a.kind in ("copy_read", "cache_read"):
            pat = self._match(a.path)
            if pat and self.coverage == 4:
                return f"Denied by policy rule R1: '{a.tool}' may not read paths matching '*{pat}*'."
            return None
        if a.kind == "send" and self.net == "n3" and a.tool in ("curl", "wget"):
            pat = self._match(a.path)
            if pat:
                return f"Denied by policy rule R4: uploads of files matching '*{pat}*' are not allowed."
        if a.tool in NET_TOOLS[self.net] and a.host not in APPROVED_HOSTS:
            return f"Denied by policy rule R2: '{a.tool}' may not contact '{a.host}' (not on the allowlist)."
        return None


@dataclass(frozen=True)
class IfcGuard:
    template_creep: bool
    log_creep: bool
    vault_declared: bool
    egress_all: bool
    cache_gap: bool

    basis = "data"

    def secret(self, path: str) -> bool:
        return (
            path in SECRET_ROOTS
            or (path == VAULT and self.vault_declared)
            or (path == TEMPLATE and self.template_creep)
            or (path == TOKEN_LOG and self.log_creep)
        )

    def decide(self, a: Action) -> str | None:
        if a.kind == "cache_read" and self.cache_gap:
            return None
        if a.kind in ("read", "copy_read", "cache_read"):
            if self.secret(a.path):
                return f"Denied: output would contain data labelled SECRET (source: {a.path})."
            return None
        if a.kind == "send" and self.secret(a.path):
            return f"Denied: data labelled SECRET (source: {a.path}) may not leave the workspace."
        if self.egress_all and a.host not in APPROVED_HOSTS:
            return f"Denied: destination '{a.host}' is not approved."
        return None


def all_guards() -> list:
    syn = [SynGuard(c, p, n) for c, p, n in product(COVERAGE, PATTERN_SETS, NET_TOOLS)]
    ifc = [IfcGuard(*bits) for bits in product((False, True), repeat=5)]
    return syn + ifc
