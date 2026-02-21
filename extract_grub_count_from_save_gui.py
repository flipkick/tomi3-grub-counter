import os
import glob
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from tomi3_save import SAVEDIR, read_grub_count


class GrubCountApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tales of Monkey Island 3 Grub Count Reader")
        self.resizable(True, True)
        self.minsize(560, 300)
        self._build_ui()
        self._scan()

    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────────────
        top = ttk.Frame(self, padding=(8, 8, 8, 4))
        top.pack(fill=tk.X)

        ttk.Label(top, text="Save directory:").pack(side=tk.LEFT)

        self.dir_var = tk.StringVar(value=SAVEDIR)
        ttk.Entry(top, textvariable=self.dir_var, width=52).pack(
            side=tk.LEFT, padx=(4, 4), fill=tk.X, expand=True)

        ttk.Button(top, text="Browse…", command=self._browse).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(top, text="Refresh", command=self._scan).pack(side=tk.LEFT)

        # ── Treeview ─────────────────────────────────────────────────────────
        mid = ttk.Frame(self, padding=(8, 0, 8, 4))
        mid.pack(fill=tk.BOTH, expand=True)

        cols = ("file", "count")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("file",  text="Save file",  anchor=tk.W)
        self.tree.heading("count", text="Grub count", anchor=tk.E)
        self.tree.column("file",  stretch=True, anchor=tk.W, minwidth=200)
        self.tree.column("count", width=230,    anchor=tk.E, minwidth=180, stretch=True)

        vsb = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Status bar ───────────────────────────────────────────────────────
        bot = ttk.Frame(self, padding=(8, 2, 8, 6))
        bot.pack(fill=tk.X)
        self.status_var = tk.StringVar()
        ttk.Label(bot, textvariable=self.status_var, anchor=tk.W).pack(fill=tk.X)

        # ── Bottom button ─────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self, padding=(8, 0, 8, 8))
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Open single file…", command=self._open_file).pack(side=tk.LEFT)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get(), title="Select save directory")
        if d:
            self.dir_var.set(d)
            self._scan()

    def _scan(self):
        self.tree.delete(*self.tree.get_children())
        savedir = self.dir_var.get().strip()
        pattern = os.path.join(savedir, "*.save")
        saves = sorted(glob.glob(pattern), reverse=True)

        if not saves:
            self.status_var.set(f"No .save files found in:  {savedir}")
            return

        errors = 0
        for path in saves:
            name = os.path.basename(path)
            count, err = read_grub_count(path)
            if err:
                self.tree.insert("", tk.END, values=(name, err), tags=("error",))
                errors += 1
            else:
                self.tree.insert("", tk.END, values=(name, count))

        self.tree.tag_configure("error", foreground="#c0392b")
        n = len(saves)
        msg = f"{n} file{'s' if n != 1 else ''} found"
        if errors:
            msg += f", {errors} error{'s' if errors != 1 else ''}"
        self.status_var.set(msg)

    def _open_file(self):
        path = filedialog.askopenfilename(
            initialdir=self.dir_var.get(),
            title="Open save file",
            filetypes=[("Save files", "*.save"), ("All files", "*.*")],
        )
        if not path:
            return
        count, err = read_grub_count(path)
        name = os.path.basename(path)
        if err:
            messagebox.showerror("Error", f"{name}\n\n{err}")
        else:
            messagebox.showinfo("Grub Count", f"{name}\n\nGrub Count: {count}")


def main():
    app = GrubCountApp()
    app.mainloop()


if __name__ == "__main__":
    main()
