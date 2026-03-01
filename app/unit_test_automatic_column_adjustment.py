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

import os
import sys

from app.curses_util import *
import app.fake_curses_testing

TEST_FILE = "#automatic_column_adjustment_test_file_with_unlikely_file_name~"

class AutomaticColumnAdjustmentCases(app.fake_curses_testing.FakeCursesTestCase):
    def setUp(self):
        app.fake_curses_testing.FakeCursesTestCase.set_up(self)

    def tearDown(self):
        app.fake_curses_testing.FakeCursesTestCase.tear_down(self)

    def test_column_adjustment_on_moving_by_one_line(self):
        # self.set_movie_mode(True)
        self.run_with_fake_inputs(
            [
                self.display_check(
                    0,
                    0,
                    [
                        " ci     .                               ",
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
                        "New buffer         |    1, 1 |   0%,  0%",
                        "                                        ",
                    ],
                ),
                self.write_text("short line"),
                CTRL_J,
                self.write_text("super long line that should go past the screen"),
                CTRL_J,
                self.write_text("line that slightly goes off screen"),
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 rt line                          ",
                        "     2 er long line that should go past ",
                        "     3 e that slightly goes off screen  ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        3,35 |  66%,100%",
                        "                                        ",
                    ],
                ),
                KEY_UP,
                KEY_END,  # Place cursor at the end of the second line.
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1                                  ",
                        "     2  that should go past the screen  ",
                        "     3 tly goes off screen              ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        2,47 |  33%,100%",
                        "                                        ",
                    ],
                ),
                # scroll_col should be set to 0 since line 1 fits on screen.
                KEY_UP,
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        1,11 |   0%,100%",
                        "                                        ",
                    ],
                ),
                # cursor should snap back to the end of the second line.
                KEY_DOWN,
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1                                  ",
                        "     2  that should go past the screen  ",
                        "     3 tly goes off screen              ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        2,47 |  33%,100%",
                        "                                        ",
                    ],
                ),
                # scroll_col should not change since line 1 doesn't fit on
                # screen.
                KEY_DOWN,
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1                                  ",
                        "     2  that should go past the screen  ",
                        "     3 tly goes off screen              ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        3,35 |  66%,100%",
                        "                                        ",
                    ],
                ),
                KEY_UP,  # cursor moves back to original position.
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1                                  ",
                        "     2  that should go past the screen  ",
                        "     3 tly goes off screen              ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        2,47 |  33%,100%",
                        "                                        ",
                    ],
                ),
                # Make line 3 fit on screen. This includes making room for the
                # cursor.
                KEY_DOWN,
                KEY_BACKSPACE1,
                KEY_BACKSPACE1,
                KEY_BACKSPACE1,
                KEY_UP,
                # Since line 3 now fits on screen, this should set scroll_col to
                # 0.
                KEY_DOWN,
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scr  ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        3,32 |  66%,100%",
                        "                                        ",
                    ],
                ),
                CTRL_Q,
                "n",
            ]
        )

    def test_column_adjustment_on_moving_multiple_lines(self):
        """
        A test to check that the cursor column is stored properly and that
        after using a series of up/down arrow keys, when we end up back at the
        same line, the cursor should also be at the same position as when
        it first arrived on that line.
        """
        # self.set_movie_mode(True)
        self.run_with_fake_inputs(
            [
                self.display_check(
                    0,
                    0,
                    [
                        " ci     .                               ",
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
                        "New buffer         |    1, 1 |   0%,  0%",
                        "                                        ",
                    ],
                ),
                self.write_text("short line"),
                CTRL_J,
                self.write_text("super long line that should go past the screen"),
                CTRL_J,
                self.write_text("line that slightly goes off screen"),
                CTRL_J,
                self.write_text("short line"),
                CTRL_J,
                self.write_text("medium-short line"),
                CTRL_J,
                self.write_text("medium-long line that can fit"),
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "     4 short line                       ",
                        "     5 medium-short line                ",
                        "     6 medium-long line that can fit    ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        6,30 |  83%,100%",
                        "                                        ",
                    ],
                ),
                KEY_UP,  # Goes to end of 5th line.
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "     4 short line                       ",
                        "     5 medium-short line                ",
                        "     6 medium-long line that can fit    ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        5,18 |  66%,100%",
                        "                                        ",
                    ],
                ),
                KEY_UP,  # Goes to end of 4th line.
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "     4 short line                       ",
                        "     5 medium-short line                ",
                        "     6 medium-long line that can fit    ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        4,11 |  50%,100%",
                        "                                        ",
                    ],
                ),
                # Should go to column 30 of line 3 since we started at column
                # 30.
                KEY_UP,
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "     4 short line                       ",
                        "     5 medium-short line                ",
                        "     6 medium-long line that can fit    ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        3,30 |  33%, 85%",
                        "                                        ",
                    ],
                ),
                KEY_UP,  # Goes to column 30 of line 2.
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "     4 short line                       ",
                        "     5 medium-short line                ",
                        "     6 medium-long line that can fit    ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        2,30 |  16%, 63%",
                        "                                        ",
                    ],
                ),
                KEY_UP,  # Goes to end of line 1.
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "     4 short line                       ",
                        "     5 medium-short line                ",
                        "     6 medium-long line that can fit    ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        1,11 |   0%,100%",
                        "                                        ",
                    ],
                ),
                # All subsequent KEY_DOWNs should mirror the previous displays.
                KEY_DOWN,
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "     4 short line                       ",
                        "     5 medium-short line                ",
                        "     6 medium-long line that can fit    ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        2,30 |  16%, 63%",
                        "                                        ",
                    ],
                ),
                KEY_DOWN,
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "     4 short line                       ",
                        "     5 medium-short line                ",
                        "     6 medium-long line that can fit    ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        3,30 |  33%, 85%",
                        "                                        ",
                    ],
                ),
                KEY_DOWN,
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "     4 short line                       ",
                        "     5 medium-short line                ",
                        "     6 medium-long line that can fit    ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        4,11 |  50%,100%",
                        "                                        ",
                    ],
                ),
                KEY_DOWN,
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "     4 short line                       ",
                        "     5 medium-short line                ",
                        "     6 medium-long line that can fit    ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        5,18 |  66%,100%",
                        "                                        ",
                    ],
                ),
                KEY_DOWN,
                self.display_check(
                    0,
                    0,
                    [
                        " ci     *                               ",
                        "                                        ",
                        "     1 short line                       ",
                        "     2 super long line that should go p ",
                        "     3 line that slightly goes off scre ",
                        "     4 short line                       ",
                        "     5 medium-short line                ",
                        "     6 medium-long line that can fit    ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                                        ",
                        "                        6,30 |  83%,100%",
                        "                                        ",
                    ],
                ),
                CTRL_Q,
                "n",
            ]
        )
