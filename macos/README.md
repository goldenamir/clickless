# Clickless for macOS

This folder contains the macOS version of Clickless.

It uses:

- AppKit for the transparent grid overlay
- Quartz for mouse movement, clicking, scrolling, and global keyboard events
- PyObjC for Python bindings to macOS frameworks

## Install

```bash
./install.sh
```

The installer uses Poetry for Python dependency management.

## Required Permission

Enable Accessibility access for the terminal or app that runs Clickless:

```text
System Settings -> Privacy & Security -> Accessibility
```

If key events are still not received, also enable the same app under Input Monitoring.

## Run

Foreground:

```bash
./run.sh
```

Background with launchd:

```bash
./start_background.sh
```

Stop the background job:

```bash
./stop.sh
```

## Keys

| Key | Action |
|-----|--------|
| Shift tap | Show/cycle grid overlay |
| Ctrl tap | Toggle free mouse mode |
| I / J / K / L | Move/refine cursor |
| S / D / F | Speed boost in free mode |
| A | Slow down in free mode |
| Space | Click |
| Escape | Close overlay / exit mode |
| Both Shift keys for 1 second | Emergency stop |

## Speed

Free-mode speed is configured in `config.yaml`:

```yaml
behavior:
  free_mode:
    base_move_speed: 24
    movement_easing_factor: 0.45
```

Increase `base_move_speed` for a faster cursor, then restart Clickless.
