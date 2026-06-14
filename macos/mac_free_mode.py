"""Free mode implementation for Clickless on macOS."""

import threading
import time

import AppKit
import Foundation
import objc


def _rect(x, y, w, h):
    return Foundation.NSMakeRect(float(x), float(y), float(w), float(h))


def _point(x, y):
    return Foundation.NSMakePoint(float(x), float(y))


def _run_on_main(callback):
    if threading.current_thread() is threading.main_thread():
        callback()
    else:
        Foundation.NSOperationQueue.mainQueue().addOperationWithBlock_(callback)


class MacFreeModeIndicatorView(AppKit.NSView):
    def initWithIndicator_(self, indicator):
        self = objc.super(MacFreeModeIndicatorView, self).initWithFrame_(_rect(0, 0, 150, 32))
        if self is None:
            return None
        self.indicator = indicator
        return self

    def isFlipped(self):
        return True

    def drawRect_(self, dirty_rect):
        self.indicator.draw()


class MacFreeModeIndicator:
    def __init__(self):
        self.width = 150
        self.height = 32
        self.text = 'FREE MODE'
        self.color = (0.3, 1.0, 0.5, 0.9)

        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            _rect(0, 0, self.width, self.height),
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.window.setIgnoresMouseEvents_(True)
        self.window.setReleasedWhenClosed_(False)
        self.window.setLevel_(AppKit.NSStatusWindowLevel)
        behavior = (
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | AppKit.NSWindowCollectionBehaviorStationary
        )
        self.window.setCollectionBehavior_(behavior)
        self.view = MacFreeModeIndicatorView.alloc().initWithIndicator_(self)
        self.window.setContentView_(self.view)
        self._hide_timer = None

    def _position_on_screen(self):
        mouse = AppKit.NSEvent.mouseLocation()
        target_screen = None
        for screen in AppKit.NSScreen.screens():
            if Foundation.NSPointInRect(mouse, screen.frame()):
                target_screen = screen
                break
        if target_screen is None:
            target_screen = AppKit.NSScreen.mainScreen() or AppKit.NSScreen.screens()[0]
        frame = target_screen.frame()
        x = frame.origin.x + (frame.size.width - self.width) / 2
        y = frame.origin.y + frame.size.height - self.height - 8
        self.window.setFrame_display_(_rect(x, y, self.width, self.height), True)

    def draw(self):
        bg = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.08, 0.08, 0.12, 0.85)
        bg.set()
        radius = 10
        path = AppKit.NSBezierPath.bezierPath()
        path.moveToPoint_(_point(radius, 0))
        path.lineToPoint_(_point(self.width - radius, 0))
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
            _point(self.width - radius, radius), radius, 90, 0
        )
        path.lineToPoint_(_point(self.width, self.height - radius))
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
            _point(self.width - radius, self.height - radius), radius, 0, -90
        )
        path.lineToPoint_(_point(radius, self.height))
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
            _point(radius, self.height - radius), radius, -90, -180
        )
        path.lineToPoint_(_point(0, radius))
        path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
            _point(radius, radius), radius, -180, -270
        )
        path.closePath()
        path.fill()

        font = AppKit.NSFont.monospacedSystemFontOfSize_weight_(
            14, getattr(AppKit, 'NSFontWeightBold', 0.4)
        )
        attrs = {
            AppKit.NSFontAttributeName: font,
            AppKit.NSForegroundColorAttributeName:
                AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(*self.color),
        }
        text = Foundation.NSString.stringWithString_(self.text)
        size = text.sizeWithAttributes_(attrs)
        text.drawAtPoint_withAttributes_(
            _point((self.width - size.width) / 2, (self.height - size.height) / 2),
            attrs,
        )

    def show_on(self):
        if self._hide_timer is not None:
            self._hide_timer.cancel()
            self._hide_timer = None
        self.text = 'FREE MODE'
        self.color = (0.3, 1.0, 0.5, 0.9)
        self._position_on_screen()
        self.window.orderFrontRegardless()
        self.view.setNeedsDisplay_(True)

    def flash_off(self):
        if self._hide_timer is not None:
            self._hide_timer.cancel()
            self._hide_timer = None
        self.text = 'FREE MODE OFF'
        self.color = (1.0, 0.4, 0.3, 0.9)
        self._position_on_screen()
        self.window.orderFrontRegardless()
        self.view.setNeedsDisplay_(True)
        self._hide_timer = threading.Timer(0.8, self._hide_after_flash)
        self._hide_timer.daemon = True
        self._hide_timer.start()

    def _hide_after_flash(self):
        _run_on_main(self._hide_window)

    def _hide_window(self):
        self.window.orderOut_(None)
        self._hide_timer = None


