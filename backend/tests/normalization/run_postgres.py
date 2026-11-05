"""Run API regressions in a disposable local PostgreSQL cluster, never an existing DB.

Usage from backend: python -m tests.normalization.run_postgres
Requires PostgreSQL's bin directory (psql, initdb, pg_ctl) on PATH.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    executable = shutil.which("psql")
    if not executable:
        raise RuntimeError("Install PostgreSQL client/server binaries first")
    binaries = Path(executable).parent
    suffix = ".exe" if os.name == "nt" else ""
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    command_number = 0
    def run(command, **kwargs):
        nonlocal command_number
        command_number += 1
        output_path = Path(scratch) / f"command-{command_number}.log"
        # A Windows postmaster can inherit pipes from pg_ctl. File-backed output
        # avoids waiting for EOF from a server that intentionally keeps running.
        with output_path.open("w", encoding="utf8") as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, text=True, **flags, **kwargs)
        print(output_path.read_text(encoding="utf8", errors="replace"), end="", flush=True)
        return result
    with tempfile.TemporaryDirectory(prefix="akela-normalization-pg-") as scratch:
        directory = Path(scratch) / "data"
        run([str(binaries / f"initdb{suffix}"), "-D", str(directory), "-U", "normalization_test",
             "--auth=trust", "--encoding=UTF8", "--locale=C"]).check_returncode()
        control = [str(binaries / f"pg_ctl{suffix}"), "-D", str(directory)]
        try:
            run([*control, "-l", str(Path(scratch) / "server.log"), "-o", "-h 127.0.0.1 -p 55439", "-w", "start"]).check_returncode()
            env = {**os.environ, "NORMALIZATION_TEST_POSTGRES_URL": "postgresql://normalization_test@127.0.0.1:55439/postgres"}
            result = run([sys.executable, "-m", "pytest", "tests/normalization/test_integration.py", "-q", "--disable-warnings",
                          "--tb=short", "--basetemp", str(Path(scratch) / "pytest")],
                         cwd=Path(__file__).resolve().parents[2], env=env)
            return result.returncode
        finally:
            if (directory / "postmaster.pid").exists():
                run([*control, "-m", "fast", "-w", "stop"]).check_returncode()


if __name__ == "__main__":
    raise SystemExit(main())
