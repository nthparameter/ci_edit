# -*- coding: utf-8 -*-
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

import unittest

import app.log
import app.ci_program
import app.selectable

class SelectableTestCases(unittest.TestCase):
    def setUp(self):
        self.selectable = app.selectable.Selectable(app.ci_program.CiProgram())
        app.log.shouldWritePrintLog = True

    def tearDown(self):
        self.selectable = None

    def test_default_values(self):
        selectable = self.selectable
        self.assertEqual(selectable.selection(), (0, 0, 0, 0))

    def test_selection_none(self):
        selectable = self.selectable
        selectable.parser.data = "oneTwo\n\nfive"
        selectable.parse_document()
        selectable.selectionMode = app.selectable.SELECTION_NONE
        self.assertEqual(selectable.extend_selection(), (0, 0, 0, 0, 0))
        selectable.pen_col = 3
        self.assertEqual(selectable.extend_selection(), (0, 0, 0, 0, 0))

    def test_selection_all(self):
        selectable = self.selectable
        selectable.parser.data = "oneTwo\n\nfive"
        selectable.parse_document()
        selectable.selectionMode = app.selectable.SELECTION_ALL
        self.assertEqual(selectable.extend_selection(), (2, 4, 0, 0, 0))
        selectable.pen_col = 3
        self.assertEqual(selectable.extend_selection(), (2, 1, 0, 0, 0))

    def test_selection_block(self):
        selectable = self.selectable
        selectable.parser.data = "oneTwo\n\nfive"
        selectable.parse_document()
        selectable.selectionMode = app.selectable.SELECTION_BLOCK
        self.assertEqual(selectable.extend_selection(), (0, 0, 0, 0, 0))
        selectable.pen_col = 3
        self.assertEqual(selectable.extend_selection(), (0, 0, 0, 0, 0))

    def test_selection_character(self):
        selectable = self.selectable
        selectable.parser.data = "oneTwo\n\nfive"
        selectable.parse_document()
        selectable.selectionMode = app.selectable.SELECTION_CHARACTER
        self.assertEqual(selectable.extend_selection(), (0, 0, 0, 0, 0))
        selectable.pen_col = 3
        self.assertEqual(selectable.extend_selection(), (0, 0, 0, 0, 0))

    def test_selection_line(self):
        selectable = self.selectable
        selectable.parser.data = "one two\n\nfive"
        selectable.parse_document()
        selectable.pen_row = 1
        selectable.selectionMode = app.selectable.SELECTION_LINE
        app.log.debug("selectable.extend_selection", selectable.extend_selection())
        self.assertEqual(selectable.extend_selection(), (0, 0, 0, 0, 0))
        selectable.pen_row = 3
        selectable.pen_col = 3
        selectable.marker_row = 1
        selectable.marker_col = 4
        self.assertEqual(selectable.extend_selection(), (0, -3, 0, -4, 0))

    def test_selection_word(self):
        selectable = self.selectable
        selectable.parser.data = "one two\nSeveral test words\nfive"
        selectable.parse_document()
        selectable.selectionMode = app.selectable.SELECTION_WORD
        selectable.pen_row = 1
        selectable.pen_col = 2
        self.assertEqual(selectable.extend_selection(), (0, 5, 0, 0, 0))
        selectable.pen_row = 1
        selectable.pen_col = 9
        selectable.marker_col = 2
        self.assertEqual(selectable.extend_selection(), (0, 3, 0, -2, 0))

    # Deletion tests.

    def test_deletion_none(self):
        selectable = self.selectable
        selectable.parser.data = "one two\nSeveral test words.\nfive"
        selectable.parse_document()
        selectable.selectionMode = app.selectable.SELECTION_NONE
        selectable.pen_col = 1
        selectable.do_delete_selection()
        self.assertEqual(selectable.parser.data, "one two\nSeveral test words.\nfive")

    def test_deletion_all(self):
        selectable = self.selectable

        def apply_selection(args):
            selectable.pen_row += args[0]
            selectable.pen_col += args[1]
            selectable.marker_row += args[2]
            selectable.marker_col += args[3]
            selectable.selectionMode += args[4]

        self.assertEqual(selectable.selection(), (0, 0, 0, 0))
        selectable.parser.data = "oneTwo\n\nfive"
        selectable.parse_document()
        self.assertEqual(selectable.selection(), (0, 0, 0, 0))
        selectable.selectionMode = app.selectable.SELECTION_ALL
        self.assertEqual(selectable.extend_selection(), (2, 4, 0, 0, 0))
        selectable.pen_col = 3
        self.assertEqual(selectable.extend_selection(), (2, 1, 0, 0, 0))

        apply_selection(selectable.extend_selection())
        self.assertEqual(selectable.selection(), (2, 4, 0, 0))
        selectable.do_delete_selection()
        self.assertEqual(selectable.parser.data, "")

        selectable.insert_lines_at(
            0, 0, ("wx", "", "yz"), app.selectable.SELECTION_ALL
        )
        self.assertEqual(selectable.parser.data, "wx\n\nyz")

    def test_deletion_block(self):
        selectable = self.selectable
        selectable.parser.data = "oneTwo\n\nfive"
        selectable.parse_document()
        selectable.selectionMode = app.selectable.SELECTION_BLOCK
        self.assertEqual(selectable.extend_selection(), (0, 0, 0, 0, 0))
        selectable.marker_row = 0
        selectable.marker_col = 1
        selectable.pen_row = 2
        selectable.pen_col = 3
        self.assertEqual(selectable.extend_selection(), (0, 0, 0, 0, 0))
        self.assertEqual(selectable.parser.data, "oneTwo\n\nfive")
        selectable.do_delete_selection()
        self.assertEqual(selectable.parser.data, "oTwo\n\nfe")
        selectable.insert_lines_at(
            0, 1, ("wx", "", "yz"), app.selectable.SELECTION_BLOCK
        )
        self.assertEqual(selectable.parser.data, "owxTwo\n\nfyze")

    def test_deletion_character(self):
        selectable = self.selectable
        selectable.parser.data = "one two\nSeveral test words.\nfive"
        selectable.parse_document()
        selectable.selectionMode = app.selectable.SELECTION_CHARACTER
        selectable.pen_col = 1
        selectable.do_delete_selection()
        self.assertEqual(selectable.parser.data, "ne two\nSeveral test words.\nfive")
        selectable.marker_col = 3
        selectable.do_delete_selection()
        self.assertEqual(selectable.parser.data, "ntwo\nSeveral test words.\nfive")
        selectable.pen_row = 1
        selectable.pen_col = 1
        selectable.do_delete_selection()
        self.assertEqual(selectable.parser.data, "ntweveral test words.\nfive")

    def test_deletion_line(self):
        selectable = self.selectable
        selectable.parser.data = "one two\n\nfive"
        selectable.parse_document()
        selectable.pen_row = 1
        selectable.selectionMode = app.selectable.SELECTION_LINE
        app.log.debug("selectable.extend_selection", selectable.extend_selection())
        self.assertEqual(selectable.extend_selection(), (0, 0, 0, 0, 0))
        selectable.pen_row = 3
        selectable.pen_col = 3
        selectable.marker_row = 1
        selectable.marker_col = 4
        self.assertEqual(selectable.extend_selection(), (0, -3, 0, -4, 0))

    def test_deletion_word(self):
        selectable = self.selectable
        selectable.parser.data = "one two\nSeveral test words.\nfive"
        selectable.parse_document()
        selectable.selectionMode = app.selectable.SELECTION_WORD
        selectable.pen_row = 1
        selectable.pen_col = 2
        self.assertEqual(selectable.extend_selection(), (0, 5, 0, 0, 0))
        selectable.pen_row = 1
        selectable.pen_col = 9
        selectable.marker_col = 2
        self.assertEqual(selectable.extend_selection(), (0, 3, 0, -2, 0))

    def test_unicode(self):
        selectable = self.selectable
        selectable.parser.data = "one two\n😀Several test words.\nfive"
        selectable.parse_document()
        selectable.selectionMode = app.selectable.SELECTION_CHARACTER
        selectable.pen_row = 1
        selectable.pen_col = 0
        self.assertEqual(selectable.marker_col, 0)
        selectable.pen_col = 2
        self.assertEqual(selectable.marker_col, 0)

if __name__ == "__main__":
    unittest.main()
