import sys
import pyautogui
import keyboard
from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtCore import Qt, QTimer, QPoint, QSize
from PyQt5.QtGui import QMovie, QCursor
import time
import win32api
import win32con


class StickmanOverlay(QLabel):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setScaledContents(True)

        # Fixed file paths - put GIFs in current directory
        self.animations = {
            "idle": QMovie("idle.gif"),
            "walk_right": QMovie("Walk_Right.gif"),
            "walk_left": QMovie("Walk_Left.gif"),
            "single_click": QMovie("single_tap.gif"),
            "double_click": QMovie("double_tap.gif")
        }

        self.current_animation = None
        self.last_pos = pyautogui.position()

        # Click detection variables
        self.last_click_time = 0
        self.double_click_threshold = 0.4  # seconds
        self.is_performing_action = False
        self.last_mouse_state = False

        # Fixed Y coordinate
        self.fixed_y = pyautogui.size().height - self.height() + 222 # taskbar height
        print (self.fixed_y)
        print(self.height())

        # Set fixed size like the working version
        self.setFixedSize(100, 200)

        self.set_animation("idle")

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_position)
        self.timer.start(20)

        # Click detection timer
        self.click_timer = QTimer()
        self.click_timer.timeout.connect(self.detect_click)
        self.click_timer.start(50)

        self.show()

    def set_animation(self, name):
        if self.current_animation == name or self.is_performing_action:
            return

        if self.current_animation:
            self.animations[self.current_animation].stop()

        self.current_animation = name
        movie = self.animations.get(name)
        if movie:
            # Scale the movie like in working version
            movie.setScaledSize(QSize(self.width(), self.height()))
            self.setMovie(movie)
            movie.start()

            # Handle one-shot animations
            if name in ["click", "double_click"]:
                self.is_performing_action = True
                # Use a fixed duration instead of movie.duration()
                duration = 1000 if name == "double_click" else 500
                QTimer.singleShot(duration, self.end_action_animation)

    def end_action_animation(self):
        self.is_performing_action = False
        self.set_animation("idle")

    def update_position(self):
        if self.is_performing_action:
            return  # Don't change animation during click actions

        pos = pyautogui.position()
        dx = pos.x - self.last_pos.x

        if dx > 2:
            self.set_animation("walk_right")
        elif dx < -2:
            self.set_animation("walk_left")
        else:
            self.set_animation("idle")

        # Keep stickman at fixed Y coordinate, follow X coordinate of mouse
        self.move(pos.x - 50, self.fixed_y)  # Center the stickman horizontally

        self.last_pos = pos

    def detect_click(self):
        """Detect mouse clicks using win32api"""
        try:
            # Check if left mouse button is pressed
            current_mouse_state = win32api.GetKeyState(win32con.VK_LBUTTON) < 0

            # Detect button press (transition from not pressed to pressed)
            if current_mouse_state and not self.last_mouse_state and not self.is_performing_action:
                current_time = time.time()

                # Check if this is a double click
                if current_time - self.last_click_time < self.double_click_threshold:
                    self.set_animation("double_click")
                else:
                    self.set_animation("single_click")

                self.last_click_time = current_time

            self.last_mouse_state = current_mouse_state

        except Exception as e:
            print(f"Click detection error: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StickmanOverlay()

    # Add ESC key exit like in working version
    keyboard.add_hotkey("esc", lambda: sys.exit())

    sys.exit(app.exec_())