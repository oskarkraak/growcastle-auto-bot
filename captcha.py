import cv2
import numpy as np
import matplotlib.pyplot as plt

# Load image
img = cv2.imread('captcha_screenshots/screenshot_005.png')
if img is None:
    raise FileNotFoundError("Image not found.")
# Convert to grayscale and threshold using Otsu
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
# Apply slight blur
blur = cv2.GaussianBlur(gray, (5,5), 0)
_, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
# Invert threshold if needed: logs are lighter than background so white on dark after threshold. Check mean
# Actually, background is darker, logs are lighter, so threshold will produce background=0, logs=255.
# Good.
# Morph close to fill holes
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9,9))
closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
# Find contours
contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
# Filter contours by area, choose those > threshold
areas = [(cv2.contourArea(cnt), idx) for idx, cnt in enumerate(contours)]
# Keep those with area > some threshold, e.g. >1000
filtered = [contours[idx] for area, idx in areas if area > 2000]
# Expect 8 logs
print(len(contours), len(filtered))
# If filtered >8, take largest 8 by area
filtered_sorted = sorted(filtered, key=cv2.contourArea, reverse=True)
filtered_top8 = filtered_sorted[:8]

# Try without morphological closing
contours2, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
filtered2 = [cnt for cnt in contours2 if cv2.contourArea(cnt) > 2000]
len(filtered2)

filtered2_sorted = sorted(filtered2, key=lambda cnt: cv2.contourArea(cnt), reverse=True)[:8]
rects2 = []
for i, cnt in enumerate(filtered2_sorted):
    rect = cv2.minAreaRect(cnt)
    box = cv2.boxPoints(rect).astype(int)
    # compute longest edge and angle
    edges = []
    for j in range(4):
        p1 = box[j]
        p2 = box[(j+1)%4]
        edge_vec = p2 - p1
        length = np.linalg.norm(edge_vec)
        edges.append((length, edge_vec, (p1,p2)))
    length, vec, pts = max(edges, key=lambda x: x[0])
    dx, dy = vec
    angle = np.degrees(np.arctan2(dy, dx))
    angle_norm = angle % 180
    angle_horiz = angle_norm if angle_norm <=90 else 180-angle_norm
    tilt_vert = 90 - angle_horiz
    rects2.append({'i':i, 'center':rect[0],'angle':angle, 'angle_norm':angle_norm,
                   'angle_horiz':angle_horiz, 'tilt_vert':tilt_vert, 'box':box})
# identify most tilted
most_tilted2 = max(rects2, key=lambda x: x['tilt_vert'])

# --- Assign positions to each rectangle ---
# Define positions in order (fixed: swapped Left/Right)
positions = ['Top', 'Top Left', 'Left', 'Bottom Left', 'Bottom', 'Bottom Right', 'Right', 'Top Right']
# Get image center
img_h, img_w = img.shape[:2]
center_x, center_y = img_w/2, img_h/2
# Compute angle from image center to each rect center
import math
rect_angles = []
for r in rects2:
    cx, cy = r['center']
    dx = cx - center_x
    dy = cy - center_y
    angle = (math.degrees(math.atan2(-dy, dx)) + 360) % 360  # y axis inverted for image
    rect_angles.append((r['i'], angle, r))
# Sort by angle (0=right, 90=up, 180=left, 270=down)
rect_angles_sorted = sorted(rect_angles, key=lambda x: x[1])
# Assign positions by angle order: start from Top (90deg), go clockwise
# Find the rect closest to 90deg (top)
top_idx = min(range(len(rect_angles_sorted)), key=lambda i: abs(rect_angles_sorted[i][1]-90))
# Reorder so that top is first, then clockwise
rect_angles_sorted = rect_angles_sorted[top_idx:] + rect_angles_sorted[:top_idx]
# Invert all except the first item (keep top first, then reverse the rest)
rect_angles_sorted = [rect_angles_sorted[0]] + rect_angles_sorted[:0:-1]
# Now assign positions
rect_pos_map = {}
for pos, (idx, angle, r) in zip(positions, rect_angles_sorted):
    rect_pos_map[pos] = r
print("Rectangle to position mapping:")
for pos in positions:
    print(f"{pos}: index={rect_pos_map[pos]['i']}, center={rect_pos_map[pos]['center']}")

import pandas as pd
df = pd.DataFrame([{'Index':r['i'],
                    'Center':tuple(map(lambda v: round(v,2), r['center'])),
                    'Angle':round(r['angle'],2),
                    'AngleNorm':round(r['angle_norm'],2),
                    'AngleHoriz':round(r['angle_horiz'],2),
                    'TiltVert':round(r['tilt_vert'],2)} for r in rects2])
print(df)
print(most_tilted2)

# Visualize the results
for r in rects2:
    # Use red color for the most tilted log, green for others
    color = (0,0,255) if r['i'] == most_tilted2['i'] else (0,255,0)
    cv2.polylines(img, [r['box']], True, color, 2)
    cv2.putText(img, f"{r['i']}: {round(r['angle'],1)}", tuple(map(int, r['center'])), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0), 1)
# Draw position numbers (0-7) at each log's center in clockwise order
for pos_idx, pos in enumerate(positions):
    r = rect_pos_map[pos]
    cx, cy = map(int, r['center'])
    cv2.putText(img, str(pos_idx), (cx, cy-15), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
import os
output_path = './rects_visualization.png'
os.makedirs(os.path.dirname(output_path), exist_ok=True)
cv2.imwrite(output_path, img)

