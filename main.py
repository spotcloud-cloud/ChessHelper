import os, sys, time, json, ctypes
from ctypes import wintypes

# make screenshot pixels and click pixels use the same scale (must run first)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import numpy as np
import cv2
import mss
import chess, chess.engine
import vision

CONFIG_PATH = os.path.join(vision.BASE_DIR, "config.json")
STYLE_CHOICES = list(vision.STYLES.keys())
ORIENT_CHOICES = ["auto", "white", "black"]

# key, label, type, min (or choices), max, help
SETTINGS = [
    ("game_style", "Game / board style", str, STYLE_CHOICES, None,
     "chesscom = Chess.com, rochess = RoChess on Roblox. Each has its own piece templates."),
    ("orientation", "Board orientation", str, ORIENT_CHOICES, None,
     "auto = detect from the corner labels. white / black = force which side is at the BOTTOM of the screen."),
    ("stop_key", "Stop hotkey", str, None, None,
     "One letter or digit. Hold it to stop while running (works even when the game is in front)."),
    ("limit_strength", "Limit engine strength", bool, None, None,
     "on = play at the Elo below on normal moves, off = always full-strength Stockfish"),
    ("elo", "Engine strength (Elo)", int, 1320, 3190,
     "Strength of normal moves. Higher = fewer dumb moves."),
    ("think_time", "Think time (seconds)", float, 0.05, 30.0,
     "Per analysis. More time = stronger, and also fewer random mistakes."),
    ("obvious_gap", "Obvious-move gap (centipawns)", int, 0, 2000,
     "Best move must beat the 2nd best by this much to be played at full strength. Lower = plays closer to the engine."),
    ("mate_within", "Always play forced mate within (moves)", int, 0, 20,
     "0 turns this off."),
    ("use_drag", "Move pieces by dragging", bool, None, None,
     "off = click the piece, then click the square. on = press and drag."),
    ("click_hold", "Click hold time (seconds)", float, 0.01, 1.0,
     "How long the mouse button stays down per click. Raise this if clicks don't register."),
    ("click_gap", "Pause between the two clicks (seconds)", float, 0.05, 3.0,
     "Time between selecting the piece and clicking the target square."),
    ("move_speed", "Mouse travel time (seconds)", float, 0.05, 3.0,
     "How long the cursor takes to travel to a square."),
    ("after_move_delay", "Wait after each move (seconds)", float, 0.2, 10.0,
     "Gives the animation and the opponent's reply time to appear."),
    ("next_delay", "Wait after pressing Next (seconds)", float, 0.3, 10.0,
     "Gives the next puzzle time to load before reading the board."),
    ("max_retries", "Retries if a move doesn't register", int, 0, 10,
     "After this many failed retries it assumes the game has ended."),
    ("stop_when_game_over", "Stop when the game ends", bool, None, None,
     "on = go back to the menu when the game ends, off = wait for a new game to start"),
    ("stockfish_path", "Stockfish file", str, None, None,
     "File name next to the exe, or a full path."),
]
SPEC = {s[0]: s for s in SETTINGS}
DEFAULTS = {
    "game_style": "chesscom",
    "orientation": "auto",
    "stop_key": "o",
    "limit_strength": True,
    "elo": 2200,
    "think_time": 0.6,
    "obvious_gap": 120,
    "mate_within": 3,
    "use_drag": False,
    "click_hold": 0.08,
    "click_gap": 0.4,
    "move_speed": 0.3,
    "after_move_delay": 1.2,
    "next_delay": 1.5,
    "max_retries": 2,
    "stop_when_game_over": True,
    "stockfish_path": "stockfish.exe",
}
CFG = dict(DEFAULTS)
PUZZLE_MIN_THINK = 1.0     # puzzle mode thinks at least this long (seconds)
PUZZLE_SOLVED_WAIT = 12    # single-puzzle mode: no reply for this long = solved

# ---------------------------------------------------------------- config

def apply_cfg():
    vision.set_style(CFG["game_style"])
    vision.set_orientation(CFG["orientation"])

