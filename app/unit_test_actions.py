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

import os
import unittest

import app.log
import app.text_buffer

class FakeCursorWindow:
    def getmaxyx(self):
        return (100, 100)

class FakeView:
    def __init__(self):
        self.cursor_window = FakeCursorWindow()
        self.top = 0
        self.left = 0
        self.rows = 10
        self.cols = 100
        self.scroll_row = 0
        self.scroll_col = 0

def check_row(test, text_buffer, row, expected):
    text_buffer.parse_document()
    if not (expected == text_buffer.parser.row_text(row)):
        test.fail(
            f"\n\nExpected these to match: row {row}: expected {repr(expected)}, parser {repr(text_buffer.parser.data)}"
        )

class ActionsTestCase(unittest.TestCase):
    def current_row_text(self):
        return self.text_buffer.parser.row_text(self.text_buffer.pen_row)

    def set_marker_pen_row_col(self, mRow, mCol, row, col):
        self.assertTrue(isinstance(mRow, int))
        self.assertTrue(isinstance(mCol, int))
        self.assertTrue(isinstance(row, int))
        self.assertTrue(isinstance(col, int))
        self.assertTrue(hasattr(self.text_buffer, "marker_row"))
        self.assertTrue(hasattr(self.text_buffer, "marker_col"))
        self.assertTrue(hasattr(self.text_buffer, "pen_row"))
        self.assertTrue(hasattr(self.text_buffer, "pen_col"))
        self.assertTrue(hasattr(self.text_buffer, "goal_col"))
        self.text_buffer.marker_row = mRow
        self.text_buffer.marker_col = mCol
        self.text_buffer.pen_row = row
        self.text_buffer.pen_col = col
        self.text_buffer.goal_col = col

    def marker_pen_row_col(self):
        return (
            self.text_buffer.marker_row,
            self.text_buffer.marker_col,
            self.text_buffer.pen_row,
            self.text_buffer.pen_col,
        )

