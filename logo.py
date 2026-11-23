import sys, os, struct
import numpy as np, cv2

_master = None

def _rr(S, x0, y0, x1, y1, r):
    m = np.zeros((S, S), np.uint8)
    cv2.rectangle(m, (x0 + r, y0), (x1 - r, y1), 255, -1)
    cv2.rectangle(m, (x0, y0 + r), (x1, y1 - r), 255, -1)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
        cv2.circle(m, (cx, cy), r, 255, -1)
    return m

def render_master(S=1024):
    u = S / 1024.0
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)

    # background: diagonal gradient with a faint chessboard pattern
    t = ((xx + yy) / (2.0 * S))[..., None]
    c1 = np.array((74, 42, 27), np.float32)       # deep navy (BGR)
    c2 = np.array((255, 140, 79), np.float32)     # bright blue (BGR)
    bg = c1 * (1 - t) + c2 * t
    sq = S / 8.0
    chk = ((xx // sq).astype(int) + (yy // sq).astype(int)) % 2
    bg = np.clip(bg * (1 + 0.08 * chk)[..., None], 0, 255)

    # pawn silhouette
    def rr(x0, y0, x1, y1, r):
        return _rr(S, int(x0 * u), int(y0 * u), int(x1 * u), int(y1 * u), int(r * u))
    pawn = np.zeros((S, S), np.uint8)
    cv2.circle(pawn, (int(512 * u), int(300 * u)), int(108 * u), 255, -1)             # head
    pawn = cv2.bitwise_or(pawn, rr(410, 408, 614, 452, 22))                          # collar
    body = np.array([(462, 440), (562, 440), (572, 520), (600, 610), (650, 720),
                     (374, 720), (424, 610), (452, 520)], np.float32) * u
    cv2.fillPoly(pawn, [body.astype(np.int32)], 255)                                 # body
    pawn = cv2.bitwise_or(pawn, rr(330, 712, 694, 776, 30))                          # base
    pawn = cv2.bitwise_or(pawn, rr(290, 770, 734, 836, 32))                          # foot

    # soft shadow
    shadow = np.roll(pawn, int(22 * u), axis=0).astype(np.float32) / 255.0
    shadow = cv2.GaussianBlur(shadow, (0, 0), 26 * u)
    out = bg * (1 - 0.42 * shadow[..., None])

    # pawn fill: soft vertical gradient from white to light blue
    top = np.array((252, 248, 246), np.float32)
    bot = np.array((240, 214, 196), np.float32)
    tp = np.clip((yy - 190 * u) / (650 * u), 0, 1)[..., None]
    fill = top * (1 - tp) + bot * tp
    m = (pawn.astype(np.float32) / 255.0)[..., None]
    out = out * (1 - m) + fill * m

    # rounded-square icon shape as the alpha channel
    alpha = _rr(S, 0, 0, S - 1, S - 1, int(0.22 * S))
    return np.dstack([np.clip(out, 0, 255).astype(np.uint8), alpha])

def render(size):
    """BGRA image of the logo at the given pixel size."""
    global _master
    if _master is None:
        _master = render_master(1024)
    return cv2.resize(_master, (size, size), interpolation=cv2.INTER_AREA)

def write_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    imgs = []
    for s in sizes:
        ok, buf = cv2.imencode(".png", render(s))
        imgs.append((s, buf.tobytes()))
    header = struct.pack("<HHH", 0, 1, len(imgs))
    offset = 6 + 16 * len(imgs)
    entries, data = b"", b""
    for s, png in imgs:
        d = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", d, d, 0, 0, 1, 32, len(png), offset)
        data += png
        offset += len(png)
    with open(path, "wb") as f:
        f.write(header + entries + data)

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    write_ico(os.path.join(here, "logo.ico"))
    ok, buf = cv2.imencode(".png", render(512))
    with open(os.path.join(here, "logo.png"), "wb") as f:
        f.write(buf.tobytes())
    print("Saved logo.ico and logo.png in", here)