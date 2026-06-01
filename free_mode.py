"""Clickless - Free mode: relative cursor movement via keyboard (IJKL)

Provides continuous mouse movement, scrolling, and clicking
without the overlay, similar to Mouseless's free mode.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
import math
import time


class FreeModeIndicator(Gtk.Window):
    """Small on-screen indicator showing free mode state."""

    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.stick()

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self._width = 150
        self._height = 32
        self._text = "FREE MODE"
        self._color = (0.3, 1.0, 0.5, 0.9)
        self.set_default_size(self._width, self._height)
        self._position_on_screen()

        self.connect('draw', self._on_draw)
        self.connect('realize', self._make_click_through)

    def _position_on_screen(self):
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        pointer = seat.get_pointer() if seat else None
        if pointer:
            _, x, y = pointer.get_position()
            monitor = display.get_monitor_at_point(x, y)
        else:
            monitor = None
        if monitor is None:
            monitor = display.get_primary_monitor() or display.get_monitor(0)
        geom = monitor.get_geometry()
        self.move(geom.x + (geom.width - self._width) // 2, geom.y + 8)

    def _make_click_through(self, widget):
        region = cairo.Region(cairo.RectangleInt(0, 0, 0, 0))
        self.get_window().input_shape_combine_region(region, 0, 0)

    def _on_draw(self, widget, cr):
        w, h = self._width, self._height
        r = 10

        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.new_sub_path()
        cr.arc(w - r, r, r, -math.pi / 2, 0)
        cr.arc(w - r, h - r, r, 0, math.pi / 2)
        cr.arc(r, h - r, r, math.pi / 2, math.pi)
        cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.set_source_rgba(0.08, 0.08, 0.12, 0.85)
        cr.fill()

        cr.set_operator(cairo.OPERATOR_OVER)
        cr.select_font_face('monospace', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(14)
        ext = cr.text_extents(self._text)
        cr.move_to((w - ext.width) / 2, (h + ext.height) / 2)
        cr.set_source_rgba(*self._color)
        cr.show_text(self._text)
        return False

    def show_on(self):
        self._text = "FREE MODE"
        self._color = (0.3, 1.0, 0.5, 0.9)
        self._position_on_screen()
        self.show_all()
        self.queue_draw()

    def flash_off(self):
        """Briefly show 'FREE MODE OFF' then hide."""
        self._text = "FREE MODE OFF"
        self._color = (1.0, 0.4, 0.3, 0.9)
        self._position_on_screen()
        self.show_all()
        self.queue_draw()
        GLib.timeout_add(800, self._hide_after_flash)

    def _hide_after_flash(self):
        self.hide()
        return False


class FreeMode:
    """Keyboard-driven relative mouse movement and scrolling."""

    def __init__(self, config, mouse_ctrl):
        self.mouse = mouse_ctrl
        self.active = False
        self._load_config(config)
        self._indicator = FreeModeIndicator()

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
        self._indicator.show_on()
        print("Free mode ON")

    def deactivate(self):
        if not self.active:
            return
        self.active = False
        self._stop_tick()
        self.move_keys.clear()
        self.speed_keys.clear()
        self.scroll_keys.clear()
        self._indicator.flash_off()
        print("Free mode OFF")

    def finish_deactivate(self):
        """GTK-thread cleanup after active flag was already cleared."""
        self._stop_tick()
        self.move_keys.clear()
        self.speed_keys.clear()
        self.scroll_keys.clear()
        self._indicator.flash_off()
        print("Free mode OFF")
        return False  # Don't repeat GLib idle callback

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
            try:
                GLib.source_remove(self._tick_id)
            except Exception:
                pass
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
        for _ in list(self.speed_keys):
            speed *= self.speed_mult
        if self.speed_dec:
            speed /= self.speed_mult

        # Target velocity
        tx, ty = 0.0, 0.0
        for d in list(self.move_keys):
            if d == 'up':    ty -= speed
            if d == 'down':  ty += speed
            if d == 'left':  tx -= speed
            if d == 'right': tx += speed

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
        scroll_snapshot = list(self.scroll_keys)
        if scroll_snapshot:
            scroll_speed = self.base_wheel
            for _ in list(self.speed_keys):
                scroll_speed *= self.wheel_mult
            if self.speed_dec:
                scroll_speed /= self.wheel_mult
            amount = max(1, int(scroll_speed))

            for d in scroll_snapshot:
                if d in ('up', 'down'):
                    self.mouse.scroll(d, amount)
                elif d == 'left':
                    self.mouse.scroll('left', amount)
                elif d == 'right':
                    self.mouse.scroll('right', amount)
            self.last_action_time = time.time()

        return True  # keep ticking
