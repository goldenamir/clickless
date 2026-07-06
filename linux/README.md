# Clickless for Linux

This folder contains the original Linux X11 version of Clickless.

It uses:

- GTK 3 for the transparent grid overlay
- `evdev` and `uinput` for keyboard capture and forwarding
- `xdotool` for mouse movement, clicking, scrolling, and dragging

## Install

```bash
./install.sh
```

## Run

```bash
./run.sh
```

This starts Clickless in the background, so it keeps running after you close the terminal.
Logs are written to `~/.local/state/clickless/linux.log`.

## Requirements

- Linux with X11
- Python 3.10+
- GTK 3 and PyGObject
- `xdotool`
- Keyboard input access, usually by being in the `input` group

## Keys

| Key | Action |
|-----|--------|
| Shift tap | Show/cycle grid overlay |
| Ctrl tap | Toggle free mouse mode |
| A-Z first letter | Filter grid to matching row |
| A-Z second letter | Jump cursor to that cell |
| I / K / J / L | Refine cursor position |
| S / D / F | Speed boost in free mode |
| A | Slow down in free mode |
| Space | Click |
| Backspace | Undo last grid key |
| Escape | Close overlay / exit mode |
| Both Shift keys for 1 second | Emergency ungrab and exit |

## Config

Edit `config.yaml` in this folder, then restart Clickless.
