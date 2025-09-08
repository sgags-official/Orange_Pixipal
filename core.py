"""
This is the main source code of the Orange Pixipal
The original design of the Orange Pixipal is heavily inspired from the TSC from the ALan Becker's Animated Series
The inspiration from those animations led me to coding these following lines
"""

# Importing the Header Files

import sys
import time
import itertools
import pathlib
import traceback
from PyQt5.QtCore import Qt, QTimer, QSize, QElapsedTimer
from PyQt5.QtGui import QMovie, QKeySequence
from PyQt5.QtWidgets import QApplication, QLabel, QShortcut


# Safe Imports with Fallbacks set for error detection
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

# Import win32api for click detection
try:
    import win32api
    import win32con
    HAS_WIN32API = True
except ImportError:
    HAS_WIN32API = False
    print("Warning: win32api not available, click detection disabled")

ASSET_DIR = pathlib.Path(__file__).parent

# Animation Cycles and Clips
IDLE_CLIP_1 = "idle_animation_1.gif"
IDLE_CLIP_2 = "idle_animation_2.gif"
IDLE_CLIP_3 = "idle_animation_3.gif"
IDLE_CLIP_4 = "idle_animation_4.gif"
IDLE_CLIP_5 = "idle_animation_5.gif"
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

# Create IDLE_CLIPS list from the individual constants
IDLE_CLIPS = [IDLE_CLIP_1, IDLE_CLIP_2, IDLE_CLIP_3, IDLE_CLIP_4, IDLE_CLIP_5]

# Speed Values and Control Panel
WALK_VEL = 50
FAST_CURSOR_SPEED = 400
RUN_IDLE_MAX_TIME = 5
STICKMAN_FOLLOW_SPEED = 3.0

# Fixed timing values for idle animations (in milliseconds)
IDLE_ANIMATION_TIMEOUT_1 = int(40.9 * 1000)
IDLE_ANIMATION_TIMEOUT_2 = int(4.266666 * 1000)
IDLE_ANIMATION_TIMEOUT_3 = int(31.5 * 1000)
IDLE_ANIMATION_TIMEOUT_4 = int(8.833333 * 1000)
IDLE_ANIMATION_TIMEOUT_5 = 0  # Placeholder - idle_5 loops indefinitely

# Enjoying animation duration
ENJOY_DURATION = int(0.766666 * 1000)  # 0.766666 seconds in milliseconds

# Click animation durations (in milliseconds)
CLICK_SINGLE_DURATION = int(0.7666666 * 1000)  # 766.6666 ms
CLICK_DOUBLE_DURATION = int(1.1333333 * 1000)  # 1133.3333 ms

# Create timeout list for easy access
IDLE_TIMEOUTS = [
    IDLE_ANIMATION_TIMEOUT_1,
    IDLE_ANIMATION_TIMEOUT_2,
    IDLE_ANIMATION_TIMEOUT_3,
    IDLE_ANIMATION_TIMEOUT_4,
    IDLE_ANIMATION_TIMEOUT_5
]

CHROME_NAMES = {"chrome.exe"}
RUNNING_ANIMS = {RUN_LEFT, RUN_RIGHT, RUN_IDLE_L, RUN_IDLE_R, RUN2SLOW_L, RUN2SLOW_R}

# Target display sizes
SIZE_IDLE = QSize(100, 200)
SIZE_RUN = QSize(150, 200)

# QMOVIE FUNCTION
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

