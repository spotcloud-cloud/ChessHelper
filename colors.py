import mss, numpy as np
from collections import Counter

with mss.MSS() as sct:
    img = np.array(sct.grab(sct.monitors[1]))[:, :, :3]   # BGR

pix = img.reshape(-1, 3)
counts = Counter(map(tuple, pix[::7]))        # sample every 7th pixel for speed

print("Most common bright colors on screen (BGR, as the script uses them):")
shown = 0
for (b, g, r), n in counts.most_common(60):
    if (int(b) + int(g) + int(r)) / 3 < 100:  # skip the dark UI background
        continue
    print(f"  BGR=({b}, {g}, {r})   RGB=({r}, {g}, {b})   pixels~{n * 7}")
    shown += 1
    if shown == 8:
        break
print("\nThe two biggest entries should be the dark and light board squares.")