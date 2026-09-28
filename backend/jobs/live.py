"""Live browser view + run controls.

LiveHub keeps the latest browser frame for every run (JPEG on disk + metadata in memory and in
frames.json so replays survive restarts). RunControl lets the UI pause, resume, single-step and stop
a run, and lets the agent block on a human decision (e.g. "Confirm this booking?").
"""
import json
import os
import threading
import time

from backend.config import settings


class StopRequested(Exception):
    pass


class RunControl:
    def __init__(self, step_mode: bool = False):
        self.cond = threading.Condition()
        self.paused = step_mode
        self.step_mode = step_mode
        self.stop = False
        self.pending: dict | None = None     # {"message": str, "kind": "approval", "asked_at": ts}
        self.response: dict | None = None

    # ---- called from the API ----
    def command(self, action: str):
        with self.cond:
            if action == "pause":
                self.paused = True
            elif action == "resume":
                self.paused, self.step_mode = False, False
            elif action == "step":
                self.step_mode, self.paused = True, False   # run exactly one action, then pause again
            elif action == "stop":
                self.stop = True
            else:
                raise ValueError(f"Unknown control action '{action}'")
            self.cond.notify_all()

    def respond(self, approve: bool, note: str | None = None):
        with self.cond:
            if not self.pending:
                raise ValueError("This run is not waiting for a decision")
            self.response = {"approve": approve, "note": note}
            self.cond.notify_all()

    # ---- called from the browser worker thread ----
    def checkpoint(self, on_pause=None):
        """Block while paused; raise if stopped. Call before every browser action."""
        with self.cond:
            notified = False
            while self.paused and not self.stop:
                if on_pause and not notified:
                    on_pause()
                    notified = True
                self.cond.wait(0.5)
            if self.stop:
                raise StopRequested()

    def after_action(self):
        with self.cond:
            if self.step_mode:
                self.paused = True

    def ask(self, message: str, timeout_s: float) -> dict:
        with self.cond:
            self.pending, self.response = {"message": message, "kind": "approval", "asked_at": time.time()}, None
            end = time.time() + timeout_s
            while self.response is None and not self.stop and time.time() < end:
                self.cond.wait(0.5)
            resp, self.pending = self.response, None
            if self.stop:
                raise StopRequested()
            return resp or {"approve": False, "note": f"No decision within {int(timeout_s // 60)} minutes"}

    def snapshot(self):
        return {"paused": self.paused, "step_mode": self.step_mode, "stopping": self.stop, "awaiting_input": self.pending}


class LiveHub:
    def __init__(self):
        self._lock = threading.Lock()
        self.runs: dict[str, dict] = {}
        self.controls: dict[str, RunControl] = {}

    def _dir(self, run_id):
        d = os.path.join(settings.snapshot_dir, run_id, "frames")
        os.makedirs(d, exist_ok=True)
        return d

    def start(self, run_id, steps, options):
        with self._lock:
            self.runs[run_id] = {"seq": 0, "frames": [], "steps": [{"order": s["order"], "tool": s["tool"],
                                 "purpose": s.get("purpose", ""), "target": s.get("target"), "status": "pending"} for s in steps],
                                 "step_index": None, "caption": "Starting browser", "url": None, "engine": None,
                                 "options": options, "vars": {}}
            self.controls[run_id] = RunControl(step_mode=bool(options.get("step_mode")))
        return self.controls[run_id]

    def control(self, run_id) -> RunControl | None:
        return self.controls.get(run_id)

    def update(self, run_id, **kw):
        with self._lock:
            st = self.runs.get(run_id)
            if st:
                st.update(kw)

    def step_status(self, run_id, index, status):
        with self._lock:
            st = self.runs.get(run_id)
            if st and 0 <= index < len(st["steps"]):
                st["steps"][index]["status"] = status
                st["step_index"] = index

    def frame(self, run_id, jpeg: bytes, caption: str, url: str | None, step_index: int | None):
        with self._lock:
            st = self.runs.get(run_id)
            if not st:
                return
            st["seq"] += 1
            seq = st["seq"]
        path = os.path.join(self._dir(run_id), f"{seq:05d}.jpg")
        with open(path, "wb") as f:
            f.write(jpeg)
        meta = {"seq": seq, "caption": caption, "url": url, "step_index": step_index, "at": time.time()}
        with self._lock:
            st["frames"].append(meta)
            st.update(caption=caption, url=url)
            frames = list(st["frames"])
        try:
            with open(os.path.join(self._dir(run_id), "frames.json"), "w", encoding="utf-8") as f:
                json.dump(frames, f)
        except OSError:
            pass

    def state(self, run_id, since: int = 0) -> dict | None:
        with self._lock:
            st = self.runs.get(run_id)
            if st:
                out = {k: v for k, v in st.items() if k != "frames"}
                out["steps"] = [dict(s) for s in st["steps"]]
                out["frames"] = [f for f in st["frames"] if f["seq"] > since][-200:]
                ctl = self.controls.get(run_id)
                out["control"] = ctl.snapshot() if ctl else None
                out["live"] = True
                return out
        path = os.path.join(settings.snapshot_dir, run_id, "frames", "frames.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                frames = json.load(f)
            last = frames[-1] if frames else {}
            return {"seq": last.get("seq", 0), "frames": [x for x in frames if x["seq"] > since], "steps": [],
                    "caption": last.get("caption"), "url": last.get("url"), "control": None, "live": False}
        return None

    def frame_path(self, run_id, seq):
        return os.path.join(settings.snapshot_dir, run_id, "frames", f"{int(seq):05d}.jpg")

    def finish(self, run_id):
        with self._lock:
            self.controls.pop(run_id, None)
            st = self.runs.get(run_id)
            if st:
                st["finished_at"] = time.time()
            # keep finished runs' live state for 10 minutes for the live wall
            cutoff = time.time() - 600
            for rid in [r for r, s in self.runs.items() if s.get("finished_at", time.time()) < cutoff]:
                self.runs.pop(rid, None)


hub = LiveHub()
