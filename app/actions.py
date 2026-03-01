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

# For Python 2to3 support.

try:
    unicode
except NameError:
    unicode = str
    unichr = chr

import bisect
import curses.ascii
import difflib
import binascii
import io
import os
import re
import sys
import time
import traceback
import warnings

import app.bookmark
import app.config
import app.curses_util
import app.history
import app.log
import app.mutator
import app.parser
import app.selectable

class Actions(app.mutator.Mutator):
    """This base class to TextBuffer handles the text manipulation (without
    handling the drawing/rendering of the text)."""

    def __init__(self, program):
        app.mutator.Mutator.__init__(self, program)
        self.view = None
        self.bookmarks = []
        self.file_extension = None
        self.next_bookmark_color_pos = 0
        self.file_encoding = None
        self.file_history = {}
        self.last_checksum = None
        self.last_file_size = 0
        self.file_filter("")

    def get_matching_bracket_row_col(self):
        """Gives the position of the bracket which matches
        the bracket at the current position of the cursor.

        Args:
          None.

        Returns:
          None if matching bracket isn't found.
          Position (int row, int col) of the matching bracket otherwise.
        """
        if self.parser.row_count() <= self.pen_row:
            return None
        text, width = self.parser.row_text_and_width(self.pen_row)
        if width <= self.pen_col:
            return None
        ch = app.curses_util.char_at_column(self.pen_col, text)

        def search_forward(openCh, closeCh):
            count = 1
            textCol = self.pen_col + 1
            for row in range(self.pen_row, self.parser.row_count()):
                line = self.parser.row_text(row)
                if row == self.pen_row:
                    line = app.curses_util.rendered_sub_str(line, textCol)
                else:
                    textCol = 0
                for match in re.finditer(
                    "(\\" + openCh + ")|(\\" + closeCh + ")", line
                ):
                    if match.group() == openCh:
                        count += 1
                    else:
                        count -= 1
                    if count == 0:
                        textCol += app.curses_util.column_width(line[: match.start()])
                        return row, textCol

        def search_back(closeCh, openCh):
            count = -1
            for row in range(self.pen_row, -1, -1):
                line = self.parser.row_text(row)
                if row == self.pen_row:
                    line = app.curses_util.rendered_sub_str(line, 0, self.pen_col)
                found = [
                    i
                    for i in re.finditer(
                        "(\\" + openCh + ")|(\\" + closeCh + ")", line
                    )
                ]
                for match in reversed(found):
                    if match.group() == openCh:
                        count += 1
                    else:
                        count -= 1
                    if count == 0:
                        textCol = app.curses_util.column_width(line[: match.start()])
                        return row, textCol

        matcher = {
            "(": (")", search_forward),
            "[": ("]", search_forward),
            "{": ("}", search_forward),
            ")": ("(", search_back),
            "]": ("[", search_back),
            "}": ("{", search_back),
        }
        look = matcher.get(ch)
        if look:
            return look[1](ch, look[0])

    def jump_to_matching_bracket(self):
        matchingBracketRowCol = self.get_matching_bracket_row_col()
        if matchingBracketRowCol is not None:
            self.pen_row = matchingBracketRowCol[0]
            self.pen_col = matchingBracketRowCol[1]

    def perform_delete(self):
        if self.selectionMode != app.selectable.SELECTION_NONE:
            text = self.get_selected_text()
            if text:
                if self.selectionMode == app.selectable.SELECTION_BLOCK:
                    upper = min(self.pen_row, self.marker_row)
                    left = min(self.pen_col, self.marker_col)
                    lower = max(self.pen_row, self.marker_row)
                    right = max(self.pen_col, self.marker_col)
                    self.cursor_move_and_mark(
                        upper - self.pen_row,
                        left - self.pen_col,
                        lower - self.marker_row,
                        right - self.marker_col,
                        0,
                    )
                elif self.pen_row > self.marker_row or (
                    self.pen_row == self.marker_row and self.pen_col > self.marker_col
                ):
                    self.swap_pen_and_marker()
                self.redo_add_change(("ds", text))
                self.redo()
            self.selection_none()

    def _perform_delete_range(self, upperRow, upperCol, lowerRow, lowerCol):
        if upperRow == self.pen_row == lowerRow:
            if upperCol < self.pen_col:
                col = upperCol - self.pen_col
                if lowerCol <= self.pen_col:
                    col = upperCol - lowerCol
                self.cursor_move(0, col)
        elif upperRow <= self.pen_row < lowerRow:
            self.cursor_move(upperRow - self.pen_row, upperCol - self.pen_col)
        elif self.pen_row == lowerRow:
            col = upperCol - lowerCol
            self.cursor_move(upperRow - self.pen_row, col)
        self.redo_add_change(
            (
                "dr",
                (upperRow, upperCol, lowerRow, lowerCol),
                self.get_text(upperRow, upperCol, lowerRow, lowerCol),
            )
        )
        self.redo()

    def get_bookmark_color(self):
        """Returns a new color by cycling through a predefined section of the
        color palette.

        Args:
          None.

        Returns:
          A color (int) for a new bookmark.
        """
        if self.program.prefs.startup["numColors"] == 8:
            goodColorIndices = [1, 2, 3, 4, 5]
        else:
            goodColorIndices = [97, 98, 113, 117, 127]
        self.next_bookmark_color_pos = (self.next_bookmark_color_pos + 1) % len(
            goodColorIndices
        )
        return goodColorIndices[self.next_bookmark_color_pos]

    def data_to_bookmark(self):
        """Convert bookmark data to a bookmark.

        Args:
          None.

        Returns:
          A Bookmark object containing its range and the current state of the
          cursor and selection mode. The bookmark is also assigned a color,
          which is used to determine the color of the bookmark's line numbers.
        """
        bookmarkData = {
            "marker": (self.marker_row, self.marker_col),
            "pen": (self.pen_row, self.pen_col),
            "selectionMode": self.selectionMode,
            "colorIndex": self.get_bookmark_color(),
        }
        upperRow, _, lowerRow, _ = self.start_and_end()
        return app.bookmark.Bookmark(upperRow, lowerRow, bookmarkData)

    def bookmark_add(self):
        """Adds a bookmark at the cursor's location. If multiple lines are
        selected, all existing bookmarks in those lines are overwritten with the
        new bookmark.

        Args:
          None.

        Returns:
          None.
        """
        newBookmark = self.data_to_bookmark()
        self.bookmark_remove()
        bisect.insort_right(self.bookmarks, newBookmark)

    def bookmark_goto(self, bookmark):
        """Goes to the bookmark that is passed in.

        Args:
          bookmark (Bookmark): The bookmark you want to jump to. This object is
                               defined in bookmark.py

        Returns:
          None.
        """
        bookmarkData = bookmark.data
        pen_row, pen_col = bookmarkData["pen"]
        marker_row, marker_col = bookmarkData["marker"]
        selectionMode = bookmarkData["selectionMode"]
        self.cursor_move_and_mark(
            pen_row - self.pen_row,
            pen_col - self.pen_col,
            marker_row - self.marker_row,
            marker_col - self.marker_col,
            selectionMode - self.selectionMode,
        )
        self.scroll_to_optimal_scroll_position()

    def bookmark_next(self):
        """Goes to the closest bookmark after the cursor.

        Args:
          None.

        Returns:
          None.
        """
        if not len(self.bookmarks):
            self.set_message("No bookmarks to jump to")
            return
        _, _, lowerRow, _ = self.start_and_end()
        needle = app.bookmark.Bookmark(lowerRow + 1, lowerRow + 1, {})
        index = bisect.bisect_left(self.bookmarks, needle)
        self.bookmark_goto(self.bookmarks[index % len(self.bookmarks)])

    def bookmark_prior(self):
        """Goes to the closest bookmark before the cursor.

        Args:
          None.

        Returns:
          None.
        """
        if not len(self.bookmarks):
            self.set_message("No bookmarks to jump to")
            return
        upperRow, _, _, _ = self.start_and_end()
        needle = app.bookmark.Bookmark(upperRow, upperRow, {})
        index = bisect.bisect_left(self.bookmarks, needle)
        self.bookmark_goto(self.bookmarks[index - 1])

    def bookmark_remove(self):
        """Removes bookmarks in all selected lines.

        Args:
          None.

        Returns:
          (boolean) Whether any bookmarks were removed.
        """
        upperRow, _, lowerRow, _ = self.start_and_end()
        rangeList = self.bookmarks
        needle = app.bookmark.Bookmark(upperRow, lowerRow, {})
        # Find the left-hand index.
        begin = bisect.bisect_left(rangeList, needle)
        if begin and needle.begin <= rangeList[begin - 1].end:
            begin -= 1
        # Find the right-hand index.
        low = begin
        index = begin
        high = len(rangeList)
        offset = needle.end
        while True:
            index = (high + low) // 2
            if low == high:
                break
            if offset >= rangeList[index].end:
                low = index + 1
            elif offset < rangeList[index].begin:
                high = index
            else:
                index += 1
                break
        if begin == index:
            return False
        self.bookmarks = rangeList[:begin] + rangeList[index:]
        return True

    def backspace(self):
        # app.log.info('backspace', self.pen_row > self.marker_row)
        if self.selectionMode != app.selectable.SELECTION_NONE:
            self.perform_delete()
        elif self.pen_col == 0:
            if self.pen_row > 0:
                self.cursor_left()
                self.join_lines()
        else:
            offset = self.parser.data_offset(self.pen_row, self.pen_col)
            if offset is None:
                change = ("b", self.parser.data[-1])
            else:
                change = ("b", self.parser.data[offset - 1])
            self.redo_add_change(change)
            self.redo()

    def backspace_word(self):
        if self.selectionMode != app.selectable.SELECTION_NONE:
            self.perform_delete()
        elif self.pen_col == 0:
            if self.pen_row > 0:
                self.cursor_left()
                self.join_lines()
        else:
            line = self.parser.row_text(self.pen_row)
            colDelta = self.get_cursor_move_left_to(app.regex.RE_WORD_BOUNDARY)[1][1]
            change = ("bw", line[self.pen_col + colDelta : self.pen_col])
            self.redo_add_change(change)
            self.redo()

    def carriage_return(self):
        self.perform_delete()
        grammar = self.parser.grammar_at(self.pen_row, self.pen_col)
        self.redo_add_change(("n", 1, self.get_cursor_move(1, -self.pen_col)))
        self.redo()
        if not self.program.prefs.editor["autoIndent"]:
            self.update_basic_scroll_position()
            return
        grammarIndent = grammar.get("indent")
        if grammarIndent:
            # TODO(): Hack fix. Reconsider how it should be done.
            self.do_parse(self.pen_row - 1, self.pen_row + 1)
            line, width = self.parser.row_text_and_width(self.pen_row - 1)
            # commonIndent = len(self.program.prefs.editor['indentation'])
            nonSpace = 0
            while nonSpace < width and line[nonSpace].isspace():
                nonSpace += 1
            indent = line[:nonSpace]
            if width:
                lastChar = line.rstrip()[-1:]
                if lastChar == ":":
                    indent += grammarIndent
                elif lastChar in ["[", "{"]:
                    # Check whether a \n is inserted in {} or []; if so add
                    # another line and unindent the closing character.
                    split_line = self.parser.row_text(self.pen_row)
                    if split_line[self.pen_col : self.pen_col + 1] in ["]", "}"]:
                        self.redo_add_change(("i", indent))
                        self.redo()
                        self.cursor_move(0, -len(indent))
                        self.redo()
                        self.redo_add_change(("n", 1, self.get_cursor_move(0, 0)))
                        self.redo()
                    indent += grammarIndent
                elif lastChar in ["=", "+", "-", "/", "*"]:
                    indent += grammarIndent * 2
                # Good idea or bad idea?
                # elif indent >= 2 and line.lstrip()[:6] == 'return':
                #  indent -= grammarIndent
                elif line.count("(") > line.count(")"):
                    indent += grammarIndent * 2
            if indent:
                self.redo_add_change(("i", indent))
                self.redo()
        self.update_basic_scroll_position()

    def cursor_col_delta(self, toRow):
        if app.config.strict_debug:
            assert isinstance(toRow, int)
            assert 0 <= toRow < self.parser.row_count()
        line, lineLen = self.parser.row_text_and_width(toRow)
        if self.goal_col <= lineLen:
            return app.curses_util.floor_col(self.goal_col, line) - self.pen_col
        else:
            return lineLen - self.pen_col

    def cursor_down(self):
        self.selection_none()
        self.cursor_move_down_or_end()

    def cursor_down_scroll(self):
        self.selection_none()
        self.scroll_down()

    def cursor_left(self):
        self.selection_none()
        self.cursor_move_left()

    def get_cursor_move(self, rowDelta, colDelta):
        if app.config.strict_debug:
            assert isinstance(rowDelta, int)
            assert isinstance(colDelta, int)
        return self.get_cursor_move_and_mark(rowDelta, colDelta, 0, 0, 0)

    def cursor_move(self, rowDelta, colDelta):
        self.cursor_move_and_mark(rowDelta, colDelta, 0, 0, 0)

    def get_cursor_move_and_mark(
        self, rowDelta, colDelta, markRowDelta, markColDelta, selectionModeDelta
    ):
        if app.config.strict_debug:
            assert isinstance(rowDelta, int)
            assert isinstance(colDelta, int)
            assert isinstance(markRowDelta, int)
            assert isinstance(markColDelta, int)
            assert isinstance(selectionModeDelta, int)
        if self.pen_col + colDelta < 0:  # Catch cursor at beginning of line.
            colDelta = -self.pen_col
        self.goal_col = self.pen_col + colDelta
        return (
            "m",
            (rowDelta, colDelta, markRowDelta, markColDelta, selectionModeDelta),
        )

    def cursor_move_and_mark(
        self, rowDelta, colDelta, markRowDelta, markColDelta, selectionModeDelta
    ):
        if app.config.strict_debug:
            assert isinstance(rowDelta, int)
            assert isinstance(colDelta, int)
        change = self.get_cursor_move_and_mark(
            rowDelta, colDelta, markRowDelta, markColDelta, selectionModeDelta
        )
        self.redo_add_change(change)
        self.redo()

    def cursor_move_scroll(self, rowDelta, colDelta, scrollRowDelta, scrollColDelta):
        self.update_scroll_position(scrollRowDelta, scrollColDelta)
        self.redo_add_change(("m", (rowDelta, colDelta, 0, 0, 0)))

    def unused_____cursor_move_down(self):
        if self.pen_row == self.parser.row_count() - 1:
            self.set_message("Bottom of file")
            return
        savedGoal = self.goal_col
        self.cursor_move(1, self.cursor_col_delta(self.pen_row + 1))
        self.goal_col = savedGoal
        self.adjust_horizontal_scroll()

    def cursor_move_down_or_end(self):
        savedGoal = self.goal_col
        if self.pen_row == self.parser.row_count() - 1:
            self.set_message("End of file")
            self.cursor_end_of_line()
        else:
            self.cursor_move(1, self.cursor_col_delta(self.pen_row + 1))
        self.goal_col = savedGoal
        self.adjust_horizontal_scroll()

    def adjust_horizontal_scroll(self):
        if self.view.scrollCol:
            width = self.parser.row_width(self.pen_row)
            if width < self.view.cols:
                # The whole line fits on screen.
                self.view.scrollCol = 0
            elif self.view.scrollCol == self.pen_col and self.pen_col == width:
                self.view.scrollCol = max(0, self.view.scrollCol - self.view.cols // 4)

    def cursor_move_left(self):
        if not self.parser.row_count():
            return
        rowCol = self.parser.prior_char_row_col(self.pen_row, self.pen_col)
        if rowCol is None:
            self.set_message("Top of file")
        else:
            self.cursor_move(*rowCol)

    def cursor_move_right(self):
        if not self.parser.row_count():
            return
        rowCol = self.parser.next_char_row_col(self.pen_row, self.pen_col)
        if rowCol is None:
            self.set_message("Bottom of file")
        else:
            self.cursor_move(*rowCol)

    def unused_____cursor_move_up(self):
        if self.pen_row <= 0:
            self.set_message("Top of file")
            return
        savedGoal = self.goal_col
        lineLen = self.parser.row_width(self.pen_row - 1)
        if self.goal_col <= lineLen:
            self.cursor_move(-1, self.goal_col - self.pen_col)
        else:
            self.cursor_move(-1, lineLen - self.pen_col)
        self.goal_col = savedGoal
        self.adjust_horizontal_scroll()

    def cursor_move_to_begin(self):
        savedGoal = self.goal_col
        self.set_message("Top of file")
        self.cursor_move(-self.pen_row, -self.pen_col)
        self.goal_col = savedGoal
        self.update_basic_scroll_position()

    def cursor_move_up_or_begin(self):
        savedGoal = self.goal_col
        if self.pen_row <= 0:
            self.set_message("Top of file")
            self.cursor_move(0, -self.pen_col)
        else:
            self.cursor_move(-1, self.cursor_col_delta(self.pen_row - 1))
        self.goal_col = savedGoal
        self.adjust_horizontal_scroll()

    def cursor_move_subword_left(self):
        self.selection_none()
        self.do_cursor_move_left_to(app.regex.RE_SUBWORD_BOUNDARY_RVR)

    def cursor_move_subword_right(self):
        self.selection_none()
        self.do_cursor_move_right_to(app.regex.RE_SUBWORD_BOUNDARY_FWD)

    def cursor_move_to(self, row, col):
        pen_row = min(max(row, 0), self.parser.row_count() - 1)
        self.cursor_move(pen_row - self.pen_row, col - self.pen_col)

    def cursor_move_word_left(self):
        self.selection_none()
        self.do_cursor_move_left_to(app.regex.RE_WORD_BOUNDARY)

    def cursor_move_word_right(self):
        self.selection_none()
        self.do_cursor_move_right_to(app.regex.RE_WORD_BOUNDARY)

    def get_cursor_move_left_to(self, boundary):
        if self.pen_col > 0:
            line = self.parser.row_text(self.pen_row)
            pos = self.pen_col
            for segment in re.finditer(boundary, line):
                if segment.start() < pos <= segment.end():
                    pos = segment.start()
                    break
            return self.get_cursor_move(0, pos - self.pen_col)
        elif self.pen_row > 0:
            return self.get_cursor_move(-1, self.parser.row_width(self.pen_row - 1))
        return self.get_cursor_move(0, 0)

    def do_cursor_move_left_to(self, boundary):
        change = self.get_cursor_move_left_to(boundary)
        self.redo_add_change(change)
        self.redo()

    def do_cursor_move_right_to(self, boundary):
        if not self.parser.row_count():
            return
        line, lineWidth = self.parser.row_text_and_width(self.pen_row)
        if self.pen_col < lineWidth:
            pos = self.pen_col
            for segment in re.finditer(boundary, line):
                if segment.start() <= pos < segment.end():
                    pos = segment.end()
                    break
            self.cursor_move(0, pos - self.pen_col)
        elif self.pen_row + 1 < self.parser.row_count():
            self.cursor_move(1, -lineWidth)

    def cursor_right(self):
        self.selection_none()
        self.cursor_move_right()

    def cursor_select_down(self):
        if self.selectionMode == app.selectable.SELECTION_NONE:
            self.selection_character()
        self.cursor_move_down_or_end()

    def cursor_select_down_scroll(self):
        """Move the line below the selection to above the selection."""
        upperRow, _, lowerRow, _ = self.start_and_end()
        if lowerRow + 1 >= self.parser.row_count():
            return
        begin = lowerRow + 1
        end = lowerRow + 2
        to = upperRow
        self.redo_add_change(("ml", (begin, end, to)))
        self.redo()

    def cursor_select_left(self):
        if self.selectionMode == app.selectable.SELECTION_NONE:
            self.selection_character()
        self.cursor_move_left()

    def cursor_select_right(self):
        if self.selectionMode == app.selectable.SELECTION_NONE:
            self.selection_character()
        self.cursor_move_right()

    def cursor_select_subword_left(self):
        if self.selectionMode == app.selectable.SELECTION_NONE:
            self.selection_character()
        self.cursor_move_subword_left()
        self.cursor_move_and_mark(*self.extend_selection())

    def cursor_select_subword_right(self):
        if self.selectionMode == app.selectable.SELECTION_NONE:
            self.selection_character()
        self.cursor_move_subword_right()
        self.cursor_move_and_mark(*self.extend_selection())

    def cursor_select_word_left(self):
        if self.selectionMode == app.selectable.SELECTION_NONE:
            self.selection_character()
        self.do_cursor_move_left_to(app.regex.RE_WORD_BOUNDARY)
        self.cursor_move_and_mark(*self.extend_selection())

    def cursor_select_word_right(self):
        if self.selectionMode == app.selectable.SELECTION_NONE:
            self.selection_character()
        self.do_cursor_move_right_to(app.regex.RE_WORD_BOUNDARY)
        self.cursor_move_and_mark(*self.extend_selection())

    def cursor_select_up(self):
        if self.selectionMode == app.selectable.SELECTION_NONE:
            self.selection_character()
        self.cursor_move_up_or_begin()

    def cursor_select_up_scroll(self):
        """Move the line above the selection to below the selection."""
        upperRow, _, lowerRow, _ = self.start_and_end()
        if upperRow == 0:
            return
        begin = upperRow - 1
        end = upperRow
        to = lowerRow + 1
        self.redo_add_change(("ml", (begin, end, to)))
        self.redo()

    def cursor_end_of_line(self):
        lineLen = self.parser.row_width(self.pen_row)
        self.cursor_move(0, lineLen - self.pen_col)

    def cursor_select_to_start_of_line(self):
        self.selection_character()
        self.cursor_start_of_line()

    def cursor_select_to_end_of_line(self):
        self.selection_character()
        self.cursor_end_of_line()

    def __cursor_page_down(self):
        """Moves the view and cursor down by a page or stops at the bottom of
        the document if there is less than a page left.

        Args:
          None.

        Returns:
          None.
        """
        if self.pen_row == self.parser.row_count() - 1:
            self.set_message("Bottom of file")
            return
        maxRow = self.view.rows
        penRowDelta = maxRow
        scrollRowDelta = maxRow
        numLines = self.parser.row_count()
        if self.pen_row + maxRow >= numLines:
            penRowDelta = numLines - self.pen_row - 1
        if numLines <= maxRow:
            scrollRowDelta = -self.view.scrollRow
        elif numLines <= 2 * maxRow + self.view.scrollRow:
            scrollRowDelta = numLines - self.view.scrollRow - maxRow
        self.cursor_move_scroll(
            penRowDelta,
            self.cursor_col_delta(self.pen_row + penRowDelta),
            scrollRowDelta,
            0,
        )
        self.redo()

    def __cursor_page_up(self):
        """Moves the view and cursor up by a page or stops at the top of the
        document if there is less than a page left.

        Args:
          None.

        Returns:
          None.
        """
        if self.pen_row == 0:
            self.set_message("Top of file")
            return
        maxRow = self.view.rows
        penRowDelta = -maxRow
        scrollRowDelta = -maxRow
        if self.pen_row < maxRow:
            penRowDelta = -self.pen_row
        if self.view.scrollRow + scrollRowDelta < 0:
            scrollRowDelta = -self.view.scrollRow
        cursor_col_delta = self.cursor_col_delta(self.pen_row + penRowDelta)
        self.cursor_move_scroll(penRowDelta, cursor_col_delta, scrollRowDelta, 0)
        self.redo()

    def cursor_select_none_page_down(self):
        """Performs a page down. This function does not select any text and
        removes all existing highlights.

        Args:
          None.

        Returns:
          None.
        """
        self.selection_none()
        self.__cursor_page_down()

    def cursor_select_none_page_up(self):
        """Performs a page up. This function does not select any text and
        removes all existing highlights.

        Args:
          None.

        Returns:
          None.
        """
        self.selection_none()
        self.__cursor_page_up()

    def cursor_select_character_page_down(self):
        """Performs a page down. This function selects all characters between
        the previous and current cursor position.

        Args:
          None.

        Returns:
          None.
        """
        self.selection_character()
        self.__cursor_page_down()

    def cursor_select_character_page_up(self):
        """Performs a page up. This function selects all characters between the
        previous and current cursor position.

        Args:
          None.

        Returns:
          None.
        """
        self.selection_character()
        self.__cursor_page_up()

    def cursor_select_block_page_down(self):
        """Performs a page down. This function sets the selection mode to
        "block.".

        Args:
          None.

        Returns:
          None.
        """
        self.selection_block()
        self.__cursor_page_down()

    def cursor_select_block_page_up(self):
        """Performs a page up. This function sets the selection mode to
        "block.".

        Args:
          None.

        Returns:
          None.
        """
        self.selection_block()
        self.__cursor_page_up()

    def cursor_scroll_to_middle(self):
        maxRow = self.view.rows
        rowDelta = (
            min(
                max(0, self.parser.row_count() - maxRow),
                max(0, self.pen_row - maxRow // 2),
            )
            - self.view.scrollRow
        )
        self.cursor_move_scroll(0, 0, rowDelta, 0)

    def cursor_start_of_line(self):
        self.cursor_move(0, -self.pen_col)

    def cursor_up(self):
        self.selection_none()
        self.cursor_move_up_or_begin()

    def cursor_up_scroll(self):
        self.selection_none()
        self.scroll_up()

    def del_ch(self):
        line = self.parser.row_text(self.pen_row)
        change = ("d", line[self.pen_col : self.pen_col + 1])
        self.redo_add_change(change)
        self.redo()

    def delete(self):
        """Delete character to right of pen i.e. Del key."""
        if self.selectionMode != app.selectable.SELECTION_NONE:
            self.perform_delete()
        elif self.pen_col == self.parser.row_width(self.pen_row):
            if self.pen_row + 1 < self.parser.row_count():
                self.join_lines()
        else:
            self.del_ch()

    def delete_to_end_of_line(self):
        line, lineWidth = self.parser.row_text_and_width(self.pen_row)
        if self.pen_col == lineWidth:
            if self.pen_row + 1 < self.parser.row_count():
                self.join_lines()
        else:
            change = ("d", line[self.pen_col :])
            self.redo_add_change(change)
            self.redo()

    def edit_copy(self):
        text = self.get_selected_text()
        if len(text):
            data = "\n".join(text)
            self.program.clipboard.copy(data)
            if len(text) == 1:
                self.set_message(f"copied {len(text[0])} characters")
            else:
                self.set_message(f"copied {len(text)} lines")

    def edit_cut(self):
        self.edit_copy()
        self.perform_delete()

    def edit_paste(self):
        data = self.program.clipboard.paste()
        if not isinstance(data, unicode) and hasattr(data, "decode"):
            data = data.decode("utf-8")
        if data is not None:
            self.edit_paste_data(data)
        else:
            app.log.info("clipboard empty")

    def edit_paste_data(self, data):
        self.edit_paste_lines(tuple(data.split("\n")))

    def edit_paste_lines(self, clip):
        if self.selectionMode != app.selectable.SELECTION_NONE:
            self.perform_delete()
        self.redo_add_change(("v", clip))
        self.redo()
        rowDelta = len(clip) - 1
        if rowDelta == 0:
            endCol = self.pen_col + app.curses_util.column_width(clip[0])
        else:
            endCol = app.curses_util.column_width(clip[-1])
        self.cursor_move(rowDelta, endCol - self.pen_col)

    def edit_redo(self):
        """Undo a set of redo nodes."""
        self.redo()
        if not self.is_selection_in_view():
            self.scroll_to_optimal_scroll_position()

    def edit_undo(self):
        """Undo a set of redo nodes."""
        self.undo()
        if not self.is_selection_in_view():
            self.scroll_to_optimal_scroll_position()

    def file_filter(self, data):
        self.parser.data = data
        self.saved_at_redo_index = self.redoIndex

    def file_load(self):
        app.log.info("file_load", self.full_path)
        inputFile = None
        self.is_read_only = os.path.isfile(self.full_path) and not os.access(
            self.full_path, os.W_OK
        )
        if not os.path.exists(self.full_path):
            data = ""
            self.set_message("Creating new file")
        else:
            try:
                inputFile = open(self.full_path)
                data = unicode(inputFile.read())
                self.file_encoding = inputFile.encoding
                self.set_message("Opened existing file")
                self.is_binary = False
            except Exception as e:
                # app.log.info(unicode(e))
                try:
                    inputFile = open(self.full_path, "rb")
                    if 1:
                        binary_data = inputFile.read()
                        long_hex = binascii.hexlify(binary_data).decode("utf-8")
                        hex_list = []
                        i = 0
                        width = 32
                        while i < len(long_hex):
                            hex_list.append(long_hex[i : i + width] + "\n")
                            i += width
                        data = "".join(hex_list)
                    else:
                        data = inputFile.read()
                    self.is_binary = True
                    self.file_encoding = None
                    app.log.info("Opened file as a binary file")
                    self.set_message("Opened file as a binary file")
                except Exception as e:
                    app.log.info(unicode(e))
                    app.log.info("error opening file", self.full_path)
                    self.set_message("error opening file", self.full_path)
                    return
            self.file_stat = os.stat(self.full_path)
        self.relativePath = os.path.relpath(self.full_path, os.getcwd())
        app.log.info("full_path", self.full_path)
        app.log.info("cwd", os.getcwd())
        app.log.info("relativePath", self.relativePath)
        self.file_filter(data)
        if inputFile:
            inputFile.close()
        self.determine_file_type()

    def _determine_root_grammar(self, name, extension):
        if extension == "" and self.parser.row_count() > 0:
            line = self.parser.row_text(0)
            if line.startswith("#!"):
                if "python" in line:
                    extension = ".py"
                elif "bash" in line:
                    extension = ".sh"
                elif "node" in line:
                    extension = ".js"
                elif "sh" in line:
                    extension = ".sh"
        if self.file_extension != extension:
            self.file_extension = extension
            self.parser.resumeAtRow = 0
        self.file_type = self.program.prefs.get_file_type(name + extension)
        return self.program.prefs.get_grammar(self.file_type)

    def determine_file_type(self):
        self.root_grammar = self._determine_root_grammar(
            *os.path.splitext(self.full_path)
        )
        self.parse_grammars()

        # Restore all user history.
        self.restore_user_history()

    def replace_lines(self, clip):
        self.selection_all()
        self.edit_paste_lines(tuple(clip))

    def restore_user_history(self):
        """This function restores all stored history of the file into the
        TextBuffer object. If there does not exist a stored history of the file,
        it will initialize the variables to default values.

        Args:
          None.

        Returns:
          None.
        """
        # Restore the file history.
        self.file_history = self.program.history.get_file_history(
            self.full_path, self.parser.data
        )

        # Restore all positions and values of variables.
        self.pen_row, self.pen_col = self.file_history.setdefault("pen", (0, 0))
        # Need to initialize goal_col since we set the cursor position directly
        # instead of performing a chain of redoes (which sets goal_col).
        self.goal_col = self.pen_col
        # Do not restore the scroll position here because the view may not be
        # set. the scroll position is handled in the InputWindow.set_text_buffer.
        # self.view.scrollRow, self.view.scrollCol =
        #     self.file_history.setdefault(
        #     'scroll', (0, 0))
        self.do_selection_mode(
            self.file_history.setdefault("selectionMode", app.selectable.SELECTION_NONE)
        )
        self.marker_row, self.marker_col = self.file_history.setdefault("marker", (0, 0))
        if self.program.prefs.editor["saveUndo"]:
            self.redo_chain = self.file_history.setdefault("redoChainCompound", [])
            self.saved_at_redo_index = self.file_history.setdefault(
                "savedAtRedoIndexCompound", 0
            )
            self.tempChange = self.file_history.setdefault("tempChange", None)
            self.redoIndex = self.saved_at_redo_index
            self.old_redo_index = self.saved_at_redo_index
        if app.config.strict_debug:
            assert self.pen_row < self.parser.row_count(), self.pen_row
            assert self.marker_row < self.parser.row_count(), self.marker_row

        # Restore file bookmarks
        self.bookmarks = self.file_history.setdefault("bookmarks", [])

        # Store the file's info.
        self.last_checksum, self.last_file_size = app.history.get_file_info(self.full_path)

    def update_basic_scroll_position(self):
        """Sets scrollRow, scrollCol to the closest values that the view's
        position must be in order to see the cursor.

        Args:
          None.

        Returns:
          None.
        """
        if self.view is None:
            return
        # Row.
        maxRow = self.view.rows
        if self.view.scrollRow > self.pen_row:
            self.view.scrollRow = self.pen_row
        elif self.pen_row >= self.view.scrollRow + maxRow:
            self.view.scrollRow = self.pen_row - maxRow + 1
        # Column.
        maxCol = self.view.cols
        if self.view.scrollCol > self.pen_col:
            self.view.scrollCol = self.pen_col
        elif self.pen_col >= self.view.scrollCol + maxCol:
            self.view.scrollCol = self.pen_col - maxCol + 1

    def scroll_to_optimal_scroll_position(self):
        """Put the selection in the 'optimal' position in the view. What is
        optimal is defined by the "optimalCursorRow" and "optimalCursorCol"
        preferences.

        Args:
          None.

        Returns:
          A tuple of (scrollRow, scrollCol) representing where the view's
          optimal position should be.
        """
        if self.view is None:
            return
        top, left, bottom, right = self.start_and_end()
        # Row.
        maxRows = self.view.rows
        scrollRow = self.view.scrollRow
        height = bottom - top + 1
        extraRows = maxRows - height
        if extraRows > 0:
            optimalRowRatio = self.program.prefs.editor["optimalCursorRow"]
            scrollRow = max(
                0,
                min(
                    self.parser.row_count() - 1,
                    top - int(optimalRowRatio * (maxRows - 1)),
                ),
            )
        else:
            scrollRow = top
        # Column.
        maxCols = self.view.cols
        scrollCol = self.view.scrollCol
        length = right - left + 1
        extraCols = maxCols - length
        if extraCols > 0:
            if right < maxCols:
                scrollCol = 0
            else:
                optimalColRatio = self.program.prefs.editor["optimalCursorCol"]
                scrollCol = max(
                    0, min(right, left - int(optimalColRatio * (maxCols - 1)))
                )
        else:
            scrollCol = left
        self.view.scrollRow = scrollRow
        self.view.scrollCol = scrollCol

    def is_selection_in_view(self):
        """If there is no selection, checks if the cursor is in the view.

        Args:
          None.

        Returns:
          True if selection is in view. Otherwise, False.
        """
        return self.is_in_view(*self.start_and_end())

    def is_in_view(self, top, left, bottom, right):
        """Determine if the rectangle is visible in the view. Returns:

        True if selection is in view. Otherwise, False.
        """
        if self.view is None:
            return False
        horizontally = (
            self.view.scrollCol <= left and right < self.view.scrollCol + self.view.cols
        )
        vertically = (
            self.view.scrollRow <= top and bottom < self.view.scrollRow + self.view.rows
        )
        return horizontally and vertically

    def fence_redo_chain(self):
        self.redo_add_change(("f",))
        self.redo()

    def file_write(self):
        # Preload the message with an error that should be overwritten.
        self.set_message("Error saving file")
        self.is_read_only = not os.access(self.full_path, os.W_OK)
        self.fence_redo_chain()
        try:
            try:
                if self.program.prefs.editor["onSaveStripTrailingSpaces"]:
                    self.strip_trailing_white_space()
                    self.compound_change_push()
                # Save user data that applies to read-only files into history.
                self.file_history["path"] = self.full_path
                self.file_history["pen"] = (self.pen_row, self.pen_col)
                if self.view is not None:
                    self.file_history["scroll"] = (
                        self.view.scrollRow,
                        self.view.scrollCol,
                    )
                self.file_history["marker"] = (self.marker_row, self.marker_col)
                self.file_history["selectionMode"] = self.selectionMode
                self.file_history["bookmarks"] = self.bookmarks
                if self.is_binary:
                    removeWhitespace = {
                        ord(" "): None,
                        ord("\n"): None,
                        ord("\r"): None,
                        ord("\t"): None,
                    }
                    outputData = binascii.unhexlify(
                        self.parser.data.translate(removeWhitespace)
                    )
                    outputFile = open(self.full_path, "wb+")
                elif self.file_encoding is None:
                    outputData = self.parser.data
                    outputFile = open(self.full_path, "w+", encoding="UTF-8")
                else:
                    outputData = self.parser.data
                    outputFile = open(
                        self.full_path, "w+", encoding=self.file_encoding
                    )
                outputFile.seek(0)
                outputFile.truncate()
                outputFile.write(outputData)
                outputFile.close()
                # Save user data that applies to writable files.
                self.saved_at_redo_index = self.redoIndex
                if self.program.prefs.editor["saveUndo"]:
                    self.file_history["redoChainCompound"] = self.redo_chain
                    self.file_history[
                        "savedAtRedoIndexCompound"
                    ] = self.saved_at_redo_index
                    self.file_history["tempChange"] = self.tempChange
                self.program.history.save_user_history(
                    (self.full_path, self.last_checksum, self.last_file_size),
                    self.file_history,
                )
                # Store the file's new info
                self.last_checksum, self.last_file_size = app.history.get_file_info(
                    self.full_path
                )
                self.file_stat = os.stat(self.full_path)
                # If we're writing this file for the first time, self.is_read_only
                # will still be True (from when it didn't exist).
                self.is_read_only = False
                self.set_message("File saved")
            except Exception as e:
                color = self.program.prefs.color.get("status_line_error")
                if self.is_read_only:
                    self.set_message(
                        "Permission error. Try modifying in sudo mode.", color=color
                    )
                else:
                    self.set_message(
                        "Error writing file. The file did not save properly.",
                        color=color,
                    )
                app.log.error("error writing file")
                app.log.exception(e)
        except Exception:
            app.log.info("except had exception")
        self.determine_file_type()

    def select_text(self, row, col, length, mode):
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            assert isinstance(length, int)
            assert isinstance(mode, int)
        row = max(0, min(row, self.parser.row_count() - 1))
        row_width = self.parser.row_width(row)
        col = max(0, min(col, row_width))
        endCol = col + length
        inView = self.is_in_view(row, endCol, row, endCol)
        self.do_selection_mode(app.selectable.SELECTION_NONE)
        self.cursor_move(row - self.pen_row, endCol - self.pen_col)
        self.do_selection_mode(mode)
        self.cursor_move(0, -length)
        if not inView:
            self.scroll_to_optimal_scroll_position()

    def find(self, searchFor, direction=0):
        """direction is -1 for find_prior, 0 for at pen, 1 for find_next."""
        if app.config.strict_debug:
            assert isinstance(searchFor, unicode)
            assert isinstance(direction, int)
        app.log.info(searchFor, direction)
        if not len(searchFor):
            self.find_re = None
            self.do_selection_mode(app.selectable.SELECTION_NONE)
            return
        editorPrefs = self.program.prefs.editor
        flags = 0
        flags |= editorPrefs.get("findIgnoreCase") and re.IGNORECASE or 0
        flags |= editorPrefs.get("findMultiLine") and re.MULTILINE or 0
        flags |= editorPrefs.get("findLocale") and re.LOCALE or 0
        flags |= editorPrefs.get("findDotAll") and re.DOTALL or 0
        flags |= editorPrefs.get("findVerbose") and re.VERBOSE or 0
        flags |= editorPrefs.get("findUnicode") and re.UNICODE or 0
        if not editorPrefs.get("findUseRegex"):
            searchFor = re.escape(searchFor)
        if editorPrefs.get("findWholeWord"):
            searchFor = r"\b%s\b" % searchFor
        # app.log.info(searchFor, flags)
        with warnings.catch_warnings():
            # Ignore future warning with '[[' regex.
            warnings.simplefilter("ignore")
            # The saved re is also used for highlighting.
            self.find_re = re.compile(searchFor, flags)
            self.find_back_re = re.compile(
                f"{searchFor}(?!.*{searchFor}.*)", flags
            )
        self.find_current_pattern(direction)

    def replace_found(self, replaceWith):
        """direction is -1 for find_prior, 0 for at pen, 1 for find_next."""
        if app.config.strict_debug:
            assert isinstance(replaceWith, unicode)
        if not self.find_re:
            return
        if self.program.prefs.editor.get("findUseRegex"):
            toReplace = "\n".join(self.get_selected_text())
            try:
                toReplace = self.find_re.sub(replaceWith, toReplace)
            except re.error as e:
                # TODO(dschuyler): This is stomped by another set_message().
                self.set_message(str(e))
            self.edit_paste_data(toReplace)
        else:
            self.edit_paste_data(replaceWith)

    def find_plain_text(self, text):
        searchFor = re.escape(text)
        self.find_re = re.compile("()^" + searchFor)
        self.find_current_pattern(0)

    def find_replace_flags(self, tokens):
        """Map letters in |tokens| to re flags."""
        flags = re.MULTILINE
        if "i" in tokens:
            flags |= re.IGNORECASE
        if "l" in tokens:
            # Affects \w, \W, \b, \B.
            flags |= re.LOCALE
        if "m" in tokens:
            # Affects ^, $.
            flags |= re.MULTILINE
        if "s" in tokens:
            # Affects ..
            flags |= re.DOTALL
        if "x" in tokens:
            # Affects whitespace and # comments.
            flags |= re.VERBOSE
        if "" in tokens:
            # Affects \w, \W, \b, \B.
            flags |= re.UNICODE
        if 0:
            tokens = re.sub("[ilmsxu]", "", tokens)
            if len(tokens):
                self.set_message("unknown regex flags " + tokens)
        return flags

    def find_replace(self, cmd):
        """Replace (substitute) text using regex in entire document.

        In a command such as `substitute/a/b/flags`, the `substitute` should
        already be removed. The remaining |cmd| of `/a/b/flags` implies a
        separator of '/' since that is the first character. The values between
        separators are:
          - 'a': search string (regex)
          - 'b': replacement string (may contain back references into the regex)
          - 'flags': regex flags string to be parsed by |find_replace_flags()|.
        """
        if not len(cmd):
            return
        separator = cmd[0]
        splitCmd = cmd.split(separator, 3)
        if len(splitCmd) < 4:
            self.set_message("An exchange needs three " + separator + " separators")
            return
        _, find, replace, flags = splitCmd
        data = self.find_replace_text(find, replace, flags, self.parser.data)
        self.apply_document_update(data)

    def find_replace_text(self, find, replace, flags, text):
        flags = self.find_replace_flags(flags)
        return re.sub(find, replace, text, flags=flags)

    def apply_document_update(self, data):
        lines = self.doDataToLines(self.parser.data)
        diff = difflib.ndiff(lines, self.doDataToLines(data))
        ndiff = []
        counter = 0
        for i in diff:
            if i[0] != " ":
                if counter:
                    ndiff.append(counter)
                    counter = 0
                if i[0] in ["+", "-"]:
                    ndiff.append(i)
            else:
                counter += 1
        if counter:
            ndiff.append(counter)
        if len(ndiff) == 1 and type(ndiff[0]) is type(0):
            # Nothing was changed. The only entry is a 'skip these lines'
            self.set_message("No matches found")
            return
        ndiff = tuple(ndiff)
        if 0:
            for i in ndiff:
                app.log.info(i)
        self.redo_add_change(("ld", ndiff))
        self.redo()

    def find_current_pattern(self, direction):
        localRe = self.find_re
        offset = self.pen_col + direction
        if direction < 0:
            localRe = self.find_back_re
        if localRe is None:
            app.log.info("localRe is None")
            return
        # Check part of current line.
        text = self.parser.row_text(self.pen_row)
        if direction >= 0:
            text = text[offset:]
        else:
            text = text[: self.pen_col]
            offset = 0
        # app.log.info('find() searching', repr(text))
        found = localRe.search(text)
        rowFound = self.pen_row
        if not found:
            offset = 0
            row_count = self.parser.row_count()
            # To end of file.
            if direction >= 0:
                theRange = range(self.pen_row + 1, row_count)
            else:
                theRange = range(self.pen_row - 1, -1, -1)
            for i in theRange:
                found = localRe.search(self.parser.row_text(i))
                if found:
                    if 0:
                        for k in found.regs:
                            app.log.info("AAA", k[0], k[1])
                        app.log.info("b found on line", i, repr(found))
                    rowFound = i
                    break
            if not found:
                # Wrap around to the opposite side of the file.
                self.set_message("Find wrapped around.")
                if direction >= 0:
                    theRange = range(self.pen_row)
                else:
                    theRange = range(row_count - 1, self.pen_row, -1)
                for i in theRange:
                    found = localRe.search(self.parser.row_text(i))
                    if found:
                        rowFound = i
                        break
                if not found:
                    # Check the rest of the current line
                    if direction >= 0:
                        text = self.parser.row_text(self.pen_row)
                    else:
                        text = self.parser.row_text(self.pen_row)[self.pen_col :]
                        offset = self.pen_col
                    found = localRe.search(text)
                    rowFound = self.pen_row
        if found:
            # app.log.info('c found on line', rowFound, repr(found.regs))
            start = found.regs[0][0]
            end = found.regs[0][1]
            self.select_text(
                rowFound,
                offset + start,
                end - start,
                app.selectable.SELECTION_CHARACTER,
            )
            return
        app.log.info("find not found")
        self.do_selection_mode(app.selectable.SELECTION_NONE)

    def find_again(self):
        """Find the current pattern, searching down the document."""
        self.find_current_pattern(1)

    def find_back(self):
        """Find the current pattern, searching up the document."""
        self.find_current_pattern(-1)

    def find_next(self, searchFor):
        """Find a new pattern, searching down the document."""
        self.find(searchFor, 1)

    def find_prior(self, searchFor):
        """Find a new pattern, searching up the document."""
        self.find(searchFor, -1)

    def indent(self):
        grammar = self.parser.grammar_at(self.pen_row, self.pen_col)
        indentation = (
            grammar.get("indent") or self.program.prefs.editor["indentation"]
        )
        indentationLength = len(indentation)
        if self.selectionMode == app.selectable.SELECTION_NONE:
            self.vertical_insert(self.pen_row, self.pen_row, self.pen_col, indentation)
        else:
            self.indent_lines()
        self.cursor_move_and_mark(0, indentationLength, 0, indentationLength, 0)

    def indent_lines(self):
        """Indents all selected lines.

        Do not use for when the selection mode is SELECTION_NONE since
        marker_row/marker_col currently do not get updated alongside
        pen_row/pen_col.
        """
        col = 0
        row = min(self.marker_row, self.pen_row)
        endRow = max(self.marker_row, self.pen_row)
        indentation = self.program.prefs.editor["indentation"]
        self.vertical_insert(row, endRow, col, indentation)

    def vertical_delete(self, row, endRow, col, text):
        self.redo_add_change(("vd", (text, row, endRow, col)))
        self.redo()
        if row <= self.marker_row <= endRow:
            self.cursor_move_and_mark(0, 0, 0, -len(text), 0)
        if row <= self.pen_row <= endRow:
            self.cursor_move_and_mark(0, -len(text), 0, 0, 0)

    def vertical_insert(self, row, endRow, col, text):
        self.redo_add_change(("vi", (text, row, endRow, col)))
        self.redo()

    def insert(self, text):
        if app.config.strict_debug:
            assert isinstance(text, unicode)
        self.perform_delete()
        self.redo_add_change(("i", text))
        self.redo()
        self.update_basic_scroll_position()

    def insert_printable(self, ch, meta):
        # app.log.info(ch, meta)
        if ch is app.curses_util.BRACKETED_PASTE:
            self.edit_paste_data(meta)
        elif ch is app.curses_util.UNICODE_INPUT:
            self.insert(meta)
        elif type(ch) is int and curses.ascii.isprint(ch):
            self.insert(unichr(ch))

    def insert_printable_with_pairing(self, ch, meta):
        # app.log.info(ch, meta)
        if type(ch) is int and curses.ascii.isprint(ch):
            if self.program.prefs.editor["autoInsertClosingCharacter"]:
                pairs = {
                    ord("'"): "'",
                    ord('"'): '"',
                    ord("("): ")",
                    ord("{"): "}",
                    ord("["): "]",
                }
                skips = pairs.values()
                mate = pairs.get(ch)
                nextChr = self.parser.char_at(self.pen_row, self.pen_col)
                if unichr(ch) in skips and unichr(ch) == nextChr:
                    self.cursor_move(0, 1)
                elif mate is not None and (nextChr is None or nextChr.isspace()):
                    self.insert(unichr(ch) + mate)
                    self.compound_change_push()
                    self.cursor_move(0, -1)
                else:
                    self.insert(unichr(ch))
            else:
                self.insert(unichr(ch))
        elif ch is app.curses_util.BRACKETED_PASTE:
            self.edit_paste_data(meta)
        elif ch is app.curses_util.UNICODE_INPUT:
            self.insert(meta)

    def join_lines(self):
        """join the next line onto the current line."""
        self.redo_add_change(("j",))
        self.redo()

    def marker_place(self):
        self.redo_add_change(
            (
                "m",
                (0, 0, self.pen_row - self.marker_row, self.pen_col - self.marker_col, 0),
            )
        )
        self.redo()

    def mouse_click(self, paneRow, paneCol, shift, ctrl, alt):
        if 0:
            if ctrl:
                app.log.info("click at", paneRow, paneCol)
                self.view.present_modal(self.view.contextMenu, paneRow, paneCol)
                return
        if shift:
            if alt:
                self.selection_block()
            else:
                self.selection_character()
        else:
            self.selection_none()
        self.mouse_release(paneRow, paneCol, shift, ctrl, alt)

    def mouse_double_click(self, paneRow, paneCol, shift, ctrl, alt):
        app.log.info("double click", paneRow, paneCol)
        row = self.view.scrollRow + paneRow
        if row < self.parser.row_count() and self.parser.row_width(row):
            self.select_word_at(row, self.view.scrollCol + paneCol)

    def mouse_moved(self, paneRow, paneCol, shift, ctrl, alt):
        app.log.info(" mouse_moved", paneRow, paneCol, shift, ctrl, alt)
        if alt:
            self.selection_block()
        elif self.selectionMode == app.selectable.SELECTION_NONE:
            self.selection_character()
        self.mouse_release(paneRow, paneCol, shift, ctrl, alt)

    def mouse_release(self, paneRow, paneCol, shift, ctrl, alt):
        app.log.info(" mouse release", paneRow, paneCol)
        if not self.parser.row_count():
            return
        virtualRow = self.view.scrollRow + paneRow
        row_count = self.parser.row_count()
        if virtualRow >= row_count:
            # Off the bottom of document.
            lastLine = row_count - 1
            self.cursor_move(
                lastLine - self.pen_row, self.parser.row_width(lastLine) - self.pen_col
            )
            return
        row = max(0, min(virtualRow, row_count))
        col = max(0, self.view.scrollCol + paneCol)
        if self.selectionMode == app.selectable.SELECTION_BLOCK:
            self.cursor_move_and_mark(
                0, 0, row - self.marker_row, col - self.marker_col, 0
            )
            return
        marker_row = 0
        # If not block selection, restrict col to the chars on the line.
        row_width = self.parser.row_width(row)
        col = min(col, row_width)
        # Adjust the marker column delta when the pen and marker positions
        # cross over each other.
        marker_col = 0
        if self.selectionMode == app.selectable.SELECTION_LINE:
            if self.pen_row + 1 == self.marker_row and row > self.pen_row:
                marker_row = -1
            elif self.pen_row == self.marker_row + 1 and row < self.pen_row:
                marker_row = 1
        elif self.selectionMode == app.selectable.SELECTION_WORD:
            if self.pen_row == self.marker_row:
                if row == self.pen_row:
                    if self.pen_col > self.marker_col and col < self.marker_col:
                        marker_col = 1
                    elif self.pen_col < self.marker_col and col >= self.marker_col:
                        marker_col = -1
                else:
                    if row < self.pen_row and self.pen_col > self.marker_col:
                        marker_col = 1
                    elif row > self.pen_row and self.pen_col < self.marker_col:
                        marker_col = -1
            elif row == self.marker_row:
                if col < self.marker_col and row < self.pen_row:
                    marker_col = 1
                elif col >= self.marker_col and row > self.pen_row:
                    marker_col = -1
        self.cursor_move_and_mark(
            row - self.pen_row, col - self.pen_col, marker_row, marker_col, 0
        )
        if self.selectionMode == app.selectable.SELECTION_LINE:
            self.cursor_move_and_mark(*self.extend_selection())
        elif self.selectionMode == app.selectable.SELECTION_WORD:
            if self.pen_row < self.marker_row or (
                self.pen_row == self.marker_row and self.pen_col < self.marker_col
            ):
                self.cursor_select_word_left()
            elif paneCol < row_width:
                self.cursor_select_word_right()

    def mouse_triple_click(self, paneRow, paneCol, shift, ctrl, alt):
        app.log.info("triple click", paneRow, paneCol)
        self.mouse_release(paneRow, paneCol, shift, ctrl, alt)
        self.select_line_at(self.view.scrollRow + paneRow)

    def scroll_window(self, rows, cols):
        self.cursor_move_scroll(rows, self.cursor_col_delta(self.pen_row - rows), -1, 0)
        self.redo()

    def mouse_wheel_down(self, shift, ctrl, alt):
        if not shift:
            self.selection_none()
        if self.program.prefs.editor["naturalScrollDirection"]:
            self.scroll_up()
        else:
            self.scroll_down()

    def scroll_up(self):
        if self.view.scrollRow == 0:
            self.set_message("Top of file")
            return
        maxRow = self.view.rows
        cursorDelta = 0
        if self.pen_row >= self.view.scrollRow + maxRow - 2:
            cursorDelta = self.view.scrollRow + maxRow - 2 - self.pen_row
        self.update_scroll_position(-1, 0)
        if self.view.hasCaptiveCursor:
            self.cursor_move_scroll(
                cursorDelta, self.cursor_col_delta(self.pen_row + cursorDelta), 0, 0
            )
            self.redo()

    def mouse_wheel_up(self, shift, ctrl, alt):
        if not shift:
            self.selection_none()
        if self.program.prefs.editor["naturalScrollDirection"]:
            self.scroll_down()
        else:
            self.scroll_up()

    def scroll_down(self):
        maxRow = self.view.rows
        if self.view.scrollRow + maxRow >= self.parser.row_count():
            self.set_message("Bottom of file")
            return
        cursorDelta = 0
        if self.pen_row <= self.view.scrollRow + 1:
            cursorDelta = self.view.scrollRow - self.pen_row + 1
        self.update_scroll_position(1, 0)
        if self.view.hasCaptiveCursor:
            self.cursor_move_scroll(
                cursorDelta, self.cursor_col_delta(self.pen_row + cursorDelta), 0, 0
            )
            self.redo()

    def open_file_at_cursor(self):
        """
        Opens the file under cursor.
        """

        def open_file(path):
            textBuffer = self.view.program.buffer_manager.load_text_buffer(path)
            inputWindow = self.view.controller.current_input_window()
            inputWindow.set_text_buffer(textBuffer)
            self.change_to(inputWindow)
            self.set_message(f"Opened file {path}")

        text, linkType = self.parser.grammar_text_at(self.pen_row, self.pen_col)
        if linkType is None:
            self.set_message("Text is not a recognized file.")
            return
        if linkType in ("c<", 'c"'):
            # These link types include the outer quotes or brackets.
            text = text[1:-1]
        # Give the raw text a try (current working directory or a full path).
        if os.access(text, os.R_OK):
            return open_file(text)
        # Try the path in the same directory as the current file.
        path = os.path.join(os.path.dirname(self.full_path), text)
        if os.access(path, os.R_OK):
            return open_file(path)
        # TODO(): try a list of path prefixes. Maybe from project, prefs, build
        # information, or another tool.
        # Ran out of tries.
        self.set_message(f'No readable file "{text}"')

    def next_selection_mode(self):
        nextMode = self.selectionMode + 1
        nextMode %= app.selectable.SELECTION_MODE_COUNT
        self.do_selection_mode(nextMode)
        app.log.info("next_selection_mode", self.selectionMode)

    def no_op(self, ignored):
        pass

    def no_op_default(self, ignored, ignored2=None):
        pass

    def normalize(self):
        self.selection_none()
        self.find_re = None
        self.view.normalize()

    def parse_screen_maybe(self):
        begin = self.parser.resumeAtRow
        end = self.view.scrollRow + self.view.rows + 1
        if end > begin + 100:
            # Call do_parse with an empty range.
            end = begin
        self.do_parse(begin, end)

    def parse_grammars(self):
        if not self.view:
            return
        scrollRow = self.view.scrollRow
        # If there is a gap, leave it to the background parsing.
        if self.parser.resumeAtRow < scrollRow:
            return
        end = self.view.scrollRow + self.view.rows + 1
        self.do_parse(self.parser.resumeAtRow, end)

    def do_selection_mode(self, mode):
        if self.selectionMode != mode:
            self.redo_add_change(
                (
                    "m",
                    (
                        0,
                        0,
                        self.pen_row - self.marker_row,
                        self.pen_col - self.marker_col,
                        mode - self.selectionMode,
                    ),
                )
            )
            self.redo()

    def cursor_select_line(self):
        """This function is used to select the line in which the cursor is in.

        Consecutive calls to this function will select subsequent lines.
        """
        if self.selectionMode != app.selectable.SELECTION_LINE:
            self.selection_line()
        self.select_line_at(self.pen_row)

    def selection_all(self):
        self.do_selection_mode(app.selectable.SELECTION_ALL)
        self.cursor_move_and_mark(*self.extend_selection())

    def selection_block(self):
        self.do_selection_mode(app.selectable.SELECTION_BLOCK)

    def selection_character(self):
        self.do_selection_mode(app.selectable.SELECTION_CHARACTER)

    def selection_line(self):
        self.do_selection_mode(app.selectable.SELECTION_LINE)

    def selection_none(self):
        self.do_selection_mode(app.selectable.SELECTION_NONE)

    def selection_word(self):
        self.do_selection_mode(app.selectable.SELECTION_WORD)

    def select_line_at(self, row):
        """Adds the line with the specified row to the current selection.

        Args:
          row (int): the specified line of text that you want to select.

        Returns:
          None
        """
        row_count = self.parser.row_count()
        if row >= row_count:
            self.selection_none()
            return
        if row + 1 < row_count:
            self.cursor_move_and_mark(
                (row + 1) - self.pen_row,
                -self.pen_col,
                0,
                -self.marker_col,
                app.selectable.SELECTION_LINE - self.selectionMode,
            )
        else:
            self.cursor_move_and_mark(
                row - self.pen_row,
                self.parser.row_width(row) - self.pen_col,
                0,
                -self.marker_col,
                app.selectable.SELECTION_LINE - self.selectionMode,
            )

    def select_word_at(self, row, col):
        """row and col may be from a mouse click and may not actually land in
        the document text."""
        self.select_text(row, col, 0, app.selectable.SELECTION_WORD)
        row_width = self.parser.row_width(row)
        if col < row_width:
            self.cursor_select_word_right()

    def set_view(self, view):
        self.view = view

    def toggle_show_tips(self):
        self.view.toggle_show_tips()

    def split_line(self):
        """split the line into two at current column."""
        self.redo_add_change(("n", (1,)))
        self.redo()
        self.update_basic_scroll_position()

    def swap_pen_and_marker(self):
        self.cursor_move_and_mark(
            self.marker_row - self.pen_row,
            self.marker_col - self.pen_col,
            self.pen_row - self.marker_row,
            self.pen_col - self.marker_col,
            0,
        )

    def test(self):
        self.insert_printable(0x00, None)

    def strip_trailing_white_space(self):
        for i in range(self.parser.row_count()):
            for found in app.regex.RE_END_SPACES.finditer(self.parser.row_text(i)):
                self._perform_delete_range(i, found.regs[0][0], i, found.regs[0][1])

    def unindent(self):
        if self.selectionMode != app.selectable.SELECTION_NONE:
            self.unindent_lines()
        else:
            indentation = self.program.prefs.editor["indentation"]
            indentationLength = len(indentation)
            line = self.parser.row_text(self.pen_row)
            start = self.pen_col - indentationLength
            if indentation == line[start : self.pen_col]:
                self.vertical_delete(self.pen_row, self.pen_row, start, indentation)

    def unindent_lines(self):
        indentation = self.program.prefs.editor["indentation"]
        indentationLength = len(indentation)
        row = min(self.marker_row, self.pen_row)
        endRow = max(self.marker_row, self.pen_row)
        # Collect a run of lines that can be unindented as a group.
        begin = 0
        i = 0
        for i in range(endRow + 1 - row):
            line, lineWidth = self.parser.row_text_and_width(row + i)
            if lineWidth < indentationLength or line[:indentationLength] != indentation:
                if begin < i:
                    # There is a run of lines that should be unindented.
                    self.vertical_delete(row + begin, row + i - 1, 0, indentation)
                # Skip this line (don't unindent).
                begin = i + 1
        if begin <= i:
            # There is one last run of lines that should be unindented.
            self.vertical_delete(row + begin, row + i, 0, indentation)

    def update_scroll_position(self, scrollRowDelta, scrollColDelta):
        """This function updates the view's scroll position using the optional
        scrollRowDelta and scrollColDelta arguments.

        Args:
          scrollRowDelta (int): The number of rows down to move the view.
          scrollColDelta (int): The number of rows right to move the view.

        Returns:
          None
        """
        self.view.scrollRow += scrollRowDelta
        self.view.scrollCol += scrollColDelta
