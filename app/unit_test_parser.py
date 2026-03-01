# -*- coding: utf-8 -*-
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

import cProfile
import io
import pstats
import sys
from timeit import timeit
import unittest

import app.parser
import app.prefs

class ParserTestCases(unittest.TestCase):
    def setUp(self):
        self.parser = app.parser.Parser(app.prefs.Prefs())

    def tearDown(self):
        self.parser = None

    def check_parser_nodes(self, expected, actual, startIndex=None):
        kGrammar = app.parser.kGrammar
        kBegin = app.parser.kBegin
        kPrior = app.parser.kPrior
        kVisual = app.parser.kVisual
        if startIndex is None:
            # Test for exact match.
            startIndex = 0
            self.assertEqual(len(expected), len(actual))
        else:
            # Test a subset.
            self.assertLessEqual(len(expected), startIndex + len(actual))
        for index, expectedNode in enumerate(expected):
            actualNode = actual[startIndex + index]
            self.assertTrue(isinstance(actualNode, tuple))
            # print("Node:", startIndex + index, expectedNode, actualNode[1:])
            self.assertEqual(expectedNode[kGrammar], actualNode[kGrammar]["name"])
            self.assertEqual(expectedNode[kBegin], actualNode[kBegin])
            self.assertEqual(expectedNode[kPrior], actualNode[kPrior])
            self.assertEqual(expectedNode[kVisual], actualNode[kVisual])

    def check_parser_rows(self, expected, actual, startIndex=None):
        if startIndex is None:
            # Test for exact match.
            startIndex = 0
            self.assertEqual(len(expected), len(actual))
        else:
            # Test a subset.
            self.assertLessEqual(len(expected), startIndex + len(actual))
        for index, expectedRow in enumerate(expected):
            actualRow = actual[startIndex + index]
            self.assertTrue(isinstance(actualRow, int))
            # print("Node:", startIndex + index, expectedNode, actualRow)
            self.assertEqual(expectedRow, actualRow)

    def print_parser_nodes(self, nodes):
        for n in nodes:
            print("({}, {}, {}, {}),".format(n[0]["name"], n[1], n[2], n[3]))

    def test_parse(self):
        tests = [
            """/* first comment */
two
// second comment
#include "test.h"
void blah();
// No end of line""",
            """/* first comment */
two
// second comment
#include "test.h"
void blah();
""",
            """/* test includes */
// The malformed include on the next line is a regression test.
#include <test.h"
#include "test.h"
#include <test.h
#include "test.h"

#include <te"st.h>
#include "test>.h"

#include "test.h>
#include <test.h>
#include "test.h
#include <test.h>
void blah();

""",
        ]
        for test in tests:
            # self.assertEqual(test.splitlines(), test.split("\n"))
            lines = test.split("\n")
            self.prefs = app.prefs.Prefs()
            self.parser.parse(None, test, self.prefs.grammars["cpp"], 0, 99999)
            # self.parser.debug_log(print, test)
            self.assertEqual(len(lines), self.parser.row_count())
            for i, line in enumerate(lines):
                self.assertEqual(self.parser.row_text(i), line)
                self.assertEqual(self.parser.row_text_and_width(i), (line, len(line)))
            for node in self.parser.parserNodes:
                # These tests have no double wide characters.
                self.assertEqual(node[app.parser.kBegin], node[app.parser.kVisual])
            self.parser.debug_check_lines(None, test)

    def test_parse_cpp_literal(self):
        test = """/* first comment */
char stuff = R"mine(two
// not a comment)mine";
void blah();
"""
        self.prefs = app.prefs.Prefs()
        self.parser.parse(None, test, self.prefs.grammars["cpp"], 0, 99999)
        # self.parser.debug_log(print, test)
        self.assertEqual(self.parser.row_text(0), "/* first comment */")
        self.assertEqual(self.parser.row_text(1), """char stuff = R"mine(two""")
        self.assertEqual(
            self.parser.grammar_at(0, 0), self.prefs.grammars["cpp_block_comment"]
        )
        self.assertEqual(self.parser.grammar_at(1, 8), self.prefs.grammars["cpp"])
        self.assertEqual(
            self.parser.grammar_at(1, 18), self.prefs.grammars["cpp_string_literal"]
        )
        self.assertEqual(self.parser.grammar_at(3, 7), self.prefs.grammars["cpp"])

    def test_parse_rs_raw_string(self):
        test = """// one
let stuff = r###"two
not an "## end
ignored " quote"###;
fn main { }
// two
"""
        self.prefs = app.prefs.Prefs()
        self.parser.parse(None, test, self.prefs.grammars["rs"], 0, 99999)
        self.assertEqual(self.parser.row_text(0), "// one")
        self.assertEqual(self.parser.row_text(1), """let stuff = r###"two""")
        self.assertEqual(
            self.parser.grammar_at(0, 0), self.prefs.grammars["cpp_line_comment"]
        )
        self.assertEqual(self.parser.grammar_at(1, 8), self.prefs.grammars["rs"])
        self.assertEqual(
            self.parser.grammar_at(1, 18), self.prefs.grammars["rs_raw_string"]
        )
        self.assertEqual(
            self.parser.grammar_at(2, 12), self.prefs.grammars["rs_raw_string"]
        )
        self.assertEqual(
            self.parser.grammar_at(3, 15), self.prefs.grammars["rs_raw_string"]
        )
        self.assertEqual(
            self.parser.grammar_at(3, 12), self.prefs.grammars["rs_raw_string"]
        )
        self.assertEqual(self.parser.grammar_at(4, 7), self.prefs.grammars["rs"])

    def test_parse_tabs(self):
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
parse\t\t\tz
"""
        self.prefs = app.prefs.Prefs()
        p = self.parser
        self.parser.parse(None, test, self.prefs.grammars["rs"], 0, 99999)
        if 0:
            print("")
            for i, t in enumerate(test.splitlines()):
                print("{}: {}".format(i, repr(t)))
            p.debug_log(print, test)

        self.assertEqual(p.row_count(), 12)

        self.assertEqual(p.row_text(0), "\t<tab")
        self.assertEqual(p.row_text(1), "\t <tab+space")
        self.assertEqual(p.row_text(2), " \t<space+tab")
        self.assertEqual(p.row_text(3), "\ta<")
        self.assertEqual(p.row_text(4), "a\t<")
        self.assertEqual(p.row_text(5), "some text.>\t<")
        self.assertEqual(p.row_text(6), "\t\t<2tabs")
        self.assertEqual(p.row_text(7), "line\twith\ttabs")
        self.assertEqual(p.row_text(8), "ends with tab>\t")
        self.assertEqual(p.row_text(9), "\t")
        self.assertEqual(p.row_text(10), "parse\t\t\tz")
        self.assertEqual(p.row_text(11), "")

        self.assertEqual(p.row_text(0, 0), "\t<tab")
        self.assertEqual(p.row_text(0, 0, 0), "")
        self.assertEqual(p.row_text(0, 0, 30), "\t<tab")
        self.assertEqual(p.row_text(0, 8), "<tab")
        self.assertEqual(p.row_text(0, 8, 9), "<")
        self.assertEqual(p.row_text(0, 8, -3), "<")
        self.assertEqual(p.row_text(0, -4, -3), "<")
        self.assertEqual(p.row_text(0, -1), "b")
        self.assertEqual(p.row_text(0, -2, -1), "a")
        self.assertEqual(p.row_text(0, -3, -2), "t")
        self.assertEqual(p.row_text(0, 11), "b")
        self.assertEqual(p.row_text(1, 0, 0), "")
        self.assertEqual(p.row_text(1, 1, 1), "")
        self.assertEqual(p.row_text(11, 0, 0), "")

        self.assertEqual(p.row_text_and_width(0), ("\t<tab", 12))
        self.assertEqual(p.row_text_and_width(1), ("\t <tab+space", 19))
        self.assertEqual(p.row_text_and_width(2), (" \t<space+tab", 18))
        self.assertEqual(p.row_text_and_width(3), ("\ta<", 10))
        self.assertEqual(p.row_text_and_width(4), ("a\t<", 9))
        self.assertEqual(p.row_text_and_width(5), ("some text.>\t<", 17))
        self.assertEqual(p.row_text_and_width(6), ("\t\t<2tabs", 22))
        self.assertEqual(p.row_text_and_width(7), ("line\twith\ttabs", 20))
        self.assertEqual(p.row_text_and_width(8), ("ends with tab>\t", 16))
        self.assertEqual(p.row_text_and_width(9), ("\t", 8))

        self.assertEqual(p.row_width(0), 12)
        self.assertEqual(p.row_width(1), 19)
        self.assertEqual(p.row_width(2), 18)
        self.assertEqual(p.row_width(3), 10)
        self.assertEqual(p.row_width(4), 9)
        self.assertEqual(p.row_width(5), 17)
        self.assertEqual(p.row_width(6), 22)
        self.assertEqual(p.row_width(7), 20)
        self.assertEqual(p.row_width(8), 16)
        self.assertEqual(p.row_width(9), 8)

        self.assertEqual(p.grammar_index_from_row_col(0, 0), 1)
        self.assertEqual(p.grammar_index_from_row_col(0, 7), 1)
        self.assertEqual(p.grammar_index_from_row_col(0, 8), 2)
        self.assertEqual(p.grammar_index_from_row_col(1, 0), 1)

        # self.assertEqual(p.grammar_at(0, 0), 0)

        self.assertEqual(p.next_char_row_col(999999, 0), None)
        # Test "\t<tab".
        self.assertEqual(p.next_char_row_col(0, 0), (0, 8))
        self.assertEqual(p.next_char_row_col(0, 1), (0, 7))
        self.assertEqual(p.next_char_row_col(0, 7), (0, 1))
        self.assertEqual(p.next_char_row_col(0, 8), (0, 1))
        self.assertEqual(p.next_char_row_col(0, 11), (0, 1))
        self.assertEqual(p.next_char_row_col(0, 12), (1, -12))
        # Test "\t\t<2tabs".
        self.assertEqual(p.next_char_row_col(6, 0), (0, 8))
        self.assertEqual(p.next_char_row_col(6, 8), (0, 8))
        self.assertEqual(p.next_char_row_col(6, 16), (0, 1))
        self.assertEqual(p.next_char_row_col(6, 22), (1, -22))
        # Test "\t".
        self.assertEqual(p.next_char_row_col(9, 0), (0, 8))
        self.assertEqual(p.next_char_row_col(9, 8), (1, -8))
        # Test "parse\t\t\tz".
        self.assertEqual(p.next_char_row_col(10, 0), (0, 1))
        self.assertEqual(p.next_char_row_col(10, 4), (0, 1))
        self.assertEqual(p.next_char_row_col(10, 5), (0, 3))
        self.assertEqual(p.next_char_row_col(10, 8), (0, 8))
        self.assertEqual(p.next_char_row_col(10, 16), (0, 8))
        self.assertEqual(p.next_char_row_col(10, 24), (0, 1))
        self.assertEqual(p.next_char_row_col(10, 25), (1, -25))
        self.assertEqual(p.next_char_row_col(11, 0), None)

        # Test "\t<tab".
        self.assertEqual(p.prior_char_row_col(0, 0), None)
        self.assertEqual(p.prior_char_row_col(0, 1), (0, -1))
        self.assertEqual(p.prior_char_row_col(0, 7), (0, -7))
        # Test "\t\t<2tabs".
        self.assertEqual(p.prior_char_row_col(6, 1), (0, -1))
        self.assertEqual(p.prior_char_row_col(6, 5), (0, -5))
        self.assertEqual(p.prior_char_row_col(6, 8), (0, -8))
        self.assertEqual(p.prior_char_row_col(6, 9), (0, -1))
        self.assertEqual(p.prior_char_row_col(6, 15), (0, -7))
        self.assertEqual(p.prior_char_row_col(6, 16), (0, -8))
        self.assertEqual(p.prior_char_row_col(6, 17), (0, -1))
        self.assertEqual(p.prior_char_row_col(6, 18), (0, -1))
        self.assertEqual(p.prior_char_row_col(6, 19), (0, -1))
        self.assertEqual(p.prior_char_row_col(6, 20), (0, -1))
        # Test "\t".
        self.assertEqual(p.prior_char_row_col(9, 1), (0, -1))
        self.assertEqual(p.prior_char_row_col(9, 5), (0, -5))
        self.assertEqual(p.prior_char_row_col(9, 8), (0, -8))

        # Test "\t<tab".
        self.assertEqual(p.data_offset(0, 0), 0)
        self.assertEqual(p.data_offset_row_col(0), (0, 0))
        self.assertEqual(p.data_offset(0, 1), 0)
        self.assertEqual(p.data_offset(0, 2), 0)
        self.assertEqual(p.data_offset(0, 3), 0)
        self.assertEqual(p.data_offset(0, 7), 0)
        self.assertEqual(p.data_offset(0, 8), 1)
        self.assertEqual(p.data_offset_row_col(1), (0, 8))
        self.assertEqual(p.data_offset(0, 9), 2)
        self.assertEqual(p.data_offset_row_col(2), (0, 9))
        self.assertEqual(p.data_offset(0, 12), 5)
        self.assertEqual(p.data_offset_row_col(5), (0, 12))
        self.assertEqual(p.data_offset(0, 13), None)
        self.assertEqual(p.data_offset(0, 99), None)
        # Test "\t <tab+space".
        self.assertEqual(p.data_offset(1, 0), 6)
        self.assertEqual(p.data_offset_row_col(6), (1, 0))
        self.assertEqual(p.data_offset(1, 1), 6)
        self.assertEqual(p.data_offset(1, 2), 6)
        self.assertEqual(p.data_offset(1, 3), 6)
        self.assertEqual(p.data_offset(1, 7), 6)
        self.assertEqual(p.data_offset(1, 8), 7)
        self.assertEqual(p.data_offset_row_col(7), (1, 8))
        self.assertEqual(p.data_offset(1, 12), 11)
        self.assertEqual(p.data_offset(1, 14), 13)
        self.assertEqual(p.data_offset(1, 19), 18)
        self.assertEqual(p.data_offset_row_col(18), (1, 19))
        self.assertEqual(p.data_offset(1, 29), None)
        # Test " \t<space+tab".
        self.assertEqual(p.data_offset(2, 0), 19)
        self.assertEqual(p.data_offset_row_col(19), (2, 0))
        self.assertEqual(p.data_offset(2, 1), 20)
        self.assertEqual(p.data_offset(2, 2), 20)
        self.assertEqual(p.data_offset(2, 12), 25)
        self.assertEqual(p.data_offset_row_col(20), (2, 1))
        self.assertEqual(p.data_offset_row_col(21), (2, 8))
        self.assertEqual(p.data_offset_row_col(25), (2, 12))
        # Test "\ta<".
        # Test "a\t<".
        self.assertEqual(p.data_offset(4, 0), 36)
        self.assertEqual(p.data_offset_row_col(36), (4, 0))
        self.assertEqual(p.data_offset(4, 1), 37)
        self.assertEqual(p.data_offset(4, 2), 37)
        # Test "some text.>\t<".
        # Test "\t\t<2tabs".
        self.assertEqual(p.data_offset(6, 0), 54)
        self.assertEqual(p.data_offset(6, 7), 54)
        self.assertEqual(p.data_offset(6, 8), 55)
        self.assertEqual(p.data_offset(6, 15), 55)
        self.assertEqual(p.data_offset(6, 16), 56)
        self.assertEqual(p.data_offset(6, 17), 57)
        # Test "line\twith\ttabs".
        # Test "ends with tab>\t".
        # Test "\t".
        # Test "parse\t\t\tz".
        self.assertEqual(p.data_offset(10, 0), 96)
        self.assertEqual(p.data_offset(10, 4), 100)
        self.assertEqual(p.data_offset(10, 5), 101)
        self.assertEqual(p.data_offset(10, 6), 101)
        self.assertEqual(p.data_offset(10, 7), 101)
        self.assertEqual(p.data_offset(10, 8), 102)
        self.assertEqual(p.data_offset(10, 9), 102)
        self.assertEqual(p.data_offset(10, 15), 102)
        self.assertEqual(p.data_offset(10, 16), 103)
        self.assertEqual(p.data_offset(10, 23), 103)
        self.assertEqual(p.data_offset(10, 24), 104)
        self.assertEqual(p.data_offset_row_col(104), (10, 24))
        self.assertEqual(p.data_offset(10, 25), 105)
        self.assertEqual(p.data_offset_row_col(105), (10, 25))
        self.assertEqual(p.data_offset_row_col(106), None)
        self.assertEqual(p.data_offset_row_col(107), None)

        self.assertEqual(p.row_text(10, 5), "\t\t\tz")
        self.assertEqual(p.row_text(10, 7), "\t\t\tz")
        self.assertEqual(p.row_text(10, 8), "\t\tz")

    def test_parse_mixed(self):
        test = """ち\t<tab
