#!/usr/bin/env python3
"""
ADB Screen Controller - Real-time screen mirroring with click forwarding
Continuously takes screenshots from an ADB device and forwards your clicks to it.
"""

import sys
import argparse
import subprocess
import tempfile
import os
import time
import threading
from datetime import datetime
from PIL import Image
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Button
import tkinter as tk
from tkinter import messagebox, ttk
import queue

class ADBController:
    def __init__(self, device="127.0.0.1:5555"):
        self.device = device
        self.running = False
        self.screenshot_path = os.path.join(tempfile.gettempdir(), f"adb_controller_{device.replace(':', '_').replace('.', '_')}.png")
        self.last_screenshot_time = 0
        self.fps_target = 2  # Screenshots per second
        self.click_queue = queue.Queue()
        
    def connect_device(self):
        """Connect to the ADB device"""
        try:
            result = subprocess.run(["adb", "connect", self.device], capture_output=True, text=True, timeout=10)
            output = (result.stdout or "").strip()
            if "connected" in output or "already connected" in output:
                print(f"Connected to {self.device}: {output}")
                return True
            else:
                print(f"Failed to connect to {self.device}: {output}")
                return False
        except FileNotFoundError:
            print("ERROR: adb executable not found in PATH. Install platform-tools or add adb to PATH.")
            return False
        except subprocess.TimeoutExpired:
            print(f"ERROR: Connection to {self.device} timed out")
            return False
        except Exception as e:
            print(f"ERROR: Failed to connect to {self.device}: {e}")
            return False
    
    def check_device_status(self):
        """Check if device is still connected"""
        try:
            result = subprocess.run(["adb", "-s", self.device, "get-state"], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0 and "device" in result.stdout
        except:
            return False
    
    def take_screenshot(self):
        """Take a screenshot from the device"""
        try:
            with open(self.screenshot_path, 'wb') as f:
                result = subprocess.run(["adb", "-s", self.device, "exec-out", "screencap", "-p"], 
                                      stdout=f, timeout=10)
            if result.returncode == 0:
                self.last_screenshot_time = time.time()
                return True
            else:
                print("Screenshot failed")
                return False
        except Exception as e:
            print(f"Screenshot error: {e}")
            return False
    
    def send_tap(self, x, y):
        """Send tap command to device"""
        try:
            subprocess.run(["adb", "-s", self.device, "shell", "input", "tap", str(int(x)), str(int(y))], 
                          timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"Tapped at ({int(x)}, {int(y)})")
            return True
        except Exception as e:
            print(f"Tap error: {e}")
            return False
    
    def send_swipe(self, x1, y1, x2, y2, duration_ms=300):
        """Send swipe command to device"""
        try:
            subprocess.run(["adb", "-s", self.device, "shell", "input", "swipe", 
                          str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(duration_ms))], 
                          timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"Swiped from ({int(x1)}, {int(y1)}) to ({int(x2)}, {int(y2)})")
            return True
        except Exception as e:
            print(f"Swipe error: {e}")
            return False

