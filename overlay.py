"""Clickless - Transparent GTK overlay with multi-level grid mouse control

Supports:
- Level 1 grid (cell selection)
- Optional level 2 grid
- Subgrid for precision
- Subgrid nudges
- Drag & drop
- Multi-monitor
- Modifier clicks
- Continuous mode
- Virtual cursor display
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

        # Grid selection state
        self.level = 0              # 0=no selection, 1=level1 selected, 2=level2 selected, 3=subgrid
        self.selected_keys = []     # keys typed so far
        self.selected_cell = None   # (row, col) at level 1
        self.selected_l2 = None     # (row, col) at level 2
        self.virtual_cursor = None  # (screen_x, screen_y) absolute
        self.virtual_cursor_local = None  # (x, y) relative to overlay

        # Nudge state
        self.nudge_held_key = None
        self.nudge_offset = (0, 0)

        # Action state
        self.action_type = 'click'  # click | move | drag
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
            # Try compositing check
            print(f"DEBUG: Screen is composited: {screen.is_composited()}")

        self._apply_monitor_geometry()

        self.connect('draw', self._on_draw)
        self.connect('key-press-event', self._on_key_press)
        self.connect('key-release-event', self._on_key_release)

    # ── Config loading ───────────────────────────────────────────

    def _load_config(self):
        grid_cfgs = self.config.get('grid', {}).get('configs', [{}])
        self.grid_configs = grid_cfgs
        self.active_grid = grid_cfgs[0] if grid_cfgs else {}

        g = self.active_grid
        self.l1_cols = g.get('level1_columns', 10)
        self.l1_rows = g.get('level1_rows', 9)
        self.l1_keys = g.get('level1_keys', 'ASDFGHJKLQWERTYUIOP').upper()
        self.l2_cols = g.get('level2_columns', 0)
        self.l2_rows = g.get('level2_rows', 0)
        self.l2_keys = g.get('level2_keys', '').upper()
        self.sg_cols = g.get('subgrid_columns', 3)
        self.sg_rows = g.get('subgrid_rows', 3)
        self.sg_keys = g.get('subgrid_keys', 'UIOJKLM,.').upper()
        self.always_show_subgrid = g.get('always_show_subgrid', False)
        self.hold_for_nudge = g.get('hold_subgrid_key_for_nudge', True)
        self.nudges_per_cell = g.get('nudges_per_cell', 4)

        self.has_l2 = self.l2_cols > 0 and self.l2_rows > 0

        # Build key-to-position maps for level 1
        self.l1_key_map = {}
        idx = 0
        for r in range(self.l1_rows):
            for c in range(self.l1_cols):
                if idx < len(self.l1_keys):
                    self.l1_key_map[self.l1_keys[idx]] = (r, c)
                    idx += 1

        # Level 2 key map
        self.l2_key_map = {}
        if self.has_l2 and self.l2_keys:
            idx = 0
            for r in range(self.l2_rows):
                for c in range(self.l2_cols):
                    if idx < len(self.l2_keys):
                        self.l2_key_map[self.l2_keys[idx]] = (r, c)
                        idx += 1

        # Subgrid key map
        self.sg_key_map = {}
        idx = 0
        for r in range(self.sg_rows):
            for c in range(self.sg_cols):
                if idx < len(self.sg_keys):
                    self.sg_key_map[self.sg_keys[idx]] = (r, c)
                    idx += 1

        # Style
        s = self.config.get('style', {})
        self.master_opacity = s.get('master_opacity', 1.0)
        self.overlay_opacity = s.get('overlay_opacity', 0.22)
        self.grid_color = s.get('grid_line_color', [0.3, 0.8, 0.5, 0.35])
        self.subgrid_color = s.get('subgrid_line_color', [0.3, 0.8, 0.5, 0.2])
        self.text_color = s.get('text_color', [1, 1, 1, 0.85])
        self.sg_text_color = s.get('subgrid_text_color', [1, 1, 1, 0.6])
        self.highlight_color = s.get('highlight_color', [0, 1, 0.53, 0.25])
        self.highlight_anim_ms = s.get('highlight_animation_ms', 100)
        self.grid_line_width = s.get('grid_line_width', 1)
        self.font_name = s.get('font', 'monospace')
        self.font_weight = s.get('font_weight', 'bold')
        self.font_size_mult = s.get('font_size_multiplier', 1.0)
        self.sg_font_size_mult = s.get('subgrid_font_size_multiplier', 0.8)
        self.cursor_size = s.get('cursor_size', 12)
        self.cursor_color = s.get('cursor_color', [1, 0.3, 0.3, 0.85])
        self.cursor_right_color = s.get('cursor_right_button_color', [0.3, 0.5, 1, 0.85])
        self.cursor_move_color = s.get('cursor_move_color', [0.3, 1, 0.5, 0.85])
        self.cursor_drag_color = s.get('cursor_drag_color', [1, 0.8, 0.2, 0.85])
        self.text_shadow = s.get('text_shadow_rgba', [0, 0, 0, 0.5])
        self.bg_colors = s.get('background_colors', ['#1a1a2e'])

        # Behavior
        b = self.config.get('behavior', {})
        self.action_level = b.get('grid_action_level', 'subgrid')
        self.hide_cursor_on_click = b.get('hide_cursor_on_click', False)
        self.hide_location = b.get('hide_location', 'bottom_left')
        self.move_duration = b.get('move_duration_ms', 80)
        self.multi_click_threshold = b.get('multi_click_threshold_ms', 300)
        self.continuous_mode = b.get('continuous_mode', False)
        self.initial_action_loc = b.get('initial_action_location', 'virtual_cursor')

        # Keybindings
        kb = self.config.get('keybindings', {})
        self.kb = kb

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

    def move_to_next_monitor(self):
        if len(self.monitors) < 2:
            return
        self.current_monitor_idx = (self.current_monitor_idx + 1) % len(self.monitors)
        self._apply_monitor_geometry()
        self._load_grid_for_monitor()
        self._reset_state()
        self.queue_draw()

    def move_to_prev_monitor(self):
        if len(self.monitors) < 2:
            return
        self.current_monitor_idx = (self.current_monitor_idx - 1) % len(self.monitors)
        self._apply_monitor_geometry()
        self._load_grid_for_monitor()
        self._reset_state()
        self.queue_draw()

    def _load_grid_for_monitor(self):
        mode = self.config.get('grid', {}).get('monitor_assignment_mode', 'auto')
        m = self.monitors[self.current_monitor_idx]

        if mode == 'single' or len(self.grid_configs) < 2:
            self.active_grid = self.grid_configs[0]
        elif mode == 'auto':
            is_horizontal = m['w'] >= m['h']
            self.active_grid = self.grid_configs[0] if is_horizontal else self.grid_configs[min(1, len(self.grid_configs)-1)]
        elif mode == 'custom':
            assignments = self.config.get('grid', {}).get('custom_monitor_assignments', '')
            names = [n.strip() for n in assignments.split(',') if n.strip()]
            if self.current_monitor_idx < len(names):
                target = names[self.current_monitor_idx]
                for gc in self.grid_configs:
                    if gc.get('name', '') == target:
                        self.active_grid = gc
                        break

        # Reload grid params
        g = self.active_grid
        self.l1_cols = g.get('level1_columns', 10)
        self.l1_rows = g.get('level1_rows', 9)
        self.l1_keys = g.get('level1_keys', 'ASDFGHJKLQWERTYUIOP').upper()
        self.sg_cols = g.get('subgrid_columns', 3)
        self.sg_rows = g.get('subgrid_rows', 3)
        self.sg_keys = g.get('subgrid_keys', 'UIOJKLM,.').upper()

        # Rebuild key maps
        self.l1_key_map = {}
        idx = 0
        for r in range(self.l1_rows):
            for c in range(self.l1_cols):
                if idx < len(self.l1_keys):
                    self.l1_key_map[self.l1_keys[idx]] = (r, c)
                    idx += 1

        self.sg_key_map = {}
        idx = 0
        for r in range(self.sg_rows):
            for c in range(self.sg_cols):
                if idx < len(self.sg_keys):
                    self.sg_key_map[self.sg_keys[idx]] = (r, c)
                    idx += 1

    # ── Show / hide ──────────────────────────────────────────────

    def toggle(self):
        if self.is_visible:
            self.hide_overlay()
        else:
            self.show_overlay()

    def show_overlay(self):
        self._reset_state()
        self.is_visible = True
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
        self.level = 0
        self.selected_keys = []
        self.selected_cell = None
        self.selected_l2 = None
        self.virtual_cursor = None
        self.virtual_cursor_local = None
        self.nudge_held_key = None
        self.nudge_offset = (0, 0)
        self.action_type = 'click'
        self.mouse_button = 'left'
        self.click_count = 1

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

    # ── Coordinate math ──────────────────────────────────────────

    def _cell_rect(self, row, col):
        """Return (x, y, w, h) for a level-1 cell in local coords."""
        cw = self.screen_w / self.l1_cols
        ch = self.screen_h / self.l1_rows
        return col * cw, row * ch, cw, ch

    def _subcell_center(self, cell_row, cell_col, sg_row, sg_col):
        """Return (local_x, local_y) for subgrid cell center."""
        cx, cy, cw, ch = self._cell_rect(cell_row, cell_col)
        scw = cw / self.sg_cols
        sch = ch / self.sg_rows
        lx = cx + sg_col * scw + scw / 2
        ly = cy + sg_row * sch + sch / 2
        return lx, ly

    def _local_to_screen(self, lx, ly):
        return int(self.screen_x + lx), int(self.screen_y + ly)

    def _cell_center(self, row, col):
        cx, cy, cw, ch = self._cell_rect(row, col)
        return cx + cw / 2, cy + ch / 2

    def _l2_cell_rect(self, l1_row, l1_col, l2_row, l2_col):
        """Return (x, y, w, h) for a level-2 cell inside a level-1 cell."""
        cx, cy, cw, ch = self._cell_rect(l1_row, l1_col)
        scw = cw / self.l2_cols
        sch = ch / self.l2_rows
        return cx + l2_col * scw, cy + l2_row * sch, scw, sch

    def _l2_cell_center(self, l1_row, l1_col, l2_row, l2_col):
        """Return (local_x, local_y) center of a level-2 cell."""
        x, y, w, h = self._l2_cell_rect(l1_row, l1_col, l2_row, l2_col)
        return x + w / 2, y + h / 2

    # ── Drawing ──────────────────────────────────────────────────

    def _on_draw(self, widget, cr):
        cw = self.screen_w / self.l1_cols
        ch = self.screen_h / self.l1_rows

        # Background
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, self.overlay_opacity * self.master_opacity)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        font_size = max(10, min(cw, ch) * 0.25 * self.font_size_mult)
        weight = cairo.FONT_WEIGHT_BOLD if self.font_weight == 'bold' else cairo.FONT_WEIGHT_NORMAL
        cr.select_font_face(self.font_name, cairo.FONT_SLANT_NORMAL, weight)
        cr.set_font_size(font_size)

        for r in range(self.l1_rows):
            for c in range(self.l1_cols):
                x, y, w, h = self._cell_rect(r, c)
                key_idx = r * self.l1_cols + c
                key_char = self.l1_keys[key_idx] if key_idx < len(self.l1_keys) else '?'

                is_selected = (self.selected_cell == (r, c))
                is_highlighted = False

                if self.level == 0:
                    # No selection yet — show all cells
                    pass
                elif self.level >= 1 and self.selected_cell is not None:
                    if is_selected:
                        is_highlighted = True
                    else:
                        # Dim unselected cells
                        cr.set_source_rgba(0, 0, 0, 0.45 * self.master_opacity)
                        cr.rectangle(x, y, w, h)
                        cr.fill()
                        continue

                # Highlight
                if is_highlighted:
                    cr.set_source_rgba(*self._apply_opacity(self.highlight_color))
                    cr.rectangle(x, y, w, h)
                    cr.fill()

                # Grid lines
                cr.set_source_rgba(*self._apply_opacity(self.grid_color))
                cr.set_line_width(self.grid_line_width)
                cr.rectangle(x, y, w, h)
                cr.stroke()

                # Draw level 2 grid or subgrid if selected
                if is_selected and self.level >= 1:
                    if self.has_l2:
                        self._draw_l2_grid(cr, x, y, w, h)
                    else:
                        self._draw_subgrid(cr, x, y, w, h)
                elif self.always_show_subgrid:
                    self._draw_subgrid_faint(cr, x, y, w, h)

                # Label
                if not (is_selected and self.level >= 1):
                    self._draw_label(cr, key_char, x, y, w, h, font_size, self.text_color)

        # Virtual cursor
        if self.virtual_cursor_local:
            self._draw_virtual_cursor(cr)

        return False

    def _draw_l2_grid(self, cr, cx, cy, cw, ch):
        """Draw level 2 grid (keyboard-like layout) inside a selected level 1 cell."""
        scw = cw / self.l2_cols
        sch = ch / self.l2_rows

        l2_font_size = max(8, min(scw, sch) * 0.3 * self.font_size_mult)
        weight = cairo.FONT_WEIGHT_BOLD if self.font_weight == 'bold' else cairo.FONT_WEIGHT_NORMAL
        cr.select_font_face(self.font_name, cairo.FONT_SLANT_NORMAL, weight)
        cr.set_font_size(l2_font_size)

        idx = 0
        for r in range(self.l2_rows):
            for c in range(self.l2_cols):
                sx = cx + c * scw
                sy = cy + r * sch

                # Grid lines
                cr.set_source_rgba(*self._apply_opacity(self.grid_color))
                cr.set_line_width(1)
                cr.rectangle(sx, sy, scw, sch)
                cr.stroke()

                # Label
                if idx < len(self.l2_keys):
                    char = self.l2_keys[idx]
                    self._draw_label(cr, char, sx, sy, scw, sch, l2_font_size, self.text_color)
                idx += 1

    def _draw_subgrid(self, cr, cx, cy, cw, ch):
        """Draw the subgrid inside a selected cell."""
        scw = cw / self.sg_cols
        sch = ch / self.sg_rows

        sg_font_size = max(8, min(scw, sch) * 0.3 * self.sg_font_size_mult)
        weight = cairo.FONT_WEIGHT_BOLD if self.font_weight == 'bold' else cairo.FONT_WEIGHT_NORMAL
        cr.select_font_face(self.font_name, cairo.FONT_SLANT_NORMAL, weight)
        cr.set_font_size(sg_font_size)

        idx = 0
        for r in range(self.sg_rows):
            for c in range(self.sg_cols):
                sx = cx + c * scw
                sy = cy + r * sch

                # Subgrid lines
                cr.set_source_rgba(*self._apply_opacity(self.subgrid_color))
                cr.set_line_width(1)
                cr.rectangle(sx, sy, scw, sch)
                cr.stroke()

                # Subgrid label
                if idx < len(self.sg_keys):
                    char = self.sg_keys[idx]
                    self._draw_label(cr, char, sx, sy, scw, sch, sg_font_size, self.sg_text_color)
                idx += 1

    def _draw_subgrid_faint(self, cr, cx, cy, cw, ch):
        """Draw a faint subgrid (always_show_subgrid mode)."""
        scw = cw / self.sg_cols
        sch = ch / self.sg_rows
        cr.set_source_rgba(*self._apply_opacity(self.subgrid_color[:3] + [self.subgrid_color[3] * 0.4]))
        cr.set_line_width(0.5)
        for r in range(1, self.sg_rows):
            cr.move_to(cx, cy + r * sch)
            cr.line_to(cx + cw, cy + r * sch)
            cr.stroke()
        for c in range(1, self.sg_cols):
            cr.move_to(cx + c * scw, cy)
            cr.line_to(cx + c * scw, cy + ch)
            cr.stroke()

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
        # Apply nudge offset
        lx += self.nudge_offset[0]
        ly += self.nudge_offset[1]

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

        # Nudge key release → execute at nudged position
        if self.nudge_held_key is not None:
            nk = key
            if key == 'SEMICOLON':
                nk = ';'
            elif key == 'COMMA':
                nk = ','
            elif key == 'PERIOD':
                nk = '.'
            if nk == self.nudge_held_key:
                self._execute_at_nudged_pos()
                self.nudge_held_key = None
                self.nudge_offset = (0, 0)
                return True

        return True

    def _handle_grid_key(self, key, has_shift, has_alt):
        """Process a grid/subgrid key press."""
        if self.level == 0:
            # Level 1 selection
            if key in self.l1_key_map:
                r, c = self.l1_key_map[key]
                self.selected_cell = (r, c)
                self.selected_keys.append(key)
                self.level = 1

                lx, ly = self._cell_center(r, c)
                self.virtual_cursor_local = (lx, ly)
                self.virtual_cursor = self._local_to_screen(lx, ly)

                # If action level is "1", execute immediately
                if self.action_level == '1' or self.action_level == 1:
                    self._execute_action(has_shift, has_alt)
                    return

                self.queue_draw()
            return

        elif self.level == 1 and self.has_l2:
            # Level 2 selection (if configured)
            if key in self.l2_key_map:
                r2, c2 = self.l2_key_map[key]
                self.selected_l2 = (r2, c2)
                self.selected_keys.append(key)
                self.level = 2

                # Calculate cursor position inside the level 2 subcell
                cr, cc = self.selected_cell
                lx, ly = self._l2_cell_center(cr, cc, r2, c2)
                self.virtual_cursor_local = (lx, ly)
                self.virtual_cursor = self._local_to_screen(lx, ly)

                if self.action_level == '2' or self.action_level == 2:
                    self._execute_action(has_shift, has_alt)
                    return
                self.queue_draw()
            return

        elif (self.level == 1 and not self.has_l2) or self.level == 2:
            # Subgrid selection
            if key in self.sg_key_map:
                sg_r, sg_c = self.sg_key_map[key]
                cr, cc = self.selected_cell

                lx, ly = self._subcell_center(cr, cc, sg_r, sg_c)
                self.virtual_cursor_local = (lx, ly)
                self.virtual_cursor = self._local_to_screen(lx, ly)

                # Nudge mode: hold subgrid key
                if self.hold_for_nudge:
                    self.nudge_held_key = key
                    self.nudge_offset = (0, 0)
                    self.queue_draw()
                    return

                self._execute_action(has_shift, has_alt)
                return
            elif key in self.l1_key_map:
                # Restart with new level-1 cell
                self.level = 0
                self.selected_keys = []
                self.selected_cell = None
                self.selected_l2 = None
                self.virtual_cursor = None
                self.virtual_cursor_local = None
                self.nudge_offset = (0, 0)
                self._handle_grid_key(key, has_shift, has_alt)
                return

    def _undo_last_key(self):
        if self.selected_keys:
            self.selected_keys.pop()
        if self.level > 0:
            self.level -= 1
        if self.level == 0:
            self.selected_cell = None
            self.selected_l2 = None
            self.virtual_cursor = None
            self.virtual_cursor_local = None
        self.nudge_offset = (0, 0)
        self.nudge_held_key = None
        self.queue_draw()

    # ── Nudge handling ───────────────────────────────────────────

    def handle_nudge(self, direction):
        """Move virtual cursor by a nudge increment."""
        if self.virtual_cursor_local is None or self.selected_cell is None:
            return
        cr, cc = self.selected_cell
        _, _, cw, ch = self._cell_rect(cr, cc)
        nudge_x = (cw / self.sg_cols) / self.nudges_per_cell
        nudge_y = (ch / self.sg_rows) / self.nudges_per_cell

        dx, dy = self.nudge_offset
        if direction == 'up':
            dy -= nudge_y
        elif direction == 'down':
            dy += nudge_y
        elif direction == 'left':
            dx -= nudge_x
        elif direction == 'right':
            dx += nudge_x
        self.nudge_offset = (dx, dy)

        # Update actual cursor position
        lx, ly = self.virtual_cursor_local
        sx, sy = self._local_to_screen(lx + dx, ly + dy)
        self.mouse.move(sx, sy)
        self.queue_draw()

    def _execute_at_nudged_pos(self):
        """Execute action at nudged virtual cursor position."""
        if self.virtual_cursor_local is None:
            return
        lx, ly = self.virtual_cursor_local
        dx, dy = self.nudge_offset
        sx, sy = self._local_to_screen(lx + dx, ly + dy)
        self.virtual_cursor = (sx, sy)
        self._do_action(sx, sy)

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
            else:
                sx, sy = self.mouse.get_position()

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

        if self.action_type == 'move':
            self.mouse.move(sx, sy, self.move_duration)
        elif self.action_type == 'drag':
            if not self.mouse.dragging:
                self.mouse.move(sx, sy, self.move_duration)
                self.mouse.start_drag(self.mouse_button)
                # Stay in overlay for drop target
                self._reset_selection_keep_cursor()
                self.queue_draw()
                return
            else:
                # Drop
                self.mouse.move(sx, sy, self.move_duration)
                self.mouse.end_drag(self.mouse_button)
        elif self.action_type == 'click':
            self.mouse.click_at(sx, sy, self.mouse_button, self.click_count)

        # Post-action
        if self.hide_cursor_on_click and self.action_type == 'click':
            self.mouse.hide_cursor(self.screen_w, self.screen_h, self.hide_location)

        if self.continuous_mode:
            self._reset_selection_keep_cursor()
            self.queue_draw()
        else:
            self.hide_overlay()

        # Reset action modifiers
        self.action_type = 'click'
        self.mouse_button = 'left'

    def _reset_selection_keep_cursor(self):
        """Reset grid selection but keep overlay up."""
        self.level = 0
        self.selected_keys = []
        self.selected_cell = None
        self.selected_l2 = None
        self.nudge_held_key = None
        self.nudge_offset = (0, 0)

    # ── Config editor ────────────────────────────────────────────

    def _open_config_editor(self):
        try:
            from config_editor import ConfigEditor
            editor = ConfigEditor(self.config)
            editor.show_all()
        except Exception as e:
            print(f"Config editor error: {e}")
        return False
