#!/usr/bin/env python3
"""Clickless for macOS.

Uses a Quartz CGEvent tap for global keyboard events, AppKit for transparent
overlays, and Quartz mouse events for pointer control. macOS requires the
terminal or app running this script to be allowed in Accessibility permissions.
"""

import atexit
import os
import platform
import signal
import sys
import threading
import time
import traceback

import AppKit
import ApplicationServices
import CoreFoundation
import Quartz
import yaml

from mac_free_mode import MacFreeMode
from mac_keymap import (
    BACKSPACE,
    ESCAPE,
    LEFT_ALT,
    LEFT_CTRL,
    LEFT_SHIFT,
    MAC_CODE_NAMES,
    MAC_KEY_NAMES,
    RIGHT_ALT,
    RIGHT_CTRL,
    RIGHT_SHIFT,
    SPACE,
    TAB,
    code_to_grid_key,
    parse_hotkey_str,
)
from mac_mouse_control import MacMouseController
from mac_overlay import MacGridOverlay


ACTIVE_APP = None


def load_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'config.yaml')
    user_config = os.path.expanduser('~/.config/clickless/config.yaml')
    if os.path.exists(user_config):
        config_path = user_config
    with open(config_path) as file:
        return yaml.safe_load(file)


def run_on_main(callback):
    if threading.current_thread() is threading.main_thread():
        callback()
    else:
        CoreFoundation.CFRunLoopPerformBlock(
            CoreFoundation.CFRunLoopGetMain(),
            CoreFoundation.kCFRunLoopCommonModes,
            callback,
        )
        CoreFoundation.CFRunLoopWakeUp(CoreFoundation.CFRunLoopGetMain())


def accessibility_trusted(prompt=True):
    try:
        if prompt and hasattr(ApplicationServices, 'AXIsProcessTrustedWithOptions'):
            key = getattr(
                ApplicationServices,
                'kAXTrustedCheckOptionPrompt',
                'AXTrustedCheckOptionPrompt',
            )
            ApplicationServices.AXIsProcessTrustedWithOptions({key: True})
        if hasattr(ApplicationServices, 'AXIsProcessTrusted'):
            return bool(ApplicationServices.AXIsProcessTrusted())
    except Exception:
        return False
    return True


def event_tap_callback(proxy, event_type, event, refcon):
    if ACTIVE_APP is None:
        return event
    return ACTIVE_APP.handle_event(proxy, event_type, event)


