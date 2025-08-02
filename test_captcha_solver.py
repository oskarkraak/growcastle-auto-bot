"""
This script tests the captcha solver by iterating through a series of screenshots saved in a folder.
"""

import captcha

screenshot_count = 11
folder_name = "captcha_screenshots"

# Go through screenshots from last to first
for i in reversed(range(screenshot_count)):
    screenshot_path = f"{folder_name}/screenshot_{i:03d}.png"
    log_index = captcha.get_most_tilted(screenshot_path)
    if log_index is not None:
        print(f"Most tilted ({log_index}) found in: {screenshot_path}")
        break

if log_index is None:
    print("Failed to solve captcha: No tilted log found.")
    exit(1)
