import chess, chess.engine

STOCKFISH_PATH = r"C:\Users\hamza\Downloads\ChessHelper\stockfish.exe"
board = chess.Board("rnbqkbnr/pp2pppp/8/2pp2Q1/4P3/3P4/PPP2PPP/RNB1KBNR b KQkq - 0 1")
lim = chess.engine.Limit(time=0.3)

def run(name, fn):
    try:
        print(f"[ OK ] {name}: {fn()}")
    except Exception as e:
        print(f"[FAIL] {name}: {type(e).__name__}: {e}")

def new():
    return chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

def t_info():
    e = new()
    try:
        return e.id.get("name"), "| Elo range:", e.options["UCI_Elo"].min, "-", e.options["UCI_Elo"].max
    finally:
        e.quit()

def t_plain():
    e = new()
    try:
        return e.play(board, lim).move
    finally:
        e.quit()

def t_elo():
    e = new()
    try:
        e.configure({"UCI_LimitStrength": True, "UCI_Elo": 1600})
        return e.play(board, lim).move
    finally:
        e.quit()

def t_multipv():
    e = new()
    try:
        infos = e.analyse(board, lim, multipv=2)
        return [i["pv"][0] for i in infos]
    finally:
        e.quit()

def t_two():
    a, b = new(), new()
    try:
        return a.play(board, lim).move, b.play(board, lim).move
    finally:
        a.quit()
        b.quit()

run("engine info", t_info)
run("plain play", t_plain)
run("Elo-limited play", t_elo)
run("multipv=2 analysis", t_multipv)
run("two engines at once", t_two)