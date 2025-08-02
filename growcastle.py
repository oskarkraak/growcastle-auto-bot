import sys
import argparse
import json
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


# Config file path
CONFIG_PATH = "config.json"

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"Config file '{CONFIG_PATH}' not found. Please run with --setup-config to create it.")
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def setup_config(add_mode=False):
    print("=== Grow Castle Bot Config Setup ===")
    print("You will be prompted to click on various points in the game window. Move your mouse to the requested location and press Enter.")
    # Load existing config if present, else start new
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
    else:
        config = {}

    if add_mode:
        print("=== Add to menu_upgrades and abilities ===")
        for key, desc in [("menu_upgrades", "menu upgrade positions"), ("abilities", "ability positions")]:
            if key not in config or not isinstance(config[key], list):
                config[key] = []
            print(f"Now adding to: {desc}")
            while True:
                val = input("Move mouse to point and press Enter, or type 'done' to finish: ")
                if val.strip().lower() == 'done':
                    break
                x, y = pyautogui.position()
                config[key].append([x, y])
                print(f"Added: {x}, {y}")
        save_config(config)
        print(f"Config saved to {CONFIG_PATH}.")
        print("You can now run the bot normally.")
        sys.exit(0)

    stages = [
        {"name": "battle_button", "desc": "Golden horn button (when in battle mode)"},
        {"name": "menu_button", "desc": "Battle button (when in main menu)"},
        {"name": "captcha_diamond", "desc": "Captcha diamond (when captcha is visible)"},
        {"name": "win_panel", "desc": "Any green pixel on the victory panel on the top left after winning a wave (for win detection)"},
        {"name": "boss_pixel", "desc": "A red pixel on the boss health bar (for boss detection)"},
        {"name": "close_popup", "desc": "Popup close button position (for closing the popup at the start of a wave)"},
        {"name": "military_band_f", "desc": "Military Band (F) ability target position (click to use ability)"},
        {"name": "hero_upgrade_button", "desc": "Hero upgrade button position (hold to upgrade hero)"},
        {"name": "hero_window_close1", "desc": "First hero window close button position (after upgrade)"},
        {"name": "hero_window_close2", "desc": "Second hero window close button position (final close)"},
    ]

    # Dynamic points for logs, upgrades, and abilities
    dynamic_points = [
        {"name": "captcha_logs", "desc": "Captcha log positions (click each log in order, press Enter after each, type 'done' when finished)", "multi": True},
        {"name": "one_click_upgrades", "desc": "One-click upgrade positions (click each, press Enter after each, type 'done' when finished)", "multi": True},
        {"name": "menu_upgrades", "desc": "Menu upgrade positions (click each, press Enter after each, type 'done' when finished)", "multi": True},
        {"name": "abilities", "desc": "Ability positions (click each, press Enter after each, type 'done' when finished)", "multi": True},
        {"name": "battle_switch", "desc": "Battle switch button (for switching back to battle mode)", "multi": False},
    ]

    # Single points
    for stage in stages:
        if stage["name"] in config and config[stage["name"]]:
            print(f"{stage['name']} already set, skipping.")
            continue
        input(f"Move mouse to {stage['desc']} and press Enter...")
        x, y = pyautogui.position()
        color = pyautogui.pixel(x, y)
        config[stage["name"]] = {"coord": [x, y], "color": color}
        print(f"Recorded {stage['name']}: {x}, {y}, color: {color}")

    # Dynamic points
    for dp in dynamic_points:
        if dp["name"] in config and config[dp["name"]]:
            print(f"{dp['name']} already set, skipping.")
            continue
        points = []
        if dp.get("multi"):
            print(f"Now setting up: {dp['desc']}")
            while True:
                val = input("Move mouse to point and press Enter, or type 'done' to finish: ")
                if val.strip().lower() == 'done':
                    break
                x, y = pyautogui.position()
                points.append([x, y])
                print(f"Recorded: {x}, {y}")
            config[dp["name"]] = points
        else:
            input(f"Move mouse to {dp['desc']} and press Enter...")
            x, y = pyautogui.position()
            config[dp["name"]] = [x, y]
            print(f"Recorded: {x}, {y}")

    save_config(config)
    print(f"Config saved to {CONFIG_PATH}.")
    print("You can now run the bot normally.")
    sys.exit(0)

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
    config = load_config()
    boss_pixel = config.get("boss_pixel")
    x, y = boss_pixel["coord"]
    expected_color = tuple(boss_pixel["color"])
    pixel_color = pyautogui.pixel(x, y)
    return pixel_color == expected_color


