# Copyright 2018 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import curses
import os
import signal
import sys

import app.curses_util
import app.debug_window
import app.file_manager_window
import app.log
import app.prediction_window
import app.window

class ProgramWindow(app.window.ActiveWindow):
    """The outermost window. This window doesn't draw content itself. It is
    primarily a container the child windows that make up the UI. The program
    window is expected to be a singleton. The program window has no parent (the
    parent is None). Calls that propagate up the window tree stop here or jump
    over to the |program|."""

    def __init__(self, program):
        if app.config.strict_debug:
            assert issubclass(program.__class__, app.ci_program.CiProgram), self
        app.window.ActiveWindow.__init__(self, program, None)
        self.clicks = 0
        self.focused_window = None
        self.modal_ui = None
        self.program = program
        self.prior_click = 0
        self.saved_mouse_button_1_down = False
        self.saved_mouse_window = None
        self.saved_mouse_x = -1
        self.saved_mouse_y = -1
        self.show_log_window = self.program.prefs.startup["show_log_window"]
        self.debug_window = app.debug_window.DebugWindow(self.program, self)
        self.debug_undo_window = app.debug_window.DebugUndoWindow(self.program, self)
        self.log_window = app.window.LogWindow(self.program, self)
        self.popup_window = app.window.PopupWindow(self.program, self)
        self.palette_window = app.window.PaletteWindow(self.program, self)
        # The input window is the main document window.
        self.input_window = app.window.InputWindow(self.program, self)
        self.input_window.parent = self
        # Set up file manager.
        self.file_manager_window = app.file_manager_window.FileManagerWindow(
            self.program, self, self.input_window
        )
        self.file_manager_window.parent = self
        # Set up prediction.
        self.prediction_window = app.prediction_window.PredictionWindow(
            self.program, self
        )
        self.prediction_window.parent = self
        # Put the input window in front on startup.
        self.input_window.reattach()

    def change_focus_to(self, change_to):
        self.focused_window.controller.on_change()
        # Unfocus all the windows from the prior focused window to the common
        # root.
        common_root = self.find_common_root(self.focused_window, change_to)
        current = self.focused_window
        while current != common_root:
            if current.is_focusable:
                current.unfocus()
            current = current.parent
        self.set_focused_window(change_to)

    def debug_draw(self, win):
        if self.show_log_window:
            self.debug_window.debug_draw(self.program, win)
            self.debug_undo_window.debug_undo_draw(win)

    def execute_command_list(self, cmd_list):
        for cmd, event_info in cmd_list:
            self.do_pre_command()
            if cmd == curses.KEY_RESIZE:
                self.handle_screen_resize(self.focused_window)
                continue
            self.focused_window.controller.do_command(cmd, event_info)
            if cmd == curses.KEY_MOUSE:
                self.handle_mouse(event_info)
            self.focused_window.controller.on_change()

    def find_common_root(self, first, second):
        """Find the Window that is the parent of both |first| and |second|. If
        |first| is a (grand*)parent of |second|, return |first| (or vice versa).
        """
        # assert self.focused_window is not change_to
        if first is second:
            return first
        first_path = [first]
        while first_path[-1].parent:
            first_path.append(first_path[-1].parent)
            if first_path[-1] == second:
                return second
        second_path = [second]
        while second_path[-1].parent:
            second_path.append(second_path[-1].parent)
            if second_path[-1] == first:
                return first
        # assert first_path[-1] is second_path[-1]
        # Assumptions: The first unequal match will never be found at [-1]. A
        # match will always be found before exhausting the lists. It doesn't
        # matter which list is longer.
        for i in range(len(first_path)):
            if first_path[-(i + 1)] is not second_path[-(i + 1)]:
                root = first_path[-i]
                break
        return root

    def focus(self):
        self.set_focused_window(self.z_order[-1])

    def set_focused_window(self, window):
        # Depth-first search for focusable window.
        depth = [window]
        while len(depth):
            possibility = depth.pop()
            if possibility.is_focusable:
                if app.config.strict_debug:
                    assert issubclass(possibility.__class__, app.window.ActiveWindow)
                    assert possibility.controller
                self.focused_window = possibility
                self.focused_window.focus()
                self.focused_window.text_buffer.compound_change_push()
                return
            depth += possibility.z_order
            app.log.info(depth)
        app.log.error("focusable window not found")

    def do_pre_command(self):
        # Reset UI elements that adjust when new commands are issued.
        # E.g. set_message()
        win = self.focused_window
        while win is not None and win is not self:
            win.do_pre_command()
            win = win.parent

    def long_time_slice(self):
        """returns whether work is finished (no need to call again)."""
        win = self.focused_window
        while win is not None and win is not self:
            if not win.long_time_slice():
                return False
            win = win.parent
        return True

    def short_time_slice(self):
        """returns whether work is finished (no need to call again)."""
        win = self.focused_window
        while win is not None and win is not self:
            if not win.short_time_slice():
                return False
            # assert win is not win.parent
            win = win.parent
        return True

    def clicked_nearby(self, row, col):
        y, x = self.prior_click_row_col
        return y - 1 <= row <= y + 1 and x - 1 <= col <= x + 1

    def handle_mouse(self, info):
        """Mouse handling is a special case. The getch() curses function will
        signal the existence of a mouse event, but the event must be fetched and
        parsed separately."""
        (_, mouse_col, mouse_row, _, b_state) = info[0]
        app.log.mouse()
        event_time = info[1]
        rapid_click_timeout = 0.5

        def find_window(parent, mouse_row, mouse_col):
            for window in reversed(parent.z_order):
                if window.contains(mouse_row, mouse_col):
                    return find_window(window, mouse_row, mouse_col)
            return parent

        window = find_window(self, mouse_row, mouse_col)
        if window == self:
            app.log.mouse("click landed on screen")
            return
        if self.focused_window != window and window.is_focusable:
            app.log.debug("before change focus")
            window.change_focus_to(window)
            app.log.debug("after change focus")
        mouse_row -= window.top
        mouse_col -= window.left
        app.log.mouse(mouse_row, mouse_col)
        app.log.mouse("\n", window)
        button_1_was_down = self.saved_mouse_button_1_down
        self.saved_mouse_button_1_down = False
        # app.log.info('b_state', app.curses_util.mouse_button_name(b_state))
        if b_state & curses.BUTTON1_RELEASED:
            if button_1_was_down:
                app.log.mouse(b_state, curses.BUTTON1_RELEASED)
                if self.prior_click + rapid_click_timeout <= event_time:
                    window.mouse_release(
                        mouse_row,
                        mouse_col,
                        b_state & curses.BUTTON_SHIFT,
                        b_state & curses.BUTTON_CTRL,
                        b_state & curses.BUTTON_ALT,
                    )
                # else:
                #  signal.setitimer(signal.ITIMER_REAL, rapid_click_timeout)
            else:
                # Some terminals (linux?) send BUTTON1_RELEASED after moving the
                # mouse. Specifically if the terminal doesn't use button 4 for
                # mouse movement. Mouse drag or mouse wheel movement done.
                pass
        elif b_state & curses.BUTTON1_PRESSED:
            self.saved_mouse_button_1_down = True
            if self.prior_click + rapid_click_timeout > event_time and self.clicked_nearby(
                mouse_row, mouse_col
            ):
                self.clicks += 1
                self.prior_click = event_time
                if self.clicks == 2:
                    window.mouse_double_click(
                        mouse_row,
                        mouse_col,
                        b_state & curses.BUTTON_SHIFT,
                        b_state & curses.BUTTON_CTRL,
                        b_state & curses.BUTTON_ALT,
                    )
                else:
                    window.mouse_triple_click(
                        mouse_row,
                        mouse_col,
                        b_state & curses.BUTTON_SHIFT,
                        b_state & curses.BUTTON_CTRL,
                        b_state & curses.BUTTON_ALT,
                    )
                    self.clicks = 1
            else:
                self.clicks = 1
                self.prior_click = event_time
                self.prior_click_row_col = (mouse_row, mouse_col)
                window.mouse_click(
                    mouse_row,
                    mouse_col,
                    b_state & curses.BUTTON_SHIFT,
                    b_state & curses.BUTTON_CTRL,
                    b_state & curses.BUTTON_ALT,
                )
        elif b_state & (curses.BUTTON2_PRESSED | 0x200000):
            window.mouse_wheel_up(
                b_state & curses.BUTTON_SHIFT,
                b_state & curses.BUTTON_CTRL,
                b_state & curses.BUTTON_ALT,
            )
        elif b_state & (curses.BUTTON4_PRESSED | curses.REPORT_MOUSE_POSITION):
            # Notes from testing:
            # Mac seems to send BUTTON4_PRESSED during mouse move; followed by
            #   BUTTON4_RELEASED.
            # Linux seems to send REPORT_MOUSE_POSITION during mouse move;
            # followed by
            #   BUTTON1_RELEASED.
            if self.saved_mouse_x == mouse_col and self.saved_mouse_y == mouse_row:
                if b_state & curses.REPORT_MOUSE_POSITION:
                    # This is a hack for dtterm mouse wheel on Mac OS X.
                    window.mouse_wheel_up(
                        b_state & curses.BUTTON_SHIFT,
                        b_state & curses.BUTTON_CTRL,
                        b_state & curses.BUTTON_ALT,
                    )
                else:
                    # This is the normal case:
                    window.mouse_wheel_down(
                        b_state & curses.BUTTON_SHIFT,
                        b_state & curses.BUTTON_CTRL,
                        b_state & curses.BUTTON_ALT,
                    )
            else:
                if self.saved_mouse_window and self.saved_mouse_window is not window:
                    mouse_row += window.top - self.saved_mouse_window.top
                    mouse_col += window.left - self.saved_mouse_window.left
                    window = self.saved_mouse_window
                window.mouse_moved(
                    mouse_row,
                    mouse_col,
                    b_state & curses.BUTTON_SHIFT,
                    b_state & curses.BUTTON_CTRL,
                    b_state & curses.BUTTON_ALT,
                )
        elif b_state & curses.BUTTON4_RELEASED:
            # Mouse drag or mouse wheel movement done.
            app.log.mouse("BUTTON4_RELEASED")
            pass
        else:
            app.log.mouse(
                "got b_state", app.curses_util.mouse_button_name(b_state), hex(b_state)
            )
        self.saved_mouse_window = window
        self.saved_mouse_x = mouse_col
        self.saved_mouse_y = mouse_row

    def handle_screen_resize(self, window):
        # app.log.debug('handle_screen_resize -----------------------')
        if sys.platform == "darwin":
            # Some terminals seem to resize the terminal and others leave it
            # to the application to resize the curses terminal.
            rows, cols = app.curses_util.terminal_size()
            curses.resizeterm(rows, cols)
        self.top = self.left = 0
        self.rows, self.cols = app.window.main_curses_window.getmaxyx()
        self.layout()
        window.controller.on_change()
        self.render()

    def hide(self):
        pass

    def layout(self):
        """Arrange the debug, log, and input windows."""
        rows, cols = self.rows, self.cols
        # app.log.detail('layout', rows, cols)
        if self.show_log_window:
            input_width = min(88, cols)
            debug_width = max(cols - input_width - 1, 0)
            debug_rows = 20
            self.debug_window.reshape(0, input_width + 1, debug_rows, debug_width)
            self.debug_undo_window.reshape(
                debug_rows, input_width + 1, rows - debug_rows, debug_width
            )
            self.log_window.reshape(debug_rows, 0, rows - debug_rows, input_width)
            rows = debug_rows
        else:
            input_width = cols
        if 1:  # Full screen.
            for window in self.z_order:
                window.reshape(0, 0, rows, input_width)
        else:  # Split horizontally.
            count = len(self.z_order)
            each_rows = rows // count
            for i, window in enumerate(self.z_order[:-1]):
                window.reshape(each_rows * i, 0, each_rows, input_width)
            self.z_order[-1].reshape(
                each_rows * (count - 1), 0, rows - each_rows * (count - 1), input_width
            )

    def next_focusable_window(self, start, reverse=False):
        # Keep the tab focus in the child branch. (The child view will call
        # this, tell the child there is nothing to tab to up here).
        return None

    def normalize(self):
        self.present_modal(None)

    def on_pref_changed(self, category, name):
        pass

    def present_modal(self, change_to, top=0, left=0):
        if self.modal_ui is not None:
            # self.modal_ui.controller.on_change()
            self.modal_ui.hide()
        app.log.info("\n", change_to)
        self.modal_ui = change_to
        if self.modal_ui is not None:
            self.modal_ui.move_size_to_fit(top, left)
            self.modal_ui.bring_to_front()

    def quit_now(self):
        self.program.quit_now()

    def render(self):
        if self.show_log_window:
            self.log_window.render()
        app.window.ActiveWindow.render(self)
        window = self.focused_window
        self.debug_draw(window)
        pen_row = window.text_buffer.pen_row
        pen_col = window.text_buffer.pen_col
        if (
            window.show_cursor
            and pen_row >= window.scroll_row
            and pen_row < window.scroll_row + window.rows
        ):
            self.program.background_frame.set_cursor(
                (
                    window.top + pen_row - window.scroll_row,
                    window.left + pen_col - window.scroll_col,
                )
            )
        else:
            self.program.background_frame.set_cursor(None)

    def reshape(self, top, left, rows, cols):
        app.window.ActiveWindow.reshape(self, top, left, rows, cols)
        self.layout()

    def bring_to_front(self):
        pass

    def unfocus(self):
        pass
