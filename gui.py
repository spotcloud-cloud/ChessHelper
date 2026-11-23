import sys, os, re, math, queue, threading, time, ctypes, traceback, base64, webbrowser

def fatal(text):
    try:
        ctypes.windll.user32.MessageBoxW(0, text[-1800:], "ChessHelper", 0x10)
    except Exception:
        pass

try:
    import main          # sets DPI awareness, must come before the window exists
    import vision
    import version
    import updater
    import logo
    import cv2
    import tkinter as tk
    from tkinter import ttk, messagebox
    import tkinter.font as tkfont
except Exception:
    fatal("ChessHelper could not start:\n\n" + traceback.format_exc())
    sys.exit(1)

ANIMATIONS = True        # set to False to turn every animation off

# ---------------------------------------------------------------- look

BG, SIDEBAR, PANEL, PANEL2 = "#0f1117", "#0b0d12", "#171a22", "#1f2330"
BORDER, BORDER_H = "#2a2f3d", "#3a4156"
FG, MUTED, DIM = "#e8eaf0", "#8a90a2", "#555b6e"
ACCENT, ACCENT_H, ACCENT_L = "#5b8cff", "#4a78e6", "#8fb0ff"
GREEN, RED, AMBER = "#38d39f", "#ff5d6c", "#f5b942"

SCALE = 1.0

def px(n):
    return max(1, int(round(n * SCALE)))

def F(size, bold=False):
    return ("Segoe UI Semibold" if bold else "Segoe UI", -px(size))

def _rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * t)) for x, y in zip(ra, rb))

def ease_out(t):
    return 1 - (1 - t) ** 3

def ease_back(t):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

class Anim:
    """Tiny tween engine. Starting an animation with the same key cancels the old one."""
    root = None
    jobs = {}

    @classmethod
    def cancel(cls, key):
        j = cls.jobs.pop(key, None)
        if j is not None:
            try:
                cls.root.after_cancel(j)
            except Exception:
                pass

    @classmethod
    def run(cls, key, duration, step, done=None, ease=ease_out):
        cls.cancel(key)
        if not ANIMATIONS or cls.root is None:
            try:
                step(1.0)
            except tk.TclError:
                pass
            if done:
                done()
            return
        start = time.perf_counter()

        def tick():
            t = (time.perf_counter() - start) / duration
            try:
                if t >= 1:
                    cls.jobs.pop(key, None)
                    step(1.0)
                    if done:
                        done()
                    return
                step(ease(t))
            except tk.TclError:
                cls.jobs.pop(key, None)
                return
            cls.jobs[key] = cls.root.after(15, tick)
        tick()

def border_to(frame, target, dur=0.18, done=None):
    start = frame.bcolor

    def step(t):
        frame.bcolor = mix(start, target, t)
        frame.configure(highlightbackground=frame.bcolor)
    Anim.run((frame, "border"), dur, step, done=done)

MODES = [
    ("play",   "\u25B6", "Play a game",   "plays your side in a bot game"),
    ("puzzle", "\u265F", "Single puzzle", "solves one puzzle, then stops"),
    ("auto",   "\u221E", "Auto puzzles",  "solves, presses Next, repeats"),
    ("dry",    "\u25CE", "Dry run",       "prints moves, never clicks"),
]

GROUPS = [
    ("Game & engine", ["game_style", "limit_strength", "elo", "think_time", "obvious_gap", "mate_within"]),
    ("Mouse & timing", ["use_drag", "click_hold", "click_gap", "move_speed", "after_move_delay", "next_delay"]),
    ("Behavior", ["orientation", "stop_key", "max_retries", "stop_when_game_over", "stockfish_path"]),
]
CHOICE_LABELS = {"chesscom": "Chess.com", "rochess": "RoChess"}

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

# ---------------------------------------------------------------- custom widgets

def rrect(c, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **kw)

class Button(tk.Canvas):
    KINDS = {"normal": (PANEL2, "#2d3347", FG),
             "primary": (ACCENT, "#7aa2ff", "#ffffff"),
             "danger": (RED, "#ff7a87", "#ffffff")}

    def __init__(self, parent, text, command, width=150, height=42, kind="normal", size=14):
        self.cw, self.ch = px(width), px(height)
        super().__init__(parent, width=self.cw, height=self.ch, bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, cursor="hand2")
        self.label_text, self.on_click, self.kind, self.fsize = text, command, kind, size
        self.hv = 0.0
        self.down = False
        self.enabled = True
        self.bind("<Enter>", lambda e: self._hover(1.0))
        self.bind("<Leave>", lambda e: self._leave())
        self.bind("<ButtonPress-1>", lambda e: self._press(True))
        self.bind("<ButtonRelease-1>", self._release)
        self.draw()

    def _hover(self, target):
        if not self.enabled:
            target = 0.0
        v0 = self.hv

        def step(t):
            self.hv = v0 + (target - v0) * t
            self.draw()
        Anim.run((self, "hv"), 0.14, step)

    def _leave(self):
        self.down = False
        self._hover(0.0)

    def _press(self, v):
        self.down = v
        self.draw()

    def _release(self, e):
        was_down = self.down
        self._press(False)
        if was_down and self.enabled and 0 <= e.x < self.cw and 0 <= e.y < self.ch:
            self.on_click()

    def set_enabled(self, on):
        self.enabled = on
        self.hv = 0.0
        self.configure(cursor="hand2" if on else "arrow")
        self.draw()

    def set_text(self, text):
        self.label_text = text
        self.draw()

    def draw(self):
        self.delete("all")
        base, hov, fg = self.KINDS[self.kind]
        if not self.enabled:
            fill, fg = "#1a1d26", DIM
        else:
            fill = mix(base, hov, self.hv)
            if self.down:
                fill = mix(fill, "#000000", 0.18)
        inset = px(2) if (self.down and self.enabled) else 0
        rrect(self, 1 + inset, 1 + inset, self.cw - 1 - inset, self.ch - 1 - inset, px(11),
              fill=fill, outline="")
        self.create_text(self.cw / 2, self.ch / 2, text=self.label_text, fill=fg, font=F(self.fsize, True))