\tち<
\t<ち
sちome text.>\t<
line\tち\ttabs
\tち
ち\t\t\tz
Здравствуйте
こんにちはtranslate
"""
        self.prefs = app.prefs.Prefs()
        p = self.parser
        self.parser.parse(None, test, self.prefs.grammars["rs"], 0, 99999)
        if 0:
            print("")
            for i, t in enumerate(test.splitlines()):
                print("{}: {}".format(i, repr(t)))
            p.debug_log(print, test)

        self.assertEqual(p.row_count(), 10)

        self.assertEqual(p.row_text(0), "ち\t<tab")
        self.assertEqual(p.row_text(1), "\tち<")
        self.assertEqual(p.row_text(2), "\t<ち")
        self.assertEqual(p.row_text(3), "sちome text.>\t<")
        self.assertEqual(p.row_text(4), "line\tち\ttabs")
        self.assertEqual(p.row_text(5), "\tち")
        self.assertEqual(p.row_text(6), "ち\t\t\tz")
        self.assertEqual(p.row_text(7), "Здравствуйте")
        self.assertEqual(p.row_text(8), "こんにちはtranslate")
        self.assertEqual(p.row_text(9), "")

        self.assertEqual(app.curses_util.char_width("З", 0), 1)
        self.assertEqual(app.curses_util.char_width("こ", 0), 2)
        self.assertEqual(app.curses_util.char_width("ん", 0), 2)
        self.assertEqual(app.curses_util.char_width("に", 0), 2)
        self.assertEqual(p.data_offset(7, 0), 51)
        self.assertEqual(p.data_offset(7, 1), 52)
        self.assertEqual(p.data_offset(7, 2), 53)
        self.assertEqual(p.row_text(7, 0), "Здравствуйте")
        self.assertEqual(p.row_text(7, 1), "дравствуйте")
        self.assertEqual(p.row_text(7, 2), "равствуйте")
        self.assertEqual(p.row_text(7, 3), "авствуйте")
        self.assertEqual(p.row_text(7, 0, -1), "Здравствуйт")
        self.assertEqual(p.row_text(7, 1, -3), "дравству")
        self.assertEqual(p.row_text(7, 2, -5), "равст")
        self.assertEqual(p.row_text(7, 3, -7), "ав")
        self.assertEqual(p.row_text(8, 0), "こんにちはtranslate")
        self.assertEqual(p.row_text(8, 2), "んにちはtranslate")
        self.assertEqual(p.row_text(8, 4), "にちはtranslate")
        self.assertEqual(p.row_text(8, 6), "ちはtranslate")
        self.assertEqual(p.row_text(8, 8), "はtranslate")

        self.assertEqual(p.row_text_and_width(0), ("ち\t<tab", 12))
        self.assertEqual(p.row_text_and_width(1), ("\tち<", 11))
        self.assertEqual(p.row_text_and_width(2), ("\t<ち", 11))
        self.assertEqual(p.row_text_and_width(3), ("sちome text.>\t<", 17))
        self.assertEqual(p.row_text_and_width(4), ("line\tち\ttabs", 20))
        self.assertEqual(p.row_text_and_width(5), ("\tち", 10))
        self.assertEqual(p.row_text_and_width(6), ("ち\t\t\tz", 25))
        self.assertEqual(p.row_text_and_width(7), ("Здравствуйте", 12))
        self.assertEqual(p.row_text_and_width(8), ("こんにちはtranslate", 19))
        self.assertEqual(p.row_text_and_width(9), ("", 0))

        self.assertEqual(p.row_width(0), 12)
        self.assertEqual(p.row_width(1), 11)
        self.assertEqual(p.row_width(2), 11)
        self.assertEqual(p.row_width(3), 17)
        self.assertEqual(p.row_width(4), 20)
        self.assertEqual(p.row_width(5), 10)
        self.assertEqual(p.row_width(6), 25)
        self.assertEqual(p.row_width(7), 12)
        self.assertEqual(p.row_width(8), 19)
        self.assertEqual(p.row_width(9), 0)

        self.assertEqual(p.grammar_index_from_row_col(0, 0), 1)
        self.assertEqual(p.grammar_index_from_row_col(0, 7), 2)
        self.assertEqual(p.grammar_index_from_row_col(0, 8), 3)
        self.assertEqual(p.grammar_index_from_row_col(1, 0), 1)

        self.assertEqual(p.next_char_row_col(999999, 0), None)
        # Test "ち\t<tab".
        self.assertEqual(p.next_char_row_col(0, 0), (0, 2))
        self.assertEqual(p.next_char_row_col(0, 1), (0, 2))
        self.assertEqual(p.next_char_row_col(0, 2), (0, 6))
        self.assertEqual(p.next_char_row_col(0, 8), (0, 1))
        self.assertEqual(p.next_char_row_col(0, 11), (0, 1))
        self.assertEqual(p.next_char_row_col(0, 12), (1, -12))
        # Test "ち\t\t\tz".
        self.assertEqual(p.next_char_row_col(6, 0), (0, 2))
        self.assertEqual(p.next_char_row_col(6, 8), (0, 8))
        self.assertEqual(p.next_char_row_col(6, 16), (0, 8))
        self.assertEqual(p.next_char_row_col(6, 25), (1, -25))
        # Test "".
        self.assertEqual(p.next_char_row_col(9, 0), None)

        # Test "ち\t<tab".
        self.assertEqual(p.prior_char_row_col(0, 0), None)
        self.assertEqual(p.prior_char_row_col(0, 1), (0, -1))
        self.assertEqual(p.prior_char_row_col(0, 2), (0, -2))
        self.assertEqual(p.prior_char_row_col(0, 3), (0, -1))
        self.assertEqual(p.prior_char_row_col(0, 7), (0, -5))
        # Test "ち\t\t\tz".
        self.assertEqual(p.prior_char_row_col(6, 1), (0, -1))
        self.assertEqual(p.prior_char_row_col(6, 5), (0, -3))
        self.assertEqual(p.prior_char_row_col(6, 8), (0, -6))
        self.assertEqual(p.prior_char_row_col(6, 9), (0, -1))
        self.assertEqual(p.prior_char_row_col(6, 15), (0, -7))
        self.assertEqual(p.prior_char_row_col(6, 16), (0, -8))
        self.assertEqual(p.prior_char_row_col(6, 17), (0, -1))
        self.assertEqual(p.prior_char_row_col(6, 18), (0, -2))
        self.assertEqual(p.prior_char_row_col(6, 19), (0, -3))
        self.assertEqual(p.prior_char_row_col(6, 20), (0, -4))

        # Test "ち\t<tab".
        self.assertEqual(p.data_offset(0, 0), 0)
        self.assertEqual(p.data_offset(0, 1), 0)
        self.assertEqual(p.data_offset(0, 2), 1)
        self.assertEqual(p.data_offset(0, 3), 1)
        self.assertEqual(p.data_offset(0, 7), 1)
        self.assertEqual(p.data_offset(0, 8), 2)
        self.assertEqual(p.data_offset(0, 9), 3)
        self.assertEqual(p.data_offset(0, 12), 6)
        self.assertEqual(p.data_offset(0, 13), None)
        self.assertEqual(p.data_offset(0, 99), None)
        # Test "\tち<".
        self.assertEqual(p.data_offset(1, 0), 7)
        self.assertEqual(p.data_offset(1, 1), 7)
        self.assertEqual(p.data_offset(1, 2), 7)
        self.assertEqual(p.data_offset(1, 3), 7)
        self.assertEqual(p.data_offset(1, 7), 7)
        self.assertEqual(p.data_offset(1, 8), 8)
        self.assertEqual(p.data_offset(1, 12), None)
        self.assertEqual(p.data_offset(1, 14), None)
        # Test "\t<ち".
        self.assertEqual(p.data_offset(2, 0), 11)
        self.assertEqual(p.data_offset(2, 1), 11)
        self.assertEqual(p.data_offset(2, 2), 11)
        self.assertEqual(p.data_offset(2, 11), 14)
        self.assertEqual(p.data_offset(2, 12), None)
        # Test "sちome text.>\t<".
        # Test "line\tち\ttabs".
        self.assertEqual(p.data_offset(4, 0), 30)
        self.assertEqual(p.data_offset(4, 1), 31)
        self.assertEqual(p.data_offset(4, 2), 32)
        # Test "\tち".
        self.assertEqual(p.data_offset(5, 0), 42)
        self.assertEqual(p.data_offset(5, 1), 42)
        self.assertEqual(p.data_offset(5, 7), 42)
        self.assertEqual(p.data_offset(5, 8), 43)
        # Test "ち\t\t\tz".
        self.assertEqual(p.data_offset(6, 0), 45)
        self.assertEqual(p.data_offset(6, 7), 46)
        self.assertEqual(p.data_offset(6, 8), 47)
        self.assertEqual(p.data_offset(6, 15), 47)
        self.assertEqual(p.data_offset(6, 16), 48)
        self.assertEqual(p.data_offset(6, 17), 48)
        # Test "Здравствуйте".
        # Test "こんにちはtranslate".
        # Test "".

    def test_backspace(self):
        test = """ち\t<tab
