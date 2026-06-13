"""Clickless - Transparent GTK overlay with 2-letter hint grid

Supports:
- 2-letter hint grid: screen is covered with labeled cells, type 2 letters
  to jump cursor there. Then IJKL to refine position directionally.
- Virtual cursor display
- Drag & drop
- Multi-monitor
- Modifier clicks
- Continuous mode
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
import math
import time


class GridOverlay(Gtk.Window):

    def __init__(self, config, mouse_ctrl):
        super().__init__(type=Gtk.WindowType.POPUP)

        self.config = config
        self.mouse = mouse_ctrl
        self._load_config()

        # ── State ────────────────────────────────────────────────
        self.is_visible = False
        self.locked = False
        self.continuous_mode = False

        # Phase: 'hints' → typing first letter
        #        'filtered' → first letter typed, typing second
        #        'refine' → cell selected, IJKL to fine-tune
        self.phase = 'hints'
        self.first_letter = None
        self.selected_keys = []

        # Hint grid data (generated on show)
        self.hint_cols = 0
        self.hint_rows = 0
        self.hint_cell_w = 0
        self.hint_cell_h = 0
        self.hint_labels = {}    # (row, col) → "XY"
        self.hint_reverse = {}   # "XY" → (row, col)
        self.row_keys = ''       # first-letter chars (one per row)
        self.col_keys = ''       # second-letter chars (one per col)

        # Refinement state (directional shrinking after hint selection)
        self.sub_rect = [0, 0, 0, 0]
        self.sub_level = 0
        self.shrink_keys = {'I': 'up', 'K': 'down', 'J': 'left', 'L': 'right'}

        # Cursor
        self.virtual_cursor = None
        self.virtual_cursor_local = None

        # Action state
        self.action_type = 'click'
        self.mouse_button = 'left'
        self.click_count = 1
        self.last_click_time = 0

        # Monitor tracking
        self.current_monitor_idx = 0
        self.monitors = []
        self._detect_monitors()

        # ── Window setup ─────────────────────────────────────────
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
            print(f"DEBUG: RGBA visual set OK")
        else:
            print(f"DEBUG: NO RGBA visual - transparency won't work!")
            print(f"DEBUG: Screen is composited: {screen.is_composited()}")

        self._apply_monitor_geometry()

        self.connect('draw', self._on_draw)
        self.connect('key-press-event', self._on_key_press)
        self.connect('key-release-event', self._on_key_release)
        self.connect('realize', self._make_click_through)

    # ── Config loading ───────────────────────────────────────────

    def _load_config(self):
        # Style
        s = self.config.get('style', {})
        self.master_opacity = s.get('master_opacity', 1.0)
        self.overlay_opacity = s.get('overlay_opacity', 0.22)
        self.grid_color = s.get('grid_line_color', [0.3, 0.8, 0.5, 0.35])
        self.text_color = s.get('text_color', [1, 1, 1, 0.85])
        self.highlight_color = s.get('highlight_color', [0, 1, 0.53, 0.25])
        self.grid_line_width = s.get('grid_line_width', 1)
        self.font_name = s.get('font', 'monospace')
        self.font_weight = s.get('font_weight', 'bold')
        self.font_size_mult = s.get('font_size_multiplier', 1.0)
        self.cursor_size = s.get('cursor_size', 12)
        self.cursor_color = s.get('cursor_color', [1, 0.3, 0.3, 0.85])
        self.cursor_right_color = s.get('cursor_right_button_color', [0.3, 0.5, 1, 0.85])
        self.cursor_move_color = s.get('cursor_move_color', [0.3, 1, 0.5, 0.85])
        self.cursor_drag_color = s.get('cursor_drag_color', [1, 0.8, 0.2, 0.85])
        self.text_shadow = s.get('text_shadow_rgba', [0, 0, 0, 0.5])

        # Behavior
        b = self.config.get('behavior', {})
        self.hide_cursor_on_click = b.get('hide_cursor_on_click', False)
        self.hide_location = b.get('hide_location', 'bottom_left')
        self.move_duration = b.get('move_duration_ms', 80)
        self.multi_click_threshold = b.get('multi_click_threshold_ms', 300)
        self.continuous_mode = b.get('continuous_mode', False)
        self.initial_action_loc = b.get('initial_action_location', 'virtual_cursor')

    # ── Monitor management ───────────────────────────────────────

    def _detect_monitors(self):
        display = Gdk.Display.get_default()
        self.monitors = []
        n = display.get_n_monitors()
        primary_idx = 0
        for i in range(n):
            mon = display.get_monitor(i)
            geom = mon.get_geometry()
            self.monitors.append({
                'x': geom.x, 'y': geom.y,
                'w': geom.width, 'h': geom.height,
                'is_primary': mon.is_primary(),
            })
            if mon.is_primary():
                primary_idx = i
        self.current_monitor_idx = primary_idx
        if not self.monitors:
            self.monitors = [{'x': 0, 'y': 0, 'w': 1920, 'h': 1080, 'is_primary': True}]

    def _apply_monitor_geometry(self):
        m = self.monitors[self.current_monitor_idx]
        self.screen_x = m['x']
        self.screen_y = m['y']
        self.screen_w = m['w']
        self.screen_h = m['h']
        self.set_default_size(self.screen_w, self.screen_h)
        self.resize(self.screen_w, self.screen_h)
        self.move(self.screen_x, self.screen_y)

    def _make_click_through(self, widget):
        region = cairo.Region(cairo.RectangleInt(0, 0, 0, 0))
        self.get_window().input_shape_combine_region(region, 0, 0)

    def move_to_next_monitor(self):
        if len(self.monitors) < 2:
            return
        self.current_monitor_idx = (self.current_monitor_idx + 1) % len(self.monitors)
        self._apply_monitor_geometry()
        self._reset_state()
        self.queue_draw()

    def move_to_prev_monitor(self):
        if len(self.monitors) < 2:
            return
        self.current_monitor_idx = (self.current_monitor_idx - 1) % len(self.monitors)
        self._apply_monitor_geometry()
        self._reset_state()
        self.queue_draw()

    # ── Show / hide ──────────────────────────────────────────────

    def toggle(self):
        if self.is_visible:
            self.hide_overlay()
        else:
            self.show_overlay()

    def _monitor_for_cursor(self):
        """Return monitor index containing the current mouse cursor."""
        mx, my = self.mouse.get_position()
        for i, m in enumerate(self.monitors):
            if m['x'] <= mx < m['x'] + m['w'] and m['y'] <= my < m['y'] + m['h']:
                return i
        return self.current_monitor_idx

    def show_overlay(self):
        self._detect_monitors()
        self.current_monitor_idx = self._monitor_for_cursor()
        self._apply_monitor_geometry()
        self._start_monitor_idx = self.current_monitor_idx
        self._generate_hints()
        self._reset_state()
        self.is_visible = True
        self.show_all()
        self.present()
        GLib.timeout_add(50, self._grab_keyboard)
        self.queue_draw()

    def cycle_or_close(self):
        """Advance grid to next monitor; hide after the last one."""
        if len(self.monitors) < 2:
            self.hide_overlay()
            return
        next_idx = (self.current_monitor_idx + 1) % len(self.monitors)
        if next_idx == self._start_monitor_idx:
            # We've cycled through all monitors → close
            self.hide_overlay()
        else:
            self._ungrab_keyboard()
            self.hide()
            self.current_monitor_idx = next_idx
            self._apply_monitor_geometry()
            self._generate_hints()
            self._reset_state()
            self.show_all()
            self.present()
            GLib.timeout_add(50, self._grab_keyboard)
            self.queue_draw()

    def hide_overlay(self):
        self._ungrab_keyboard()
        self.is_visible = False
        self._reset_state()
        self.hide()

    def _reset_state(self):
        self.phase = 'hints'
        self.first_letter = None
        self.selected_keys = []
        self.sub_rect = [0, 0, self.screen_w, self.screen_h]
        self.sub_level = 0
        self.virtual_cursor = None
        self.virtual_cursor_local = None
        self.action_type = 'click'
        self.mouse_button = 'left'
        self.click_count = 1

    def _generate_hints(self):
        """Generate 2-letter labels for grid cells.
        First letter = row, second letter = column."""
        keys = 'ASDFGHJKLQWERTYUIOPZXCVBNM'
        target_cell_w = 80
        target_cell_h = 55

        self.hint_cols = min(len(keys), max(4, int(self.screen_w / target_cell_w)))
        self.hint_rows = min(len(keys), max(3, int(self.screen_h / target_cell_h)))
        self.hint_cell_w = self.screen_w / self.hint_cols
        self.hint_cell_h = self.screen_h / self.hint_rows

        self.row_keys = keys[:self.hint_rows]
        self.col_keys = keys[:self.hint_cols]

        self.hint_labels = {}
        self.hint_reverse = {}
        for r in range(self.hint_rows):
            for c in range(self.hint_cols):
                label = self.row_keys[r] + self.col_keys[c]
                self.hint_labels[(r, c)] = label
                self.hint_reverse[label] = (r, c)

    def _grab_keyboard(self):
        window = self.get_window()
        if window is None:
            return True

        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        seat.grab(
            window,
            Gdk.SeatCapabilities.KEYBOARD,
            True, None, None, None
        )

        # Click-through for mouse
        region = cairo.Region(cairo.RectangleInt(0, 0, 0, 0))
        window.input_shape_combine_region(region, 0, 0)
        return False

    def _ungrab_keyboard(self):
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        seat.ungrab()

    def _local_to_screen(self, lx, ly):
        return int(self.screen_x + lx), int(self.screen_y + ly)

    # ── Drawing ──────────────────────────────────────────────────

    def _on_draw(self, widget, cr):
        # Background
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, self.overlay_opacity * self.master_opacity)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        if self.phase in ('hints', 'filtered'):
            self._draw_hint_grid(cr)
        elif self.phase == 'refine':
            self._draw_refine(cr)

        # Virtual cursor
        if self.virtual_cursor_local:
            self._draw_virtual_cursor(cr)

        return False

    def _draw_hint_grid(self, cr):
        """Draw the 2-letter hint grid."""
        cw = self.hint_cell_w
        ch = self.hint_cell_h
        font_size = max(9, min(cw, ch) * 0.28 * self.font_size_mult)
        weight = cairo.FONT_WEIGHT_BOLD if self.font_weight == 'bold' else cairo.FONT_WEIGHT_NORMAL
        cr.select_font_face(self.font_name, cairo.FONT_SLANT_NORMAL, weight)

        for r in range(self.hint_rows):
            for c in range(self.hint_cols):
                x = c * cw
                y = r * ch
                label = self.hint_labels.get((r, c), '')

                is_match = True
                if self.phase == 'filtered' and self.first_letter:
                    is_match = label[0] == self.first_letter

                if not is_match:
                    # Dim non-matching cells
                    cr.set_source_rgba(0, 0, 0, 0.5 * self.master_opacity)
                    cr.rectangle(x, y, cw, ch)
                    cr.fill()
                    continue

                if self.phase == 'filtered':
                    # Highlight matching cells
                    cr.set_source_rgba(*self._apply_opacity(self.highlight_color))
                    cr.rectangle(x, y, cw, ch)
                    cr.fill()

                # Grid lines
                cr.set_source_rgba(*self._apply_opacity(self.grid_color))
                cr.set_line_width(0.5)
                cr.rectangle(x, y, cw, ch)
                cr.stroke()

                # Draw label
                if self.phase == 'filtered' and self.first_letter:
                    # Show first letter dimmed, second letter bright
                    self._draw_two_tone_label(cr, label, x, y, cw, ch, font_size)
                else:
                    self._draw_label(cr, label, x, y, cw, ch, font_size, self.text_color)

    def _draw_two_tone_label(self, cr, label, x, y, w, h, font_size):
        """Draw label with first char dim and second char bright."""
        cr.set_font_size(font_size)
        ext_full = cr.text_extents(label)
        ext_first = cr.text_extents(label[0])

        tx = x + (w - ext_full.width) / 2
        ty = y + (h + ext_full.height) / 2

        # First char (dim)
        cr.set_source_rgba(*self._apply_opacity([1, 1, 1, 0.35]))
        cr.move_to(tx, ty)
        cr.show_text(label[0])

        # Second char (bright)
        cr.set_source_rgba(*self._apply_opacity(self.text_color))
        cr.move_to(tx + ext_first.x_advance, ty)
        cr.show_text(label[1])

    def _draw_refine(self, cr):
        """Draw refinement mode: selected cell highlighted, IJKL cross."""
        rx, ry, rw, rh = self.sub_rect

        # Dim everything outside
        cr.set_source_rgba(0, 0, 0, 0.5 * self.master_opacity)
        cr.rectangle(0, 0, self.screen_w, ry)
        cr.fill()
        cr.rectangle(0, ry + rh, self.screen_w, self.screen_h - ry - rh)
        cr.fill()
        cr.rectangle(0, ry, rx, rh)
        cr.fill()
        cr.rectangle(rx + rw, ry, self.screen_w - rx - rw, rh)
        cr.fill()

        # Highlight current rect
        cr.set_source_rgba(*self._apply_opacity(self.highlight_color))
        cr.rectangle(rx, ry, rw, rh)
        cr.fill()

        # Draw cross
        mid_x = rx + rw / 2
        mid_y = ry + rh / 2
        cr.set_source_rgba(*self._apply_opacity(self.grid_color))
        cr.set_line_width(self.grid_line_width + 1)
        cr.move_to(mid_x, ry)
        cr.line_to(mid_x, ry + rh)
        cr.stroke()
        cr.move_to(rx, mid_y)
        cr.line_to(rx + rw, mid_y)
        cr.stroke()

        # Border
        cr.set_line_width(self.grid_line_width)
        cr.rectangle(rx, ry, rw, rh)
        cr.stroke()

        # Direction labels
        hw = rw / 2
        hh = rh / 2
        font_size = max(12, min(hw, hh) * 0.25 * self.font_size_mult)
        weight = cairo.FONT_WEIGHT_BOLD if self.font_weight == 'bold' else cairo.FONT_WEIGHT_NORMAL
        cr.select_font_face(self.font_name, cairo.FONT_SLANT_NORMAL, weight)
        lh = font_size * 1.5
        lw = font_size * 1.5
        self._draw_label(cr, 'I', mid_x - lw/2, ry + hh*0.05, lw, lh, font_size, self.text_color)
        self._draw_label(cr, 'K', mid_x - lw/2, ry + rh - lh - hh*0.05, lw, lh, font_size, self.text_color)
        self._draw_label(cr, 'J', rx + hw*0.05, mid_y - lh/2, lw, lh, font_size, self.text_color)
        self._draw_label(cr, 'L', rx + rw - lw - hw*0.05, mid_y - lh/2, lw, lh, font_size, self.text_color)

        # Virtual cursor
        if self.virtual_cursor_local:
            self._draw_virtual_cursor(cr)

        return False

    def _draw_label(self, cr, text, x, y, w, h, font_size, color):
        cr.set_font_size(font_size)
        ext = cr.text_extents(text)
        tx = x + (w - ext.width) / 2
        ty = y + (h + ext.height) / 2

        # Shadow
        if self.text_shadow[3] > 0:
            cr.set_source_rgba(*self._apply_opacity(self.text_shadow))
            cr.move_to(tx + 1, ty + 1)
            cr.show_text(text)

        # Text
        cr.set_source_rgba(*self._apply_opacity(color))
        cr.move_to(tx, ty)
        cr.show_text(text)

    def _draw_virtual_cursor(self, cr):
        lx, ly = self.virtual_cursor_local

        size = self.cursor_size / 2

        # Choose color based on state
        if self.action_type == 'move':
            color = self.cursor_move_color
        elif self.action_type == 'drag':
            color = self.cursor_drag_color
        elif self.mouse_button == 'right':
            color = self.cursor_right_color
        else:
            color = self.cursor_color

        cr.set_source_rgba(*self._apply_opacity(color))

        # Crosshair
        cr.set_line_width(2)
        cr.move_to(lx - size, ly)
        cr.line_to(lx + size, ly)
        cr.stroke()
        cr.move_to(lx, ly - size)
        cr.line_to(lx, ly + size)
        cr.stroke()

        # Center dot
        cr.arc(lx, ly, 3, 0, 2 * math.pi)
        cr.fill()

    def _apply_opacity(self, color):
        if len(color) == 4:
            return (color[0], color[1], color[2], color[3] * self.master_opacity)
        return color

    # ── Keyboard handling ────────────────────────────────────────

    def _on_key_press(self, widget, event):
        if self.locked:
            return False

        name = Gdk.keyval_name(event.keyval)
        if name is None:
            return True
        key = name.upper()
        state = event.state
        has_shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        has_alt = bool(state & Gdk.ModifierType.MOD1_MASK)
        has_ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)

        # ── Escape → hide / cancel drag
        if key == 'ESCAPE':
            if self.mouse.dragging:
                self.mouse.cancel_drag()
                self._reset_state()
                self.queue_draw()
            else:
                self.hide_overlay()
            return True

        # ── Tab → config editor
        if key == 'TAB':
            self.hide_overlay()
            GLib.timeout_add(100, self._open_config_editor)
            return True

        # ── Backspace → undo last key
        if key in ('BACKSPACE', 'BACK_SPACE'):
            self._undo_last_key()
            return True

        # ── Hold modifiers for action changes
        if has_shift and not has_alt:
            self.mouse_button = 'right'
        if has_alt and not has_shift:
            if self.action_type != 'drag':
                self.action_type = 'move'

        # Alt held = drag mode
        if has_alt and has_shift:
            self.action_type = 'drag'

        # ── Space → execute action at virtual cursor
        if key == 'SPACE':
            self._execute_action_at_virtual_cursor(has_shift, has_alt)
            return True

        # ── Arrow keys → scroll
        if key in ('UP', 'DOWN', 'LEFT', 'RIGHT'):
            direction = key.lower()
            if direction in ('up', 'down'):
                self.mouse.scroll(direction, 3)
            return True

        # ── Single char → grid key input
        if len(key) == 1 or key in ('SEMICOLON', 'COMMA', 'PERIOD'):
            # Normalize special key names
            if key == 'SEMICOLON':
                key = ';'
            elif key == 'COMMA':
                key = ','
            elif key == 'PERIOD':
                key = '.'

            self._handle_grid_key(key, has_shift, has_alt)
            return True

        return True  # absorb

    def _on_key_release(self, widget, event):
        name = Gdk.keyval_name(event.keyval)
        if name is None:
            return True
        key = name.upper()

        # Reset button/action on modifier release
        if key in ('SHIFT_L', 'SHIFT_R'):
            self.mouse_button = 'left'
        if key in ('ALT_L', 'ALT_R'):
            if self.action_type == 'move':
                self.action_type = 'click'

        return True

    def _handle_grid_key(self, key, has_shift, has_alt):
        """Route key based on current phase."""
        if self.phase == 'hints':
            # First letter — filter to matching row
            if key in self.row_keys:
                self.first_letter = key
                self.phase = 'filtered'
                self.selected_keys.append(key)
                self.queue_draw()
            return

        elif self.phase == 'filtered':
            # Second letter — select cell
            if key in self.col_keys and self.first_letter:
                label = self.first_letter + key
                if label in self.hint_reverse:
                    r, c = self.hint_reverse[label]
                    self.selected_keys.append(key)

                    # Position cursor at cell center
                    lx = c * self.hint_cell_w + self.hint_cell_w / 2
                    ly = r * self.hint_cell_h + self.hint_cell_h / 2
                    self.virtual_cursor_local = (lx, ly)
                    self.virtual_cursor = self._local_to_screen(lx, ly)

                    # Set up refinement rect around the selected cell
                    self.sub_rect = [c * self.hint_cell_w, r * self.hint_cell_h,
                                     self.hint_cell_w, self.hint_cell_h]
                    self.sub_level = 0
                    self.phase = 'refine'
                    self.queue_draw()
            return

        elif self.phase == 'refine':
            # IJKL directional shrinking
            if key in self.shrink_keys:
                direction = self.shrink_keys[key]
                rx, ry, rw, rh = self.sub_rect

                if direction == 'up':
                    rh = rh / 2
                elif direction == 'down':
                    ry = ry + rh / 2
                    rh = rh / 2
                elif direction == 'left':
                    rw = rw / 2
                elif direction == 'right':
                    rx = rx + rw / 2
                    rw = rw / 2

                self.sub_rect = [rx, ry, rw, rh]
                self.sub_level += 1
                self.selected_keys.append(key)

                lx = rx + rw / 2
                ly = ry + rh / 2
                self.virtual_cursor_local = (lx, ly)
                self.virtual_cursor = self._local_to_screen(lx, ly)
                self.queue_draw()
            elif key in self.row_keys:
                # Start over with a new hint selection
                self.phase = 'hints'
                self.first_letter = None
                self.selected_keys = []
                self.sub_level = 0
                self.virtual_cursor = None
                self.virtual_cursor_local = None
                self._handle_grid_key(key, has_shift, has_alt)
            return

    def _undo_last_key(self):
        if not self.selected_keys:
            return

        self.selected_keys.pop()

        if len(self.selected_keys) == 0:
            # Back to initial hints
            self.phase = 'hints'
            self.first_letter = None
            self.sub_level = 0
            self.virtual_cursor = None
            self.virtual_cursor_local = None
        elif len(self.selected_keys) == 1:
            # Back to filtered (first letter typed)
            self.phase = 'filtered'
            self.first_letter = self.selected_keys[0]
            self.virtual_cursor = None
            self.virtual_cursor_local = None
        else:
            # Replay hint selection + refinements
            saved = self.selected_keys[:]
            self.selected_keys = []
            self.phase = 'hints'
            self.first_letter = None
            self.sub_level = 0
            self.virtual_cursor = None
            self.virtual_cursor_local = None
            for k in saved:
                self._handle_grid_key(k, False, False)

        self.queue_draw()

    # ── Action execution ─────────────────────────────────────────

    def _execute_action(self, has_shift=False, has_alt=False):
        """Execute mouse action at virtual cursor."""
        if self.virtual_cursor is None:
            return

        sx, sy = self.virtual_cursor

        # Determine action
        if has_alt and not has_shift:
            self.action_type = 'move'
        elif has_alt and has_shift:
            self.action_type = 'drag'
        if has_shift and not has_alt:
            self.mouse_button = 'right'

        self._do_action(sx, sy)

    def _execute_action_at_virtual_cursor(self, has_shift, has_alt):
        """Execute action at current virtual cursor (Space key)."""
        if self.virtual_cursor:
            sx, sy = self.virtual_cursor
        else:
            # No cell selected — execute at system cursor or screen center
            if self.initial_action_loc == 'screen_center':
                sx = self.screen_x + self.screen_w // 2
                sy = self.screen_y + self.screen_h // 2
            elif self.initial_action_loc == 'system_cursor':
                sx, sy = self.mouse.get_position()
            else:
                print("Grid: select a cell before pressing Space")
                return

        if has_shift:
            self.mouse_button = 'right'
        if has_alt:
            self.action_type = 'move'

        self._do_action(sx, sy)

    def _do_action(self, sx, sy):
        """Perform the actual mouse action."""
        # Multi-click detection
        now = time.time()
        if now - self.last_click_time < self.multi_click_threshold / 1000.0:
            self.click_count = min(3, self.click_count + 1)
        else:
            self.click_count = 1
        self.last_click_time = now
        action_type = self.action_type
        mouse_button = self.mouse_button
        click_count = self.click_count

        if action_type == 'click':
            if self.continuous_mode:
                self._finish_click(sx, sy, mouse_button, click_count)
                self._reset_selection_keep_cursor()
                self.queue_draw()
            else:
                self.hide_overlay()
                GLib.timeout_add(60, self._finish_click, sx, sy, mouse_button, click_count)
            self.action_type = 'click'
            self.mouse_button = 'left'
            return

        if action_type == 'move':
            self.mouse.move(sx, sy, self.move_duration)
        elif action_type == 'drag':
            if not self.mouse.dragging:
                self.mouse.move(sx, sy, self.move_duration)
                self.mouse.start_drag(mouse_button)
                # Stay in overlay for drop target
                self._reset_selection_keep_cursor()
                self.queue_draw()
                return
            else:
                # Drop
                self.mouse.move(sx, sy, self.move_duration)
                self.mouse.end_drag(mouse_button)

        # Post-action
        if self.continuous_mode:
            self._reset_selection_keep_cursor()
            self.queue_draw()
        elif self.is_visible:
            self.hide_overlay()

        # Reset action modifiers
        self.action_type = 'click'
        self.mouse_button = 'left'

    def _finish_click(self, sx, sy, mouse_button, click_count):
        self.mouse.click_at(sx, sy, mouse_button, click_count)
        if self.hide_cursor_on_click:
            self.mouse.hide_cursor(self.screen_w, self.screen_h, self.hide_location)
        return False

    def _reset_selection_keep_cursor(self):
        """Reset grid selection but keep overlay up."""
        self.phase = 'hints'
        self.first_letter = None
        self.selected_keys = []
        self.sub_rect = [0, 0, self.screen_w, self.screen_h]
        self.sub_level = 0

    # ── Config editor ────────────────────────────────────────────

    def _open_config_editor(self):
        try:
            from config_editor import ConfigEditor
            editor = ConfigEditor(self.config)
            editor.show_all()
        except Exception as e:
            print(f"Config editor error: {e}")
        return False