class Toggle(tk.Canvas):
    def __init__(self, parent, variable):
        self.cw, self.ch = px(52), px(28)
        super().__init__(parent, width=self.cw, height=self.ch, bg=parent.cget("bg"),
                         highlightthickness=0, cursor="hand2")
        self.var = variable
        self.pos = 1.0 if variable.get() else 0.0
        self.bind("<Button-1>", lambda e: self.var.set(not self.var.get()))
        variable.trace_add("write", lambda *a: self._changed())
        self.draw()

    def _changed(self):
        v0 = self.pos
        tg = 1.0 if self.var.get() else 0.0

        def step(t):
            self.pos = v0 + (tg - v0) * t
            self.draw()
        Anim.run((self, "pos"), 0.26, step, ease=ease_back)

    def draw(self):
        self.delete("all")
        p = self.pos
        rrect(self, 1, 1, self.cw - 1, self.ch - 1, px(13), fill=mix("#2b3040", ACCENT, p), outline="")
        r = px(10)
        x0, x1 = px(15), self.cw - px(15)
        cx = x0 + (x1 - x0) * p
        self.create_oval(cx - r, self.ch / 2 - r, cx + r, self.ch / 2 + r, fill="#ffffff", outline="")

class Segmented(tk.Canvas):
    def __init__(self, parent, variable, options, seg_w=110, height=40):
        self.opts = options
        self.pad = px(3)
        self.seg = px(seg_w)
        self.cw = self.pad * 2 + self.seg * len(options)
        self.ch = px(height)
        super().__init__(parent, width=self.cw, height=self.ch, bg=parent.cget("bg"),
                         highlightthickness=0, cursor="hand2")
        self.var = variable
        self.pos = float(self._index())
        self.bind("<Button-1>", self.click)
        variable.trace_add("write", lambda *a: self._changed())
        self.draw()

    def _index(self):
        cur = self.var.get()
        for i, (val, _) in enumerate(self.opts):
            if val == cur:
                return i
        return 0

    def click(self, e):
        i = int((e.x - self.pad) // self.seg)
        i = max(0, min(len(self.opts) - 1, i))
        self.var.set(self.opts[i][0])

    def _changed(self):
        v0, tg = self.pos, float(self._index())

        def step(t):
            self.pos = v0 + (tg - v0) * t
            self.draw()
        Anim.run((self, "pos"), 0.26, step)

    def draw(self):
        self.delete("all")
        rrect(self, 1, 1, self.cw - 1, self.ch - 1, px(13), fill=PANEL2, outline=BORDER)
        x0 = self.pad + self.pos * self.seg
        rrect(self, x0, self.pad, x0 + self.seg, self.ch - self.pad, px(10), fill=ACCENT, outline="")
        for i, (val, label) in enumerate(self.opts):
            near = max(0.0, 1 - abs(i - self.pos))
            cx = self.pad + i * self.seg + self.seg / 2
            self.create_text(cx, self.ch / 2, text=label, fill=mix(MUTED, "#ffffff", near), font=F(14, True))

class Slider(tk.Canvas):
    def __init__(self, parent, variable, lo, hi, width=300, step=10, bubble=False):
        self.cw = px(width)
        self.bubble = bubble
        self.ch = px(60 if bubble else 34)
        super().__init__(parent, width=self.cw, height=self.ch, bg=parent.cget("bg"),
                         highlightthickness=0, cursor="hand2")
        self.var, self.lo, self.hi, self.step = variable, lo, hi, step
        self.pad = px(14)
        self.drag = self.hover = False
        self.grow = 0.0
        self.shown = self._val()
        self.bind("<Button-1>", self.press)
        self.bind("<B1-Motion>", self.pick)
        self.bind("<ButtonRelease-1>", self.release)
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        variable.trace_add("write", lambda *a: self._changed())
        self.draw()

    def _val(self):
        try:
            return float(self.var.get())
        except Exception:
            return float(self.lo)

    def _grow_to(self):
        tg = 1.0 if self.drag else (0.5 if self.hover else 0.0)
        v0 = self.grow

        def step(t):
            self.grow = v0 + (tg - v0) * t
            self.draw()
        Anim.run((self, "grow"), 0.15, step)

    def _hover(self, v):
        self.hover = v
        self._grow_to()

    def press(self, e):
        self.drag = True
        self._grow_to()
        self.pick(e)

    def release(self, e):
        self.drag = False
        self._grow_to()

    def pick(self, e):
        t = (e.x - self.pad) / max(1, self.cw - 2 * self.pad)
        t = min(1.0, max(0.0, t))
        v = int(round((self.lo + t * (self.hi - self.lo)) / self.step) * self.step)
        self.var.set(max(self.lo, min(self.hi, v)))

    def _changed(self):
        v = self._val()
        if self.drag:
            self.shown = v
            self.draw()
            return
        v0 = self.shown

        def step(t):
            self.shown = v0 + (v - v0) * t
            self.draw()
        Anim.run((self, "shown"), 0.24, step)

    def draw(self):
        self.delete("all")
        t = min(1.0, max(0.0, (self.shown - self.lo) / (self.hi - self.lo)))
        y = self.ch - px(17) if self.bubble else self.ch // 2
        th = px(6)
        x0, x1 = self.pad, self.cw - self.pad
        xk = x0 + t * (x1 - x0)
        rrect(self, x0, y - th // 2, x1, y + th // 2, th // 2, fill="#2b3040", outline="")
        if xk > x0 + th:
            rrect(self, x0, y - th // 2, xk, y + th // 2, th // 2, fill=ACCENT, outline="")
        r = px(9) + px(3) * self.grow
        if self.grow > 0.02:
            g = r + px(6) * self.grow
            self.create_oval(xk - g, y - g, xk + g, y + g,
                             fill=mix(self.cget("bg"), ACCENT, 0.28 * self.grow), outline="")
        self.create_oval(xk - r, y - r, xk + r, y + r, fill="#ffffff", outline=ACCENT, width=px(3))
        if self.bubble and self.grow > 0.05:
            w, h = px(56), px(24)
            top = y - r - px(8) - h
            rrect(self, xk - w / 2, top, xk + w / 2, top + h, px(8), fill=ACCENT, outline="")
            self.create_text(xk, top + h / 2, text=str(int(round(self.shown))), fill="#ffffff", font=F(13, True))

class Chip(tk.Canvas):
    def __init__(self, parent, var, value, label, width=68, height=34):
        self.cw, self.ch = px(width), px(height)
        super().__init__(parent, width=self.cw, height=self.ch, bg=parent.cget("bg"),
                         highlightthickness=0, cursor="hand2")
        self.var, self.value, self.label = var, value, label
        self.sel = 1.0 if self._is_sel() else 0.0
        self.hov = 0.0
        self.bind("<Button-1>", lambda e: self.var.set(self.value))
        self.bind("<Enter>", lambda e: self._tween("hov", 1.0))
        self.bind("<Leave>", lambda e: self._tween("hov", 0.0))
        var.trace_add("write", lambda *a: self._tween("sel", 1.0 if self._is_sel() else 0.0))
        self.draw()

    def _is_sel(self):
        try:
            return int(self.var.get()) == self.value
        except Exception:
            return False

    def _tween(self, attr, tg):
        v0 = getattr(self, attr)

        def step(t):
            setattr(self, attr, v0 + (tg - v0) * t)
            self.draw()
        Anim.run((self, attr), 0.18, step)

    def draw(self):
        self.delete("all")
        fill = mix(mix(PANEL2, "#2d3347", self.hov), ACCENT, self.sel)
        fg = mix(MUTED, "#ffffff", max(self.sel, self.hov * 0.7))
        rrect(self, 1, 1, self.cw - 1, self.ch - 1, px(12), fill=fill, outline="")
        self.create_text(self.cw / 2, self.ch / 2, text=self.label, fill=fg, font=F(13, True))

class Field(tk.Frame):
    """Text entry with a rounded-looking border that glows when focused."""
    def __init__(self, parent, var, width=18):
        super().__init__(parent, bg=PANEL2, highlightthickness=2, highlightbackground=BORDER,
                         highlightcolor=BORDER)
        self.bcolor = BORDER
        self.entry = tk.Entry(self, textvariable=var, width=width, bg=PANEL2, fg=FG,
                              insertbackground=FG, relief="flat", bd=0, highlightthickness=0, font=F(14))
        self.entry.pack(padx=px(10), pady=px(7))
        self.entry.bind("<FocusIn>", lambda e: border_to(self, ACCENT))
        self.entry.bind("<FocusOut>", lambda e: border_to(self, BORDER))

class EloInput(tk.Frame):
    """Big typeable Elo field with - / + buttons. Typing, the slider and the chips stay in sync."""
    def __init__(self, parent, var, lo, hi, step=50, big=True, on_error=None):
        super().__init__(parent, bg=parent.cget("bg"))
        self.var, self.lo, self.hi, self.step, self.on_error = var, lo, hi, step, on_error
        self.text = tk.StringVar(value=str(self._cur()))
        self.focused = False
        bs = 46 if big else 36
        Button(self, "\u2212", lambda: self.nudge(-self.step), width=bs, height=bs,
               size=22 if big else 18).pack(side="left")
        self.box = tk.Frame(self, bg=PANEL2, highlightthickness=2, highlightbackground=BORDER,
                            highlightcolor=BORDER)
        self.bcolor = BORDER
        self.box.pack(side="left", padx=px(8))
        inner = tk.Frame(self.box, bg=PANEL2)
        inner.pack(padx=px(14 if big else 10), pady=px(4 if big else 2))
        self.entry = tk.Entry(inner, textvariable=self.text, width=5, justify="center", bg=PANEL2, fg=FG,
                              insertbackground=FG, relief="flat", bd=0, highlightthickness=0,
                              font=F(28 if big else 17, True), validate="key",
                              validatecommand=(self.register(self._valid), "%P"))
        self.entry.pack(side="left")
        tk.Label(inner, text="ELO", bg=PANEL2, fg=MUTED, font=F(12, True)).pack(
            side="left", padx=(px(6), 0), pady=(px(9) if big else px(3), 0))
        Button(self, "+", lambda: self.nudge(self.step), width=bs, height=bs,
               size=22 if big else 18).pack(side="left")

        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", lambda e: self._focus_out())
        self.entry.bind("<Return>", lambda e: self._enter())
        self.entry.bind("<Up>", lambda e: self.nudge(self.step))
        self.entry.bind("<Down>", lambda e: self.nudge(-self.step))
        if big:
            self.entry.bind("<MouseWheel>", lambda e: self.nudge(self.step if e.delta > 0 else -self.step))
        self.text.trace_add("write", lambda *a: self._typed())
        self.var.trace_add("write", lambda *a: self._external())

    def _cur(self):
        try:
            return int(self.var.get())
        except Exception:
            return self.lo

    @staticmethod
    def _valid(p):
        return p == "" or (p.isdigit() and len(p) <= 4)

    def _typed(self):
        t = self.text.get()
        if t.isdigit():
            n = int(t)
            if self.lo <= n <= self.hi and n != self._cur():
                self.var.set(n)

    def _external(self):
        s = str(self._cur())
        if self.text.get() != s:
            self.text.set(s)

    def nudge(self, d):
        self.var.set(max(self.lo, min(self.hi, self._cur() + d)))

    def _focus_in(self, e):
        self.focused = True
        border_to(self, ACCENT)

    def _focus_out(self):
        self.focused = False
        self.commit()
        border_to(self, BORDER)

    def _enter(self):
        self.commit()
        self.winfo_toplevel().focus_set()

    def commit(self):
        t = self.text.get().strip()
        try:
            n = int(t)
        except ValueError:
            self.text.set(str(self._cur()))
            return
        clamped = max(self.lo, min(self.hi, n))
        if clamped != n:
            self.flash_error()
            if self.on_error:
                self.on_error(f"Elo must be between {self.lo} and {self.hi}")
        self.var.set(clamped)
        self.text.set(str(clamped))

    def flash_error(self):
        back = ACCENT if self.focused else BORDER
        border_to(self, RED, 0.1, done=lambda: border_to(self, back, 0.5))

class ModeCard(tk.Canvas):
    def __init__(self, parent, var, key, icon, title, desc, width=306, height=86):
        self.cw, self.ch = px(width), px(height)
        super().__init__(parent, width=self.cw, height=self.ch, bg=parent.cget("bg"),
                         highlightthickness=0, cursor="hand2")
        self.var, self.key, self.icon, self.title, self.desc = var, key, icon, title, desc
        self.sel = 1.0 if var.get() == key else 0.0
        self.hov = 0.0
        self.bind("<Button-1>", lambda e: self.var.set(self.key))
        self.bind("<Enter>", lambda e: self._tween("hov", 1.0))
        self.bind("<Leave>", lambda e: self._tween("hov", 0.0))
        var.trace_add("write", lambda *a: self._tween("sel", 1.0 if self.var.get() == self.key else 0.0))
        self.draw()

    def _tween(self, attr, tg):
        v0 = getattr(self, attr)

        def step(t):
            setattr(self, attr, v0 + (tg - v0) * t)
            self.draw()
        Anim.run((self, attr), 0.2, step)

    def draw(self):
        self.delete("all")
        fill = mix(mix(PANEL, "#1b2030", self.hov), "#1c2744", self.sel)
        outline = mix(mix(BORDER, BORDER_H, self.hov), ACCENT, self.sel)
        rrect(self, 2, 2, self.cw - 2, self.ch - 2, px(14), fill=fill, outline=outline,
              width=2 if self.sel > 0.5 else 1)
        self.create_text(px(32), self.ch / 2, text=self.icon, fill=mix(MUTED, ACCENT_L, self.sel), font=F(26))
        self.create_text(px(66), self.ch / 2 - px(12), text=self.title, anchor="w", fill=FG, font=F(16, True))
        self.create_text(px(66), self.ch / 2 + px(14), text=self.desc, anchor="w", fill=MUTED, font=F(12))

class NavItem(tk.Frame):
    def __init__(self, parent, icon, text, command):
        super().__init__(parent, bg=SIDEBAR, cursor="hand2")
        self.command = command
        self.hv = self.act = 0.0
        self.intro = 0.0
        self.bar = tk.Frame(self, width=px(4), bg=SIDEBAR)
        self.bar.pack(side="left", fill="y")
        self.lbl = tk.Label(self, text=f"{icon}    {text}", bg=SIDEBAR, fg=SIDEBAR, font=F(15, True),
                            anchor="w", padx=px(18), pady=px(12))
        self.lbl.pack(side="left", fill="x", expand=True)
        for w in (self, self.lbl):
            w.bind("<Button-1>", lambda e: self.command())
            w.bind("<Enter>", lambda e: self._tween("hv", 1.0))
            w.bind("<Leave>", lambda e: self._tween("hv", 0.0))
        self.paint()

    def _tween(self, attr, tg, dur=0.16):
        v0 = getattr(self, attr)

        def step(t):
            setattr(self, attr, v0 + (tg - v0) * t)
            self.paint()
        Anim.run((self, attr), dur, step)

    def paint(self):
        k = max(self.hv, self.act)
        bg = mix(SIDEBAR, PANEL, k)
        fg = mix(SIDEBAR, mix(MUTED, FG, k), self.intro)
        self.configure(bg=bg)
        self.lbl.configure(bg=bg, fg=fg)
        self.bar.configure(bg=mix(bg, ACCENT, self.act))

    def set_active(self, a):
        self._tween("act", 1.0 if a else 0.0, 0.22)

    def fade_in(self):
        def step(t):
            self.intro = t
            self.paint()
        Anim.run((self, "intro"), 0.45, step)

class ScrollFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self.wheel, add="+")

    def wheel(self, e):
        if self.winfo_ismapped():
            self.canvas.yview_scroll(int(-e.delta / 120), "units")

# ---------------------------------------------------------------- the app

class App:
    def __init__(self, root):
        self.root = root
        Anim.root = root
        self.q = queue.Queue()
        self.buf = ""
        self.running = False
        self.minimized = False
        self.solved = 0
        self.images = []
        self.current = None
        self.toast_w = None
        self.phase = 0.0
        self.pill_color = MUTED
        sys.stdout = QueueWriter(self.q)
        sys.stderr = QueueWriter(self.q)

        root.title(f"ChessHelper v{version.VERSION}")
        root.geometry(f"{px(1260)}x{px(820)}")
        root.minsize(px(1200), px(760))
        root.configure(bg=BG)
        self.make_style()
        self.make_vars()
        self.load_logos()
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
        self.pulse()
        self.bob()
        for i, nav in enumerate(self.navs.values()):
            root.after(150 + i * 80, nav.fade_in)
        root.after(1500, lambda: updater.check_async(root, self.log))

    # ------------------------------------------------------------ setup
    def make_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=BG, bordercolor=BG,
                    arrowcolor=MUTED, lightcolor=PANEL2, darkcolor=PANEL2)
        s.map("Vertical.TScrollbar", background=[("active", BORDER_H)])

    def make_vars(self):
        self.vars = {}
        for key, label, typ, lo, hi, help_ in main.SETTINGS:
            v = main.CFG[key]
            if typ is bool:
                var = tk.BooleanVar(value=bool(v))
            elif key == "elo":
                var = tk.IntVar(value=int(v))
            else:
                var = tk.StringVar(value=str(v))
            self.vars[key] = var
        self.mode = tk.StringVar(value="play")
        self.min_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Idle")
        self.last_move = tk.StringVar(value="-")
        self.solved_var = tk.StringVar(value="0")

    def load_logos(self):
        self.logo_small = self.logo_big = None
        try:
            def img(size):
                ok, buf = cv2.imencode(".png", logo.render(size))
                im = tk.PhotoImage(data=base64.b64encode(buf.tobytes()))
                self.images.append(im)
                return im
            self.logo_small = img(44)
            self.logo_big = img(128)
            self.root.iconphoto(True, img(64))
        except Exception:
            pass

    # ------------------------------------------------------------ layout helpers
    def card(self, parent):
        return tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)

    def section(self, parent, text):
        tk.Label(parent, text=text, bg=BG, fg=MUTED, font=F(12, True)).pack(
            anchor="w", pady=(px(18), px(8)))

    def page_title(self, parent, title, sub):
        tk.Label(parent, text=title, bg=BG, fg=FG, font=F(30, True)).pack(anchor="w")
        tk.Label(parent, text=sub, bg=BG, fg=MUTED, font=F(14)).pack(anchor="w", pady=(px(2), 0))

    def build(self):
        self.sidebar = tk.Frame(self.root, bg=SIDEBAR, width=px(230))
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.main_area = tk.Frame(self.root, bg=BG)
        self.main_area.pack(side="left", fill="both", expand=True)

        head = tk.Frame(self.sidebar, bg=SIDEBAR)
        head.pack(fill="x", padx=px(20), pady=(px(26), px(22)))
        if self.logo_small:
            tk.Label(head, image=self.logo_small, bg=SIDEBAR).pack(side="left")
        names = tk.Frame(head, bg=SIDEBAR)
        names.pack(side="left", padx=(px(12), 0))
        tk.Label(names, text="ChessHelper", bg=SIDEBAR, fg=FG, font=F(17, True)).pack(anchor="w")
        tk.Label(names, text=f"v{version.VERSION}", bg=SIDEBAR, fg=MUTED, font=F(12)).pack(anchor="w")

        self.pages, self.navs = {}, {}
        for key, icon, text in (("play", "\u25B6", "Play"), ("settings", "\u2699", "Settings"),
                                ("tools", "\u2692", "Tools"), ("about", "\u2139", "About")):
            self.pages[key] = tk.Frame(self.main_area, bg=BG)
            nav = NavItem(self.sidebar, icon, text, lambda k=key: self.show_page(k))
            nav.pack(fill="x", pady=1)
            self.navs[key] = nav

        bottom = tk.Frame(self.sidebar, bg=SIDEBAR)
        bottom.pack(side="bottom", fill="x", padx=px(20), pady=px(20))
        pill = tk.Frame(bottom, bg=SIDEBAR)
        pill.pack(anchor="w")
        self.dot = tk.Label(pill, text="\u25CF", bg=SIDEBAR, fg=MUTED, font=F(14, True))
        self.dot.pack(side="left")
        self.pill_text = tk.Label(pill, text="Idle", bg=SIDEBAR, fg=MUTED, font=F(14, True))
        self.pill_text.pack(side="left", padx=(px(8), 0))
        self.hotkey_lbl = tk.Label(bottom, text="", bg=SIDEBAR, fg=DIM, font=F(11),
                                   justify="left", wraplength=px(190))
        self.hotkey_lbl.pack(anchor="w", pady=(px(6), 0))

        self.build_play()
        self.build_settings()
        self.build_tools()
        self.build_about()
        self.update_hint()
        self.show_page("play", animate=False)

    def show_page(self, key, animate=True):
        if key == self.current:
            return
        old, self.current = self.current, key
        for k, nav in self.navs.items():
            nav.set_active(k == key)
        if old:
            self.pages[old].place_forget()
        page = self.pages[key]
        if not animate:
            page.place(x=0, y=0, relwidth=1, relheight=1)
            return
        off = px(60)
        page.place(x=off, y=0, relwidth=1, relheight=1)

        def step(t):
            page.place_configure(x=int(off * (1 - t)))
        Anim.run(("page",), 0.3, step)

    # ------------------------------------------------------------ Play page
    def build_play(self):
        page = self.pages["play"]
        left = tk.Frame(page, bg=BG, width=px(660))
        left.pack(side="left", fill="y", padx=(px(30), px(10)), pady=px(26))
        left.pack_propagate(False)
        self.page_title(left, "Play", "Pick a game and a mode, then press Start.")

        self.section(left, "GAME")
        Segmented(left, self.vars["game_style"],
                  [("chesscom", "Chess.com"), ("rochess", "RoChess")], seg_w=150).pack(anchor="w")

        self.section(left, "MODE")
        grid = tk.Frame(left, bg=BG)
        grid.pack(anchor="w")
        for i, (key, icon, title, desc) in enumerate(MODES):
            ModeCard(grid, self.mode, key, icon, title, desc).grid(
                row=i // 2, column=i % 2, padx=(0, px(12)), pady=(0, px(12)))

        self.section(left, "ENGINE STRENGTH")
        card = self.card(left)
        card.pack(fill="x")
        r1 = tk.Frame(card, bg=PANEL)
        r1.pack(fill="x", padx=px(18), pady=(px(14), px(8)))
        t = tk.Frame(r1, bg=PANEL)
        t.pack(side="left")
        tk.Label(t, text="Limit engine strength", bg=PANEL, fg=FG, font=F(15, True)).pack(anchor="w")
        tk.Label(t, text="Off = always plays the best move", bg=PANEL, fg=MUTED, font=F(12)).pack(anchor="w")
        Toggle(r1, self.vars["limit_strength"]).pack(side="right")

        r2 = tk.Frame(card, bg=PANEL)
        r2.pack(fill="x", padx=px(18), pady=(px(4), px(8)))
        EloInput(r2, self.vars["elo"], 1320, 3190,
                 on_error=lambda m: self.toast(m, "warn")).pack(side="left")
        Slider(r2, self.vars["elo"], 1320, 3190, width=290).pack(side="left", padx=(px(18), 0))

        r3 = tk.Frame(card, bg=PANEL)
        r3.pack(fill="x", padx=px(18), pady=(px(2), px(16)))
        for value, label in ((1320, "Min"), (1800, "1800"), (2200, "2200"), (2600, "2600"), (3190, "Max")):
            Chip(r3, self.vars["elo"], value, label).pack(side="left", padx=(0, px(8)))

        bf = tk.Frame(left, bg=BG)
        bf.pack(anchor="w", pady=(px(20), 0))
        self.start_btn = Button(bf, "\u25B6   Start", self.on_start, width=190, height=50, kind="primary", size=16)
        self.start_btn.pack(side="left")
        self.stop_btn = Button(bf, "\u25A0   Stop", self.on_stop, width=150, height=50, kind="danger", size=16)
        self.stop_btn.pack(side="left", padx=(px(12), 0))
        self.stop_btn.set_enabled(False)

        mf = tk.Frame(left, bg=BG)
        mf.pack(anchor="w", pady=(px(14), 0))
        Toggle(mf, self.min_var).pack(side="left")
        tk.Label(mf, text="Minimize this window while running", bg=BG, fg=MUTED,
                 font=F(13)).pack(side="left", padx=(px(10), 0))

        right = tk.Frame(page, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(px(10), px(30)), pady=px(26))
        stats = tk.Frame(right, bg=BG)
        stats.pack(fill="x")
        self.stat_labels = {}
        for i, (title, var) in enumerate((("STATUS", self.status_var), ("LAST MOVE", self.last_move),
                                          ("PUZZLES", self.solved_var))):
            c = self.card(stats)
            c.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else px(10), 0))
            stats.columnconfigure(i, weight=1, uniform="s")
            tk.Label(c, text=title, bg=PANEL, fg=MUTED, font=F(11, True)).pack(anchor="w", padx=px(14), pady=(px(10), 0))
            lbl = tk.Label(c, textvariable=var, bg=PANEL, fg=FG, font=F(22, True))
            lbl.pack(anchor="w", padx=px(14), pady=(0, px(10)))
            self.stat_labels[title] = lbl

        logcard = self.card(right)
        logcard.pack(fill="both", expand=True, pady=(px(14), 0))
        head = tk.Frame(logcard, bg=PANEL)
        head.pack(fill="x", padx=px(14), pady=(px(10), px(4)))
        tk.Label(head, text="LIVE LOG", bg=PANEL, fg=MUTED, font=F(11, True)).pack(side="left")
        clear = tk.Label(head, text="Clear", bg=PANEL, fg=MUTED, font=F(12), cursor="hand2")
        clear.pack(side="right")
        clear.bind("<Button-1>", lambda e: self.clear_log())
        clear.bind("<Enter>", lambda e: clear.configure(fg=FG))
        clear.bind("<Leave>", lambda e: clear.configure(fg=MUTED))
        wrap = tk.Frame(logcard, bg=PANEL)
        wrap.pack(fill="both", expand=True, padx=(px(10), px(6)), pady=(0, px(10)))
        self.text = tk.Text(wrap, bg="#0c0e13", fg="#cfd3dd", relief="flat", wrap="word",
                            font=("Consolas", -px(13)), padx=px(10), pady=px(8), state="disabled",
                            insertbackground=FG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for tag, color in (("move", ACCENT_L), ("pos", DIM), ("ok", GREEN), ("warn", AMBER), ("err", RED)):
            self.text.tag_configure(tag, foreground=color)

    # ------------------------------------------------------------ Settings page
    def build_settings(self):
        page = self.pages["settings"]
        head = tk.Frame(page, bg=BG)
        head.pack(fill="x", padx=px(30), pady=(px(26), px(6)))
        tf = tk.Frame(head, bg=BG)
        tf.pack(side="left")
        self.page_title(tf, "Settings", "Changes apply when you press Save or Start.")
        Button(head, "Save changes", self.save_settings, width=160, kind="primary").pack(side="right")
        Button(head, "Reset all", self.reset_settings, width=120).pack(side="right", padx=(0, px(10)))

        sf = ScrollFrame(page)
        sf.pack(fill="both", expand=True, padx=(px(30), px(14)), pady=(0, px(16)))
        for gtitle, keys in GROUPS:
            tk.Label(sf.inner, text=gtitle.upper(), bg=BG, fg=MUTED, font=F(12, True)).pack(
                anchor="w", pady=(px(14), px(6)))
            card = self.card(sf.inner)
            card.pack(fill="x", padx=(0, px(16)))
            for i, key in enumerate(keys):
                if i:
                    tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=px(18))
                self.setting_row(card, key)

    def setting_row(self, parent, key):
        _, label, typ, lo, hi, help_ = main.SPEC[key]
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=px(20), pady=px(11))
        textf = tk.Frame(row, bg=PANEL)
        textf.pack(side="left", fill="x", expand=True)
        tk.Label(textf, text=label, bg=PANEL, fg=FG, font=F(15, True), anchor="w").pack(anchor="w")
        extra = f"  (range {lo} to {hi})" if typ in (int, float) else ""
        tk.Label(textf, text=help_ + extra, bg=PANEL, fg=MUTED, font=F(12), anchor="w",
                 justify="left", wraplength=px(440)).pack(anchor="w", pady=(px(2), 0))
        ctrl = tk.Frame(row, bg=PANEL)
        ctrl.pack(side="right", padx=(px(16), 0))
        var = self.vars[key]
        if typ is bool:
            Toggle(ctrl, var).pack()
        elif key == "elo":
            Slider(ctrl, var, 1320, 3190, width=180).pack(side="left", padx=(0, px(10)))
            EloInput(ctrl, var, 1320, 3190, big=False,
                     on_error=lambda m: self.toast(m, "warn")).pack(side="left")
        elif typ is str and isinstance(lo, list):
            Segmented(ctrl, var, [(o, CHOICE_LABELS.get(o, o.capitalize())) for o in lo],
                      seg_w=92 if len(lo) > 2 else 112, height=38).pack()
        else:
            Field(ctrl, var, width=18).pack()

    # ------------------------------------------------------------ Tools page
    def build_tools(self):
        page = self.pages["tools"]
        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=px(30), pady=px(26))
        self.page_title(wrap, "Tools", "Setup helpers and checks.")
        grid = tk.Frame(wrap, bg=BG)
        grid.pack(fill="x", pady=(px(18), 0))
        tools = [
            ("Save piece templates", "Cuts the piece images from the board. Needs the starting position with White at the bottom, no move made.",
             "Save", self.tool_templates),
            ("Debug view", "Shows what the program sees, with match scores and the check glow. Saves debug_board.png.",
             "Run", lambda: self.start_job("Debug view", vision.debug)),
            ("Cursor check", "Moves the cursor to a1, h1 and h8 without clicking, to check the click positions.",
             "Run", lambda: self.start_job("Cursor check", main.cursor_check)),
            ("Next button check", "Finds the blue Next button in puzzles and moves the cursor there.",
             "Run", lambda: self.start_job("Next button check", main.next_check)),
            ("Program folder", "Opens the folder with config.json, the templates and the debug image.",
             "Open", self.open_folder),
        ]
        for i, (name, desc, btn, cmd) in enumerate(tools):
            c = self.card(grid)
            c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, px(14)), pady=(0, px(14)))
            grid.columnconfigure(i % 2, weight=1, uniform="t")
            tk.Label(c, text=name, bg=PANEL, fg=FG, font=F(16, True)).pack(anchor="w", padx=px(18), pady=(px(14), 0))
            tk.Label(c, text=desc, bg=PANEL, fg=MUTED, font=F(12), justify="left",
                     wraplength=px(380), anchor="w").pack(anchor="w", padx=px(18), pady=(px(4), px(10)))
            Button(c, btn, cmd, width=110, height=38).pack(anchor="w", padx=px(18), pady=(0, px(16)))

    # ------------------------------------------------------------ About page
    def build_about(self):
        page = self.pages["about"]
        box = tk.Frame(page, bg=BG)
        box.pack(expand=True)
        self.about_canvas = None
        if self.logo_big:
            self.about_canvas = tk.Canvas(box, width=px(150), height=px(156), bg=BG, highlightthickness=0)
            self.about_canvas.pack(pady=(0, px(10)))
            self.about_img = self.about_canvas.create_image(px(75), px(84), image=self.logo_big)
        tk.Label(box, text="ChessHelper", bg=BG, fg=FG, font=F(34, True)).pack()
        tk.Label(box, text=f"Version {version.VERSION}", bg=BG, fg=MUTED, font=F(14)).pack(pady=(px(2), px(14)))
        tk.Label(box, text="Reads the board from your screen and plays it with Stockfish.\n"
                           "Made for bot games and puzzles.",
                 bg=BG, fg=MUTED, font=F(14), justify="center").pack()
        row = tk.Frame(box, bg=BG)
        row.pack(pady=px(22))
        Button(row, "Check for updates", self.check_updates, width=190, kind="primary").pack(side="left", padx=px(6))
        Button(row, "Releases page", self.open_releases, width=160).pack(side="left", padx=px(6))
        tk.Label(box, text="Contains Stockfish (GPL). Source: stockfishchess.org",
                 bg=BG, fg=DIM, font=F(12)).pack(pady=(px(8), 0))

    def bob(self):
        try:
            if self.about_canvas is not None and self.current == "about":
                y = px(84) + px(6) * math.sin(time.time() * 1.8)
                self.about_canvas.coords(self.about_img, px(75), y)
        except tk.TclError:
            return
        self.root.after(40, self.bob)

    # ------------------------------------------------------------ toasts
    def toast(self, text, kind="ok"):
        color = {"ok": GREEN, "warn": AMBER, "err": RED}.get(kind, ACCENT)
        if self.toast_w is not None:
            try:
                self.toast_w.destroy()
            except Exception:
                pass
        Anim.cancel((self, "toast"))
        w = tkfont.Font(font=F(14, True)).measure(text) + px(70)
        h = px(48)
        c = tk.Canvas(self.main_area, width=w, height=h, bg=BG, highlightthickness=0)
        rrect(c, 1, 1, w - 1, h - 1, px(14), fill=PANEL2, outline=BORDER_H)
        c.create_oval(px(16), h / 2 - px(5), px(26), h / 2 + px(5), fill=color, outline="")
        c.create_text(px(38), h / 2, text=text, anchor="w", fill=FG, font=F(14, True))
        self.toast_w = c
        hidden, shown = px(80), -px(28)
        c.place(relx=1.0, rely=1.0, x=-px(28), y=hidden, anchor="se")

        def slide(a, b):
            def step(t):
                if self.toast_w is c:
                    c.place_configure(y=int(a + (b - a) * t))
            return step

        def hide():
            if self.toast_w is not c:
                return

            def gone():
                if self.toast_w is c:
                    try:
                        c.destroy()
                    except Exception:
                        pass
                    self.toast_w = None
            Anim.run((self, "toast"), 0.25, slide(shown, hidden), done=gone)

        Anim.run((self, "toast"), 0.32, slide(hidden, shown),
                 done=lambda: self.root.after(2300, hide), ease=ease_back)

    # ------------------------------------------------------------ helpers
    def log(self, s):
        self.q.put(s + "\n")

    def clear_log(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def update_hint(self):
        k = main.CFG.get("stop_key", "o")
        self.hotkey_lbl.configure(text=f"Hold '{k}' for half a second to stop. A screen corner works too.")

    def set_status(self, text, color):
        self.status_var.set(text)
        self.pill_color = color
        self.dot.configure(fg=color)
        self.pill_text.configure(text=text, fg=color)
        self.stat_labels["STATUS"].configure(fg=color if color != MUTED else FG)

    def pulse(self):
        try:
            if self.running and self.pill_color != MUTED:
                self.phase += 0.14
                k = (math.sin(self.phase) + 1) / 2
                self.dot.configure(fg=mix(mix(self.pill_color, SIDEBAR, 0.7), self.pill_color, 0.25 + 0.75 * k))
        except tk.TclError:
            return
        self.root.after(60, self.pulse)

    def flash(self, widget, color, base=FG, dur=0.8):
        def step(t):
            widget.configure(fg=mix(color, base, t))
        Anim.run((widget, "flash"), dur, step)

    def collect(self, show_errors=True):
        errors = []
        for key, var in self.vars.items():
            try:
                value = main.coerce(key, var.get())
                main.CFG[key] = value
                if isinstance(var, tk.StringVar):
                    var.set(str(value))
            except Exception as e:
                errors.append(f"{main.SPEC[key][1]}: {e}")
        if errors:
            if show_errors:
                messagebox.showwarning("Some values are not valid", "\n".join(errors))
            return False
        main.save_config()
        main.apply_cfg()
        self.update_hint()
        return True

    def save_settings(self):
        if self.collect():
            self.log("Settings saved.")
            self.toast("Settings saved")

    def sync_from_cfg(self):
        for key, var in self.vars.items():
            v = main.CFG[key]
            if isinstance(var, tk.BooleanVar):
                var.set(bool(v))
            elif isinstance(var, tk.IntVar):
                var.set(int(v))
            else:
                var.set(str(v))

    def reset_settings(self):
        if not messagebox.askyesno("Reset", "Reset every setting to its default?"):
            return
        main.CFG.update(main.DEFAULTS)
        main.save_config()
        main.apply_cfg()
        self.sync_from_cfg()
        self.update_hint()
        self.log("Settings reset to defaults.")
        self.toast("Settings reset to defaults", "warn")

    def open_folder(self):
        try:
            os.startfile(vision.BASE_DIR)
        except Exception as e:
            self.log(f"Could not open the folder: {e}")

    def check_updates(self):
        self.log("Checking for updates...")
        self.toast("Checking for updates...", "info")
        updater.check_async(self.root, self.log)

    def open_releases(self):
        webbrowser.open(f"https://github.com/{version.REPO}/releases")

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
            "play":   ("Playing",       main.run, (False,)),
            "puzzle": ("Single puzzle", main.run, (False, True)),
            "auto":   ("Auto puzzles",  main.auto_puzzles, ()),
            "dry":    ("Dry run",       main.run, (True,)),
        }
        label, fn, args = jobs[mode]
        self.start_job(label, fn, args, delay=2.0 if mode == "auto" else 3.0)

    def start_job(self, label, fn, args=(), delay=2.0):
        if self.running:
            self.log("Already running. Press Stop first.")
            self.toast("Already running", "warn")
            return
        if not self.collect():
            return
        stop_event.clear()
        self.running = True
        self.solved = 0
        self.solved_var.set("0")
        self.last_move.set("-")
        self.set_status(label, GREEN)
        self.start_btn.set_enabled(False)
        self.stop_btn.set_enabled(True)
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
        self.set_status("Stopping", AMBER)
        self.log("Stopping...")

    def finished(self):
        self.running = False
        self.set_status("Idle", MUTED)
        self.start_btn.set_enabled(True)
        self.stop_btn.set_enabled(False)
        if self.minimized:
            self.minimized = False
            self.root.deiconify()
            self.root.lift()
        self.log("--- finished ---")

    # ------------------------------------------------------------ log output
    def add_line(self, line):
        s = line.strip()
        tag = ""
        if s.startswith("Move:"):
            tag = "move"
            m = re.match(r"Move:\s*(\S+)", s)
            if m:
                self.last_move.set(m.group(1))
                self.flash(self.stat_labels["LAST MOVE"], ACCENT_L)
        elif s.startswith("Position:"):
            tag = "pos"
        elif "Puzzle finished" in s:
            tag = "ok"
            self.solved += 1
            self.solved_var.set(str(self.solved))
            self.flash(self.stat_labels["PUZZLES"], GREEN)
        elif s.startswith("Skipping") or s.startswith("Nothing has happened") or s.startswith("Still can't"):
            tag = "warn"
        elif any(w in s for w in ("!!", "Error", "error", "failed", "Traceback", "[vision]", "crashed")):
            tag = "err"
        elif s.startswith("---") or s.startswith("Stopped") or s.startswith("Game over") or s.startswith("Stopping"):
            tag = "warn"
        self.text.insert("end", line + "\n", tag)

    def poll(self):
        chunks, done = [], False
        try:
            while True:
                item = self.q.get_nowait()
                if item == DONE:
                    done = True
                else:
                    chunks.append(item)
        except queue.Empty:
            pass
        if chunks:
            self.buf += "".join(chunks)
            lines = self.buf.split("\n")
            self.buf = lines.pop()
            if lines:
                self.text.configure(state="normal")
                for ln in lines:
                    self.add_line(ln)
                total = int(self.text.index("end-1c").split(".")[0])
                if total > 1500:
                    self.text.delete("1.0", f"{total - 1200}.0")
                self.text.see("end")
                self.text.configure(state="disabled")
        if done:
            if self.buf:
                self.text.configure(state="normal")
                self.add_line(self.buf)
                self.text.configure(state="disabled")
                self.buf = ""
            self.finished()
        self.root.after(80, self.poll)

    def on_close(self):
        stop_event.set()

        def fade(t):
            try:
                self.root.attributes("-alpha", 1 - t)
            except tk.TclError:
                pass
        Anim.run(("win",), 0.15, fade, done=self.root.destroy)

def run_app():
    global SCALE
    try:
        main.load_config()
        root = tk.Tk()
        Anim.root = root
        try:
            SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)
        except Exception:
            SCALE = 1.0
        try:
            root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        App(root)

        def fade_in(t):
            try:
                root.attributes("-alpha", t)
            except tk.TclError:
                pass
        Anim.run(("win",), 0.35, fade_in)
        root.mainloop()
    except Exception:
        fatal("ChessHelper crashed:\n\n" + traceback.format_exc())

if __name__ == "__main__":
    run_app()