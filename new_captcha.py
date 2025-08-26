import cv2, numpy as np
import math

def crop_image(img, top:int, right: int, bottom: int, left: int):
    height, width = img.shape[:2]
    cropped_img = img[top:height-bottom, left:width-right]
    return cropped_img

def solve_captcha(path1: str, path2: str, debug: bool=False):
    from pathlib import Path
    from matplotlib import pyplot as plt

    # Load the two screenshots
    im1 = cv2.imread(path1)
    im2 = cv2.imread(path2)
    if im1 is None or im2 is None:
        raise FileNotFoundError("One of the screenshots not found")

    # Crop to make sure 
    im1 = crop_image(im1, 0, 25, 50, 25)
    im2 = crop_image(im2, 0, 25, 50, 25)

    # Ensure same size
    h, w = im1.shape[:2]
    im2 = cv2.resize(im2, (w,h))

    # Compute absolute difference
    diff = cv2.absdiff(im1, im2)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

    # Threshold the difference
    _, thresh = cv2.threshold(diff_gray, 25, 255, cv2.THRESH_BINARY)

    # Morphological cleanup
    kernel = np.ones((5,5), np.uint8)
    thresh_clean = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    thresh_clean = cv2.morphologyEx(thresh_clean, cv2.MORPH_DILATE, kernel, iterations=1)

    # Find contours of differences
    contours, _ = cv2.findContours(thresh_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Find the largest contour (biggest change)
    largest = None
    max_area = 0
    for c in contours:
        area = cv2.contourArea(c)
        if area > max_area:
            max_area = area
            largest = c

    vis = im2.copy()
    if largest is None:
        return (None, 0)
    #if max_area 
        
    x,y,wc,hc = cv2.boundingRect(largest)
    cv2.rectangle(vis, (x,y), (x+wc,y+hc), (0,0,255), 2)
    cv2.putText(vis, f"Changed area", (x,y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2)

    if debug:
        # Save output images
        base = Path("")
        cv2.imwrite(str(base/"difference_map.png"), diff_gray)
        cv2.imwrite(str(base/"difference_mask.png"), thresh_clean)
        cv2.imwrite(str(base/"difference_annotated.png"), vis)

    cx = x + wc // 2
    cy = y + hc // 2

    # Image center
    center_x, center_y = w // 2, h // 2

    # Calculate relative position
    dx = cx - center_x
    dy = cy - center_y

    # Determine direction based on angle
    angle = math.atan2(dy, dx)

    # Convert to 8-direction index (0-7)
    # Add pi/8 to shift boundaries, then divide by pi/4 for 8 sectors
    direction_index = int((angle + math.pi + math.pi/8) / (math.pi/4)) % 8

    direction_index_starting_from_top = (direction_index-2+8)%8
    return (direction_index_starting_from_top, max_area)


def actually_solve(folder_path, screenshot_count):
    # Iterate through all screenshots
    for i in reversed(range(0, screenshot_count-1)):
        img1_path = f"{folder_path}/screenshot_{i:03d}.png"
        img2_path = f"{folder_path}/screenshot_{i+1:03d}.png"
        dir, confidence = solve_captcha(img1_path, img2_path)
        if confidence > 500:
            return dir
    else:
        return None


def test(folder_name, screenshot_count):
    # Iterate through all screenshots
    for i in reversed(range(0, screenshot_count-1)):
        img1_path = f"{folder_name}/screenshot_{i:03d}.png"
        img2_path = f"{folder_name}/screenshot_{i+1:03d}.png"
        dir, confidence = solve_captcha(img1_path, img2_path)
        print(f"Direction for screenshot {i}: {dir}, Confidence: {confidence}")


if __name__ == "__main__":
    screenshot_count = 140
    folder_name = "TODO captcha fail/20250813_200634_attempt1"
    #folder_name = "TODO captcha fail/20250813_200648_attempt2"
    test(folder_name, screenshot_count)
    dir = actually_solve(folder_name, screenshot_count)
    print("Result: ", dir)
