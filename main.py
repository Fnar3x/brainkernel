#!/usr/bin/env python3
"""BrainKernel v3.4.0 - AI Process Manager"""

import psutil
import os
import json
import urllib.request
import urllib.error
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.widgets import Static, DataTable, Footer, Input, Button
from textual.screen import ModalScreen
from textual import work

VER = "3.4.0"
CFG = Path.home() / ".brainkernel.json"
GROQ_MODEL = "llama-3.1-8b-instant"
OLLAMA_URL = "http://localhost:11434"
FAKE_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

active_ollama_model = None
api_key = os.environ.get("GROQ_API_KEY")
logs = []
tick_count = 0
protected_pids = set()
lowered_pids = set()
suspended_pids = set()
foreground_pid = None
kill_on_sight = set()
kill_history = {}
adaptive_threshold = 15.0
bad_actors = {}
hall_of_shame = []
focus_app = None
focus_mode_active = False
ollama_available = False
llm_thinking = False
process_static_cache = {}
dismissed_names = set()
decision_cache = {}


@dataclass
class ProcessRecord:
    first_seen: float
    violation_count: int
    last_cpu: float
    last_mem: float
    create_time: float = 0.0
    name: str = ""


process_history: dict[int, ProcessRecord] = {}

SAFE = [
    'system', 'csrss', 'wininit', 'services', 'lsass', 'svchost',
    'explorer', 'dwm', 'winlogon', 'smss', 'registry', 'idle',
    'systemd', 'init', 'kthreadd', 'launchd', 'audiodg', 'fontdrvhost'
]

IMMUNE_CATEGORIES = ['browser', 'social', 'media', 'dev_tool', 'gaming']

PROCESS_INFO = {
    'mongod': ('MongoDB', 'database'),
    'chrome': ('Chrome', 'browser'),
    'firefox': ('Firefox', 'browser'),
    'msedge': ('Edge', 'browser'),
    'brave': ('Brave', 'browser'),
    'opera': ('Opera', 'browser'),
    'vivaldi': ('Vivaldi', 'browser'),
    'code': ('VS Code', 'dev_tool'),
    'node': ('Node.js', 'dev_tool'),
    'python': ('Python', 'dev_tool'),
    'java': ('Java', 'dev_tool'),
    'discord': ('Discord', 'social'),
    'slack': ('Slack', 'social'),
    'teams': ('Teams', 'social'),
    'zoom': ('Zoom', 'social'),
    'webex': ('Webex', 'social'),
    'spotify': ('Spotify', 'media'),
    'obs': ('OBS', 'media'),
    'vlc': ('VLC', 'media'),
    'steam': ('Steam', 'gaming'),
    'epic': ('Epic Games', 'gaming'),
    'kiro': ('Kiro', 'dev_tool'),
}

BLOATWARE = [
    'Lenovo.Modern.ImController', 'LenovoVantage', 'ImController',
    'ArmouryCrate', 'AsusOptimization', 'ROGLiveService',
    'GeForce Experience', 'NVDisplay.Container', 'NVIDIA Web Helper',
    'McAfee', 'Norton', 'Avast', 'AVG', 'CCleaner', 'DriverBooster',
    'IObit', 'Razer Synapse', 'RazerCentral', 'SteelSeriesEngine',
    'LogiOptions', 'CorsairService', 'iCUE', 'HPSupportAssistant',
    'DellSupportAssist', 'AcerQuickAccess', 'TouchpointAnalytics', 'Tobii',
]

USER_LAUNCHERS = [
    'explorer.exe', 'cmd.exe', 'powershell.exe', 'wt.exe',
    'windowsterminal.exe', 'bash', 'zsh', 'fish', 'Terminal'
]

