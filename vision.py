import sys, os, traceback
import mss, numpy as np, cv2

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)      # folder of the .exe
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# BGR colors measured from the screen
STYLES = {
    "chesscom": {"light": (210, 238, 238), "dark": (86, 150, 118),
                 "hl": [(105, 247, 247), (43, 202, 186)],
                 "folder": "templates"},
    "rochess":  {"light": (242, 234, 227), "dark": (160, 127, 95),
                 "hl": [(249, 190, 197)],
                 "folder": "templates_rochess"},
}
STYLE = "chesscom"
ORIENT = "auto"         # auto / white / black = which side is at the bottom of the screen
LIGHT = DARK = None
HL = []
TPL_DIR = ""
BG_TOL = 22             # how close a pixel must be to the background to be erased
WHITE_BRIGHTNESS = 170  # bright-pixel level above which a piece counts as white
RED_MARGIN = 10         # red must beat green and blue by this much to count as check glow
GLOW_MIN_PIXELS = 60    # this many red pixels in a square = king-in-check glow

_printed_errors = set()

def set_style(name):
    global STYLE, LIGHT, DARK, HL, TPL_DIR
    if name not in STYLES:
        name = "chesscom"
    s = STYLES[name]
    STYLE = name
    LIGHT = np.array(s["light"])
    DARK = np.array(s["dark"])
    HL = [np.array(c) for c in s["hl"]]
    TPL_DIR = os.path.join(BASE_DIR, s["folder"])

def set_orientation(name):
    global ORIENT
    ORIENT = name if name in ("auto", "white", "black") else "auto"

set_style("chesscom")

def grab():
    with mss.MSS() as sct:
        return np.array(sct.grab(sct.monitors[1]))[:, :, :3]

