import sys, os, subprocess
import cv2, numpy as np
import chess.engine
import main, vision

if getattr(sys, "frozen", False):
    RES_DIR = getattr(sys, "_MEIPASS", vision.BASE_DIR)   # where bundled files are unpacked
else:
    RES_DIR = vision.BASE_DIR

def _load_templates():
    t = {}
    folder = os.path.basename(vision.TPL_DIR)             # templates or templates_rochess
    for sym in "PNBRQK":
        name = f"{'w' if sym.isupper() else 'b'}_{sym}.png"
        img = None
        for base in (vision.TPL_DIR, os.path.join(RES_DIR, folder)):   # external first
            img = cv2.imread(os.path.join(base, name), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                break
        if img is None:
            raise FileNotFoundError(
                f"Missing template {name} for style '{vision.STYLE}'. "
                "Use Tools > Save piece templates from the starting position.")
        t[sym] = img.astype(np.float32)
    return t

def _stockfish_path():
    p = main.CFG["stockfish_path"]
    if os.path.isabs(p):
        return p
    external = os.path.join(vision.BASE_DIR, p)
    if os.path.exists(external):
        return external
    bundled = os.path.join(RES_DIR, p)
    return bundled if os.path.exists(bundled) else external

def _new_engine():
    """Start Stockfish without opening a console window."""
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0                                  # SW_HIDE
        kwargs["startupinfo"] = si
    try:
        return chess.engine.SimpleEngine.popen_uci(main.stockfish_path(), **kwargs)
    except TypeError:
        # very old python-chess without extra-argument support
        return chess.engine.SimpleEngine.popen_uci(main.stockfish_path())

vision.load_templates = _load_templates
main.stockfish_path = _stockfish_path
main.new_engine = _new_engine