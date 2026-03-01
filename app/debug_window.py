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

try:
    unicode
except NameError:
    unicode = str
    unichr = chr

import curses

import app.curses_util
import app.log
import app.window

class DebugWindow(app.window.ActiveWindow):
    def __init__(self, program, host):
        app.window.ActiveWindow.__init__(self, program, host)

    def debug_draw(self, program, win):
        """Draw real-time debug information to the screen."""
        text_buffer = win.text_buffer
        self.writeLineRow = 0
        intent = "no_intent"
        if hasattr(win, "user_intent"):
            intent = win.user_intent
        color = program.color.get("debug_window")
        self.write_line(
            "   cRow %3d    cCol %2d goal_col %2d  %s"
            % (
                win.text_buffer.pen_row,
                win.text_buffer.pen_col,
                win.text_buffer.goal_col,
                intent,
            ),
            color,
        )
        self.write_line(
            "   pRow %3d    pCol %2d chRow %4d"
            % (text_buffer.pen_row, text_buffer.pen_col, text_buffer.debug_upper_changed_row),
            color,
        )
        self.write_line(
            " mkrRow %3d  mkrCol %2d sm %d"
            % (text_buffer.marker_row, text_buffer.marker_col, text_buffer.selection_mode),
            color,
        )
        self.write_line(
            "scrlRow %3d scrlCol %2d lines %3d"
            % (win.scroll_row, win.scroll_col, text_buffer.parser.row_count()),
            color,
        )
        y, x = win.top, win.left
        max_row, max_col = win.rows, win.cols
        self.write_line(
            "y %2d x %2d max_row %d max_col %d baud %d color %d"
            % (y, x, max_row, max_col, curses.baudrate(), curses.can_change_color()),
            color,
        )
        screen_rows, screen_cols = program.curses_screen.getmaxyx()
        self.write_line(
            "scr rows %d cols %d mlt %f/%f pt %f"
            % (
                screen_rows,
                screen_cols,
                program.main_loop_time,
                program.main_loop_time_peak,
                text_buffer.parser_time,
            ),
            color,
        )
        self.write_line(
            "ch %3s %s"
            % (program.ch, app.curses_util.curses_key_name(program.ch) or "UNKNOWN"),
            color,
        )
        self.write_line(f"win {win!r}", color)
        self.write_line(f"foc {program.program_window.focused_window!r}", color)
        self.write_line(f"tb {text_buffer!r}", color)
        (id, mouse_col, mouse_row, mouse_z, b_state) = program.debug_mouse_event
        self.write_line(
            "mouse id %d, mouse_col %d, mouse_row %d, mouse_z %d"
            % (id, mouse_col, mouse_row, mouse_z),
            color,
        )
        self.write_line(
            f"b_state {app.curses_util.mouse_button_name(b_state)} {b_state}", color
        )
        self.write_line(f"start_and_end {text_buffer.start_and_end()!r}", color)

class DebugUndoWindow(app.window.ActiveWindow):
    def __init__(self, program, host):
        app.window.ActiveWindow.__init__(self, program, host)

    def debug_undo_draw(self, win):
        """Draw real-time debug information to the screen."""
        text_buffer = win.text_buffer
        self.writeLineRow = 0
        # Display some of the redo chain.
        colorPrefs = win.program.color
        redo_color_a = colorPrefs.get(100)
        self.write_line(
            "proc_temp %d temp %r"
            % (
                text_buffer.process_temp_change,
                text_buffer.temp_change,
            ),
            redo_color_a,
        )
        self.write_line(
            "redo_index %3d saved_at %3d depth %3d"
            % (
                text_buffer.redo_index,
                text_buffer.saved_at_redo_index,
                len(text_buffer.redo_chain),
            ),
            redo_color_a,
        )
        redo_color_b = colorPrefs.get(101)
        split = 8
        for i in range(text_buffer.redo_index - split, text_buffer.redo_index):
            text = i >= 0 and repr(text_buffer.redo_chain[i]) or ""
            self.write_line(unicode(text), redo_color_b)
        redo_color_c = colorPrefs.get(1)
        for i in range(text_buffer.redo_index, text_buffer.redo_index + split - 1):
            text = i < len(text_buffer.redo_chain) and text_buffer.redo_chain[i] or ""
            self.write_line(unicode(text), redo_color_c)
