"""Clickless mouse control for macOS via Quartz."""

import time

import Quartz


class MacMouseController:
    """Wraps Quartz mouse, scroll, and drag events."""

    BUTTONS = {
        'left': Quartz.kCGMouseButtonLeft,
        'right': Quartz.kCGMouseButtonRight,
        'middle': Quartz.kCGMouseButtonCenter,
        'back': 3,
        'forward': 4,
    }

    EVENT_TYPES = {
        'left': (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp),
        'right': (Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp),
        'middle': (Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp),
        'back': (Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp),
        'forward': (Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp),
    }

    def __init__(self):
        self.dragging = False
        self.drag_button = 'left'
        self.last_action = None

    def get_position(self):
        """Return current cursor position in Quartz global display coordinates."""
        event = Quartz.CGEventCreate(None)
        point = Quartz.CGEventGetLocation(event)
        return int(point.x), int(point.y)

    def move(self, x, y, duration_ms=0):
        if duration_ms > 0:
            self._smooth_move(x, y, duration_ms)
        else:
            self._move_now(x, y)

    def move_relative(self, dx, dy):
        x, y = self.get_position()
        self._move_now(x + dx, y + dy)

    def _move_now(self, x, y):
        point = (float(x), float(y))
        Quartz.CGWarpMouseCursorPosition(point)
        event_type = Quartz.kCGEventMouseMoved
        button = Quartz.kCGMouseButtonLeft
        if self.dragging:
            button = self.BUTTONS.get(self.drag_button, Quartz.kCGMouseButtonLeft)
            if self.drag_button == 'right':
                event_type = Quartz.kCGEventRightMouseDragged
            elif self.drag_button == 'left':
                event_type = Quartz.kCGEventLeftMouseDragged
            else:
                event_type = Quartz.kCGEventOtherMouseDragged
        event = Quartz.CGEventCreateMouseEvent(
            None, event_type, point, button
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def _smooth_move(self, x, y, duration_ms):
        sx, sy = self.get_position()
        steps = max(1, duration_ms // 8)
        for i in range(1, steps + 1):
            t = i / steps
            t = t * (2 - t)
            cx = int(sx + (x - sx) * t)
            cy = int(sy + (y - sy) * t)
            self._move_now(cx, cy)
            time.sleep(0.008)

    def hide_cursor(self, screen_w, screen_h, location='bottom_left'):
        x, y = self.get_position()
        positions = {
            'top_left': (0, 0),
            'top_right': (screen_w - 1, 0),
            'bottom_left': (0, screen_h - 1),
            'bottom_right': (screen_w - 1, screen_h - 1),
            'top': (screen_w // 2, 0),
            'bottom': (screen_w // 2, screen_h - 1),
            'left': (0, screen_h // 2),
            'right': (screen_w - 1, screen_h // 2),
        }
        dx, dy = positions.get(location, (0, screen_h - 1))
        self._move_now(x - (x % screen_w) + dx, y - (y % screen_h) + dy)

    def click(self, button='left', count=1, modifiers=None):
        x, y = self.get_position()
        self.click_at(x, y, button, count, modifiers)

    def click_at(self, x, y, button='left', count=1, modifiers=None):
        self.move(x, y)
        for _ in range(max(1, count)):
            self._post_button(button, True, x, y)
            self._post_button(button, False, x, y)
            if count > 1:
                time.sleep(0.05)
        self.last_action = ('click', x, y, button, count)

    def start_drag(self, button='left'):
        x, y = self.get_position()
        self.drag_button = button
        self._post_button(button, True, x, y)
        self.dragging = True

    def end_drag(self, button='left'):
        x, y = self.get_position()
        button = self.drag_button or button
        self._post_button(button, False, x, y)
        self.dragging = False
        self.drag_button = 'left'

    def cancel_drag(self, button='left'):
        if self.dragging:
            self.end_drag(button)

    def _post_button(self, button, is_down, x, y):
        down_type, up_type = self.EVENT_TYPES.get(button, self.EVENT_TYPES['left'])
        event_type = down_type if is_down else up_type
        cg_button = self.BUTTONS.get(button, Quartz.kCGMouseButtonLeft)
        event = Quartz.CGEventCreateMouseEvent(
            None, event_type, (float(x), float(y)), cg_button
        )
        Quartz.CGEventSetIntegerValueField(
            event, Quartz.kCGMouseEventButtonNumber, cg_button
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def scroll(self, direction, amount=1):
        vertical = 0
        horizontal = 0
        if direction == 'up':
            vertical = max(1, amount)
        elif direction == 'down':
            vertical = -max(1, amount)
        elif direction == 'left':
            horizontal = max(1, amount)
        elif direction == 'right':
            horizontal = -max(1, amount)

        event = Quartz.CGEventCreateScrollWheelEvent(
            None, Quartz.kCGScrollEventUnitLine, 2, vertical, horizontal
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def scroll_smooth(self, direction, amount=1):
        self.scroll(direction, amount)

    def repeat_last(self):
        if self.last_action is None:
            return
        action_type, x, y, button, count = self.last_action
        if action_type == 'click':
            self.click_at(x, y, button, count)
