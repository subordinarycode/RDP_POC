import io
import json
import pyautogui
import threading
from os import name
from PIL import ImageGrab
from src.Netcat import Netcat
import time
from pynput import keyboard, mouse
import pyperclip

IP = "127.0.0.1"
PORT = 4444
VIDEO_PORT = 4445


class IdleDetector:
    def __init__(self, idle_threshold_seconds=60):
        self.idle_threshold_seconds = idle_threshold_seconds
        self.last_activity_time = time.time()
        self.idle = False

        self.mouse_listener = mouse.Listener(on_move=self.on_activity, on_click=self.on_activity)
        self.keyboard_listener = keyboard.Listener(on_press=self.on_activity)

    def start(self):
        self.mouse_listener.start()
        self.keyboard_listener.start()

    def on_activity(self, *args):
        self.last_activity_time = time.time()
        if self.idle:
            print("System is no longer idle")
        self.idle = False

    def check_idle_status(self):
        current_time = time.time()
        if current_time - self.last_activity_time > self.idle_threshold_seconds and not self.idle:
            print("System is now idle")
            self.idle = True

        return self.idle


class RdpClient:
    def __init__(self, nc, video_uid, conn_uid):
        self.conn = nc
        self.uid = conn_uid
        self.video_uid = video_uid
        self.input_blocked = False
        self.video_capture_thread = None
        self.video_capture_running = False

        self.keyboard_listener = None
        self.mouse_listener = None


        self.jiggle_thread = None
        self.jiggler_running = False

    def block_input(self):
        if not self.input_blocked:
            self.keyboard_listener = keyboard.Listener(suppress=True)
            self.mouse_listener = mouse.Listener(suppress=True)
            self.keyboard_listener.start()
            self.mouse_listener.start()
            self.input_blocked = True

    def unblock_input(self):
        if self.input_blocked:
            self.keyboard_listener.stop()
            self.mouse_listener.stop()
            self.input_blocked = False

    def start_video_capture(self):
        if not self.video_capture_running:
            self.video_capture_running = True
            self.video_capture_thread = threading.Thread(target=self._grab_desktop_image)
            self.video_capture_thread.daemon = True
            self.video_capture_thread.start()

    def stop_video_capture(self):
        if self.video_capture_thread:
            self.video_capture_running = False
            self.video_capture_thread.join()
            self.video_capture_thread = None

    def start_jiggler(self):
        if not self.jiggler_running:
            self.jiggler_running = True
            self.jiggle_thread = threading.Thread(target=self._jiggle_mouse)
            self.jiggle_thread.daemon = True
            self.jiggle_thread.start()

    def _jiggle_mouse(self):
        idle_detector = IdleDetector()
        idle_detector.start()
        while self.jiggler_running:
            if idle_detector.check_idle_status():
                # Get current mouse position
                original_x, original_y = pyautogui.position()
                pyautogui.moveTo(original_x + 1, original_y)  # Move 1 pixel to the right
                pyautogui.moveTo(original_x, original_y)  # Move back to original position
            time.sleep(60)

    def _grab_desktop_image(self):
        while self.video_capture_running:
            image = ImageGrab.grab()
            # Convert the image to bytes
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='JPEG')  # Adjust format as needed
            img_bytes = img_bytes.getvalue()

            self.conn.send(self.video_uid, img_bytes)
        self.conn.close_conn(self.video_uid)

    def listen_for_instructions(self):

        while self.video_capture_running:

            data = self.conn.recv(self.uid).decode()
            if not data:
                break

            try:
                data = json.loads(data)
            except json.decoder.JSONDecodeError:
                print(f"[ERROR] Json decode error on message: {data}")
                continue

            mouse_button = data.get("mouse_button")
            key = data.get("key")
            blocking_status = data.get("block_input")
            clipboard_content = data.get("clipboard")
            dy = data.get("dy")

            # Add 100 so the mouse actually scrollz
            if dy:
                if dy > 0:
                    dy = dy + 100
                else:
                    dy = + -100

                pyautogui.scroll(dy)

            if clipboard_content:
                pyperclip.copy(clipboard_content)

            if key:
                if "." in key and key != ".":
                    key = key.split(".")[-1].replace("_", "")
                    if key == 'cmd' and name == "nt":
                        key = "win"

                if self.input_blocked:
                    self.unblock_input()
                    pyautogui.press(key)
                    self.block_input()
                else:
                    pyautogui.press(key)

            elif mouse_button:
                if mouse_button == "Button.left":
                    if self.input_blocked:
                        self.unblock_input()
                        pyautogui.click(data.get("x"), data.get("y"))
                        self.block_input()
                    else:
                        pyautogui.click(data.get("x"), data.get("y"))
                elif mouse_button == 'Button.right':
                    if self.input_blocked:
                        self.unblock_input()
                        pyautogui.rightClick(data.get("x"), data.get("y"))
                        self.block_input()
                    else:
                        pyautogui.rightClick(data.get("x"), data.get("y"))


            self.unblock_input() if not blocking_status else self.block_input()

        self.conn.close_conn(self.uid)


def main():
    nc = Netcat()
    conn_uid = nc.connect(IP, PORT)
    if not conn_uid:
        print("[ERROR] Unable to connect to remote server.")
        exit()

    video_conn_uid = nc.connect(IP, VIDEO_PORT)

    rdp_client = RdpClient(nc=nc, video_uid=video_conn_uid, conn_uid=conn_uid)
    rdp_client.start_video_capture()
    rdp_client.start_jiggler()
    rdp_client.listen_for_instructions()
    rdp_client.jiggler_running = False

    nc.close()


if __name__ == "__main__":
    main()

