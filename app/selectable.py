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

import enum
import re

import app.config
import app.line_buffer
import app.log
import app.regex


class SelectionMode(enum.IntEnum):
    NONE = 0
    ALL = 1
    BLOCK = 2
    CHARACTER = 3
    LINE = 4
    WORD = 5


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
        self.selection_mode = SelectionMode.NONE

    def count_selected(self):
        lines = self.get_selected_text()
        chars = len(lines) - 1  # Count carriage returns.
        for line in lines:
            chars += len(line)
        return chars, len(lines)

    def selection(self):
        return (self.pen_row, self.pen_col, self.marker_row, self.marker_col)

    def selection_mode_name(self):
        return SELECTION_MODE_NAMES[self.selection_mode]

    def get_selected_text(self):
        upper_row, upper_col, lower_row, lower_col = self.start_and_end()
        return self.get_text(upper_row, upper_col, lower_row, lower_col, self.selection_mode)

    def get_text(
        self, upper_row, upper_col, lower_row, lower_col, selection_mode=SelectionMode.CHARACTER
    ):
        if app.config.strict_debug:
            assert isinstance(upper_row, int)
            assert isinstance(upper_col, int)
            assert isinstance(lower_row, int)
            assert isinstance(lower_col, int)
            assert isinstance(selection_mode, int)
            assert upper_row <= lower_row
            assert upper_row != lower_row or upper_col <= lower_col
            assert SelectionMode.NONE <= selection_mode < len(SelectionMode)
        lines = []
        if selection_mode == SelectionMode.BLOCK:
            if lower_row + 1 < self.parser.row_count():
                lower_row += 1
            for i in range(upper_row, lower_row):
                lines.append(self.parser.row_text(i, upper_col, lower_col))
        elif (
            selection_mode == SelectionMode.ALL
            or selection_mode == SelectionMode.CHARACTER
            or selection_mode == SelectionMode.LINE
            or selection_mode == SelectionMode.WORD
        ):
            if upper_row == lower_row:
                lines.append(self.parser.row_text(upper_row, upper_col, lower_col))
            else:
                for i in range(upper_row, lower_row + 1):
                    if i == upper_row:
                        lines.append(self.parser.row_text(i, upper_col))
                    elif i == lower_row:
                        lines.append(self.parser.row_text(i, 0, lower_col))
                    else:
                        lines.append(self.parser.row_text(i))
        return tuple(lines)

    def do_delete_selection(self):
        """Call do_delete() with current pen and marker values."""
        upper_row, upper_col, lower_row, lower_col = self.start_and_end()
        self.do_delete(upper_row, upper_col, lower_row, lower_col)

    def do_delete(self, upper_row, upper_col, lower_row, lower_col):
        """Delete characters from (upper_row, upper_col) up to (lower_row,
        lower_col) using the current selection mode."""
        if app.config.strict_debug:
            assert isinstance(upper_row, int)
            assert isinstance(upper_col, int)
            assert isinstance(lower_row, int)
            assert isinstance(lower_col, int)
            assert upper_row <= lower_row
            assert upper_row != lower_row or upper_col <= lower_col
        if self.selection_mode == SelectionMode.BLOCK:
            self.parser.delete_block(upper_row, upper_col, lower_row, lower_col)
        elif (
            self.selection_mode == SelectionMode.NONE
            or self.selection_mode == SelectionMode.ALL
            or self.selection_mode == SelectionMode.CHARACTER
            or self.selection_mode == SelectionMode.LINE
            or self.selection_mode == SelectionMode.WORD
        ):
            self.parser.delete_range(upper_row, upper_col, lower_row, lower_col)

    def insert_lines(self, lines):
        if app.config.strict_debug:
            assert isinstance(lines, tuple)
        self.insert_lines_at(self.pen_row, self.pen_col, lines, self.selection_mode)

    def insert_lines_at(self, row, col, lines, selection_mode):
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            assert isinstance(lines, tuple)
            assert isinstance(selection_mode, int)
        if len(lines) <= 1:
            if len(lines) == 0 or len(lines[0]) == 0:
                # Optimization. There's nothing to insert.
                return
        lines = list(lines)
        if selection_mode == SelectionMode.BLOCK:
            self.parser.insert_block(row, col, lines)
        elif (
            selection_mode == SelectionMode.NONE
            or selection_mode == SelectionMode.ALL
            or selection_mode == SelectionMode.CHARACTER
            or selection_mode == SelectionMode.LINE
            or selection_mode == SelectionMode.WORD
        ):
            if len(lines) == 1:
                self.parser.insert(row, col, lines[0])
            else:
                self.parser.insert_lines(row, col, lines)
        else:
            app.log.info("selection mode not recognized", selection_mode)

    def __extend_words(self, upper_row, upper_col, lower_row, lower_col):
        """Extends and existing selection to the nearest word boundaries. The
        pen and marker will be extended away from each other. The extension may
        occur in one, both, or neither direction.

        Returns: tuple of (upper_col, lower_col).
        """
        line = self.parser.row_text(upper_row)
        for segment in re.finditer(app.regex.RE_WORD_BOUNDARY, line):
            if segment.start() <= upper_col < segment.end():
                upper_col = segment.start()
                break
        line = self.parser.row_text(lower_row)
        for segment in re.finditer(app.regex.RE_WORD_BOUNDARY, line):
            if segment.start() < lower_col < segment.end():
                lower_col = segment.end()
                break
        return upper_col, lower_col

    def extend_selection(self):
        """Expand the current selection to fit the selection mode. E.g. if the
        pen in the middle of a word, selection word will extend the selection to
        the left and right so that the whole word is selected.

        Returns: tuple of (pen_row, pen_col, marker_row, marker_col, selection_mode)
            which are the delta values to accomplish the selection mode.
        """
        if self.selection_mode == SelectionMode.NONE:
            return (0, 0, -self.marker_row, -self.marker_col, 0)
        elif self.selection_mode == SelectionMode.ALL:
            lower_row = self.parser.row_count() - 1
            lower_col = self.parser.row_width(-1)
            return (
                lower_row - self.pen_row,
                lower_col - self.pen_col,
                -self.marker_row,
                -self.marker_col,
                0,
            )
        elif self.selection_mode == SelectionMode.LINE:
            return (0, -self.pen_col, 0, -self.marker_col, 0)
        elif self.selection_mode == SelectionMode.WORD:
            if self.pen_row > self.marker_row or (
                self.pen_row == self.marker_row and self.pen_col > self.marker_col
            ):
                upper_col, lower_col = self.__extend_words(
                    self.marker_row, self.marker_col, self.pen_row, self.pen_col
                )
                return (0, lower_col - self.pen_col, 0, upper_col - self.marker_col, 0)
            else:
                upper_col, lower_col = self.__extend_words(
                    self.pen_row, self.pen_col, self.marker_row, self.marker_col
                )
                return (0, upper_col - self.pen_col, 0, lower_col - self.marker_col, 0)
        return (0, 0, 0, 0, 0)

    def start_and_end(self):
        """Get the marker and pen pair as the earlier of the two then the later
        of the two. The result accounts for the current selection mode."""
        upper_row = 0
        upper_col = 0
        lower_row = 0
        lower_col = 0
        if self.selection_mode == SelectionMode.NONE:
            upper_row = self.pen_row
            upper_col = self.pen_col
            lower_row = self.pen_row
            lower_col = self.pen_col
        elif self.selection_mode == SelectionMode.ALL:
            upper_row = 0
            upper_col = 0
            lower_row = self.parser.row_count() - 1
            lower_col = self.parser.row_width(-1)
        elif self.selection_mode == SelectionMode.BLOCK:
            upper_row = min(self.marker_row, self.pen_row)
            upper_col = min(self.marker_col, self.pen_col)
            lower_row = max(self.marker_row, self.pen_row)
            lower_col = max(self.marker_col, self.pen_col)
        elif (
            self.selection_mode == SelectionMode.CHARACTER
            or self.selection_mode == SelectionMode.LINE
            or self.selection_mode == SelectionMode.WORD
        ):
            upper_row = self.marker_row
            upper_col = self.marker_col
            lower_row = self.pen_row
            lower_col = self.pen_col
            if upper_row == lower_row and upper_col > lower_col:
                upper_col, lower_col = lower_col, upper_col
            elif upper_row > lower_row:
                upper_row, lower_row = lower_row, upper_row
                upper_col, lower_col = lower_col, upper_col
        # app.log.detail('start and end', upper_row, upper_col, lower_row, lower_col)
        return (upper_row, upper_col, lower_row, lower_col)
