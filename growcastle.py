import sys
import argparse
try:
    import pyautogui
except ImportError:
    print("Error: pyautogui module not found. Install with 'pip install pyautogui'.")
    sys.exit(1)

import random
import time

# Coordinates
archers = [(316, 577), (316, 738)]
heroes = [(537, 546), (640, 546), (750, 546), (537, 431), (640, 431), (750, 431), (537, 302), (640, 302), (750, 302)]
upgrades = [(1442, 218), (1440, 348)]
battle_switch = (1755, 939)

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

def main(no_upgrades=False):
    n_wave = 0
    won = False
    while True:
        pixel_color = pyautogui.pixel(1755, 939)
        
        if pixel_color == hex_to_rgb(BATTLE_HEX):
            # Battle mode
            target = random.choice(heroes + archers)
            click_pos = with_offset(target)
            pyautogui.click(*click_pos)
            if is_boss_present():
                max_skill_sleep_time = 0.1
            else: 
                max_skill_sleep_time = 1
            time.sleep(random.uniform(0, max_skill_sleep_time))
        elif pixel_color == hex_to_rgb(MENU_HEX):
            # Reset won
            if won:
                print("VICTORY")
            else:
                print("DEFEAT")
            won = False

            sleep_quick()
            # Upgrade mode
            if no_upgrades:
                # Skip upgrades, just switch back to battle
                switch_pos = with_offset(battle_switch)
                pyautogui.click(*switch_pos)
            else:
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

            n_wave = n_wave + 1
            print("Wave " + str(n_wave) + " started")

            # Exponential distribution - higher numbers exponentially less likely
            time.sleep(min(120, random.expovariate(0.5) + 4))
        else:
            pixel_color = pyautogui.pixel(209, 315)
            if pixel_color == hex_to_rgb(0x10FF00):
                won = True
            time.sleep(0.1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Grow Castle automation bot')
    parser.add_argument('--no-upgrades', action='store_true', 
                       help='Skip upgrade actions and only perform battle actions')
    args = parser.parse_args()
    
    main(no_upgrades=args.no_upgrades)