CSS = """
Screen { background: #0a0a0a; }
#hdr { height: 5; }
#logo { color: #ff8000; text-align: center; text-style: bold; }
#heartbeat { color: #666; text-align: center; height: 1; }
#ver { color: #ff8000; text-align: right; }
#main { height: 1fr; }
#procs { width: 55%; background: #1a1a1a; border: solid #ff8000; }
#log_panel { width: 45%; background: #0f111a; border: solid #ff8000; }
.ttl { color: #ff8000; text-style: bold; padding: 1; text-align: center; background: #1a1a1a; }
#tbl { height: 1fr; }
#tbl > .datatable--header { color: #ff8000; background: #1a1a1a; text-style: bold; }
#tbl > .datatable--cursor { background: #333; }
#scroll { height: 1fr; padding: 0 1; }
#dials { height: 6; background: #1a1a1a; border: solid #ff8000; }
#dr { height: 100%; align: center middle; }
.d { width: 1fr; height: 4; content-align: center middle; }
Footer { background: #1a1a1a; }
Footer > .footer--key { color: #ff8000; background: #0a0a0a; }
KeyScreen { align: center middle; }
#box { width: 60; height: 14; background: #1a1a1a; border: solid #ff8000; padding: 1 2; }
#t { color: #ff8000; text-align: center; text-style: bold; }
#s { color: #666; text-align: center; }
#i { margin: 1 0; width: 100%; }
#btns { height: 3; align: center middle; margin-top: 1; }
Button { margin: 0 1; min-width: 10; }
ConfirmScreen { align: center middle; }
#confirm-box { width: 60; height: 14; background: #1a1a1a; border: solid #f00; padding: 1 2; }
#confirm-title { color: #f00; text-align: center; text-style: bold; }
#confirm-msg { color: #fff; text-align: center; padding: 1; }
#confirm-reason { color: #666; text-align: center; }
FocusScreen { align: center middle; }
#focus-box { width: 60; height: 14; background: #1a1a1a; border: solid #0ff; padding: 1 2; }
#focus-title { color: #0ff; text-align: center; text-style: bold; }
"""

LOGO = """[#ff8000]╔╗ ╦═╗╔═╗╦╔╗╔╦╔═╔═╗╦═╗╔╗╔╔═╗╦  
╠╩╗╠╦╝╠═╣║║║║╠╩╗║╣ ╠╦╝║║║║╣ ║  
╚═╝╩╚═╩ ╩╩╝╚╝╩ ╩╚═╝╩╚═╝╚╝╚═╝╩═╝[/]"""


def check_ollama() -> bool:
    global active_ollama_model
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as r:
            if r.status == 200:
                data = json.loads(r.read())
                models = [m['name'] for m in data.get('models', [])]
                if not models:
                    return False
                for p in ['llama3.2', 'llama3.1', 'llama3', 'mistral', 'gemma', 'deepseek']:
                    matches = [m for m in models if p in m]
                    if matches:
                        active_ollama_model = matches[0]
                        break
                if not active_ollama_model:
                    active_ollama_model = models[0]
                return True
    except:
        pass
    return False


def call_ollama(prompt: str, json_mode: bool = False) -> Optional[str]:
    try:
        payload = {"model": active_ollama_model, "prompt": prompt, "stream": False}
        if json_mode:
            payload["format"] = "json"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("response", "").strip()
    except:
        return None