def main(no_upgrades=False, no_solve_captcha=False, captcha_retry_attempts=3):
    config = load_config()
    one_click_upgrades = config["one_click_upgrades"]
    menu_upgrades = config["menu_upgrades"]
    abilities = config["abilities"]
    battle_switch = config["battle_switch"]
    captcha_logs = config["captcha_logs"]
    battle_button = config["battle_button"]
    menu_button = config["menu_button"]
    captcha_diamond = config["captcha_diamond"]
    win_panel = config["win_panel"]
    close_popup = config["close_popup"]
    military_band_f = config["military_band_f"]
    hero_upgrade_button = config["hero_upgrade_button"]
    hero_window_close1 = config["hero_window_close1"]
    hero_window_close2 = config["hero_window_close2"]

    n_wave = 0
    won = False
    captcha_attempt = 0
    while True:
        battle_button_pixel_color = pyautogui.pixel(*battle_button["coord"])
        menu_button_pixel_color = pyautogui.pixel(*menu_button["coord"])
        captcha_diamond_pixel_color = pyautogui.pixel(*captcha_diamond["coord"])

        if captcha_diamond_pixel_color == tuple(captcha_diamond["color"]):
            if no_solve_captcha:
                time.sleep(1)
                continue
            captcha_attempt += 1
            if captcha_attempt > captcha_retry_attempts:
                print(f"Captcha solving failed after {captcha_retry_attempts} attempts. Exiting.")
                exit(1)
            print(f"Solving captcha (attempt {captcha_attempt})")

            # Click diamond (use offset from config if needed)
            pyautogui.click(*with_offset(tuple(captcha_diamond["coord"])))
            # Create folder for screenshots
            folder_name = f"captcha_screenshots/{datetime.now().strftime('%Y%m%d_%H%M%S')}_attempt{captcha_attempt}"
            os.makedirs(folder_name, exist_ok=True)

            # Take screenshots for 3 seconds continuously
            start_time = time.time()
            screenshot_count = 0
            # Use region around diamond, or default
            region = (captcha_diamond["coord"][0] - 244, captcha_diamond["coord"][1] - 260, 500, 500)
            while time.time() - start_time < 3:
                screenshot = pyautogui.screenshot(region=region)
                screenshot.save(f"{folder_name}/screenshot_{screenshot_count:03d}.png")
                screenshot_count += 1

            # Go through screenshots from last to first
            log_index = None
            for i in reversed(range(screenshot_count)):
                screenshot_path = f"{folder_name}/screenshot_{i:03d}.png"
                log_index = captcha.get_most_tilted(screenshot_path)
                if log_index is not None:
                    print(f"Most tilted log (number {log_index} clockwise) found in: {screenshot_path}")
                    break

            if log_index is None:
                print("Failed to solve captcha: No tilted log found. Random log selected.")
                log_index = random.randint(0, len(captcha_logs) - 1)

            target = captcha_logs[log_index]
            click_pos = with_offset(tuple(target))
            pyautogui.moveTo(*click_pos)
            time.sleep(random.uniform(1, 2))
            pyautogui.click(*click_pos)

            sleep_quick()
        elif battle_button_pixel_color == tuple(battle_button["color"]):
            if captcha_attempt > 0:
                captcha_attempt = 0
                print("Captcha solved")

            # Battle mode: use abilities
            if abilities:
                target = random.choice(abilities)
                click_pos = with_offset(tuple(target))
                pyautogui.click(*click_pos)
            if is_boss_present():
                max_skill_sleep_time = 0.1
            else:
                max_skill_sleep_time = 1
            time.sleep(random.uniform(0, max_skill_sleep_time))
        elif menu_button_pixel_color == tuple(menu_button["color"]):
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
                # Choose randomly between one_click_upgrades and menu_upgrades
                upgrade_type = random.choice(["one_click", "menu"])
                if upgrade_type == "one_click" and one_click_upgrades:
                    target = random.choice(one_click_upgrades)
                    click_pos = with_offset(tuple(target))
                    pyautogui.moveTo(*click_pos)
                    sleep_quick()
                    pyautogui.mouseDown()
                    time.sleep(random.uniform(3, 4.5))
                    pyautogui.mouseUp()
                    sleep_quick()
                elif upgrade_type == "menu" and menu_upgrades:
                    target = random.choice(menu_upgrades)
                    click_pos = with_offset(tuple(target))
                    pyautogui.moveTo(*click_pos)
                    sleep_quick()
                    pyautogui.mouseDown()
                    time.sleep(random.uniform(3, 4.5))
                    pyautogui.mouseUp()
                    sleep_quick()

                    # Hero upgrade sequence (configurable)
                    sleep_quick()
                    pyautogui.moveTo(*with_offset(tuple(hero_upgrade_button["coord"])))
                    pyautogui.mouseDown()
                    time.sleep(random.uniform(3, 4.5))
                    pyautogui.mouseUp()
                    sleep_quick()
                    pyautogui.click(*with_offset(tuple(hero_window_close1["coord"])))
                    sleep_quick()
                    pyautogui.click(*with_offset(tuple(hero_window_close2["coord"])))
                    sleep_quick()

            # Switch back to battle mode
            switch_pos = with_offset(tuple(battle_switch))
            pyautogui.click(*switch_pos)
            time.sleep(random.uniform(2, 3))

            # Close popup if present, then use Military Band (F) ability (now configurable)
            pyautogui.click(*with_offset(tuple(close_popup["coord"])))
            sleep_quick()
            pyautogui.click(*with_offset(tuple(military_band_f["coord"])))
            sleep_quick()

            n_wave = n_wave + 1
            print("Wave " + str(n_wave) + " started")
        else:
            win_panel_pixel_color = pyautogui.pixel(*win_panel["coord"])
            if win_panel_pixel_color == tuple(win_panel["color"]):
                won = True
            time.sleep(0.1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Grow Castle automation bot')
    parser.add_argument('--no-upgrades', action='store_true', 
                       help='Skip upgrade actions and only perform battle actions')
    parser.add_argument('--no-solve-captcha', action='store_true',
                       help='Skip solving captchas (bot will wait if captcha appears)')
    parser.add_argument('--captcha-retry-attempts', type=int, default=3,
                       help='Number of retry attempts for solving captcha (default: 3)')
    parser.add_argument('--setup', action='store_true',
                       help='Run interactive setup to create/update config file')
    parser.add_argument('--setup-add', action='store_true',
                       help='Add new points to menu_upgrades and abilities')
    args = parser.parse_args()

    if args.setup:
        setup_config()
    elif args.setup_add:
        setup_config(add_mode=True)

    main(no_upgrades=args.no_upgrades, no_solve_captcha=args.no_solve_captcha, captcha_retry_attempts=args.captcha_retry_attempts)
