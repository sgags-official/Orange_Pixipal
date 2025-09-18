"""
This is the main source code of the Orange Pixipal
The original design of the Orange Pixipal is heavily inspired from the TSC from the ALan Becker's Animated Series
The inspiration from those animations led me to coding these following lines
"""

import sys
import time
import itertools
import pathlib
import traceback
from PyQt5.QtCore import Qt, QTimer, QSize, QElapsedTimer, QThread, pyqtSignal
from PyQt5.QtGui import QMovie, QKeySequence, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QShortcut

# Safe Imports with Fallbacks
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

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    print("Error: pyautogui is required")
    sys.exit(1)

try:
    import win32api
    import win32con

    HAS_WIN32API = True
except ImportError:
    HAS_WIN32API = False
    print("Warning: win32api not available, click detection disabled")

ASSET_DIR = pathlib.Path(__file__).parent

# Animation Constants (unchanged)
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

IDLE_CLIPS = [IDLE_CLIP_1, IDLE_CLIP_2, IDLE_CLIP_3, IDLE_CLIP_4, IDLE_CLIP_5]

# Optimized Constants
WALK_VEL = 50
FAST_CURSOR_SPEED = 400
RUN_IDLE_MAX_TIME = 5
STICKMAN_FOLLOW_SPEED = 3.0

# Timing constants
IDLE_ANIMATION_TIMEOUT_1 = int(40.9 * 1000)
IDLE_ANIMATION_TIMEOUT_2 = int(4.266666 * 1000)
IDLE_ANIMATION_TIMEOUT_3 = int(31.5 * 1000)
IDLE_ANIMATION_TIMEOUT_4 = int(8.833333 * 1000)
IDLE_ANIMATION_TIMEOUT_5 = 0

ENJOY_DURATION = int(0.766666 * 1000)
CLICK_SINGLE_DURATION = int(0.7666666 * 1000)
CLICK_DOUBLE_DURATION = int(1.1333333 * 1000)

IDLE_TIMEOUTS = [
    IDLE_ANIMATION_TIMEOUT_1,
    IDLE_ANIMATION_TIMEOUT_2,
    IDLE_ANIMATION_TIMEOUT_3,
    IDLE_ANIMATION_TIMEOUT_4,
    IDLE_ANIMATION_TIMEOUT_5
]

CHROME_NAMES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"}  # Added more browsers
RUNNING_ANIMS = {RUN_LEFT, RUN_RIGHT, RUN_IDLE_L, RUN_IDLE_R, RUN2SLOW_L, RUN2SLOW_R}

# Optimized display sizes
SIZE_IDLE = QSize(100, 200)
SIZE_RUN = QSize(150, 200)


# Background thread for system monitoring
class SystemMonitorThread(QThread):
    chrome_status_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.running = True
        self.check_interval = 2.0  # Reduced from 5 seconds for better responsiveness

    def run(self):
        last_chrome_state = False

        while self.running:
            try:
                current_chrome_state = self.is_chrome_active_window()

                # Only emit signal if state changed
                if current_chrome_state != last_chrome_state:
                    self.chrome_status_changed.emit(current_chrome_state)
                    last_chrome_state = current_chrome_state

                self.msleep(int(self.check_interval * 1000))

            except Exception as e:
                print(f"System monitor error: {e}")
                self.msleep(1000)

    def is_chrome_active_window(self):
        """Optimized Chrome detection"""
        if not HAS_WIN32 or not HAS_PSUTIL:
            return False

        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd == 0:
                return False

            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            # Cache process info to avoid repeated lookups
            if not hasattr(self, '_process_cache'):
                self._process_cache = {}

            if pid not in self._process_cache:
                try:
                    process = psutil.Process(pid)
                    self._process_cache[pid] = process.name().lower()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    return False

            return self._process_cache[pid] in CHROME_NAMES

        except Exception:
            return False

    def stop(self):
        self.running = False
        self.quit()
        self.wait()