#Creating a Class
class StickmanOverlay(QLabel):
    def __init__(self):
        super().__init__()

        # Initialize all attributes first
        self.movies = {}
        self.idle_sequence_index = 0  # Track position in idle sequence (0-4)
        self.cur_name = None
        self.current_movie = None
        self.last_cursor_pos = None
        self.stickman_x = 500
        self.vel_timer = QElapsedTimer()
        self.fixed_y = 0
        self.is_chrome_active = False
        self.chrome_state = "none"  # "none", "enjoying", "watching"
        self.chrome_first_detected_time = None
        self.chrome_fixed_position = None  # Store position when Chrome is detected

        # Running state tracking
        self.running_idle_start_time = None
        self.current_direction = "right"
        self.movement_locked = False

        # Idle animation timing
        self.idle_timer = QTimer()
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self.play_next_idle)

        # Chrome enjoy timer
        self.enjoy_timer = QTimer()
        self.enjoy_timer.setSingleShot(True)
        self.enjoy_timer.timeout.connect(self.start_watching)

        # Click animation timer
        self.click_timer_single = QTimer()
        self.click_timer_single.setSingleShot(True)
        self.click_timer_single.timeout.connect(lambda: self.force_stop_click_animation(CLICK_SINGLE))

        self.click_timer_double = QTimer()
        self.click_timer_double.setSingleShot(True)
        self.click_timer_double.timeout.connect(lambda: self.force_stop_click_animation(CLICK_DOUBLE))

        # Cursor movement detection
        self.last_cursor_move_time = time.time()
        self.cursor_stationary = False

        # Click detection with win32api
        self.last_click_time = 0
        self.double_click_threshold = 0.4  # seconds
        self.last_mouse_state = False

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
                self.fixed_y = screen_size.height - SIZE_RUN.height() - 50
                cursor_pos = pyautogui.position()
                self.last_cursor_pos = cursor_pos
                self.stickman_x = cursor_pos.x
                self.vel_timer.start()
        except Exception as e:
            print(f"Position setup error: {e}")
            self.fixed_y = 100
            self.last_cursor_pos = type('pos', (), {'x': 500, 'y': 100})()
            self.stickman_x = 500

    def setup_timers(self):
        """Setting up all timers safely"""
        # Main animation timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_state)
        self.anim_timer.start(33)  # 30 FPS

        # Click detection timer
        if HAS_WIN32API:
            self.click_timer = QTimer(self)
            self.click_timer.timeout.connect(self.detect_click)
            self.click_timer.start(50)  # Check every 50ms

        # Chrome check timer - 5 seconds as requested
        if HAS_PSUTIL and HAS_WIN32:
            self.browser_timer = QTimer(self)
            self.browser_timer.timeout.connect(self.check_chrome_active)
            self.browser_timer.start(5000)  # Check every 5 seconds

    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        try:
            self.exit_shortcut = QShortcut(QKeySequence("Escape"), self)
            self.exit_shortcut.activated.connect(self.safe_exit)
        except Exception as e:
            print(f"Shortcut setup error: {e}")

    def detect_click(self):
        """Detect mouse clicks using win32api - simple and reliable"""
        try:
            if not HAS_WIN32API:
                return

            # Check if left mouse button is pressed
            current_mouse_state = win32api.GetKeyState(win32con.VK_LBUTTON) < 0

            # Detect button press (transition from not pressed to pressed)
            if current_mouse_state and not self.last_mouse_state:
                # Only trigger click animations during normal states
                if (not self.movement_locked and
                    self.chrome_state == "none" and
                    self.cur_name not in [ENJOY, WATCHING, RUN2SLOW_L, RUN2SLOW_R]):

                    current_time = time.time()

                    # Check if this is a double click
                    if current_time - self.last_click_time < self.double_click_threshold:
                        if CLICK_DOUBLE in self.movies:
                            self.reset_idle_sequence()  # Stop idle sequence
                            self.set_animation(CLICK_DOUBLE)
                            # Start timer to force stop after exact duration
                            self.click_timer_double.start(CLICK_DOUBLE_DURATION)
                            print("🖱️ Double click detected")
                    else:
                        if CLICK_SINGLE in self.movies:
                            self.reset_idle_sequence()  # Stop idle sequence
                            self.set_animation(CLICK_SINGLE)
                            # Start timer to force stop after exact duration
                            self.click_timer_single.start(CLICK_SINGLE_DURATION)
                            print("🖱️ Single click detected")

                    self.last_click_time = current_time

            self.last_mouse_state = current_mouse_state

        except Exception as e:
            print(f"Click detection error: {e}")

    def reset_idle_sequence(self):
        """Reset idle animation sequence to beginning"""
        self.idle_sequence_index = 0
        self.idle_timer.stop()
        print("🔄 Idle sequence reset to beginning")

    def play_next_idle(self):
        """Play next animation in idle sequence with proper timing"""
        if not self.cursor_stationary or self.movement_locked or self.chrome_state != "none":
            return

        # Play current idle animation
        if self.idle_sequence_index < len(IDLE_CLIPS):
            animation = IDLE_CLIPS[self.idle_sequence_index]
            self.set_animation(animation)
            print(f"🎬 Playing {animation} (index {self.idle_sequence_index})")

            # Move to next animation
            self.idle_sequence_index += 1

            # If we've reached idle_5, keep looping it
            if self.idle_sequence_index >= len(IDLE_CLIPS):
                self.idle_sequence_index = len(IDLE_CLIPS) - 1  # Stay on idle_5

            # Schedule next animation
            self.schedule_next_idle()

    def schedule_next_idle(self):
        """Schedule the next idle animation"""
        if not self.cursor_stationary or self.chrome_state != "none":
            return

        # Get timeout for current animation
        if self.idle_sequence_index < len(IDLE_TIMEOUTS):
            timeout = IDLE_TIMEOUTS[self.idle_sequence_index - 1] if self.idle_sequence_index > 0 else IDLE_TIMEOUTS[0]
        else:
            timeout = IDLE_TIMEOUTS[-2]  # Use timeout 4 for idle_5 loops

        if timeout > 0:
            print(f"⏰ Next idle in {timeout/1000:.1f} seconds")
            self.idle_timer.start(timeout)

    def start_idle_sequence(self):
        """Start the idle animation sequence"""
        if self.cursor_stationary and self.chrome_state == "none" and not self.movement_locked:
            print("🎬 Starting idle sequence")
            self.idle_sequence_index = 0
            self.play_next_idle()

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
                    pass

            # Scale based on animation type
            if clip_name in RUNNING_ANIMS:
                movie.setScaledSize(SIZE_RUN)
            else:
                movie.setScaledSize(SIZE_IDLE)

            # Set new movie
            self.cur_name = clip_name
            self.current_movie = movie
            self.setMovie(movie)

            # Connect finished signal for special animations (excluding click animations since we handle them with timers)
            if clip_name in [ENJOY, WATCHING, RUN2SLOW_L, RUN2SLOW_R]:
                movie.finished.connect(lambda: self.on_animation_finished(clip_name))

            movie.start()

        except Exception as e:
            print(f"Animation error: {e}")

    def on_animation_finished(self, clip_name):
        """Handle animation completion"""
        try:
            if clip_name == ENJOY:
                # After enjoying, start watching animation
                self.chrome_state = "watching"
                if WATCHING in self.movies:
                    self.set_animation(WATCHING)

            elif clip_name == WATCHING:
                # Loop watching animation while Chrome is active
                if self.is_chrome_active and self.chrome_state == "watching":
                    if WATCHING in self.movies:
                        self.set_animation(WATCHING)
                else:
                    # Chrome no longer active, return to idle
                    self.chrome_state = "none"
                    self.chrome_fixed_position = None
                    self.return_to_idle_1()

            elif clip_name in [RUN2SLOW_L, RUN2SLOW_R]:
                self.movement_locked = False
                self.running_idle_start_time = None
                self.return_to_idle_1()

        except Exception as e:
            print(f"Animation finish error: {e}")

    def force_stop_click_animation(self, expected_clip):
        """Force stop click animation after exact duration and return to idle_animation_1"""
        try:
            # Only stop if we're still playing the expected click animation
            if self.cur_name == expected_clip:
                print(f"Force stopping {expected_clip} after precise duration")
                self.return_to_idle_1()
        except Exception as e:
            print(f"Force stop error: {e}")

    def return_to_idle(self):
        """Return to idle sequence from beginning"""
        self.reset_idle_sequence()
        if IDLE_CLIPS[0] in self.movies:
            self.set_animation(IDLE_CLIPS[0])
            # Start idle sequence after a short delay
            QTimer.singleShot(1000, self.start_idle_sequence)

    def return_to_idle_1(self):
        """Return directly to idle_animation_1 (used for click animations)"""
        self.reset_idle_sequence()
        if IDLE_CLIPS[0] in self.movies:
            self.set_animation(IDLE_CLIPS[0])
            print("🔄 Returned to idle_animation_1")

    def start_watching(self):
        """Start watching animation after enjoy timer"""
        self.chrome_state = "watching"
        if WATCHING in self.movies:
            self.set_animation(WATCHING)

    def is_chrome_active_window(self):
        """Check if Chrome is the active window"""
        if not HAS_WIN32:
            return False

        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd == 0:
                return False

            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            try:
                process = psutil.Process(pid)
                process_name = process.name().lower()
                return process_name in CHROME_NAMES

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False

        except Exception:
            return False

    def check_chrome_active(self):
        """Check if Chrome is active and handle enjoy → watching sequence"""
        try:
            chrome_active = self.is_chrome_active_window()
            current_time = time.time()

            # Chrome just became active
            if chrome_active and not self.is_chrome_active:
                print("🌐 Chrome detected!")
                self.is_chrome_active = True
                self.chrome_first_detected_time = current_time

                # Store current position for Chrome animations
                self.chrome_fixed_position = (self.x(), self.y())

                # Start with enjoying animation
                self.chrome_state = "enjoying"
                self.reset_idle_sequence()  # Stop idle sequence

                if ENJOY in self.movies:
                    self.set_animation(ENJOY)
                    # Start timer for exact duration of enjoy animation
                    self.enjoy_timer.start(ENJOY_DURATION)

            # Chrome is no longer active
            elif not chrome_active and self.is_chrome_active:
                print("🌐 Chrome closed")
                self.is_chrome_active = False
                self.chrome_state = "none"
                self.chrome_first_detected_time = None
                self.chrome_fixed_position = None

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
                if self.cursor_stationary:
                    self.cursor_stationary = False
                    # Reset idle sequence when cursor starts moving
                    if self.cur_name in IDLE_CLIPS and self.chrome_state == "none":
                        self.reset_idle_sequence()
            else:
                # Check if cursor has been stationary
                if time.time() - self.last_cursor_move_time > 1.0:
                    if not self.cursor_stationary:
                        self.cursor_stationary = True
                        # Start idle sequence
                        if (self.chrome_state == "none" and not self.movement_locked
                            and self.cur_name == IDLE_CLIPS[0]):
                            self.start_idle_sequence()

            # Handle Chrome mode positioning
            if self.chrome_state in ["enjoying", "watching"] and self.chrome_fixed_position:
                # Stay at fixed position during Chrome animations
                self.move(self.chrome_fixed_position[0], self.chrome_fixed_position[1])
                self.last_cursor_pos = cursor_pos
                return

            # Skip movement logic for special animations or when locked
            if (self.cur_name in (CLICK_SINGLE, CLICK_DOUBLE, ENJOY, WATCHING)
                or self.movement_locked):
                self.last_cursor_pos = cursor_pos
                return

            # Calculate cursor speed and movement
            dx = cursor_pos.x - self.last_cursor_pos.x
            elapsed_ms = max(1, self.vel_timer.restart())
            cursor_speed = abs(dx) / (elapsed_ms / 1000.0)

            # Calculate distance between cursor and stickman
            distance_to_cursor = abs(cursor_pos.x - self.stickman_x)

            # Update stickman position
            if distance_to_cursor > 20:
                if cursor_pos.x > self.stickman_x:
                    new_direction = "right"
                else:
                    new_direction = "left"

                # Check if direction changed
                if new_direction != self.current_direction and self.cur_name in RUNNING_ANIMS:
                    self.movement_locked = False
                    self.running_idle_start_time = None

                self.current_direction = new_direction

                # Move stickman towards cursor with lag
                move_amount = distance_to_cursor * STICKMAN_FOLLOW_SPEED * (elapsed_ms / 1000.0)
                if cursor_pos.x > self.stickman_x:
                    self.stickman_x += move_amount
                else:
                    self.stickman_x -= move_amount

                # Don't overshoot
                if abs(cursor_pos.x - self.stickman_x) < move_amount:
                    self.stickman_x = cursor_pos.x

            # Update stickman visual position
            screen_width = pyautogui.size().width
            new_x = max(0, min(int(self.stickman_x) - self.width() // 2,
                             screen_width - self.width()))
            self.move(new_x, self.fixed_y)

            # Animation logic
            if cursor_speed >= FAST_CURSOR_SPEED and cursor_moved and distance_to_cursor > 100:
                # Fast cursor movement - running
                run_anim = RUN_RIGHT if self.current_direction == "right" else RUN_LEFT
                if run_anim in self.movies and not self.movement_locked:
                    self.set_animation(run_anim)
                    self.movement_locked = False
                    QTimer.singleShot(800, self.start_running_idle)

            elif cursor_moved and distance_to_cursor > 20:
                # Normal cursor movement - walking
                walk_anim = WALK_RIGHT if self.current_direction == "right" else WALK_LEFT
                if walk_anim in self.movies and not self.movement_locked:
                    self.set_animation(walk_anim)

            elif distance_to_cursor <= 30:
                # Stickman caught up
                if self.cur_name in [RUN_LEFT, RUN_RIGHT, WALK_LEFT, WALK_RIGHT]:
                    self.return_to_idle()
                elif self.cur_name in [RUN_IDLE_L, RUN_IDLE_R]:
                    if (self.running_idle_start_time and
                        time.time() - self.running_idle_start_time > RUN_IDLE_MAX_TIME):
                        slow_anim = RUN2SLOW_R if self.current_direction == "right" else RUN2SLOW_L
                        if slow_anim in self.movies:
                            self.movement_locked = True
                            self.set_animation(slow_anim)

            self.last_cursor_pos = cursor_pos

        except Exception as e:
            print(f"State update error: {e}")

    def start_running_idle(self):
        """Start running idle animation"""
        try:
            if self.cur_name in [RUN_LEFT, RUN_RIGHT] and not self.movement_locked:
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
            if hasattr(self, 'enjoy_timer'):
                self.enjoy_timer.stop()
            if hasattr(self, 'click_timer'):
                self.click_timer.stop()
            if hasattr(self, 'click_timer_single'):
                self.click_timer_single.stop()
            if hasattr(self, 'click_timer_double'):
                self.click_timer_double.stop()

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