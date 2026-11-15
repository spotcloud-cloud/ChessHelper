import mss, numpy as np, cv2

with mss.mss() as sct:
    mon = sct.monitors[1]
    img = np.array(sct.grab(mon))[:, :, :3]   # BGR

print("Screen size (pixels):", mon["width"], "x", mon["height"])

def near(color_bgr, tol=30):
    return (np.abs(img.astype(int) - np.array(color_bgr)).sum(axis=2) < tol)

dark  = near((86, 150, 118))     # green squares
light = near((210, 238, 238))    # cream squares
mask = (dark | light).astype(np.uint8) * 255

# Merge the squares into one solid blob, then take the biggest one
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
c = max(contours, key=cv2.contourArea)
left, top, w, h = cv2.boundingRect(c)

side = min(w, h)   # the board is square
print(f"BOARD = left={left}, top={top}, width={side}, height={side}")

cv2.imwrite("board_crop.png", img[top:top+side, left:left+side])
print("Saved board_crop.png")