class MacClickless:
    def __init__(self):
        self.config = load_config()
        self.mouse = MacMouseController()
        self.overlay = MacGridOverlay(self.config, self.mouse)
        self.free_mode = MacFreeMode(self.config, self.mouse)
        self.hotkeys = {}
        self._parse_keybindings()

        behavior = self.config.get('behavior', {})
        self.tap_threshold = behavior.get('tap_threshold_ms', 200) / 1000.0
        self.key_down_times = {}
        self.key_interrupted = set()
        self.pressed = set()
        self.consumed_keys = set()
        self._panic_timer = None
        self._event_tap = None
        self._run_loop_source = None

    def _parse_keybindings(self):
        keybindings = self.config.get('keybindings', {})
        for action_name, binding in keybindings.items():
            if isinstance(binding, list):
                parsed = []
                for item in binding:
                    hotkey = parse_hotkey_str(item)
                    if hotkey and hotkey['code'] is not None:
                        parsed.append(hotkey)
                if parsed:
                    self.hotkeys[action_name] = parsed
            else:
                hotkey = parse_hotkey_str(binding)
                if hotkey and hotkey['code'] is not None:
                    self.hotkeys[action_name] = hotkey

    def start_event_tap(self):
        mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
            | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        )
        self._event_tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            event_tap_callback,
            None,
        )
        if self._event_tap is None:
            print('Error: could not create macOS keyboard event tap.')
            print('Grant Accessibility permission to your terminal app, then run ./run_mac.sh again.')
            sys.exit(1)

        self._run_loop_source = CoreFoundation.CFMachPortCreateRunLoopSource(
            None, self._event_tap, 0
        )
        CoreFoundation.CFRunLoopAddSource(
            CoreFoundation.CFRunLoopGetCurrent(),
            self._run_loop_source,
            CoreFoundation.kCFRunLoopCommonModes,
        )
        Quartz.CGEventTapEnable(self._event_tap, True)
        atexit.register(self.stop_event_tap)

    def stop_event_tap(self):
        try:
            if self._event_tap is not None:
                Quartz.CGEventTapEnable(self._event_tap, False)
        except Exception:
            pass

    def handle_event(self, proxy, event_type, event):
        if event_type in (
            Quartz.kCGEventTapDisabledByTimeout,
            Quartz.kCGEventTapDisabledByUserInput,
        ):
            Quartz.CGEventTapEnable(self._event_tap, True)
            return event

        try:
            if event_type == Quartz.kCGEventFlagsChanged:
                return self._handle_flags_changed(event)
            if event_type not in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
                return event
            return self._handle_key_event(event_type, event)
        except Exception as exc:
            print(f'ERROR in macOS key handler: {exc}')
            traceback.print_exc()
            return event

    def _handle_flags_changed(self, event):
        code = int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode))
        flags = int(Quartz.CGEventGetFlags(event))
        is_down = self._modifier_is_down(code, flags)
        event_type = Quartz.kCGEventKeyDown if is_down else Quartz.kCGEventKeyUp
        return self._handle_key_event(event_type, event, code_override=code)

    def _modifier_is_down(self, code, flags):
        if code in (LEFT_SHIFT, RIGHT_SHIFT, LEFT_CTRL, RIGHT_CTRL, LEFT_ALT, RIGHT_ALT):
            return code not in self.pressed
        return code not in self.pressed

    def _handle_key_event(self, event_type, event, code_override=None):
        code = code_override
        if code is None:
            code = int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode))

        consumed = False
        if event_type == Quartz.kCGEventKeyDown:
            is_repeat = bool(
                Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat)
            )
            if not is_repeat and code not in self.pressed:
                self.pressed.add(code)
                self.key_down_times[code] = time.time()
                for other in list(self.key_down_times.keys()):
                    if other != code and other in self.pressed:
                        self.key_interrupted.add(other)
                self._update_panic_timer()
                consumed = self._on_key_down(code)
            else:
                consumed = self._on_key_hold(code)
            if consumed:
                self.consumed_keys.add(code)

        elif event_type == Quartz.kCGEventKeyUp:
            self.pressed.discard(code)
            self._update_panic_timer()
            was_consumed = code in self.consumed_keys
            self.consumed_keys.discard(code)
            consumed = self._on_key_up(code)
            if was_consumed:
                consumed = True
            self.key_down_times.pop(code, None)
            self.key_interrupted.discard(code)

        return None if consumed else event

    def _update_panic_timer(self):
        both_shifts = LEFT_SHIFT in self.pressed and RIGHT_SHIFT in self.pressed
        if both_shifts and self._panic_timer is None:
            self._panic_timer = threading.Timer(1.0, self._panic_if_still_pressed)
            self._panic_timer.daemon = True
            self._panic_timer.start()
        elif not both_shifts and self._panic_timer is not None:
            self._panic_timer.cancel()
            self._panic_timer = None

    def _panic_if_still_pressed(self):
        self._panic_timer = None
        if LEFT_SHIFT in self.pressed and RIGHT_SHIFT in self.pressed:
            print('\n*** PANIC: both Shift keys held; disabling Clickless event tap ***')
            self.stop_event_tap()
            run_on_main(lambda: AppKit.NSApplication.sharedApplication().terminate_(None))

    def _is_tap(self, code):
        if code in self.key_interrupted:
            return False
        down_time = self.key_down_times.get(code)
        if down_time is None:
            return False
        return time.time() - down_time < self.tap_threshold

    def _check_hotkey(self, action_name, code, is_tap_event=False):
        hotkey = self.hotkeys.get(action_name)
        if hotkey is None:
            return False
        if isinstance(hotkey, list):
            return any(self._match_single(item, code, is_tap_event) for item in hotkey)
        return self._match_single(hotkey, code, is_tap_event)

    def _match_single(self, hotkey, code, is_tap_event):
        if hotkey['code'] != code:
            return False
        if hotkey['is_tap'] and not is_tap_event:
            return False
        if not hotkey['is_tap'] and is_tap_event:
            return False
        for modifier_code in hotkey['modifiers']:
            if modifier_code not in self.pressed:
                return False
        return True

    def _on_key_down(self, code):
        if self.overlay.is_visible:
            has_shift = LEFT_SHIFT in self.pressed or RIGHT_SHIFT in self.pressed
            has_alt = LEFT_ALT in self.pressed or RIGHT_ALT in self.pressed

            if code == ESCAPE:
                self.overlay.hide_overlay()
                return True
            if code == BACKSPACE:
                self.overlay._undo_last_key()
                return True
            if code == TAB:
                self.overlay.hide_overlay()
                print('Config editor is GTK-only for now; edit config.yaml directly on macOS.')
                return True
            if code == SPACE:
                self.overlay._execute_action_at_virtual_cursor(has_shift, has_alt)
                return True
            if code == MAC_KEY_NAMES['UP']:
                self.mouse.scroll('up', 3)
                return True
            if code == MAC_KEY_NAMES['DOWN']:
                self.mouse.scroll('down', 3)
                return True
            if code == MAC_KEY_NAMES['LEFT']:
                self.mouse.scroll('left', 3)
                return True
            if code == MAC_KEY_NAMES['RIGHT']:
                self.mouse.scroll('right', 3)
                return True

            key_char = code_to_grid_key(code)
            if key_char:
                self.overlay._handle_grid_key(key_char, has_shift, has_alt)
                return True
            return True

        if self.free_mode.active:
            key_name = MAC_CODE_NAMES.get(code, '')
            if code == SPACE:
                self.free_mode.on_key_down(key_name)
                self.free_mode.active = False
                self.free_mode.finish_deactivate()
                return True
            if self.free_mode.on_key_down(key_name):
                return True
            if code == ESCAPE:
                self.free_mode.active = False
                self.free_mode.finish_deactivate()
                return True
            return False

        return False

    def _on_key_up(self, code):
        is_tap = self._is_tap(code)

        if self.overlay.is_visible:
            if is_tap and code in (LEFT_SHIFT, RIGHT_SHIFT):
                self.overlay.cycle_or_close()
                return True
            if is_tap and code in (LEFT_CTRL, RIGHT_CTRL):
                if self.free_mode.active:
                    self.free_mode.active = False
                    self.free_mode.finish_deactivate()
                else:
                    self.free_mode.activate()
                return True
            if code in (LEFT_SHIFT, RIGHT_SHIFT):
                self.overlay.mouse_button = 'left'
            if code in (LEFT_ALT, RIGHT_ALT):
                if self.overlay.action_type == 'move':
                    self.overlay.action_type = 'click'
            return True

        if self.free_mode.active:
            key_name = MAC_CODE_NAMES.get(code, '')
            consumed = self.free_mode.on_key_up(key_name)

            if is_tap and code in (LEFT_CTRL, RIGHT_CTRL):
                self.free_mode.active = False
                self.free_mode.finish_deactivate()
                return False

            if is_tap and code in (LEFT_SHIFT, RIGHT_SHIFT):
                self.overlay.show_overlay()
                return False

            return consumed

        if is_tap:
            if code in (LEFT_SHIFT, RIGHT_SHIFT):
                self.overlay.show_overlay()
                return False
            if code in (LEFT_CTRL, RIGHT_CTRL):
                self.free_mode.activate()
                return False

        return False

    def _on_key_hold(self, code):
        if self.overlay.is_visible:
            return True
        if self.free_mode.active:
            key_name = MAC_CODE_NAMES.get(code, '').upper()
            if key_name in (
                'I', 'K', 'J', 'L', 'S', 'D', 'F', 'A', 'M',
                'COMMA', 'DOT', 'PERIOD', 'SLASH', 'SPACE', 'R', 'E', 'Q', 'W',
            ):
                return True
        return False

    def run(self):
        print('Clickless running for macOS (Quartz event tap)')
        print('  Shift tap     -> toggle grid overlay / cycle monitors')
        print('  Ctrl tap      -> toggle free mode')
        print('  Escape        -> dismiss overlay / exit free mode')
        print('  Safety        -> hold both Shift keys for 1s to exit')
        self.start_event_tap()
        AppKit.NSApplication.sharedApplication().run()


def main():
    global ACTIVE_APP
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    if platform.system() != 'Darwin':
        print('mac_main.py only runs on macOS. Use ./run.sh on Linux.')
        sys.exit(1)

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    if not accessibility_trusted(prompt=True):
        print('macOS Accessibility permission is required.')
        print('Open System Settings -> Privacy & Security -> Accessibility and enable your terminal app.')

    ACTIVE_APP = MacClickless()
    ACTIVE_APP.run()


if __name__ == '__main__':
    main()
