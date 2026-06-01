# Clickless

Free keyboard-driven mouse control for Linux. Inspired by [Mouseless](https://www.mouseless.click) and [mousemaster](https://github.com/petoncle/mousemaster).

## Features

- **Grid overlay** — Shift tap to activate. Type 2-letter label to jump cursor to that cell. Then IJKL to refine position. Space to click.
- **Free mode** — Ctrl tap to activate. IJKL for continuous mouse movement with easing. Space to click.
- **Multi-monitor** — Shift tap cycles monitors while overlay is open.
- **Modifier clicks** — Hold Shift for right-click, Alt for move-only, Alt+Shift for drag & drop.
- **Scrolling** — Arrow keys scroll while overlay is open. M/, in free mode.

## Install

```bash
./install.sh
```

## Run

```bash
./run.sh
```

## Safety

Hold **both Shift keys** for 1 second to emergency ungrab the keyboard and exit.

## Keys (Grid Overlay)

| Key | Action |
|-----|--------|
| Shift tap | Show/cycle monitor |
| A-Z (1st letter) | Filter grid to matching row |
| A-Z (2nd letter) | Jump cursor to that cell |
| I / K / J / L | Refine: shrink up / down / left / right |
| Space | Click at cursor position |
| Backspace | Undo last keystroke |
| Escape | Close overlay |

## Keys (Free Mode)

| Key | Action |
|-----|--------|
| Ctrl tap | Toggle free mode |
| I / K / J / L | Move mouse: up / down / left / right |
| S / D / F | Speed boost (stackable) |
| A | Slow down |
| Space | Click + exit |

## Requirements

- Linux with X11
- Python 3.10+
- GTK 3, PyGObject, xdotool

## License

MIT