class MatplotlibController:
    def __init__(self, adb_controller):
        self.adb = adb_controller
        self.fig = None
        self.ax = None
        self.img_display = None
        self.running = False
        self.swipe_start = None
        self.current_image = None
        
    def start_matplotlib_viewer(self):
        """Start the matplotlib-based viewer"""
        print("Starting matplotlib viewer...")
        print("Controls:")
        print("- Left click: Tap")
        print("- Right click + drag: Swipe")
        print("- Press 'q' or close window to quit")
        
        self.fig, self.ax = plt.subplots(figsize=(10, 16))
        self.ax.set_title(f"ADB Screen Controller - {self.adb.device}")
        
        # Remove axes for cleaner look
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        
        # Connect event handlers
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.fig.canvas.mpl_connect('button_release_event', self.on_release)
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)
        self.fig.canvas.mpl_connect('close_event', self.on_close)
        
        # Initial screenshot
        if self.adb.take_screenshot():
            self.update_display()
        
        # Setup animation for continuous updates
        self.ani = animation.FuncAnimation(self.fig, self.animate, interval=500, blit=False)
        
        self.running = True
        plt.show()
    
    def animate(self, frame):
        """Animation function for continuous screenshot updates"""
        if not self.running:
            return
        
        current_time = time.time()
        if current_time - self.adb.last_screenshot_time > (1.0 / self.adb.fps_target):
            if self.adb.check_device_status() and self.adb.take_screenshot():
                self.update_display()
    
    def update_display(self):
        """Update the displayed image"""
        try:
            img = Image.open(self.adb.screenshot_path)
            self.current_image = img
            
            if self.img_display is None:
                self.img_display = self.ax.imshow(img)
            else:
                self.img_display.set_data(img)
            
            self.ax.set_title(f"ADB Screen Controller - {self.adb.device} - {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"Display update error: {e}")
    
    def on_click(self, event):
        """Handle mouse click events"""
        if event.inaxes != self.ax or event.xdata is None or event.ydata is None:
            return
        
        x, y = int(event.xdata), int(event.ydata)
        
        if event.button == 1:  # Left click - tap
            self.adb.send_tap(x, y)
        elif event.button == 3:  # Right click - start swipe
            self.swipe_start = (x, y)
            print(f"Swipe started at ({x}, {y}) - drag to end point")
    
    def on_release(self, event):
        """Handle mouse release events"""
        if event.button == 3 and self.swipe_start and event.inaxes == self.ax:  # Right click release - end swipe
            if event.xdata is not None and event.ydata is not None:
                x, y = int(event.xdata), int(event.ydata)
                x1, y1 = self.swipe_start
                if abs(x - x1) > 10 or abs(y - y1) > 10:  # Only swipe if significant movement
                    self.adb.send_swipe(x1, y1, x, y)
                else:
                    print("Swipe too short, sending tap instead")
                    self.adb.send_tap(x1, y1)
            self.swipe_start = None
    
    def on_key(self, event):
        """Handle keyboard events"""
        if event.key == 'q':
            self.stop()
    
    def on_close(self, event):
        """Handle window close event"""
        self.stop()
    
    def stop(self):
        """Stop the viewer"""
        self.running = False
        if hasattr(self, 'ani'):
            self.ani.event_source.stop()
        plt.close('all')

class TkinterController:
    def __init__(self, adb_controller):
        self.adb = adb_controller
        self.root = None
        self.canvas = None
        self.image_id = None
        self.running = False
        self.swipe_start = None
        self.update_job = None
        
    def start_tkinter_viewer(self):
        """Start the tkinter-based viewer"""
        print("Starting tkinter viewer...")
        print("Controls:")
        print("- Left click: Tap")
        print("- Right click + drag: Swipe")
        print("- Close window to quit")
        
        self.root = tk.Tk()
        self.root.title(f"ADB Screen Controller - {self.adb.device}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Control frame
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(control_frame, text="Device:").pack(side=tk.LEFT)
        ttk.Label(control_frame, text=self.adb.device).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(control_frame, text="Refresh", command=self.force_refresh).pack(side=tk.LEFT)
        ttk.Button(control_frame, text="Home", command=self.send_home).pack(side=tk.LEFT)
        ttk.Button(control_frame, text="Back", command=self.send_back).pack(side=tk.LEFT)
        ttk.Button(control_frame, text="Menu", command=self.send_menu).pack(side=tk.LEFT)
        
        # Canvas for image display
        self.canvas = tk.Canvas(self.root, bg='black')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bind events
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<B3-Motion>", self.on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_right_release)
        
        # Initial screenshot
        if self.adb.take_screenshot():
            self.update_display()
        
        self.running = True
        self.schedule_update()
        self.root.mainloop()
    
    def schedule_update(self):
        """Schedule the next screen update"""
        if self.running:
            if self.adb.check_device_status() and self.adb.take_screenshot():
                self.update_display()
            self.update_job = self.root.after(500, self.schedule_update)  # Update every 500ms
    
    def update_display(self):
        """Update the displayed image"""
        try:
            img = Image.open(self.adb.screenshot_path)
            
            # Resize to fit window while maintaining aspect ratio
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:  # Window is properly sized
                img_width, img_height = img.size
                scale_w = canvas_width / img_width
                scale_h = canvas_height / img_height
                scale = min(scale_w, scale_h, 1.0)  # Don't upscale
                
                new_width = int(img_width * scale)
                new_height = int(img_height * scale)
                
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                from PIL import ImageTk
                self.photo = ImageTk.PhotoImage(img_resized)
                
                # Store scale for click coordinate conversion
                self.display_scale = scale
                self.display_offset_x = (canvas_width - new_width) // 2
                self.display_offset_y = (canvas_height - new_height) // 2
                
                # Update canvas
                self.canvas.delete("all")
                self.image_id = self.canvas.create_image(
                    canvas_width // 2, canvas_height // 2, 
                    image=self.photo
                )
                
                # Update title with timestamp
                self.root.title(f"ADB Screen Controller - {self.adb.device} - {datetime.now().strftime('%H:%M:%S')}")
                
        except Exception as e:
            print(f"Display update error: {e}")
    
    def convert_coordinates(self, display_x, display_y):
        """Convert display coordinates to device coordinates"""
        device_x = (display_x - self.display_offset_x) / self.display_scale
        device_y = (display_y - self.display_offset_y) / self.display_scale
        return int(device_x), int(device_y)
    
    def on_left_click(self, event):
        """Handle left click - send tap"""
        if hasattr(self, 'display_scale'):
            device_x, device_y = self.convert_coordinates(event.x, event.y)
            self.adb.send_tap(device_x, device_y)
    
    def on_right_click(self, event):
        """Handle right click - start swipe"""
        if hasattr(self, 'display_scale'):
            device_x, device_y = self.convert_coordinates(event.x, event.y)
            self.swipe_start = (device_x, device_y)
            print(f"Swipe started at ({device_x}, {device_y})")
    
    def on_right_drag(self, event):
        """Handle right drag - show swipe preview"""
        pass  # Could add visual feedback here
    
    def on_right_release(self, event):
        """Handle right release - send swipe"""
        if self.swipe_start and hasattr(self, 'display_scale'):
            device_x, device_y = self.convert_coordinates(event.x, event.y)
            start_x, start_y = self.swipe_start
            
            if abs(device_x - start_x) > 10 or abs(device_y - start_y) > 10:
                self.adb.send_swipe(start_x, start_y, device_x, device_y)
            else:
                print("Swipe too short, sending tap instead")
                self.adb.send_tap(start_x, start_y)
            
            self.swipe_start = None
    
    def force_refresh(self):
        """Force a screen refresh"""
        if self.adb.take_screenshot():
            self.update_display()
    
    def send_home(self):
        """Send home key"""
        try:
            subprocess.run(["adb", "-s", self.adb.device, "shell", "input", "keyevent", "KEYCODE_HOME"], timeout=5)
        except Exception as e:
            print(f"Home key error: {e}")
    
    def send_back(self):
        """Send back key"""
        try:
            subprocess.run(["adb", "-s", self.adb.device, "shell", "input", "keyevent", "KEYCODE_BACK"], timeout=5)
        except Exception as e:
            print(f"Back key error: {e}")
    
    def send_menu(self):
        """Send menu key"""
        try:
            subprocess.run(["adb", "-s", self.adb.device, "shell", "input", "keyevent", "KEYCODE_MENU"], timeout=5)
        except Exception as e:
            print(f"Menu key error: {e}")
    
    def on_closing(self):
        """Handle window closing"""
        self.running = False
        if self.update_job:
            self.root.after_cancel(self.update_job)
        self.root.destroy()

def main():
    parser = argparse.ArgumentParser(description='ADB Screen Controller - Real-time screen mirroring with click forwarding')
    parser.add_argument('--device', '-d', type=str, default='127.0.0.1:5555',
                       help='ADB device serial (default: 127.0.0.1:5555)')
    parser.add_argument('--ui', choices=['matplotlib', 'tkinter'], default='tkinter',
                       help='UI framework to use (default: tkinter)')
    parser.add_argument('--fps', type=float, default=2,
                       help='Screenshot refresh rate in FPS (default: 2)')
    
    args = parser.parse_args()
    
    print(f"ADB Screen Controller - Device: {args.device}")
    
    # Initialize ADB controller
    adb = ADBController(args.device)
    adb.fps_target = args.fps
    
    # Connect to device
    if not adb.connect_device():
        print("Failed to connect to device. Please check:")
        print("1. ADB is installed and in PATH")
        print("2. Device is connected and USB debugging is enabled")
        print("3. Device address is correct")
        sys.exit(1)
    
    # Check if device responds
    if not adb.check_device_status():
        print("Device is not responding. Please check connection.")
        sys.exit(1)
    
    try:
        if args.ui == 'matplotlib':
            controller = MatplotlibController(adb)
            controller.start_matplotlib_viewer()
        else:  # tkinter
            controller = TkinterController(adb)
            controller.start_tkinter_viewer()
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Cleanup
        try:
            os.remove(adb.screenshot_path)
        except:
            pass
        print("Cleanup complete")

if __name__ == "__main__":
    main()
