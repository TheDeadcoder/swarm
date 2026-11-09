import base64
import json
import shlex
import subprocess
import time
from dataclasses import dataclass

from .workspace import tarball

IMAGE = "swarmgate-sandbox:dev"
STATE = "/var/lib/sg"
TRACED = ("execve,clone,clone3,fork,vfork,read,readv,pread64,write,writev,pwrite64,sendto,sendmsg,connect,"
          "sendfile,splice,copy_file_range,mmap,rename,renameat,renameat2,link,linkat")
DROP = "setpriv --reuid ops --regid ops --init-groups"
OPS_ENV = "env -i HOME=/home/ops USER=ops LOGNAME=ops PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8"
COLLECT = ("import base64, json; print(json.dumps({k: base64.b64encode(open(f'/var/lib/sg/{k}', 'rb').read()).decode() "
           "for k in ('status', 'out', 'trace')}))")


@dataclass
class Run:
    status: int
    output: str
    trace: str


class Container:
    def __init__(self, name: str, image: str = IMAGE):
        self.name = name
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "run", "-d", "--rm", "--network", "none", "--cap-add", "SYS_PTRACE",
                        "--security-opt", "seccomp=unconfined", "--name", name, image], check=True, capture_output=True)
        self._wait_for_stub()

    def exec(self, script: str, user: str = "root", stdin: bytes | None = None, timeout: float = 60) -> subprocess.CompletedProcess:
        cmd = ["docker", "exec", *(["-i"] if stdin is not None else []), "-u", user, self.name, "sh", "-c", script]
        return subprocess.run(cmd, input=stdin, capture_output=True, timeout=timeout)

    def _wait_for_stub(self, attempts: int = 50) -> None:
        probe = "python3 -c \"import socket; socket.create_connection(('127.0.0.1', 80), 1).close()\""
        for _ in range(attempts):
            if self.exec(probe).returncode == 0:
                return
            time.sleep(0.1)
        raise RuntimeError(f"stub server did not start in {self.name}")

    def write_files(self, contents: dict[str, str]) -> None:
        self.exec("tar -x -p -C /", stdin=tarball(contents)).check_returncode()

    def run_traced(self, command: str, timeout: int = 20) -> Run:
        script = (f"cd /srv/app; timeout -s KILL {timeout} strace -f -y -qq -s 512 -e trace={TRACED} -o {STATE}/trace "
                  f"{DROP} {OPS_ENV} bash -c {shlex.quote(command)} > {STATE}/out 2>&1; "
                  f"echo $? > {STATE}/status; {DROP} kill -KILL -1 2>/dev/null; true")
        self.exec(script, timeout=timeout + 30).check_returncode()
        data = json.loads(self.exec(f"python3 -c {shlex.quote(COLLECT)}").stdout)
        decoded = {k: base64.b64decode(v).decode(errors="replace") for k, v in data.items()}
        return Run(int(decoded["status"].strip() or -1), decoded["out"], decoded["trace"])

    def close(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)