\tち<
\t<ち
sちome text.>\t<
line\tち\ttabs
\tち
ち\t\t\tz
Здравствуйте
こんにちはtranslate
"""
        self.prefs = app.prefs.Prefs()
        p = self.parser
        self.assertEqual(p.resumeAtRow, 0)
        self.parser.parse(None, test, self.prefs.grammars["rs"], 0, 99999)
        self.assertEqual(p.resumeAtRow, 10)
        if 0:
            print("")
            for i, t in enumerate(test.splitlines()):
                print("{}: {}".format(i, repr(t)))
            p.debug_log(print, test)
        self.assertEqual(p.data_offset(4, 5), 34)

        self.assertEqual(p.data_offset(4, 5), 34)
        self.assertEqual(p.row_text_and_width(0), ("ち\t<tab", 12))
        self.assertEqual(p.backspace(0, 0), (0, 0))
        self.assertEqual(p.data_offset(4, 5), 34)
        self.assertEqual(p.row_text_and_width(0), ("ち\t<tab", 12))
        self.assertEqual(p.backspace(0, 1), (0, 1))
        self.assertEqual(p.data_offset(4, 5), 34)
        self.assertEqual(p.row_text_and_width(0), ("ち\t<tab", 12))
        self.assertEqual(p.backspace(0, 2), (0, 0))
        self.assertEqual(p.data_offset(4, 5), 33)
        self.assertEqual(p.row_text(0), "\t<tab")
        self.assertEqual(p.row_width(0), 12)
        self.assertEqual(p.row_text_and_width(0), ("\t<tab", 12))
        self.assertEqual(p.prior_char_row_col(0, 0), None)
        self.assertEqual(p.prior_char_row_col(0, 1), (0, -1))
        self.assertEqual(p.prior_char_row_col(0, 2), (0, -2))
        self.assertEqual(p.prior_char_row_col(0, 3), (0, -3))
        self.assertEqual(p.prior_char_row_col(0, 7), (0, -7))
        self.assertEqual(p.prior_char_row_col(0, 8), (0, -8))
        self.assertEqual(p.prior_char_row_col(0, 9), (0, -1))
        self.assertEqual(p.backspace(0, 8), (0, 0))
        self.assertEqual(p.row_text(0), "<tab")
        self.assertEqual(p.backspace(0, 2), (0, 1))
        self.assertEqual(p.row_text(0), "<ab")

        self.assertEqual(p.row_text(4), "line\tち\ttabs")
        self.assertEqual(p.prior_char_row_col(4, 20), (0, -1))
        p.data_offset(4, 19)
        self.assertEqual(p.data_offset(0, 0), 0)
        self.assertEqual(p.data_offset(4, 0), 27)
        self.assertEqual(p.data_offset(4, 3), 30)
        self.assertEqual(p.data_offset(4, 4), 31)
        self.assertEqual(p.data_offset(4, 5), 31)
        self.assertEqual(p.data_offset(4, 7), 31)
        self.assertEqual(p.data_offset(4, 8), 32)
        self.assertEqual(p.data_offset(4, 9), 32)
        self.assertEqual(p.data_offset(4, 10), 33)
        self.assertEqual(p.data_offset(4, 16), 34)
        self.assertEqual(p.data_offset(4, 19), 37)
        self.assertEqual(p.data[p.data_offset(4, 19)], "s")
        self.assertEqual(p.data_offset(4, 20), 38)
        self.assertEqual(p.backspace(4, 20), (4, 19))
        self.assertEqual(p.row_text(4), "line\tち\ttab")
        self.assertEqual(p.backspace(4, 19), (4, 18))
        self.assertEqual(p.row_text(4), "line\tち\tta")
        self.assertEqual(p.backspace(4, 16), (4, 10))
        self.assertEqual(p.row_text(4), "line\tちta")
        self.assertEqual(p.backspace(4, 10), (4, 8))
        self.assertEqual(p.row_text(4), "line\tta")
        self.assertEqual(p.backspace(4, 8), (4, 4))
        self.assertEqual(p.row_text(4), "lineta")
        self.assertEqual(p.backspace(4, 4), (4, 3))
        self.assertEqual(p.row_text(4), "linta")

        self.assertEqual(p.row_text_and_width(3), ("sちome text.>\t<", 17))
        self.assertEqual(p.row_width(3), 17)
        self.assertEqual(p.row_text(5), "\tち")
        self.assertEqual(p.backspace(4, 0), (3, 17))
        self.assertEqual(p.row_text(3), "sちome text.>\t<linta")
        self.assertEqual(p.row_text(4), "\tち")

    def test_delete_char(self):
        test = """ち\t<tab
