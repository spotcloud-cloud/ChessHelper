import sys, os, queue, threading, time, ctypes, traceback

def fatal(text):
    try:
        ctypes.windll.user32.MessageBoxW(0, text[-1800:], "ChessHelper", 0x10)
    except Exception:
        pass

try:
    import main          # sets DPI awareness, must come before the window exists
    import vision
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:
    fatal("ChessHelper could not start:\n\n" + traceback.format_exc())
    sys.exit(1)

BG, PANEL, PANEL2 = "#14161c", "#1c1f27", "#2a2f3b"
FG, MUTED = "#e6e8ee", "#8b90a0"
ACCENT, GREEN, RED, AMBER = "#4f8cff", "#3ecf8e", "#ff5c6c", "#f5b942"

MODES = [
    ("play",   "Play a game",    "plays your side in a bot game"),
    ("puzzle", "Single puzzle",  "full strength, stops when solved"),
    ("auto",   "Auto puzzles",   "solves, presses Next, repeats until stopped"),
    ("dry",    "Dry run",        "only prints moves, never clicks"),
]
HIDDEN_IN_SETTINGS = {"game_style", "limit_strength", "elo"}   # these live on the Play tab

# ---- stop button support: main.py's loops call check_failsafe() constantly
stop_event = threading.Event()
_orig_failsafe = main.check_failsafe
def _patched_failsafe():
    if stop_event.is_set():
        raise main.StopKey()
    _orig_failsafe()
main.check_failsafe = _patched_failsafe

DONE = "\0DONE\0"

class QueueWriter:
    def __init__(self, q):
        self.q = q
    def write(self, s):
        if s:
            self.q.put(s)
        return len(s) if s else 0
    def flush(self):
        pass
    def isatty(self):
        return False

class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))

