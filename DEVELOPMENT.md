# ci_edit — Developer Notes

ci_edit is a terminal text editor written in Python. Its primary goal is to provide familiar GUI-style keyboard shortcuts (ctrl+s, ctrl+q, ctrl+z, etc.) in a curses-based terminal environment.

This is a fork of [google/ci_edit](https://github.com/google/ci_edit). The upstream project is no longer actively maintained; this fork continues development.

## Commands

- **run**: `./ci.py [file]`
- **test**: `python -m unittest discover -s app -p 'unit_test_*.py'`
- **format**: `yapf -i --style google <file>` (migrating toward Google Python style)

## Repository Layout

```
ci.py               Entry point
app/                All Python source and unit tests
  text_buffer.py    Top of the model inheritance chain (see Data Model below)
  mutator.py        Undo/redo tracking
  selectable.py     Selection and cursor state
  line_buffer.py    Base: file type, parsing init, binary escaping
  actions.py        Text manipulation methods (insert, delete, move, etc.)
  parser.py         Nested grammar parser (HTML/JS/CSS/etc.)
  render.py         Frame buffer (list of draw instructions)
  controller.py     Base keyboard/mouse event dispatcher
  sm_editor.py      Default (GUI-style) key bindings — CiEdit class
  em_editor.py      Emacs-style key bindings for single-line inputs
  vi_editor.py      Vi-style key bindings
  window.py         Window class hierarchy
  program_window.py Root window; owns focus management and the event loop
  ci_program.py     Application singleton (prefs, color, clipboard, buffers)
  buffer_manager.py Collection of open TextBuffers
  buffer_file.py    File I/O: path parsing, line/col extraction, git diff paths
  prefs.py          User preferences loaded from ~/.ci_edit/prefs/
  default_prefs.py  Built-in defaults (colors, grammars, file types)
  history.py        Cursor positions and recent files (pickle)
  spelling.py       Binary-search spell checker
  background.py     Background thread + instruction queue for async I/O
  color.py          Curses color pair management
  curses_util.py    Key constants, mouse parsing, Unicode utilities
  interactive_prompt.py  Execute-prompt logic (pipes, shell, logic chains)
  prediction_controller.py  File/buffer prediction dropdown
  file_manager_controller.py  File browser
  formatter.py      Format helpers (e.g., black for Python files)
  fake_curses_testing.py  Headless curses harness for integration tests
  unit_test_*.py    Unit and integration tests
design/             Design notes (glossary, save logic)
docs/               Style guide
help.md             User-facing keybindings reference
```

## Data Model (Inheritance Chain)

All text buffer state lives in a single inheritance hierarchy:

```
LineBuffer          file type, binary escaping, parse init
  └─ Selectable     cursor (penRow/penCol), selection mode and marker
       └─ Mutator   undo/redo via redo_chain list + redoIndex
            └─ Actions    text operations (insert, delete, bookmarks, etc.)
                 └─ TextBuffer   rendering, scroll, highlight, draw calls
```

Text is stored in `parser.data`. Mutations create tuples stored in `redo_chain`; rewinding the index undoes changes. The parser tokenizes the text into `ParserNode` spans to support nested grammars (e.g., JavaScript inside HTML).

## Architecture: MVC + Host/Contractor

**Model**: `TextBuffer` — holds text, cursor, selection, undo history.

**View**: `Window` hierarchy — each window knows its screen region (top, left, rows, cols) and renders via curses. `ProgramWindow` is the root; it contains `InputWindow`, `FileManagerWindow`, `PredictionWindow`, etc.

**Controller**: `Controller` subclasses — map keyboard/mouse events to model actions via a `commandSet` dict. The three main controllers are:
- `CiEdit` (`sm_editor.py`) — default GUI-style bindings
- `ViEdit` (`vi_editor.py`) — vi-style normal/insert modes
- `EditText` (`em_editor.py`) — used in single-line prompts (find, goto, open)

**Host/Contractor**: A "host" window holds focus during normal editing. A "contractor" window (e.g., FileManagerWindow, PredictionWindow) temporarily takes focus to perform a task and then returns focus to its host. Transitions go through `Window.change_focus_to()`.

## Data Flow: Keypress to Screen

```
curses.getch()
  → ProgramWindow routes to focusedWindow.controller.do_command(key)
  → Controller looks up key in commandSet → calls Actions method
  → Actions method builds change tuple → appended to Mutator.redo_chain
  → shouldReparse = True
  → LineBuffer.do_parse() tokenizes changed text via ParserNode grammar stack
  → TextBuffer.check_scroll_to_cursor() adjusts viewport
  → Render loop builds Frame (list of draw calls)
  → curses.addstr() paints screen
```

Double-buffering: a `backgroundFrame` is built and then swapped to `frontFrame` for atomic display updates.

## Testing

Tests use Python's `unittest` framework. Test files live in `app/` and are named `unit_test_*.py`.

`fake_curses_testing.py` provides a headless curses harness (`FakeCursesTestCase`) that lets integration tests inject keyboard and mouse events and verify rendered output — no real terminal required. Use this base class for any test that exercises the full UI stack.

## Key Design Decisions

- **Inheritance over composition** for the data model — the chain from `LineBuffer` to `TextBuffer` is intentional; don't flatten it without a strong reason.
- **Undo is append-only** — changes append to `redo_chain`; undoing moves the index back but does not delete history. Branching (new edit after undo) truncates the future.
- **Parsing is synchronous on the main thread** for correctness; only file I/O and spell checking run in the background thread.
- **No third-party Python dependencies** in the core editor; `third_party/` contains vendored code.
