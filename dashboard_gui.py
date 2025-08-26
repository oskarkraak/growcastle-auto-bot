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
import tempfile
from collections import deque

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception as e:
    print("Tkinter is required for the GUI dashboard.", file=sys.stderr)
    raise


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
    last_update: float = field(default_factory=time.time)
    uptime_start: Optional[float] = None
    uptime_stop: Optional[float] = None
    last_line: str = ""
    error: Optional[str] = None
    exit_code: Optional[int] = None
    last_outcomes: deque = field(default_factory=lambda: deque(maxlen=5))
    no_upgrades: bool = False
    autobattle: bool = False

    def uptime(self) -> float:
        if self.uptime_start is None:
            return 0.0
        end = self.uptime_stop if self.uptime_stop is not None else time.time()
        return max(0.0, end - self.uptime_start)


class InstanceRunner:
    def __init__(self, python_exe: str, root: str, script: str, name: str, device: str, config: str, extra_args: List[str]):
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
               "--name", self.name,
               "--ignore-sigint"]
        cmd += (self.extra_args or [])
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
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

    def restart(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
            except Exception:
                pass
        self.proc = None
        self.queue = queue.Queue()
        self.thread = None
        self.start()


def parse_status_line(line: str) -> Optional[dict]:
    if not line.startswith("__STATUS__ "):
        return None
    payload = line[len("__STATUS__ ") :]
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def send_control_command(instance_name: str, command: str):
    safe_name = "".join(c for c in instance_name if c.isalnum() or c in ("-", "_"))
    control_path = os.path.join(tempfile.gettempdir(), f"growcastle_control_{safe_name}.json")
    try:
        with open(control_path, "w") as f:
            json.dump({"command": command, "ts": time.time()}, f)
    except Exception:
        pass


class DashboardGUI(tk.Tk):
    def __init__(self, runners: List[InstanceRunner], states: Dict[str, InstanceState], runners_by_name: Dict[str, InstanceRunner], refresh_ms: int = 100):
        super().__init__()
        self.title("GrowCastle Auto Bot Dashboard")
        self.geometry("1100x520")
        self.runners = runners
        self.states = states
        self.runners_by_name = runners_by_name
        self.refresh_ms = refresh_ms
        self.selected_name: Optional[str] = None

        self._build_ui()
        self._bind_keys()
        self.after(self.refresh_ms, self._tick)

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.BOTH, expand=True)

        columns = ("state", "wave", "captchas", "idle", "uptime", "age", "note")
        # Show tree column (#0) for the instance name, plus the rest as headings
        self.tree = ttk.Treeview(top, columns=columns, show="tree headings", height=16)
        self.tree.heading("#0", text="Name")
        self.tree.column("#0", width=200)
        self.tree.heading("state", text="State")
        self.tree.heading("wave", text="Waves")
        self.tree.heading("captchas", text="Captchas")
        self.tree.heading("idle", text="Idle iters")
        self.tree.heading("uptime", text="Uptime")
        self.tree.heading("age", text="Last Update")
        self.tree.heading("note", text="Last outcomes")
        self.tree.column("state", width=160)
        self.tree.column("wave", width=70, anchor=tk.CENTER)
        self.tree.column("captchas", width=80, anchor=tk.CENTER)
        self.tree.column("idle", width=90, anchor=tk.CENTER)
        self.tree.column("uptime", width=90, anchor=tk.CENTER)
        self.tree.column("age", width=100, anchor=tk.CENTER)
        self.tree.column("note", width=350)

        self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=8, pady=(0, 8))

        self.btn_pause = ttk.Button(btns, text="Pause/Unpause", command=self._on_pause)
        self.btn_no_up = ttk.Button(btns, text="Toggle Upgrades", command=self._on_toggle_upgrades)
        self.btn_auto = ttk.Button(btns, text="Toggle Autobattle", command=self._on_toggle_autobattle)
        self.btn_restart = ttk.Button(btns, text="Restart", command=self._on_restart)
        self.btn_pause_all = ttk.Button(btns, text="Pause/Unpause All", command=self._on_pause_all)
        self.btn_restart_all = ttk.Button(btns, text="Restart All", command=self._on_restart_all)

        for w in (self.btn_pause, self.btn_no_up, self.btn_auto, self.btn_restart, self.btn_pause_all, self.btn_restart_all):
            w.pack(side=tk.LEFT, padx=4)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, anchor=tk.W).pack(fill=tk.X, padx=8, pady=(0, 8))

        # Populate initial rows
        for name in sorted(self.states.keys()):
            self.tree.insert("", tk.END, iid=name, text=name, values=self._row_values(self.states[name]))

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def _bind_keys(self):
        self.bind("<Up>", lambda e: self._move_selection(-1))
        self.bind("<Down>", lambda e: self._move_selection(1))
        self.bind("p", lambda e: self._on_pause())
        self.bind("u", lambda e: self._on_toggle_upgrades())
        self.bind("a", lambda e: self._on_toggle_autobattle())
        self.bind("r", lambda e: self._on_restart())

    def _move_selection(self, delta: int):
        ids = list(self.tree.get_children(""))
        if not ids:
            return
        if self.selected_name is None or self.selected_name not in ids:
            target = ids[0]
        else:
            idx = ids.index(self.selected_name)
            idx = max(0, min(len(ids) - 1, idx + delta))
            target = ids[idx]
        self.tree.selection_set(target)
        self.tree.focus(target)
        self.selected_name = target

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        self.selected_name = sel[0] if sel else None

    def _selected_state(self) -> Optional[InstanceState]:
        if self.selected_name:
            return self.states.get(self.selected_name)
        return None

    def _on_pause(self):
        st = self._selected_state()
        if st:
            send_control_command(st.name, 'unpause' if st.state == 'paused' else 'pause')

    def _on_toggle_upgrades(self):
        st = self._selected_state()
        if st:
            send_control_command(st.name, 'toggle_no_upgrades')

    def _on_toggle_autobattle(self):
        st = self._selected_state()
        if st:
            send_control_command(st.name, 'autobattle_off' if st.autobattle else 'autobattle_on')

    def _on_restart(self):
        st = self._selected_state()
        if not st:
            return
        runner = self.runners_by_name.get(st.name)
        if runner:
            st.state = "restarting"
            st.error = None
            st.wave = 0
            st.captcha_attempts = 0
            st.no_battle = 0
            st.uptime_stop = None
            runner.restart()
            st.pid = runner.proc.pid if runner.proc else None
            st.uptime_start = time.time()
            st.state = "starting"

    def _on_pause_all(self):
        for st in self.states.values():
            send_control_command(st.name, 'unpause' if st.state == 'paused' else 'pause')

    def _on_restart_all(self):
        for name, st in self.states.items():
            runner = self.runners_by_name.get(name)
            if runner:
                st.state = "restarting"
                st.error = None
                st.wave = 0
                st.captcha_attempts = 0
                st.no_battle = 0
                st.uptime_stop = None
                runner.restart()
                st.pid = runner.proc.pid if runner.proc else None
                st.uptime_start = time.time()
                st.state = "starting"

    def _row_values(self, st: InstanceState):
        now = time.time()
        age = max(0, int(now - st.last_update))
        uptime = f"{st.uptime()/60:.0f}min"
        history = "".join(list(st.last_outcomes))
        return (st.state, str(st.wave), str(st.captchas_done), str(st.no_battle), uptime, f"{age}s", history)

    def _update_table_row(self, name: str, st: InstanceState):
        vals = self._row_values(st)
        if name in self.tree.get_children(""):
            self.tree.item(name, text=name, values=vals)
        else:
            self.tree.insert("", tk.END, iid=name, text=name, values=vals)

    def _tick(self):
        try:
            # Start finished/queued processes check
            for r in self.runners:
                if r.proc is None:
                    continue
                code = r.poll()
                if code is not None:
                    st = self.states.get(r.name)
                    if st:
                        st.exit_code = code
                        st.state = "stopped"
                        st.last_update = time.time()
                        if st.uptime_stop is None:
                            st.uptime_stop = st.last_update

            # Drain output queues
            for r in self.runners:
                while True:
                    try:
                        line = r.queue.get_nowait()
                    except queue.Empty:
                        break
                    if line == "__PROCESS_EXIT__":
                        st = self.states.get(r.name)
                        if st:
                            st.state = "stopped"
                            st.last_update = time.time()
                            if st.uptime_stop is None:
                                st.uptime_stop = st.last_update
                        continue
                    st = self.states.get(r.name)
                    if not st:
                        continue
                    st.last_line = line
                    payload = parse_status_line(line)
                    if payload:
                        new_state = payload.get("state", st.state)
                        if new_state == "captcha_solved" and st.state != "captcha_solved":
                            st.captchas_done += 1
                        st.state = new_state
                        st.wave = int(payload.get("wave", st.wave) or 0)
                        st.captcha_attempts = int(payload.get("captcha_attempts", st.captcha_attempts) or 0)
                        st.no_battle = int(payload.get("no_battle", st.no_battle) or 0)
                        if "no_upgrades" in payload:
                            st.no_upgrades = bool(payload.get("no_upgrades"))
                        if "autobattle" in payload:
                            st.autobattle = bool(payload.get("autobattle"))
                        if new_state == "error" and payload.get("message"):
                            st.error = str(payload.get("message"))
                        elif new_state and new_state != "error":
                            st.error = None
                        st.last_update = time.time()
                        outcome = payload.get("outcome")
                        if new_state == "wave_end" and outcome in ("W", "L"):
                            st.last_outcomes.append(outcome)

            # Update UI rows
            for name, st in self.states.items():
                self._update_table_row(name, st)

        finally:
            self.after(self.refresh_ms, self._tick)


