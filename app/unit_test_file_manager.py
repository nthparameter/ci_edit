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

class FileManagerTestCases(app.fake_curses_testing.FakeCursesTestCase):
    def setUp(self):
        self.longMessage = True
        app.fake_curses_testing.FakeCursesTestCase.set_up(self)

    def test_save_as(self):
        # self.set_movie_mode(True)
        self.run_with_fake_inputs(
            [
                self.display_check(0, 0, [" ci     "]),
                self.display_check(2, 7, ["     "]),
                CTRL_S,
                self.display_check(0, 0, [" ci    Save File As"]),
                CTRL_Q,
                CTRL_Q,
            ]
        )  # TODO(dschuyler): fix need for extra CTRL_Q.

    def test_save_as_to_quit(self):
        # self.set_movie_mode(True)
        self.run_with_fake_inputs(
            [
                self.display_check(0, 0, [" ci     "]),
                self.display_check(2, 7, ["     "]),
                ord("a"),
                self.display_check(2, 7, ["a    "]),
                CTRL_S,
                self.display_check(0, 0, [" ci    Save File As"]),
                CTRL_Q,
                self.display_check(0, 0, [" ci     "]),
                self.display_check(-2, 0, ["      "]),
                CTRL_Q,
                ord("n"),
            ]
        )

    def test_dir_and_path_with_cr(self):
        # self.set_movie_mode(True)
        self.run_with_fake_inputs(
            [
                self.display_check(0, 0, [" ci     "]),
                self.display_check(2, 7, ["     "]),
                CTRL_O,
                self.display_check(0, 0, [" ci    Open File  "]),
                CTRL_A,
                self.write_text(self.path_to_sample("")),
                self.display_check(3, 0, ["./     ", "../     "]),
                self.display_check(5, 0, ["._ A name with cr\\r/"]),
                self.mouse_event(0, 5, 0, curses.BUTTON1_PRESSED),
                self.display_check(5, 0, ["example"]),
                self.display_find_check("/._ A name with ", "cr\\r/"),
                KEY_ESCAPE,
                curses.ERR,
                self.display_check(0, 0, [" ci     "]),
                self.display_check(2, 7, ["     "]),
                CTRL_O,
                self.display_check(0, 0, [" ci    Open File  "]),
                CTRL_A,
                self.write_text(self.path_to_sample("._ A name")),
                CTRL_I,
                self.display_check(5, 0, ["example"]),
                self.display_find_check("/._ A name with ", "cr\\r/"),
                CTRL_Q,
                CTRL_Q,
            ]
        )

    def test_mouse_scroll(self):
        # self.set_movie_mode(True)
        dirList = [
            "./     ",
            "../     ",
            "._ A name with cr\\r/",
        ]
        self.run_with_fake_inputs(
            [
                self.display_check(0, 0, [" ci     "]),
                self.display_check(2, 7, ["     "]),
                CTRL_O,
                self.display_check(0, 0, [" ci    Open File  "]),
                CTRL_A,
                self.write_text(self.path_to_sample("")),
                self.display_check(3, 0, dirList[0:3]),
                self.mouse_event(0, 5, 0, curses.REPORT_MOUSE_POSITION),
                self.display_check(3, 0, dirList[0:3]),
                self.mouse_event(1, 5, 0, curses.REPORT_MOUSE_POSITION),
                self.display_check(3, 0, dirList[1:3]),
                self.mouse_event(2, 5, 0, curses.REPORT_MOUSE_POSITION),
                self.display_check(3, 0, dirList[2:3]),
                self.mouse_event(0, 5, 0, curses.BUTTON4_PRESSED),
                self.display_check(3, 0, dirList[1:3]),
                self.mouse_event(1, 5, 0, curses.BUTTON4_PRESSED),
                self.display_check(3, 0, dirList[0:3]),
                self.mouse_event(2, 5, 0, curses.BUTTON4_PRESSED),
                self.display_check(3, 0, dirList[0:3]),
                CTRL_Q,
                CTRL_Q,
            ]
        )

    def test_open(self):
        # self.set_movie_mode(True)
        self.run_with_fake_inputs(
            [
                self.display_check(0, 0, [" ci     "]),
                self.display_check(2, 7, ["     "]),
                CTRL_O,
                self.display_check(0, 0, [" ci    Open File  "]),
                CTRL_Q,
                CTRL_Q,
            ]
        )  # TODO(dschuyler): fix need for extra CTRL_Q.

    def test_open_binary_file(self):
        # self.set_movie_mode(True)
        self.run_with_fake_inputs(
            [
                self.display_check(0, 0, [" ci     "]),
                self.display_check(2, 7, ["     "]),
                CTRL_O,
                self.display_check(0, 0, [" ci    Open File  "]),
                CTRL_A,
                self.write_text(self.path_to_sample("binary_test_file")),
                CTRL_J,
                self.display_check(2, 7, ["006401006c1a005a0800640000640100"]),
                CTRL_Q,
            ]
        )

    def test_open_valid_unicode_file(self):
        # self.set_movie_mode(True)
        self.run_with_fake_inputs(
            [
                self.display_check(0, 0, [" ci     "]),
                self.display_check(2, 7, ["     "]),
                CTRL_O,
                self.display_check(0, 0, [" ci    Open File  "]),
                CTRL_A,
                self.write_text(self.path_to_sample("valid_unicode")),
                CTRL_J,
                self.display_check(4, 7, ["Здравствуйте"]),
                CTRL_Q,
            ]
        )

    def test_empty_path_input(self):
        """Avoid crash when pressing return when the path input is empty."""
        # self.set_movie_mode(True)
        self.run_with_fake_inputs(
            [
                self.display_check(0, 0, [" ci     "]),
                self.display_check(2, 7, ["     "]),
                CTRL_O,
                self.display_check(0, 0, [" ci    Open File  "]),
                CTRL_A,
                KEY_BACKSPACE1,
                self.display_check(2, 7, ["     "]),
                CTRL_J,
                self.display_check(0, 0, [" ci    Open File  "]),
                KEY_ESCAPE,
                curses.ERR,
                self.display_check(0, 0, [" ci     "]),
                CTRL_Q,
            ]
        )

    def test_show_hide_columns(self):
        # self.set_movie_mode(True)
        self.run_with_fake_inputs(
            [
                self.pref_check("editor", "filesShowSizes", True),
                self.display_check(0, 0, [" ci     "]),
                CTRL_O,
                self.display_check(0, 0, [" ci    Open"]),
                self.find_text_and_click(1000, "[x]sizes", curses.BUTTON1_PRESSED),
                CTRL_Q,
            ]
        )

    def test_click_scroll(self):
        # self.set_movie_mode(True)
        self.run_with_fake_inputs(
            [
                self.display_check(0, 0, [" ci     "]),
                CTRL_O,
                self.display_check(0, 0, [" ci    Open"]),
                KEY_PAGE_DOWN,
                self.display_find_check("AUTHORS", ""),
                CTRL_Q,
                # TODO(dschuyler): Quitting from the file manager uses two frame
                # updates. When that is fixed, this second CTRL_Q should be removed.
                CTRL_Q,
            ]
        )