class MouseTestCases(ActionsTestCase):
    def setUp(self):
        app.log.should_write_print_log = False
        self.prg = app.ci_program.CiProgram()
        self.text_buffer = app.text_buffer.TextBuffer(self.prg)
        self.text_buffer.set_view(FakeView())
        test = """/* first comment */
two
// second comment
apple banana carrot
#include "test.h"
void blah();
"""
        self.text_buffer.insert_lines(tuple(test.split("\n")))
        self.text_buffer.parse_document()
        # self.assertEqual(self.text_buffer.scroll_row, 0)
        # self.assertEqual(self.text_buffer.scroll_col, 0)
        self.assertEqual(self.text_buffer.parser.row_text(1), "two")

    def tearDown(self):
        self.text_buffer = None

    def test_mouse_selection(self):
        self.text_buffer.mouse_click(3, 9, False, False, False)
        self.assertEqual(self.text_buffer.pen_row, 3)
        self.assertEqual(self.text_buffer.pen_col, 9)

        self.text_buffer.mouse_click(3, 8, True, False, False)
        self.assertEqual(self.marker_pen_row_col(), (3, 9, 3, 8))

        self.text_buffer.mouse_click(4, 8, True, False, False)
        self.assertEqual(self.marker_pen_row_col(), (3, 9, 4, 8))

        self.text_buffer.mouse_click(3, 8, True, False, False)
        self.assertEqual(self.marker_pen_row_col(), (3, 9, 3, 8))

        self.text_buffer.mouse_click(4, 8, True, False, False)
        self.text_buffer.mouse_click(4, 9, True, False, False)
        self.assertEqual(self.marker_pen_row_col(), (3, 9, 4, 9))

        self.text_buffer.mouse_click(4, 10, True, False, False)
        self.assertEqual(self.marker_pen_row_col(), (3, 9, 4, 10))

        self.text_buffer.mouse_click(4, 11, True, False, False)
        self.assertEqual(self.marker_pen_row_col(), (3, 9, 4, 11))

    def test_mouse_word_selection(self):
        # self.assertEqual(self.text_buffer.scroll_col, 0)
        self.text_buffer.selection_word()
        # self.assertEqual(self.text_buffer.scroll_col, 0)
        row = 3
        col = 9
        word_begin = 6
        word_end = 12
        self.text_buffer.mouse_click(row, col, False, False, False)
        self.assertEqual(self.text_buffer.pen_row, row)
        self.assertEqual(self.text_buffer.pen_col, col)

        self.text_buffer.mouse_double_click(row, col - 1, False, False, False)
        self.assertEqual(self.text_buffer.marker_row, row)
        self.assertEqual(self.text_buffer.marker_col, word_begin)
        self.assertEqual(self.text_buffer.pen_row, row)
        self.assertEqual(self.text_buffer.pen_col, word_end)

        self.text_buffer.mouse_moved(row, word_begin, False, False, False)
        self.assertEqual(self.text_buffer.marker_row, row)
        self.assertEqual(self.text_buffer.marker_col, word_begin)
        self.assertEqual(self.text_buffer.pen_row, row)
        self.assertEqual(self.text_buffer.pen_col, word_end)

        self.text_buffer.mouse_moved(row, word_begin - 1, False, False, False)
        self.assertEqual(self.text_buffer.marker_row, row)
        self.assertEqual(self.text_buffer.pen_col, 0)
        self.assertEqual(self.text_buffer.marker_col, word_end)
        self.assertEqual(self.text_buffer.pen_row, row)
        self.assertEqual(self.text_buffer.pen_col, 0)

        self.text_buffer.mouse_moved(row, 1, False, False, False)
        self.assertEqual(self.text_buffer.marker_row, row)
        self.assertEqual(self.text_buffer.marker_col, word_end)
        self.assertEqual(self.text_buffer.pen_row, row)
        self.assertEqual(self.text_buffer.pen_col, 0)

        self.text_buffer.mouse_moved(row + 1, 0, False, False, False)
        self.assertEqual(self.text_buffer.marker_row, row)
        self.assertEqual(self.text_buffer.marker_col, word_begin)
        self.assertEqual(self.text_buffer.pen_row, row + 1)
        self.assertEqual(self.text_buffer.pen_col, 1)

        self.text_buffer.mouse_moved(row + 1, 1, False, False, False)
        self.assertEqual(self.text_buffer.marker_row, row)
        self.assertEqual(self.text_buffer.marker_col, word_begin)
        self.assertEqual(self.text_buffer.pen_row, row + 1)
        self.assertEqual(self.text_buffer.pen_col, 8)

        self.text_buffer.mouse_moved(row, 1, False, False, False)
        self.assertEqual(self.text_buffer.marker_row, row)
        self.assertEqual(self.text_buffer.marker_col, word_end)
        self.assertEqual(self.text_buffer.pen_row, row)
        self.assertEqual(self.text_buffer.pen_col, 0)