\tち<
\t<ち
sちome text.>\t<
line\tち\ttabs
\tち
ち\t\t\tz
Здравствуйте
こんにちはtranslate
"""
        self.prefs = app.prefs.Prefs()
        p = self.parser
        self.assertEqual(p.resumeAtRow, 0)
        self.parser.parse(None, test, self.prefs.grammars["rs"], 0, 99999)
        self.assertEqual(p.resumeAtRow, 10)
        if 0:
            print("")
            for i, t in enumerate(test.splitlines()):
                print("{}: {}".format(i, repr(t)))
            p.debug_log(print, test)

        self.assertEqual(p.data_offset(4, 5), 34)
        self.assertEqual(p.row_text_and_width(0), ("ち\t<tab", 12))
        p.delete_char(0, 0)
        self.assertEqual(p.data_offset(4, 5), 33)
        self.assertEqual(p.row_text_and_width(0), ("\t<tab", 12))
        p.delete_char(0, 1)
        self.assertEqual(p.data_offset(4, 5), 32)
        self.assertEqual(p.row_text_and_width(0), ("<tab", 4))
        p.delete_char(0, 2)
        self.assertEqual(p.data_offset(4, 5), 31)
        self.assertEqual(p.row_text(0), "<tb")
        self.assertEqual(p.row_width(0), 3)
        self.assertEqual(p.row_text_and_width(0), ("<tb", 3))
        p.delete_char(0, 8)
        self.assertEqual(p.row_text(0), "<tb")
        p.delete_char(0, 2)
        self.assertEqual(p.row_text(0), "<t")

        self.assertEqual(p.row_text(4), "line\tち\ttabs")
        self.assertEqual(p.prior_char_row_col(4, 20), (0, -1))
        self.assertEqual(p.data[p.data_offset(4, 19)], "s")
        self.assertEqual(p.data_offset(4, 20), 37)
        p.delete_char(4, 19)
        self.assertEqual(p.row_text(4), "line\tち\ttab")
        p.delete_char(4, 18)
        self.assertEqual(p.row_text(4), "line\tち\tta")
        p.delete_char(4, 15)
        self.assertEqual(p.row_text(4), "line\tちta")
        p.delete_char(4, 9)
        self.assertEqual(p.row_text(4), "line\tta")
        p.delete_char(4, 7)
        self.assertEqual(p.row_text(4), "lineta")
        p.delete_char(4, 3)
        self.assertEqual(p.row_text(4), "linta")

        self.assertEqual(p.row_text_and_width(3), ("sちome text.>\t<", 17))
        self.assertEqual(p.row_width(3), 17)
        self.assertEqual(p.row_text(5), "\tち")
        p.delete_char(3, 17)
        self.assertEqual(p.row_text(3), "sちome text.>\t<linta")
        self.assertEqual(p.row_text(4), "\tち")

    def test_delete_range(self):
        test = """ち\t<tab
