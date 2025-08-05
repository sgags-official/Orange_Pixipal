"""
stickmate_optimized.py – Smooth & Fast Stickman Desktop Pet
- Modified for specific behavior requirements
- Chrome browser detection with ENJOY → WATCHING loop
- Cursor following with lag and speed-based running
- Proper idle animation sequencing

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
WATCHING = "watching.gif"

# Speed thresholds (pixels/sec)
WALK_VEL = 50
FAST_CURSOR_SPEED = 720  # NOTE: Adjust this value to change when running starts
RUN_IDLE_MAX_TIME = 5  # Max time in running_idle before slowing
IDLE_ANIMATION_DELAY = 2000  # 2 seconds between idle animations

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
        self.idle_sequence_index = 0  # Track position in idle sequence
        self.idle_1_play_count = 0   # Count how many times idle_1 has played
        self.cur_name = None
        self.current_movie = None
        self.last_cursor_pos = None
        self.stickman_pos = None  # Stickman's current position (with lag)
        self.vel_timer = QElapsedTimer()
        self.fixed_y = 0
        self.is_chrome_active = False
        self.chrome_state = "none"  # "none", "enjoying", "watching"

        # Running state tracking
        self.running_idle_start_time = None
        self.current_direction = "right"  # Track last movement direction

        # Idle animation timing
        self.idle_timer = QTimer()
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self.play_next_idle)

        # Cursor movement detection
        self.last_cursor_move_time = time.time()
        self.cursor_stationary = False

        try:
            self.setup_ui()
            self.load_animations()
            self.setup_position()
            self.setup_timers()
            self.setup_shortcuts()

            # Start with first idle animation
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
            CLICK_SINGLE, CLICK_DOUBLE, ENJOY, WATCHING
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
                cursor_pos = pyautogui.position()
                self.last_cursor_pos = cursor_pos
                self.stickman_pos = cursor_pos  # Start at cursor position
                self.vel_timer.start()
        except Exception as e:
            print(f"Position setup error: {e}")
            self.fixed_y = 100
            self.last_cursor_pos = type('pos', (), {'x': 100, 'y': 100})()
            self.stickman_pos = type('pos', (), {'x': 100, 'y': 100})()

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

    def reset_idle_sequence(self):
        """Reset idle animation sequence to beginning"""
        self.idle_sequence_index = 0
        self.idle_1_play_count = 0
        self.idle_timer.stop()

    def play_next_idle(self):
        """Play next animation in idle sequence"""
        if not self.cursor_stationary:
            return

        # Idle sequence: idle_1 (2 times) -> idle_2 -> idle_3 -> idle_4 -> idle_5 (loop)
        if self.idle_sequence_index == 0:  # idle_animation_1
            if self.idle_1_play_count < 2:
                self.set_animation(IDLE_CLIPS[0])
                self.idle_1_play_count += 1
                if self.idle_1_play_count >= 2:
                    self.idle_sequence_index = 1
            else:
                self.idle_sequence_index = 1

        elif self.idle_sequence_index < len(IDLE_CLIPS):
            # Play idle_2, idle_3, idle_4, idle_5
            if IDLE_CLIPS[self.idle_sequence_index] in self.movies:
                self.set_animation(IDLE_CLIPS[self.idle_sequence_index])
            self.idle_sequence_index += 1

        else:
            # Loop back to idle_5 (index 4)
            self.idle_sequence_index = 4
            if IDLE_CLIPS[4] in self.movies:  # idle_animation_5
                self.set_animation(IDLE_CLIPS[4])

        # Schedule next idle animation if cursor is still stationary
        if self.cursor_stationary:
            self.idle_timer.start(IDLE_ANIMATION_DELAY)

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

            # Set new movie
            self.cur_name = clip_name
            self.current_movie = movie
            self.setMovie(movie)

            # Connect finished signal for special animations
            if clip_name in [ENJOY, WATCHING, CLICK_SINGLE, CLICK_DOUBLE, RUN2SLOW_L, RUN2SLOW_R]:
                movie.finished.connect(lambda: self.on_animation_finished(clip_name))

            movie.start()

        except Exception as e:
            print(f"Animation error: {e}")

    def on_animation_finished(self, clip_name):
        """Handle animation completion"""
        try:
            if clip_name == ENJOY:
                # After enjoying, start watching loop
                self.chrome_state = "watching"
                if WATCHING in self.movies:
                    self.set_animation(WATCHING)

            elif clip_name == WATCHING:
                # Keep looping watching if Chrome is still active
                if self.is_chrome_active and WATCHING in self.movies:
                    self.set_animation(WATCHING)
                else:
                    # Chrome no longer active, return to idle
                    self.chrome_state = "none"
                    self.return_to_idle_1()

            elif clip_name in [RUN2SLOW_L, RUN2SLOW_R]:
                # After slowing animation, return to idle_1
                self.return_to_idle_1()

            elif clip_name in [CLICK_SINGLE, CLICK_DOUBLE]:
                self.return_to_idle_1()

        except Exception as e:
            print(f"Animation finish error: {e}")

    def return_to_idle_1(self):
        """Return to idle_animation_1 and reset sequence"""
        self.reset_idle_sequence()
        if IDLE_CLIPS[0] in self.movies:
            self.set_animation(IDLE_CLIPS[0])

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
                self.chrome_state = "enjoying"

                # Start enjoying animation if not in special states
                if (self.cur_name not in (ENJOY, WATCHING, CLICK_SINGLE, CLICK_DOUBLE)
                    and ENJOY in self.movies):
                    self.reset_idle_sequence()  # Stop idle sequence
                    self.set_animation(ENJOY)

            # If Chrome is no longer active
            elif not chrome_active and self.is_chrome_active:
                self.is_chrome_active = False
                self.chrome_state = "none"

                # Return to idle if currently in browser-specific animations
                if self.cur_name in (ENJOY, WATCHING):
                    self.return_to_idle_1()

        except Exception as e:
            print(f"Chrome check error: {e}")

    def update_state(self):
        """Main state update loop"""
        try:
            if not HAS_PYAUTOGUI:
                return

            # Get current cursor position
            try:
                cursor_pos = pyautogui.position()
            except Exception:
                return

            if not self.last_cursor_pos:
                self.last_cursor_pos = cursor_pos
                return

            # Check if cursor moved
            cursor_moved = (cursor_pos.x != self.last_cursor_pos.x or
                          cursor_pos.y != self.last_cursor_pos.y)

            if cursor_moved:
                self.last_cursor_move_time = time.time()
                self.cursor_stationary = False
                # Reset idle sequence when cursor moves
                if self.cur_name in IDLE_CLIPS and self.chrome_state == "none":
                    self.reset_idle_sequence()
            else:
                # Check if cursor has been stationary for a while
                if time.time() - self.last_cursor_move_time > 1.0:  # 1 second delay
                    if not self.cursor_stationary:
                        self.cursor_stationary = True
                        # Start idle sequence if not in Chrome mode
                        if self.chrome_state == "none" and self.cur_name == IDLE_CLIPS[0]:
                            self.idle_timer.start(IDLE_ANIMATION_DELAY)

            # Skip movement logic for Chrome animations
            if self.chrome_state in ["enjoying", "watching"]:
                self.last_cursor_pos = cursor_pos
                return

            # Skip movement logic for special animations
            if self.cur_name in (CLICK_SINGLE, CLICK_DOUBLE, ENJOY, WATCHING):
                self.last_cursor_pos = cursor_pos
                return

            # Calculate cursor speed
            dx = cursor_pos.x - self.last_cursor_pos.x
            elapsed_ms = max(1, self.vel_timer.restart())
            cursor_speed = abs(dx) / (elapsed_ms / 1000.0)

            # Update stickman position with lag (move towards cursor)
            if self.stickman_pos:
                # Calculate distance to cursor
                distance_to_cursor = abs(cursor_pos.x - self.stickman_pos.x)

                # Stickman movement speed (lag effect)
                if distance_to_cursor > 10:  # Only move if far enough from cursor
                    move_speed = min(distance_to_cursor * 0.1, 200)  # Lag factor
                    if cursor_pos.x > self.stickman_pos.x:
                        self.stickman_pos = type('pos', (), {
                            'x': self.stickman_pos.x + move_speed * (elapsed_ms / 1000.0),
                            'y': self.stickman_pos.y
                        })()
                        self.current_direction = "right"
                    else:
                        self.stickman_pos = type('pos', (), {
                            'x': self.stickman_pos.x - move_speed * (elapsed_ms / 1000.0),
                            'y': self.stickman_pos.y
                        })()
                        self.current_direction = "left"

            # Update stickman visual position
            if self.stickman_pos:
                screen_width = pyautogui.size().width
                new_x = max(0, min(int(self.stickman_pos.x) - self.width() // 2,
                                 screen_width - self.width()))
                self.move(new_x, self.fixed_y)

            # Animation logic based on cursor speed and distance
            if cursor_speed >= FAST_CURSOR_SPEED and cursor_moved:
                # Fast cursor movement - start running immediately
                run_anim = RUN_RIGHT if self.current_direction == "right" else RUN_LEFT
                if run_anim in self.movies and self.cur_name != run_anim:
                    self.set_animation(run_anim)
                    # Immediately transition to running idle
                    QTimer.singleShot(500, self.start_running_idle)  # 0.5 second delay

            elif cursor_moved and distance_to_cursor > 50:
                # Normal cursor movement - walking
                if distance_to_cursor > 10:
                    walk_anim = WALK_RIGHT if self.current_direction == "right" else WALK_LEFT
                    if walk_anim in self.movies and self.cur_name not in RUNNING_ANIMS:
                        self.set_animation(walk_anim)

            elif not cursor_moved or distance_to_cursor <= 10:
                # Cursor stopped or stickman caught up
                if self.cur_name in [RUN_LEFT, RUN_RIGHT, WALK_LEFT, WALK_RIGHT]:
                    self.return_to_idle_1()
                elif self.cur_name in [RUN_IDLE_L, RUN_IDLE_R]:
                    # Check if running idle has been playing too long
                    if (self.running_idle_start_time and
                        time.time() - self.running_idle_start_time > RUN_IDLE_MAX_TIME):
                        # Play slowing animation
                        slow_anim = RUN2SLOW_R if self.current_direction == "right" else RUN2SLOW_L
                        if slow_anim in self.movies:
                            self.set_animation(slow_anim)
                        self.running_idle_start_time = None

            self.last_cursor_pos = cursor_pos

        except Exception as e:
            print(f"State update error: {e}")

    def start_running_idle(self):
        """Start running idle animation"""
        try:
            if self.cur_name in [RUN_LEFT, RUN_RIGHT]:
                idle_anim = RUN_IDLE_R if self.current_direction == "right" else RUN_IDLE_L
                if idle_anim in self.movies:
                    self.set_animation(idle_anim)
                    self.running_idle_start_time = time.time()
        except Exception as e:
            print(f"Running idle error: {e}")

    def cleanup(self):
        """Clean up resources"""
        try:
            # Stop all timers
            if hasattr(self, 'anim_timer'):
                self.anim_timer.stop()
            if hasattr(self, 'browser_timer'):
                self.browser_timer.stop()
            if hasattr(self, 'idle_timer'):
                self.idle_timer.stop()

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