class SelectionTestCases(ActionsTestCase):
    def setUp(self):
        app.log.should_write_print_log = False
        self.prg = app.ci_program.CiProgram()
        self.text_buffer = app.text_buffer.TextBuffer(self.prg)
        self.text_buffer.set_view(FakeView())
        test = """/* first comment */
two
// second comment
apple banana carrot
#include "test.h"
void blah();
\ta\t
a\twith tab
\t\t
\twhile
{
"""
        self.text_buffer.set_file_type("text")
        self.text_buffer.insert_lines(tuple(test.split("\n")))
        self.text_buffer.parse_document()
        # self.text_buffer.parser.debug_log(print, test)
        # self.assertEqual(self.text_buffer.scroll_row, 0)
        # self.assertEqual(self.text_buffer.scroll_col, 0)
        self.assertEqual(self.text_buffer.parser.row_text(1), "two")
        self.assertEqual(self.text_buffer.parser.row_text_and_width(8), ("\t\t", 16))

    def test_cursor_col_delta(self):
        self.set_marker_pen_row_col(0, 0, 0, 2)
        self.assertEqual(self.text_buffer.cursor_col_delta(4), 0)
        self.assertEqual(self.text_buffer.cursor_col_delta(6), -2)
        self.set_marker_pen_row_col(0, 0, 0, 12)
        self.assertEqual(self.text_buffer.cursor_col_delta(4), 0)
        self.assertEqual(self.text_buffer.cursor_col_delta(6), -3)

    def test_cursor_move(self):
        self.set_marker_pen_row_col(0, 0, 2, 5)
        self.assertEqual(self.current_row_text(), "// second comment")
        self.text_buffer.cursor_move_left()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 2, 4))
        self.text_buffer.cursor_move_right()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 2, 5))

        self.set_marker_pen_row_col(0, 0, 8, 16)
        self.assertEqual(self.current_row_text(), "\t\t")
        self.text_buffer.cursor_move_left()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 8, 8))
        self.text_buffer.cursor_move_left()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 8, 0))
        self.text_buffer.cursor_move_left()
        self.assertEqual(self.current_row_text(), "a\twith tab")
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 7, 16))
        self.text_buffer.cursor_move_right()
        self.assertEqual(self.current_row_text(), "\t\t")
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 8, 0))
        self.text_buffer.cursor_move_right()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 8, 8))
        self.text_buffer.cursor_move_right()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 8, 16))
        self.text_buffer.cursor_move_right()
        self.assertEqual(self.current_row_text(), "\twhile")
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 9, 0))
        self.text_buffer.cursor_move_right()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 9, 8))
        self.text_buffer.cursor_move_right()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 9, 9))
        self.text_buffer.cursor_move_right()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 9, 10))
        self.text_buffer.cursor_move_up_or_begin()
        self.assertEqual(self.current_row_text(), "\t\t")
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 8, 8))
        self.text_buffer.cursor_move_up_or_begin()
        self.assertEqual(self.current_row_text(), "a\twith tab")
        # The column is 10 because of the prior move right which set goal_col.
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 7, 10))
        self.text_buffer.cursor_move_left()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 7, 9))
        self.text_buffer.cursor_move_left()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 7, 8))
        self.text_buffer.cursor_move_left()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 7, 1))
        self.text_buffer.cursor_move_down_or_end()
        self.assertEqual(self.current_row_text(), "\t\t")
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 8, 0))

    def test_backspace(self):
        self.set_marker_pen_row_col(0, 0, 6, 8)
        self.assertEqual(self.current_row_text(), "\ta\t")
        self.text_buffer.backspace()
        self.text_buffer.parse_document()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 6, 0))
        self.assertEqual(self.current_row_text(), "a\t")
        self.text_buffer.cursor_move_right()
        self.assertEqual(self.marker_pen_row_col(), (0, 0, 6, 1))

    def test_cursor_select_word_left(self):
        tb = self.text_buffer
        self.set_marker_pen_row_col(0, 0, 2, 5)

        self.assertEqual(self.current_row_text(), "// second comment")
        self.text_buffer.cursor_select_word_left()
        self.assertEqual(self.marker_pen_row_col(), (2, 5, 2, 3))

        self.text_buffer.cursor_select_word_left()
        self.assertEqual(self.marker_pen_row_col(), (2, 5, 2, 0))

        self.text_buffer.cursor_select_word_left()
        self.assertEqual(self.marker_pen_row_col(), (2, 5, 1, 3))

        self.text_buffer.cursor_select_word_left()
        self.assertEqual(self.marker_pen_row_col(), (2, 5, 1, 0))

        self.text_buffer.cursor_select_word_left()
        self.assertEqual(self.marker_pen_row_col(), (2, 5, 0, 19))

        self.text_buffer.cursor_select_word_left()
        self.assertEqual(self.marker_pen_row_col(), (2, 5, 0, 16))

        self.text_buffer.cursor_select_word_left()
        self.assertEqual(self.marker_pen_row_col(), (2, 5, 0, 9))

        self.text_buffer.cursor_select_word_left()
        self.assertEqual(self.marker_pen_row_col(), (2, 5, 0, 8))

        self.text_buffer.cursor_select_word_left()
        self.assertEqual(self.marker_pen_row_col(), (2, 5, 0, 3))

        self.text_buffer.cursor_select_word_left()
        self.assertEqual(self.marker_pen_row_col(), (2, 5, 0, 0))

        # Top of document. This call should have no effect (and not crash).
        self.text_buffer.cursor_select_word_left()
        self.assertEqual(self.marker_pen_row_col(), (2, 5, 0, 0))