def coerce(key, value):
    _, _, typ, lo, hi, _ = SPEC[key]
    if typ is bool:
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("y", "yes", "1", "true", "on"): return True
            if v in ("n", "no", "0", "false", "off"): return False
            raise ValueError("answer y or n")
        return bool(value)
    if typ is str:
        s = str(value).strip()
        if isinstance(lo, list):
            if s.isdigit() and 1 <= int(s) <= len(lo):
                return lo[int(s) - 1]
            if s.lower() in lo:
                return s.lower()
            raise ValueError("choose one of: " + ", ".join(lo))
        if key == "stop_key":
            if len(s) != 1 or not s.isalnum():
                raise ValueError("enter a single letter or digit")
            return s.lower()
        return s
    v = typ(value)
    return max(lo, min(hi, v))

def save_config():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(CFG, f, indent=2)

def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        for k in DEFAULTS:
            if k in saved:
                try:
                    CFG[k] = coerce(k, saved[k])
                except Exception:
                    pass
        save_config()
    except FileNotFoundError:
        save_config()
    except Exception as e:
        print("Could not read config.json, using defaults:", e)
    apply_cfg()

def stockfish_path():
    p = CFG["stockfish_path"]
    return p if os.path.isabs(p) else os.path.join(vision.BASE_DIR, p)

def show_value(key):
    v = CFG[key]
    return ("on" if v else "off") if isinstance(v, bool) else v

def settings_menu():
    while True:
        print("\n=== Settings ===")
        for i, s in enumerate(SETTINGS, 1):
            print(f" {i:>2}. {s[1]}: {show_value(s[0])}")
        print("  r. Reset everything to defaults")
        print("  b. Back")
        choice = input("Pick a number to change: ").strip().lower()
        if choice in ("b", ""):
            return
        if choice == "r":
            CFG.update(DEFAULTS)
            save_config()
            apply_cfg()
            print("Reset to defaults.")
            continue
        if not choice.isdigit() or not (1 <= int(choice) <= len(SETTINGS)):
            print("Not a valid choice.")
            continue
        key, label, typ, lo, hi, help_ = SETTINGS[int(choice) - 1]
        print(f"\n{label}\n  {help_}")
        if typ is bool:
            print("  Answer y or n.")
        elif typ is str and isinstance(lo, list):
            print("  Options: " + ", ".join(f"{i} = {n}" for i, n in enumerate(lo, 1)))
        elif typ in (int, float):
            print(f"  Allowed range: {lo} to {hi}")
        raw = input(f"  New value (now {show_value(key)}, blank = keep): ").strip()
        if not raw:
            continue
        try:
            new = coerce(key, raw)
        except Exception as e:
            print("  Invalid value:", e)
            continue
        if typ in (int, float) and float(raw) != new:
            print(f"  Adjusted to {new} (allowed range {lo} to {hi}).")
        CFG[key] = new
        save_config()
        apply_cfg()
        print("  Saved.")

# ---------------------------------------------------------------- board helpers

def guess_castling(b):
    r = ""
    wk, bk = chess.Piece(chess.KING, True), chess.Piece(chess.KING, False)
    wr, br = chess.Piece(chess.ROOK, True), chess.Piece(chess.ROOK, False)
    if b.piece_at(chess.E1) == wk:
        if b.piece_at(chess.H1) == wr: r += "K"
        if b.piece_at(chess.A1) == wr: r += "Q"
    if b.piece_at(chess.E8) == bk:
        if b.piece_at(chess.H8) == br: r += "k"
        if b.piece_at(chess.A8) == br: r += "q"
    return r or "-"

def build_board(st):
    turn_white = True if st["mover_white"] is None else (not st["mover_white"])
    tmp = chess.Board(st["placement"] + " w - - 0 1")
    fen = f'{st["placement"]} {"w" if turn_white else "b"} {guess_castling(tmp)} - 0 1'
    return chess.Board(fen), turn_white

