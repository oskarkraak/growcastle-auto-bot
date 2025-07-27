import sys
import argparse
try:
    import pyautogui
except ImportError:
    print("Error: pyautogui module not found. Install with 'pip install pyautogui'.")
    sys.exit(1)

import random
import time
import os
from datetime import datetime
import captcha

# Coordinates
archers = [(316, 577), (316, 738)]
heroes = [(537, 546), (640, 546), (750, 546), (537, 431), (640, 431), (750, 431), (537, 302), (640, 302), (750, 302)]
upgrades = [(1442, 218), (1440, 348)]
battle_switch = (1755, 939)
captcha_logs = [(1007, 370), (1124, 410), (1172, 532), (1133, 654), (1007, 696), (885, 657), (844, 534), (887, 412)]

MENU_HEX = 0xBFB9AC
BATTLE_HEX = 0x6E6256

# Optional PyAutoGUI settings
pyautogui.FAILSAFE = True  # Move mouse to a corner to abort
pyautogui.PAUSE = 0.1      # Small pause after each PyAutoGUI call

def with_offset(coord, max_offset=40):
    """Apply a random offset to a coordinate."""
    x, y = coord
    return x + random.randint(-max_offset, max_offset), y + random.randint(-max_offset, max_offset)

def hex_to_rgb(hex_value):
    """
    Convert a hex color (e.g., 0xBFB9AC or '#BFB9AC') to an (R, G, B) tuple.
    """
    # Handle string input like '#BFB9AC' or 'BFB9AC'
    if isinstance(hex_value, str):
        hex_value = hex_value.lstrip('#')
        hex_value = int(hex_value, 16)
    
    # Extract RGB components
    r = (hex_value >> 16) & 0xFF
    g = (hex_value >> 8) & 0xFF
    b = hex_value & 0xFF
    return (r, g, b)

def sleep_quick():
    time.sleep(random.uniform(0.2, 0.5))

def is_boss_present():
    pixel_color = pyautogui.pixel(1110, 113)
    return pixel_color == hex_to_rgb(0xE84D4D)

def main(no_upgrades=False, no_solve_captcha=False):
    n_wave = 0
    won = False
    while True:
        battle_button_pixel_color = pyautogui.pixel(1755, 939)
        captcha_diamond_pixel_color = pyautogui.pixel(1010, 532)
        
        if captcha_diamond_pixel_color == hex_to_rgb(0x42C3FF):
            if no_solve_captcha:
                time.sleep(1)
                continue
            print("Solving captcha")

            pyautogui.click(*with_offset((1428, 841)))
            # Create folder for screenshots
            folder_name = f"captcha_screenshots/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.makedirs(folder_name, exist_ok=True)

            # Take screenshots for 3 seconds continuously
            start_time = time.time()
            screenshot_count = 0
            while time.time() - start_time < 3:
                screenshot = pyautogui.screenshot(region=(766, 272, 500, 500))  # x, y, width, height around captcha area
                screenshot.save(f"{folder_name}/screenshot_{screenshot_count:03d}.png")
                screenshot_count += 1
                # No sleep to achieve faster capture rate
                # The actual rate will be limited by screenshot and save

            # Go through screenshots from last to first
            for i in reversed(range(screenshot_count)):
                screenshot_path = f"{folder_name}/screenshot_{i:03d}.png"
                log_index = captcha.get_most_tilted(screenshot_path)
                if log_index is not None:
                    print(f"Most tilted log (number {log_index} clockwise) found in: {screenshot_path}")
                    break
            
            if log_index is None:
                print("Failed to solve captcha: No tilted log found.")
                exit(1)

            target = captcha_logs[log_index]
            click_pos = with_offset(target)
            pyautogui.moveTo(*click_pos)
            time.sleep(random.uniform(1, 2))
            pyautogui.click(*click_pos)

            sleep_quick()
        elif battle_button_pixel_color == hex_to_rgb(BATTLE_HEX):
            # Battle mode
            target = random.choice(heroes + archers)
            click_pos = with_offset(target)
            pyautogui.click(*click_pos)
            if is_boss_present():
                max_skill_sleep_time = 0.1
            else: 
                max_skill_sleep_time = 1
            time.sleep(random.uniform(0, max_skill_sleep_time))
        elif battle_button_pixel_color == hex_to_rgb(MENU_HEX):
            # Reset won
            if won:
                print("VICTORY")
            else:
                print("DEFEAT")
            won = False

            # Exponential distribution - higher numbers exponentially less likely
            time.sleep(min(60, random.expovariate(0.5)))

            # Upgrade mode
            if not no_upgrades:
                target = random.choice(heroes + upgrades)
                click_pos = with_offset(target)
                
                if target in heroes:
                    # Hero was chosen - additional hero-specific actions can go here
                    pyautogui.click(*click_pos)
                    sleep_quick()         
                    pyautogui.moveTo(*with_offset((1304, 660)))
                    pyautogui.mouseDown()
                    time.sleep(random.uniform(2, 3.5))
                    pyautogui.mouseUp()
                    sleep_quick()         
                    pyautogui.click(*with_offset((1488, 258)))
                    sleep_quick()         
                    pyautogui.click(*with_offset((1827, 144)))
                    sleep_quick()         
                else:
                    # Upgrade was chosen - additional upgrade-specific actions can go here
                    pyautogui.moveTo(*click_pos)
                    sleep_quick()
                    pyautogui.mouseDown()
                    time.sleep(random.uniform(2, 3.5))
                    pyautogui.mouseUp()
                    sleep_quick()         

            # Switch back to battle mode
            switch_pos = with_offset(battle_switch)
            pyautogui.click(*switch_pos)

            # Military Band (F) ability
            sleep_quick()
            pyautogui.click(*with_offset((1342, 334)))
            sleep_quick()
            pyautogui.click(*with_offset((751, 163)))
            sleep_quick()

            n_wave = n_wave + 1
            print("Wave " + str(n_wave) + " started")
        else:
            battle_button_pixel_color = pyautogui.pixel(209, 315)
            if battle_button_pixel_color == hex_to_rgb(0x10FF00):
                won = True
            time.sleep(0.1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Grow Castle automation bot')
    parser.add_argument('--no-upgrades', action='store_true', 
                       help='Skip upgrade actions and only perform battle actions')
    parser.add_argument('--no-solve-captcha', action='store_true',
                       help='Skip solving captchas (bot will wait if captcha appears)')
    args = parser.parse_args()
    
    main(no_upgrades=args.no_upgrades, no_solve_captcha=args.no_solve_captcha)