class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.running = False
        self.minimized = False
        sys.stdout = QueueWriter(self.q)
        sys.stderr = QueueWriter(self.q)

        root.title("ChessHelper")
        root.geometry("780x760")
        root.minsize(700, 640)
        root.configure(bg=BG)
        self.make_style()
        self.build()
        root.update()
        try:   # dark title bar on Windows 10/11
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
        except Exception:
            pass
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.log("Ready. Pick a game and a mode, then press Start.")
        self.poll()

    # ------------------------------------------------------------ look
    def make_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL,
                    bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL,
                    troughcolor=PANEL, font=("Segoe UI", 10))
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Muted.TLabel", foreground=MUTED, font=("Segoe UI", 9))
        s.configure("Head.TLabel", font=("Segoe UI", 11, "bold"))
        s.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(18, 8), borderwidth=0)
        s.map("TNotebook.Tab", background=[("selected", PANEL2)], foreground=[("selected", FG)])
        s.configure("TButton", background=PANEL2, foreground=FG, padding=9, borderwidth=0)
        s.map("TButton", background=[("active", "#353b4a"), ("disabled", PANEL)],
              foreground=[("disabled", MUTED)])
        s.configure("Start.TButton", background=ACCENT, foreground="white",
                    font=("Segoe UI", 12, "bold"), padding=12)
        s.map("Start.TButton", background=[("active", "#3b74e0"), ("disabled", PANEL2)])
        s.configure("Stop.TButton", background=RED, foreground="white",
                    font=("Segoe UI", 12, "bold"), padding=12)
        s.map("Stop.TButton", background=[("active", "#e04555"), ("disabled", PANEL2)])
        s.configure("TCheckbutton", background=BG, foreground=FG)
        s.map("TCheckbutton", background=[("active", BG)])
        s.configure("TRadiobutton", background=BG, foreground=FG, padding=3)
        s.map("TRadiobutton", background=[("active", BG)])
        s.configure("TEntry", fieldbackground=PANEL, foreground=FG, insertcolor=FG, padding=5)
        s.configure("TCombobox", fieldbackground=PANEL, background=PANEL2,
                    foreground=FG, arrowcolor=FG, padding=5)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", FG)])
        s.configure("Horizontal.TScale", background=BG, troughcolor=PANEL2)
        s.configure("TScrollbar", background=PANEL2, troughcolor=BG, arrowcolor=FG)
        self.root.option_add("*TCombobox*Listbox.background", PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    # ------------------------------------------------------------ layout
    def build(self):
        top = ttk.Frame(self.root, padding=(18, 14, 18, 6))
        top.pack(fill="x")
        ttk.Label(top, text="\u265E ChessHelper", style="Title.TLabel").pack(side="left")
        self.status = tk.Label(top, text="\u25CF Idle", bg=BG, fg=MUTED, font=("Segoe UI", 11, "bold"))
        self.status.pack(side="right")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="x", padx=14, pady=(4, 8))
        self.play_tab = ttk.Frame(nb, padding=18)
        self.settings_tab = ttk.Frame(nb)
        self.tools_tab = ttk.Frame(nb, padding=18)
        nb.add(self.play_tab, text="  Play  ")
        nb.add(self.settings_tab, text="  Settings  ")
        nb.add(self.tools_tab, text="  Tools  ")
        self.build_play()
        self.build_settings()
        self.build_tools()

        logbox = ttk.Frame(self.root, padding=(14, 0, 14, 12))
        logbox.pack(fill="both", expand=True)
        ttk.Label(logbox, text="Log", style="Head.TLabel").pack(anchor="w", pady=(0, 4))
        wrap = ttk.Frame(logbox)
        wrap.pack(fill="both", expand=True)
        self.text = tk.Text(wrap, height=10, bg="#0e1015", fg="#cfd3dd", insertbackground=FG,
                            relief="flat", font=("Consolas", 9), wrap="word", padx=10, pady=8,
                            state="disabled")
        sb = ttk.Scrollbar(wrap, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def build_play(self):
        f = self.play_tab
        ttk.Label(f, text="Game", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        self.style_var = tk.StringVar(value=main.CFG["game_style"])
        ttk.Combobox(f, textvariable=self.style_var, values=main.STYLE_CHOICES,
                     state="readonly", width=16).grid(row=0, column=1, sticky="w", padx=12)
        ttk.Label(f, text="chesscom = Chess.com, rochess = RoChess (Roblox)",
                  style="Muted.TLabel").grid(row=0, column=2, sticky="w")

        ttk.Label(f, text="Mode", style="Head.TLabel").grid(row=1, column=0, sticky="nw", pady=(16, 0))
        self.mode = tk.StringVar(value="play")
        mf = ttk.Frame(f)
        mf.grid(row=1, column=1, columnspan=2, sticky="w", padx=12, pady=(14, 0))
        for key, name, desc in MODES:
            ttk.Radiobutton(mf, text=f"{name}  \u2014  {desc}", value=key,
                            variable=self.mode).pack(anchor="w")

        ttk.Label(f, text="Strength", style="Head.TLabel").grid(row=2, column=0, sticky="nw", pady=(16, 0))
        sf = ttk.Frame(f)
        sf.grid(row=2, column=1, columnspan=2, sticky="w", padx=12, pady=(14, 0))
        self.limit_var = tk.BooleanVar(value=main.CFG["limit_strength"])
        ttk.Checkbutton(sf, text="Limit engine strength (off = always full strength)",
                        variable=self.limit_var).pack(anchor="w")
        row = ttk.Frame(sf)
        row.pack(anchor="w", pady=(6, 0))
        self.elo_var = tk.DoubleVar(value=main.CFG["elo"])
        ttk.Scale(row, from_=1320, to=3190, variable=self.elo_var, length=300,
                  command=self.elo_changed).pack(side="left")
        self.elo_label = ttk.Label(row, text=f"{main.CFG['elo']} Elo", width=10)
        self.elo_label.pack(side="left", padx=10)

        bf = ttk.Frame(f)
        bf.grid(row=3, column=0, columnspan=3, sticky="w", pady=(22, 0))
        self.start_btn = ttk.Button(bf, text="\u25B6  Start", style="Start.TButton",
                                    command=self.on_start, width=14)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(bf, text="\u25A0  Stop", style="Stop.TButton",
                                   command=self.on_stop, width=14, state="disabled")
        self.stop_btn.pack(side="left", padx=12)

        self.min_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Minimize this window while running (so it can't cover the board)",
                        variable=self.min_var).grid(row=4, column=0, columnspan=3, sticky="w", pady=(14, 0))
        self.hint = ttk.Label(f, text="", style="Muted.TLabel")
        self.hint.grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.update_hint()

    def build_settings(self):
        sf = ScrollFrame(self.settings_tab)
        sf.pack(fill="both", expand=True)
        self.setting_vars = {}
        self.setting_boxes = {}
        for key, label, typ, lo, hi, help_ in main.SETTINGS:
            if key in HIDDEN_IN_SETTINGS:
                continue
            row = ttk.Frame(sf.inner)
            row.pack(fill="x", padx=16, pady=7)
            ttk.Label(row, text=label, style="Head.TLabel").pack(anchor="w")
            extra = f"  (range {lo} to {hi})" if typ in (int, float) else ""
            ttk.Label(row, text=help_ + extra, style="Muted.TLabel", wraplength=640,
                      justify="left").pack(anchor="w", pady=(0, 3))
            if typ is bool:
                var = tk.BooleanVar(value=main.CFG[key])
                ttk.Checkbutton(row, text="On", variable=var).pack(anchor="w")
            elif typ is str and isinstance(lo, list):
                var = tk.StringVar(value=main.CFG[key])
                ttk.Combobox(row, textvariable=var, values=lo, state="readonly",
                             width=18).pack(anchor="w")
            else:
                var = tk.StringVar(value=str(main.CFG[key]))
                ttk.Entry(row, textvariable=var, width=26).pack(anchor="w")
            self.setting_vars[key] = var
        bar = ttk.Frame(sf.inner)
        bar.pack(fill="x", padx=16, pady=16)
        ttk.Button(bar, text="Save settings", command=self.save_settings).pack(side="left")
        ttk.Button(bar, text="Reset all to defaults", command=self.reset_settings).pack(side="left", padx=10)

    def build_tools(self):
        f = self.tools_tab
        tools = [
            ("Save piece templates", "Cut piece images from the board. Needs the starting position, White at the bottom.",
             self.tool_templates),
            ("Debug view", "Shows what the program sees on screen, with match scores. Saves debug_board.png.",
             lambda: self.start_job("Debug view", vision.debug)),
            ("Cursor check", "Moves the cursor to a1, h1 and h8 without clicking, to check the click positions.",
             lambda: self.start_job("Cursor check", main.cursor_check)),
            ("Next button check", "Finds the blue Next button in puzzles and moves the cursor there.",
             lambda: self.start_job("Next button check", main.next_check)),
            ("Open program folder", "Opens the folder with the templates, config.json and debug image.",
             self.open_folder),
        ]
        for i, (name, desc, cmd) in enumerate(tools):
            ttk.Button(f, text=name, command=cmd, width=24).grid(row=i, column=0, sticky="w", pady=6)
            ttk.Label(f, text=desc, style="Muted.TLabel", wraplength=480,
                      justify="left").grid(row=i, column=1, sticky="w", padx=14)

    # ------------------------------------------------------------ small helpers
    def log(self, s):
        self.q.put(s + "\n")

    def elo_changed(self, _=None):
        self.elo_label.configure(text=f"{int(round(self.elo_var.get()))} Elo")

    def update_hint(self):
        k = main.CFG.get("stop_key", "o")
        self.hint.configure(text=f"Stop hotkey: hold '{k}' for about half a second. "
                                 f"Slamming the mouse into a screen corner also stops it.")

    def apply_play_controls(self):
        main.CFG["game_style"] = self.style_var.get()
        main.CFG["limit_strength"] = bool(self.limit_var.get())
        main.CFG["elo"] = int(round(self.elo_var.get()))
        main.save_config()
        main.apply_cfg()

    def save_settings(self):
        errors = []
        for key, var in self.setting_vars.items():
            try:
                value = main.coerce(key, var.get())
                main.CFG[key] = value
                if not isinstance(value, bool):
                    var.set(str(value))
            except Exception as e:
                errors.append(f"{main.SPEC[key][1]}: {e}")
        main.save_config()
        main.apply_cfg()
        self.update_hint()
        if errors:
            messagebox.showwarning("Some values were not saved", "\n".join(errors))
        else:
            self.log("Settings saved.")

    def reset_settings(self):
        if not messagebox.askyesno("Reset", "Reset every setting to its default?"):
            return
        main.CFG.update(main.DEFAULTS)
        main.save_config()
        main.apply_cfg()
        for key, var in self.setting_vars.items():
            v = main.CFG[key]
            var.set(v if isinstance(v, bool) else str(v))
        self.style_var.set(main.CFG["game_style"])
        self.limit_var.set(main.CFG["limit_strength"])
        self.elo_var.set(main.CFG["elo"])
        self.elo_changed()
        self.update_hint()
        self.log("Settings reset to defaults.")

    def open_folder(self):
        try:
            os.startfile(vision.BASE_DIR)
        except Exception as e:
            self.log(f"Could not open the folder: {e}")

    def tool_templates(self):
        if messagebox.askokcancel(
                "Save piece templates",
                "The board must be in the STARTING position with White at the bottom, "
                "and no move made yet.\n\nThis window will minimize, then the templates are cut "
                "for the game selected on the Play tab.\n\n"
                "Existing template files are not overwritten: delete the templates folder first "
                "to redo them."):
            self.start_job("Save piece templates", vision.save_templates)

    # ------------------------------------------------------------ running
    def on_start(self):
        mode = self.mode.get()
        jobs = {
            "play":   ("Playing",        main.run, (False,)),
            "puzzle": ("Single puzzle",  main.run, (False, True)),
            "auto":   ("Auto puzzles",   main.auto_puzzles, ()),
            "dry":    ("Dry run",        main.run, (True,)),
        }
        label, fn, args = jobs[mode]
        self.start_job(label, fn, args, delay=2.0 if mode == "auto" else 3.0)

    def start_job(self, label, fn, args=(), delay=2.0):
        if self.running:
            self.log("Already running. Press Stop first.")
            return
        self.apply_play_controls()
        stop_event.clear()
        self.running = True
        self.status.configure(text=f"\u25CF {label}", fg=GREEN)
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.log(f"--- {label} ---")
        if self.min_var.get():
            self.root.iconify()
            self.minimized = True
        threading.Thread(target=self.worker, args=(fn, args, delay), daemon=True).start()

    def worker(self, fn, args, delay):
        try:
            if delay > 0 and self.minimized:
                print(f"Starting in {delay:.0f} seconds. Click into the game window now...")
                end = time.time() + delay
                while time.time() < end:
                    if stop_event.is_set():
                        print("Stopped before starting.")
                        return
                    time.sleep(0.05)
            main.safe(fn, *args)
        except Exception:
            traceback.print_exc()
        finally:
            self.q.put(DONE)

    def on_stop(self):
        stop_event.set()
        self.status.configure(text="\u25CF Stopping...", fg=AMBER)
        self.log("Stopping...")

    def finished(self):
        self.running = False
        self.status.configure(text="\u25CF Idle", fg=MUTED)
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if self.minimized:
            self.minimized = False
            self.root.deiconify()
            self.root.lift()
        self.log("--- finished ---")

    def poll(self):
        got = []
        done = False
        try:
            while True:
                item = self.q.get_nowait()
                if item == DONE:
                    done = True
                else:
                    got.append(item)
        except queue.Empty:
            pass
        if got:
            self.text.configure(state="normal")
            self.text.insert("end", "".join(got))
            lines = int(self.text.index("end-1c").split(".")[0])
            if lines > 1500:
                self.text.delete("1.0", f"{lines - 1200}.0")
            self.text.see("end")
            self.text.configure(state="disabled")
        if done:
            self.finished()
        self.root.after(80, self.poll)

    def on_close(self):
        stop_event.set()
        self.root.destroy()

def run_app():
    try:
        main.load_config()
        root = tk.Tk()
        App(root)
        root.mainloop()
    except Exception:
        fatal("ChessHelper crashed:\n\n" + traceback.format_exc())

if __name__ == "__main__":
    run_app()