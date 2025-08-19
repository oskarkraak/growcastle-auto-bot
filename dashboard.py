import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import random
from dataclasses import dataclass, field
from collections import deque
from typing import Dict, Optional, List
import tempfile

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

# Cross-platform keyboard input normalization
WINDOWS = False
try:
    import msvcrt  # type: ignore
    WINDOWS = True
except ImportError:
    msvcrt = None  # type: ignore

def get_key() -> Optional[str]:
    """Return a normalized key identifier or None.
    Normal keys: single character lowercased (e.g. 'p').
    Special keys: 'UP', 'DOWN', 'LEFT', 'RIGHT', 'ESC'.
    """
    if WINDOWS and msvcrt:
        if not msvcrt.kbhit():  # type: ignore
            return None
        ch = msvcrt.getch()  # type: ignore
        if ch in (b'\x00', b'\xe0'):  # extended key prefix
            ch2 = msvcrt.getch()  # type: ignore
            mapping = {
                b'H': 'up',
                b'P': 'down',
                b'K': 'left',
                b'M': 'right',
            }
            return mapping.get(ch2)
        if ch == b'\x1b':
            return 'esc'
        # Try decode ASCII only
        try:
            s = ch.decode('ascii')
            if len(s) == 1 and s.isprintable():
                return s.lower()
        except Exception:
            return None
        return None
    else:
        # POSIX: use termios non-blocking read with select
        import select, termios, tty
        fd = sys.stdin.fileno()
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if not dr:
            return None
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                # Escape or escape sequence
                if select.select([sys.stdin], [], [], 0)[0]:
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[' and select.select([sys.stdin], [], [], 0)[0]:
                        ch3 = sys.stdin.read(1)
                        mapping = {'A': 'up', 'B': 'down', 'C': 'right', 'D': 'left'}
                        return mapping.get(ch3, 'esc')
                return 'esc'
            if ch and ch.isprintable():
                return ch.lower()
            return None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

@dataclass
class InstanceState:
    name: str
    device: str
    pid: Optional[int] = None
    state: str = "starting"
    wave: int = 0
    captcha_attempts: int = 0
    captchas_done: int = 0
    no_battle: int = 0
    log_index: Optional[int] = None
    last_update: float = field(default_factory=time.time)
    uptime_start: Optional[float] = None
    uptime_stop: Optional[float] = None
    last_line: str = ""
    error: Optional[str] = None
    exit_code: Optional[int] = None
    last_outcomes: deque = field(default_factory=lambda: deque(maxlen=5))
    scheduled_at: Optional[float] = None
    stop_scheduled_at: Optional[float] = None

    def uptime(self) -> float:
        if self.uptime_start is None:
            return 0.0
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
        self.scheduled_at: Optional[float] = None
        self.stop_scheduled_at: Optional[float] = None

    def start(self):
        cmd = [self.python_exe, os.path.join(self.root, self.script),
               "--adb-device", self.device,
               "--config", self.config,
               "--status",
               "--name", self.name,
               "--ignore-sigint"]
        cmd += self.extra_args
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        # On POSIX, start_new_session isolates the child from our signal group
        self.proc = subprocess.Popen(
            cmd,
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            creationflags=creationflags,
            start_new_session=(os.name != "nt")
        )

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
            return None
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


def build_layout(states: Dict[str, InstanceState], selected_idx: int = 0, footer: Optional[str] = None) -> Layout:
    # Create a table for all instances
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", justify="right", width=3)
    table.add_column("Name", style="bold")
    table.add_column("State")
    table.add_column("Waves", justify="right")
    table.add_column("Captchas", justify="right")
    table.add_column("Idle iterations", justify="right")
    table.add_column("Uptime")
    table.add_column("Last Update")
    table.add_column("Start/Stop")
    table.add_column("History")
    now = time.time()
    for idx, (key, st) in enumerate(sorted(states.items())):
        age = now - st.last_update
        age_sec = int(age) if age > 0 else 0
        age_text = f"{age_sec}s"
        uptime_text = f"{st.uptime()/60:.0f}min"
        state_style = {
            "scheduled": "cyan",
            "stopping": "yellow",
            "connected": "green",
            "battle": "bright_green",
            "boss": "bright_green",
            "menu": "yellow",
            "idle": "grey66",
            "captcha_solving": "magenta",
            "captcha_wait": "magenta",
            "captcha_failed": "red",
            "home": "cyan",
            "connecting": "cyan",
            "error": "bold red",
            "stopped": "red",
        }.get(st.state, "white")
        # Start/Stop column: show only the most recent of:
        # (1) start in, (2) started at, (3) stop in, (4) stopped at
        def _fmt_time(ts: Optional[float]) -> str:
            return time.strftime("%H:%M", time.localtime(ts)) if ts else "-"

        # Priority order (most recent):
        # 1) stopped at (if stopped)
        # 2) stop in (if a stop is scheduled)
        # 3) started at (if started)
        # 4) start in (if a start is scheduled)
        if st.uptime_stop:
            start_stop_text = Text(f"stopped {_fmt_time(st.uptime_stop)}", style="grey70")
        elif st.stop_scheduled_at and st.stop_scheduled_at > now:
            rem2 = max(0.0, st.stop_scheduled_at - now)
            start_stop_text = Text(f"stop in {rem2/60.0:.1f}m", style="red")
        elif st.uptime_start:
            start_stop_text = Text(f"started {_fmt_time(st.uptime_start)}", style="green")
        elif st.scheduled_at and st.scheduled_at > now:
            rem = max(0.0, st.scheduled_at - now)
            start_stop_text = Text(f"start in {rem/60.0:.1f}m", style="cyan")
        else:
            start_stop_text = Text("-", style="grey50")

        # History column: last 5 outcomes only (newest on the left, fading to the right)
        if st.last_outcomes:
            segments = []
            for j, ch in enumerate(reversed(st.last_outcomes)):
                intensity = int(255 * (len(st.last_outcomes) - j) / len(st.last_outcomes))
                color = f"bold rgb(0,{intensity},0)" if ch == 'W' else f"bold rgb({intensity},0,0)"
                segments.append(Text(ch, style=color))
            history_text = Text.assemble(*segments)
        else:
            history_text = Text("")
        row_style = "reverse" if idx == selected_idx else ""
        name_text = Text(st.name, style="bold white")
        
        if st.state == "paused":
            name_text.append(" (paused)", style="yellow")
        table.add_row(
            str(idx+1),
            name_text,
            Text(st.state, style=state_style),
            str(st.wave),
            str(st.captchas_done),
            str(st.no_battle),
            uptime_text,
            age_text,
            start_stop_text,
            history_text,
            style=row_style
        )

    layout = Layout()
    total_solved = sum(st.captchas_done for st in states.values()) if states else 0
    if footer:
        layout.split_column(
            Layout(Panel(table, title=f"GrowCastle Auto Bot Instances (Use ↑/↓ to select, 'p' to pause/unpause)", border_style="blue"), ratio=5),
            Layout(Panel(Text(footer), title="Status", border_style="grey50"), ratio=1),
        )
    else:
        layout.split_column(
            Layout(Panel(table, title=f"GrowCastle Auto Bot Instances (Use ↑/↓ to select, 'p' to pause/unpause)", border_style="blue"), ratio=1),
        )
    return layout


def send_control_command(instance_name: str, command: str):
    """Send a control command to the instance via a control file."""
    # Control file path: tempdir/growcastle_control_{instance_name}.json
    safe_name = "".join(c for c in instance_name if c.isalnum() or c in ('-', '_'))
    control_path = os.path.join(tempfile.gettempdir(), f"growcastle_control_{safe_name}.json")
    try:
        with open(control_path, "w") as f:
            json.dump({"command": command, "ts": time.time()}, f)
    except Exception as e:
        pass

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
    parser.add_argument("--stagger-seconds", type=float, default=0.0, help="If > 0, delay each instance start by a truncated-normal sample in [0,T], T=stagger-seconds (mean=T/2, std=T/2)")
    parser.add_argument("--stagger-stop-seconds", type=float, default=0.0, help="If > 0, on Ctrl+C stop instances with delays sampled in [0,T], T=stagger-stop-seconds (mean=T/2, std=T/2)")
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

    # Helper: truncated-normal delay in [0, T]
    def sample_stagger_delay(T: float) -> float:
        if T <= 0:
            return 0.0
        mu = T / 2.0
        sigma = max(1e-6, T / 6.0)
        for _ in range(50):
            d = random.gauss(mu, sigma)
            if 0.0 <= d <= T:
                return d
        return max(0.0, min(T, random.gauss(mu, sigma)))

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
            runners.append(runner)
            st = InstanceState(name=name, device=device, pid=None)
            states[name] = st
            delay = sample_stagger_delay(float(args.stagger_seconds)) if args.stagger_seconds else 0.0
            if delay > 0:
                runner.scheduled_at = time.time() + delay
                st.state = "scheduled"
                st.last_update = time.time()
                st.scheduled_at = runner.scheduled_at
            else:
                runner.start()
                st.pid = runner.proc.pid if runner.proc else None
                st.state = "starting"
                st.scheduled_at = None
                st.uptime_start = time.time()
    elif args.devices:
        # Fallback to devices provided via CLI
        for i, device in enumerate(args.devices):
            name = f"{args.name_prefix}-{i+1:02d}"
            runner = InstanceRunner(args.python, root, args.script, name, device, args.config, extra)
            runners.append(runner)
            st = InstanceState(name=name, device=device, pid=None)
            states[name] = st
            delay = sample_stagger_delay(float(args.stagger_seconds)) if args.stagger_seconds else 0.0
            if delay > 0:
                runner.scheduled_at = time.time() + delay
                st.state = "scheduled"
                st.last_update = time.time()
                st.scheduled_at = runner.scheduled_at
            else:
                runner.start()
                st.pid = runner.proc.pid if runner.proc else None
                st.state = "starting"
                st.scheduled_at = None
                st.uptime_start = time.time()
    else:
        console.print("No instances started. Provide --devices or an instances file (default: instances.json).", style="bold red")
        sys.exit(2)

    # Live updating UI with keyboard selection and pause/unpause
    selected_idx = 0
    instance_keys = sorted(states.keys())
    try:
        # Higher refresh rate for more responsive UI
        with Live(build_layout(states, selected_idx), console=console, refresh_per_second=10, screen=True, transient=False) as live:
            stopping_mode = False
            last_key_time = 0
            last_layout_update = 0.0
            MIN_BG_UPDATE_INTERVAL = 0.5  # seconds between automatic layout refreshes (when no key events)
            while True:
                try:
                    # Start any runners whose schedule has arrived
                    now_ts = time.time()
                    for runner in runners:
                        if runner.proc is None and runner.scheduled_at and now_ts >= runner.scheduled_at:
                            st = states.get(runner.name)
                            runner.start()
                            if st:
                                st.pid = runner.proc.pid if runner.proc else None
                                st.state = "starting"
                                st.last_update = time.time()
                                st.scheduled_at = None
                                st.uptime_start = time.time()

                    # If in stopping mode, terminate those whose stop time has arrived
                    if stopping_mode and args.stagger_stop_seconds and args.stagger_stop_seconds > 0:
                        now_ts = time.time()
                        for r in runners:
                            st = states.get(r.name)
                            if st and st.stop_scheduled_at and now_ts >= st.stop_scheduled_at:
                                r.terminate()
                                st.stop_scheduled_at = None

                    # Consume output without blocking too long
                    for runner in runners:
                        while True:
                            try:
                                line = runner.queue.get_nowait()
                            except queue.Empty:
                                break
                            if line == "__PROCESS_EXIT__":
                                # mark as stopped
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
                                    new_state = payload.get("state", st.state)
                                    # Count only on transition into captcha_solved
                                    if new_state == "captcha_solved" and st.state != "captcha_solved":
                                        st.captchas_done += 1
                                    st.state = new_state
                                    st.wave = int(payload.get("wave", st.wave) or 0)
                                    st.captcha_attempts = int(payload.get("captcha_attempts", st.captcha_attempts) or 0)
                                    st.no_battle = int(payload.get("no_battle", st.no_battle) or 0)
                                    st.log_index = payload.get("log_index", st.log_index)
                                    # Capture an error message if provided
                                    if new_state == "error" and payload.get("message"):
                                        st.error = str(payload.get("message"))
                                    elif new_state and new_state != "error":
                                        # Clear previous error when leaving error state
                                        st.error = None
                                    st.last_update = time.time()
                                    # Track wave outcomes
                                    outcome = payload.get("outcome")
                                    if new_state == "wave_end" and outcome in ("W","L"):
                                        st.last_outcomes.append(outcome)

                    # Keyboard input for selection and pause/unpause (process all buffered keys)
                    key_event = False
                    if sys.stdin.isatty():
                        # Attempt to drain multiple pending keys (bounded)
                        for _ in range(10):
                            key = get_key()
                            if not key:
                                break
                            key_event = True
                            last_key_time = time.time()
                            if key == 'esc':
                                raise KeyboardInterrupt  # unified exit path
                            elif key == 'p':
                                if 0 <= selected_idx < len(instance_keys):
                                    inst_name = instance_keys[selected_idx]
                                    st = states.get(inst_name)
                                    if st:
                                        send_control_command(inst_name, 'unpause' if st.state == 'paused' else 'pause')
                            elif key == 'up':
                                selected_idx = max(0, selected_idx - 1)
                            elif key == 'down':
                                selected_idx = min(len(instance_keys) - 1, selected_idx + 1)
                    # Update instance_keys in case states changed
                    instance_keys = sorted(states.keys())
                    selected_idx = min(selected_idx, len(instance_keys) - 1)

                    # Determine if any are still running (process perspective)
                    all_stopped_process = True
                    for r in runners:
                        code = r.poll()
                        if code is None and (r.proc is not None or r.scheduled_at is not None):
                            all_stopped_process = False
                        elif code is None and r.proc is None and r.scheduled_at is None:
                            # Not started yet or missing schedule; treat as not stopped
                            all_stopped_process = False
                        else:
                            # Process finished; record exit
                            st_ref = states.get(r.name)
                            if st_ref and r.proc is not None:
                                st_ref.exit_code = code
                                if st_ref.state != "stopped":
                                    st_ref.state = "stopped"
                                    st_ref.last_update = time.time()
                                if st_ref.uptime_stop is None:
                                    st_ref.uptime_stop = st_ref.last_update
                    # UI-level all stopped means every state == 'stopped'
                    all_stopped_ui = all(st.state == 'stopped' for st in states.values()) and len(states) > 0
                    # Decide whether to update layout now
                    now_loop = time.time()
                    need_update = False
                    if key_event:
                        need_update = True  # immediate feedback
                    elif (now_loop - last_layout_update) >= MIN_BG_UPDATE_INTERVAL:
                        need_update = True

                    if need_update:
                        # Update layout with footer if all stopped and keep_open
                        footer_lines = []
                        error_items = [(name, st) for name, st in states.items() if st.state == "error" and st.error]
                        if error_items:
                            footer_lines.append("Errors:")
                            for name, st in sorted(error_items):
                                footer_lines.append(f"- {st.name}: {st.error}")
                        if all_stopped_ui and args.keep_open:
                            footer_lines.append("All instances have stopped. Press Ctrl+C to exit.")
                        footer = "\n".join(footer_lines) if footer_lines else None
                        live.update(build_layout(states, selected_idx, footer=footer))
                        last_layout_update = now_loop

                    # Short sleep to prevent tight loop CPU spin
                    time.sleep(0.05)

                    # Exit if all stopped and we are not keeping open
                    if all_stopped_ui and not args.keep_open:
                        break
                except KeyboardInterrupt:
                    # First Ctrl+C schedules staggered stops (if enabled); second breaks the loop
                    if getattr(args, "stagger_stop_seconds", 0.0) and args.stagger_stop_seconds > 0 and not stopping_mode:
                        T = float(args.stagger_stop_seconds)
                        now0 = time.time()
                        for r in runners:
                            st = states.get(r.name)
                            if st and st.state not in ("stopped",):
                                delay = sample_stagger_delay(T)
                                st.stop_scheduled_at = now0 + delay
                                st.state = "stopping"
                        stopping_mode = True
                        continue
                    else:
                        break
    finally:
        # Terminate child processes
        for r in runners:
            r.terminate()

if __name__ == "__main__":
    main()
