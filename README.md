# Clickless

Free keyboard-driven mouse control, split by platform.

Open the folder for your operating system:

| Platform | Folder | Start here |
|----------|--------|------------|
| macOS | `macos/` | `macos/README.md` |
| Linux X11 | `linux/` | `linux/README.md` |
| External ideas | `integrations/` | `integrations/README.md` |

## Quick Start

macOS:

```bash
cd macos
./install.sh
./run.sh
```

Linux:

```bash
cd linux
./install.sh
./run.sh
```

## Default Keys

| Key | Action |
|-----|--------|
| Shift tap | Show/cycle grid overlay |
| Ctrl tap | Toggle free mouse mode |
| I / J / K / L | Move/refine cursor |
| Space | Click |
| Escape | Close overlay / exit mode |
| Both Shift keys for 1 second | Emergency stop |

See the platform README for system permissions and dependencies.

## Integrations

`integrations/handy` is a Git submodule for exploring voice control through Handy's offline speech-to-text app. Clone with submodules when you want that folder populated:

```bash
git clone --recurse-submodules https://github.com/goldenamir/clickless.git
```
