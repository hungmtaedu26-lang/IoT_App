from __future__ import annotations

import signal
import subprocess
import sys
from pathlib import Path
from typing import List

from shared.config import get_settings

COMMANDS = [
    [sys.executable, "-m", "uvicorn", "services.device_a.app:app", "--host", "{device_a_host}", "--port", "{device_a_port}"],
    [sys.executable, "-m", "uvicorn", "services.device_b.app:app", "--host", "{device_b_host}", "--port", "{device_b_port}"],
    [sys.executable, "-m", "uvicorn", "services.snark_runner.app:app", "--host", "{snark_runner_host}", "--port", "{snark_runner_port}"],
    [sys.executable, "-m", "services.smart_contract.listener"],
    [sys.executable, "-m", "services.storage.ipfs"],
    [sys.executable, "-m", "services.storage.filecoin"],
]


def format_commands(settings) -> List[List[str]]:
    formatted = []
    for cmd in COMMANDS:
        formatted.append([part.format(**settings.__dict__) for part in cmd])
    return formatted


def main() -> None:
    settings = get_settings()
    processes = []
    commands = format_commands(settings)

    print("Starting services.")
    for cmd in commands:
        proc = subprocess.Popen(cmd, cwd=Path(__file__).resolve().parents[1])
        processes.append(proc)
        print(f" -> {' '.join(cmd)} (pid={proc.pid})")

    def shutdown(signum, frame):
        print("Stopping services.")
        for proc in processes:
            proc.terminate()
        for proc in processes:
            proc.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for proc in processes:
        proc.wait()


if __name__ == "__main__":
    main()

