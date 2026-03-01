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

try:
    unicode
except NameError:
    unicode = str
    unichr = chr

import curses
import inspect
import os
import sys
import tempfile
import unittest

import app.ci_program
import app.curses_util

# from app.curses_util import *

def debug_print_stack(*args):
    stack = inspect.stack()[1:]
    stack.reverse()
    lines = []
    for i, frame in enumerate(stack):
        lines.append(
            "stack %2d %14s %4s %s"
            % (i, os.path.split(frame[1])[1], frame[2], frame[3])
        )
    print("\n".join(lines))

class FakeCursesTestCase(unittest.TestCase):
    def set_up(self):
        self.curses_screen = curses.StandardScreen()
        self.prg = app.ci_program.CiProgram()
        self.prg.set_up_curses(self.curses_screen)
        # For testing, use the internal clipboard. Using the system clipboard
        # can create races between tests running in parallel.
        self.prg.clipboard.set_os_handlers(None, None)

    def find_text_and_click(self, time_stamp, screen_text, b_state):
        caller = inspect.stack()[1]
        caller_text = f"\n  {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def create_event(display, cmd_index):
            row, col = self.find_text(screen_text)
            if row < 0:
                output = "%s at index %d, did not find %r" % (
                    caller_text,
                    cmd_index,
                    screen_text,
                )
                if self.curses_screen.movie:
                    print(output)
                else:
                    self.fail(output)
            # Note that the mouse info is x,y (col, row).
            info = (time_stamp, col, row, 0, b_state)
            curses.add_mouse_event(info)
            return curses.KEY_MOUSE

        return create_event

    def mouse_event(self, time_stamp, mouse_row, mouse_col, b_state):
        """
        b_state may be a logical or of:
          curses.BUTTON1_PRESSED;
          curses.BUTTON1_RELEASED;
          ...
          curses.BUTTON_SHIFT
          curses.BUTTON_CTRL
          curses.BUTTON_ALT
        """
        assert isinstance(time_stamp, int)
        assert isinstance(mouse_row, int)
        assert isinstance(mouse_col, int)
        assert isinstance(b_state, int)
        # Note that the mouse info is x,y (col, row).
        info = (time_stamp, mouse_col, mouse_row, 0, b_state)

        def create_event(display, cmd_index):
            curses.add_mouse_event(info)
            return curses.KEY_MOUSE

        return create_event

    def add_mouse_info(self, time_stamp, mouse_row, mouse_col, b_state):
        """
        b_state may be a logical or of:
          curses.BUTTON1_PRESSED;
          curses.BUTTON1_RELEASED;
          ...
          curses.BUTTON_SHIFT
          curses.BUTTON_CTRL
          curses.BUTTON_ALT
        """
        assert isinstance(time_stamp, int)
        assert isinstance(mouse_row, int)
        assert isinstance(mouse_col, int)
        assert isinstance(b_state, int)
        # Note that the mouse info is x,y (col, row).
        info = (time_stamp, mouse_col, mouse_row, 0, b_state)

        def create_event(display, cmd_index):
            curses.add_mouse_event(info)
            return None

        return create_event

    def call(self, *args):
        """Call arbitrary function as a 'fake input'."""
        caller = inspect.stack()[1]
        caller_text = f"\n  {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def caller(display, cmd_index):
            try:
                args[0](*args[1:])
            except Exception as e:
                output = caller_text + " at index " + str(cmd_index)
                print(output)
                self.fail(e)
            return None

        return caller

    def display_check(self, *args):
        assert isinstance(args[0], int)
        assert isinstance(args[1], int)
        assert isinstance(args[2], list)
        caller = inspect.stack()[1]
        caller_text = f"\n  {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def display_checker(display, cmd_index):
            result = display.check_text(*args)
            if result is not None:
                output = caller_text + " at index " + str(cmd_index) + result
                if self.curses_screen.movie:
                    print(output)
                else:
                    self.fail(output)
            return None

        return display_checker

    def display_find_check(self, *args):
        """
        Args:
            find_string (unicode): locate this string.
            check_string (unicode): verify this follows |find_string|.
        """
        assert len(args) == 2
        assert isinstance(args[0], unicode)
        assert isinstance(args[1], unicode)
        caller = inspect.stack()[1]
        caller_text = f"\n  {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def display_find_checker(display, cmd_index):
            find_string, check_string = args
            row, col = display.find_text(find_string)
            result = display.check_text(row, col + len(find_string), [check_string])
            if result is not None:
                output = caller_text + " at index " + str(cmd_index) + result
                if self.curses_screen.movie:
                    print(output)
                else:
                    self.fail(output)
            return None

        return display_find_checker

    def display_check_not(self, *args):
        """
        Verify that the display does not match.
        """
        assert isinstance(args[0], int)
        caller = inspect.stack()[1]
        caller_text = f"\n  {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def display_checker_not(display, cmd_index):
            result = display.check_text(*args)
            if result is None:
                output = caller_text + " at index " + str(cmd_index)
                if self.curses_screen.movie:
                    print(output)
                else:
                    self.fail(output)
            return None

        return display_checker_not

    def display_check_style(self, *args):
        """*args are (row, col, height, width, color_pair)."""
        (row, col, height, width, color_pair) = args
        assert height != 0
        assert width != 0
        assert color_pair is not None
        caller = inspect.stack()[1]
        caller_text = f"\n  {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def display_style_checker(display, cmd_index):
            result = display.check_style(*args)
            if result is not None:
                output = caller_text + " at index " + str(cmd_index) + result
                if self.curses_screen.movie:
                    print(output)
                else:
                    self.fail(output)
            return None

        return display_style_checker

    def find_text(self, screen_text):
        """Locate |screen_text| on the display, returning row, col."""
        return self.curses_screen.test_find_text(screen_text)

    def cursor_check(self, expected_row, expected_col):
        assert isinstance(expected_row, int)
        assert isinstance(expected_col, int)
        caller = inspect.stack()[1]
        caller_text = f"in {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def cursor_checker(display, cmd_index):
            if self.curses_screen.movie:
                return None
            win = self.prg.program_window.focused_window
            tb = win.text_buffer
            screen_row, screen_col = self.curses_screen.getyx()
            self.assertEqual(
                (
                    win.top + tb.pen_row - win.scroll_row,
                    win.left + tb.pen_col - win.scroll_col,
                ),
                (screen_row, screen_col),
                caller_text + "internal mismatch",
            )
            self.assertEqual(
                (expected_row, expected_col), (screen_row, screen_col), caller_text
            )
            return None

        return cursor_checker

    def path_to_sample(self, rel_path):
        path = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(path, "sample", rel_path)

    def pref_check(self, *args):
        assert isinstance(args[0], unicode)
        assert isinstance(args[1], unicode)
        assert isinstance(args[2], (int, bool))
        caller = inspect.stack()[1]
        caller_text = f"\n  {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def pref_checker(display, cmd_index):
            result = self.prg.prefs.category(args[0])[args[1]]
            if result != args[2]:
                output = "%s at index %s, expected %r, found %r" % (
                    caller_text,
                    unicode(cmd_index),
                    args[2],
                    result,
                )
                if self.curses_screen.movie:
                    print(output)
                else:
                    self.fail(output)
            return None

        return pref_checker

    def print_parser_state(self):
        caller = inspect.stack()[1]
        caller_text = f"in {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def redo_chain(display, cmd_index):
            print("Parser state", caller_text)
            tb = self.prg.program_window.focused_window.text_buffer
            tb.parser.debug_log(print, tb.parser.data)
            return None

        return redo_chain

    def print_redo_state(self):
        caller = inspect.stack()[1]
        caller_text = f"in {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def redo_state(display, cmd_index):
            print("Redo state", caller_text)
            tb = self.prg.program_window.focused_window.text_buffer
            tb.print_redo_state(print)
            return None

        return redo_state

    def resize_screen(self, rows, cols):
        assert isinstance(rows, int)
        assert isinstance(cols, int)

        def set_screen_size(display, cmd_index):
            self.curses_screen.fakeDisplay.set_screen_size(rows, cols)
            return curses.KEY_RESIZE

        return set_screen_size

    def set_clipboard(self, text):
        assert isinstance(text, str)
        caller = inspect.stack()[1]
        caller_text = f"in {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def copy_to_clipboard(display, cmd_index):
            self.assertTrue(self.prg.clipboard.copy, caller_text)
            self.prg.clipboard.copy(text)
            return None

        return copy_to_clipboard

    def set_movie_mode(self, enabled):
        self.curses_screen.movie = enabled
        self.curses_screen.fake_input.is_verbose = enabled

    def write_text(self, text):
        assert isinstance(text, unicode), type(text)
        caller = inspect.stack()[1]
        caller_text = f"in {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def copy_to_clipboard(display, cmd_index):
            self.assertTrue(self.prg.clipboard.copy, caller_text)
            self.prg.clipboard.copy(text)
            return app.curses_util.CTRL_V

        return copy_to_clipboard

    def check_not_reached(self, depth=1):
        """Check that this step doesn't occur. E.g. verify the app exited.

        Args:
          depth (int): how many stack frames up to report as the error location.
        """
        caller = inspect.stack()[depth]
        caller_text = f"\n  {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def check_end_of_inputs(display, cmd_index):
            self.fail(
                caller_text + "\n  Unexpectedly ran out of fake inputs. Consider adding"
                " CTRL_Q (and 'n' if necessary)."
            )
            return None

        return check_end_of_inputs

    def run_with_fake_inputs(self, fake_inputs, argv=None):
        assert hasattr(fake_inputs, "__getitem__") or hasattr(fake_inputs, "__iter__")
        if argv is None:
            argv = ["no_argv"]
        sys.argv = argv
        self.curses_screen.set_fake_inputs(
            fake_inputs
            + [
                self.check_not_reached(2),
            ]
        )
        self.assertTrue(self.prg)
        self.assertFalse(self.prg.exiting)
        self.prg.run()
        # curses.print_fake_display()
        if app.ci_program.user_console_message:
            message = app.ci_program.user_console_message
            app.ci_program.user_console_message = None
            self.fail(message)
        # Check that the application is closed down (don't leave it running
        # across tests).
        self.assertTrue(self.prg.exiting)
        self.assertEqual(self.curses_screen.fake_input.inputs_index, len(fake_inputs) - 1)
        # Handy for debugging.
        if 0:
            caller = inspect.stack()[1]
            caller_text = f"  {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "
            print("\n-------- finished", caller_text)

    def run_with_test_file(self, TEST_FILE, fake_inputs):
        if os.path.isfile(TEST_FILE):
            os.unlink(TEST_FILE)
        self.assertFalse(os.path.isfile(TEST_FILE))
        self.run_with_fake_inputs(fake_inputs, ["ci_test_program", TEST_FILE])

    def selection_document_check(
        self,
        expected_pen_row,
        expected_pen_col,
        expected_marker_row,
        expected_marker_col,
        expected_mode,
    ):
        caller = inspect.stack()[1]
        caller_text = f"in {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def checker(display, cmd_index):
            selection = self.prg.get_document_selection()
            self.assertEqual(
                (
                    expected_pen_row,
                    expected_pen_col,
                    expected_marker_row,
                    expected_marker_col,
                    expected_mode,
                ),
                selection,
                caller_text,
            )

        return checker

    def selection_check(
        self,
        expected_pen_row,
        expected_pen_col,
        expected_marker_row,
        expected_marker_col,
        expected_mode,
    ):
        caller = inspect.stack()[1]
        caller_text = f"in {os.path.split(caller[1])[1]}:{caller[2]}:{caller[3]}(): "

        def checker(display, cmd_index):
            selection = self.prg.get_selection()
            self.assertEqual(
                (
                    expected_pen_row,
                    expected_pen_col,
                    expected_marker_row,
                    expected_marker_col,
                    expected_mode,
                ),
                selection,
                caller_text,
            )

        return checker

    def tear_down(self):
        # Disable mouse tracking in xterm.
        sys.stdout.write("\033[?1002l")
        # Disable Bracketed Paste Mode.
        sys.stdout.write("\033[?2004l")
