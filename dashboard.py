import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List

# Third-party: Rich for TUI
try:
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    from rich.progress import Progress
except ImportError:
    print("Rich is required. Install with: pip install rich", file=sys.stderr)
    sys.exit(1)

console = Console()

@dataclass
class InstanceState:
    name: str
    device: str
    pid: Optional[int] = None
    state: str = "starting"
    wave: int = 0
    captcha_attempts: int = 0
    no_battle: int = 0
    log_index: Optional[int] = None
    last_update: float = field(default_factory=time.time)
    uptime_start: float = field(default_factory=time.time)
    uptime_stop: Optional[float] = None
    last_line: str = ""
    error: Optional[str] = None
    exit_code: Optional[int] = None

    def uptime(self) -> float:
        end = self.uptime_stop if self.uptime_stop is not None else time.time()
        return max(0.0, end - self.uptime_start)

class InstanceRunner:
    def __init__(self, python_exe: str, root: str, script: str, name: str, device: str, config: str, extra_args: list[str]):
        self.python_exe = python_exe
        self.root = root
        self.script = script
        self.name = name
        self.device = device
        self.config = config
        self.extra_args = extra_args
        self.proc: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.queue: "queue.Queue[str]" = queue.Queue()

    def start(self):
        cmd = [self.python_exe, os.path.join(self.root, self.script),
               "--adb-device", self.device,
               "--config", self.config,
               "--status",
               "--name", self.name]
        cmd += self.extra_args
        self.proc = subprocess.Popen(cmd, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)

        def reader():
            assert self.proc and self.proc.stdout
            for line in self.proc.stdout:
                self.queue.put(line.rstrip("\n"))
            # process ended
            self.queue.put("__PROCESS_EXIT__")

        self.thread = threading.Thread(target=reader, daemon=True)
        self.thread.start()

    def poll(self) -> Optional[int]:
        if self.proc is None:
            return 0
        return self.proc.poll()

    def terminate(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass


def parse_status_line(line: str) -> Optional[dict]:
    if not line.startswith("__STATUS__ "):
        return None
    payload = line[len("__STATUS__ "):]
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def build_layout(states: Dict[str, InstanceState], footer: Optional[str] = None) -> Layout:
    # Create a table for all instances
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", justify="right", width=3)
    table.add_column("Name", style="bold")
    table.add_column("Device")
    table.add_column("State")
    table.add_column("Wave", justify="right")
    table.add_column("Captcha", justify="right")
    table.add_column("NoBattle", justify="right")
    table.add_column("Uptime")
    table.add_column("Last Update")
    table.add_column("Exit", justify="right")
    table.add_column("Last")

    now = time.time()
    for idx, (key, st) in enumerate(sorted(states.items())):
        age = now - st.last_update
        age_text = f"{age:4.1f}s"
        uptime_text = f"{st.uptime():.0f}s"
        state_style = {
            "connected": "green",
            "battle": "bright_green",
            "menu": "yellow",
            "idle": "grey66",
            "captcha_solving": "magenta",
            "captcha_wait": "magenta",
            "captcha_failed": "red",
            "home": "cyan",
            "connecting": "cyan",
            "stopped": "red",
        }.get(st.state, "white")
        last_msg = (st.last_line or "").strip()
        if len(last_msg) > 60:
            last_msg = last_msg[:57] + "..."
        exit_text = "" if st.exit_code is None else str(st.exit_code)
        table.add_row(
            str(idx+1),
            Text(st.name, style="bold white"),
            st.device,
            Text(st.state, style=state_style),
            str(st.wave),
            str(st.captcha_attempts),
            str(st.no_battle),
            uptime_text,
            age_text,
            exit_text,
            last_msg,
        )

    layout = Layout()
    if footer:
        layout.split_column(
            Layout(Panel(table, title="GrowCastle Instances", border_style="blue"), ratio=5),
            Layout(Panel(Text(footer), title="Status", border_style="grey50"), ratio=1),
        )
    else:
        layout.split_column(
            Layout(Panel(table, title="GrowCastle Instances", border_style="blue"), ratio=1),
        )
    return layout


def main():
    parser = argparse.ArgumentParser(description="Dashboard to run and monitor multiple GrowCastle instances")
    parser.add_argument("--config", type=str, default="config.json", help="Config file to use for all instances")
    parser.add_argument("--script", type=str, default="growcastle.py", help="Script to run for each instance")
    parser.add_argument("--name-prefix", type=str, default="bot", help="Prefix for instance names")
    parser.add_argument("--python", type=str, default=sys.executable, help="Python executable to use")
    parser.add_argument("--extra-args", type=str, nargs=argparse.REMAINDER, default=[], help="Extra args for each instance (also supports bare -- passthrough)")
    # Positional passthrough after bare --
    parser.add_argument("passthrough", nargs=argparse.REMAINDER, help="Args forwarded to every instance after --")
    parser.add_argument("--no-keep-open", dest="keep_open", action="store_false", help="Exit the dashboard when all instances stop")
    parser.add_argument("--instances", type=str, default="instances.json", help="JSON file listing instances with device and display name (default: instances.json)")
    parser.set_defaults(keep_open=True)

    args = parser.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))

    runners: List[InstanceRunner] = []
    states: Dict[str, InstanceState] = {}

    # Prepare extra args (combine --extra-args and positional passthrough, strip any leading --)
    extra = list(args.extra_args or [])
    if extra and extra[0] == "--":
        extra = extra[1:]
    passthrough = list(getattr(args, "passthrough", []) or [])
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    extra = (extra or []) + (passthrough or [])

    # Prefer instances file if available
    cfg_path = os.path.abspath(args.instances) if args.instances else None
    data = None
    if cfg_path and os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            console.print(f"Failed to read instances file '{cfg_path}': {e}", style="bold red")
            sys.exit(2)

    if data is not None:
        items = data.get("instances", [])
        if not isinstance(items, list):
            console.print("Invalid instances config: 'instances' must be a list", style="bold red")
            sys.exit(2)
        script = data.get("script", args.script)
        py = data.get("python", args.python)
        for idx, item in enumerate(items, start=1):
            device = item.get("device")
            name = item.get("name") or f"{args.name_prefix}-{idx:02d}"
            if not device:
                console.print(f"Skipping entry {idx}: missing 'device'", style="yellow")
                continue
            inst_config = item.get("config") or args.config
            inst_extra = item.get("extra_args") or extra
            runner = InstanceRunner(py, root, script, name, device, inst_config, inst_extra)
            runner.start()
            runners.append(runner)
            states[name] = InstanceState(name=name, device=device, pid=runner.proc.pid if runner.proc else None)
    elif args.devices:
        # Fallback to devices provided via CLI
        for i, device in enumerate(args.devices):
            name = f"{args.name_prefix}-{i+1:02d}"
            runner = InstanceRunner(args.python, root, args.script, name, device, args.config, extra)
            runner.start()
            runners.append(runner)
            states[name] = InstanceState(name=name, device=device, pid=runner.proc.pid if runner.proc else None)
    else:
        console.print("No instances started. Provide --devices or an instances file (default: instances.json).", style="bold red")
        sys.exit(2)

    # Live updating UI
    try:
        with Live(build_layout(states), console=console, refresh_per_second=4, screen=True, transient=False) as live:
            running = True
            while running:
                running = False
                # Consume output without blocking too long
                for runner in runners:
                    while True:
                        try:
                            line = runner.queue.get_nowait()
                        except queue.Empty:
                            break
                        if line == "__PROCESS_EXIT__":
                            # mark as stopped
                            # find state by name
                            for st in states.values():
                                if st.pid == (runner.proc.pid if runner.proc else None):
                                    st.state = "stopped"
                                    st.last_update = time.time()
                                    if st.uptime_stop is None:
                                        st.uptime_stop = st.last_update
                            continue
                        st = states.get(runner.name)
                        if st:
                            st.last_line = line
                            payload = parse_status_line(line)
                            if payload:
                                st.state = payload.get("state", st.state)
                                st.wave = int(payload.get("wave", st.wave) or 0)
                                st.captcha_attempts = int(payload.get("captcha_attempts", st.captcha_attempts) or 0)
                                st.no_battle = int(payload.get("no_battle", st.no_battle) or 0)
                                st.log_index = payload.get("log_index", st.log_index)
                                st.last_update = time.time()
                # Determine if any are still running
                all_stopped = True
                for r in runners:
                    code = r.poll()
                    if code is None:
                        running = True
                        all_stopped = False
                    else:
                        # record exit codes
                        st = states.get(r.name)
                        if st:
                            st.exit_code = code
                            if st.state != "stopped":
                                st.state = "stopped"
                                st.last_update = time.time()
                            if st.uptime_stop is None:
                                st.uptime_stop = st.last_update
                time.sleep(0.1)
                # Update layout with footer if all stopped and keep_open
                footer = None
                if all_stopped and args.keep_open:
                    footer = "All instances have stopped. Press Ctrl+C to exit."
                    running = True  # keep loop alive
                live.update(build_layout(states, footer=footer))
    except KeyboardInterrupt:
        pass
    finally:
        # Terminate child processes
        for r in runners:
            r.terminate()

if __name__ == "__main__":
    main()