def main():
    parser = argparse.ArgumentParser(description="GrowCastle GUI Dashboard")
    parser.add_argument("--config", type=str, default="config.json", help="Config file for instances (per instance)")
    parser.add_argument("--script", type=str, default="growcastle.py", help="Script to run for each instance")
    parser.add_argument("--instances", type=str, default="instances.json", help="instances.json with device/name entries")
    parser.add_argument("--python", type=str, default=sys.executable, help="Python interpreter to run instances")
    parser.add_argument("--extra-args", type=str, nargs=argparse.REMAINDER, default=[], help="Extra args for each instance after --")
    parser.add_argument("--refresh-ms", type=int, default=120, help="GUI refresh interval in ms (default 120)")
    args = parser.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))

    extra = list(args.extra_args or [])
    if extra and extra[0] == "--":
        extra = extra[1:]

    # Load instances
    cfg_path = os.path.abspath(args.instances)
    data = None
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        print(f"Instances file not found: {cfg_path}", file=sys.stderr)
        sys.exit(2)

    items = data.get("instances", []) if isinstance(data, dict) else []
    script = data.get("script", args.script) if isinstance(data, dict) else args.script
    py = data.get("python", args.python) if isinstance(data, dict) else args.python

    runners: List[InstanceRunner] = []
    states: Dict[str, InstanceState] = {}
    runners_by_name: Dict[str, InstanceRunner] = {}

    for idx, item in enumerate(items, start=1):
        device = item.get("device")
        name = item.get("name") or f"bot-{idx:02d}"
        if not device:
            print(f"Skipping entry {idx}: missing 'device'", file=sys.stderr)
            continue
        inst_config = item.get("config") or args.config
        inst_extra = item.get("extra_args") or extra
        runner = InstanceRunner(py, root, script, name, device, inst_config, inst_extra)
        runners.append(runner)
        st = InstanceState(name=name, device=device, pid=None)
        states[name] = st
        runners_by_name[name] = runner
        runner.start()
        st.pid = runner.proc.pid if runner.proc else None
        st.uptime_start = time.time()
        st.state = "starting"

    app = DashboardGUI(runners, states, runners_by_name, refresh_ms=int(args.refresh_ms))
    try:
        app.mainloop()
    finally:
        for r in runners:
            r.terminate()


if __name__ == "__main__":
    main()
