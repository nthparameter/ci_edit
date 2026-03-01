# -*- coding: latin-1 -*-

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

TEST_FILE = "#undo_redo_test_file_with_unlikely_file_name~"

class UndoRedoTestCases(app.fake_curses_testing.FakeCursesTestCase):
    def setUp(self):
        self.longMessage = True
        if os.path.isfile(TEST_FILE):
            os.unlink(TEST_FILE)
        self.assertFalse(os.path.isfile(TEST_FILE))
        app.fake_curses_testing.FakeCursesTestCase.set_up(self)

    def test_undo_bracketed_paste(self):
        # self.set_movie_mode(True)
        self.run_with_test_file(
            TEST_FILE,
            [
                self.display_check(2, 7, ["      "]),
                curses.ascii.ESC,
                app.curses_util.BRACKETED_PASTE_BEGIN,
                "a",
                "b",
                "c",
                curses.ascii.ESC,
                app.curses_util.BRACKETED_PASTE_END,
                self.display_check(2, 7, ["abc "]),
                CTRL_Z,
                self.display_check(2, 7, ["                "]),
                CTRL_Q,
            ],
        )

    def test_basic_undo(self):
        # self.set_movie_mode(True)
        self.run_with_test_file(
            TEST_FILE,
            [
                self.display_check(2, 7, ["      "]),
                self.write_text("sand"),
                self.display_check(2, 7, ["sand "]),
                KEY_BACKSPACE1,
                "s",
                self.display_check(2, 7, ["sans "]),
                CTRL_Z,
                self.display_check(2, 7, ["san "]),
                CTRL_Z,
                self.display_check(2, 7, ["sand "]),
                CTRL_Z,
                self.display_check(2, 7, ["     "]),
                # Don't go past first change.
                CTRL_Z,
                self.display_check(2, 7, ["     "]),
                CTRL_Y,
                self.display_check(2, 7, ["sand "]),
                CTRL_Y,
                self.display_check(2, 7, ["san "]),
                CTRL_Y,
                self.display_check(2, 7, ["sans "]),
                # Don't go past last change.
                CTRL_Y,
                self.display_check(2, 7, ["sans "]),
                CTRL_Z,
                self.display_check(2, 7, ["san "]),
                CTRL_Z,
                self.display_check(2, 7, ["sand "]),
                CTRL_Z,
                self.display_check(2, 7, ["     "]),
                CTRL_Q,
            ],
        )

    def test_undo_words(self):
        # self.set_movie_mode(True)
        self.run_with_test_file(
            TEST_FILE,
            [
                self.display_check(2, 7, ["      "]),
                self.write_text("one two "),
                self.display_check(2, 7, ["one two "]),
                self.write_text("three four "),
                self.display_check(2, 7, ["one two three four", "     "]),
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                KEY_SHIFT_LEFT,
                self.write_text("five "),
                self.display_check(2, 7, ["one five"]),
                CTRL_Z,
                self.display_check(2, 7, ["one two three four        "]),
                CTRL_Z,
                self.display_check(2, 7, ["one two        "]),
                CTRL_Y,
                self.display_check(2, 7, ["one two three four        "]),
                CTRL_Y,
                self.display_check(2, 7, ["one five        "]),
                CTRL_Q,
                "n",
            ],
        )
