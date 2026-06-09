#!/usr/bin/env python3
"""Clickless - Free keyboard-driven mouse control for Linux

Uses evdev grab + uinput virtual keyboard to:
- Intercept keys exclusively (suppresses them from reaching apps)
- Forward non-consumed keys through a virtual keyboard
- Provide grid overlay and free mode without leaking keystrokes
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')

import os
import sys
import signal
import shutil
import threading
import time
import atexit
import traceback
import yaml
import evdev
from evdev import ecodes, UInput
from gi.repository import Gtk, GLib
from overlay import GridOverlay
from mouse_control import MouseController
from free_mode import FreeMode


# ── Key name mapping ─────────────────────────────────────────────

EVDEV_KEY_NAMES = {}
for attr in dir(ecodes):
    if attr.startswith('KEY_'):
        EVDEV_KEY_NAMES[attr[4:].upper()] = getattr(ecodes, attr)

_ALIASES = {
    'SHIFTLEFT': ecodes.KEY_LEFTSHIFT, 'SHIFTRIGHT': ecodes.KEY_RIGHTSHIFT,
    'SHIFT_L': ecodes.KEY_LEFTSHIFT, 'SHIFT_R': ecodes.KEY_RIGHTSHIFT,
    'CONTROLLEFT': ecodes.KEY_LEFTCTRL, 'CONTROLRIGHT': ecodes.KEY_RIGHTCTRL,
    'CTRL_L': ecodes.KEY_LEFTCTRL, 'CTRL_R': ecodes.KEY_RIGHTCTRL,
    'CTRLLEFT': ecodes.KEY_LEFTCTRL, 'CTRLRIGHT': ecodes.KEY_RIGHTCTRL,
    'ALTLEFT': ecodes.KEY_LEFTALT, 'ALTRIGHT': ecodes.KEY_RIGHTALT,
    'ALT_L': ecodes.KEY_LEFTALT, 'ALT_R': ecodes.KEY_RIGHTALT,
    'METALEFT': ecodes.KEY_LEFTMETA, 'METARIGHT': ecodes.KEY_RIGHTMETA,
    'SHIFT': ecodes.KEY_LEFTSHIFT, 'CTRL': ecodes.KEY_LEFTCTRL,
    'CONTROL': ecodes.KEY_LEFTCTRL, 'ALT': ecodes.KEY_LEFTALT,
    'OPTION': ecodes.KEY_LEFTALT, 'META': ecodes.KEY_LEFTMETA,
    'CMD': ecodes.KEY_LEFTMETA, 'WIN': ecodes.KEY_LEFTMETA,
    'SEMICOLON': ecodes.KEY_SEMICOLON,
}
EVDEV_KEY_NAMES.update(_ALIASES)
for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
    EVDEV_KEY_NAMES[c] = getattr(ecodes, f'KEY_{c}')
for d in '0123456789':
    EVDEV_KEY_NAMES[d] = getattr(ecodes, f'KEY_{d}')
EVDEV_KEY_NAMES[','] = ecodes.KEY_COMMA
EVDEV_KEY_NAMES['.'] = ecodes.KEY_DOT
EVDEV_KEY_NAMES['/'] = ecodes.KEY_SLASH
EVDEV_KEY_NAMES[';'] = ecodes.KEY_SEMICOLON

EVDEV_CODE_NAMES = {}
for attr in dir(ecodes):
    if attr.startswith('KEY_'):
        code = getattr(ecodes, attr)
        name = attr[4:]
        if code not in EVDEV_CODE_NAMES or len(name) < len(EVDEV_CODE_NAMES[code]):
            EVDEV_CODE_NAMES[code] = name


def parse_hotkey_str(s):
    if not s or not s.strip():
        return None
    s = s.strip()
    is_tap = False
    is_double_tap = False
    parts = s.split()
    if len(parts) >= 2:
        if parts[-1].lower() == 'tap':
            is_tap = True
            s = ' '.join(parts[:-1])
        elif len(parts) >= 3 and parts[-1].lower() == 'tap' and parts[-2].lower() == 'double':
            is_double_tap = True
            s = ' '.join(parts[:-2])
    keys = [k.strip() for k in s.split('+')]
    main_key = keys[-1].upper()
    modifiers = set()
    for m in keys[:-1]:
        code = EVDEV_KEY_NAMES.get(m.upper())
        if code is not None:
            modifiers.add(code)
    key_code = EVDEV_KEY_NAMES.get(main_key)
    return {'code': key_code, 'modifiers': modifiers, 'is_tap': is_tap, 'is_double_tap': is_double_tap}


def load_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'config.yaml')
    user_config = os.path.expanduser('~/.config/clickless/config.yaml')
    if os.path.exists(user_config):
        config_path = user_config
    with open(config_path) as f:
        return yaml.safe_load(f)


def _evdev_to_grid_key(code):
    """Convert evdev key code to the key char the overlay expects."""
    name = EVDEV_CODE_NAMES.get(code, '')
    if len(name) == 1:
        return name
    return {'SEMICOLON': ';', 'COMMA': ',', 'DOT': '.', 'SLASH': '/'}.get(name)


def find_keyboard():
    """Auto-detect the main keyboard device."""
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        caps = dev.capabilities()
        if ecodes.EV_KEY in caps:
            keys = caps[ecodes.EV_KEY]
            if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                return dev
    return None


class Clickless:

    def __init__(self):
        self.config = load_config()
        self.mouse = MouseController()
        self.overlay = GridOverlay(self.config, self.mouse)
        self.free_mode = FreeMode(self.config, self.mouse)

        self.hotkeys = {}
        self._parse_keybindings()

        # Tap detection
        self.tap_threshold = self.config.get('behavior', {}).get('tap_threshold_ms', 200) / 1000.0
        self.key_down_times = {}
        self.key_interrupted = set()
        self.pressed = set()
        self.consumed_keys = set()  # keys consumed by overlay/free mode (eat their key-ups too)

        # Virtual keyboard for forwarding
        self.uinput = None
        self._start_listener()

    def _parse_keybindings(self):
        kb = self.config.get('keybindings', {})
        for action_name, binding_str in kb.items():
            if isinstance(binding_str, list):
                parsed = []
                for bs in binding_str:
                    p = parse_hotkey_str(str(bs))
                    if p and p['code'] is not None:
                        parsed.append(p)
                if parsed:
                    self.hotkeys[action_name] = parsed
            else:
                p = parse_hotkey_str(str(binding_str))
                if p and p['code'] is not None:
                    self.hotkeys[action_name] = p

    def _start_listener(self):
        kbd = find_keyboard()
        if kbd is None:
            print("Error: no keyboard found. Are you in the 'input' group?")
            sys.exit(1)
        self._kbd = kbd
        print(f"Keyboard: {kbd.name} ({kbd.path})")

        # Create virtual keyboard to forward non-consumed keys
        caps = kbd.capabilities()
        caps.pop(ecodes.EV_SYN, None)  # UInput adds SYN automatically
        self.uinput = UInput(caps, name='clickless-virtual-kbd')
        print(f"Virtual keyboard: {self.uinput.name}")

        # Grab the real keyboard exclusively
        kbd.grab()
        print("Keyboard grabbed (exclusive mode)")
        print("SAFETY: Hold BOTH Shift keys for 1s → emergency ungrab + exit")

        # Safety: ungrab on exit/crash
        atexit.register(self._emergency_ungrab)
        signal.signal(signal.SIGTERM, self._signal_exit)
        signal.signal(signal.SIGHUP, self._signal_exit)

        t = threading.Thread(target=self._listen_loop, args=(kbd,), daemon=True)
        t.start()

    def _emergency_ungrab(self):
        """Release keyboard grab - called on exit/crash."""
        try:
            if self._kbd:
                self._kbd.ungrab()
                print("Keyboard ungrabbed (safety release)")
        except Exception:
            pass

    def _signal_exit(self, signum, frame):
        self._emergency_ungrab()
        sys.exit(0)

    def _listen_loop(self, kbd):
        both_shifts_since = None

        for event in kbd.read_loop():
            if event.type != ecodes.EV_KEY:
                # Forward non-key events
                self.uinput.write_event(event)
                self.uinput.syn()
                continue

            # ── PANIC COMBO: both shifts held for 1 second → ungrab + exit ──
            both_held = (ecodes.KEY_LEFTSHIFT in self.pressed and
                         ecodes.KEY_RIGHTSHIFT in self.pressed)
            if both_held:
                if both_shifts_since is None:
                    both_shifts_since = time.time()
                elif time.time() - both_shifts_since > 1.0:
                    print("\n*** PANIC: Both shifts held → ungrabbing keyboard ***")
                    kbd.ungrab()
                    # Forward the shift releases so they don't stick
                    self.uinput.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
                    self.uinput.write(ecodes.EV_KEY, ecodes.KEY_RIGHTSHIFT, 0)
                    self.uinput.syn()
                    os._exit(0)
            else:
                both_shifts_since = None

            # ── Process the key event safely ──
            try:
                key_event = evdev.categorize(event)
                consumed = False

                if key_event.keystate == key_event.key_down:
                    self.pressed.add(event.code)
                    self.key_down_times[event.code] = time.time()
                    for other in list(self.key_down_times.keys()):
                        if other != event.code and other in self.pressed:
                            self.key_interrupted.add(other)
                    consumed = self._on_key_down(event.code)
                    if consumed:
                        self.consumed_keys.add(event.code)

                elif key_event.keystate == key_event.key_up:
                    self.pressed.discard(event.code)
                    # Always eat key-ups for keys whose key-down was consumed
                    was_consumed = event.code in self.consumed_keys
                    self.consumed_keys.discard(event.code)
                    consumed = self._on_key_up(event.code)
                    if not consumed and was_consumed:
                        consumed = True
                    self.key_down_times.pop(event.code, None)
                    self.key_interrupted.discard(event.code)

                elif key_event.keystate == key_event.key_hold:
                    consumed = self._on_key_hold(event.code)

                # Forward to virtual keyboard if NOT consumed
                if not consumed:
                    self.uinput.write_event(event)
                    self.uinput.syn()

            except Exception as e:
                # SAFETY: On ANY error, always forward the key so user isn't locked out
                print(f"ERROR in key handler: {e}")
                traceback.print_exc()
                try:
                    self.uinput.write_event(event)
                    self.uinput.syn()
                except Exception:
                    pass

    def _is_tap(self, code):
        if code in self.key_interrupted:
            return False
        down_time = self.key_down_times.get(code)
        if down_time is None:
            return False
        return (time.time() - down_time) < self.tap_threshold

    def _check_hotkey(self, action_name, code, is_tap_event=False):
        hk = self.hotkeys.get(action_name)
        if hk is None:
            return False
        if isinstance(hk, list):
            return any(self._match_single(h, code, is_tap_event) for h in hk)
        return self._match_single(hk, code, is_tap_event)

    def _match_single(self, hk, code, is_tap_event):
        if hk['code'] != code:
            return False
        if hk['is_tap'] and not is_tap_event:
            return False
        if not hk['is_tap'] and is_tap_event:
            return False
        for mod_code in hk['modifiers']:
            if mod_code not in self.pressed:
                return False
        return True

    # ── Key events ───────────────────────────────────────────

    def _on_key_down(self, code):
        """Returns True if key is consumed (not forwarded)."""

        # ── Overlay is visible: consume ALL keys ──
        if self.overlay.is_visible:
            has_shift = (ecodes.KEY_LEFTSHIFT in self.pressed or
                         ecodes.KEY_RIGHTSHIFT in self.pressed)
            has_alt = (ecodes.KEY_LEFTALT in self.pressed or
                       ecodes.KEY_RIGHTALT in self.pressed)

            # Escape → hide overlay
            if code == ecodes.KEY_ESC:
                GLib.idle_add(self.overlay.hide_overlay)
                return True
            # Backspace → undo
            if code == ecodes.KEY_BACKSPACE:
                GLib.idle_add(self.overlay._undo_last_key)
                return True
            # Tab → hide
            if code == ecodes.KEY_TAB:
                GLib.idle_add(self.overlay.hide_overlay)
                return True
            # Space → execute action
            if code == ecodes.KEY_SPACE:
                GLib.idle_add(self.overlay._execute_action_at_virtual_cursor,
                              has_shift, has_alt)
                return True
            # Grid/subgrid key
            key_char = _evdev_to_grid_key(code)
            if key_char:
                GLib.idle_add(self.overlay._handle_grid_key, key_char,
                              has_shift, has_alt)
                return True
            # Consume everything else (modifiers etc.)
            return True

        # ── Free mode active: consume movement keys ──
        if self.free_mode.active:
            key_name = EVDEV_CODE_NAMES.get(code, '')
            # Space → click and exit free mode
            if code == ecodes.KEY_SPACE:
                self.free_mode.on_key_down(key_name)  # performs click
                self.free_mode.active = False  # stop consuming keys immediately
                GLib.idle_add(self.free_mode.finish_deactivate)
                return True
            if self.free_mode.on_key_down(key_name):
                return True  # Movement/action key consumed
            # Escape → deactivate free mode
            if code == ecodes.KEY_ESC:
                self.free_mode.active = False  # stop consuming keys immediately
                GLib.idle_add(self.free_mode.finish_deactivate)
                return True
            # Other keys pass through (typing still works for non-free-mode keys)
            return False

        # ── Nothing active: no consumption on key down ──
        return False

    def _on_key_up(self, code):
        """Returns True if key is consumed."""
        is_tap = self._is_tap(code)

        # ── Overlay visible ──
        if self.overlay.is_visible:
            # Shift tap → next monitor or close after last
            if is_tap and code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                GLib.idle_add(self.overlay.cycle_or_close)
                return True
            # Modifier state updates
            if code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                self.overlay.mouse_button = 'left'
            if code in (ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT):
                if self.overlay.action_type == 'move':
                    self.overlay.action_type = 'click'
            return True  # Consume all key-ups while overlay is visible

        # ── Free mode active ──
        if self.free_mode.active:
            key_name = EVDEV_CODE_NAMES.get(code, '')
            consumed = self.free_mode.on_key_up(key_name)

            # Ctrl tap → deactivate free mode (toggle off)
            if is_tap and code in (ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL):
                self.free_mode.active = False  # stop consuming keys immediately
                GLib.idle_add(self.free_mode.finish_deactivate)
                return False  # Forward key-up so Ctrl doesn't stay stuck in uinput

            # Shift tap → show overlay (works FROM free mode)
            if is_tap and code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                GLib.idle_add(self.overlay.show_overlay)
                return False  # Forward key-up so Shift doesn't stay stuck in uinput

            return consumed

        # ── Nothing active: check tap hotkeys ──
        if is_tap:
            # Shift tap → show overlay
            if code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                GLib.idle_add(self.overlay.show_overlay)
                return False  # Forward key-up so Shift doesn't stay stuck in uinput
            # Ctrl tap → activate free mode
            if code in (ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL):
                GLib.idle_add(self.free_mode.activate)
                return False  # Forward key-up so Ctrl doesn't stay stuck in uinput

        return False

    def _on_key_hold(self, code):
        """Returns True if key repeat is consumed."""
        if self.overlay.is_visible:
            return True  # Suppress all repeats in overlay
        if self.free_mode.active:
            key_name = EVDEV_CODE_NAMES.get(code, '')
            # Consume repeats for free mode keys
            k = key_name.upper()
            if k in ('I', 'K', 'J', 'L', 'S', 'D', 'F', 'A', 'M',
                     'COMMA', 'PERIOD', 'SLASH', 'SPACE', 'R', 'E', 'Q', 'W'):
                return True
        return False

    def run(self):
        print("Clickless running (evdev grab + uinput)")
        print("  Shift tap     → toggle grid overlay")
        print("  Ctrl tap      → toggle free mode")
        print("  Escape        → dismiss overlay / exit free mode")
        print("  Grid: type cell key → type sub-cell key → click")
        print("  Free mode: IJKL=move, Space=click, keys suppressed")
        Gtk.main()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    if not shutil.which('xdotool'):
        print("Error: xdotool required. Install with: sudo apt install xdotool")
        sys.exit(1)
    app = Clickless()
    app.run()


if __name__ == '__main__':
    main()