\tち<
\t<ち
sちome text.>\t<
line\tち\ttabs
\tち
ち\t\t\tz
Здравствуйте
こんにちはtranslate
"""
        self.prefs = app.prefs.Prefs()
        p = self.parser
        self.assertEqual(p.resumeAtRow, 0)
        self.parser.parse(None, test, self.prefs.grammars["rs"], 0, 99999)
        self.assertEqual(p.resumeAtRow, 10)
        if 0:
            print("")
            for i, t in enumerate(test.splitlines()):
                print("{}: {}".format(i, repr(t)))
            p.debug_log(print, test)

        self.assertEqual(p.data_offset(4, 5), 34)
        self.assertEqual(p.row_text_and_width(0), ("ち\t<tab", 12))
        self.assertEqual(p.row_text_and_width(3), ("sちome text.>\t<", 17))
        self.assertEqual(p.row_text_and_width(4), ("line\tち\ttabs", 20))
        p.delete_range(3, 0, 3, 1)
        self.assertEqual(p.data_offset(4, 5), 33)
        self.assertEqual(p.row_text_and_width(3), ("ちome text.>\t<", 17))

    def test_reparse_short(self):
        test = """a⏰
e
"""
        expectedNodes = [
            # (NodeName, begin, prior, visual).
            ("rs", 0, None, 0),
            ("rs", 0, None, 0),
            ("rs", 1, None, 1),
            ("rs", 3, None, 4),
            ("rs", 5, None, 6),
        ]
        expectedRows = [0, 3, 4]
        self.prefs = app.prefs.Prefs()
        p = self.parser
        self.parser.parse(None, test, self.prefs.grammars["rs"], 0, 99999)
        if 0:
            print("")
            for i, t in enumerate(test.splitlines()):
                print("{}: {}".format(i, repr(t)))
            p.debug_log(print, test)

        self.check_parser_nodes(expectedNodes, p.parserNodes)
        self.check_parser_rows(expectedRows, p.rows)
        # Regression test: a reparse should not add nodes.
        self.parser.parse(None, test, self.prefs.grammars["rs"], 3, 4)
        self.parser.parse(None, test, self.prefs.grammars["rs"], 3, 4)
        self.parser.parse(None, test, self.prefs.grammars["rs"], 3, 4)
        self.parser.parse(None, test, self.prefs.grammars["rs"], 3, 4)
        self.check_parser_nodes(expectedNodes, p.parserNodes)
        self.check_parser_rows(expectedRows, p.rows)

    def test_parse_short(self):
        test = """a⏰
