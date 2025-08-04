"""
stickmate.py – part 1/2
Qt-based desktop companion that reacts to mouse speed,
plays multi-stage idles, and notices web browsers.
"""

import sys, time, math, itertools, pathlib, psutil, pyautogui, keyboard
from PyQt5.QtCore import Qt, QTimer, QSize, QPoint, QElapsedTimer
from PyQt5.QtGui  import QMovie
from PyQt5.QtWidgets import QApplication, QLabel

# ────────────────────────────────────────────────────────────
# Constants & helpers
# ────────────────────────────────────────────────────────────
ASSET_DIR = pathlib.Path(__file__).with_suffix('')  # folder beside script

IDLE_CLIPS   = [f"idle_animation_{i}.gif"  for i in range(1, 6)]
WALK_LEFT    = "walk_left.gif"
WALK_RIGHT   = "walk_right.gif"
RUN_LEFT     = "running_animation_left.gif"
RUN_RIGHT    = "running_animation_right.gif"
RUN_IDLE_L   = "running_idle_left.gif"
RUN_IDLE_R   = "running_idle_right.gif"
RUN2SLOW_L   = "running_to_slowing_left.gif"
RUN2SLOW_R   = "running_to_slowing_right.gif"
CLICK_SINGLE = "single_tap.gif"
CLICK_DOUBLE = "double_tap.gif"
ENJOY        = "enjoying_with_us.gif"
SIT          = "sitting.gif"

# Mouse-speed thresholds (pixels / timer-tick)
WALK_VEL  = 2
RUN_VEL   = 20           # start running
RUN_IDLE  = 8            # consider “restless” when slowing

RUN_MAX_SEC = 5          # after this many seconds of running → run2slow

BROWSER_NAMES = {"chrome.exe", "firefox.exe"}  # windows process names

class StickmanOverlay(QLabel):
    def __init__(self):
        super().__init__()

        # top-most frameless translucent window
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setScaledContents(True)
        self.setFixedSize(100, 200)          # logical size

        # Load & cache every gif clip once
        self.movies = {name: QMovie(str(ASSET_DIR / name)) for name in
                       itertools.chain(IDLE_CLIPS, [
                           WALK_LEFT, WALK_RIGHT, RUN_LEFT, RUN_RIGHT,
                           RUN_IDLE_L, RUN_IDLE_R, RUN2SLOW_L, RUN2SLOW_R,
                           CLICK_SINGLE, CLICK_DOUBLE, ENJOY, SIT])}
        for mv in self.movies.values():
            mv.setScaledSize(QSize(self.width(), self.height()))

        # Animation sequencing
        self.idle_cycle = itertools.cycle(IDLE_CLIPS)
        self.cur_name   = None
        self.set_animation(next(self.idle_cycle))

        # Motion tracking
        self.last_pos   = pyautogui.position()
        self.vel_timer  = QElapsedTimer()
        self.vel_timer.start()
        self.run_start  = None

        # Timers
        self.anim_tick  = QTimer(self, timeout=self.update_state)
        self.anim_tick.start(20)             # 50 Hz

        self.browser_poll = QTimer(self, timeout=self.check_browser, interval=1000)
        self.browser_poll.start()

        # Click detection
        self.click_state = False
        self.last_click  = 0
        self.double_thresh = 0.4
        self.click_timer = QTimer(self, timeout=self.poll_mouse_buttons, interval=30)
        self.click_timer.start()

        # Position the figure on the task-bar baseline
        self.fixed_y = pyautogui.size().height - self.height() + 222
        self.show()

    # ────────────────────────────────────────────────────────
    # High-level animation API
    # ────────────────────────────────────────────────────────
    def set_animation(self, clip_name):
        if clip_name == self.cur_name:
            return
        if self.cur_name:
            self.movies[self.cur_name].stop()
        self.cur_name = clip_name
        movie = self.movies[clip_name]
        self.setMovie(movie)
        movie.start()

    # ────────────────────────────────────────────────────────
    # Input monitoring
    # ────────────────────────────────────────────────────────
    def poll_mouse_buttons(self):
        from win32api import GetKeyState
        from win32con import VK_LBUTTON
        pressed = GetKeyState(VK_LBUTTON) < 0
        now = time.time()
        if pressed and not self.click_state:
            if now - self.last_click < self.double_thresh:
                self.play_click(double=True)
            else:
                self.play_click(double=False)
            self.last_click = now
        self.click_state = pressed

    def play_click(self, double=False):
        self.set_animation(CLICK_DOUBLE if double else CLICK_SINGLE)
        # the click gifs are short; revert to idle after they finish
        QTimer.singleShot(600 if double else 400,
                          lambda: self.set_animation(next(self.idle_cycle)))

    def check_browser(self):
        """Switch to excitement/sitting when a browser is detected running."""
        browsers = {p.name().lower() for p in psutil.process_iter(attrs=["name"])}
        if browsers & BROWSER_NAMES:
            # if starting browser, show enjoy gif once then loop sit
            if self.cur_name not in (ENJOY, SIT):
                self.set_animation(ENJOY)
                QTimer.singleShot(self.movies[ENJOY].duration() or 2500,
                                  lambda: self.set_animation(SIT))
        else:
            # return to normal cycling idle
            if self.cur_name in (ENJOY, SIT):
                self.set_animation(next(self.idle_cycle))

    # ────────────────────────────────────────────────────────
    # Main update – called every 20 ms
    # ────────────────────────────────────────────────────────
    def update_state(self):
        pos = pyautogui.position()
        dx = pos.x - self.last_pos.x
        speed = abs(dx) / max(1, self.vel_timer.restart())  # px per tick
        self.last_pos = pos

        # clip & move horizontally
        self.move(pos.x - self.width()//2, self.fixed_y)

        if self.cur_name in (CLICK_SINGLE, CLICK_DOUBLE, ENJOY):
            return  # wait until these end

        # Decide walk/run/idle states
        if speed < WALK_VEL:
            # completely idle
            self.run_start = None
            if self.cur_name not in IDLE_CLIPS:
                self.set_animation(next(self.idle_cycle))
        elif speed < RUN_VEL:
            self.run_start = None
            self.set_animation(WALK_RIGHT if dx > 0 else WALK_LEFT)
        else:
            # currently running
            if self.run_start is None:
                self.run_start = time.time()
            run_dir = RUN_RIGHT if dx > 0 else RUN_LEFT
            self.set_animation(run_dir)

            # after 5 s running → slow animation
            if time.time() - self.run_start > RUN_MAX_SEC:
                self.set_animation(RUN2SLOW_R if dx > 0 else RUN2SLOW_L)
                # when run2slow finishes, go to base idle
                dur = self.movies[self.cur_name].duration() or 1200
                QTimer.singleShot(dur, lambda: self.set_animation(next(self.idle_cycle)))
                self.run_start = None
                return

        # If running but suddenly slows (mouse still moving a bit) → run-idle
        if self.cur_name in (RUN_RIGHT, RUN_LEFT) and speed < RUN_IDLE:
            self.set_animation(RUN_IDLE_R if dx > 0 else RUN_IDLE_L)

# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = StickmanOverlay()
    keyboard.add_hotkey("esc", lambda: sys.exit())
    sys.exit(app.exec_())
