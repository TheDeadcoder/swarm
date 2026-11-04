import os
import re
from dataclasses import dataclass

LINE = re.compile(r"^(\d+)\s+(.*)$")
CALL = re.compile(r"^([a-z0-9_]+)\((.*)\)\s+=\s+(-?\d+|0x[0-9a-f]+|\?)(.*)$", re.S)
RESUMED = re.compile(r"^<\.\.\. ([a-z0-9_]+) resumed>(.*)$", re.S)
FD = re.compile(r"\b\d+<([^>]*)>")
DIRFD_PATH = re.compile(r"(?:AT_FDCWD|\d+)<([^>]*)>,\s+\"((?:[^\"\\]|\\.)*)\"")
QUOTED = re.compile(r"\"((?:[^\"\\]|\\.)*)\"")
INET = re.compile(r"sin_addr=inet_addr\(\"([0-9.]+)\"\)")
UNFINISHED = "<unfinished ...>"

READS = {"read", "readv", "pread64"}
WRITES = {"write", "writev", "pwrite64", "sendto", "sendmsg"}
FORKS = {"clone", "clone3", "fork", "vfork"}
RENAMES = {"rename", "renameat", "renameat2", "link", "linkat"}


@dataclass(frozen=True)
class Event:
    pid: int
    kind: str
    target: str = ""
    source: str = ""
    argv: tuple[str, ...] = ()
    child: int = 0


def _unescape(s: str) -> str:
    return s.encode().decode("unicode_escape", errors="replace")


def _paths(args: str) -> list[str]:
    found = []
    for base, path in DIRFD_PATH.findall(args):
        path = _unescape(path)
        found.append(path if path.startswith("/") else os.path.normpath(os.path.join(base or "/", path)))
    return found


def _argv(args: str) -> tuple[str, ...]:
    start = args.find("[")
    if start < 0:
        return ()
    found, pos = [], start + 1
    for m in QUOTED.finditer(args, start + 1):
        if "]" in args[pos:m.start()]:
            break
        found.append(_unescape(m[1]))
        pos = m.end()
    return tuple(found)


def _event(pid: int, name: str, args: str, ret: str, rest: str) -> Event | None:
    ok = ret.startswith("0x") or (ret.lstrip("-").isdigit() and int(ret) >= 0)
    fds = FD.findall(args)
    if name == "execve":
        path = QUOTED.match(args)
        return Event(pid, "exec", target=_unescape(path[1]) if path else "", argv=_argv(args)) if ret == "0" else None
    if name in FORKS:
        return Event(pid, "fork", child=int(ret)) if ok and ret.isdigit() and int(ret) > 0 else None
    if name in READS or (name == "mmap" and ret.startswith("0x") and "PROT_READ" in args):
        return Event(pid, "read", target=fds[0]) if fds and (ret.startswith("0x") or (ok and int(ret) > 0)) else None
    if name in WRITES:
        return Event(pid, "write", target=fds[0]) if fds and ok and int(ret) > 0 else None
    if name == "sendfile":
        return Event(pid, "move", target=fds[0], source=fds[1]) if len(fds) >= 2 and ok and int(ret) > 0 else None
    if name in ("splice", "copy_file_range"):
        return Event(pid, "move", target=fds[1], source=fds[0]) if len(fds) >= 2 and ok and int(ret) > 0 else None
    if name == "connect":
        address = INET.search(args)
        connected = ret == "0" or (ret == "-1" and "EINPROGRESS" in rest)
        return Event(pid, "connect", target=fds[0], source=address[1]) if address and fds and connected else None
    if name in RENAMES and ret == "0":
        paths = _paths(args) or [_unescape(p) for p in QUOTED.findall(args)]
        return Event(pid, "rename" if name.startswith("rename") else "link", target=paths[1], source=paths[0]) if len(paths) >= 2 else None
    return None


def parse(text: str) -> list[Event]:
    pending, events = {}, []
    for raw in text.splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        pid, body = int(m[1]), m[2].rstrip()
        if body.endswith(UNFINISHED):
            pending[pid] = body[: -len(UNFINISHED)].rstrip()
            continue
        resumed = RESUMED.match(body)
        if resumed:
            body = pending.pop(pid, f"{resumed[1]}(") + resumed[2]
        call = CALL.match(body)
        if call:
            event = _event(pid, *call.groups())
            if event:
                events.append(event)
    return events
