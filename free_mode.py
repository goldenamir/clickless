"""Clickless - Free mode: relative cursor movement via keyboard (IJKL)

Provides continuous mouse movement, scrolling, and clicking
without the overlay, similar to Mouseless's free mode.
"""

import gi
gi.require_version('Gdk', '3.0')
from gi.repository import GLib
import time


class FreeMode:
    """Keyboard-driven relative mouse movement and scrolling."""

    def __init__(self, config, mouse_ctrl):
        self.mouse = mouse_ctrl
        self.active = False
        self._load_config(config)

        # Movement state
        self.move_keys = set()     # currently held movement keys
        self.speed_keys = set()    # held speed increase keys
        self.speed_dec = False     # speed decrease held
        self.move_velocity = [0.0, 0.0]
        self.scroll_keys = set()   # held scroll keys

        # Auto-off timer
        self.last_action_time = 0
        self._tick_id = None

    def _load_config(self, config):
        fm = config.get('behavior', {}).get('free_mode', {})
        self.base_speed = fm.get('base_move_speed', 8)
        self.speed_mult = fm.get('move_speed_multiplier', 2.5)
        self.easing = fm.get('movement_easing_factor', 0.2)
        self.base_wheel = fm.get('base_wheel_speed', 5)
        self.wheel_mult = fm.get('wheel_speed_multiplier', 3.0)
        self.wheel_easing = fm.get('wheel_easing_factor', 0.2)
        self.wheel_step = fm.get('wheel_step_size', 3)
        self.wheel_step_large = fm.get('wheel_step_size_large', 10)
        self.auto_off_sec = fm.get('auto_off_seconds', 10)

    def activate(self):
        if self.active:
            return
        self.active = True
        self.last_action_time = time.time()
        self.move_keys.clear()
        self.speed_keys.clear()
        self.scroll_keys.clear()
        self.speed_dec = False
        self.move_velocity = [0.0, 0.0]
        self._start_tick()
        print("Free mode ON")

    def deactivate(self):
        if not self.active:
            return
        self.active = False
        self._stop_tick()
        self.move_keys.clear()
        self.speed_keys.clear()
        self.scroll_keys.clear()
        print("Free mode OFF")

    def toggle(self):
        if self.active:
            self.deactivate()
        else:
            self.activate()

    # ── Key handling ─────────────────────────────────────────────

    def on_key_down(self, key_name):
        """Process key press in free mode. Returns True if consumed."""
        if not self.active:
            return False

        self.last_action_time = time.time()
        k = key_name.upper()

        # Movement
        if k == 'I':
            self.move_keys.add('up')
            return True
        elif k == 'K':
            self.move_keys.add('down')
            return True
        elif k == 'J':
            self.move_keys.add('left')
            return True
        elif k == 'L':
            self.move_keys.add('right')
            return True

        # Speed modifiers
        if k in ('S', 'D', 'F'):
            self.speed_keys.add(k)
            return True
        if k == 'A':
            self.speed_dec = True
            return True

        # Scrolling
        if k == 'M':
            self.scroll_keys.add('up')
            return True
        elif k in (',', 'COMMA'):
            self.scroll_keys.add('down')
            return True
        elif k in ('.', 'PERIOD'):
            self.scroll_keys.add('left')
            return True
        elif k in ('/', 'SLASH'):
            self.scroll_keys.add('right')
            return True

        # Clicking
        if k == 'SPACE':
            self.mouse.click('left')
            return True
        elif k == 'R':
            self.mouse.click('right')
            return True
        elif k == 'E':
            self.mouse.click('middle')
            return True
        elif k == 'Q':
            self.mouse.click('back')
            return True
        elif k == 'W':
            self.mouse.click('forward')
            return True

        return False

    def on_key_up(self, key_name):
        """Process key release in free mode. Returns True if consumed."""
        if not self.active:
            return False

        k = key_name.upper()

        if k == 'I':
            self.move_keys.discard('up')
            return True
        elif k == 'K':
            self.move_keys.discard('down')
            return True
        elif k == 'J':
            self.move_keys.discard('left')
            return True
        elif k == 'L':
            self.move_keys.discard('right')
            return True

        if k in ('S', 'D', 'F'):
            self.speed_keys.discard(k)
            return True
        if k == 'A':
            self.speed_dec = False
            return True

        if k == 'M':
            self.scroll_keys.discard('up')
            return True
        elif k in (',', 'COMMA'):
            self.scroll_keys.discard('down')
            return True
        elif k in ('.', 'PERIOD'):
            self.scroll_keys.discard('left')
            return True
        elif k in ('/', 'SLASH'):
            self.scroll_keys.discard('right')
            return True

        return False

    # ── Tick loop (16ms ≈ 60fps) ─────────────────────────────────

    def _start_tick(self):
        if self._tick_id is None:
            self._tick_id = GLib.timeout_add(16, self._tick)

    def _stop_tick(self):
        if self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None

    def _tick(self):
        if not self.active:
            return False

        # Auto-off check
        if self.auto_off_sec > 0:
            idle = time.time() - self.last_action_time
            if idle > self.auto_off_sec:
                self.deactivate()
                return False

        # Calculate speed
        speed = self.base_speed
        for _ in self.speed_keys:
            speed *= self.speed_mult
        if self.speed_dec:
            speed /= self.speed_mult

        # Target velocity
        tx, ty = 0.0, 0.0
        if 'up' in self.move_keys:
            ty -= speed
        if 'down' in self.move_keys:
            ty += speed
        if 'left' in self.move_keys:
            tx -= speed
        if 'right' in self.move_keys:
            tx += speed

        # Easing
        self.move_velocity[0] += (tx - self.move_velocity[0]) * self.easing
        self.move_velocity[1] += (ty - self.move_velocity[1]) * self.easing

        # Move
        dx = int(round(self.move_velocity[0]))
        dy = int(round(self.move_velocity[1]))
        if dx != 0 or dy != 0:
            self.mouse.move_relative(dx, dy)
            self.last_action_time = time.time()

        # Scrolling
        if self.scroll_keys:
            scroll_speed = self.base_wheel
            for _ in self.speed_keys:
                scroll_speed *= self.wheel_mult
            if self.speed_dec:
                scroll_speed /= self.wheel_mult
            amount = max(1, int(scroll_speed))

            for d in self.scroll_keys:
                if d in ('up', 'down'):
                    self.mouse.scroll(d, amount)
                elif d == 'left':
                    self.mouse.scroll('left', amount)
                elif d == 'right':
                    self.mouse.scroll('right', amount)
            self.last_action_time = time.time()

        return True  # keep ticking
