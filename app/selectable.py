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

import re

import app.config
import app.line_buffer
import app.log
import app.regex

# No selection.
SELECTION_NONE = 0
# Entire document selected.
SELECTION_ALL = 1
# A rectangular block selection.
SELECTION_BLOCK = 2
# Character by character selection.
SELECTION_CHARACTER = 3
# Select whole lines.
SELECTION_LINE = 4
# Select whole words.
SELECTION_WORD = 5
# How many selection modes are there.
SELECTION_MODE_COUNT = 6

SELECTION_MODE_NAMES = [
    "None",
    "All",
    "Block",
    "Char",
    "Line",
    "Word",
]

class Selectable(app.line_buffer.LineBuffer):
    def __init__(self, program):
        app.line_buffer.LineBuffer.__init__(self, program)
        # When a text document is not line wrapped then each row will represent
        # one line in the document, thow rows are zero based and lines are one
        # based. With line wrapping enabled there may be more rows than lines
        # since a line may wrap into multiple rows.
        self.pen_row = 0
        # When a text document contains only ascii characters then each char
        # (character) will represent one column in the text line (col is zero
        # based and the column displayed in the UI is one based). When double
        # wide character are present then a line of text will have more columns
        # than characters.
        # (pen_char is not currently used).
        self.pen_char = 0
        # When a text document contains only ascii characters then each column
        # will represent one column in the text line (col is zero based and
        # column displayed in the UI is one based).
        self.pen_col = 0
        self.marker_row = 0
        self.marker_col = 0
        self.selectionMode = SELECTION_NONE

    def count_selected(self):
        lines = self.get_selected_text()
        chars = len(lines) - 1  # Count carriage returns.
        for line in lines:
            chars += len(line)
        return chars, len(lines)

    def selection(self):
        return (self.pen_row, self.pen_col, self.marker_row, self.marker_col)

    def selection_mode_name(self):
        return SELECTION_MODE_NAMES[self.selectionMode]

    def get_selected_text(self):
        upperRow, upperCol, lowerRow, lowerCol = self.start_and_end()
        return self.get_text(upperRow, upperCol, lowerRow, lowerCol, self.selectionMode)

    def get_text(
        self, upperRow, upperCol, lowerRow, lowerCol, selectionMode=SELECTION_CHARACTER
    ):
        if app.config.strict_debug:
            assert isinstance(upperRow, int)
            assert isinstance(upperCol, int)
            assert isinstance(lowerRow, int)
            assert isinstance(lowerCol, int)
            assert isinstance(selectionMode, int)
            assert upperRow <= lowerRow
            assert upperRow != lowerRow or upperCol <= lowerCol
            assert SELECTION_NONE <= selectionMode < SELECTION_MODE_COUNT
        lines = []
        if selectionMode == SELECTION_BLOCK:
            if lowerRow + 1 < self.parser.row_count():
                lowerRow += 1
            for i in range(upperRow, lowerRow):
                lines.append(self.parser.row_text(i, upperCol, lowerCol))
        elif (
            selectionMode == SELECTION_ALL
            or selectionMode == SELECTION_CHARACTER
            or selectionMode == SELECTION_LINE
            or selectionMode == SELECTION_WORD
        ):
            if upperRow == lowerRow:
                lines.append(self.parser.row_text(upperRow, upperCol, lowerCol))
            else:
                for i in range(upperRow, lowerRow + 1):
                    if i == upperRow:
                        lines.append(self.parser.row_text(i, upperCol))
                    elif i == lowerRow:
                        lines.append(self.parser.row_text(i, 0, lowerCol))
                    else:
                        lines.append(self.parser.row_text(i))
        return tuple(lines)

    def do_delete_selection(self):
        """Call do_delete() with current pen and marker values."""
        upperRow, upperCol, lowerRow, lowerCol = self.start_and_end()
        self.do_delete(upperRow, upperCol, lowerRow, lowerCol)

    def do_delete(self, upperRow, upperCol, lowerRow, lowerCol):
        """Delete characters from (upperRow, upperCol) up to (lowerRow,
        lowerCol) using the current selection mode."""
        if app.config.strict_debug:
            assert isinstance(upperRow, int)
            assert isinstance(upperCol, int)
            assert isinstance(lowerRow, int)
            assert isinstance(lowerCol, int)
            assert upperRow <= lowerRow
            assert upperRow != lowerRow or upperCol <= lowerCol
        if self.selectionMode == SELECTION_BLOCK:
            self.parser.delete_block(upperRow, upperCol, lowerRow, lowerCol)
        elif (
            self.selectionMode == SELECTION_NONE
            or self.selectionMode == SELECTION_ALL
            or self.selectionMode == SELECTION_CHARACTER
            or self.selectionMode == SELECTION_LINE
            or self.selectionMode == SELECTION_WORD
        ):
            self.parser.delete_range(upperRow, upperCol, lowerRow, lowerCol)

    def insert_lines(self, lines):
        if app.config.strict_debug:
            assert isinstance(lines, tuple)
        self.insert_lines_at(self.pen_row, self.pen_col, lines, self.selectionMode)

    def insert_lines_at(self, row, col, lines, selectionMode):
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            assert isinstance(lines, tuple)
            assert isinstance(selectionMode, int)
        if len(lines) <= 1:
            if len(lines) == 0 or len(lines[0]) == 0:
                # Optimization. There's nothing to insert.
                return
        lines = list(lines)
        if selectionMode == SELECTION_BLOCK:
            self.parser.insert_block(row, col, lines)
        elif (
            selectionMode == SELECTION_NONE
            or selectionMode == SELECTION_ALL
            or selectionMode == SELECTION_CHARACTER
            or selectionMode == SELECTION_LINE
            or selectionMode == SELECTION_WORD
        ):
            if len(lines) == 1:
                self.parser.insert(row, col, lines[0])
            else:
                self.parser.insert_lines(row, col, lines)
        else:
            app.log.info("selection mode not recognized", selectionMode)

    def __extend_words(self, upperRow, upperCol, lowerRow, lowerCol):
        """Extends and existing selection to the nearest word boundaries. The
        pen and marker will be extended away from each other. The extension may
        occur in one, both, or neither direction.

        Returns: tuple of (upperCol, lowerCol).
        """
        line = self.parser.row_text(upperRow)
        for segment in re.finditer(app.regex.RE_WORD_BOUNDARY, line):
            if segment.start() <= upperCol < segment.end():
                upperCol = segment.start()
                break
        line = self.parser.row_text(lowerRow)
        for segment in re.finditer(app.regex.RE_WORD_BOUNDARY, line):
            if segment.start() < lowerCol < segment.end():
                lowerCol = segment.end()
                break
        return upperCol, lowerCol

    def extend_selection(self):
        """Expand the current selection to fit the selection mode. E.g. if the
        pen in the middle of a word, selection word will extend the selection to
        the left and right so that the whole word is selected.

        Returns: tuple of (pen_row, pen_col, marker_row, marker_col, selectionMode)
            which are the delta values to accomplish the selection mode.
        """
        if self.selectionMode == SELECTION_NONE:
            return (0, 0, -self.marker_row, -self.marker_col, 0)
        elif self.selectionMode == SELECTION_ALL:
            lowerRow = self.parser.row_count() - 1
            lowerCol = self.parser.row_width(-1)
            return (
                lowerRow - self.pen_row,
                lowerCol - self.pen_col,
                -self.marker_row,
                -self.marker_col,
                0,
            )
        elif self.selectionMode == SELECTION_LINE:
            return (0, -self.pen_col, 0, -self.marker_col, 0)
        elif self.selectionMode == SELECTION_WORD:
            if self.pen_row > self.marker_row or (
                self.pen_row == self.marker_row and self.pen_col > self.marker_col
            ):
                upperCol, lowerCol = self.__extend_words(
                    self.marker_row, self.marker_col, self.pen_row, self.pen_col
                )
                return (0, lowerCol - self.pen_col, 0, upperCol - self.marker_col, 0)
            else:
                upperCol, lowerCol = self.__extend_words(
                    self.pen_row, self.pen_col, self.marker_row, self.marker_col
                )
                return (0, upperCol - self.pen_col, 0, lowerCol - self.marker_col, 0)
        return (0, 0, 0, 0, 0)

    def start_and_end(self):
        """Get the marker and pen pair as the earlier of the two then the later
        of the two. The result accounts for the current selection mode."""
        upperRow = 0
        upperCol = 0
        lowerRow = 0
        lowerCol = 0
        if self.selectionMode == SELECTION_NONE:
            upperRow = self.pen_row
            upperCol = self.pen_col
            lowerRow = self.pen_row
            lowerCol = self.pen_col
        elif self.selectionMode == SELECTION_ALL:
            upperRow = 0
            upperCol = 0
            lowerRow = self.parser.row_count() - 1
            lowerCol = self.parser.row_width(-1)
        elif self.selectionMode == SELECTION_BLOCK:
            upperRow = min(self.marker_row, self.pen_row)
            upperCol = min(self.marker_col, self.pen_col)
            lowerRow = max(self.marker_row, self.pen_row)
            lowerCol = max(self.marker_col, self.pen_col)
        elif (
            self.selectionMode == SELECTION_CHARACTER
            or self.selectionMode == SELECTION_LINE
            or self.selectionMode == SELECTION_WORD
        ):
            upperRow = self.marker_row
            upperCol = self.marker_col
            lowerRow = self.pen_row
            lowerCol = self.pen_col
            if upperRow == lowerRow and upperCol > lowerCol:
                upperCol, lowerCol = lowerCol, upperCol
            elif upperRow > lowerRow:
                upperRow, lowerRow = lowerRow, upperRow
                upperCol, lowerCol = lowerCol, upperCol
        # app.log.detail('start and end', upperRow, upperCol, lowerRow, lowerCol)
        return (upperRow, upperCol, lowerRow, lowerCol)
