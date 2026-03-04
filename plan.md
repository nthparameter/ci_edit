# Plan: Right-Click Context Menu

## Current State

There's already a **partial implementation** scattered across the codebase:

- **`Menu` class** (`window.py:552-590`) — A `ViewWindow` subclass with `add_item()`, `clear()`, `move_size_to_fit()`, and `render()`. Hardcodes 3 items ("some menu", "cut", "paste"). Has no keyboard navigation, no click handling, no dismiss logic.
- **`context_menu` instance** (`window.py:1106`) — Created as a child of every `InputWindow`.
- **`present_modal()` system** (`program_window.py:365-373`) — Already supports showing/hiding one modal at a time. Calls `move_size_to_fit(top, left)` and `bring_to_front()`.
- **Disabled trigger** (`actions.py:1569`) — Ctrl+click was wired to `present_modal(context_menu)` but is wrapped in `if 0:`.
- **Right-click (BUTTON3)** — Fully detected by curses (`mousemask(-1)`) and named in `curses_util.py`, but **completely ignored** in `handle_mouse()`. Falls through to the debug log.
- **`context_menu` color** — Already defined in all three palettes (8/16/256 color) in `default_prefs.py`.

## What Needs to Happen

### 1. Handle BUTTON3 in the mouse dispatcher (`program_window.py`)

Add an `elif b_state & curses.BUTTON3_PRESSED:` branch in `handle_mouse()` (around line 258, before the wheel-up check). This should:

- Find the clicked window (already done above in the method)
- Change focus to it if needed (already done)
- Convert to local coordinates (already done)
- Call a new `window.mouse_right_click(row, col, shift, ctrl, alt)` method

### 2. Add `mouse_right_click()` to the window hierarchy

- Add a default no-op `mouse_right_click()` on `ViewWindow` (alongside the existing `mouse_click`, `mouse_release`, etc.)
- Override in the `Window` class to forward to the controller (same pattern as `mouse_click`)

### 3. Wire the trigger in the controller (`actions.py`)

In the `CuaPlusEdit` controller (or its parent), add a `mouse_right_click()` handler that calls `self.view.present_modal(self.view.context_menu, pane_row, pane_col)`. This replaces the disabled `if 0:` ctrl+click code.

### 4. Flesh out the `Menu` class (`window.py`)

The existing skeleton needs:

- **Dynamic items**: `move_size_to_fit()` should build the menu items based on context (has selection? clipboard non-empty? read-only?). Reasonable starting set:
  - Cut / Copy / Paste (cut/copy disabled if no selection; paste disabled if clipboard empty)
  - Select All
  - Undo / Redo
  - Find (opens InteractiveFind)
- **Highlight rendering**: Track a `selected_index` and render the highlighted item in a different color.
- **Keyboard navigation**: Up/Down to move highlight, Enter to execute, Escape to dismiss.
- **Mouse click on item**: `mouse_click()` should execute the corresponding command and dismiss.
- **Dismiss**: Clicking outside the menu or pressing Escape should call `self.host.present_modal(None)` (which calls `normalize()`). Need a `hide()` method that calls `detach()`.
- **Screen edge clamping**: `move_size_to_fit()` should clamp position so the menu doesn't render off-screen.

### 5. Make Menu focusable for keyboard navigation

Currently `Menu` extends `ViewWindow` (not focusable, no controller). Two approaches:

**Option A — Keep Menu as ViewWindow, handle keys in ProgramWindow:**
The modal_ui could intercept keys before they reach the focused window. Simpler but less encapsulated.

**Option B — Make Menu extend ActiveWindow with its own controller:**
Give it `is_focusable = True` and a small controller that handles Up/Down/Enter/Escape. This follows the existing pattern (InteractiveFind, PredictionWindow, etc.).

**Recommendation: Option B** — it's consistent with the rest of the codebase. The controller would be small (< 30 lines).

### 6. Dismiss on outside click

In `handle_mouse()`, if `modal_ui` is set and the click lands outside it, call `normalize()` to dismiss. Add this check early in `handle_mouse()`, before the existing window-finding logic.

## Files to Change

| File | Change |
|------|--------|
| `app/program_window.py` | Add BUTTON3 dispatch in `handle_mouse()`; add outside-click dismiss |
| `app/window.py` | Expand `Menu` class (rendering, highlight, keyboard, click, hide/dismiss); add `mouse_right_click()` to `ViewWindow` and `Window` |
| `app/actions.py` | Add `mouse_right_click()` handler in controller; remove the `if 0:` block |
| `app/cu_editor.py` (new controller) | Small controller for Menu keyboard nav (Up/Down/Enter/Esc), or add to existing controllers |
| `app/curses_util.py` | No changes needed — BUTTON3 constants already exist |
| `app/default_prefs.py` | Possibly add a `context_menu_highlight` color for selected item |

## Rendering Approach

The menu renders as a floating rectangle overlaid on the editor content. Since curses doesn't have true z-order compositing, the menu simply draws over whatever is underneath (same as PopupWindow and other overlays). When dismissed, the next full render cycle redraws the underlying content.

The existing `Menu.render()` already does this — it writes lines with `write_line()` using absolute screen coordinates. It just needs the highlight row differentiation.

## Estimated Scope

- ~20 lines in `program_window.py` (BUTTON3 dispatch + outside-click dismiss)
- ~80 lines in `window.py` (expand Menu class)
- ~30 lines for a Menu controller
- ~5 lines in `actions.py` (wire the trigger)
- ~5 lines in `default_prefs.py` (highlight color)

Total: ~140 lines of new/modified code.
