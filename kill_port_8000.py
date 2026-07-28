import os
import re
import subprocess
import sys


PORT = 8000


def get_pids_on_port(port: int):
    """Знаходить PID процесів, які слухають вказаний порт."""
    try:
        output = subprocess.check_output(
            ["netstat", "-ano"], text=True, encoding="utf-8", errors="replace"
        )
    except Exception as exc:
        print(f"[ERR] Не вдалося виконати netstat: {exc}")
        return []

    pids = set()
    for line in output.splitlines():
        parts = line.strip().split()
        # TCP    0.0.0.0:8000    0.0.0.0:0    LISTENING    12345
        if len(parts) >= 5 and parts[1].endswith(f":{port}"):
            state = parts[3].upper()
            if state == "TIME_WAIT":
                continue
            try:
                pid = int(parts[-1])
                if pid > 0:
                    pids.add(pid)
            except ValueError:
                continue
    return list(pids)


def get_python_processes():
    """Знаходить усі python.exe процеси та їх CommandLine (через wmic)."""
    try:
        output = subprocess.check_output(
            ["wmic", "process", "where", "Name='python.exe'", "get", "CommandLine,ProcessId", "/value"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        print(f"[ERR] Не вдалося отримати список python-процесів: {exc}")
        return []

    processes = []
    blocks = re.split(r"\n\s*\n", output.strip())
    current_pid = os.getpid()

    for block in blocks:
        pid_match = re.search(r"^ProcessId=(\d+)", block, re.MULTILINE)
        cmd_match = re.search(r"^CommandLine=(.*)", block, re.MULTILINE)
        if not pid_match:
            continue
        try:
            pid = int(pid_match.group(1))
        except ValueError:
            continue
        if pid == current_pid:
            continue
        command_line = cmd_match.group(1).strip() if cmd_match else ""
        processes.append((pid, command_line))
    return processes


def kill_pid(pid: int):
    print(f"[INFO] Закриваю процес PID {pid}...")
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except Exception as exc:
        print(f"[ERR] taskkill PID {pid}: {exc}")


def main():
    print(f"[INFO] Шукаю старі запуски main.py та прослуховування порту {PORT}...")

    killed = set()

    # 1. Закриваємо процеси на порту 8000
    for pid in get_pids_on_port(PORT):
        kill_pid(pid)
        killed.add(pid)

    # 2. Закриваємо всі python.exe, що запускали main.py (старий бот + веб-сервер)
    for pid, command_line in get_python_processes():
        if pid in killed:
            continue
        if "main.py" in command_line:
            print(f"[INFO] Знайдено попередній main.py: PID {pid} — {command_line}")
            kill_pid(pid)
            killed.add(pid)

    if not killed:
        print(f"[INFO] Старих процесів не знайдено, порт {PORT} вільний")
    else:
        print(f"[OK] Закрито процесів: {len(killed)}")


if __name__ == "__main__":
    main()