class TextIndentTestCases(ActionsTestCase):
    def setUp(self):
        app.log.should_write_print_log = False
        self.prg = app.ci_program.CiProgram()
        self.text_buffer = app.text_buffer.TextBuffer(self.prg)
        self.text_buffer.set_view(FakeView())
        # self.assertEqual(self.text_buffer.scroll_row, 0)
        # self.assertEqual(self.text_buffer.scroll_col, 0)

    def tearDown(self):
        self.text_buffer = None

    def test_auto_indent(self):
        self.prg.prefs.editor["auto_insert_closing_character"] = False

        def insert(*args):
            self.text_buffer.insert_printable_with_pairing(*args)
            self.text_buffer.parse_document()

        tb = self.text_buffer
        self.assertEqual(tb.parser.row_count(), 1)
        insert(ord("a"), None)
        insert(ord(":"), None)
        self.assertEqual(tb.pen_row, 0)
        tb.carriage_return()
        self.assertEqual(tb.pen_row, 1)
        check_row(self, tb, 0, "a:")
        check_row(self, tb, 1, "")

        # Replace member function to return a grammar with and indent.
        def grammar_at(row, col):
            return {"indent": "  "}

        tb.parser.grammar_at = grammar_at
        tb.backspace()
        tb.carriage_return()
        check_row(self, tb, 0, "a:")
        check_row(self, tb, 1, "  ")
        insert(ord("b"), None)
        insert(ord(":"), None)
        tb.carriage_return()
        insert(ord("c"), None)
        insert(ord(":"), None)
        tb.carriage_return()
        check_row(self, tb, 0, "a:")
        check_row(self, tb, 1, "  b:")
        check_row(self, tb, 2, "    c:")

    def test_indent_unindent_lines(self):
        def insert(*args):
            self.text_buffer.insert_printable_with_pairing(*args)
            self.text_buffer.parse_document()

        tb = self.text_buffer
        self.assertEqual(tb.parser.row_count(), 1)
        insert(ord("a"), None)
        tb.carriage_return()
        insert(ord("b"), None)
        tb.carriage_return()
        insert(ord("c"), None)
        tb.carriage_return()
        insert(ord("d"), None)
        tb.carriage_return()
        check_row(self, tb, 0, "a")
        check_row(self, tb, 1, "b")
        check_row(self, tb, 2, "c")
        check_row(self, tb, 3, "d")
        tb.pen_row = 1
        tb.marker_row = 2
        tb.indent_lines()
        check_row(self, tb, 0, "a")
        check_row(self, tb, 1, "  b")
        check_row(self, tb, 2, "  c")
        check_row(self, tb, 3, "d")
        tb.pen_row = 0
        tb.marker_row = 3
        tb.indent_lines()
        check_row(self, tb, 0, "  a")
        check_row(self, tb, 1, "    b")
        check_row(self, tb, 2, "    c")
        check_row(self, tb, 3, "  d")
        tb.unindent_lines()
        check_row(self, tb, 0, "a")
        check_row(self, tb, 1, "  b")
        check_row(self, tb, 2, "  c")
        check_row(self, tb, 3, "d")
        tb.unindent_lines()
        check_row(self, tb, 0, "a")
        check_row(self, tb, 1, "b")
        check_row(self, tb, 2, "c")
        check_row(self, tb, 3, "d")
        tb.pen_row = 1
        tb.marker_row = 1
        tb.indent_lines()
        check_row(self, tb, 0, "a")
        check_row(self, tb, 1, "  b")
        check_row(self, tb, 2, "c")
        check_row(self, tb, 3, "d")
        tb.indent_lines()
        check_row(self, tb, 0, "a")
        check_row(self, tb, 1, "    b")
        check_row(self, tb, 2, "c")
        check_row(self, tb, 3, "d")
        tb.unindent_lines()
        check_row(self, tb, 0, "a")
        check_row(self, tb, 1, "  b")
        check_row(self, tb, 2, "c")
        check_row(self, tb, 3, "d")
        tb.pen_row = 3
        tb.marker_row = 3
        tb.indent_lines()
        check_row(self, tb, 0, "a")
        check_row(self, tb, 1, "  b")
        check_row(self, tb, 2, "c")
        check_row(self, tb, 3, "  d")
        tb.pen_row = 0
        tb.marker_row = 3
        tb.indent_lines()
        check_row(self, tb, 0, "  a")
        check_row(self, tb, 1, "    b")
        check_row(self, tb, 2, "  c")
        check_row(self, tb, 3, "    d")
        tb.pen_row = 3
        tb.marker_row = 3
        tb.unindent_lines()
        check_row(self, tb, 0, "  a")
        check_row(self, tb, 1, "    b")
        check_row(self, tb, 2, "  c")
        check_row(self, tb, 3, "  d")
        tb.unindent_lines()
        check_row(self, tb, 0, "  a")
        check_row(self, tb, 1, "    b")
        check_row(self, tb, 2, "  c")
        check_row(self, tb, 3, "d")
        tb.unindent_lines()
        check_row(self, tb, 0, "  a")
        check_row(self, tb, 1, "    b")
        check_row(self, tb, 2, "  c")
        check_row(self, tb, 3, "d")
        tb.pen_row = 0
        tb.marker_row = 0
        tb.unindent_lines()
        check_row(self, tb, 0, "a")
        check_row(self, tb, 1, "    b")
        check_row(self, tb, 2, "  c")
        check_row(self, tb, 3, "d")
        tb.unindent_lines()
        check_row(self, tb, 0, "a")
        check_row(self, tb, 1, "    b")
        check_row(self, tb, 2, "  c")
        check_row(self, tb, 3, "d")

    def test_indent_unindent_lines2(self):
        def insert(input):
            for i in input:
                if i == "\n":
                    self.text_buffer.carriage_return()
                else:
                    self.text_buffer.insert_printable_with_pairing(ord(i), None)
                    self.text_buffer.parse_document()
            self.assertEqual(self.text_buffer.parser.data, input)

        def check_pen_marker(pen_row, pen_col, marker_row, marker_col):
            self.assertEqual(
                (pen_row, pen_col, marker_row, marker_col),
                (tb.pen_row, tb.pen_col, tb.marker_row, tb.marker_col),
            )

        def select_char(pen_row, pen_col, marker_row, marker_col):
            self.text_buffer.pen_row = pen_row
            self.text_buffer.pen_col = pen_col
            self.text_buffer.marker_row = marker_row
            self.text_buffer.marker_col = marker_col
            self.text_buffer.selection_mode = app.selectable.SELECTION_CHARACTER

        tb = self.text_buffer
        self.assertEqual(tb.parser.row_count(), 1)
        check_pen_marker(0, 0, 0, 0)
        insert("apple\nbanana\ncarrot\ndate\neggplant\n")
        check_row(self, tb, 0, "apple")
        check_row(self, tb, 1, "banana")
        check_row(self, tb, 2, "carrot")
        check_row(self, tb, 3, "date")
        check_row(self, tb, 4, "eggplant")
        select_char(0, 3, 2, 2)
        check_pen_marker(0, 3, 2, 2)
        tb.indent()
        check_row(self, tb, 0, "  apple")
        check_row(self, tb, 1, "  banana")
        check_row(self, tb, 2, "  carrot")
        check_row(self, tb, 3, "date")
        check_row(self, tb, 4, "eggplant")
        check_pen_marker(0, 5, 2, 4)
        tb.indent()
        check_row(self, tb, 0, "    apple")
        check_row(self, tb, 1, "    banana")
        check_row(self, tb, 2, "    carrot")
        check_row(self, tb, 3, "date")
        check_row(self, tb, 4, "eggplant")
        check_pen_marker(0, 7, 2, 6)

        select_char(0, 3, 0, 2)
        tb.unindent()
        check_row(self, tb, 0, "  apple")
        check_row(self, tb, 1, "    banana")
        check_row(self, tb, 2, "    carrot")
        check_row(self, tb, 3, "date")
        check_row(self, tb, 4, "eggplant")
        check_pen_marker(0, 1, 0, 0)

        select_char(0, 3, 2, 2)
        tb.indent()
        check_row(self, tb, 0, "    apple")
        check_row(self, tb, 1, "      banana")
        check_row(self, tb, 2, "      carrot")
        check_row(self, tb, 3, "date")
        check_row(self, tb, 4, "eggplant")
        check_pen_marker(0, 5, 2, 4)
        tb.indent()
        check_pen_marker(0, 7, 2, 6)
        tb.indent()
        check_pen_marker(0, 9, 2, 8)

