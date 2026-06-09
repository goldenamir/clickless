# Integrations

This folder is for external projects that can help Clickless grow beyond keyboard-driven mouse control.

## Handy

`handy/` is a Git submodule pointing to [`cjpais/Handy`](https://github.com/cjpais/Handy).

Handy is an offline speech-to-text desktop app. The most practical Clickless integration idea is:

```text
voice command
  -> Handy local transcription
  -> Clickless command parser
  -> Clickless macOS/Linux mouse backend
  -> optional screenshot/accessibility verification
```

Example future commands:

- "click the blue submit button"
- "open Downloads"
- "move to the search field"
- "select the second file"

Keep Handy as a separate submodule instead of copying its source into Clickless. That makes ownership clear and lets each project update independently.

## Clone With Integrations

```bash
git clone --recurse-submodules https://github.com/goldenamir/clickless.git
```

If the repo was already cloned:

```bash
git submodule update --init --recursive
```