def plausible(board):
    if board.status() != chess.STATUS_VALID:
        return False
    for color in (True, False):
        n = lambda pt: len(board.pieces(pt, color))
        pawns = n(chess.PAWN)
        extras = (max(0, n(chess.KNIGHT) - 2) + max(0, n(chess.BISHOP) - 2) +
                  max(0, n(chess.ROOK) - 2) + max(0, n(chess.QUEEN) - 1))
        if n(chess.KING) != 1 or pawns > 8 or extras > 8 - pawns:
            return False
    return True

def describe_result(board):
    o = board.outcome()
    if o is None:
        return "game over"
    if o.termination == chess.Termination.CHECKMATE:
        return "checkmate, " + ("White" if o.winner else "Black") + " wins"
    return o.termination.name.replace("_", " ").lower()

# ---------------------------------------------------------------- mouse input (Windows SendInput)

user32 = ctypes.windll.user32
ULONG_PTR = ctypes.c_size_t

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _anonymous_ = ("i",)
    _fields_ = [("type", wintypes.DWORD), ("i", _I)]

MOVE, LEFTDOWN, LEFTUP = 0x0001, 0x0002, 0x0004
ABSOLUTE, VIRTUALDESK = 0x8000, 0x4000

class FailSafe(Exception):
    pass

class StopKey(Exception):
    pass

def _send(flags, nx=0, ny=0):
    inp = INPUT(type=0, mi=MOUSEINPUT(nx, ny, 0, flags, 0, 0))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

def _virtual():
    return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
            user32.GetSystemMetrics(78), user32.GetSystemMetrics(79))

def cursor_pos():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y

def stop_pressed():
    k = (CFG.get("stop_key") or "").strip().upper()[:1]
    if not k:
        return False
    return bool(user32.GetAsyncKeyState(ord(k)) & 0x8000)

def check_failsafe():
    """Abort on the stop hotkey, or when the mouse is slammed into a screen corner."""
    if stop_pressed():
        raise StopKey()
    vx, vy, vw, vh = _virtual()
    x, y = cursor_pos()
    if x <= vx + 1 and y <= vy + 1 or x >= vx + vw - 2 and y <= vy + 1 \
       or x <= vx + 1 and y >= vy + vh - 2 or x >= vx + vw - 2 and y >= vy + vh - 2:
        raise FailSafe()

def sleep_check(seconds):
    """Sleep in small slices so the stop key stays responsive."""
    end = time.time() + seconds
    while time.time() < end:
        check_failsafe()
        time.sleep(min(0.05, max(0.0, end - time.time())))

def set_cursor(x, y):
    vx, vy, vw, vh = _virtual()
    nx = int((x - vx) * 65535 / max(1, vw - 1))
    ny = int((y - vy) * 65535 / max(1, vh - 1))
    _send(MOVE | ABSOLUTE | VIRTUALDESK, nx, ny)

def move_to(x, y, duration=0.2):
    sx, sy = cursor_pos()
    steps = max(4, int(duration / 0.01))
    for i in range(1, steps + 1):
        set_cursor(sx + (x - sx) * i / steps, sy + (y - sy) * i / steps)
        time.sleep(duration / steps)
    set_cursor(x, y)
    time.sleep(0.03)

def mouse_down():
    _send(LEFTDOWN)

def mouse_up():
    _send(LEFTUP)

def screen_origin():
    with mss.MSS() as sct:
        m = sct.monitors[1]
        return m["left"], m["top"]

def square_xy(sq, st):
    ox, oy = screen_origin()
    x, y, side = st["box"]
    f, r = chess.square_file(sq), chess.square_rank(sq)
    col = f if st["wab"] else 7 - f
    row = 7 - r if st["wab"] else r
    s = side / 8
    return ox + x + (col + 0.5) * s, oy + y + (row + 0.5) * s

def press(x, y):
    check_failsafe()
    move_to(x, y, CFG["move_speed"])
    set_cursor(x + 2, y)
    time.sleep(0.03)
    set_cursor(x, y)
    time.sleep(0.08)
    mouse_down()
    time.sleep(CFG["click_hold"])
    mouse_up()