def call_groq(prompt: str, json_mode: bool = False) -> Optional[str]:
    if not api_key:
        return None
    try:
        payload = {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 100,
            "temperature": 0.7
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key.strip()}",
            "User-Agent": FAKE_USER_AGENT
        }
        req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data, headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            resp = json.loads(r.read())
            if resp and "choices" in resp:
                return resp["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        return f"API ERROR: {e.code}"
    except:
        pass
    return None


def call_llm(prompt: str, json_mode: bool = False) -> Optional[str]:
    global llm_thinking
    llm_thinking = True
    try:
        if ollama_available:
            res = call_ollama(prompt, json_mode)
            if res:
                return res
        return call_groq(prompt, json_mode)
    finally:
        llm_thinking = False


def safe_kill(pid: int, ctime: float, name: str) -> bool:
    try:
        p = psutil.Process(pid)
        if abs(p.create_time() - ctime) < 0.1 and p.name() == name:
            p.terminate()
            return True
    except:
        pass
    return False


def safe_suspend(pid: int, ctime: float, name: str) -> bool:
    try:
        p = psutil.Process(pid)
        if abs(p.create_time() - ctime) < 0.1 and p.name() == name:
            p.suspend()
            return True
    except:
        pass
    return False


def safe_resume(pid: int) -> bool:
    try:
        psutil.Process(pid).resume()
        return True
    except:
        return False


def nice_process(pid: int, ctime: float, name: str) -> bool:
    try:
        p = psutil.Process(pid)
        if abs(p.create_time() - ctime) > 0.1 or p.name() != name:
            return False
        if os.name == 'posix':
            p.nice(10)
        elif os.name == 'nt':
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        return True
    except:
        return False


def get_foreground_pid() -> Optional[int]:
    if os.name == 'nt':
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return pid.value
        except:
            pass
    return None


def load_config():
    global api_key, kill_on_sight, bad_actors, hall_of_shame, focus_app
    try:
        cfg = json.loads(CFG.read_text())
        api_key = cfg.get("k")
        kill_on_sight = set(cfg.get("kill_on_sight", []))
        bad_actors = cfg.get("bad_actors", {})
        hall_of_shame = cfg.get("hall_of_shame", [])[:20]
        focus_app = cfg.get("focus_app")
    except:
        pass
    if not api_key:
        api_key = os.environ.get("GROQ_API_KEY")


def save_config():
    try:
        cfg = {
            "k": api_key,
            "kill_on_sight": list(kill_on_sight),
            "bad_actors": bad_actors,
            "hall_of_shame": hall_of_shame[:20],
            "focus_app": focus_app
        }
        CFG.write_text(json.dumps(cfg, indent=2))
    except:
        pass


def save_key(k: str):
    global api_key
    api_key = k
    save_config()


def add_to_kill_list(name: str):
    kill_on_sight.add(name.lower())
    save_config()


def add_to_hall_of_shame(name: str, roast: str, action: str):
    global hall_of_shame
    hall_of_shame.insert(0, {
        "process": name,
        "roast": roast,
        "action": action,
        "time": time.strftime("%Y-%m-%d %H:%M")
    })
    hall_of_shame = hall_of_shame[:20]
    save_config()


def should_auto_kill(name: str) -> bool:
    return name.lower() in kill_on_sight


def is_safe(name: str) -> bool:
    return any(s in name.lower() for s in SAFE)


def is_bloatware(name: str) -> bool:
    return any(b.lower() in name.lower() for b in BLOATWARE)


def get_reputation(name: str) -> dict:
    return bad_actors.get(name.lower(), {'kills': 0, 'violations': 0})


def get_process_info(name: str) -> Tuple[Optional[str], Optional[str]]:
    n = name.lower().replace('.exe', '')
    for key, (desc, cat) in PROCESS_INFO.items():
        if key in n:
            return desc, cat
    return None, None


def track_violation(name: str):
    name_lower = name.lower()
    if name_lower not in bad_actors:
        bad_actors[name_lower] = {'kills': 0, 'violations': 0}
    bad_actors[name_lower]['violations'] += 1
    if bad_actors[name_lower]['violations'] % 10 == 0:
        save_config()


def track_manual_kill(name: str) -> bool:
    name_lower = name.lower()
    if name_lower not in kill_history:
        kill_history[name_lower] = 0
    kill_history[name_lower] += 1
    if name_lower not in bad_actors:
        bad_actors[name_lower] = {'kills': 0, 'violations': 0}
    bad_actors[name_lower]['kills'] += 1
    save_config()
    return kill_history[name_lower] >= 3 and name_lower not in kill_on_sight


def get_deep_context(pid: int) -> dict:
    try:
        p = psutil.Process(pid)
        try:
            io = p.io_counters()
            total = io.read_bytes + io.write_bytes
            if total > 10_000_000:
                pattern = "Heavy"
            elif total > 100_000:
                pattern = "Active"
            else:
                pattern = "Idle"
        except:
            pattern = "Unknown"

        try:
            parent = p.parent()
            pname = parent.name() if parent else "Unknown"
            ctx = "User" if pname.lower() in [u.lower() for u in USER_LAUNCHERS] else "System"
        except:
            pname, ctx = "Unknown", "Unknown"

        return {'io_pattern': pattern, 'parent_name': pname, 'launch_context': ctx}
    except:
        return {'io_pattern': "Unknown", 'parent_name': "Unknown", 'launch_context': "Unknown"}


def update_history(pid: int, cpu: float, mem: float, ctime: float, name: str, threshold: float) -> int:
    now = time.time()
    if pid not in process_history:
        process_history[pid] = ProcessRecord(
            first_seen=now, violation_count=0,
            last_cpu=cpu, last_mem=mem,
            create_time=ctime, name=name
        )
    rec = process_history[pid]
    rec.violation_count = rec.violation_count + 1 if cpu > threshold else 0
    rec.last_cpu = cpu
    rec.last_mem = mem
    return rec.violation_count


def get_history_info(pid: int) -> Tuple[str, int]:
    if pid not in process_history:
        return "New", 0
    rec = process_history[pid]
    elapsed = time.time() - rec.first_seen
    if elapsed < 60:
        t_str = f"{int(elapsed)}s"
    elif elapsed < 3600:
        t_str = f"{int(elapsed/60)}m"
    else:
        t_str = f"{int(elapsed/3600)}h"
    return t_str, rec.violation_count


def update_adaptive_threshold(procs: list):
    global adaptive_threshold
    loads = [p['cpu'] for p in procs if p['cpu'] > 1.0]
    if not loads:
        adaptive_threshold = 15.0
        return
    adaptive_threshold = max(10.0, min(50.0, (sum(loads) / len(loads)) * 2.5))


def build_json_prompt(proc: dict, deep_ctx: dict, fg_name: str) -> str:
    name = proc['name']
    desc, cat = get_process_info(name)
    time_str, violations = get_history_info(proc['pid'])
    is_bloat = is_bloatware(name)
    rep = get_reputation(name)

    notes = ""
    if desc:
        notes += f" ({desc})"
    if is_bloat:
        notes += " [BLOATWARE]"
    if rep['kills'] >= 2:
        notes += f" [KILLED {rep['kills']}x]"

    return f"""Analyze this process. User is working.
CONTEXT:
- Foreground: {fg_name}
- Target: {name}{notes}
- CPU: {proc['cpu']:.0f}%, MEM: {proc['mem']:.1f}%
- Parent: {deep_ctx['parent_name']} ({deep_ctx['launch_context']})
- Disk: {deep_ctx['io_pattern']}
- Running: {time_str}, Violations: {violations}
RULES:
- If Browser/Chat/DevTool/Media -> IGNORE or LOWER only. (NEVER KILL/SUSPEND).
- If Bloatware -> KILL.
- Return "action": "ignore" if unsure.
Return ONLY JSON: {{"action": "ignore|lower|suspend|kill", "roast": "Funny 10-word roast"}}"""


def parse_llm_decision(response: str) -> Tuple[Optional[str], Optional[str]]:
    if not response:
        return None, None
    try:
        if "```" in response:
            response = response.split("```")[1].replace("json", "").strip()
        data = json.loads(response)
        action = data.get("action", "").lower()
        if action in ("kill", "suspend", "lower"):
            return action, data.get("roast", "")
        return None, data.get("roast", "")
    except:
        return None, response


def get_smart_decision(proc: dict, fg_name: str) -> Tuple[Optional[str], Optional[str]]:
    name, pid = proc['name'], proc['pid']

    # debounce - don't spam decisions for same process
    if pid in decision_cache and (time.time() - decision_cache[pid]) < 300:
        return None, None

    desc, cat = get_process_info(name)
    if cat in IMMUNE_CATEGORIES:
        if proc['cpu'] > 60:
            return "lower", f"{name} is heavy, lowering priority"
        return None, None

    deep = get_deep_context(pid)
    _, violations = get_history_info(pid)

    # fallback when no llm
    if not ollama_available and not api_key:
        if is_bloatware(name) and pid != foreground_pid:
            return "kill", f"Detected bloatware {name}"
        if violations > 5 and proc['cpu'] > 40:
            return "lower", f"{name} is hogging CPU"
        return None, None

    prompt = build_json_prompt(proc, deep, fg_name)
    response = call_llm(prompt, json_mode=True)
    decision_cache[pid] = time.time()
    return parse_llm_decision(response)


def color(p: float) -> str:
    if p < 30:
        return "#0f0"
    elif p < 60:
        return "#ff0"
    elif p < 80:
        return "#ff8000"
    return "#f00"


def bar(p: float, lbl: str) -> str:
    c = color(p)
    n = int(p / 10)
    return f"[#444]\\[[/][{c}]{'█'*n}[/][#222]{'░'*(10-n)}[/][#444]\\][/] [{c}]{p:4.0f}%[/] [#ff8000]{lbl}[/]"


def bar2(v: int, lbl: str) -> str:
    p = min(100, v / 5)
    c = color(p)
    n = int(p / 10)
    return f"[#444]\\[[/][{c}]{'█'*n}[/][#222]{'░'*(10-n)}[/][#444]\\][/] [{c}]{v:4}[/] [#ff8000]{lbl}[/]"


class KeyScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Close"), ("enter", "save_key", "Save")]

    def compose(self):
        yield Container(
            Static("BYOK - Bring Your Own Key", id="t"),
            Static("Groq API key (optional)", id="s"),
            Input(placeholder="gsk_...", id="i", value=api_key or ""),
            Horizontal(Button("Save", id="save"), Button("Cancel", id="cancel"), id="btns"),
            id="box"
        )

    def on_button_pressed(self, e):
        if e.button.id == "save":
            self.do_save()
        else:
            self.dismiss(False)

    def action_save_key(self):
        self.do_save()

    def do_save(self):
        k = self.query_one("#i", Input).value.strip()
        if k:
            save_key(k)
        self.dismiss(True)


class ConfirmScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Close"), ("y", "yes", "Yes"), ("n", "no", "No")]

    def __init__(self, name, pid, action, reason, ctime):
        super().__init__()
        self.n = name
        self.p = pid
        self.a = action
        self.r = reason
        self.ct = ctime

    def compose(self):
        yield Container(
            Static(f"CONFIRM {self.a.upper()}", id="confirm-title"),
            Static(f"{self.a.upper()} {self.n} (PID {self.p})?", id="confirm-msg"),
            Static(self.r, id="confirm-reason"),
            Horizontal(Button("Yes (Y)", id="yes"), Button("No (N)", id="no"), id="btns"),
            id="confirm-box"
        )

    def on_button_pressed(self, e):
        self.dismiss(e.button.id == "yes")

    def action_yes(self):
        self.dismiss(True)

    def action_no(self):
        self.dismiss(False)


class FocusScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Close"), ("enter", "set_focus", "Set")]

    def compose(self):
        yield Container(
            Static("FOCUS MODE", id="focus-title"),
            Static("Enter app name to protect", id="s"),
            Input(placeholder="App name...", id="i", value=focus_app or ""),
            Horizontal(
                Button("Set", id="set"),
                Button("Clear", id="clear"),
                Button("Cancel", id="cancel"),
                id="btns"
            ),
            id="focus-box"
        )

    def on_button_pressed(self, e):
        global focus_app, focus_mode_active
        if e.button.id == "set":
            self.do_set()
        elif e.button.id == "clear":
            focus_app = None
            focus_mode_active = False
            save_config()
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_set_focus(self):
        self.do_set()

    def do_set(self):
        global focus_app, focus_mode_active
        focus_app = self.query_one("#i", Input).value.strip().lower()
        focus_mode_active = bool(focus_app)
        save_config()
        self.dismiss(True)


class BrainKernel(App):
    CSS = CSS
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("k", "key", "Key"),
        ("p", "protect", "Protect"),
        ("r", "resume_all", "Resume"),
        ("x", "begone", "Begone!"),
        ("f", "focus", "Focus"),
        ("s", "shame", "Shame"),
        ("n", "roast_now", "Roast Now")
    ]

    def compose(self) -> ComposeResult:
        yield Container(
            Static(LOGO, id="logo"),
            Static("", id="heartbeat"),
            Static(f"v{VER}", id="ver"),
            id="hdr"
        )
        yield Horizontal(
            Container(Static("PROCESS MONITOR", classes="ttl"), DataTable(id="tbl"), id="procs"),
            Container(Static("BRAIN STREAM", classes="ttl"), ScrollableContainer(id="scroll"), id="log_panel"),
            id="main"
        )
        yield Container(
            Horizontal(
                Static("", id="d1", classes="d"),
                Static("", id="d2", classes="d"),
                Static("", id="d3", classes="d"),
                id="dr"
            ),
            id="dials"
        )
        yield Footer()

    def on_mount(self):
        global ollama_available
        psutil.cpu_percent()
        t = self.query_one("#tbl", DataTable)
        t.add_columns("PID", "NAME", "CPU%", "MEM%", "STATUS")
        t.cursor_type = "row"
        load_config()
        ollama_available = check_ollama()

        self.log_msg(f"[#0f0]> BRAINKERNEL v{VER}[/]")
        if ollama_available:
            self.log_msg(f"[#0f0]> 🦙 LOCAL ({active_ollama_model})[/]")
        elif api_key:
            self.log_msg("[#ff0]> ☁️ CLOUD[/]")
        else:
            self.log_msg("[#ff0]> ⚡ HEURISTIC[/]")
        if focus_app:
            self.log_msg(f"[#0ff]> Focus: {focus_app}[/]")

        self.set_interval(2.0, self.tick)

    def action_key(self):
        self.push_screen(KeyScreen())

    def action_focus(self):
        self.push_screen(FocusScreen())

    def action_shame(self):
        self.log_msg("[#f0f]═══ HALL OF SHAME ═══[/]")
        for e in hall_of_shame[:5]:
            self.log_msg(f"[#ff8000]{e['process']}[/] → {e['roast']}")

    def action_roast_now(self):
        self.log_msg("[#0ff]> 🍳 Forcing roast...[/]")
        top = sorted(process_static_cache.values(), key=lambda x: x.get('cpu', 0), reverse=True)[:10]
        self.run_commentary(top)

    def action_protect(self):
        t = self.query_one("#tbl", DataTable)
        if t.cursor_row is not None:
            pid = int(t.get_row_at(t.cursor_row)[0])
            if pid in protected_pids:
                protected_pids.remove(pid)
                self.log_msg(f"[#ff0]> Unprotected {pid}[/]")
            else:
                protected_pids.add(pid)
                self.log_msg(f"[#0f0]> Protected {pid}[/]")

    def action_resume_all(self):
        for pid in list(suspended_pids):
            if safe_resume(pid):
                self.log_msg(f"[#0f0]> Resumed {pid}[/]")
        suspended_pids.clear()

    def action_begone(self):
        t = self.query_one("#tbl", DataTable)
        if t.cursor_row is not None:
            pid = int(t.get_row_at(t.cursor_row)[0])
            if pid in process_static_cache:
                name = process_static_cache[pid]['name']
                if is_safe(name):
                    self.log_msg("[#f00]> System process![/]")
                    return
                add_to_kill_list(name)
                self.log_msg(f"[#f00]> Banned {name}[/]")
                if safe_kill(pid, process_static_cache[pid]['create_time'], name):
                    self.log_msg(f"[#f00]> Killed {name}[/]")

    def log_msg(self, msg: str):
        global logs
        logs.insert(0, msg)
        del logs[30:]
        try:
            sc = self.query_one("#scroll", ScrollableContainer)
            sc.remove_children()
            for line in logs:
                sc.mount(Static(line))
        except:
            pass

    def do_action(self, proc, action, reason, ctime):
        pid, name = proc['pid'], proc['name']
        name_lower = name.lower()

        if pid in protected_pids or is_safe(name) or name_lower in dismissed_names:
            return

        self.log_msg(f"[#0ff]> THINKING: {name}...[/]")

        if action == "lower" and pid not in lowered_pids:
            if nice_process(pid, ctime, name):
                lowered_pids.add(pid)
                self.log_msg(f"[#ff0]> LOWERED[/] {name}")
                add_to_hall_of_shame(name, reason, "lower")

        elif action == "suspend":
            def callback(ok):
                if ok and safe_suspend(pid, ctime, name):
                    suspended_pids.add(pid)
                    self.log_msg(f"[#f00]> SUSPENDED[/] {name}")
                    add_to_hall_of_shame(name, reason, "suspend")
                else:
                    dismissed_names.add(name_lower)
                    self.log_msg(f"[#666]> Ignoring {name}[/]")
            self.push_screen(ConfirmScreen(name, pid, "suspend", reason, ctime), callback)

        elif action == "kill":
            def callback(ok):
                if ok and safe_kill(pid, ctime, name):
                    self.log_msg(f"[#f00]> KILLED[/] {name}")
                    add_to_hall_of_shame(name, reason, "kill")
                    if track_manual_kill(name):
                        def ban_callback(bok):
                            if bok:
                                add_to_kill_list(name)
                                self.log_msg(f"[#f00]> BANNED {name}[/]")
                        self.push_screen(ConfirmScreen(name, 0, "PERMA-BAN", "Ban forever?", 0), ban_callback)
                else:
                    dismissed_names.add(name_lower)
                    self.log_msg(f"[#666]> Ignoring {name}[/]")
            self.push_screen(ConfirmScreen(name, pid, "kill", reason, ctime), callback)

    def tick(self):
        global tick_count, foreground_pid
        tick_count += 1
        MY_PID = os.getpid()

        try:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            cnt = len(psutil.pids())
            self.query_one("#d1", Static).update(bar(cpu, "CPU"))
            self.query_one("#d2", Static).update(bar(mem, "MEM"))
            self.query_one("#d3", Static).update(bar2(cnt, "PRC"))

            hb = self.query_one("#heartbeat", Static)
            if llm_thinking:
                hb.update(f"[#ff8000]{'●' if tick_count % 2 == 0 else '○'} THINKING...[/]")
            else:
                hb.update(f"[#666]{'🦙 LOCAL' if ollama_available else '☁️ CLOUD'}[/]")
        except:
            pass

        current_pids = set()
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                pid = p.info['pid']
                if pid == 0 or pid == MY_PID:
                    continue
                current_pids.add(pid)
                if pid in process_static_cache:
                    process_static_cache[pid]['cpu'] = p.info['cpu_percent'] or 0
                    process_static_cache[pid]['mem'] = p.info['memory_percent'] or 0
                else:
                    p_obj = psutil.Process(pid)
                    process_static_cache[pid] = {
                        'pid': pid,
                        'name': p.info['name'] or '?',
                        'cpu': p.info['cpu_percent'] or 0,
                        'mem': p.info['memory_percent'] or 0,
                        'create_time': p_obj.create_time()
                    }
            except:
                pass

        for pid in list(process_static_cache.keys()):
            if pid not in current_pids:
                del process_static_cache[pid]

        all_procs = sorted(process_static_cache.values(), key=lambda x: x['cpu'], reverse=True)
        foreground_pid = get_foreground_pid()
        update_adaptive_threshold(all_procs)

        t = self.query_one("#tbl", DataTable)
        t.clear()

        for p in all_procs[:50]:
            v = update_history(p['pid'], p['cpu'], p['mem'], p['create_time'], p['name'], adaptive_threshold)
            if v > 0 and not is_safe(p['name']):
                track_violation(p['name'])

            if should_auto_kill(p['name']) and p['pid'] != foreground_pid:
                if safe_kill(p['pid'], p['create_time'], p['name']):
                    self.log_msg(f"[#f00]> Auto-killed {p['name']}[/]")

            if focus_mode_active and focus_app:
                if focus_app not in p['name'].lower() and p['cpu'] > 5:
                    if p['pid'] != foreground_pid and not is_safe(p['name']):
                        if safe_suspend(p['pid'], p['create_time'], p['name']):
                            suspended_pids.add(p['pid'])
                            self.log_msg(f"[#0ff]> Focused: suspended {p['name']}[/]")

            status = "[#666]ok[/]"
            if p['pid'] in protected_pids:
                status = "[#0f0]SAFE[/]"
            elif should_auto_kill(p['name']):
                status = "[#f00]BANNED[/]"
            elif p['pid'] in suspended_pids:
                status = "[#f00]PAUSED[/]"
            elif p['pid'] in lowered_pids:
                status = "[#ff0]SLOWED[/]"
            elif p['pid'] == foreground_pid:
                status = "[#0ff]ACTIVE[/]"
            elif is_bloatware(p['name']):
                status = "[#f0f]BLOAT[/]"
            elif p['cpu'] > adaptive_threshold:
                status = "[#f00]HOG[/]"

            t.add_row(str(p['pid']), p['name'][:25], f"{p['cpu']:.0f}", f"{p['mem']:.1f}", status)

        self.run_smart_analysis(all_procs, "Unknown")
        if tick_count % 5 == 0:
            self.run_commentary(all_procs)

    @work(exclusive=True, thread=True)
    def run_smart_analysis(self, procs, fg):
        for p in procs[:20]:
            pid, name = p['pid'], p['name']
            if pid == foreground_pid or pid in protected_pids:
                continue
            if name.lower() in dismissed_names:
                continue
            if pid in lowered_pids or pid in suspended_pids:
                continue
            if is_safe(name) or p['cpu'] <= adaptive_threshold * 0.5:
                continue

            a, r = get_smart_decision(p, fg)
            if a and r:
                self.call_from_thread(self.do_action, p, a, r, p['create_time'])
                break

    @work(exclusive=True, thread=True)
    def run_commentary(self, procs):
        hog = next((p for p in procs if p['cpu'] > adaptive_threshold and not is_safe(p['name']) and p['pid'] != foreground_pid), None)
        if hog:
            c = call_llm(f"{hog['name']} using {hog['cpu']:.0f}% CPU. Give a 10-word savage roast. ONLY text.")
            if c:
                self.call_from_thread(self.log_msg, f"[#f0f]> {c}[/]")


if __name__ == "__main__":
    BrainKernel().run()
