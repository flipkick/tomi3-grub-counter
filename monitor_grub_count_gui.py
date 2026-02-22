"""
Tales of Monkey Island 3 - Live Grub Count Monitor (GUI)
GUI wrapper for monitor_grub_count, polls the running game every second
and displays the current grub count in a window.
Works on Windows (native) and Linux (Proton/Wine).

Threading model:
  A daemon worker thread runs the polling loop (including full memory scans).
  Results are passed back to the GUI thread via a queue.Queue.
  The GUI thread drains the queue every 50 ms via tkinter's after(). It
  never blocks, so the window stays responsive at all times.
"""

import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog

from tomi3_ram import (
    PROCESS_NAME, DEFAULT_OUTPUT_FILE, POLL_INTERVAL,
    find_pid, open_process, close_process, is_process_alive,
    scan_for_count, read_count_at,
)

# How often the GUI thread drains the result queue (ms).
# Keep well below POLL_INTERVAL so updates feel instant.
_QUEUE_CHECK_MS = 50


class GrubMonitorApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Tales of Monkey Island 3 - Grub Count Monitor")
        self.resizable(True, True)
        self.minsize(300, 200)

        self._result_queue = queue.Queue()
        self._stop_event   = threading.Event()

        self._build_ui()
        self.count_var.set(self._read_file_value())

        self._worker = threading.Thread(target=self._poll_loop, daemon=True)
        self._worker.start()
        self._check_queue()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Count display ─────────────────────────────────────────────────────
        disp = ttk.Frame(self, padding=(16, 16, 16, 8))
        disp.pack(fill=tk.BOTH, expand=True)

        ttk.Label(disp, text="Grub Count", font=("TkDefaultFont", 11)).pack()

        self.count_var = tk.StringVar(value="X")
        ttk.Label(
            disp,
            textvariable=self.count_var,
            font=("TkFixedFont", 64, "bold"),
            anchor=tk.CENTER,
        ).pack(expand=True, fill=tk.BOTH)

        # ── Status bar ────────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value=f"Waiting for {PROCESS_NAME}...")
        status = ttk.Frame(self, padding=(8, 0, 8, 4))
        status.pack(fill=tk.X)
        ttk.Label(status, textvariable=self.status_var, anchor=tk.W).pack(fill=tk.X)

        # ── Output file row ───────────────────────────────────────────────────
        bot = ttk.Frame(self, padding=(8, 0, 8, 8))
        bot.pack(fill=tk.X)

        self.write_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bot, text="Write to file:", variable=self.write_var).pack(side=tk.LEFT)

        self.file_var = tk.StringVar(value=DEFAULT_OUTPUT_FILE)
        ttk.Entry(bot, textvariable=self.file_var, width=28).pack(
            side=tk.LEFT, padx=(4, 4), fill=tk.X, expand=True
        )
        ttk.Button(bot, text="...", width=3, command=self._browse_file).pack(side=tk.LEFT)

    # ── GUI-thread helpers ────────────────────────────────────────────────────

    def _read_file_value(self):
        """Read the last known count from the output file, or '?' if unavailable."""
        try:
            with open(self.file_var.get(), "r") as f:
                content = f.read().strip()
                if content:
                    return content
        except OSError:
            pass
        return "?"

    def _browse_file(self):
        path = filedialog.asksaveasfilename(
            initialfile=self.file_var.get(),
            title="Output file",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.file_var.set(path)

    def _check_queue(self):
        """Drain all pending worker results and update the UI (GUI thread)."""
        try:
            while True:
                msg = self._result_queue.get_nowait()
                self._apply(msg)
        except queue.Empty:
            pass
        self.after(_QUEUE_CHECK_MS, self._check_queue)

    def _apply(self, msg):
        """Apply one result message to the UI (always called on GUI thread)."""
        kind = msg["kind"]

        if kind == "status":
            self.status_var.set(msg["text"])
            if msg.get("reset_display"):
                self.count_var.set(self._read_file_value())

        elif kind == "count":
            value   = msg["value"]
            changed = msg["changed"]
            display = str(value) if value is not None else "?"
            self.count_var.set(display)
            if changed:
                if msg.get("status"):
                    self.status_var.set(msg["status"])
                if value is not None and self.write_var.get():
                    try:
                        with open(self.file_var.get(), "w") as f:
                            f.write(display)
                    except OSError as e:
                        self.status_var.set(f"Cannot write file: {e}")

    # ── Worker thread ─────────────────────────────────────────────────────────

    def _poll_loop(self):
        """Background thread: connect, scan, repeat. Never touches the UI directly."""
        handle           = None
        last             = None
        cached_node_addr = None

        def put(msg):
            self._result_queue.put(msg)

        while not self._stop_event.is_set():

            # ── (Re-)connect ──────────────────────────────────────────────────
            if handle is None:
                pid = find_pid(PROCESS_NAME)
                if pid is None:
                    put({"kind": "status",
                         "text": f"Waiting for {PROCESS_NAME}...",
                         "reset_display": True})
                    self._stop_event.wait(POLL_INTERVAL)
                    continue
                try:
                    handle           = open_process(pid)
                    last             = None
                    cached_node_addr = None
                    put({"kind": "status",
                         "text": f"Connected to {PROCESS_NAME} (pid={pid})"})
                except OSError as e:
                    put({"kind": "status", "text": f"Cannot open process: {e}"})
                    self._stop_event.wait(POLL_INTERVAL)
                    continue

            # ── Liveness check ────────────────────────────────────────────────
            if not is_process_alive(handle):
                close_process(handle)
                handle           = None
                last             = None
                cached_node_addr = None
                put({"kind": "status",
                     "text": f"Game exited. Waiting for {PROCESS_NAME}...",
                     "reset_display": True})
                continue

            # ── Read count (cached fast path or full scan) ────────────────────
            try:
                if cached_node_addr is not None and last != 0:
                    value = read_count_at(handle, cached_node_addr)
                    if value is None or (
                        last is not None and (value < last or value > last + 1)
                    ):
                        value, cached_node_addr = scan_for_count(handle)
                else:
                    value, cached_node_addr = scan_for_count(handle)
            except Exception:
                value            = None
                cached_node_addr = None

            changed = value != last
            if value is None:
                status = "Count not found (game not in episode 3?)"
            elif changed:
                status = f"Connected. Grub count: {value}"
            else:
                status = None

            put({"kind": "count", "value": value, "changed": changed, "status": status})
            last = value

            self._stop_event.wait(POLL_INTERVAL)

        # ── Cleanup ───────────────────────────────────────────────────────────
        if handle is not None:
            close_process(handle)

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def destroy(self):
        self._stop_event.set()
        super().destroy()


def main():
    app = GrubMonitorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