def drag(x1, y1, x2, y2):
    check_failsafe()
    move_to(x1, y1, CFG["move_speed"])
    time.sleep(0.1)
    mouse_down()
    time.sleep(0.15)
    move_to(x2, y2, CFG["move_speed"])
    time.sleep(0.15)
    mouse_up()

def play(move, st):
    x1, y1 = square_xy(move.from_square, st)
    x2, y2 = square_xy(move.to_square, st)
    if CFG["use_drag"]:
        drag(x1, y1, x2, y2)
    else:
        press(x1, y1)
        time.sleep(CFG["click_gap"])
        press(x2, y2)
    if move.promotion:
        time.sleep(0.5)
        press(x2, y2)
    ox, oy = screen_origin()
    bx, by, side = st["box"]
    move_to(ox + bx + side + 40, oy + by + side // 2, 0.15)   # park beside the board

def cursor_check():
    """Moves the cursor to a1, h1 and h8 (no clicking) and compares where it lands."""
    tpl = vision.load_templates()
    st = vision.read_state(tpl)
    ox, oy = screen_origin()
    print("Screen origin:", (ox, oy), " Board (x, y, size):", st["box"])
    print("White at bottom" if st["wab"] else "Black at bottom (board flipped)")
    print("Switch to the game window. Starting in 3 seconds; watch where the cursor goes.")
    time.sleep(3)
    for name in ("a1", "h1", "h8"):
        sq = chess.parse_square(name)
        x, y = square_xy(sq, st)
        move_to(x, y, 0.6)
        time.sleep(0.8)
        ax, ay = cursor_pos()
        off = max(abs(ax - x), abs(ay - y))
        flag = "OK" if off <= 2 else "MISMATCH (display scaling or multi-monitor problem?)"
        print(f"  {name}: wanted ({x:.0f}, {y:.0f}), cursor is at ({ax}, {ay}) -> {flag}")
    print("The cursor should have sat in the centre of those three squares.")

def test_move():
    tpl = vision.load_templates()
    st = vision.read_state(tpl)
    print("Position:", st["placement"])
    print("White at bottom" if st["wab"] else "Black at bottom (board flipped)")
    raw = input("Move to test, like e2e4 (blank = cancel): ").strip().lower()
    if not raw:
        return
    try:
        move = chess.Move.from_uci(raw)
    except Exception:
        print("That isn't a move like e2e4.")
        return
    print("Switch to the game window now. Playing in 3 seconds...")
    time.sleep(3)
    mode = "drag" if CFG["use_drag"] else "click-click"
    print(f"Playing {raw} by {mode} (hold {CFG['click_hold']}s, gap {CFG['click_gap']}s).")
    play(move, st)
    print("Done. Did the piece move?")

def stable_state(tpl):
    a = vision.read_state(tpl)
    time.sleep(0.35)
    b = vision.read_state(tpl)
    same = (a["placement"], a["wab"], a["mover_white"]) == \
           (b["placement"], b["wab"], b["mover_white"])
    return b if same else None

# ---------------------------------------------------------------- Next button (puzzles)

def find_next_button(img):
    """Finds the big blue 'Next' button left of the board. Returns (x, y) in image pixels or None."""
    try:
        bx, by, side = vision.find_board(img)
    except Exception:
        return None
    if bx < 60:
        return None
    region = np.ascontiguousarray(img[:, :max(0, bx - 10)])
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    mask = ((h >= 100) & (h <= 122) & (s >= 150) & (v >= 170)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_area = None, 0
    for c in cnts:
        x, y, w, hh = cv2.boundingRect(c)
        area = w * hh
        if area >= 3500 and 1.4 <= w / max(1, hh) <= 5 and area > best_area:
            best, best_area = (x + w // 2, y + hh // 2), area
    return best

def next_check():
    """Shows where the Next button is found (moves the cursor there, no click)."""
    img = vision.grab()
    ox, oy = screen_origin()
    pos = find_next_button(img)
    if pos is None:
        print("No Next button found. Solve (or fail) a puzzle so the Next button is")
        print("showing, keep the whole board on screen, and try again.")
        return
    x, y = pos[0] + ox, pos[1] + oy
    print(f"Next button found at ({x}, {y}). Moving the cursor there in 3 seconds...")
    time.sleep(3)
    move_to(x, y, 0.6)
    print("The cursor should be sitting on the blue Next button.")

# ---------------------------------------------------------------- engine

def new_engine():
    return chess.engine.SimpleEngine.popen_uci(stockfish_path())

def limit(t=None):
    return chess.engine.Limit(time=t if t else CFG["think_time"])

def full_strength_analysis(board, t=None):
    eng = new_engine()
    try:
        infos = eng.analyse(board, limit(t), multipv=2)
    finally:
        try: eng.quit()
        except Exception: pass
    return [infos] if isinstance(infos, dict) else infos

def weak_play(board):
    eng = new_engine()
    try:
        eng.configure({"UCI_LimitStrength": True, "UCI_Elo": CFG["elo"]})
        return eng.play(board, limit()).move
    finally:
        try: eng.quit()
        except Exception: pass

def plain_play(board, t=None):
    eng = new_engine()
    try:
        return eng.play(board, limit(t)).move
    finally:
        try: eng.quit()
        except Exception: pass

def choose_move(board, force_full=False):
    t = max(CFG["think_time"], PUZZLE_MIN_THINK) if force_full else None
    try:
        infos = full_strength_analysis(board, t)
        best = infos[0]["pv"][0]
        if force_full or not CFG["limit_strength"]:
            return best, "full strength"
        if len(infos) < 2:
            return best, "only legal move"
        s1 = infos[0]["score"].pov(board.turn)
        s2 = infos[1]["score"].pov(board.turn)
        m = CFG["mate_within"]
        if m > 0 and s1.is_mate() and s1.mate() > 0 and s1.mate() <= m:
            return best, f"mate in {s1.mate()}"
        gap = s1.score(mate_score=10000) - s2.score(mate_score=10000)
        if gap >= CFG["obvious_gap"]:
            return best, f"obvious move (gap {gap} cp)"
    except Exception as ex:
        print("!! analysis failed:", type(ex).__name__, "FEN:", board.fen())
        return plain_play(board, t), "fallback: plain full-strength move"

    try:
        return weak_play(board), f"normal move (~{CFG['elo']} Elo)"
    except Exception as ex:
        print("!! Elo-limited play failed:", type(ex).__name__, "FEN:", board.fen())
        return plain_play(board), "fallback: plain full-strength move"

# ---------------------------------------------------------------- main loops

def wait_for_new_position(tpl, placement):
    print("Waiting for a new position (start a new game, or press Ctrl+C to go back)...")
    while True:
        sleep_check(1.0)
        try:
            st = stable_state(tpl)
        except Exception:
            continue
        if st is not None and st["placement"] != placement:
            return

def run(dry, puzzle=False):
    if not os.path.exists(stockfish_path()):
        print("Can't find Stockfish at:", stockfish_path())
        print("Put stockfish.exe next to this program, or change the path in Settings.")
        return
    apply_cfg()
    tpl = vision.load_templates()
    print("Game style:", CFG["game_style"], "| orientation:", CFG["orientation"])
    if puzzle:
        print("PUZZLE MODE: full-strength engine, stops when the puzzle looks solved.")
    elif CFG["limit_strength"]:
        print(f"Normal moves ~{CFG['elo']} Elo, obvious moves at full strength.")
    else:
        print("Playing at full engine strength.")
    if not puzzle:
        print("Stops when the game ends." if CFG["stop_when_game_over"]
              else "Waits for a new game when one ends.")
    print("Running" + (" (dry run: no clicking)" if dry else "") +
          f". Hold '{CFG['stop_key']}', press Ctrl+C, or move the mouse into a screen corner to stop.")

    last_fen = None
    last_moved = None
    tries = 0
    last_bad = None
    hidden_msg = False
    opp_seen = None
    opp_since = time.time()

    while True:
        check_failsafe()
        try:
            st = stable_state(tpl)
        except Exception:
            if not hidden_msg:
                print("Can't see the board right now (is it fully on screen?)")
                hidden_msg = True
            sleep_check(1.0)
            continue
        hidden_msg = False
        if st is None:
            continue

        board, turn_white = build_board(st)

        if not plausible(board):
            if st["placement"] != last_bad:
                print("Skipping a misread board:", st["placement"])
                last_bad = st["placement"]
            sleep_check(0.8)
            continue

        if board.is_game_over():
            print("Game over:", describe_result(board))
            if CFG["stop_when_game_over"] or puzzle:
                return
            wait_for_new_position(tpl, st["placement"])
            last_moved, tries, last_fen = None, 0, None
            continue

        if turn_white != st["wab"]:
            last_moved, tries = None, 0
            if puzzle and not dry:
                if st["placement"] != opp_seen:
                    opp_seen = st["placement"]
                    opp_since = time.time()
                elif time.time() - opp_since > PUZZLE_SOLVED_WAIT:
                    print(f"No reply for {PUZZLE_SOLVED_WAIT} seconds after my move:")
                    print("the puzzle is probably solved. (If it never moved, check the orientation.)")
                    return
            sleep_check(0.4)
            continue
        opp_seen = None

        fen = board.fen()
        if dry and fen == last_fen:
            sleep_check(0.8)
            continue

        if not dry and fen == last_moved:
            tries += 1
            if tries > CFG["max_retries"]:
                print("The board didn't change after my move. Either the game has ended")
                print("(solved, resigned, timeout or draw) or the game ignored the mouse input.")
                print("Try menu option 9 (Cursor check) and option 8 (Test a move).")
                if CFG["stop_when_game_over"] or puzzle:
                    return
                wait_for_new_position(tpl, st["placement"])
                last_moved, tries = None, 0
                continue
            print(f"Move didn't register, retrying ({tries}/{CFG['max_retries']})...")
        else:
            tries = 0

        last_fen = fen
        print("Position:", fen)
        move, reason = choose_move(board, force_full=puzzle)
        print("Move:", board.san(move), f"({move.uci()}) -", reason)
        if not dry:
            play(move, st)
            last_moved = fen
            sleep_check(CFG["after_move_delay"])

def auto_puzzles():
    """Solves puzzle after puzzle: plays the moves, presses Next, repeats until the stop key."""
    if not os.path.exists(stockfish_path()):
        print("Can't find Stockfish at:", stockfish_path())
        return
    apply_cfg()
    tpl = vision.load_templates()
    ox, oy = screen_origin()
    print("AUTO PUZZLES: solves a puzzle, presses Next, and repeats.")
    print(f"Hold '{CFG['stop_key']}' (about half a second) to stop. Ctrl+C or a screen corner also work.")
    print("Starting in 3 seconds. Click into the game window now.")
    sleep_check(3)

    solved = 0
    last_moved = None
    tries = 0
    last_bad = None
    hidden_msg = False
    opp_seen = None
    opp_since = time.time()
    warned = False

    while True:
        check_failsafe()

        # 1) puzzle finished: the Next button is showing
        try:
            pos = find_next_button(vision.grab())
        except Exception:
            pos = None
        if pos is not None:
            solved += 1
            print(f"Puzzle finished (#{solved}). Pressing Next...")
            press(pos[0] + ox, pos[1] + oy)
            move_to(pos[0] + ox - 120, pos[1] + oy, 0.15)       # step off the button
            last_moved, tries, opp_seen, warned = None, 0, None, False
            sleep_check(CFG["next_delay"])
            continue

        # 2) read the board
        try:
            st = stable_state(tpl)
        except Exception:
            if not hidden_msg:
                print("Can't see the board right now (is it fully on screen?)")
                hidden_msg = True
            sleep_check(1.0)
            continue
        hidden_msg = False
        if st is None:
            continue

        board, turn_white = build_board(st)

        if not plausible(board):
            if st["placement"] != last_bad:
                print("Skipping a misread board (a new puzzle may be loading):", st["placement"])
                last_bad = st["placement"]
            sleep_check(0.8)
            continue

        if board.is_game_over():
            sleep_check(0.8)
            continue

        # 3) opponent's turn: wait for the reply
        if turn_white != st["wab"]:
            last_moved, tries = None, 0
            if st["placement"] != opp_seen:
                opp_seen = st["placement"]
                opp_since = time.time()
                warned = False
            elif time.time() - opp_since > 20 and not warned:
                print("Nothing has happened for 20 seconds. If the puzzle looks solved, the Next")
                print("button wasn't found: use menu option 10 (Next button check).")
                warned = True
            sleep_check(0.4)
            continue
        opp_seen = None

        # 4) my turn
        fen = board.fen()
        if fen == last_moved:
            tries += 1
            if tries > CFG["max_retries"] + 1:
                print("The board stopped changing after my move, so I'm stopping.")
                print("(Failed puzzle, or the game ignored the mouse. Try menu options 8 and 9.)")
                return
            print(f"Move didn't register, retrying ({tries}/{CFG['max_retries'] + 1})...")
        else:
            tries = 0

        print("Position:", fen)
        move, reason = choose_move(board, force_full=True)
        print("Move:", board.san(move), f"({move.uci()}) -", reason)
        play(move, st)
        last_moved = fen
        sleep_check(CFG["after_move_delay"])

# ---------------------------------------------------------------- menu

def safe(fn, *args):
    try:
        fn(*args)
    except KeyboardInterrupt:
        print("\nStopped.")
    except StopKey:
        print(f"\nStopped (hotkey '{CFG['stop_key']}').")
    except FailSafe:
        print("\nStopped (mouse moved into a screen corner).")
    except Exception as e:
        print("\nError:", type(e).__name__, e)

def menu():
    while True:
        print(f"\n=== ChessHelper (style: {CFG['game_style']}) ===")
        print(" 1. Start playing")
        print(" 2. Puzzle mode (one puzzle, full strength)")
        print(" 3. Auto puzzles (keeps going, presses Next, until the stop key)")
        print(" 4. Dry run (show moves only, no clicking)")
        print(" 5. Settings")
        print(" 6. Save piece templates (starting position, White at the bottom)")
        print(" 7. Debug view (what the program sees)")
        print(" 8. Test a move (plays one move you type)")
        print(" 9. Cursor check (moves to a1, h1, h8 without clicking)")
        print("10. Next button check (finds the blue Next button, no clicking)")
        print("11. Quit")
        c = input("> ").strip()
        if c == "1": safe(run, False)
        elif c == "2": safe(run, False, True)
        elif c == "3": safe(auto_puzzles)
        elif c == "4": safe(run, True)
        elif c == "5": safe(settings_menu)
        elif c == "6": safe(vision.save_templates)
        elif c == "7": safe(vision.debug)
        elif c == "8": safe(test_move)
        elif c == "9": safe(cursor_check)
        elif c == "10": safe(next_check)
        elif c == "11": return

def main():
    load_config()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "":
        menu()
        return
    if cmd == "dry": safe(run, True)
    elif cmd == "run": safe(run, False)
    elif cmd == "puzzle": safe(run, False, True)
    elif cmd == "auto": safe(auto_puzzles)
    elif cmd == "settings": safe(settings_menu)
    elif cmd == "save": safe(vision.save_templates)
    elif cmd == "debug": safe(vision.debug)
    elif cmd == "test": safe(test_move)
    elif cmd == "cursor": safe(cursor_check)
    elif cmd == "next": safe(next_check)
    elif cmd == "read": safe(vision.show)
    else:
        print("Unknown option. Use: run, puzzle, auto, dry, settings, save, debug, test, cursor, next, read (or no option for the menu).")
    if getattr(sys, "frozen", False):
        input("\nPress Enter to close...")

if __name__ == "__main__":
    main()