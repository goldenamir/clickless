"""Transparent AppKit overlay with Clickless hint grid for macOS."""

import math
import time

import AppKit
import Foundation
import objc


def _rgba(color, opacity=1.0):
    if len(color) == 4:
        alpha = color[3] * opacity
    else:
        alpha = opacity
    return AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
        float(color[0]), float(color[1]), float(color[2]), float(alpha)
    )


def _rect(x, y, w, h):
    return Foundation.NSMakeRect(float(x), float(y), float(w), float(h))


def _point(x, y):
    return Foundation.NSMakePoint(float(x), float(y))


class MacOverlayView(AppKit.NSView):
    def initWithOverlay_(self, overlay):
        self = objc.super(MacOverlayView, self).initWithFrame_(_rect(0, 0, 1, 1))
        if self is None:
            return None
        self.overlay = overlay
        return self

    def isFlipped(self):
        return True

    def drawRect_(self, dirty_rect):
        self.overlay.draw()


class MacGridOverlay:
    """macOS implementation of the Clickless grid overlay."""

    def __init__(self, config, mouse_ctrl):
        self.config = config
        self.mouse = mouse_ctrl
        self._load_config()

        self.is_visible = False
        self.continuous_mode = False
        self.phase = 'hints'
        self.first_letter = None
        self.selected_keys = []

        self.hint_cols = 0
        self.hint_rows = 0
        self.hint_cell_w = 0
        self.hint_cell_h = 0
        self.hint_labels = {}
        self.hint_reverse = {}
        self.row_keys = ''
        self.col_keys = ''

        self.sub_rect = [0, 0, 0, 0]
        self.sub_level = 0
        self.shrink_keys = {'I': 'up', 'K': 'down', 'J': 'left', 'L': 'right'}

        self.virtual_cursor = None
        self.virtual_cursor_local = None

        self.action_type = 'click'
        self.mouse_button = 'left'
        self.click_count = 1
        self.last_click_time = 0

        self.current_monitor_idx = 0
        self.monitors = []
        self._start_monitor_idx = 0
        self._main_height = 0
        self._detect_monitors()

        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            _rect(0, 0, 100, 100),
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.window.setIgnoresMouseEvents_(True)
        self.window.setReleasedWhenClosed_(False)
        self.window.setLevel_(AppKit.NSScreenSaverWindowLevel)
        behavior = (
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | AppKit.NSWindowCollectionBehaviorStationary
        )
        self.window.setCollectionBehavior_(behavior)

        self.view = MacOverlayView.alloc().initWithOverlay_(self)
        self.window.setContentView_(self.view)
        self._apply_monitor_geometry()

    def _load_config(self):
        style = self.config.get('style', {})
        self.master_opacity = style.get('master_opacity', 1.0)
        self.overlay_opacity = style.get('overlay_opacity', 0.22)
        self.grid_color = style.get('grid_line_color', [0.3, 0.8, 0.5, 0.35])
        self.text_color = style.get('text_color', [1, 1, 1, 0.85])
        self.highlight_color = style.get('highlight_color', [0, 1, 0.53, 0.25])
        self.grid_line_width = style.get('grid_line_width', 1)
        self.font_name = style.get('font', 'monospace')
        self.font_weight = style.get('font_weight', 'bold')
        self.font_size_mult = style.get('font_size_multiplier', 1.0)
        self.cursor_size = style.get('cursor_size', 12)
        self.cursor_color = style.get('cursor_color', [1, 0.3, 0.3, 0.85])
        self.cursor_right_color = style.get('cursor_right_button_color', [0.3, 0.5, 1, 0.85])
        self.cursor_move_color = style.get('cursor_move_color', [0.3, 1, 0.5, 0.85])
        self.cursor_drag_color = style.get('cursor_drag_color', [1, 0.8, 0.2, 0.85])
        self.text_shadow = style.get('text_shadow_rgba', [0, 0, 0, 0.5])

        behavior = self.config.get('behavior', {})
        self.hide_cursor_on_click = behavior.get('hide_cursor_on_click', False)
        self.hide_location = behavior.get('hide_location', 'bottom_left')
        self.move_duration = behavior.get('move_duration_ms', 80)
        self.multi_click_threshold = behavior.get('multi_click_threshold_ms', 300)
        self.continuous_mode = behavior.get('continuous_mode', False)
        self.initial_action_loc = behavior.get('initial_action_location', 'virtual_cursor')

    def _detect_monitors(self):
        screens = list(AppKit.NSScreen.screens())
        main = AppKit.NSScreen.mainScreen()
        self._main_height = float(main.frame().size.height) if main else 0
        self.monitors = []
        primary_idx = 0

        for idx, screen in enumerate(screens):
            frame = screen.frame()
            ns_x = float(frame.origin.x)
            ns_y = float(frame.origin.y)
            width = float(frame.size.width)
            height = float(frame.size.height)
            q_x = ns_x
            q_y = self._main_height - (ns_y + height)
            is_primary = screen == main
            if is_primary:
                primary_idx = idx
            self.monitors.append({
                'ns_x': ns_x,
                'ns_y': ns_y,
                'q_x': q_x,
                'q_y': q_y,
                'w': width,
                'h': height,
                'is_primary': is_primary,
            })

        if not self.monitors:
            self.monitors = [{
                'ns_x': 0,
                'ns_y': 0,
                'q_x': 0,
                'q_y': 0,
                'w': 1440,
                'h': 900,
                'is_primary': True,
            }]
        self.current_monitor_idx = primary_idx

    def _apply_monitor_geometry(self):
        monitor = self.monitors[self.current_monitor_idx]
        self.screen_x = monitor['q_x']
        self.screen_y = monitor['q_y']
        self.screen_w = int(monitor['w'])
        self.screen_h = int(monitor['h'])
        self.window.setFrame_display_(
            _rect(monitor['ns_x'], monitor['ns_y'], monitor['w'], monitor['h']),
            True,
        )

    def _monitor_for_cursor(self):
        mx, my = self.mouse.get_position()
        for idx, monitor in enumerate(self.monitors):
            if (monitor['q_x'] <= mx < monitor['q_x'] + monitor['w']
                    and monitor['q_y'] <= my < monitor['q_y'] + monitor['h']):
                return idx
        return self.current_monitor_idx

    def toggle(self):
        if self.is_visible:
            self.hide_overlay()
        else:
            self.show_overlay()

    def show_overlay(self):
        self._detect_monitors()
        self.current_monitor_idx = self._monitor_for_cursor()
        self._apply_monitor_geometry()
        self._start_monitor_idx = self.current_monitor_idx
        self._generate_hints()
        self._reset_state()
        self.is_visible = True
        self.window.orderFrontRegardless()
        self.queue_draw()

    def cycle_or_close(self):
        if len(self.monitors) < 2:
            self.hide_overlay()
            return
        next_idx = (self.current_monitor_idx + 1) % len(self.monitors)
        if next_idx == self._start_monitor_idx:
            self.hide_overlay()
            return
        self.current_monitor_idx = next_idx
        self._apply_monitor_geometry()
        self._generate_hints()
        self._reset_state()
        self.window.orderFrontRegardless()
        self.queue_draw()

    def hide_overlay(self):
        self.is_visible = False
        self._reset_state()
        self.window.orderOut_(None)

    def queue_draw(self):
        self.view.setNeedsDisplay_(True)

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
        keys = 'ASDFGHJKLQWERTYUIOPZXCVBNM'
        target_cell_w = self.config.get('grid', {}).get('hint_cell_width', 80)
        target_cell_h = self.config.get('grid', {}).get('hint_cell_height', 55)

        self.hint_cols = min(len(keys), max(4, int(self.screen_w / target_cell_w)))
        self.hint_rows = min(len(keys), max(3, int(self.screen_h / target_cell_h)))
        self.hint_cell_w = self.screen_w / self.hint_cols
        self.hint_cell_h = self.screen_h / self.hint_rows

        self.row_keys = keys[:self.hint_rows]
        self.col_keys = keys[:self.hint_cols]
        self.hint_labels = {}
        self.hint_reverse = {}
        for row in range(self.hint_rows):
            for col in range(self.hint_cols):
                label = self.row_keys[row] + self.col_keys[col]
                self.hint_labels[(row, col)] = label
                self.hint_reverse[label] = (row, col)

    def _local_to_screen(self, lx, ly):
        return int(self.screen_x + lx), int(self.screen_y + ly)

    def draw(self):
        _rgba([0, 0, 0, self.overlay_opacity], self.master_opacity).set()
        AppKit.NSBezierPath.fillRect_(_rect(0, 0, self.screen_w, self.screen_h))

        if self.phase in ('hints', 'filtered'):
            self._draw_hint_grid()
        elif self.phase == 'refine':
            self._draw_refine()

        if self.virtual_cursor_local:
            self._draw_virtual_cursor()

    def _draw_hint_grid(self):
        cell_w = self.hint_cell_w
        cell_h = self.hint_cell_h
        font_size = max(9, min(cell_w, cell_h) * 0.28 * self.font_size_mult)

        for row in range(self.hint_rows):
            for col in range(self.hint_cols):
                x = col * cell_w
                y = row * cell_h
                label = self.hint_labels.get((row, col), '')
                is_match = True
                if self.phase == 'filtered' and self.first_letter:
                    is_match = label[0] == self.first_letter

                if not is_match:
                    _rgba([0, 0, 0, 0.5], self.master_opacity).set()
                    AppKit.NSBezierPath.fillRect_(_rect(x, y, cell_w, cell_h))
                    continue

                if self.phase == 'filtered':
                    _rgba(self.highlight_color, self.master_opacity).set()
                    AppKit.NSBezierPath.fillRect_(_rect(x, y, cell_w, cell_h))

                _rgba(self.grid_color, self.master_opacity).set()
                path = AppKit.NSBezierPath.bezierPathWithRect_(_rect(x, y, cell_w, cell_h))
                path.setLineWidth_(0.5)
                path.stroke()

                if self.phase == 'filtered' and self.first_letter:
                    self._draw_two_tone_label(label, x, y, cell_w, cell_h, font_size)
                else:
                    self._draw_label(label, x, y, cell_w, cell_h, font_size, self.text_color)

    def _draw_two_tone_label(self, label, x, y, width, height, font_size):
        attrs = self._text_attrs(font_size, self.text_color)
        dim_attrs = self._text_attrs(font_size, [1, 1, 1, 0.35])
        full_w, full_h = self._text_size(label, attrs)
        first_w, _ = self._text_size(label[0], attrs)
        tx = x + (width - full_w) / 2
        ty = y + (height - full_h) / 2
        self._draw_text(label[0], tx, ty, dim_attrs)
        self._draw_text(label[1], tx + first_w, ty, attrs)

    def _draw_refine(self):
        rx, ry, rw, rh = self.sub_rect

        _rgba([0, 0, 0, 0.5], self.master_opacity).set()
        AppKit.NSBezierPath.fillRect_(_rect(0, 0, self.screen_w, ry))
        AppKit.NSBezierPath.fillRect_(_rect(0, ry + rh, self.screen_w, self.screen_h - ry - rh))
        AppKit.NSBezierPath.fillRect_(_rect(0, ry, rx, rh))
        AppKit.NSBezierPath.fillRect_(_rect(rx + rw, ry, self.screen_w - rx - rw, rh))

        _rgba(self.highlight_color, self.master_opacity).set()
        AppKit.NSBezierPath.fillRect_(_rect(rx, ry, rw, rh))

        mid_x = rx + rw / 2
        mid_y = ry + rh / 2
        _rgba(self.grid_color, self.master_opacity).set()
        path = AppKit.NSBezierPath.bezierPath()
        path.setLineWidth_(self.grid_line_width + 1)
        path.moveToPoint_(_point(mid_x, ry))
        path.lineToPoint_(_point(mid_x, ry + rh))
        path.moveToPoint_(_point(rx, mid_y))
        path.lineToPoint_(_point(rx + rw, mid_y))
        path.stroke()

        border = AppKit.NSBezierPath.bezierPathWithRect_(_rect(rx, ry, rw, rh))
        border.setLineWidth_(self.grid_line_width)
        border.stroke()

        half_w = rw / 2
        half_h = rh / 2
        font_size = max(12, min(half_w, half_h) * 0.25 * self.font_size_mult)
        label_h = font_size * 1.5
        label_w = font_size * 1.5
        self._draw_label('I', mid_x - label_w / 2, ry + half_h * 0.05,
                         label_w, label_h, font_size, self.text_color)
        self._draw_label('K', mid_x - label_w / 2, ry + rh - label_h - half_h * 0.05,
                         label_w, label_h, font_size, self.text_color)
        self._draw_label('J', rx + half_w * 0.05, mid_y - label_h / 2,
                         label_w, label_h, font_size, self.text_color)
        self._draw_label('L', rx + rw - label_w - half_w * 0.05, mid_y - label_h / 2,
                         label_w, label_h, font_size, self.text_color)

    def _draw_label(self, text, x, y, width, height, font_size, color):
        attrs = self._text_attrs(font_size, color)
        text_w, text_h = self._text_size(text, attrs)
        tx = x + (width - text_w) / 2
        ty = y + (height - text_h) / 2

        if len(self.text_shadow) == 4 and self.text_shadow[3] > 0:
            shadow_attrs = self._text_attrs(font_size, self.text_shadow)
            self._draw_text(text, tx + 1, ty + 1, shadow_attrs)
        self._draw_text(text, tx, ty, attrs)

    def _draw_virtual_cursor(self):
        lx, ly = self.virtual_cursor_local
        size = self.cursor_size / 2

        if self.action_type == 'move':
            color = self.cursor_move_color
        elif self.action_type == 'drag':
            color = self.cursor_drag_color
        elif self.mouse_button == 'right':
            color = self.cursor_right_color
        else:
            color = self.cursor_color

        _rgba(color, self.master_opacity).set()
        path = AppKit.NSBezierPath.bezierPath()
        path.setLineWidth_(2)
        path.moveToPoint_(_point(lx - size, ly))
        path.lineToPoint_(_point(lx + size, ly))
        path.moveToPoint_(_point(lx, ly - size))
        path.lineToPoint_(_point(lx, ly + size))
        path.stroke()
        AppKit.NSBezierPath.bezierPathWithOvalInRect_(_rect(lx - 3, ly - 3, 6, 6)).fill()

    def _font(self, size):
        if hasattr(AppKit.NSFont, 'monospacedSystemFontOfSize_weight_'):
            weight = getattr(AppKit, 'NSFontWeightBold', 0.4)
            if self.font_weight != 'bold':
                weight = getattr(AppKit, 'NSFontWeightRegular', 0.0)
            return AppKit.NSFont.monospacedSystemFontOfSize_weight_(size, weight)
        font = AppKit.NSFont.fontWithName_size_(self.font_name, size)
        return font or AppKit.NSFont.systemFontOfSize_(size)

    def _text_attrs(self, font_size, color):
        return {
            AppKit.NSFontAttributeName: self._font(font_size),
            AppKit.NSForegroundColorAttributeName: _rgba(color, self.master_opacity),
        }

    def _text_size(self, text, attrs):
        ns_text = Foundation.NSString.stringWithString_(text)
        size = ns_text.sizeWithAttributes_(attrs)
        return float(size.width), float(size.height)

    def _draw_text(self, text, x, y, attrs):
        Foundation.NSString.stringWithString_(text).drawAtPoint_withAttributes_(
            _point(x, y), attrs
        )

    def _handle_grid_key(self, key, has_shift, has_alt):
        if self.phase == 'hints':
            if key in self.row_keys:
                self.first_letter = key
                self.phase = 'filtered'
                self.selected_keys.append(key)
                self.queue_draw()
            return

        if self.phase == 'filtered':
            if key in self.col_keys and self.first_letter:
                label = self.first_letter + key
                if label in self.hint_reverse:
                    row, col = self.hint_reverse[label]
                    self.selected_keys.append(key)
                    lx = col * self.hint_cell_w + self.hint_cell_w / 2
                    ly = row * self.hint_cell_h + self.hint_cell_h / 2
                    self.virtual_cursor_local = (lx, ly)
                    self.virtual_cursor = self._local_to_screen(lx, ly)
                    self.sub_rect = [
                        col * self.hint_cell_w,
                        row * self.hint_cell_h,
                        self.hint_cell_w,
                        self.hint_cell_h,
                    ]
                    self.sub_level = 0
                    self.phase = 'refine'
                    self.queue_draw()
            return

        if self.phase == 'refine':
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
                self.phase = 'hints'
                self.first_letter = None
                self.selected_keys = []
                self.sub_level = 0
                self.virtual_cursor = None
                self.virtual_cursor_local = None
                self._handle_grid_key(key, has_shift, has_alt)

    def _undo_last_key(self):
        if not self.selected_keys:
            return
        self.selected_keys.pop()

        if len(self.selected_keys) == 0:
            self.phase = 'hints'
            self.first_letter = None
            self.sub_level = 0
            self.virtual_cursor = None
            self.virtual_cursor_local = None
        elif len(self.selected_keys) == 1:
            self.phase = 'filtered'
            self.first_letter = self.selected_keys[0]
            self.virtual_cursor = None
            self.virtual_cursor_local = None
        else:
            saved = self.selected_keys[:]
            self.selected_keys = []
            self.phase = 'hints'
            self.first_letter = None
            self.sub_level = 0
            self.virtual_cursor = None
            self.virtual_cursor_local = None
            for key in saved:
                self._handle_grid_key(key, False, False)

        self.queue_draw()

    def _execute_action_at_virtual_cursor(self, has_shift, has_alt):
        if self.virtual_cursor:
            sx, sy = self.virtual_cursor
        elif self.initial_action_loc == 'screen_center':
            sx = self.screen_x + self.screen_w // 2
            sy = self.screen_y + self.screen_h // 2
        else:
            sx, sy = self.mouse.get_position()

        if has_shift:
            self.mouse_button = 'right'
        if has_alt:
            self.action_type = 'move'
        if has_alt and has_shift:
            self.action_type = 'drag'

        self._do_action(sx, sy)

    def _do_action(self, sx, sy):
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
                self._reset_selection_keep_cursor()
                self.queue_draw()
                return
            self.mouse.move(sx, sy, self.move_duration)
            self.mouse.end_drag(self.mouse_button)
        else:
            self.mouse.click_at(sx, sy, self.mouse_button, self.click_count)

        if self.hide_cursor_on_click and self.action_type == 'click':
            self.mouse.hide_cursor(self.screen_w, self.screen_h, self.hide_location)

        if self.continuous_mode:
            self._reset_selection_keep_cursor()
            self.queue_draw()
        else:
            self.hide_overlay()

        self.action_type = 'click'
        self.mouse_button = 'left'

    def _reset_selection_keep_cursor(self):
        self.phase = 'hints'
        self.first_letter = None
        self.selected_keys = []
        self.sub_rect = [0, 0, self.screen_w, self.screen_h]
        self.sub_level = 0
