import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QTextEdit, QVBoxLayout, QWidget, QLabel
from PyQt5.QtGui import QPalette, QColor, QFont
from PyQt5.QtCore import Qt
import dlib
from PIL import Image
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
import ctypes
from pynput import keyboard, mouse
import pygetwindow as gw
from mss import mss

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

alt_pressed = False
stop_flag = threading.Event()
pause_flag = threading.Event()
click_event = threading.Event()
first_run = True
last_click_coords = (None, None)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        self.flower_detector = dlib.simple_object_detector(os.path.join(base_path, "flower_detector.svm"))
        self.play_detector = dlib.simple_object_detector(os.path.join(base_path, "play_detector.svm"))
        self.invite_detector = dlib.simple_object_detector(os.path.join(base_path, "invite_detector.svm"))
        self.capture_thread = None
        self.last_detection_time = time.time()
        self.window_left = None
        self.window_top = None
        self.window_width = None
        self.window_height = None

    def init_ui(self):
        self.setWindowTitle("Bot for the 'Blum' app")
        self.setGeometry(100, 100, 400, 350)
        self.center_window()
        self.start_button = QPushButton("Start", self)
        self.exit_button = QPushButton("Exit", self)
        self.log_text_edit = QTextEdit(self)
        self.log_text_edit.setReadOnly(True)
        self.hint_label = QLabel(self)
        hint_font_size = 10
        hint_text = f"""
            <span style="font-size:{hint_font_size}pt;">
                <b>Hint:</b> 
                <span style="color:#1c92ff; font-weight:bold;">Alt + Space</span> (pause) | 
                <span style="color:#1c92ff; font-weight:bold;">Alt + F2</span> (stop program)
            </span>
        """
        self.hint_label.setText(hint_text)
        button_font = QFont("Arial", 13, QFont.Bold)
        self.start_button.setFont(button_font)
        self.exit_button.setFont(button_font)
        log_font = QFont("Segoe UI", 10)
        self.log_text_edit.setFont(log_font)
        border_color = "#737373"
        button_style = f"""
            QPushButton {{
                background-color: #1e77ff;
                color: #eeeeee;
                padding: 10px;
                border-radius: 10px;
                border: 1px solid {border_color};
            }}
            QPushButton:hover {{
                background-color: #002d6f;
            }}
            QPushButton:pressed {{
                background-color: #002254;
            }}
        """
        exit_button_style = f"""
            QPushButton {{
                background-color: #0148b3;
                color: #eeeeee;
                padding: 10px;
                border-radius: 10px;
                border: 1px solid {border_color};
            }}
            QPushButton:hover {{
                background-color: #002d6f;
            }}
            QPushButton:pressed {{
                background-color: #002254;
            }}
        """
        log_style = f"""
            QTextEdit {{
                background-color: #373737;
                color: #D1D1D1;
                border: 2px solid {border_color};
                border-radius: 10px;
                padding: 5px;
            }}
        """
        self.start_button.setStyleSheet(button_style)
        self.exit_button.setStyleSheet(exit_button_style)
        self.log_text_edit.setStyleSheet(log_style)
        layout = QVBoxLayout()
        layout.addWidget(self.start_button)
        layout.addWidget(self.exit_button)
        layout.addWidget(self.log_text_edit)
        layout.addWidget(self.hint_label)
        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
        self.start_button.clicked.connect(self.start_process)
        self.exit_button.clicked.connect(self.exit_program)

    def center_window(self):
        screen = QApplication.primaryScreen().availableGeometry()
        size = self.geometry()
        self.move((screen.width() - size.width()) // 2, (screen.height() - size.height()) // 2)

    def update_log(self, message):
        self.log_text_edit.append(message)
        self.log_text_edit.ensureCursorVisible()
        QApplication.processEvents()

    def start_process(self):
        self.update_log("Process started...")
        window = self.get_window_from_click()
        if window:
            global stop_flag, first_run, last_click_coords
            stop_flag.clear()
            first_run = True
            last_click_coords = (None, None)
            self.last_detection_time = time.time()
            self.window_left = window.left
            self.window_top = window.top
            self.window_width = window.width
            self.window_height = window.height
            self.capture_thread = threading.Thread(target=self.capture_and_process, args=(window,), daemon=True)
            self.capture_thread.start()

    def stop_process(self):
        global stop_flag
        stop_flag.set()
        self.update_log("Process stopped.")

    def exit_program(self):
        self.stop_process()
        self.update_log("Exiting the program.")
        QApplication.quit()

    def get_window_from_click(self):
        self.update_log("Please click on the application window...")
        global click_event
        click_event.clear()
        click_event.wait()
        x, y = self.get_cursor_pos()
        self.update_log("Script started.")
        window = gw.getWindowsAt(x, y)
        if not window:
            self.update_log("Window not found at the coordinates.")
            return None
        try:
            window[0].activate()
        except:
            pass
        return window[0]

    def get_cursor_pos(self):
        cursor = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(cursor))
        return cursor.x, cursor.y

    def capture_and_process(self, window):
        left, top, width, height = window.left, window.top, window.width, window.height
        monitor = {"top": top, "left": left, "width": width, "height": height}
        sct = mss()
        resize_factor = 1
        with ThreadPoolExecutor(max_workers=9) as executor:
            futures = []
            while not stop_flag.is_set():
                if pause_flag.is_set():
                    time.sleep(0.1)
                    continue
                screenshot = np.array(sct.grab(monitor))
                future = executor.submit(
                    self.process_image,
                    screenshot,
                    self.flower_detector,
                    self.play_detector,
                    self.invite_detector,
                    left,
                    top,
                    resize_factor
                )
                futures.append(future)
                for future in as_completed(futures):
                    flower_detections, play_detections, invite_detections, shape = future.result()
                    futures.remove(future)
                    if flower_detections or play_detections:
                        self.last_detection_time = time.time()
                    global first_run, last_click_coords
                    if not first_run and play_detections:
                        time.sleep(2)
                        if not pause_flag.is_set() and not stop_flag.is_set():
                            for det in play_detections:
                                cX = int((det.left() + det.right()) / 2 / resize_factor) + left
                                cY = int((det.top() + det.bottom()) / 2 / resize_factor) + top
                                if (cX, cY) != last_click_coords:
                                    self.mouse_click(cX, cY)
                                    last_click_coords = (cX, cY)
                            time.sleep(1)
                    if not pause_flag.is_set():
                        if flower_detections:
                            for det in flower_detections:
                                cX = int((det.left() + det.right()) / 2 / resize_factor) + left
                                cY = int((det.top() + det.bottom()) / 2 / resize_factor) + top
                                cY += 50
                                if (cX, cY) != last_click_coords:
                                    self.mouse_click(cX, cY)
                                    last_click_coords = (cX, cY)
                        else:
                            if play_detections:
                                for det in play_detections:
                                    cX = int((det.left() + det.right()) / 2 / resize_factor) + left
                                    cY = int((det.top() + det.bottom()) / 2 / resize_factor) + top
                                    if (cX, cY) != last_click_coords:
                                        self.mouse_click(cX, cY)
                                        last_click_coords = (cX, cY)
                first_run = False

    def process_image(self, screenshot, flower_detector, play_detector, invite_detector, left, top, resize_factor):
        small_screenshot = Image.fromarray(screenshot).resize(
            (int(screenshot.shape[1] * resize_factor), int(screenshot.shape[0] * resize_factor))
        )
        small_screenshot_rgb = np.array(small_screenshot.convert("RGB"))
        flower_detections = flower_detector(small_screenshot_rgb)
        play_detections = play_detector(small_screenshot_rgb)
        invite_detections = invite_detector(small_screenshot_rgb)
        return flower_detections, play_detections, invite_detections, small_screenshot_rgb.shape

    def mouse_click(self, x, y):
        x = max(self.window_left + 10, min(x, self.window_left + self.window_width - 10))
        y = max(self.window_top + 62, min(y, self.window_top + self.window_height - 43))
        ctypes.windll.user32.SetCursorPos(x, y)
        ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0)

def on_press(key):
    global alt_pressed, stop_flag, pause_flag
    try:
        if key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
            alt_pressed = True
        if key == keyboard.Key.f2 and alt_pressed:
            stop_flag.set()
            main_window.update_log("Script stopped by user (ALT + F2).")
        if key == keyboard.Key.space and alt_pressed:
            if pause_flag.is_set():
                pause_flag.clear()
                main_window.update_log("Script resumed (ALT + Space).")
            else:
                pause_flag.set()
                main_window.update_log("Script paused (ALT + Space).")
    except Exception as e:
        main_window.update_log(f"Error processing key press: {e}")

def on_release(key):
    global alt_pressed
    if key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
        alt_pressed = False

def on_click(x, y, button, pressed):
    global click_event
    if pressed:
        click_event.set()

def main():
    global main_window
    app = QApplication(sys.argv)
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(33, 33, 33))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(dark_palette)
    main_window = MainWindow()
    main_window.show()
    keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    mouse_listener = mouse.Listener(on_click=on_click)
    keyboard_listener.start()
    mouse_listener.start()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
