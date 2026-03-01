# -*- coding: utf-8 -*-

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
import sys

from app.curses_util import *
import app.fake_curses_testing

class BraceMatchingTestCases(app.fake_curses_testing.FakeCursesTestCase):
    def setUp(self):
        self.longMessage = True
        app.fake_curses_testing.FakeCursesTestCase.set_up(self)

    def test_parenthesis(self):
        # self.set_movie_mode(True)
        sys.argv = []
        write = self.write_text
        check_style = self.display_check_style
        bracket_color = self.prg.color.get("bracket", 0)
        default_color = self.prg.color.get("default", 0)
        matching_bracket_color = self.prg.color.get("matching_bracket", 0)
        self.run_with_fake_inputs(
            [
                self.display_check(2, 7, ["     "]),
                # Regression test for open ([{ without closing.
                write("("),
                self.display_check(2, 7, ["(    "]),
                KEY_LEFT,
                CTRL_A,
                write("["),
                self.display_check(2, 7, ["[    "]),
                KEY_LEFT,
                CTRL_A,
                write("{"),
                self.display_check(2, 7, ["{    "]),
                KEY_LEFT,
                CTRL_A,
                # Test for closing )]} without opening.
                write(")"),
                self.display_check(2, 7, [")    "]),
                KEY_LEFT,
                CTRL_A,
                write("]"),
                self.display_check(2, 7, ["]    "]),
                KEY_LEFT,
                CTRL_A,
                write("}"),
                self.display_check(2, 7, ["}    "]),
                KEY_LEFT,
                CTRL_A,
                # Test adjacent matching.
                write("()"),
                self.display_check(2, 7, ["()    "]),
                check_style(2, 7, 1, 2, bracket_color),
                KEY_LEFT,
                check_style(2, 7, 1, 2, matching_bracket_color),
                CTRL_A,
                write("[]"),
                self.display_check(2, 7, ["[]    "]),
                check_style(2, 7, 1, 2, bracket_color),
                KEY_LEFT,
                check_style(2, 7, 1, 2, matching_bracket_color),
                CTRL_A,
                write("{}"),
                self.display_check(2, 7, ["{}    "]),
                check_style(2, 7, 1, 2, bracket_color),
                KEY_LEFT,
                check_style(2, 7, 1, 2, matching_bracket_color),
                CTRL_A,
                # Test same line matching.
                write("(test)"),
                self.display_check(2, 7, ["(test)    "]),
                check_style(2, 7, 1, 1, bracket_color),
                check_style(2, 8, 1, 4, default_color),
                check_style(2, 12, 1, 1, bracket_color),
                KEY_LEFT,
                check_style(2, 7, 1, 1, matching_bracket_color),
                check_style(2, 8, 1, 4, default_color),
                check_style(2, 12, 1, 1, matching_bracket_color),
                CTRL_A,
                write("[test]"),
                self.display_check(2, 7, ["[test]    "]),
                check_style(2, 7, 1, 1, bracket_color),
                check_style(2, 8, 1, 4, default_color),
                check_style(2, 12, 1, 1, bracket_color),
                KEY_LEFT,
                check_style(2, 7, 1, 1, matching_bracket_color),
                check_style(2, 8, 1, 4, default_color),
                check_style(2, 12, 1, 1, matching_bracket_color),
                CTRL_A,
                write("{test}"),
                self.display_check(2, 7, ["{test}    "]),
                check_style(2, 7, 1, 1, bracket_color),
                check_style(2, 8, 1, 4, default_color),
                check_style(2, 12, 1, 1, bracket_color),
                KEY_LEFT,
                check_style(2, 7, 1, 1, matching_bracket_color),
                check_style(2, 8, 1, 4, default_color),
                check_style(2, 12, 1, 1, matching_bracket_color),
                CTRL_A,
                CTRL_Q,
                "n",
            ]
        )

    def test_parenthesis_double_wide_chars(self):
        # self.set_movie_mode(True)
        sys.argv = []
        write = self.write_text
        check_style = self.display_check_style
        bracket_color = self.prg.color.get("bracket", 0)
        default_color = self.prg.color.get("default", 0)
        matching_bracket_color = self.prg.color.get("matching_bracket", 0)
        self.run_with_fake_inputs(
            [
                self.display_check(2, 7, ["     "]),
                # Test for open ([{ without closing.
                write("😃("),
                self.display_check(2, 7, ["😃(    "]),
                KEY_LEFT,
                CTRL_A,
                write("😃["),
                self.display_check(2, 7, ["😃[    "]),
                KEY_LEFT,
                CTRL_A,
                write("😃{"),
                self.display_check(2, 7, ["😃{    "]),
                KEY_LEFT,
                CTRL_A,
                # Test for closing )]} without opening.
                write("😃)"),
                self.display_check(2, 7, ["😃)    "]),
                KEY_LEFT,
                CTRL_A,
                write("😃]"),
                self.display_check(2, 7, ["😃]    "]),
                KEY_LEFT,
                CTRL_A,
                write("😃}"),
                self.display_check(2, 7, ["😃}    "]),
                KEY_LEFT,
                CTRL_A,
                # Test with wide character.
                write("(😃)"),
                self.display_check(2, 7, ["(😃)    "]),
                # check_style(2, 7, 1, 2, bracket_color),
                KEY_LEFT,
                # check_style(2, 7, 1, 2, matching_bracket_color),
                CTRL_A,
                write("[😃]"),
                self.display_check(2, 7, ["[😃]    "]),
                # check_style(2, 7, 1, 2, bracket_color),
                KEY_LEFT,
                # check_style(2, 7, 1, 2, matching_bracket_color),
                CTRL_A,
                write("{😃}"),
                self.display_check(2, 7, ["{😃}    "]),
                # check_style(2, 7, 1, 2, bracket_color),
                KEY_LEFT,
                # check_style(2, 7, 1, 2, matching_bracket_color),
                CTRL_A,
                # Test same line matching.
                write("(test😃😃)"),
                self.display_check(2, 7, ["(test😃😃)    "]),
                # check_style(2, 7, 1, 1, bracket_color),
                # check_style(2, 8, 1, 4, default_color),
                # check_style(2, 12, 1, 1, bracket_color),
                KEY_LEFT,
                # check_style(2, 7, 1, 1, matching_bracket_color),
                # heckStyle(2, 8, 1, 4, default_color),
                # check_style(2, 12, 1, 1, matching_bracket_color),
                CTRL_A,
                write("[😃😃test]"),
                self.display_check(2, 7, ["[😃😃test]    "]),
                # check_style(2, 7, 1, 1, bracket_color),
                # check_style(2, 8, 1, 4, default_color),
                # check_style(2, 12, 1, 1, bracket_color),
                KEY_LEFT,
                # check_style(2, 7, 1, 1, matching_bracket_color),
                # check_style(2, 8, 1, 4, default_color),
                # check_style(2, 12, 1, 1, matching_bracket_color),
                CTRL_A,
                write("😃😃{test}"),
                self.display_check(2, 7, ["😃😃{test}    "]),
                # check_style(2, 7, 1, 1, bracket_color),
                # check_style(2, 8, 1, 4, default_color),
                # check_style(2, 12, 1, 1, bracket_color),
                KEY_LEFT,
                # check_style(2, 7, 1, 1, matching_bracket_color),
                # check_style(2, 8, 1, 4, default_color),
                # check_style(2, 12, 1, 1, matching_bracket_color),
                CTRL_A,
                CTRL_Q,
                "n",
            ]
        )
