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
import unittest
import unicodedata

import app.curses_util

class CursesUtilTestCases(unittest.TestCase):
    def test_curses_key_name(self):
        # These actually test the fake curses.
        def test1():
            curses.keyname(-3)

        self.assertRaises(ValueError, test1)

        def test2():
            curses.keyname([])

        self.assertRaises(TypeError, test2)

        def test3():
            curses.keyname(9 ** 999)

        self.assertRaises(OverflowError, test3)

    def test_rendered_find_iter(self):
        def test(line, start_col, end_col, matches):
            matches.reverse()
            for s, column, length, index in app.curses_util.rendered_find_iter(
                line, start_col, end_col, ("[]{}()",), True, True
            ):
                self.assertEqual(matches.pop(), (s, column, length, index))

        # Float and leading zero.
        line = """5.32e+30 a 000808"""
        test(
            line,
            0,
            len(line),
            [
                ("5.32e+30", 0, 8, 1),
                ("000808", 11, 6, 1),
            ],
        )

        # Parenthesis and number.
        line = """(23432ull a"""
        test(
            line,
            0,
            len(line),
            [
                ("(", 0, 1, 0),
                ("23432ull", 1, 8, 1),
            ],
        )

        # Multiple numbers and string of brackets.
        line = """23 five )}]](23432ull a"""
        test(
            line,
            0,
            len(line),
            [
                ("23", 0, 2, 1),
                (")}]](", 8, 5, 0),
                ("23432ull", 13, 8, 1),
            ],
        )

        # Constrained columns.
        line = """23 five )}]](23432ull a"""
        test(
            line,
            1,
            len(line) - 4,
            [
                ("3", 1, 1, 1),
                (")}]](", 8, 5, 0),
                ("23432u", 13, 6, 1),
            ],
        )

    def test_unicode_data(self):
        self.assertEqual(unicodedata.east_asian_width("a"), "Na")
        self.assertEqual(unicodedata.east_asian_width(" "), "Na")
        self.assertEqual(unicodedata.east_asian_width("\b"), "N")
        self.assertEqual(unicodedata.east_asian_width("こ"), "W")
        # This is "W" in python3 and "F" in python2.
        self.assertIn(unicodedata.east_asian_width("⏰"), ("F", "W"))

    def test_column_to_index(self):
        self.assertEqual(0, app.curses_util.column_to_index(0, "test"))
        self.assertEqual(1, app.curses_util.column_to_index(1, "test"))
        self.assertEqual(2, app.curses_util.column_to_index(2, "test"))
        self.assertEqual(3, app.curses_util.column_to_index(3, "test"))
        # Test past the length of the string.
        self.assertIs(None, app.curses_util.column_to_index(4, "test"))
        self.assertIs(None, app.curses_util.column_to_index(8, "test"))

        self.assertEqual(0, app.curses_util.column_to_index(0, "\ttest\ttabs"))
        self.assertEqual(0, app.curses_util.column_to_index(1, "\ttest\ttabs"))
        self.assertEqual(0, app.curses_util.column_to_index(2, "\ttest\ttabs"))
        self.assertEqual(0, app.curses_util.column_to_index(3, "\ttest\ttabs"))
        self.assertEqual(0, app.curses_util.column_to_index(4, "\ttest\ttabs"))
        self.assertEqual(0, app.curses_util.column_to_index(5, "\ttest\ttabs"))
        self.assertEqual(0, app.curses_util.column_to_index(6, "\ttest\ttabs"))
        self.assertEqual(0, app.curses_util.column_to_index(7, "\ttest\ttabs"))
        self.assertEqual(1, app.curses_util.column_to_index(8, "\ttest\ttabs"))
        self.assertEqual(2, app.curses_util.column_to_index(9, "\ttest\ttabs"))
        self.assertEqual(3, app.curses_util.column_to_index(10, "\ttest\ttabs"))
        self.assertEqual(4, app.curses_util.column_to_index(11, "\ttest\ttabs"))
        self.assertEqual(5, app.curses_util.column_to_index(12, "\ttest\ttabs"))
        self.assertEqual(5, app.curses_util.column_to_index(13, "\ttest\ttabs"))
        self.assertEqual(5, app.curses_util.column_to_index(14, "\ttest\ttabs"))
        self.assertEqual(5, app.curses_util.column_to_index(15, "\ttest\ttabs"))
        self.assertEqual(6, app.curses_util.column_to_index(16, "\ttest\ttabs"))
        self.assertEqual(7, app.curses_util.column_to_index(17, "\ttest\ttabs"))
        self.assertEqual(8, app.curses_util.column_to_index(18, "\ttest\ttabs"))
        # Test past the length of the string.
        self.assertIs(None, app.curses_util.column_to_index(21, "\ttest\ttabs"))
        self.assertIs(None, app.curses_util.column_to_index(22, "\ttest\ttabs"))
        self.assertIs(None, app.curses_util.column_to_index(999, "\ttest\ttabs"))

        self.assertEqual(0, app.curses_util.column_to_index(0, "こんにちは"))
        self.assertEqual(0, app.curses_util.column_to_index(1, "こんにちは"))
        self.assertEqual(1, app.curses_util.column_to_index(2, "こんにちは"))
        self.assertEqual(1, app.curses_util.column_to_index(3, "こんにちは"))
        self.assertEqual(2, app.curses_util.column_to_index(4, "こんにちは"))
        self.assertEqual(4, app.curses_util.column_to_index(8, "こんにちは"))
        self.assertEqual(4, app.curses_util.column_to_index(9, "こんにちは"))
        # Test past the length of the string.
        self.assertIs(None, app.curses_util.column_to_index(10, "こんにちは"))
        self.assertIs(None, app.curses_util.column_to_index(11, "こんにちは"))
        self.assertIs(None, app.curses_util.column_to_index(12, "こんにちは"))

    def test_char_at_column(self):
        cu = app.curses_util
        self.assertEqual("t", cu.char_at_column(0, "test"))
        self.assertEqual("e", cu.char_at_column(1, "test"))
        self.assertEqual("s", cu.char_at_column(2, "test"))
        self.assertEqual("t", cu.char_at_column(3, "test"))
        # Test past the length of the string.
        self.assertIs(None, cu.char_at_column(4, "test"))
        self.assertIs(None, cu.char_at_column(8, "test"))

        self.assertEqual("\t", cu.char_at_column(0, "\ttest\ttabs"))
        self.assertEqual("\t", cu.char_at_column(1, "\ttest\ttabs"))
        self.assertEqual("\t", cu.char_at_column(2, "\ttest\ttabs"))
        self.assertEqual("\t", cu.char_at_column(3, "\ttest\ttabs"))
        self.assertEqual("\t", cu.char_at_column(4, "\ttest\ttabs"))
        self.assertEqual("\t", cu.char_at_column(5, "\ttest\ttabs"))
        self.assertEqual("\t", cu.char_at_column(6, "\ttest\ttabs"))
        self.assertEqual("\t", cu.char_at_column(7, "\ttest\ttabs"))
        self.assertEqual("t", cu.char_at_column(8, "\ttest\ttabs"))
        self.assertEqual("e", cu.char_at_column(9, "\ttest\ttabs"))
        self.assertEqual("s", cu.char_at_column(10, "\ttest\ttabs"))
        self.assertEqual("t", cu.char_at_column(11, "\ttest\ttabs"))
        self.assertEqual("\t", cu.char_at_column(12, "\ttest\ttabs"))
        self.assertEqual("\t", cu.char_at_column(13, "\ttest\ttabs"))
        self.assertEqual("\t", cu.char_at_column(14, "\ttest\ttabs"))
        self.assertEqual("\t", cu.char_at_column(15, "\ttest\ttabs"))
        self.assertEqual("t", cu.char_at_column(16, "\ttest\ttabs"))
        self.assertEqual("a", cu.char_at_column(17, "\ttest\ttabs"))
        self.assertEqual("b", cu.char_at_column(18, "\ttest\ttabs"))
        self.assertEqual("s", cu.char_at_column(19, "\ttest\ttabs"))
        # Test past the length of the string.
        self.assertIs(None, cu.char_at_column(20, "\ttest\ttabs"))
        self.assertIs(None, cu.char_at_column(21, "\ttest\ttabs"))
        self.assertIs(None, cu.char_at_column(999, "\ttest\ttabs"))

        self.assertEqual("こ", cu.char_at_column(0, "こんにちは"))
        self.assertEqual("こ", cu.char_at_column(1, "こんにちは"))
        self.assertEqual("ん", cu.char_at_column(2, "こんにちは"))
        self.assertEqual("ん", cu.char_at_column(3, "こんにちは"))
        self.assertEqual("に", cu.char_at_column(4, "こんにちは"))
        self.assertEqual("は", cu.char_at_column(8, "こんにちは"))
        self.assertEqual("は", cu.char_at_column(9, "こんにちは"))
        # Test past the length of the string.
        self.assertIs(None, cu.char_at_column(10, "こんにちは"))
        self.assertIs(None, cu.char_at_column(11, "こんにちは"))
        self.assertIs(None, cu.char_at_column(12, "こんにちは"))

    def test_fit_to_rendered_width(self):
        fit_to_rendered_width = app.curses_util.fit_to_rendered_width

        self.assertEqual(0, fit_to_rendered_width(0, 0, "test"))
        self.assertEqual(1, fit_to_rendered_width(0, 1, "test"))
        self.assertEqual(2, fit_to_rendered_width(0, 2, "test"))
        self.assertEqual(3, fit_to_rendered_width(0, 3, "test"))
        self.assertEqual(4, fit_to_rendered_width(0, 4, "test"))
        # Test past the length of the string.
        self.assertEqual(4, fit_to_rendered_width(0, 8, "test"))

        # Test double wide characters (theses characters render as two cells in
        # a fixed width font).
        self.assertEqual(0, fit_to_rendered_width(0, 0, "こんにちは"))
        self.assertEqual(0, fit_to_rendered_width(0, 1, "こんにちは"))
        self.assertEqual(1, fit_to_rendered_width(0, 2, "こんにちは"))
        self.assertEqual(1, fit_to_rendered_width(0, 3, "こんにちは"))
        self.assertEqual(2, fit_to_rendered_width(0, 4, "こんにちは"))
        self.assertEqual(4, fit_to_rendered_width(0, 8, "こんにちは"))
        self.assertEqual(4, fit_to_rendered_width(0, 9, "こんにちは"))
        self.assertEqual(5, fit_to_rendered_width(0, 10, "こんにちは"))

        # Test past the length of the string.
        self.assertEqual(5, fit_to_rendered_width(0, 11, "こんにちは"))
        self.assertEqual(5, fit_to_rendered_width(0, 12, "こんにちは"))

        # Test tabs.
        self.assertEqual(1, fit_to_rendered_width(0, 8, "\t"))
        self.assertEqual(0, fit_to_rendered_width(0, 7, "\t"))

    def test_rendered_sub_str(self):
        self.assertEqual("test", app.curses_util.rendered_sub_str("test", 0))
        self.assertEqual("test", app.curses_util.rendered_sub_str("test", 0, 4))
        self.assertEqual("est", app.curses_util.rendered_sub_str("test", 1, 4))
        self.assertEqual("st", app.curses_util.rendered_sub_str("test", 2, 4))
        self.assertEqual("t", app.curses_util.rendered_sub_str("test", 3, 4))
        self.assertEqual("", app.curses_util.rendered_sub_str("test", 4, 4))
        self.assertEqual("tes", app.curses_util.rendered_sub_str("test", 0, 3))
        self.assertEqual("te", app.curses_util.rendered_sub_str("test", 0, 2))
        self.assertEqual("t", app.curses_util.rendered_sub_str("test", 0, 1))
        self.assertEqual("", app.curses_util.rendered_sub_str("test", 0, 0))
        self.assertEqual("es", app.curses_util.rendered_sub_str("test", 1, 3))
        self.assertEqual("", app.curses_util.rendered_sub_str("test", 2, 2))
        self.assertEqual("eight", app.curses_util.rendered_sub_str("eight", 0, 5))
        self.assertEqual("igh", app.curses_util.rendered_sub_str("eight", 1, 4))
        self.assertEqual("g", app.curses_util.rendered_sub_str("eight", 2, 3))
        self.assertEqual("", app.curses_util.rendered_sub_str("eight", 3, 3))
        self.assertEqual("こんにちは", app.curses_util.rendered_sub_str("こんにちは", 0, 10))
        self.assertEqual(" んにちは", app.curses_util.rendered_sub_str("こんにちは", 1, 10))
        self.assertEqual("んにちは", app.curses_util.rendered_sub_str("こんにちは", 2, 10))
        self.assertEqual(" にちは", app.curses_util.rendered_sub_str("こんにちは", 3, 10))
        self.assertEqual("にちは", app.curses_util.rendered_sub_str("こんにちは", 4, 10))
        self.assertEqual("は", app.curses_util.rendered_sub_str("こんにちは", 8))
        self.assertEqual("は", app.curses_util.rendered_sub_str("こんにちは", 8, 10))
        self.assertEqual(" ", app.curses_util.rendered_sub_str("こんにちは", 9, 10))
        self.assertEqual("", app.curses_util.rendered_sub_str("こんにちは", 10, 10))
        self.assertEqual("こんにち ", app.curses_util.rendered_sub_str("こんにちは", 0, 9))
        self.assertEqual("こんにち", app.curses_util.rendered_sub_str("こんにちは", 0, 8))
        self.assertEqual("こんに ", app.curses_util.rendered_sub_str("こんにちは", 0, 7))
        self.assertEqual("こんに", app.curses_util.rendered_sub_str("こんにちは", 0, 6))
        self.assertEqual("こん ", app.curses_util.rendered_sub_str("こんにちは", 0, 5))
        self.assertEqual("こん", app.curses_util.rendered_sub_str("こんにちは", 0, 4))
        self.assertEqual("こ ", app.curses_util.rendered_sub_str("こんにちは", 0, 3))
        self.assertEqual("こ", app.curses_util.rendered_sub_str("こんにちは", 0, 2))
        self.assertEqual(" ", app.curses_util.rendered_sub_str("こんにちは", 0, 1))
        self.assertEqual("", app.curses_util.rendered_sub_str("こんにちは", 0, 0))

        # Test past the length of the string.
        self.assertEqual("", app.curses_util.rendered_sub_str("", 1, 1))
        self.assertEqual("test", app.curses_util.rendered_sub_str("test", 0, 8))

        # Test with tabs.
        self.assertEqual("   ", app.curses_util.rendered_sub_str("\tこんにちは", 0, 3))
        self.assertEqual("     こ", app.curses_util.rendered_sub_str("\tこんにちは", 3, 10))
        self.assertEqual(
            "        こん", app.curses_util.rendered_sub_str("\tこんにちは", 0, 12)
        )
        self.assertEqual(
            "        <tab", app.curses_util.rendered_sub_str("\t<tab", 0, None)
        )
        self.assertEqual(
            "         <tab+space",
            app.curses_util.rendered_sub_str("\t <tab+space", 0, None),
        )
        self.assertEqual(
            "        <space+tab",
            app.curses_util.rendered_sub_str(" \t<space+tab", 0, None),
        )
        self.assertEqual(
            "a       <", app.curses_util.rendered_sub_str("a\t<", 0, None)
        )
        self.assertEqual(
            "some text.>     <",
            app.curses_util.rendered_sub_str("some text.>\t<", 0, None),
        )
        self.assertEqual(
            "                <2tabs",
            app.curses_util.rendered_sub_str("\t\t<2tabs", 0, None),
        )
        self.assertEqual(
            "line    with    tabs",
            app.curses_util.rendered_sub_str("line\twith\ttabs", 0, None),
        )
        self.assertEqual(
            "ends with tab>  ",
            app.curses_util.rendered_sub_str("ends with tab>\t", 0, None),
        )

    def test_rendered_width(self):
        self.assertEqual(0, app.curses_util.column_width(""))
        self.assertEqual(4, app.curses_util.column_width("test"))
        self.assertEqual(8, app.curses_util.column_width("\t"))
        self.assertEqual(9, app.curses_util.column_width("\ta"))
        self.assertEqual(16, app.curses_util.column_width("\ta\t"))
        self.assertEqual(8, app.curses_util.column_width("i\t"))

        self.assertEqual(2, app.curses_util.column_width("こ"))
        self.assertEqual(4, app.curses_util.column_width("こん"))
        self.assertEqual(6, app.curses_util.column_width("こんに"))
        self.assertEqual(10, app.curses_util.column_width("こんにちは"))

        self.assertEqual(3, app.curses_util.column_width("aこ"))
        self.assertEqual(5, app.curses_util.column_width("aこん"))
        self.assertEqual(3, app.curses_util.column_width("こc"))
        self.assertEqual(4, app.curses_util.column_width("aこc"))
        self.assertEqual(7, app.curses_util.column_width("aこbんc"))

    def test_char_width(self):
        self.assertEqual(0, app.curses_util.char_width("", 0))
        self.assertEqual(8, app.curses_util.char_width("\t", 0))
        self.assertEqual(1, app.curses_util.char_width(" ", 0))
        self.assertEqual(7, app.curses_util.char_width("\t", 1))
        self.assertEqual(6, app.curses_util.char_width("\t", 2))
        self.assertEqual(2, app.curses_util.char_width("\t", 6))
        self.assertEqual(1, app.curses_util.char_width("\t", 7))
        self.assertEqual(0, app.curses_util.char_width("", 8))
        self.assertEqual(8, app.curses_util.char_width("\t", 8))
        self.assertEqual(7, app.curses_util.char_width("\t", 9))
        self.assertEqual(2, app.curses_util.char_width("こ", 0))
        self.assertEqual(0, app.curses_util.char_width("\b", 0))
        self.assertEqual(0, app.curses_util.char_width("\n", 0))
        self.assertEqual(2, app.curses_util.char_width("⏰", 0))

    def test_floor_col(self):
        test = """\tfive\t"""
        floor_col = app.curses_util.floor_col
        self.assertEqual(0, floor_col(0, test))
        self.assertEqual(0, floor_col(1, test))
        self.assertEqual(0, floor_col(2, test))
        self.assertEqual(0, floor_col(3, test))
        self.assertEqual(0, floor_col(4, test))
        self.assertEqual(0, floor_col(5, test))
        self.assertEqual(0, floor_col(6, test))
        self.assertEqual(0, floor_col(7, test))
        self.assertEqual(8, floor_col(8, test))
        self.assertEqual(9, floor_col(9, test))
        self.assertEqual(10, floor_col(10, test))
        self.assertEqual(11, floor_col(11, test))
        self.assertEqual(12, floor_col(12, test))
        self.assertEqual(12, floor_col(13, test))
        self.assertEqual(12, floor_col(14, test))
        self.assertEqual(12, floor_col(15, test))
        self.assertEqual(16, floor_col(16, test))
        self.assertEqual(16, floor_col(17, test))
        self.assertEqual(16, floor_col(99, test))

        test2 = """more testing"""
        self.assertEqual(0, floor_col(0, test2))
        self.assertEqual(2, floor_col(2, test2))
        self.assertEqual(12, floor_col(99, test2))

    def test_prior_char_col(self):
        test = """\tfive\t"""
        prior_char_col = app.curses_util.prior_char_col
        self.assertEqual(None, prior_char_col(0, test))
        self.assertEqual(0, prior_char_col(1, test))
        self.assertEqual(0, prior_char_col(2, test))
        self.assertEqual(0, prior_char_col(3, test))
        self.assertEqual(0, prior_char_col(4, test))
        self.assertEqual(0, prior_char_col(5, test))
        self.assertEqual(0, prior_char_col(6, test))
        self.assertEqual(0, prior_char_col(7, test))
        self.assertEqual(0, prior_char_col(8, test))
        self.assertEqual(8, prior_char_col(9, test))
        self.assertEqual(9, prior_char_col(10, test))
        self.assertEqual(10, prior_char_col(11, test))
        self.assertEqual(11, prior_char_col(12, test))
        self.assertEqual(12, prior_char_col(13, test))
        self.assertEqual(12, prior_char_col(14, test))
        self.assertEqual(12, prior_char_col(15, test))
        self.assertEqual(12, prior_char_col(16, test))
        self.assertEqual(None, prior_char_col(17, test))

        test2 = """more testing"""
        self.assertEqual(None, prior_char_col(0, test2))
        self.assertEqual(1, prior_char_col(2, test2))
        self.assertEqual(11, prior_char_col(12, test2))
        self.assertEqual(None, prior_char_col(13, test2))