# Optimized movie loading function
def safe_movie(path, preload_frames=True):
    """Create a QMovie with optimized loading"""
    try:
        if not path.exists():
            print(f"⚠ Missing asset: {path.name}")
            return None

        mv = QMovie(str(path))
        if not mv.isValid():
            print(f"⚠ Invalid movie file: {path.name}")
            return None

        # Optimize caching strategy
        mv.setCacheMode(QMovie.CacheAll)

        # Pre-jump to first frame for faster startup
        if preload_frames:
            mv.jumpToFrame(0)

        return mv

    except Exception as e:
        print(f"⚠ Error loading {path.name}: {e}")
        return None


class OptimizedStickmanOverlay(QLabel):
    def __init__(self):
        super().__init__()

        # Performance tracking
        self.frame_count = 0
        self.last_fps_time = time.time()

        # Optimized state tracking
        self.movies = {}
        self.scaled_movies = {}  # Cache for scaled movies
        self.idle_sequence_index = 0
        self.cur_name = None
        self.current_movie = None

        # Movement optimization
        self.last_cursor_pos = None
        self.stickman_x = 500.0  # Use float for smoother movement
        self.target_x = 500.0
        self.vel_timer = QElapsedTimer()
        self.fixed_y = 0

        # Chrome state
        self.is_chrome_active = False
        self.chrome_state = "none"
        self.chrome_first_detected_time = None
        self.chrome_fixed_position = None

        # Running state
        self.running_idle_start_time = None
        self.current_direction = "right"
        self.movement_locked = False

        # Optimized cursor tracking
        self.last_cursor_move_time = time.time()
        self.cursor_stationary = False
        self.cursor_speed_history = []  # For smoothed speed calculation

        # Click detection optimization
        self.last_click_time = 0
        self.double_click_threshold = 0.4
        self.last_mouse_state = False
        self.click_debounce_time = 0.1  # Prevent rapid clicks
        self.last_processed_click = 0

        # Timers
        self.setup_timers()

        # Background thread for system monitoring
        self.system_monitor = SystemMonitorThread()
        self.system_monitor.chrome_status_changed.connect(self.on_chrome_status_changed)

        try:
            self.setup_ui()
            self.load_animations()
            self.setup_position()
            self.setup_shortcuts()

            # Start background monitoring
            self.system_monitor.start()

            # Start with first idle animation
            self.set_animation(IDLE_CLIPS[0])
            self.show()

        except Exception as e:
            print(f"Initialization error: {e}")
            traceback.print_exc()
            self.cleanup()

    def setup_ui(self):
        """Optimized UI setup"""
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

        # Enable hardware acceleration if available
        self.setAttribute(Qt.WA_NativeWindow, True)

    def load_animations(self):
        """Optimized animation loading with caching"""
        all_clips = list(itertools.chain(IDLE_CLIPS, [
            WALK_LEFT, WALK_RIGHT, RUN_LEFT, RUN_RIGHT,
            RUN_IDLE_L, RUN_IDLE_R, RUN2SLOW_L, RUN2SLOW_R,
            CLICK_SINGLE, CLICK_DOUBLE, ENJOY, WATCHING
        ]))

        print("🎬 Loading animations...")
        self.movies = {}
        self.scaled_movies = {}

        # Load movies in priority order (idle first, then common animations)
        priority_clips = IDLE_CLIPS + [WALK_LEFT, WALK_RIGHT, CLICK_SINGLE, CLICK_DOUBLE]

        for name in priority_clips:
            movie = safe_movie(ASSET_DIR / name, preload_frames=True)
            if movie:
                self.movies[name] = movie
                # Pre-cache scaled versions
                self.cache_scaled_movie(name, movie)

        # Load remaining animations
        for name in all_clips:
            if name not in self.movies:
                movie = safe_movie(ASSET_DIR / name, preload_frames=False)
                if movie:
                    self.movies[name] = movie

        available_idles = [clip for clip in IDLE_CLIPS if clip in self.movies]
        if not available_idles:
            raise Exception("No idle animations found!")

        print(f"✅ Loaded {len(self.movies)} animations")

    def cache_scaled_movie(self, name, movie):
        """Cache scaled versions of movies for faster switching"""
        if name in RUNNING_ANIMS:
            movie.setScaledSize(SIZE_RUN)
            self.scaled_movies[name] = SIZE_RUN
        else:
            movie.setScaledSize(SIZE_IDLE)
            self.scaled_movies[name] = SIZE_IDLE

    def setup_timers(self):
        """Optimized timer setup"""
        # Main animation timer - higher frequency for smoother animation
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_state)
        self.anim_timer.start(16)  # ~60 FPS instead of 30 FPS

        # Idle animation timer
        self.idle_timer = QTimer()
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self.play_next_idle)

        # Chrome enjoy timer
        self.enjoy_timer = QTimer()
        self.enjoy_timer.setSingleShot(True)
        self.enjoy_timer.timeout.connect(self.start_watching)

        # Click animation timers
        self.click_timer_single = QTimer()
        self.click_timer_single.setSingleShot(True)
        self.click_timer_single.timeout.connect(lambda: self.force_stop_click_animation(CLICK_SINGLE))

        self.click_timer_double = QTimer()
        self.click_timer_double.setSingleShot(True)
        self.click_timer_double.timeout.connect(lambda: self.force_stop_click_animation(CLICK_DOUBLE))

        # Optimized click detection timer
        if HAS_WIN32API:
            self.click_timer = QTimer(self)
            self.click_timer.timeout.connect(self.detect_click)
            self.click_timer.start(33)  # Reduced from 50ms for better responsiveness

    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        try:
            self.exit_shortcut = QShortcut(QKeySequence("Escape"), self)
            self.exit_shortcut.activated.connect(self.safe_exit)

            # Add debug shortcut for performance info
            self.debug_shortcut = QShortcut(QKeySequence("F12"), self)
            self.debug_shortcut.activated.connect(self.show_debug_info)

        except Exception as e:
            print(f"Shortcut setup error: {e}")

    def show_debug_info(self):
        """Show performance debug information"""
        current_time = time.time()
        elapsed = current_time - self.last_fps_time
        if elapsed > 0:
            fps = self.frame_count / elapsed
            print(f"🔧 FPS: {fps:.1f}, Animation: {self.cur_name}, Chrome: {self.chrome_state}")

    def on_chrome_status_changed(self, is_active):
        """Handle Chrome status change from background thread"""
        current_time = time.time()

        if is_active and not self.is_chrome_active:
            print("🌐 Chrome detected!")
            self.is_chrome_active = True
            self.chrome_first_detected_time = current_time
            self.chrome_fixed_position = (self.x(), self.y())
            self.chrome_state = "enjoying"
            self.reset_idle_sequence()

            if ENJOY in self.movies:
                self.set_animation(ENJOY)
                self.enjoy_timer.start(ENJOY_DURATION)

        elif not is_active and self.is_chrome_active:
            print("🌐 Chrome closed")
            self.is_chrome_active = False
            self.chrome_state = "none"
            self.chrome_first_detected_time = None
            self.chrome_fixed_position = None

            if self.cur_name in (ENJOY, WATCHING):
                self.return_to_idle_1()

    def detect_click(self):
        """Optimized click detection with debouncing"""
        try:
            if not HAS_WIN32API:
                return

            current_time = time.time()

            # Debounce rapid clicks
            if current_time - self.last_processed_click < self.click_debounce_time:
                return

            current_mouse_state = win32api.GetKeyState(win32con.VK_LBUTTON) < 0

            if current_mouse_state and not self.last_mouse_state:
                if (not self.movement_locked and
                        self.chrome_state == "none" and
                        self.cur_name not in [ENJOY, WATCHING, RUN2SLOW_L, RUN2SLOW_R]):

                    # Check for double click
                    if current_time - self.last_click_time < self.double_click_threshold:
                        if CLICK_DOUBLE in self.movies:
                            self.reset_idle_sequence()
                            self.set_animation(CLICK_DOUBLE)
                            self.click_timer_double.start(CLICK_DOUBLE_DURATION)
                    else:
                        if CLICK_SINGLE in self.movies:
                            self.reset_idle_sequence()
                            self.set_animation(CLICK_SINGLE)
                            self.click_timer_single.start(CLICK_SINGLE_DURATION)

                    self.last_click_time = current_time
                    self.last_processed_click = current_time

            self.last_mouse_state = current_mouse_state

        except Exception as e:
            print(f"Click detection error: {e}")

    def set_animation(self, clip_name):
        """Optimized animation switching"""
        try:
            if clip_name == self.cur_name or clip_name not in self.movies:
                return

            movie = self.movies[clip_name]
            if not movie or not movie.isValid():
                return

            # Stop current movie
            if self.current_movie:
                self.current_movie.stop()
                try:
                    self.current_movie.finished.disconnect()
                except:
                    pass

            # Use cached scaling if available
            if clip_name not in self.scaled_movies:
                self.cache_scaled_movie(clip_name, movie)

            # Set new movie
            self.cur_name = clip_name
            self.current_movie = movie
            self.setMovie(movie)

            # Connect signals only for necessary animations
            if clip_name in [ENJOY, WATCHING, RUN2SLOW_L, RUN2SLOW_R]:
                movie.finished.connect(lambda: self.on_animation_finished(clip_name))

            movie.start()

        except Exception as e:
            print(f"Animation error: {e}")

    def update_state(self):
        """Optimized main update loop"""
        try:
            # Performance tracking
            self.frame_count += 1
            current_time = time.time()

            if current_time - self.last_fps_time > 5.0:  # Reset every 5 seconds
                self.last_fps_time = current_time
                self.frame_count = 0

            if not HAS_PYAUTOGUI:
                return

            # Get cursor position (cached to avoid repeated calls)
            try:
                cursor_pos = pyautogui.position()
            except Exception:
                return

            if not self.last_cursor_pos:
                self.last_cursor_pos = cursor_pos
                return

            # Optimized cursor movement detection
            dx = cursor_pos.x - self.last_cursor_pos.x
            dy = cursor_pos.y - self.last_cursor_pos.y
            cursor_moved = abs(dx) > 1 or abs(dy) > 1  # Threshold to avoid micro-movements

            if cursor_moved:
                self.last_cursor_move_time = current_time
                if self.cursor_stationary:
                    self.cursor_stationary = False
                    if self.cur_name in IDLE_CLIPS and self.chrome_state == "none":
                        self.reset_idle_sequence()
            else:
                # Cursor stationary check
                if current_time - self.last_cursor_move_time > 1.0:
                    if not self.cursor_stationary:
                        self.cursor_stationary = True
                        if (self.chrome_state == "none" and not self.movement_locked
                                and self.cur_name == IDLE_CLIPS[0]):
                            self.start_idle_sequence()

            # Handle Chrome mode
            if self.chrome_state in ["enjoying", "watching"] and self.chrome_fixed_position:
                if self.x() != self.chrome_fixed_position[0] or self.y() != self.chrome_fixed_position[1]:
                    self.move(self.chrome_fixed_position[0], self.chrome_fixed_position[1])
                self.last_cursor_pos = cursor_pos
                return

            # Skip movement for special animations
            if (self.cur_name in (CLICK_SINGLE, CLICK_DOUBLE, ENJOY, WATCHING)
                    or self.movement_locked):
                self.last_cursor_pos = cursor_pos
                return

            # Optimized movement calculation
            elapsed_ms = max(1, self.vel_timer.restart())
            elapsed_s = elapsed_ms / 1000.0

            # Smooth cursor speed calculation
            if cursor_moved:
                cursor_speed = abs(dx) / elapsed_s
                self.cursor_speed_history.append(cursor_speed)
                if len(self.cursor_speed_history) > 5:  # Keep last 5 samples
                    self.cursor_speed_history.pop(0)
                avg_cursor_speed = sum(self.cursor_speed_history) / len(self.cursor_speed_history)
            else:
                avg_cursor_speed = 0

            # Smooth stickman movement
            distance_to_cursor = abs(cursor_pos.x - self.stickman_x)

            if distance_to_cursor > 20:
                # Determine direction
                new_direction = "right" if cursor_pos.x > self.stickman_x else "left"

                if new_direction != self.current_direction and self.cur_name in RUNNING_ANIMS:
                    self.movement_locked = False
                    self.running_idle_start_time = None

                self.current_direction = new_direction

                # Smooth movement with interpolation
                move_amount = min(distance_to_cursor * STICKMAN_FOLLOW_SPEED * elapsed_s, distance_to_cursor)

                if cursor_pos.x > self.stickman_x:
                    self.stickman_x += move_amount
                else:
                    self.stickman_x -= move_amount

            # Update visual position with smoother movement
            screen_width = pyautogui.size().width
            target_screen_x = max(0, min(int(self.stickman_x) - self.width() // 2,
                                         screen_width - self.width()))

            # Only move if position actually changed
            if abs(target_screen_x - self.x()) > 1:
                self.move(target_screen_x, self.fixed_y)

            # Optimized animation logic
            if avg_cursor_speed >= FAST_CURSOR_SPEED and cursor_moved and distance_to_cursor > 100:
                run_anim = RUN_RIGHT if self.current_direction == "right" else RUN_LEFT
                if run_anim in self.movies and not self.movement_locked:
                    self.set_animation(run_anim)
                    self.movement_locked = False
                    QTimer.singleShot(800, self.start_running_idle)

            elif cursor_moved and distance_to_cursor > 20:
                walk_anim = WALK_RIGHT if self.current_direction == "right" else WALK_LEFT
                if walk_anim in self.movies and not self.movement_locked:
                    self.set_animation(walk_anim)

            elif distance_to_cursor <= 30:
                if self.cur_name in [RUN_LEFT, RUN_RIGHT, WALK_LEFT, WALK_RIGHT]:
                    self.return_to_idle()
                elif self.cur_name in [RUN_IDLE_L, RUN_IDLE_R]:
                    if (self.running_idle_start_time and
                            current_time - self.running_idle_start_time > RUN_IDLE_MAX_TIME):
                        slow_anim = RUN2SLOW_R if self.current_direction == "right" else RUN2SLOW_L
                        if slow_anim in self.movies:
                            self.movement_locked = True
                            self.set_animation(slow_anim)

            self.last_cursor_pos = cursor_pos

        except Exception as e:
            print(f"State update error: {e}")

    # [Rest of the methods remain largely the same but with minor optimizations]

    def reset_idle_sequence(self):
        """Reset idle animation sequence"""
        self.idle_sequence_index = 0
        self.idle_timer.stop()

    def play_next_idle(self):
        """Play next idle animation"""
        if not self.cursor_stationary or self.movement_locked or self.chrome_state != "none":
            return

        if self.idle_sequence_index < len(IDLE_CLIPS):
            animation = IDLE_CLIPS[self.idle_sequence_index]
            self.set_animation(animation)
            self.idle_sequence_index += 1

            if self.idle_sequence_index >= len(IDLE_CLIPS):
                self.idle_sequence_index = len(IDLE_CLIPS) - 1

            self.schedule_next_idle()

    def schedule_next_idle(self):
        """Schedule next idle animation"""
        if not self.cursor_stationary or self.chrome_state != "none":
            return

        timeout_index = max(0, self.idle_sequence_index - 1)
        if timeout_index < len(IDLE_TIMEOUTS):
            timeout = IDLE_TIMEOUTS[timeout_index]
            if timeout > 0:
                self.idle_timer.start(timeout)

    def start_idle_sequence(self):
        """Start idle sequence"""
        if self.cursor_stationary and self.chrome_state == "none" and not self.movement_locked:
            self.idle_sequence_index = 0
            self.play_next_idle()

    def return_to_idle_1(self):
        """Return to first idle animation"""
        self.reset_idle_sequence()
        if IDLE_CLIPS[0] in self.movies:
            self.set_animation(IDLE_CLIPS[0])

    def return_to_idle(self):
        """Return to idle sequence"""
        self.reset_idle_sequence()
        if IDLE_CLIPS[0] in self.movies:
            self.set_animation(IDLE_CLIPS[0])
            QTimer.singleShot(1000, self.start_idle_sequence)

    def start_running_idle(self):
        """Start running idle"""
        try:
            if self.cur_name in [RUN_LEFT, RUN_RIGHT] and not self.movement_locked:
                idle_anim = RUN_IDLE_R if self.current_direction == "right" else RUN_IDLE_L
                if idle_anim in self.movies:
                    self.set_animation(idle_anim)
                    self.running_idle_start_time = time.time()
        except Exception as e:
            print(f"Running idle error: {e}")

    def start_watching(self):
        """Start watching animation"""
        self.chrome_state = "watching"
        if WATCHING in self.movies:
            self.set_animation(WATCHING)

    def on_animation_finished(self, clip_name):
        """Handle animation completion"""
        try:
            if clip_name == ENJOY:
                self.chrome_state = "watching"
                if WATCHING in self.movies:
                    self.set_animation(WATCHING)
            elif clip_name == WATCHING:
                if self.is_chrome_active and self.chrome_state == "watching":
                    if WATCHING in self.movies:
                        self.set_animation(WATCHING)
                else:
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
        """Force stop click animation"""
        try:
            if self.cur_name == expected_clip:
                self.return_to_idle_1()
        except Exception as e:
            print(f"Force stop error: {e}")

    def setup_position(self):
        """Setup initial position"""
        try:
            if HAS_PYAUTOGUI:
                screen_size = pyautogui.size()
                self.fixed_y = screen_size.height - SIZE_RUN.height() - 50
                cursor_pos = pyautogui.position()
                self.last_cursor_pos = cursor_pos
                self.stickman_x = float(cursor_pos.x)  # Use float for precision
                self.vel_timer.start()
        except Exception as e:
            print(f"Position setup error: {e}")
            self.fixed_y = 100
            self.last_cursor_pos = type('pos', (), {'x': 500, 'y': 100})()
            self.stickman_x = 500.0

    def cleanup(self):
        """Enhanced cleanup"""
        try:
            # Stop system monitor thread
            if hasattr(self, 'system_monitor'):
                self.system_monitor.stop()

            # Stop all timers
            timers = ['anim_timer', 'idle_timer', 'enjoy_timer', 'click_timer',
                      'click_timer_single', 'click_timer_double']
            for timer_name in timers:
                if hasattr(self, timer_name):
                    getattr(self, timer_name).stop()

            # Stop movies
            if self.current_movie:
                self.current_movie.stop()

            for movie in self.movies.values():
                if movie:
                    movie.stop()

        except Exception as e:
            print(f"Cleanup error: {e}")

    def safe_exit(self):
        """Safe application exit"""
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
    """Optimized main function"""
    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(True)

        def handle_exception(exc_type, exc_value, exc_traceback):
            print(f"Unhandled exception: {exc_type.__name__}: {exc_value}")
            traceback.print_exception(exc_type, exc_value, exc_traceback)

        sys.excepthook = handle_exception

        overlay = OptimizedStickmanOverlay()
        sys.exit(app.exec_())

    except Exception as e:
        print(f"Application error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()