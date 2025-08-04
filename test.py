"""
stickmate_optimized.py – Smooth & Fast Stickman Desktop Pet
- Optimized for performance, removed laggy features
- Proper idle animation sequence (1->2->3->4->5->1)
- Fixed running animations
- Chrome active window detection (enjoying_with_us.gif -> watching.gif loops continuously)
- Removed click detection for now (will add later)

REQUIRED DEPENDENCIES:
pip install PyQt5 pyautogui psutil pywin32
"""

import sys
import time
import itertools
import pathlib
import traceback
from PyQt5.QtCore import Qt, QTimer, QSize, QElapsedTimer
from PyQt5.QtGui import QMovie, QKeySequence
from PyQt5.QtWidgets import QApplication, QLabel, QShortcut

# Safe imports with fallbacks
try:
    import psutil
    import win32gui
    import win32process
    HAS_PSUTIL = True
    HAS_WIN32 = True
except ImportError as e:
    if 'win32' in str(e):
        HAS_WIN32 = False
        print("Warning: win32gui not available, using basic browser detection")
        try:
            import psutil
            HAS_PSUTIL = True
        except ImportError:
            HAS_PSUTIL = False
            print("Warning: psutil not available, browser detection disabled")
    else:
        HAS_PSUTIL = False
        HAS_WIN32 = False
        print("Warning: psutil not available, browser detection disabled")

try:
    import pyautogui
    pyautogui.FAILSAFE = False  # Disable failsafe
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    print("Error: pyautogui is required")
    sys.exit(1)

ASSET_DIR = pathlib.Path(__file__).parent

# Animation clips
IDLE_CLIPS = [f"idle_animation_{i}.gif" for i in range(1, 6)]
WALK_LEFT = "walk_left.gif"
WALK_RIGHT = "walk_right.gif"
RUN_LEFT = "running_animation_left.gif"
RUN_RIGHT = "running_animation_right.gif"
RUN_IDLE_L = "running_idle_left.gif"
RUN_IDLE_R = "running_idle_right.gif"
RUN2SLOW_L = "running_to_slowing_left.gif"
RUN2SLOW_R = "running_to_slowing_right.gif"
CLICK_SINGLE = "single_tap.gif"
CLICK_DOUBLE = "double_tap.gif"
ENJOY = "enjoying_with_us.gif"
SIT = "sitting.gif"
WATCHING = "watching.gif"

# Speed thresholds (pixels/sec)
WALK_VEL = 50
RUN_VEL = 250
RUN_IDLE = 120
RUN_MAX_SEC = 5

CHROME_NAMES = {"chrome.exe"}
RUNNING_ANIMS = {RUN_LEFT, RUN_RIGHT, RUN_IDLE_L, RUN_IDLE_R, RUN2SLOW_L, RUN2SLOW_R}

# Target display sizes
SIZE_IDLE = QSize(100, 200)
SIZE_RUN = QSize(150, 200)

def safe_movie(path):
    """Create a QMovie with proper error handling"""
    try:
        if not path.exists():
            print(f"⚠ Missing asset: {path.name}")
            return None

        mv = QMovie(str(path))
        if not mv.isValid():
            print(f"⚠ Invalid movie file: {path.name}")
            return None

        mv.setCacheMode(QMovie.CacheAll)
        return mv
    except Exception as e:
        print(f"⚠ Error loading {path.name}: {e}")
        return None

