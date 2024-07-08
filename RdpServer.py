import threading
from threading import Timer
from src.Netcat import Netcat
from pynput import mouse, keyboard
import json
import time
import pyperclip
from tkinter import Tk, Label, Button, Frame, Toplevel
from PIL import Image, ImageTk
import io


class RdpServer:
    def __init__(self, port, video_port, webcam_port, mic_port):
        # Server setup
        self.nc = Netcat()                                            # Socket connection to handle sending the client instructions
        self.video_nc = Netcat()                                      # Socket connection to handle the video feed
#        self.webcam_nc = Netcat()
#        self.mic_nc = Netcat()

        self.nc.listen(port_number=port, max_clients=1)
        self.video_nc.listen(port_number=video_port, max_clients=1)
#        self.webcam_nc.listen(port_number=webcam_port, max_clients=1)
#        self.mic_nc.listen(port_number=mic_port, max_clients=1)

        # Initial variables
        self.fps = 0
        self.width = 1080
        self.height = 1920
        self.update_interval = 10          # 10 milliseconds

        self.video_uid = None              # Uid of the video socket connection
        self.client_uid = None             # Uid of the communication socket connection
        self.client_window_width = None    # Width of the screenshot sent from the client
        self.client_window_height = None   # Height of the screenshot sent from the client

        self.running = False               # Is the application running
        self.record_mouse = False          # Should we be record the users mouse input to send to the client
        self.blocking_input = False        # Should we be blocking the clients input
        self.record_keyboard = False       # Should we be recording the users keystrokes to send to the client

        # Set listeners for keyboard and mouse events
        self.mouse_listener = mouse.Listener(on_click=self._on_mouse_click, on_scroll=self._on_mouse_scroll)       # when user clicks on the screenshot send to x, y to the clint to preform the click
        self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press)   # When user presses key send key to client for the can preform the key press
        self.mouse_listener.daemon = True
        self.keyboard_listener.daemon = True

        # Tkinter
        self.root = Tk()                                         # Basic tkinter setup
        self.root.title(f"RDP Connection FPS: {self.fps}")
        self.root.geometry(f"{self.height}x{self.width}")
        self.root.bind("<Destroy>", self._on_close)             # Call _on_close when the user closes the window

        # Create image label
        self.label = Label(self.root)                           # Create a label to display the screenshot
        self.label.place(x=0, y=0, relwidth=1, relheight=1)
        self.label.config(anchor='ne')

        self.webcam_label = None
        self.webcam_thread = None
        # Create sidebar
        self.sidebar_frame = Frame(self.root, bg="white", width=150)
        self.sidebar_frame.pack(side='left', fill='y')

        # Toggle mouse button in sidebar
        self.mouse_button = Button(self.sidebar_frame, text="{:18}".format("🔴 Mouse"), command=self._toggle_record_mouse)
        self.mouse_button.pack(padx=2, pady=2, fill='x')

        # Toggle blocking clients input button in sidebar
        self.block_input_button = Button(self.sidebar_frame, text="{:18}".format("  🔴 Block Input"), command=self._toggle_block_input)
        self.block_input_button.pack(padx=2, pady=2, fill='x')

        # Toggle keyboard button in sidebar
        self.keyboard_button = Button(self.sidebar_frame, text="{:18}".format("  🔴 Keyboard"), command=self._toggle_record_keyboard)
        self.keyboard_button.pack(padx=2, pady=2, fill='x')

        # Clipboard button
        self.clipboard_button = Button(self.sidebar_frame, text="{:18}".format("Send Clipboard"), command=self._send_clipboard)
        self.clipboard_button.pack(padx=2, pady=2, fill='x')

    def wait_for_connection(self):
        while not self.client_uid and not self.video_uid:        # Loop until both client_uid and video_uid are assigned
            if len(self.nc.clients) > 0:
                uid = list(self.nc.clients.keys())[0]             # Get the UID of the first client in the clients dictionary
                if self.nc.clients[uid]:                          # Check if the client with this UID is active
                    self.client_uid = uid                         # Assign the UID to self.client_uid

            if len(self.video_nc.clients) > 0:
                uid = list(self.video_nc.clients.keys())[0]
                if self.video_nc.clients[uid]:
                    self.video_uid = uid

            if self.video_uid and self.client_uid:
                break
            time.sleep(0.2)

    def start_display(self):
        self.running = True
        self._recv_screen_capture()
        self.mouse_listener.start()
        self.keyboard_listener.start()
        self.root.mainloop()

    def stop_display(self):
        try:
            self.root.quit()
            # self.root.destroy()
        except:
            pass
        # Stop the display loop and close the Tkinter window
        self.running = False
        self.record_keyboard = False
        self.record_mouse = False

        self.nc.close()
        self.video_nc.close()

    def _mouse_in_window(self, x, y):
        try:
            # Check if mouse coordinates are within the Tkinter window boundaries
            if self.root:
                root_x = self.root.winfo_rootx()
                root_y = self.root.winfo_rooty()
                root_width = self.root.winfo_width()
                root_height = self.root.winfo_height()
                return (root_x <= x < root_x + root_width) and (root_y <= y < root_y + root_height)
        except Exception as e:
            print(f"[ERROR] {e}")
            return None

    def _toggle_block_input(self):
        self.blocking_input = not self.blocking_input
        if self.blocking_input:
            self.block_input_button.config(text="{:18}".format("  🔵 Block Input"))
            self._send_update(None, None, None, None, block_input=True)
        else:
            self.block_input_button.config(text="{:18}".format("  🔴 Block Input"))
            self._send_update(None, None, None, None, block_input=False)

    def _send_clipboard(self):
        # Needs xclip for linux system
        try:
            clipboard_content = pyperclip.paste()
            self._send_update(
                None, None, None, None,
                block_input=self.blocking_input,
                streaming_webcam=self.streaming_webcam,
                streaming_mic=self.streaming_microphone,
                clipboard_content=clipboard_content
            )
        except Exception as e:
            print(f"[ERROR] Error trying to get clipboard content: {e}")

    def _toggle_record_mouse(self):
        self.record_mouse = not self.record_mouse
        if self.record_mouse:
            self.mouse_button.config(text="{:18}".format("🔵 Mouse"))
        else:
            self.mouse_button.config(text="{:18}".format("🔴 Mouse"))

    def _toggle_record_keyboard(self):
        self.record_keyboard = not self.record_keyboard
        if self.record_keyboard:
            self.keyboard_button.config(text="{:18}".format("  🔵 Keyboard"))
        else:
            self.keyboard_button.config(text="{:18}".format("  🔴 Keyboard"))

    def _send_update(self, x, y, mouse_button, key, block_input, clipboard_content="", dx=None, dy=None):
        if self.client_uid:
            if self.client_window_width and self.client_window_height:
                data = {
                    "x": x,
                    "y": y,
                    "dx": dx,
                    "dy": dy,
                    "key": key,
                    "mouse_button": mouse_button,
                    "block_input": block_input,
                    "clipboard": clipboard_content,
                }

                self.blocking_input = block_input

                self.nc.send(self.client_uid, json.dumps(data).encode())

    def _recv_screen_capture(self):
        try:
            if self.running:
                last_time = time.time()
                img_bytes = self.video_nc.recv(self.video_uid)

                if img_bytes:
                    # Open image from bytes and resize it to fit the window
                    image = Image.open(io.BytesIO(img_bytes))
                    self.client_window_width, self.client_window_height = image.size

                    sidebar_width = self.sidebar_frame.winfo_width()
                    window_width = self.root.winfo_width()
                    window_height = self.root.winfo_height()

                    if window_width > sidebar_width:
                        window_width = window_width - sidebar_width

                    image = image.resize((window_width, window_height), Image.LANCZOS)
                    # Convert PIL image to Tkinter-compatible image
                    tk_image = ImageTk.PhotoImage(image)

                    # Update image displayed on the label
                    self.label.config(image=tk_image)
                    self.label.image = tk_image  # Keep a reference
                    self.fps = 1 / (time.time() - last_time)
                    self.root.title(f"RDP Connection FPS: {round(self.fps)}")

                # Schedule the next update
                self.root.after(self.update_interval, self._recv_screen_capture)

        except Exception as e:
            print(f"Error receiving and displaying frame: {e}")

    def _on_mouse_click(self, x, y, button, pressed):
        if self.running:
            if self.record_mouse and pressed and self._mouse_in_window(x, y):

                label_x = self.label.winfo_rootx()
                label_y = self.label.winfo_rooty()
                sidebar_width = self.sidebar_frame.winfo_width()

                # Calculate available width for the image (considering the sidebar)
                window_width = self.root.winfo_width() - sidebar_width
                window_height = self.root.winfo_height()

                image_width = self.label.winfo_width()
                image_height = self.label.winfo_height()

                if image_width > 0 and image_height > 0:
                    # Calculate the coordinates relative to the image
                    if window_width > 0 and window_height > 0:
                        relative_x = (x - label_x - sidebar_width) * self.client_window_width / window_width
                        relative_y = (y - label_y) * self.client_window_height / window_height

                        relative_x = int(relative_x)
                        relative_y = int(relative_y)

                        self._send_update(relative_x, relative_y, str(button), None, block_input=self.blocking_input)

    def _on_mouse_scroll(self, x, y, dx, dy):
        if self.running and self.record_mouse:
            label_x = self.label.winfo_rootx()
            label_y = self.label.winfo_rooty()
            sidebar_width = self.sidebar_frame.winfo_width()

            # Calculate available width for the image (considering the sidebar)
            window_width = self.root.winfo_width() - sidebar_width
            window_height = self.root.winfo_height()

            image_width = self.label.winfo_width()
            image_height = self.label.winfo_height()

            if image_width > 0 and image_height > 0:
                # Calculate the coordinates relative to the image
                relative_x = (x - label_x - sidebar_width) * self.client_window_width / window_width
                relative_y = (y - label_y) * self.client_window_height / window_height

                relative_x = int(relative_x)
                relative_y = int(relative_y)

                self._send_update(
                    relative_x,
                    relative_y,
                    None, None,
                    block_input=self.blocking_input,
                    streaming_webcam=self.streaming_webcam,
                    streaming_mic=self.streaming_microphone,
                    dx=dx,
                    dy=dy
                )

    def _on_key_press(self, key):
        if self.running and self.record_keyboard:
            try:
                self._send_update(None, None, None, key.char, block_input=self.blocking_input)
            except AttributeError:
                self._send_update(None, None, None, str(key), block_input=self.blocking_input)
            except Exception as e:
                print(f"[ERROR] {e}")

    def _on_close(self, _):
        x = threading.Thread(target=self.stop_display)
        x.start()


def main():
    rdp_server = RdpServer(4444, 4445, 4446, 4447)
    rdp_server.wait_for_connection()
    rdp_server.start_display()


if __name__ == "__main__":
    main()
