# -*- coding: latin-1 -*-

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
import sys

from app.curses_util import *
import app.ci_program
import app.fake_curses_testing

kTestFile = "#application_test_file_with_unlikely_file_name~"

class UiBasicsTestCases(app.fake_curses_testing.FakeCursesTestCase):
    def setUp(self):
        self.longMessage = True
        app.fake_curses_testing.FakeCursesTestCase.set_up(self)

    def test_logo(self):
        self.run_with_test_file(
            kTestFile,
            [
                # self.assertEqual(256, self.prg.prefs.startup['numColors']),
                self.display_check(0, 0, [" ci "]),
                self.display_check_style(
                    0, 0, 1, len(" ci "), self.prg.color.get("logo", 0)
                ),
                CTRL_Q,
            ],
        )

    def test_prediction(self):
        # self.set_movie_mode(True)
        self.run_with_test_file(
            kTestFile,
            [
                self.display_check(-1, 0, ["      "]),
                # CTRL_P, self.display_check(-1, 0, ["p: "]), CTRL_J,
                self.display_check(-1, 0, ["      "]),
                # CTRL_P, self.display_check(-1, 0, ["p: "]), CTRL_J,
                CTRL_Q,
            ],
        )

    def test_resize_screen(self):
        self.run_with_test_file(
            kTestFile,
            [
                self.display_check(
                    0,
                    0,
                    [
                        " ci    _file_with_unlikely_file_name~ . ",
                        "                                        ",
                        "     1                                  ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "Creating new file  |    1, 1 |   0%,  0%",
                        "                                        ",
                    ],
                ),
                self.resize_screen(10, 36),
                self.display_check(
                    0,
                    0,
                    [
                        " ci    e_with_unlikely_file_name~ . ",
                        "                                    ",
                        "     1                              ",
                        "                                    ",
                        "                                    ",
                        "                                    ",
                        "                                    ",
                        "                                    ",
                        "                    1, 1 |   0%,  0%",
                        "                                    ",
                    ],
                ),
                CTRL_Q,
            ],
        )

    def test_save_on_close(self):
        # self.set_movie_mode(True)
        self.run_with_test_file(
            kTestFile,
            [
                self.display_check(
                    0,
                    0,
                    [
                        " ci    " + kTestFile[-30:],
                    ],
                ),
                self.cursor_check(2, 7),
                self.display_check(
                    13,
                    0,
                    [
                        "Creating new file  ",
                        "                   ",
                    ],
                ),
                "t",
                self.display_check(
                    13,
                    0,
                    [
                        "                   ",
                        "                   ",
                    ],
                ),
                CTRL_S,
                self.cursor_check(2, 8),
                self.display_check(
                    13,
                    0,
                    [
                        "File saved    ",
                        "                   ",
                    ],
                ),
                "e",
                CTRL_W,
                self.display_check(
                    13,
                    0,
                    [
                        "                   ",
                        "Save changes? (yes, no, or cancel):",
                    ],
                ),
                "y",
                self.display_check(
                    0,
                    0,
                    [
                        " ci     . ",
                    ],
                ),
                CTRL_O,
                self.write_text(kTestFile),
                CTRL_J,
                self.display_check(
                    0,
                    0,
                    [
                        " ci    " + kTestFile[-30:],
                        "            ",
                        "     1 te   ",
                    ],
                ),
                CTRL_Q,
            ],
        )

    def test_message_on_text_selection(self):
        self.run_with_test_file(
            kTestFile,
            [
                self.cursor_check(2, 7),
                "H",
                "e",
                "l",
                "l",
                "o",
                self.display_check(2, 0, ["     1 Hello                            "]),
                self.cursor_check(2, 12),
                CTRL_A,
                self.selection_document_check(0, 5, 0, 0, 1),
                self.display_check(13, 0, ["5 characters (1 lines) selected"]),
                "a",
                "b",
                self.cursor_check(2, 9),
                self.display_check(2, 0, ["     1 ab                               "]),
                self.display_check(
                    13, 0, ["                        1, 3 |   0%,100%"]
                ),
                KEY_SHIFT_LEFT,
                self.selection_document_check(0, 1, 0, 2, 3),
                self.display_check(13, 0, ["1 characters (1 lines) selected"]),
                "c",
                self.cursor_check(2, 9),
                self.display_check(2, 0, ["     1 ac                               "]),
                self.display_check(
                    13, 0, ["                        1, 3 |   0%,100%"]
                ),
                CTRL_Q,
                "n",
            ],
        )

    def test_session(self):
        self.run_with_test_file(
            kTestFile,
            [
                self.display_check(
                    0,
                    0,
                    [
                        " ci    _file_with_unlikely_file_name~ . ",
                        "                                        ",
                        "     1                                  ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "Creating new file  |    1, 1 |   0%,  0%",
                        "                                        ",
                    ],
                ),
                "H",
                "e",
                "l",
                "l",
                "o",
                self.display_check(
                    0,
                    0,
                    [
                        " ci    _file_with_unlikely_file_name~ * ",
                        "                                        ",
                        "     1 Hello                            ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        1, 6 |   0%,100%",
                        "                                        ",
                    ],
                ),
                CTRL_Z,
                self.display_check(
                    0,
                    0,
                    [
                        " ci    _file_with_unlikely_file_name~ . ",
                        "                                        ",
                        "     1                                  ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        1, 1 |   0%,  0%",
                        "                                        ",
                    ],
                ),
                CTRL_Q,
            ],
        )

    def test_text_contents(self):
        self.run_with_test_file(
            kTestFile,
            [
                self.display_check(2, 7, ["        "]),
                "t",
                "e",
                "x",
                "t",
                self.display_check(2, 7, ["text "]),
                CTRL_Q,
                "n",
            ],
        )

    def test_whole_screen(self):
        # self.set_movie_mode(True)
        self.run_with_test_file(
            kTestFile,
            [
                self.display_check(
                    0,
                    0,
                    [
                        " ci    _file_with_unlikely_file_name~ . ",
                        "                                        ",
                        "     1                                  ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "Creating new file  |    1, 1 |   0%,  0%",
                        "                                        ",
                    ],
                ),
                CTRL_Q,
            ],
        )