class StickmanOverlay(QLabel):
    def __init__(self):
        super().__init__()

        # Initialize all attributes first
        self.movies = {}
        self.idle_index = 0  # Start at 0 for idle_animation_1
        self.cur_name = None
        self.current_movie = None
        self.last_pos = None
        self.vel_timer = QElapsedTimer()
        self.run_start = None
        self.fixed_y = 0
        self.is_chrome_active = False
        self.enjoying_played = False

        try:
            self.setup_ui()
            self.load_animations()
            self.setup_position()
            self.setup_timers()
            self.setup_shortcuts()

            # Start with first idle animation (idle_animation_1)
            self.set_animation(IDLE_CLIPS[0])
            self.show()

        except Exception as e:
            print(f"Initialization error: {e}")
            traceback.print_exc()
            self.cleanup()

    def setup_ui(self):
        """Setup the UI with safe defaults"""
        self.setFixedSize(SIZE_RUN)
        self.setAlignment(Qt.AlignCenter)
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setScaledContents(False)

    def load_animations(self):
        """Load all animation files safely"""
        all_clips = list(itertools.chain(IDLE_CLIPS, [
            WALK_LEFT, WALK_RIGHT, RUN_LEFT, RUN_RIGHT,
            RUN_IDLE_L, RUN_IDLE_R, RUN2SLOW_L, RUN2SLOW_R,
            CLICK_SINGLE, CLICK_DOUBLE, ENJOY, SIT, WATCHING
        ]))

        self.movies = {}
        for name in all_clips:
            movie = safe_movie(ASSET_DIR / name)
            if movie:
                self.movies[name] = movie

        # Check if we have at least one idle animation
        available_idles = [clip for clip in IDLE_CLIPS if clip in self.movies]
        if not available_idles:
            raise Exception("No idle animations found!")

    def setup_position(self):
        """Setup initial position tracking"""
        try:
            if HAS_PYAUTOGUI:
                screen_size = pyautogui.size()
                self.fixed_y = screen_size.height - SIZE_RUN.height() - 50  # 50px from bottom
                self.last_pos = pyautogui.position()
                self.vel_timer.start()
        except Exception as e:
            print(f"Position setup error: {e}")
            self.fixed_y = 100
            self.last_pos = type('pos', (), {'x': 100, 'y': 100})()

    def setup_timers(self):
        """Setup all timers safely"""
        # Main animation timer - optimized interval
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_state)
        self.anim_timer.start(33)  # ~30 FPS for smooth movement

        # Chrome check timer - less frequent for performance
        if HAS_PSUTIL and HAS_WIN32:
            self.browser_timer = QTimer(self)
            self.browser_timer.timeout.connect(self.check_chrome_active)
            self.browser_timer.start(2000)  # Check every 2 seconds

    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        try:
            self.exit_shortcut = QShortcut(QKeySequence("Escape"), self)
            self.exit_shortcut.activated.connect(self.safe_exit)
        except Exception as e:
            print(f"Shortcut setup error: {e}")

    def next_idle(self):
        """Get next idle animation in strict sequence (1->2->3->4->5->1...)"""
        available_idles = [clip for clip in IDLE_CLIPS if clip in self.movies]
        if not available_idles:
            return None

        # Move to next in sequence
        self.idle_index = (self.idle_index + 1) % len(IDLE_CLIPS)
        next_clip = IDLE_CLIPS[self.idle_index]

        # If next clip is not available, find the next available one
        attempts = 0
        while next_clip not in available_idles and attempts < len(IDLE_CLIPS):
            self.idle_index = (self.idle_index + 1) % len(IDLE_CLIPS)
            next_clip = IDLE_CLIPS[self.idle_index]
            attempts += 1

        return next_clip if next_clip in available_idles else available_idles[0]

    def set_animation(self, clip_name):
        """Set animation with proper cleanup"""
        try:
            if clip_name == self.cur_name or clip_name not in self.movies:
                return

            movie = self.movies[clip_name]
            if not movie or not movie.isValid():
                return

            # Stop current movie properly
            if self.current_movie:
                self.current_movie.stop()
                try:
                    self.current_movie.finished.disconnect()
                except:
                    pass  # Ignore if no connections

            # Scale based on animation type
            if clip_name in RUNNING_ANIMS:
                movie.setScaledSize(SIZE_RUN)
            else:
                movie.setScaledSize(SIZE_IDLE)

            # Set loop count based on animation type
            if clip_name == WATCHING:
                # Set WATCHING to loop infinitely
                movie.setLoopCount(-1)  # -1 means infinite loop
            else:
                # Reset to default (play once) for other animations
                movie.setLoopCount(1)

            # Set new movie
            self.cur_name = clip_name
            self.current_movie = movie
            self.setMovie(movie)

            # Connect finished signal only for specific animations (NOT for WATCHING)
            if clip_name in [ENJOY, CLICK_SINGLE, CLICK_DOUBLE]:
                movie.finished.connect(lambda: self.on_animation_finished(clip_name))

            movie.start()

        except Exception as e:
            print(f"Animation error: {e}")

    def on_animation_finished(self, clip_name):
        """Handle animation completion"""
        try:
            if clip_name in [CLICK_SINGLE, CLICK_DOUBLE]:
                next_anim = self.next_idle()
                if next_anim:
                    self.set_animation(next_anim)
            elif clip_name == ENJOY:
                # After enjoying, play watching animation (which will loop infinitely)
                if WATCHING in self.movies:
                    self.set_animation(WATCHING)
                else:
                    # Fall back to sitting if watching not available
                    if SIT in self.movies:
                        self.set_animation(SIT)
                    else:
                        next_anim = self.next_idle()
                        if next_anim:
                            self.set_animation(next_anim)
        except Exception as e:
            print(f"Animation finish error: {e}")

    def is_chrome_active_window(self):
        """Check if Chrome is the active window"""
        if not HAS_WIN32:
            return False

        try:
            # Get the active window
            hwnd = win32gui.GetForegroundWindow()
            if hwnd == 0:
                return False

            # Get process ID of the window
            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            # Get process name
            try:
                process = psutil.Process(pid)
                process_name = process.name().lower()

                # Check if it's Chrome
                return process_name == "chrome.exe"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False

        except Exception:
            return False

    def check_chrome_active(self):
        """Check if Chrome is active and handle enjoy/watching animations"""
        try:
            chrome_active = self.is_chrome_active_window()

            # If Chrome just became active
            if chrome_active and not self.is_chrome_active:
                self.is_chrome_active = True

                # Start enjoying animation if not in special states
                if (self.cur_name not in (ENJOY, WATCHING, CLICK_SINGLE, CLICK_DOUBLE)
                    and ENJOY in self.movies):
                    self.set_animation(ENJOY)

            # If Chrome is no longer active
            elif not chrome_active and self.is_chrome_active:
                self.is_chrome_active = False

                # Return to idle if currently in browser-specific animations
                if self.cur_name in (ENJOY, WATCHING, SIT):
                    next_anim = self.next_idle()
                    if next_anim:
                        self.set_animation(next_anim)

        except Exception as e:
            print(f"Chrome check error: {e}")

    def update_state(self):
        """Main state update loop - optimized"""
        try:
            if not HAS_PYAUTOGUI:
                return

            # Get current mouse position safely
            try:
                pos = pyautogui.position()
            except Exception:
                return

            if not self.last_pos:
                self.last_pos = pos
                return

            # Calculate movement
            dx = pos.x - self.last_pos.x
            elapsed_ms = max(1, self.vel_timer.restart())
            speed = abs(dx) / (elapsed_ms / 1000.0)

            # Update position - optimized bounds checking
            screen_width = pyautogui.size().width
            new_x = max(0, min(pos.x - self.width() // 2, screen_width - self.width()))
            self.move(new_x, self.fixed_y)

            self.last_pos = pos

            # Skip animation logic for special animations (including WATCHING)
            if self.cur_name in (CLICK_SINGLE, CLICK_DOUBLE, ENJOY, WATCHING):
                return

            # Animation state machine - simplified
            if speed < WALK_VEL:
                self.run_start = None
                if self.cur_name not in IDLE_CLIPS:
                    next_anim = self.next_idle()
                    if next_anim:
                        self.set_animation(next_anim)

            elif speed < RUN_VEL:
                self.run_start = None
                walk_anim = WALK_RIGHT if dx > 0 else WALK_LEFT
                if walk_anim in self.movies:
                    self.set_animation(walk_anim)

            else:
                # Running state
                if self.run_start is None:
                    self.run_start = time.time()

                run_anim = RUN_RIGHT if dx > 0 else RUN_LEFT
                if run_anim in self.movies:
                    self.set_animation(run_anim)

                # Transition to slowing after max run time
                if time.time() - self.run_start > RUN_MAX_SEC:
                    slow_anim = RUN2SLOW_R if dx > 0 else RUN2SLOW_L
                    if slow_anim in self.movies:
                        self.set_animation(slow_anim)

                        # Schedule return to idle
                        slow_duration = self.movies[slow_anim].duration() or 1200
                        QTimer.singleShot(slow_duration, lambda: self.set_animation(self.next_idle()))

                    self.run_start = None

            # Running idle state
            if self.cur_name in (RUN_RIGHT, RUN_LEFT) and speed < RUN_IDLE:
                idle_anim = RUN_IDLE_R if dx > 0 else RUN_IDLE_L
                if idle_anim in self.movies:
                    self.set_animation(idle_anim)

        except Exception as e:
            print(f"State update error: {e}")

    def cleanup(self):
        """Clean up resources"""
        try:
            # Stop all timers
            if hasattr(self, 'anim_timer'):
                self.anim_timer.stop()
            if hasattr(self, 'browser_timer'):
                self.browser_timer.stop()

            # Stop current movie
            if self.current_movie:
                self.current_movie.stop()

            # Clean up all movies
            for movie in self.movies.values():
                if movie:
                    movie.stop()

        except Exception as e:
            print(f"Cleanup error: {e}")

    def safe_exit(self):
        """Safely exit the application"""
        try:
            self.cleanup()
            QApplication.quit()
        except Exception as e:
            print(f"Exit error: {e}")
            sys.exit(0)

    def closeEvent(self, event):
        """Handle close event"""
        self.cleanup()
        event.accept()

def main():
    """Main application entry point"""
    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(True)

        # Global exception handler
        def handle_exception(exc_type, exc_value, exc_traceback):
            print(f"Unhandled exception: {exc_type.__name__}: {exc_value}")
            traceback.print_exception(exc_type, exc_value, exc_traceback)

        sys.excepthook = handle_exception

        overlay = StickmanOverlay()
        sys.exit(app.exec_())

    except Exception as e:
        print(f"Application error: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()