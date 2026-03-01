# Copyright 2016 Google Inc.
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

import unittest

from app.curses_util import *
import app.fake_curses_testing

class DrawTestCases(app.fake_curses_testing.FakeCursesTestCase):
    def setUp(self):
        app.fake_curses_testing.FakeCursesTestCase.set_up(self)

    def test_draw_nothing(self):
        self.run_with_fake_inputs(
            [
                self.display_check(2, 7, ["      "]),
                self.write_text("tex"),
                self.display_check(2, 7, ["tex "]),
                KEY_BACKSPACE1,
                "t",
                self.display_check(2, 7, ["tet "]),
                CTRL_Q,
                "n",
            ]
        )

    def test_draw_tabs(self):
        test = """\t<tab
\t <tab+space
 \t<space+tab
\ta<
a\t<
some text.>\t<
\t\t<2tabs
line\twith\ttabs
ends with tab>\t
\t
"""
        self.run_with_fake_inputs(
            [
                self.display_check(2, 7, ["                           "]),
                self.write_text(test),
                self.display_check(2, 7, ["        <tab               "]),
                self.display_check(3, 7, ["         <tab+space        "]),
                self.display_check(4, 7, ["        <space+tab         "]),
                self.display_check(5, 7, ["        a<                 "]),
                self.display_check(6, 7, ["a       <                  "]),
                self.display_check(7, 7, ["some text.>     <          "]),
                self.display_check(8, 7, ["                <2tabs     "]),
                self.display_check(9, 7, ["line    with    tabs       "]),
                self.display_check(10, 7, ["ends with tab>             "]),
                self.display_check(11, 7, ["                           "]),
                CTRL_Q,
                "n",
            ]
        )

    def test_draw_text(self):
        self.run_with_fake_inputs(
            [
                self.display_check(2, 7, ["      "]),
                self.write_text("text"),
                self.display_check(2, 7, ["text "]),
                CTRL_Q,
                "n",
            ]
        )

    def test_draw_long_line(self):
        # self.set_movie_mode(True)
        lineLimitIndicator = self.prg.prefs.editor["lineLimitIndicator"]
        self.prg.prefs.editor["lineLimitIndicator"] = 10
        self.run_with_fake_inputs(
            [
                self.display_check(2, 7, ["      "]),
                self.write_text("A line with numbers 1234567890"),
                self.display_check(2, 7, ["A line with numbers 1234567890"]),
                self.write_text(". Writing"),
                self.display_check(2, 7, ["ith numbers 1234567890. Writing"]),
                self.write_text(" some more."),
                self.display_check(2, 7, [" 1234567890. Writing some more."]),
                self.write_text("\n"),
                self.display_check(2, 7, ["A line with numbers 1234567890."]),
                CTRL_Q,
                "n",
            ]
        )
        self.prg.prefs.editor["lineLimitIndicator"] = lineLimitIndicator

    def test_draw_line_endings(self):
        # self.set_movie_mode(True)
        assert self.prg.color.get("text", 0) != self.prg.color.get("selected", 0)
        self.run_with_fake_inputs(
            [
                self.display_check(2, 7, ["      "]),
                self.write_text("text\none\ntwo\nthree\n"),
                self.display_check(2, 7, ["text  ", "one  ", "two  ", "three  "]),
                self.display_check_style(2, 7, 4, 10, self.prg.color.get("text", 0)),
                self.selection_check(4, 0, 0, 0, 0),
                KEY_UP,
                KEY_UP,
                KEY_UP,
                KEY_UP,
                KEY_RIGHT,
                KEY_SHIFT_RIGHT,
                self.selection_check(0, 2, 0, 1, 3),
                self.display_check_style(2, 7, 1, 1, self.prg.color.get("text", 0)),
                self.display_check_style(
                    2, 8, 1, 1, self.prg.color.get("selected", 0)
                ),
                self.display_check_style(2, 9, 1, 3, self.prg.color.get("text", 0)),
                KEY_SHIFT_RIGHT,
                KEY_SHIFT_RIGHT,
                KEY_SHIFT_RIGHT,
                KEY_SHIFT_RIGHT,
                self.display_check_style(2, 7, 1, 1, self.prg.color.get("text", 0)),
                self.display_check_style(
                    2, 8, 1, 4, self.prg.color.get("selected", 0)
                ),
                self.display_check_style(
                    3, 7, 1, 1, self.prg.color.get("selected", 0)
                ),
                KEY_SHIFT_RIGHT,
                KEY_SHIFT_RIGHT,
                KEY_SHIFT_RIGHT,
                KEY_SHIFT_RIGHT,
                self.display_check_style(2, 7, 1, 1, self.prg.color.get("text", 0)),
                self.display_check_style(
                    2, 8, 1, 4, self.prg.color.get("selected", 0)
                ),
                self.display_check_style(
                    3, 7, 1, 4, self.prg.color.get("selected", 0)
                ),
                CTRL_Q,
                "n",
            ]
        )