def find_board(img):
    im = img.astype(int)
    def near(c, tol=40):
        return np.abs(im - c).sum(axis=2) < tol
    plain = near(LIGHT) | near(DARK)
    m8 = plain.astype(np.uint8) * 255
    m8 = cv2.morphologyEx(m8, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    cnts, _ = cv2.findContours(m8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    x, y, w, h = cv2.boundingRect(max(cnts, key=cv2.contourArea))
    side = (w // 8) * 8

    mask = plain.copy()
    for c in HL:
        mask |= near(c, 50)
    H, W = mask.shape

    top = y
    x0, x1 = max(0, x), min(W, x + side)
    for yy in range(max(0, y - 40), min(H, y + h)):
        if mask[yy, x0:x1].mean() > 0.6:
            top = yy
            break

    left = x
    y0, y1 = max(0, top), min(H, top + side)
    for xx in range(max(0, x - 20), min(W, x + w)):
        if mask[y0:y1, xx].mean() > 0.6:
            left = xx
            break
    return left, top, side

def prepare(raw):
    """Returns (gray image with background erased, is_highlighted, label_ink, glow).
    glow is None normally; for a king-in-check square it is 'w' or 'b' (piece color).
    A glowing square is never counted as a last-move highlight."""
    sq = cv2.resize(raw, (96, 96))
    si = sq.astype(int)
    gray = cv2.cvtColor(sq, cv2.COLOR_BGR2GRAY).astype(np.float32)
    maxc, minc = si.max(axis=2), si.min(axis=2)

    # strongly red pixels (BGR order: channel 2 is red) = the check glow
    red = (si[:, :, 2] - np.maximum(si[:, :, 0], si[:, :, 1])) > RED_MARGIN
    red = red & (si[:, :, 2] > 100)
    red_big = cv2.dilate(red.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)

    # background = the most common color among the non-red pixels
    flat = si.reshape(-1, 3)
    valid = ~red_big.reshape(-1)
    if valid.sum() < 600:
        valid = np.ones(len(flat), bool)
    fv = flat[valid]
    q = fv // 16
    key = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    vals, counts = np.unique(key, return_counts=True)
    top_key = vals[np.argmax(counts)]
    bg = np.median(fv[key == top_key], axis=0)

    d_plain = min(np.abs(bg - LIGHT).sum(), np.abs(bg - DARK).sum())
    highlighted = bool(d_plain > 30)

    region = sq[3:22, 3:20]
    rgray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    diff = np.abs(region.astype(int) - bg).sum(axis=2)
    ink = int(((diff > 45) & (rgray > 60) & ~red_big[3:22, 3:20]).sum())

    glow = None
    if red.sum() >= GLOW_MIN_PIXELS:
        # check glow: this square holds a king; only its color matters
        near_bg = (np.abs(si - LIGHT).sum(axis=2) < 30) | (np.abs(si - DARK).sum(axis=2) < 30)
        bright = (gray > 215) & ((maxc - minc) <= 28) & ~near_bg & ~red_big
        glow = "w" if bright.sum() >= 120 else "b"
        highlighted = False

    erase = (np.abs(si - bg).sum(axis=2) < BG_TOL) | red_big
    g = gray.copy()
    g[erase] = 0
    g[:30, :30] = 0      # rank number (top-left corner)
    g[74:, 70:] = 0      # file letter (bottom-right corner)
    return g, highlighted, ink, glow

def split_board(img, x, y, side):
    s = side // 8
    norm, hl, ink, glow = [], [], [], []
    for r in range(8):
        nrow, hrow, irow, grow = [], [], [], []
        for c in range(8):
            raw = img[y + r*s : y + (r+1)*s, x + c*s : x + (c+1)*s]
            g, h, i, gl = prepare(raw)
            nrow.append(g)
            hrow.append(h)
            irow.append(i)
            grow.append(gl)
        norm.append(nrow)
        hl.append(hrow)
        ink.append(irow)
        glow.append(grow)
    return norm, hl, ink, glow

def fname(sym):
    return os.path.join(TPL_DIR, f"{'w' if sym.isupper() else 'b'}_{sym.upper()}.png")

def save_templates():
    img = grab()
    x, y, side = find_board(img)
    sq, _, _, _ = split_board(img, x, y, side)
    layout = {0: "rnbqkbnr", 1: "pppppppp", 6: "PPPPPPPP", 7: "RNBQKBNR"}
    os.makedirs(TPL_DIR, exist_ok=True)
    for r, row in layout.items():
        for c, sym in enumerate(row):
            if not os.path.exists(fname(sym)):
                cv2.imwrite(fname(sym), sq[r][c].astype(np.uint8))
    print(f"Templates for '{STYLE}' saved in", TPL_DIR)
    print("(Only works from the starting position with White at the bottom.)")

def load_templates():
    t = {}
    for sym in "PNBRQK":
        img = cv2.imread(fname(sym), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise FileNotFoundError(
                f"Missing template {fname(sym)} (game style: {STYLE}). Put the board in the "
                "starting position (White at the bottom) and choose 'Save piece templates'.")
        t[sym] = img.astype(np.float32)
    return t

def is_empty(n):
    return (n[12:84, 12:84] > 0).sum() < 150

def brightness(n):
    c = n[12:84, 12:84]
    v = c[c > 0]
    return float(np.percentile(v, 90)) if v.size else 0.0

def score(n, t):
    padded = cv2.copyMakeBorder(n, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=0)
    return float(cv2.matchTemplate(padded, t, cv2.TM_CCOEFF_NORMED).max())

def read_screen_rows(sq, tpl, glow=None):
    rows, scores, lights = [], [], []
    for r in range(8):
        row, srow, lrow = "", [], []
        for c in range(8):
            n = sq[r][c]
            gl = glow[r][c] if glow else None
            if gl is not None:
                # a red check glow only ever sits on a king
                row += "K" if gl == "w" else "k"
                srow.append(1.0)
                lrow.append(250.0 if gl == "w" else 100.0)
            elif is_empty(n):
                row += "."
                srow.append(1.0)
                lrow.append(0.0)
            else:
                best = max(tpl, key=lambda k: score(n, tpl[k]))
                b = brightness(n)
                row += best if b > WHITE_BRIGHTNESS else best.lower()
                srow.append(score(n, tpl[best]))
                lrow.append(b)
        rows.append(row)
        scores.append(srow)
        lights.append(lrow)
    return rows, scores, lights

def white_at_bottom_by_pieces(rows):
    top = sum(ch.isupper() for row in rows[:4] for ch in row)
    bottom = sum(ch.isupper() for row in rows[4:] for ch in row)
    return bottom >= top

def decide_orientation(rows, ink, corner_glow=False, check_white=None):
    """True if White is at the bottom of the screen."""
    if ORIENT == "white":
        return True, "forced by setting"
    if ORIENT == "black":
        return False, "forced by setting"
    if corner_glow and check_white is not None:
        # a check glow sits on a corner label square, so the label ink is unreliable;
        # in puzzles the side to move (= the side in check) is at the bottom
        return check_white, "from the side in check (corner label hidden by the glow)"
    t, b = ink[0][0], ink[7][0]
    big = max(t, b)
    if big > 0 and abs(t - b) / big > 0.15:
        return t > b, f"from corner labels 8 vs 1 (ink top {t}, bottom {b})"
    return white_at_bottom_by_pieces(rows), f"from piece count (corner labels unclear: {t} vs {b})"

def rows_to_fen(rows):
    fen_rows = []
    for row in rows:
        out, empty = "", 0
        for ch in row:
            if ch == ".":
                empty += 1
            else:
                out += (str(empty) if empty else "") + ch
                empty = 0
        fen_rows.append(out + (str(empty) if empty else ""))
    return "/".join(fen_rows)

def _check_info(glow):
    colors = {glow[r][c] for r in range(8) for c in range(8) if glow[r][c]}
    check_white = (next(iter(colors)) == "w") if len(colors) == 1 else None
    return check_white, bool(glow[0][0] or glow[7][0])

def _read_state(tpl):
    img = grab()
    x, y, side = find_board(img)
    sq, hl, ink, glow = split_board(img, x, y, side)
    rows, _, _ = read_screen_rows(sq, tpl, glow)
    check_white, corner_glow = _check_info(glow)
    wab, _ = decide_orientation(rows, ink, corner_glow, check_white)

    movers = set()
    for r in range(8):
        for c in range(8):
            if hl[r][c] and rows[r][c] != ".":
                movers.add(rows[r][c].isupper())
    mover_white = next(iter(movers)) if len(movers) == 1 else None

    if not wab:
        rows = [row[::-1] for row in rows[::-1]]
    return {"placement": rows_to_fen(rows), "wab": wab, "mover_white": mover_white,
            "check_white": check_white, "box": (x, y, side)}

def read_state(tpl=None):
    tpl = tpl or load_templates()
    try:
        return _read_state(tpl)
    except Exception as e:
        key = (type(e).__name__, str(e))
        if key not in _printed_errors:          # print each distinct error once
            _printed_errors.add(key)
            print("\n[vision] board read failed -> real error:")
            traceback.print_exc()
        raise

def debug():
    img = grab()
    x, y, side = find_board(img)
    print("Game style:", STYLE, "| orientation setting:", ORIENT)
    print("Board found: left", x, "top", y, "size", side)
    sq, hl, ink, glow = split_board(img, x, y, side)
    rows, scores, lights = read_screen_rows(sq, load_templates(), glow)
    print("\nAs seen on screen (top row first):")
    for row in rows:
        print("  " + " ".join(row))
    print("\nHighlighted squares (X) and check glow (W/B = white/black king in check):")
    for r in range(8):
        print("  " + " ".join(glow[r][c].upper() if glow[r][c] else ("X" if hl[r][c] else ".")
                              for c in range(8)))
    print("\nShape match scores (below 0.6 = suspicious):")
    for srow in scores:
        print("  " + " ".join(f"{s:.2f}" for s in srow))
    print(f"\nBrightness (white pieces should be above {WHITE_BRIGHTNESS}, black below):")
    for lrow in lights:
        print("  " + " ".join(f"{v:5.0f}" for v in lrow))
    check_white, corner_glow = _check_info(glow)
    wab, why = decide_orientation(rows, ink, corner_glow, check_white)
    print("\nRank-number ink, left column top to bottom:", [ink[r][0] for r in range(8)])
    print("King in check:", "none" if check_white is None else ("White" if check_white else "Black"))
    print("Decision:", "White at bottom" if wab else "Black at bottom (board flipped)", "-", why)
    out = os.path.join(BASE_DIR, "debug_board.png")
    cv2.imwrite(out, img[y:y+side, x:x+side])
    print("Saved", out)

def show():
    st = read_state()
    print(st["placement"])
    print("White at bottom" if st["wab"] else "Black at bottom (board flipped)")
    m = st["mover_white"]
    print("Last mover:", "none (fresh game)" if m is None else ("White" if m else "Black"))
    c = st["check_white"]
    print("King in check:", "none" if c is None else ("White" if c else "Black"))

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if len(sys.argv) > 2:
        set_style(sys.argv[2])
    if cmd == "save":
        save_templates()
    elif cmd == "debug":
        debug()
    else:
        show()