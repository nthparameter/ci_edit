# -*- coding: utf-8 -*-
# Copyright 2017 Google Inc.
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
import sys

from app.curses_util import *
import app.ci_program
import app.fake_curses_testing

TEST_FILE = "#application_test_file_with_unlikely_file_name~"

class ApplicationTestCases(app.fake_curses_testing.FakeCursesTestCase):
    def setUp(self):
        self.longMessage = True
        app.fake_curses_testing.FakeCursesTestCase.set_up(self)

    def test_backspace(self):
        self.run_with_test_file(
            TEST_FILE,
            [
                self.display_check(2, 7, ["      "]),
                self.write_text("tex"),
                self.display_check(2, 7, ["tex "]),
                KEY_BACKSPACE1,
                "t",
                self.display_check(2, 7, ["tet "]),
                CTRL_Q,
                "n",
            ],
        )

    def test_backspace_with_colon(self):
        self.run_with_test_file(
            TEST_FILE,
            [
                self.display_check(2, 0, ["     1       "]),
                ":",
                self.display_check(2, 0, ["     1 :     "]),
                KEY_BACKSPACE1,
                self.display_check(2, 0, ["     1       "]),
                CTRL_Q,
                "n",
            ],
        )

    def test_backspace_emoji(self):
        # self.set_movie_mode(True)
        self.run_with_test_file(
            TEST_FILE,
            [
                self.display_check(2, 7, ["      "]),
                self.cursor_check(2, 7),
                (226, 143, 176),
                self.display_check(2, 7, ["⏰"]),
                self.cursor_check(2, 9),
                KEY_BACKSPACE1,
                self.cursor_check(2, 7),
                self.display_check(2, 7, ["      "]),
                CTRL_Z,
                self.cursor_check(2, 9),
                self.display_check(2, 7, ["⏰      "]),
                CTRL_Q,
                "n",
            ],
        )

    def test_backspace_emoji2(self):
        self.run_with_test_file(
            TEST_FILE,
            [
                self.display_check(2, 7, ["      "]),
                self.cursor_check(2, 7),
                "a",
                self.cursor_check(2, 8),
                (226, 143, 176),
                self.display_check(2, 7, ["a⏰"]),
                self.cursor_check(2, 10),
                KEY_BACKSPACE1,
                self.cursor_check(2, 8),
                self.display_check(2, 7, ["a      "]),
                "t",
                self.display_check(2, 7, ["at     "]),
                CTRL_Z,
                self.display_check(2, 7, ["a      "]),
                CTRL_Z,
                self.display_check(2, 7, ["a⏰"]),
                self.write_text("four"),
                self.display_check(2, 7, ["a⏰four"]),
                KEY_HOME,
                # First char.
                KEY_SHIFT_RIGHT,
                self.display_check(2, 7, ["a⏰four"]),
                self.selection_check(0, 1, 0, 0, 3),
                self.display_check_style(
                    2, 7, 1, 1, self.prg.color.get("selected", 0)
                ),
                self.display_check_style(2, 8, 1, 10, self.prg.color.get("text", 0)),
                # Second char.
                KEY_SHIFT_RIGHT,
                self.display_check(2, 7, ["a⏰four"]),
                self.selection_check(0, 3, 0, 0, 3),
                self.display_check_style(
                    2, 7, 1, 3, self.prg.color.get("selected", 0)
                ),
                self.display_check_style(2, 10, 1, 7, self.prg.color.get("text", 0)),
                # Third char.
                KEY_SHIFT_RIGHT,
                self.display_check(2, 7, ["a⏰four"]),
                self.selection_check(0, 4, 0, 0, 3),
                self.display_check_style(
                    2, 7, 1, 4, self.prg.color.get("selected", 0)
                ),
                self.display_check_style(2, 11, 1, 6, self.prg.color.get("text", 0)),
                # Fourth char.
                KEY_SHIFT_RIGHT,
                self.display_check(2, 7, ["a⏰four"]),
                self.selection_check(0, 5, 0, 0, 3),
                self.display_check_style(
                    2, 7, 1, 5, self.prg.color.get("selected", 0)
                ),
                self.display_check_style(2, 12, 1, 5, self.prg.color.get("text", 0)),
                CTRL_X,
                self.display_check(2, 7, ["ur    "]),
                CTRL_Z,
                self.display_check(2, 7, ["a⏰four"]),
                KEY_RIGHT,
                KEY_END,
                self.cursor_check(2, 14),
                CTRL_J,
                self.cursor_check(3, 7),
                self.display_check(2, 7, ["a⏰four"]),
                CTRL_Q,
                "n",
            ],
        )

    def test_cursor_moves(self):
        self.run_with_test_file(
            TEST_FILE,
            [
                self.display_check(
                    0,
                    0,
                    [
                        " ci    _file_with_unlikely_file_name~ . ",
                        "                                        ",
                        "     1                                  ",
                    ],
                ),
                self.cursor_check(2, 7),
                self.write_text("test\napple\norange"),
                self.cursor_check(4, 13),
                self.selection_check(2, 6, 0, 0, 0),
                KEY_UP,
                self.cursor_check(3, 12),
                self.selection_check(1, 5, 0, 0, 0),
                KEY_UP,
                self.cursor_check(2, 11),
                self.selection_check(0, 4, 0, 0, 0),
                KEY_UP,
                self.cursor_check(2, 7),
                self.selection_check(0, 0, 0, 0, 0),
                KEY_RIGHT,
                KEY_RIGHT,
                KEY_RIGHT,
                KEY_RIGHT,
                KEY_LEFT,
                self.cursor_check(2, 10),
                self.selection_check(0, 3, 0, 0, 0),
                KEY_LEFT,
                self.cursor_check(2, 9),
                self.selection_check(0, 2, 0, 0, 0),
                KEY_DOWN,
                self.cursor_check(3, 9),
                self.selection_check(1, 2, 0, 0, 0),
                KEY_DOWN,
                self.cursor_check(4, 9),
                self.selection_check(2, 2, 0, 0, 0),
                KEY_RIGHT,
                self.cursor_check(4, 10),
                self.selection_check(2, 3, 0, 0, 0),
                KEY_DOWN,
                self.cursor_check(4, 13),
                self.selection_check(2, 6, 0, 0, 0),
                KEY_HOME,
                self.cursor_check(4, 7),
                self.selection_check(2, 0, 0, 0, 0),
                KEY_END,
                self.cursor_check(4, 13),
                self.selection_check(2, 6, 0, 0, 0),
                KEY_SHIFT_UP,
                self.cursor_check(3, 12),
                self.selection_check(1, 5, 2, 6, 3),
                KEY_SHIFT_LEFT,
                self.cursor_check(3, 11),
                self.selection_check(1, 4, 2, 6, 3),
                KEY_SHIFT_RIGHT,
                self.cursor_check(3, 12),
                self.selection_check(1, 5, 2, 6, 3),
                KEY_SHIFT_RIGHT,
                self.cursor_check(4, 7),
                self.selection_check(2, 0, 2, 6, 3),
                KEY_SHIFT_RIGHT,
                self.cursor_check(4, 8),
                self.selection_check(2, 1, 2, 6, 3),
                CTRL_Q,
                "n",
            ],
        )

    def test_cursor_select_first_line(self):
        self.run_with_test_file(
            TEST_FILE,
            [
                self.cursor_check(2, 7),
                self.write_text("test\napple\norange"),
                self.cursor_check(4, 13),
                self.selection_check(2, 6, 0, 0, 0),
                KEY_SHIFT_UP,
                self.cursor_check(3, 12),
                self.selection_check(1, 5, 2, 6, 3),
                KEY_SHIFT_UP,
                self.cursor_check(2, 11),
                self.selection_check(0, 4, 2, 6, 3),
                # Regression test: shift down past the end of the document
                # should select to end of document (i.e. end of line).
                KEY_SHIFT_UP,
                self.cursor_check(2, 7),
                self.selection_check(0, 0, 2, 6, 3),
                # Same for non-selection.
                KEY_DOWN,
                KEY_END,
                self.cursor_check(3, 12),
                self.selection_check(1, 5, 0, 0, 0),
                KEY_UP,
                self.cursor_check(2, 11),
                self.selection_check(0, 4, 0, 0, 0),
                KEY_UP,
                self.cursor_check(2, 7),
                self.selection_check(0, 0, 0, 0, 0),
                # The goal_col should track the desired goal column.
                KEY_DOWN,
                self.cursor_check(3, 12),
                self.selection_check(1, 5, 0, 0, 0),
                CTRL_Q,
                "n",
            ],
        )

    def test_cursor_select_last_line(self):
        self.run_with_test_file(
            TEST_FILE,
            [
                self.cursor_check(2, 7),
                self.write_text("test\napple\norange"),
                self.cursor_check(4, 13),
                self.selection_check(2, 6, 0, 0, 0),
                CTRL_G,
                "t",
                self.cursor_check(2, 7),
                self.selection_check(0, 0, 0, 0, 0),
                KEY_SHIFT_DOWN,
                self.cursor_check(3, 7),
                self.selection_check(1, 0, 0, 0, 3),
                KEY_SHIFT_DOWN,
                self.cursor_check(4, 7),
                self.selection_check(2, 0, 0, 0, 3),
                # Regression test: shift down past the end of the document
                # should select to end of document (i.e. end of line).
                KEY_SHIFT_DOWN,
                self.cursor_check(4, 13),
                self.selection_check(2, 6, 0, 0, 3),
                # Same for non-selection.
                KEY_UP,
                KEY_HOME,
                self.cursor_check(3, 7),
                self.selection_check(1, 0, 2, 6, 0),
                KEY_DOWN,
                self.cursor_check(4, 7),
                self.selection_check(2, 0, 2, 6, 0),
                KEY_DOWN,
                self.cursor_check(4, 13),
                self.selection_check(2, 6, 2, 6, 0),
                # The goal_col should track the desired goal column.
                KEY_UP,
                self.cursor_check(3, 7),
                self.selection_check(1, 0, 2, 6, 0),
                CTRL_Q,
                "n",
            ],
        )

    def test_ctrl_cursor_moves(self):
        self.run_with_test_file(
            TEST_FILE,
            [
                self.display_check(
                    0,
                    0,
                    [
                        " ci    _file_with_unlikely_file_name~ . ",
                        "                                        ",
                        "     1                                  ",
                    ],
                ),
                self.cursor_check(2, 7),
                self.write_text("test\napple bananaCarrot DogElephantFrog\norange"),
                self.display_check(
                    0,
                    0,
                    [
                        " ci    _file_with_unlikely_file_name~ * ",
                        "                                        ",
                        "     1 test                             ",
                        "     2 apple bananaCarrot DogElephantFr ",
                        "     3 orange                           ",
                        "                                        ",
                    ],
                ),
                self.cursor_check(4, 13),
                self.selection_check(2, 6, 0, 0, 0),
                KEY_CTRL_LEFT,
                self.cursor_check(4, 7),
                self.selection_check(2, 0, 0, 0, 0),
                KEY_CTRL_SHIFT_RIGHT,
                self.cursor_check(4, 13),
                self.selection_check(2, 6, 2, 0, 3),
                KEY_CTRL_SHIFT_LEFT,
                self.cursor_check(4, 7),
                self.selection_check(2, 0, 2, 0, 3),
                KEY_CTRL_SHIFT_LEFT,
                self.cursor_check(3, 38),
                self.selection_check(1, 34, 2, 0, 3),
                KEY_CTRL_SHIFT_LEFT,
                self.cursor_check(3, 23),
                self.selection_check(1, 19, 2, 0, 3),
                KEY_CTRL_SHIFT_LEFT,
                self.cursor_check(3, 22),
                self.selection_check(1, 18, 2, 0, 3),
                KEY_CTRL_RIGHT,
                self.cursor_check(3, 23),
                self.selection_check(1, 19, 1, 18, 0),
                CTRL_Q,
                "n",
            ],
        )

    def test_select_line(self):
        # self.set_movie_mode(True)
        self.run_with_test_file(
            TEST_FILE,
            [
                self.display_check(
                    0,
                    0,
                    [
                        " ci    _file_with_unlikely_file_name~ . ",
                        "                                        ",
                        "     1                                  ",
                    ],
                ),
                self.cursor_check(2, 7),
                self.write_text("test\napple\norange\none\ntwenty five"),
                # self.print_parser_state(),
                self.cursor_check(6, 18),
                self.display_check(
                    -2,
                    0,
                    [
                        "             ",
                    ],
                ),
                self.selection_check(4, 11, 0, 0, 0),
                CTRL_L,
                self.selection_check(4, 11, 4, 0, 4),
                self.display_check(
                    -2,
                    0,
                    [
                        "11 characters (1 lines) selected",
                    ],
                ),
                self.selection_check(4, 11, 4, 0, 4),
                self.display_check_style(
                    0, 0, 1, len(" ci "), self.prg.color.get("logo", 0)
                ),
                KEY_UP,
                self.display_check(
                    -2,
                    0,
                    [
                        "                       ",
                    ],
                ),
                self.selection_check(3, 3, 4, 11, 0),
                CTRL_L,
                self.selection_check(4, 0, 3, 0, 4),
                self.display_check(
                    -2,
                    0,
                    [
                        "4 characters (2 lines) selected",
                    ],
                ),
                self.selection_check(4, 0, 3, 0, 4),
                CTRL_L,
                self.selection_check(4, 11, 3, 0, 4),
                self.display_check(
                    -2,
                    0,
                    [
                        "15 characters (2 lines) selected",
                    ],
                ),
                self.mouse_event(
                    0, 2, 10, curses.BUTTON1_PRESSED | curses.BUTTON_SHIFT
                ),
                self.selection_check(0, 3, 4, 11, 3),
                self.display_check(
                    -2,
                    0,
                    [
                        "30 characters (5 lines) selected",
                    ],
                ),
                KEY_UP,
                KEY_UP,
                KEY_UP,
                self.cursor_check(2, 7),
                self.display_check(
                    -2,
                    0,
                    [
                        "Top of file ",
                    ],
                ),
                KEY_DOWN,
                self.cursor_check(3, 10),
                CTRL_L,
                self.selection_check(2, 0, 1, 0, 4),
                CTRL_L,
                self.selection_check(3, 0, 1, 0, 4),
                CTRL_L,
                self.selection_check(4, 0, 1, 0, 4),
                self.cursor_check(6, 7),
                self.display_check(
                    -2,
                    0,
                    [
                        "17 characters (4 lines) selected",
                    ],
                ),
                # Test cut then undo (regression test).
                self.display_check(
                    2,
                    7,
                    [
                        "test",
                        "apple",
                        "orange",
                        "one",
                        "twenty five",
                    ],
                ),
                CTRL_X,
                self.selection_check(1, 0, 1, 0, 0),
                self.display_check(
                    -2,
                    0,
                    [
                        "copied 4 lines  ",
                    ],
                ),
                self.display_check(
                    2,
                    7,
                    [
                        "test",
                        "twenty five",
                    ],
                ),
                CTRL_Z,
                self.selection_check(1, 0, 4, 0, 4),
                self.display_check(
                    -2,
                    0,
                    [
                        "17 characters (4 lines) selected",
                    ],
                ),
                # Test backspace.
                CTRL_A,
                self.selection_check(4, 11, 0, 0, 1),
                self.display_check(
                    -2,
                    0,
                    [
                        "33 characters (5 lines) selected",
                    ],
                ),
                KEY_BACKSPACE1,
                self.display_check(
                    -2,
                    0,
                    [
                        "                       ",
                    ],
                ),
                # Test carriage return.
                CTRL_Z,
                CTRL_A,
                self.display_check(
                    -2,
                    0,
                    [
                        "33 characters (5 lines) selected",
                    ],
                ),
                CTRL_J,
                self.display_check(
                    -2,
                    0,
                    [
                        "                       ",
                    ],
                ),
                # Test insert.
                CTRL_Z,
                CTRL_A,
                self.display_check(
                    -2,
                    0,
                    [
                        "33 characters (5 lines) selected",
                    ],
                ),
                "a",
                self.display_check(
                    -2,
                    0,
                    [
                        "                       ",
                    ],
                ),
                CTRL_Q,
                "n",
            ],
        )

    def test_select_line_via_line_numbers(self):
        self.run_with_test_file(
            TEST_FILE,
            [
                self.display_check(
                    0,
                    0,
                    [
                        " ci    _file_with_unlikely_file_name~ . ",
                        "                                        ",
                        "     1                                  ",
                    ],
                ),
                self.cursor_check(2, 7),
                "a",
                "b",
                "c",
                CTRL_J,
                "d",
                "e",
                CTRL_J,
                "f",
                "g",
                "h",
                "i",
                self.cursor_check(4, 11),
                self.mouse_event(0, 3, 2, curses.BUTTON1_PRESSED),
                CTRL_L,
                CTRL_Q,
                "n",
            ],
        )
