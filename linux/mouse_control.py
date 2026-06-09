"""Clickless - Mouse control via xdotool (move, click, scroll, drag)"""

import subprocess
import time


class MouseController:
    """Wraps xdotool for mouse actions."""

    BUTTON_MAP = {
        'left': '1', 'right': '3', 'middle': '2',
        'back': '8', 'forward': '9',
    }
    SCROLL_MAP = {
        'up': '4', 'down': '5', 'left': '6', 'right': '7',
    }

    def __init__(self):
        self.dragging = False
        self.last_action = None  # (action_type, x, y, button, count)

    # ── Position ─────────────────────────────────────────────────

    def get_position(self):
        """Return current (x, y) of system cursor."""
        try:
            out = subprocess.check_output(
                ['xdotool', 'getmouselocation'], text=True
            )
            parts = out.split()
            x = int(parts[0].split(':')[1])
            y = int(parts[1].split(':')[1])
            return x, y
        except Exception:
            return 0, 0

    def move(self, x, y, duration_ms=0):
        """Move cursor to absolute (x, y)."""
        if duration_ms > 0:
            self._smooth_move(x, y, duration_ms)
        else:
            subprocess.run(['xdotool', 'mousemove', str(x), str(y)], check=False)

    def move_relative(self, dx, dy):
        """Move cursor by (dx, dy) pixels."""
        subprocess.run(
            ['xdotool', 'mousemove_relative', '--', str(dx), str(dy)],
            check=False
        )

    def _smooth_move(self, x, y, duration_ms):
        """Smooth animated move over duration_ms."""
        sx, sy = self.get_position()
        steps = max(1, duration_ms // 8)
        for i in range(1, steps + 1):
            t = i / steps
            # ease-out quad
            t = t * (2 - t)
            cx = int(sx + (x - sx) * t)
            cy = int(sy + (y - sy) * t)
            subprocess.run(
                ['xdotool', 'mousemove', str(cx), str(cy)], check=False
            )
            time.sleep(0.008)

    def hide_cursor(self, screen_w, screen_h, location='bottom_left'):
        """Move cursor to a screen edge/corner."""
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
        x, y = positions.get(location, (0, screen_h - 1))
        subprocess.run(['xdotool', 'mousemove', str(x), str(y)], check=False)

    # ── Clicking ─────────────────────────────────────────────────

    def click(self, button='left', count=1, modifiers=None):
        """Click at current position."""
        btn = self.BUTTON_MAP.get(button, '1')
        cmd = ['xdotool', 'click']
        if modifiers:
            for mod in modifiers:
                cmd.extend(['--clearmodifiers'])
                break
        if count > 1:
            cmd.extend(['--repeat', str(count), '--delay', '50'])
        cmd.append(btn)
        subprocess.run(cmd, check=False)
        self.last_action = ('click', *self.get_position(), button, count)

    def click_at(self, x, y, button='left', count=1, modifiers=None):
        """Move to (x, y) then click."""
        self.move(x, y)
        self.click(button, count, modifiers)

    # ── Dragging ─────────────────────────────────────────────────

    def start_drag(self, button='left'):
        """Press and hold mouse button (begin drag)."""
        btn = self.BUTTON_MAP.get(button, '1')
        subprocess.run(['xdotool', 'mousedown', btn], check=False)
        self.dragging = True

    def end_drag(self, button='left'):
        """Release mouse button (end drag / drop)."""
        btn = self.BUTTON_MAP.get(button, '1')
        subprocess.run(['xdotool', 'mouseup', btn], check=False)
        self.dragging = False

    def cancel_drag(self, button='left'):
        """Release drag at current system cursor position."""
        if self.dragging:
            self.end_drag(button)

    # ── Scrolling ────────────────────────────────────────────────

    def scroll(self, direction, amount=1):
        """Scroll in direction by amount clicks."""
        btn = self.SCROLL_MAP.get(direction, '5')
        for _ in range(amount):
            subprocess.run(['xdotool', 'click', btn], check=False)

    def scroll_smooth(self, direction, amount=1):
        """Scroll using button events for smooth feel."""
        self.scroll(direction, amount)

    # ── Repeat ───────────────────────────────────────────────────

    def repeat_last(self):
        """Repeat the last mouse action."""
        if self.last_action is None:
            return
        action_type, x, y, button, count = self.last_action
        if action_type == 'click':
            self.click_at(x, y, button, count)
