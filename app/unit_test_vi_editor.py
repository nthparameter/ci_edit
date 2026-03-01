# Copyright 2024 Google Inc.
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

import curses.ascii

from app.curses_util import *
import app.fake_curses_testing

TEST_FILE = "#vi_editor_test_file_with_unlikely_name~"

# The content area begins at screen row 2 (after 2 topInfo rows) and col 7
# (after the 7-column line number gutter).
CONTENT_ROW = 2
CONTENT_COL = 7


class ViEditorTestCases(app.fake_curses_testing.FakeCursesTestCase):
    def setUp(self):
        self.longMessage = True
        app.fake_curses_testing.FakeCursesTestCase.set_up(self)

    def switch_to_vi_mode(self):
        """Switch the input window's active controller to ViEdit."""
        iw = self.prg.program_window.input_window
        vi = iw.controller.controllers["ViEdit"]
        vi.set_text_buffer(iw.text_buffer)
        iw.controller.controller = vi

    def switch_to_cua_mode(self):
        """Switch the input window's active controller back to CuaEdit."""
        iw = self.prg.program_window.input_window
        iw.controller.controller = iw.controller.controllers["CuaEdit"]

    def test_insert_mode_types_text(self):
        # Pressing 'i' switches to insert mode; subsequent printable characters
        # appear in the buffer.
        self.run_with_test_file(
            TEST_FILE,
            [
                self.call(self.switch_to_vi_mode),
                self.display_check(CONTENT_ROW, CONTENT_COL, ["     "]),
                ord("i"),  # Enter insert mode.
                ord("h"),
                ord("i"),
                self.display_check(CONTENT_ROW, CONTENT_COL, ["hi   "]),
                self.cursor_check(CONTENT_ROW, CONTENT_COL + 2),
                self.call(self.switch_to_cua_mode),
                CTRL_Q,
                "n",
            ],
        )

    def test_esc_exits_insert_mode(self):
        # After pressing ESC from insert mode, navigation keys move the cursor
        # rather than inserting characters.
        self.run_with_test_file(
            TEST_FILE,
            [
                self.call(self.switch_to_vi_mode),
                ord("i"),  # Enter insert mode.
                ord("a"),
                ord("b"),
                ord("c"),
                self.display_check(CONTENT_ROW, CONTENT_COL, ["abc  "]),
                self.cursor_check(CONTENT_ROW, CONTENT_COL + 3),
                curses.ascii.ESC,  # Return to normal mode.
                curses.ERR,        # Terminate the ESC sequence (standalone ESC).
                # Press 'h' — it should move the cursor left, not insert 'h'.
                ord("h"),
                self.display_check(CONTENT_ROW, CONTENT_COL, ["abc  "]),
                self.cursor_check(CONTENT_ROW, CONTENT_COL + 2),
                self.call(self.switch_to_cua_mode),
                CTRL_Q,
                "n",
            ],
        )

    def test_normal_mode_l_moves_cursor_right(self):
        # 'l' moves the cursor one column to the right.
        self.run_with_test_file(
            TEST_FILE,
            [
                self.call(self.switch_to_vi_mode),
                ord("i"),
                ord("a"),
                ord("b"),
                ord("c"),
                curses.ascii.ESC,  # Normal mode; cursor at col CONTENT_COL+3.
                curses.ERR,        # Terminate the ESC sequence.
                ord("^"),  # Move to start of line.
                self.cursor_check(CONTENT_ROW, CONTENT_COL),
                ord("l"),
                self.cursor_check(CONTENT_ROW, CONTENT_COL + 1),
                ord("l"),
                self.cursor_check(CONTENT_ROW, CONTENT_COL + 2),
                self.call(self.switch_to_cua_mode),
                CTRL_Q,
                "n",
            ],
        )

    def test_normal_mode_h_moves_cursor_left(self):
        # 'h' moves the cursor one column to the left.
        self.run_with_test_file(
            TEST_FILE,
            [
                self.call(self.switch_to_vi_mode),
                ord("i"),
                ord("a"),
                ord("b"),
                ord("c"),
                curses.ascii.ESC,  # Normal mode; cursor at col CONTENT_COL+3.
                curses.ERR,        # Terminate the ESC sequence.
                ord("h"),
                self.cursor_check(CONTENT_ROW, CONTENT_COL + 2),
                ord("h"),
                self.cursor_check(CONTENT_ROW, CONTENT_COL + 1),
                ord("h"),
                self.cursor_check(CONTENT_ROW, CONTENT_COL),
                self.call(self.switch_to_cua_mode),
                CTRL_Q,
                "n",
            ],
        )

    def test_normal_mode_caret_goes_to_start_of_line(self):
        # '^' moves the cursor to column 0 of the current line.
        self.run_with_test_file(
            TEST_FILE,
            [
                self.call(self.switch_to_vi_mode),
                ord("i"),
                ord("a"),
                ord("b"),
                ord("c"),
                curses.ascii.ESC,  # Normal mode; cursor at col CONTENT_COL+3.
                curses.ERR,        # Terminate the ESC sequence.
                ord("^"),
                self.cursor_check(CONTENT_ROW, CONTENT_COL),
                self.call(self.switch_to_cua_mode),
                CTRL_Q,
                "n",
            ],
        )

    def test_normal_mode_dollar_goes_to_end_of_line(self):
        # '$' moves the cursor to the end of the current line.
        self.run_with_test_file(
            TEST_FILE,
            [
                self.call(self.switch_to_vi_mode),
                ord("i"),
                ord("a"),
                ord("b"),
                ord("c"),
                curses.ascii.ESC,  # Normal mode; cursor at col CONTENT_COL+3.
                curses.ERR,        # Terminate the ESC sequence.
                ord("^"),  # Go to start so '$' has a visible effect.
                self.cursor_check(CONTENT_ROW, CONTENT_COL),
                ord("$"),
                # cursor_end_of_line moves to row_width("abc") = 3 past content col.
                self.cursor_check(CONTENT_ROW, CONTENT_COL + 3),
                self.call(self.switch_to_cua_mode),
                CTRL_Q,
                "n",
            ],
        )

    def test_normal_mode_j_moves_cursor_down(self):
        # 'j' moves the cursor down one line.
        self.run_with_test_file(
            TEST_FILE,
            [
                # Set up two lines of content in CUA mode before switching.
                self.write_text("abc\nxyz\n"),
                # Cursor lands at the empty third line after paste: row 4, col 7.
                self.cursor_check(CONTENT_ROW + 2, CONTENT_COL),
                self.call(self.switch_to_vi_mode),
                ord("k"),  # Move up to "xyz" row.
                ord("k"),  # Move up to "abc" row.
                self.cursor_check(CONTENT_ROW, CONTENT_COL),
                ord("j"),  # Move down to "xyz" row.
                self.cursor_check(CONTENT_ROW + 1, CONTENT_COL),
                ord("j"),  # Move down to empty row.
                self.cursor_check(CONTENT_ROW + 2, CONTENT_COL),
                self.call(self.switch_to_cua_mode),
                CTRL_Q,
                "n",
            ],
        )

    def test_normal_mode_k_moves_cursor_up(self):
        # 'k' moves the cursor up one line.
        self.run_with_test_file(
            TEST_FILE,
            [
                self.write_text("abc\nxyz\n"),
                self.cursor_check(CONTENT_ROW + 2, CONTENT_COL),
                self.call(self.switch_to_vi_mode),
                ord("k"),  # Move up to "xyz" row.
                self.cursor_check(CONTENT_ROW + 1, CONTENT_COL),
                ord("k"),  # Move up to "abc" row.
                self.cursor_check(CONTENT_ROW, CONTENT_COL),
                self.call(self.switch_to_cua_mode),
                CTRL_Q,
                "n",
            ],
        )