class TextInsertTestCases(ActionsTestCase):
    def setUp(self):
        app.log.should_write_print_log = False
        self.prg = app.ci_program.CiProgram()
        self.text_buffer = app.text_buffer.TextBuffer(self.prg)
        self.text_buffer.set_view(FakeView())
        # self.assertEqual(self.text_buffer.scroll_row, 0)
        # self.assertEqual(self.text_buffer.scroll_col, 0)

    def tearDown(self):
        self.text_buffer = None

    def test_auto_insert_pair_disable(self):
        self.prg.prefs.editor["auto_insert_closing_character"] = False

        def insert(*args):
            self.text_buffer.insert_printable_with_pairing(*args)
            self.text_buffer.parse_document()

        tb = self.text_buffer
        insert(ord("o"), None)
        insert(ord("("), None)
        check_row(self, tb, 0, "o(")
        insert(ord("a"), None)
        check_row(self, tb, 0, "o(a")
        tb.edit_undo()
        check_row(self, tb, 0, "o(")
        tb.edit_undo()
        check_row(self, tb, 0, "o")
        tb.edit_undo()
        check_row(self, tb, 0, "")
        # Don't insert pair if the next char is not whitespace.
        insert(ord("o"), None)
        check_row(self, tb, 0, "o")
        tb.cursor_left()
        check_row(self, tb, 0, "o")
        insert(ord("("), None)
        check_row(self, tb, 0, "(o")

    def test_auto_insert_pair_enable(self):
        self.prg.prefs.editor["auto_insert_closing_character"] = True

        def insert(*args):
            self.text_buffer.insert_printable_with_pairing(*args)
            self.text_buffer.parse_document()

        tb = self.text_buffer
        insert(ord("o"), None)
        insert(ord("("), None)
        check_row(self, tb, 0, "o()")
        insert(ord("a"), None)
        check_row(self, tb, 0, "o(a)")
        tb.edit_undo()
        check_row(self, tb, 0, "o()")
        tb.edit_undo()
        check_row(self, tb, 0, "")
        # Don't insert pair if the next char is not whitespace.
        insert(ord("o"), None)
        check_row(self, tb, 0, "o")
        tb.cursor_left()
        check_row(self, tb, 0, "o")
        insert(ord("("), None)
        check_row(self, tb, 0, "(o")

class GrammarDeterminationTestCases(ActionsTestCase):
    def setUp(self):
        app.log.should_write_print_log = False
        self.prg = app.ci_program.CiProgram()
        self.text_buffer = app.text_buffer.TextBuffer(self.prg)
        self.text_buffer.set_view(FakeView())

    def tearDown(self):
        self.text_buffer = None

    def test_message_backspace(self):
        tb = self.text_buffer
        self.assertEqual(
            tb._determine_root_grammar(*os.path.splitext("test.cc")),
            self.prg.prefs.grammars.get(self.prg.prefs.extensions.get(".cc")),
        )