e
"""
        self.prefs = app.prefs.Prefs()
        p = self.parser
        self.parser.parse(None, test, self.prefs.grammars["rs"], 0, 99999)
        if 0:
            print("")
            for i, t in enumerate(test.splitlines()):
                print("{}: {}".format(i, repr(t)))
            p.debug_log(print, test)

        self.assertEqual(p.row_count(), 3)

        self.assertEqual(p.row_text(0), "a⏰")
        self.assertEqual(p.row_width(0), 3)
        self.assertEqual(p.row_text(1), "e")
        self.assertEqual(p.data_offset(0, 0), 0)
        self.assertEqual(test[p.data_offset(0, 0)], "a")
        self.assertEqual(p.data_offset(0, 1), 1)
        self.assertEqual(test[p.data_offset(0, 1)], "⏰")
        self.assertEqual(p.data_offset(0, 2), 1)
        self.assertEqual(p.data_offset(0, 3), 2)
        self.assertEqual(test[p.data_offset(0, 3)], "\n")
        self.assertEqual(p.data_offset(0, 4), None)
        self.assertEqual(p.data_offset(1, 0), 3)
        self.assertEqual(test[p.data_offset(1, 0)], "e")
        self.assertEqual(p.data_offset(1, 1), 4)
        self.assertEqual(test[p.data_offset(1, 1)], "\n")
        self.assertEqual(p.data_offset(1, 2), None)
        self.assertEqual(p.data_offset(1, 3), None)
        self.assertEqual(p.data_offset(2, 0), None)

    def test_insert(self):
        self.prefs = app.prefs.Prefs()
        p = self.parser
        self.assertEqual(p.resumeAtRow, 0)
        self.parser.parse(None, "", self.prefs.grammars["rs"], 0, 99999)
        self.assertEqual(p.resumeAtRow, 1)
        if 0:
            print("")
            for i, t in enumerate(test.splitlines()):
                print("{}: {}".format(i, repr(t)))
            p.debug_log(print, test)

        self.check_parser_nodes(
            [
                ("rs", 0, None, 0),
            ],
            p.parserNodes,
        )
        self.assertEqual(p.data_offset(4, 5), None)
        p.insert(0, 0, "a")
        self.check_parser_nodes(
            [
                ("rs", 0, None, 0),
            ],
            p.parserNodes,
        )
        self.assertEqual(p.row_text_and_width(0), ("a", 1))
        self.check_parser_nodes(
            [
                ("rs", 0, None, 0),
                ("rs", 0, None, 0),
                ("rs", 1, None, 1),
            ],
            p.parserNodes,
        )
        # An insert to an invalid row, col will append to the end.
        p.insert(2, 2, "z")
        self.assertEqual(p.row_count(), 1)
        self.assertEqual(p.row_text_and_width(0), ("az", 2))
        self.check_parser_nodes(
            [
                ("rs", 0, None, 0),
                ("rs", 0, None, 0),
                ("rs", 2, None, 2),
            ],
            p.parserNodes,
        )
        p.insert(0, 0, "ち")
        self.assertEqual(p.row_text_and_width(0), ("ちaz", 4))
        self.check_parser_nodes(
            [
                ("rs", 0, None, 0),
                ("rs", 0, None, 0),
                ("rs", 1, None, 2),
                ("rs", 3, None, 4),
            ],
            p.parserNodes,
        )
        p.insert(0, 2, "b")
        self.assertEqual(p.row_text_and_width(0), ("ちbaz", 5))
        self.check_parser_nodes(
            [
                ("rs", 0, None, 0),
                ("rs", 0, None, 0),
                ("rs", 1, None, 2),
                ("rs", 4, None, 5),
            ],
            p.parserNodes,
        )
        p.insert(0, 0, "x")
        self.assertEqual(p.row_text_and_width(0), ("xちbaz", 6))
        # p.debug_log(print, p.data)
        # self.print_parser_nodes(p.parserNodes)

    def test_data_offset(self):
        test = "xちbaz"
        self.prefs = app.prefs.Prefs()
        p = self.parser
        self.assertEqual(p.resumeAtRow, 0)
        self.parser.parse(None, test, self.prefs.grammars["rs"], 0, 99999)
        self.assertEqual(p.resumeAtRow, 1)

        self.check_parser_nodes(
            [
                ("rs", 0, None, 0),
                ("rs", 0, None, 0),
                ("rs", 1, None, 1),
                ("rs", 2, None, 3),
                ("rs", 5, None, 6),
            ],
            p.parserNodes,
        )
        self.assertEqual(p.data[p.data_offset(0, 0)], "x")
        self.assertEqual(p.data[p.data_offset(0, 1)], "ち")
        self.assertEqual(p.data[p.data_offset(0, 2)], "ち")
        self.assertEqual(p.data[p.data_offset(0, 3)], "b")
        self.assertEqual(p.data[p.data_offset(0, 4)], "a")
        self.assertEqual(p.data[p.data_offset(0, 5)], "z")

        test = "xちbちaz"
        self.parser.parse(None, test, self.prefs.grammars["rs"], 0, 99999)
        self.check_parser_nodes(
            [
                ("rs", 0, None, 0),
                ("rs", 0, None, 0),
                ("rs", 1, None, 1),
                ("rs", 2, None, 3),
                ("rs", 3, None, 4),
                ("rs", 4, None, 6),
                ("rs", 6, None, 8),
            ],
            p.parserNodes,
        )
        self.assertEqual(p.data[p.data_offset(0, 0)], "x")
        self.assertEqual(p.data[p.data_offset(0, 1)], "ち")
        self.assertEqual(p.data[p.data_offset(0, 2)], "ち")
        self.assertEqual(p.data[p.data_offset(0, 3)], "b")
        self.assertEqual(p.data[p.data_offset(0, 4)], "ち")
        self.assertEqual(p.data[p.data_offset(0, 5)], "ち")
        self.assertEqual(p.data[p.data_offset(0, 6)], "a")
        self.assertEqual(p.data[p.data_offset(0, 7)], "z")

        test = "ちbち"
        self.parser.parse(None, test, self.prefs.grammars["rs"], 0, 99999)
        self.check_parser_nodes(
            [
                ("rs", 0, None, 0),
                ("rs", 0, None, 0),
                ("rs", 1, None, 2),
                ("rs", 2, None, 3),
                ("rs", 3, None, 5),
            ],
            p.parserNodes,
        )
        self.assertEqual(p.data[p.data_offset(0, 0)], "ち")
        self.assertEqual(p.data[p.data_offset(0, 1)], "ち")
        self.assertEqual(p.data[p.data_offset(0, 2)], "b")
        self.assertEqual(p.data[p.data_offset(0, 3)], "ち")
        self.assertEqual(p.data[p.data_offset(0, 4)], "ち")

    if 0:

        def test_profile_parse(self):
            profile = cProfile.Profile()
            parser = app.parser.Parser()
            path = "app/actions.py"
            data = open(path).read()
            fileType = self.prefs.get_file_type(path)
            grammar = self.prefs.get_grammar(fileType)

            profile.enable()
            parser.parse(data, grammar, 0, sys.maxsize)
            profile.disable()

            output = io.StringIO()
            stats = pstats.Stats(profile, stream=output).sort_stats("cumulative")
            stats.print_stats()
            print(output.getvalue())
