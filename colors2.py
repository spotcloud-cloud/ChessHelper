import mss, numpy as np, cv2
from collections import Counter

DARK  = np.array((160, 127, 95))    # BGR, measured from your screen
LIGHT = np.array((242, 234, 227))

with mss.MSS() as sct:
    img = np.array(sct.grab(sct.monitors[1]))[:, :, :3]

im = img.astype(int)
def near(c, tol):
    return np.abs(im - c).sum(axis=2) < tol

# Find the board: biggest blob of dark+light square colors
m = (near(DARK, 20) | near(LIGHT, 20)).astype(np.uint8) * 255
m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
x, y, w, h = cv2.boundingRect(max(cnts, key=cv2.contourArea))
side = (w // 8) * 8
print(f"Board region: left={x} top={y} width={w} height={h}")

board = img[y:y + h, x:x + side].reshape(-1, 3).astype(int)
# colorful pixels only (highlights), skipping the two normal square colors
sat = board.max(axis=1) - board.min(axis=1)
keep = (sat > 25) \
    & (np.abs(board - DARK).sum(axis=1) > 25) \
    & (np.abs(board - LIGHT).sum(axis=1) > 25)
counts = Counter(map(tuple, board[keep][::3]))

print("\nMost common highlight-like colors on the board:")
for (b, g, r), n in counts.most_common(6):
    print(f"  BGR=({b}, {g}, {r})   RGB=({r}, {g}, {b})   pixels~{n * 3}")