class MacFreeMode:
    """Keyboard-driven relative mouse movement and scrolling on macOS."""

    def __init__(self, config, mouse_ctrl):
        self.mouse = mouse_ctrl
        self.active = False
        self._load_config(config)
        self._indicator = MacFreeModeIndicator()

        self.move_keys = set()
        self.speed_keys = set()
        self.speed_dec = False
        self.move_velocity = [0.0, 0.0]
        self.scroll_keys = set()
        self.last_action_time = 0
        self._last_scroll_time = 0.0
        self._thread = None
        self._stop_event = threading.Event()

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
        # Minimum delay between scroll ticks (seconds). Without this, scrolling
        # fires on every ~16ms loop tick, which makes paging up/down feel much
        # too fast.
        self.wheel_interval = fm.get('wheel_interval_ms', 60) / 1000.0
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
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._thread.start()
        _run_on_main(self._indicator.show_on)
        print('Free mode ON')

    def deactivate(self):
        if not self.active:
            return
        self.active = False
        self.finish_deactivate()

    def finish_deactivate(self):
        self._stop_event.set()
        self.move_keys.clear()
        self.speed_keys.clear()
        self.scroll_keys.clear()
        self.speed_dec = False
        _run_on_main(self._indicator.flash_off)
        print('Free mode OFF')
        return False

    def toggle(self):
        if self.active:
            self.deactivate()
        else:
            self.activate()

    def on_key_down(self, key_name):
        if not self.active:
            return False

        self.last_action_time = time.time()
        key = key_name.upper()

        if key == 'I':
            self.move_keys.add('up')
            return True
        if key == 'K':
            self.move_keys.add('down')
            return True
        if key == 'J':
            self.move_keys.add('left')
            return True
        if key == 'L':
            self.move_keys.add('right')
            return True

        if key in ('S', 'D', 'F'):
            self.speed_keys.add(key)
            return True
        if key == 'A':
            self.speed_dec = True
            return True

        if key == 'M':
            self.scroll_keys.add('up')
            return True
        if key in (',', 'COMMA'):
            self.scroll_keys.add('down')
            return True
        if key in ('.', 'DOT', 'PERIOD'):
            self.scroll_keys.add('left')
            return True
        if key in ('/', 'SLASH'):
            self.scroll_keys.add('right')
            return True

        if key == 'SPACE':
            self.mouse.click('left')
            return True
        if key == 'R':
            self.mouse.click('right')
            return True
        if key == 'E':
            self.mouse.click('middle')
            return True
        if key == 'Q':
            self.mouse.click('back')
            return True
        if key == 'W':
            self.mouse.click('forward')
            return True

        return False

    def on_key_up(self, key_name):
        if not self.active:
            return False

        key = key_name.upper()
        if key == 'I':
            self.move_keys.discard('up')
            return True
        if key == 'K':
            self.move_keys.discard('down')
            return True
        if key == 'J':
            self.move_keys.discard('left')
            return True
        if key == 'L':
            self.move_keys.discard('right')
            return True

        if key in ('S', 'D', 'F'):
            self.speed_keys.discard(key)
            return True
        if key == 'A':
            self.speed_dec = False
            return True
        if key == 'M':
            self.scroll_keys.discard('up')
            return True
        if key in (',', 'COMMA'):
            self.scroll_keys.discard('down')
            return True
        if key in ('.', 'DOT', 'PERIOD'):
            self.scroll_keys.discard('left')
            return True
        if key in ('/', 'SLASH'):
            self.scroll_keys.discard('right')
            return True
        return False

    def _tick_loop(self):
        while not self._stop_event.wait(0.016):
            if not self.active:
                break
            if self.auto_off_sec > 0:
                idle = time.time() - self.last_action_time
                if idle > self.auto_off_sec:
                    self.active = False
                    self.finish_deactivate()
                    break
            self._tick()

    def _tick(self):
        speed = self.base_speed
        for _ in list(self.speed_keys):
            speed *= self.speed_mult
        if self.speed_dec:
            speed /= self.speed_mult

        tx, ty = 0.0, 0.0
        for direction in list(self.move_keys):
            if direction == 'up':
                ty -= speed
            elif direction == 'down':
                ty += speed
            elif direction == 'left':
                tx -= speed
            elif direction == 'right':
                tx += speed

        self.move_velocity[0] += (tx - self.move_velocity[0]) * self.easing
        self.move_velocity[1] += (ty - self.move_velocity[1]) * self.easing

        dx = int(round(self.move_velocity[0]))
        dy = int(round(self.move_velocity[1]))
        if dx != 0 or dy != 0:
            self.mouse.move_relative(dx, dy)
            self.last_action_time = time.time()

        scroll_snapshot = list(self.scroll_keys)
        if scroll_snapshot:
            now = time.time()
            if now - self._last_scroll_time >= self.wheel_interval:
                self._last_scroll_time = now
                scroll_speed = self.base_wheel
                for _ in list(self.speed_keys):
                    scroll_speed *= self.wheel_mult
                if self.speed_dec:
                    scroll_speed /= self.wheel_mult
                amount = max(1, int(scroll_speed))

                for direction in scroll_snapshot:
                    self.mouse.scroll(direction, amount)
                self.last_action_time = now
