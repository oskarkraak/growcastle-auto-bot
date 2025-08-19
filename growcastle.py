import sys
import argparse
import json


import random
import time
import os
from datetime import datetime
import captcha
import subprocess
import tempfile
from PIL import Image
import matplotlib.pyplot as plt
import signal
import threading


# --- ADB Utility Functions ---
# Reuse connection for faster commands
_adb_connection = None
STATUS_ENABLED = False
INSTANCE_NAME = None
PAUSED = False

def emit_status(state, **kwargs):
    """Emit a single-line, machine-readable status event for dashboard consumption.
    Prints lines prefixed with __STATUS__ followed by a JSON object. No effect unless --status is enabled.
    """
    if not STATUS_ENABLED:
        return
    payload = {
        "ts": time.time(),
        "name": INSTANCE_NAME or ADB_DEVICE,
        "device": ADB_DEVICE,
        "state": state,
    }
    payload.update(kwargs or {})
    try:
        print(f"__STATUS__ {json.dumps(payload, separators=(',', ':'))}", flush=True)
    except Exception:
        # Fallback to avoid breaking main flow if serialization fails
        pass

def get_adb_connection():
    global _adb_connection
    if _adb_connection is None or _adb_connection.poll() is not None:
        # Start persistent shell connection
        _adb_connection = subprocess.Popen(
            ["adb", "-s", ADB_DEVICE, "shell"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0
        )
    return _adb_connection

def adb_shell(cmd):
    result = subprocess.run(["adb", "-s", ADB_DEVICE, "shell"] + cmd, capture_output=True, text=True)
    return result.stdout.strip()

def adb_tap(x, y):
    start_time = time.time()
    subprocess.run(["adb", "-s", ADB_DEVICE, "shell", "input", "tap", str(int(x)), str(int(y))])
    elapsed_time = time.time() - start_time
    print(f"adb_tap took {elapsed_time:.3f} seconds")

def adb_tap_fast(x, y):
    """Ultra-fast tap with safety checks to prevent random clicks"""
    global _adb_connection
    start_time = time.time()
    #print(f"DEBUG: About to tap at ({x}, {y})")
    
    try:
        conn = get_adb_connection()
        if conn and conn.stdin and conn.poll() is None:
            # Check if connection is still alive before using it
            cmd = f"input tap {int(x)} {int(y)}\n"
            conn.stdin.write(cmd)
            conn.stdin.flush()
            # Small delay to ensure command is processed
            time.sleep(0.02)
            elapsed_time = time.time() - start_time
            print(f"adb_tap_fast took {elapsed_time:.3f} seconds")
            return
        else:
            # Connection is dead, reset it
            _adb_connection = None
            print("DEBUG: Connection reset, using fallback")
    except Exception as e:
        print(f"DEBUG: Fast tap failed: {e}, using fallback")
        # Reset connection on any error
        _adb_connection = None
    
    # Fallback to reliable direct method
    subprocess.run(["adb", "-s", ADB_DEVICE, "shell", "input", "tap", str(int(x)), str(int(y))], 
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elapsed_time = time.time() - start_time
    print(f"adb_tap_fast (fallback) took {elapsed_time:.3f} seconds")

def adb_screenshot(path):
    # Use exec-out for faster screenshot
    with open(path, 'wb') as f:
        subprocess.run(["adb", "-s", ADB_DEVICE, "exec-out", "screencap", "-p"], stdout=f)

def get_pixel_color(img_path, x, y):
    img = Image.open(img_path).convert("RGB")
    return img.getpixel((int(x), int(y)))

def adb_swipe(x1, y1, x2, y2, duration_ms=300):
    subprocess.run(["adb", "-s", ADB_DEVICE, "shell", "input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(duration_ms))])

def show_screenshot_and_get_click(img_path, prompt):
    img = Image.open(img_path)
    fig, ax = plt.subplots()
    ax.imshow(img)
    plt.title(prompt)
    coords = []
    def onclick(event):
        if event.xdata is not None and event.ydata is not None:
            coords.append((int(event.xdata), int(event.ydata)))
            plt.close()
    fig.canvas.mpl_connect('button_press_event', onclick)
    plt.show()
    if coords:
        return coords[0]
    else:
        return None


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"Config file '{CONFIG_PATH}' not found. Please run with --setup to create it.")
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def setup_config(add_mode=False):
    print("=== Grow Castle Bot Config Setup (ADB Screenshot Mode) ===")
    print("For each requested point, a screenshot of your device will be shown. Click on the correct location in the screenshot window.")
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
    else:
        config = {}

    safe_device = "".join(c for c in ADB_DEVICE if c.isalnum() or c in ('-', '_'))
    screenshot_path = os.path.join(tempfile.gettempdir(), f"growcastle_setup_{safe_device}.png")

    if add_mode:
        print("=== Add to menu_upgrades and abilities ===")
        for key, desc in [("menu_upgrades", "menu upgrade positions"), ("abilities", "ability positions")]:
            if key not in config or not isinstance(config[key], list):
                config[key] = []
            print(f"Now adding to: {desc}")
            while True:
                input("Prepare the screen on your device, then press Enter to take a screenshot...")
                adb_screenshot(screenshot_path)
                print("Click on the desired point in the screenshot window, or close the window to finish.")
                try:
                    x, y = show_screenshot_and_get_click(screenshot_path, f"{desc} (click or close to finish)")
                    config[key].append([x, y])
                    print(f"Added: {x}, {y}")
                except Exception:
                    print("Done adding points.")
                    break
        save_config(config)
        print(f"Config saved to {CONFIG_PATH}.")
        print("You can now run the bot normally.")
        sys.exit(0)

    stages = [
        {"name": "android_home_screen_bottom_right", "desc": "Bottom right of the android home screen (crash detection)"},
        {"name": "android_home_screen_growcastle_icon", "desc": "GrowCastle icon on the android home screen (to start the game)"},
        {"name": "battle_button", "desc": "Golden horn button (when in battle mode)"},
        {"name": "menu_button", "desc": "Battle button (when in main menu)"},
        {"name": "captcha_diamond", "desc": "Captcha diamond (when captcha is visible - for detection only)"},
        {"name": "captcha_start_button", "desc": "Captcha start button (to click when captcha appears)"},
        {"name": "win_panel", "desc": "Any green pixel on the victory panel on the top left after winning a wave (for win detection)"},
        {"name": "boss_pixel", "desc": "A red pixel on the boss health bar (for boss detection)"},
        {"name": "close_popup", "desc": "Popup close button position (for closing the popup at the start of a wave)"},
        {"name": "military_band_f", "desc": "Military Band (F) ability target position (click to use ability)"},
        {"name": "hero_upgrade_button", "desc": "Hero upgrade button position (hold to upgrade hero)"},
        {"name": "hero_window_close1", "desc": "First hero window close button position (after upgrade)"},
        {"name": "hero_window_close2", "desc": "Second hero window close button position (final close)"},
        {"name": "golden_horn_close", "desc": "Golden horn popup close button position"},
    ]

    dynamic_points = [
        {"name": "captcha_logs", "desc": "Captcha log positions (click each log in order, close window when finished)", "multi": True},
        {"name": "captcha_region", "desc": "Captcha logs region (click upper-left corner, then bottom-right corner) - make sure to capture all the logs, but not anything else (no UI elements etc)", "multi": "corners"},
        {"name": "one_click_upgrades", "desc": "One-click upgrade positions (click each, close window when finished)", "multi": True},
        {"name": "menu_upgrades", "desc": "Menu upgrade positions (click each, close window when finished)", "multi": True},
        {"name": "abilities", "desc": "Ability positions (click each, close window when finished)", "multi": True},
        {"name": "battle_switch", "desc": "Battle switch button (for switching back to battle mode)", "multi": False},
    ]

    # Single points
    for stage in stages:
        if stage["name"] in config and config[stage["name"]]:
            print(f"{stage['name']} already set, skipping.")
            continue
        input(f"Prepare the screen for: {stage['desc']}, then press Enter to take a screenshot...")
        adb_screenshot(screenshot_path)
        print(f"Click on the {stage['desc']} in the screenshot window.")
        x, y = show_screenshot_and_get_click(screenshot_path, stage['desc'])
        color = get_pixel_color(screenshot_path, x, y)
        config[stage["name"]] = {"coord": [x, y], "color": color}
        print(f"Recorded {stage['name']}: {x}, {y}, color: {color}")

    # Dynamic points
    for dp in dynamic_points:
        if dp["name"] in config and config[dp["name"]]:
            print(f"{dp['name']} already set, skipping.")
            continue
        points = []
        if dp.get("multi") == "corners":
            print(f"Now setting up: {dp['desc']}")
            print("First, click the upper-left corner of the captcha logs region.")
            input("Prepare the screen for the captcha logs region, then press Enter to take a screenshot...")
            adb_screenshot(screenshot_path)
            x1, y1 = show_screenshot_and_get_click(screenshot_path, "Click upper-left corner of captcha logs region")
            print(f"Upper-left corner: {x1}, {y1}")
            
            print("Now, click the bottom-right corner of the captcha logs region.")
            input("Press Enter to take another screenshot...")
            adb_screenshot(screenshot_path)
            x2, y2 = show_screenshot_and_get_click(screenshot_path, "Click bottom-right corner of captcha logs region")
            print(f"Bottom-right corner: {x2}, {y2}")
            
            config[dp["name"]] = {"upper_left": [x1, y1], "bottom_right": [x2, y2]}
            print(f"Recorded captcha region: ({x1}, {y1}) to ({x2}, {y2})")
        elif dp.get("multi"):
            print(f"Now setting up: {dp['desc']}")
            while True:
                input(f"Prepare the screen for: {dp['desc']}, then press Enter to take a screenshot...")
                adb_screenshot(screenshot_path)
                print("Click on the desired point in the screenshot window, or close the window to finish.")
                try:
                    x, y = show_screenshot_and_get_click(screenshot_path, dp['desc'] + " (click or close to finish)")
                    points.append([x, y])
                    print(f"Recorded: {x}, {y}")
                except Exception:
                    print("Done with this set.")
                    break
            config[dp["name"]] = points
        else:
            input(f"Prepare the screen for: {dp['desc']}, then press Enter to take a screenshot...")
            adb_screenshot(screenshot_path)
            print(f"Click on the {dp['desc']} in the screenshot window.")
            x, y = show_screenshot_and_get_click(screenshot_path, dp['desc'])
            config[dp["name"]] = [x, y]
            print(f"Recorded: {x}, {y}")

    save_config(config)
    print(f"Config saved to {CONFIG_PATH}.")
    print("You can now run the bot normally.")
    sys.exit(0)



def with_offset(coord, max_offset=15):
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
    safe_device = "".join(c for c in ADB_DEVICE if c.isalnum() or c in ('-', '_'))
    screenshot_path = os.path.join(tempfile.gettempdir(), f"growcastle_check_{safe_device}.png")
    adb_screenshot(screenshot_path)
    pixel_color = get_pixel_color(screenshot_path, x, y)
    return pixel_color == expected_color



def check_control_file():
    """Check for pause/unpause command via control file."""
    global PAUSED
    safe_name = "".join(c for c in INSTANCE_NAME if c.isalnum() or c in ('-', '_'))
    control_path = os.path.join(tempfile.gettempdir(), f"growcastle_control_{safe_name}.json")
    if os.path.exists(control_path):
        try:
            with open(control_path, "r") as f:
                data = json.load(f)
            cmd = data.get("command")
            if cmd == "pause" and not PAUSED:
                PAUSED = True
                emit_status("paused")
            elif cmd == "unpause" and PAUSED:
                PAUSED = False
                emit_status("unpaused")
        except Exception:
            pass
        try:
            os.remove(control_path)
        except Exception:
            pass

def main(no_upgrades=False, no_solve_captcha=False, captcha_retry_attempts=3):
    config = load_config()
    android_home_screen_bottom_right = config["android_home_screen_bottom_right"]
    android_home_screen_growcastle_icon = config["android_home_screen_growcastle_icon"]
    one_click_upgrades = config["one_click_upgrades"]
    menu_upgrades = config["menu_upgrades"]
    abilities = config["abilities"]
    battle_switch = config["battle_switch"]
    captcha_logs = config["captcha_logs"]
    captcha_region = config["captcha_region"]
    battle_button = config["battle_button"]
    menu_button = config["menu_button"]
    captcha_diamond = config["captcha_diamond"]
    captcha_start_button = config["captcha_start_button"]
    win_panel = config["win_panel"]
    close_popup = config["close_popup"]
    military_band_f = config["military_band_f"]
    hero_upgrade_button = config["hero_upgrade_button"]
    hero_window_close1 = config["hero_window_close1"]
    hero_window_close2 = config["hero_window_close2"]
    golden_horn_close = config["golden_horn_close"]

    n_wave = 0
    won = False
    captcha_attempt = 0
    no_battle_count = 0
    safe_device = "".join(c for c in ADB_DEVICE if c.isalnum() or c in ('-', '_'))
    screenshot_path = os.path.join(tempfile.gettempdir(), f"growcastle_loop_{safe_device}.png")
    while True:
        check_control_file()
        if PAUSED:
            emit_status("paused")
            time.sleep(0.5)
            continue
        start_time = time.time()
        adb_screenshot(screenshot_path)
        elapsed_time = time.time() - start_time
        print(f"adb_screenshot took {elapsed_time:.3f} seconds")
        android_home_screen_pixel_color = get_pixel_color(screenshot_path, *android_home_screen_bottom_right["coord"])
        battle_button_pixel_color = get_pixel_color(screenshot_path, *battle_button["coord"])
        menu_button_pixel_color = get_pixel_color(screenshot_path, *menu_button["coord"])
        captcha_diamond_pixel_color = get_pixel_color(screenshot_path, *captcha_diamond["coord"])

        if android_home_screen_pixel_color == tuple(android_home_screen_bottom_right["color"]):
            emit_status("home", wave=n_wave, captcha_attempts=captcha_attempt, no_battle=no_battle_count)
            adb_tap_fast(*tuple(android_home_screen_growcastle_icon["coord"]))
        elif captcha_diamond_pixel_color == tuple(captcha_diamond["color"]):
            if no_solve_captcha:
                emit_status("captcha_wait", wave=n_wave, captcha_attempts=captcha_attempt, no_battle=no_battle_count)
                time.sleep(1)
                continue
            captcha_attempt += 1
            if captcha_attempt > captcha_retry_attempts:
                print(f"Captcha solving failed after {captcha_retry_attempts} attempts. Exiting.")
                emit_status("captcha_failed", wave=n_wave, captcha_attempts=captcha_attempt, no_battle=no_battle_count)
                exit(1)
            print(f"Solving captcha (attempt {captcha_attempt})")
            emit_status("captcha_solving", wave=n_wave, captcha_attempts=captcha_attempt, no_battle=no_battle_count)
            
            # Create folder for screenshots
            folder_name = f"captcha_screenshots/{datetime.now().strftime('%Y%m%d_%H%M%S')}_attempt{captcha_attempt}"
            os.makedirs(folder_name, exist_ok=True)

            # Click the captcha start button to initiate the captcha
            adb_tap_fast(*with_offset(tuple(captcha_start_button["coord"])))

            # Start screen recording
            video_path = f"{folder_name}/captcha_recording.mp4"
            recording_process = subprocess.Popen(
                ["adb", "-s", ADB_DEVICE, "shell", "screenrecord", "--time-limit", "7", "/sdcard/captcha_recording.mp4"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            
            # Wait for recording to complete
            recording_process.wait()
            
            # Pull the video file
            subprocess.run(["adb", "-s", ADB_DEVICE, "pull", "/sdcard/captcha_recording.mp4", video_path])
            subprocess.run(["adb", "-s", ADB_DEVICE, "shell", "rm", "/sdcard/captcha_recording.mp4"])
            
            extraction_fps = 40
            import cv2
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_interval = max(1, int(fps / extraction_fps))  # Extract every nth frame to get ~extraction_fps fps
            
            screenshot_count = 0
            frame_num = 0
            # Use the configured captcha region for cropping
            x1, y1 = captcha_region["upper_left"]
            x2, y2 = captcha_region["bottom_right"]
            region = (x1, y1, x2 - x1, y2 - y1)
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                    
                if frame_num % frame_interval == 0:
                    # Convert BGR to RGB and create PIL image
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame_rgb)
                    
                    # Crop to region of interest
                    region_img = img.crop((region[0], region[1], region[0]+region[2], region[1]+region[3]))
                    region_img.save(f"{folder_name}/screenshot_{screenshot_count:03d}.png")
                    screenshot_count += 1
                    
                frame_num += 1
            
            cap.release()
            os.remove(video_path)  # Clean up video file

            # Go through screenshots from last to first
            log_index = None
            for i in reversed(range(screenshot_count)):
                screenshot_file = f"{folder_name}/screenshot_{i:03d}.png"
                log_index = captcha.get_most_tilted(screenshot_file)
                if log_index is not None:
                    print(f"Most tilted log (number {log_index} clockwise) found in: {screenshot_file}")
                    break

            if log_index is None:
                print("Failed to solve captcha: No tilted log found. Random log selected.")
                log_index = random.randint(0, len(captcha_logs) - 1)

            target = captcha_logs[log_index]
            click_pos = with_offset(tuple(target))
            adb_tap(*click_pos)
            time.sleep(random.uniform(1, 2))
            sleep_quick()

            no_battle_count = 0
            emit_status("captcha_clicked", wave=n_wave, captcha_attempts=captcha_attempt, no_battle=no_battle_count, log_index=log_index)
        elif battle_button_pixel_color == tuple(battle_button["color"]):
            if captcha_attempt > 0:
                captcha_attempt = 0
                print("Captcha solved")
                emit_status("captcha_solved", wave=n_wave, captcha_attempts=captcha_attempt, no_battle=no_battle_count)

            # Battle mode: use abilities
            if abilities:
                target = random.choice(abilities)
                click_pos = with_offset(tuple(target))
                #print(f"DEBUG: Using ability at {click_pos}")
                adb_tap_fast(*click_pos)
                sleep_quick()

            no_battle_count = 0
            if is_boss_present():
                emit_status("boss", wave=n_wave, captcha_attempts=captcha_attempt, no_battle=no_battle_count)
            else:
                emit_status("battle", wave=n_wave, captcha_attempts=captcha_attempt, no_battle=no_battle_count)

        elif menu_button_pixel_color == tuple(menu_button["color"]):
            if won:
                print("VICTORY")
                try:
                    emit_status("wave_end", wave=n_wave, outcome="W")
                except Exception:
                    pass
            else:
                print("DEFEAT")
                try:
                    emit_status("wave_end", wave=n_wave, outcome="L")
                except Exception:
                    pass
            won = False

            time.sleep(min(60, random.expovariate(0.5)))

            if not no_upgrades:
                upgrade_type = random.choice(["one_click", "menu"])
                if upgrade_type == "one_click" and one_click_upgrades:
                    target = random.choice(one_click_upgrades)
                    click_pos = with_offset(tuple(target))
                    adb_tap_fast(*click_pos)
                    sleep_quick()
                    adb_swipe(click_pos[0], click_pos[1], click_pos[0], click_pos[1], duration_ms=int(random.uniform(3000, 4500)))
                    sleep_quick()
                elif upgrade_type == "menu" and menu_upgrades:
                    target = random.choice(menu_upgrades)
                    click_pos = with_offset(tuple(target))
                    adb_tap_fast(*click_pos)
                    sleep_quick()
                    adb_swipe(click_pos[0], click_pos[1], click_pos[0], click_pos[1], duration_ms=int(random.uniform(3000, 4500)))
                    sleep_quick()

                    hero_pos = with_offset(tuple(hero_upgrade_button["coord"]))
                    adb_swipe(hero_pos[0], hero_pos[1], hero_pos[0], hero_pos[1], duration_ms=int(random.uniform(3000, 4500)))
                    sleep_quick()
                    adb_tap_fast(*with_offset(tuple(hero_window_close1["coord"])))
                    sleep_quick()
                    adb_tap_fast(*with_offset(tuple(hero_window_close2["coord"])))
                    sleep_quick()

            switch_pos = with_offset(tuple(battle_switch))
            adb_tap_fast(*switch_pos)
            time.sleep(random.uniform(0.5, 1))

            adb_tap_fast(*with_offset(tuple(close_popup["coord"])))
            sleep_quick()
            adb_tap_fast(*with_offset(tuple(military_band_f["coord"])))
            sleep_quick()

            n_wave = n_wave + 1
            print("Wave " + str(n_wave) + " started")
            no_battle_count = 0
            emit_status("menu", wave=n_wave, captcha_attempts=captcha_attempt, no_battle=no_battle_count)
        else:
            win_panel_pixel_color = get_pixel_color(screenshot_path, *win_panel["coord"])
            if win_panel_pixel_color == tuple(win_panel["color"]):
                won = True
            
            no_battle_count += 1
            print(f"No battle mode detected, waiting... (count: {no_battle_count})")
            emit_status("idle", wave=n_wave, captcha_attempts=captcha_attempt, no_battle=no_battle_count)
            
            if no_battle_count >= 5:
                if no_battle_count%2 == 0:
                    print(f"No battle mode detected {no_battle_count} times, attempting to close hero windows...")
                    adb_tap_fast(*with_offset(tuple(hero_window_close1["coord"])))
                    sleep_quick()
                    adb_tap_fast(*with_offset(tuple(hero_window_close2["coord"])))
                    sleep_quick()
                else:
                    print(f"No battle mode detected {no_battle_count} times, attempting to close golden horn window...")
                    adb_tap_fast(*with_offset(tuple(golden_horn_close["coord"])))
                    sleep_quick()

            time.sleep(1)

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
    parser.add_argument('--adb-device', type=str, default='127.0.0.1:5555',
                       help='ADB device serial (default: 127.0.0.1:5555)')
    parser.add_argument('--config', type=str, default='config.json',
                       help='Config file with data from setup (default: config.json)')
    parser.add_argument('--status', action='store_true',
                        help='Emit machine-readable status lines for dashboards (__STATUS__ JSON)')
    parser.add_argument('--name', type=str, default=None,
                        help='Optional friendly name for this instance (defaults to adb device)')
    parser.add_argument('--ignore-sigint', action='store_true',
                        help='Ignore SIGINT (Ctrl+C); useful when managed by a parent dashboard')
    args = parser.parse_args()

    ADB_DEVICE = args.adb_device
    CONFIG_PATH = args.config
    STATUS_ENABLED = bool(args.status)
    INSTANCE_NAME = args.name or args.adb_device

    if args.ignore_sigint:
        try:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        except Exception:
            pass

    # Wait for ADB device to be ready
    print("Connecting...")
    emit_status("connecting")
    adb_device_running = False
    while not adb_device_running:
        try:
            adb_connect = subprocess.run(["adb", "connect", ADB_DEVICE], capture_output=True, text=True)
        except FileNotFoundError:
            msg = "adb executable not found in PATH. Install platform-tools or add adb to PATH."
            print(msg)
            emit_status("error", message=msg)
            time.sleep(2)
            continue

        output = (adb_connect.stdout or "").strip()
        if "connected" in output:
            adb_device_running = True
            print(output)
            emit_status("connected")
        else:
            # Keep retrying; emit connecting or error messages as appropriate
            if output:
                print(output)
                emit_status("connecting", message=output)
            else:
                emit_status("connecting")
            time.sleep(1)

    if args.setup:
        setup_config()
    elif args.setup_add:
        setup_config(add_mode=True)

    try:
        main(no_upgrades=args.no_upgrades, no_solve_captcha=args.no_solve_captcha, captcha_retry_attempts=args.captcha_retry_attempts)
    except KeyboardInterrupt:
        emit_status("stopped")
        raise
