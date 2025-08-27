"""
Tilt-based captcha solver implementation.

This solver detects tilted logs in individual screenshots.
"""

from typing import Optional
from .captcha_solver import CaptchaSolver

import cv2
import numpy as np
import matplotlib.pyplot as plt
import math
import os
import pandas as pd


class TiltBasedSolver(CaptchaSolver):
    """Solver that detects tilted logs in individual screenshots."""
    
    def solve_captcha(self, folder_name: str, screenshot_count: int) -> Optional[int]:
        return solve(folder_name, screenshot_count)


def load_and_preprocess_image(path):
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError("Image not found.")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5,5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9,9))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    return img, thresh, closed

def find_and_filter_contours(binary_img, area_thresh=2000, top_n=8):
    contours, _ = cv2.findContours(binary_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filtered = [cnt for cnt in contours if cv2.contourArea(cnt) > area_thresh]
    filtered_sorted = sorted(filtered, key=cv2.contourArea, reverse=True)[:top_n]
    return filtered_sorted

def extract_rect_features(contours):
    rects = []
    for i, cnt in enumerate(contours):
        rect = cv2.minAreaRect(cnt)
        box = cv2.boxPoints(rect).astype(int)
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
        rects.append({'i':i, 'center':rect[0],'angle':angle, 'angle_norm':angle_norm,
                       'angle_horiz':angle_horiz, 'tilt_vert':tilt_vert, 'box':box})
    return rects

def assign_positions(rects, img_shape):
    img_h, img_w = img_shape[:2]
    center_x, center_y = img_w/2, img_h/2
    rect_angles = []
    for r in rects:
        cx, cy = r['center']
        dx = cx - center_x
        dy = cy - center_y
        angle = (math.degrees(math.atan2(-dy, dx)) + 360) % 360
        rect_angles.append((r['i'], angle, r))
    rect_angles_sorted = sorted(rect_angles, key=lambda x: x[1])
    # Find the rectangle closest to 90deg (top)
    top_idx = min(range(len(rect_angles_sorted)), key=lambda i: abs(rect_angles_sorted[i][1]-90))
    # Rotate so that top is first, then clockwise
    rect_angles_sorted = rect_angles_sorted[top_idx:] + rect_angles_sorted[:top_idx]
    rect_angles_sorted = rect_angles_sorted[:1] + rect_angles_sorted[1:][::-1]
    # Map positions 0-7 clockwise
    rect_pos_map = {}
    for pos_num, (idx, angle, r) in enumerate(rect_angles_sorted):
        rect_pos_map[pos_num] = r
    return rect_pos_map, list(range(len(rect_angles_sorted)))

def visualize_results(img, rects, most_tilted, rect_pos_map, positions, output_path):
    for r in rects:
        color = (0,0,255) if r['i'] == most_tilted['i'] else (0,255,0)
        cv2.polylines(img, [r['box']], True, color, 2)
        cv2.putText(img, f"{r['i']}: {round(r['angle'],1)}", tuple(map(int, r['center'])), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0), 1)
    for pos_num in range(len(positions)):
        r = rect_pos_map[pos_num]
        cx, cy = map(int, r['center'])
        cv2.putText(img, str(pos_num), (cx, cy-15), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, img)

def get_most_tilted(image_path) -> int | None:
    img, thresh, _ = load_and_preprocess_image(image_path)
    # Adjust area threshold based on image size
    img_area = img.shape[0] * img.shape[1]
    area_thresh = max(500, int(img_area * 0.008))
    filtered2_sorted = find_and_filter_contours(thresh, area_thresh=area_thresh)
    rects2 = extract_rect_features(filtered2_sorted)
    if not rects2:
        return None
    most_tilted2 = max(rects2, key=lambda x: x['tilt_vert'])
    tilt_vert = most_tilted2['tilt_vert']

    if tilt_vert < 5:
        return None
    rect_pos_map, positions = assign_positions(rects2, img.shape)
    # Find which position number maps to the most tilted rectangle
    for pos_num, r in rect_pos_map.items():
        if r['i'] == most_tilted2['i']:
            return pos_num
    return None

def solve(folder_path, screenshot_count):
    # Iterate through all screenshots
    for i in reversed(range(screenshot_count)):
        img_path = f"{folder_path}/screenshot_{i:03d}.png"
        dir = get_most_tilted(img_path)
        if dir is not None:
            return dir
    else:
        return None
    
def test():
    screenshot_count = 11
    folder_name = "captcha_screenshots"

    # Go through screenshots from last to first
    for i in reversed(range(screenshot_count)):
        screenshot_path = f"{folder_name}/screenshot_{i:03d}.png"
        log_index = get_most_tilted(screenshot_path)
        if log_index is not None:
            print(f"Most tilted ({log_index}) found in: {screenshot_path}")
            break

    if log_index is None:
        print("Failed to solve captcha: No tilted log found.")
        exit(1)

    
def main():
    img, thresh, closed = load_and_preprocess_image('captcha_screenshots/20250803_181211_attempt1/screenshot_053.png')
    # Adjust area threshold based on image size
    img_area = img.shape[0] * img.shape[1]
    area_thresh = max(500, int(img_area * 0.008))  # Scale threshold with image size
    filtered2_sorted = find_and_filter_contours(thresh, area_thresh=area_thresh)
    rects2 = extract_rect_features(filtered2_sorted)
    if not rects2:
        print("No rectangles found. Try adjusting the area threshold.")
        return
    most_tilted2 = max(rects2, key=lambda x: x['tilt_vert'])
    rect_pos_map, positions = assign_positions(rects2, img.shape)
    print("Rectangle to position mapping:")
    for pos_num in positions:
        print(f"{pos_num}: index={rect_pos_map[pos_num]['i']}, center={rect_pos_map[pos_num]['center']}")
    df = pd.DataFrame([{'Index':r['i'],
                        'Center':tuple(map(lambda v: round(v,2), r['center'])),
                        'Angle':round(r['angle'],2),
                        'AngleNorm':round(r['angle_norm'],2),
                        'AngleHoriz':round(r['angle_horiz'],2),
                        'TiltVert':round(r['tilt_vert'],2)} for r in rects2])
    print(df)
    print(most_tilted2)
    visualize_results(img, rects2, most_tilted2, rect_pos_map, positions, './rects_visualization.png')

if __name__ == "__main__":
    main()

