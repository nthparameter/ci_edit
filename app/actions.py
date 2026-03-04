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
from app.selectable import SelectionMode

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

        def search_forward(open_ch, close_ch):
            count = 1
            text_col = self.pen_col + 1
            for row in range(self.pen_row, self.parser.row_count()):
                line = self.parser.row_text(row)
                if row == self.pen_row:
                    line = app.curses_util.rendered_sub_str(line, text_col)
                else:
                    text_col = 0
                for match in re.finditer(
                    "(\\" + open_ch + ")|(\\" + close_ch + ")", line
                ):
                    if match.group() == open_ch:
                        count += 1
                    else:
                        count -= 1
                    if count == 0:
                        text_col += app.curses_util.column_width(line[: match.start()])
                        return row, text_col

        def search_back(close_ch, open_ch):
            count = -1
            for row in range(self.pen_row, -1, -1):
                line = self.parser.row_text(row)
                if row == self.pen_row:
                    line = app.curses_util.rendered_sub_str(line, 0, self.pen_col)
                found = [
                    i
                    for i in re.finditer(
                        "(\\" + open_ch + ")|(\\" + close_ch + ")", line
                    )
                ]
                for match in reversed(found):
                    if match.group() == open_ch:
                        count += 1
                    else:
                        count -= 1
                    if count == 0:
                        text_col = app.curses_util.column_width(line[: match.start()])
                        return row, text_col

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
        matching_bracket_row_col = self.get_matching_bracket_row_col()
        if matching_bracket_row_col is not None:
            self.pen_row = matching_bracket_row_col[0]
            self.pen_col = matching_bracket_row_col[1]

    def perform_delete(self):
        if self.selection_mode != SelectionMode.NONE:
            text = self.get_selected_text()
            if text:
                if self.selection_mode == SelectionMode.BLOCK:
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

    def _perform_delete_range(self, upper_row, upper_col, lower_row, lower_col):
        if upper_row == self.pen_row == lower_row:
            if upper_col < self.pen_col:
                col = upper_col - self.pen_col
                if lower_col <= self.pen_col:
                    col = upper_col - lower_col
                self.cursor_move(0, col)
        elif upper_row <= self.pen_row < lower_row:
            self.cursor_move(upper_row - self.pen_row, upper_col - self.pen_col)
        elif self.pen_row == lower_row:
            col = upper_col - lower_col
            self.cursor_move(upper_row - self.pen_row, col)
        self.redo_add_change(
            (
                "dr",
                (upper_row, upper_col, lower_row, lower_col),
                self.get_text(upper_row, upper_col, lower_row, lower_col),
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
        if self.program.prefs.startup["num_colors"] == 8:
            good_color_indices = [1, 2, 3, 4, 5]
        else:
            good_color_indices = [97, 98, 113, 117, 127]
        self.next_bookmark_color_pos = (self.next_bookmark_color_pos + 1) % len(
            good_color_indices
        )
        return good_color_indices[self.next_bookmark_color_pos]

    def data_to_bookmark(self):
        """Convert bookmark data to a bookmark.

        Args:
          None.

        Returns:
          A Bookmark object containing its range and the current state of the
          cursor and selection mode. The bookmark is also assigned a color,
          which is used to determine the color of the bookmark's line numbers.
        """
        bookmark_data = {
            "marker": (self.marker_row, self.marker_col),
            "pen": (self.pen_row, self.pen_col),
            "selection_mode": self.selection_mode,
            "color_index": self.get_bookmark_color(),
        }
        upper_row, _, lower_row, _ = self.start_and_end()
        return app.bookmark.Bookmark(upper_row, lower_row, bookmark_data)

    def bookmark_add(self):
        """Adds a bookmark at the cursor's location. If multiple lines are
        selected, all existing bookmarks in those lines are overwritten with the
        new bookmark.

        Args:
          None.

        Returns:
          None.
        """
        new_bookmark = self.data_to_bookmark()
        self.bookmark_remove()
        bisect.insort_right(self.bookmarks, new_bookmark)

    def bookmark_goto(self, bookmark):
        """Goes to the bookmark that is passed in.

        Args:
          bookmark (Bookmark): The bookmark you want to jump to. This object is
                               defined in bookmark.py

        Returns:
          None.
        """
        bookmark_data = bookmark.data
        pen_row, pen_col = bookmark_data["pen"]
        marker_row, marker_col = bookmark_data["marker"]
        selection_mode = bookmark_data["selection_mode"]
        self.cursor_move_and_mark(
            pen_row - self.pen_row,
            pen_col - self.pen_col,
            marker_row - self.marker_row,
            marker_col - self.marker_col,
            selection_mode - self.selection_mode,
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
        _, _, lower_row, _ = self.start_and_end()
        needle = app.bookmark.Bookmark(lower_row + 1, lower_row + 1, {})
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
        upper_row, _, _, _ = self.start_and_end()
        needle = app.bookmark.Bookmark(upper_row, upper_row, {})
        index = bisect.bisect_left(self.bookmarks, needle)
        self.bookmark_goto(self.bookmarks[index - 1])

    def bookmark_remove(self):
        """Removes bookmarks in all selected lines.

        Args:
          None.

        Returns:
          (boolean) Whether any bookmarks were removed.
        """
        upper_row, _, lower_row, _ = self.start_and_end()
        range_list = self.bookmarks
        needle = app.bookmark.Bookmark(upper_row, lower_row, {})
        # Find the left-hand index.
        begin = bisect.bisect_left(range_list, needle)
        if begin and needle.begin <= range_list[begin - 1].end:
            begin -= 1
        # Find the right-hand index.
        low = begin
        index = begin
        high = len(range_list)
        offset = needle.end
        while True:
            index = (high + low) // 2
            if low == high:
                break
            if offset >= range_list[index].end:
                low = index + 1
            elif offset < range_list[index].begin:
                high = index
            else:
                index += 1
                break
        if begin == index:
            return False
        self.bookmarks = range_list[:begin] + range_list[index:]
        return True

    def backspace(self):
        # app.log.info('backspace', self.pen_row > self.marker_row)
        if self.selection_mode != SelectionMode.NONE:
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
        if self.selection_mode != SelectionMode.NONE:
            self.perform_delete()
        elif self.pen_col == 0:
            if self.pen_row > 0:
                self.cursor_left()
                self.join_lines()
        else:
            line = self.parser.row_text(self.pen_row)
            col_delta = self.get_cursor_move_left_to(app.regex.RE_WORD_BOUNDARY)[1][1]
            change = ("bw", line[self.pen_col + col_delta : self.pen_col])
            self.redo_add_change(change)
            self.redo()

    def carriage_return(self):
        self.perform_delete()
        grammar = self.parser.grammar_at(self.pen_row, self.pen_col)
        self.redo_add_change(("n", 1, self.get_cursor_move(1, -self.pen_col)))
        self.redo()
        if not self.program.prefs.editor["auto_indent"]:
            self.update_basic_scroll_position()
            return
        grammar_indent = grammar.get("indent")
        if grammar_indent:
            # TODO(): Hack fix. Reconsider how it should be done.
            self.do_parse(self.pen_row - 1, self.pen_row + 1)
            line, width = self.parser.row_text_and_width(self.pen_row - 1)
            # common_indent = len(self.program.prefs.editor['indentation'])
            nonSpace = 0
            while nonSpace < width and line[nonSpace].isspace():
                nonSpace += 1
            indent = line[:nonSpace]
            if width:
                last_char = line.rstrip()[-1:]
                if last_char == ":":
                    indent += grammar_indent
                elif last_char in ["[", "{"]:
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
                    indent += grammar_indent
                elif last_char in ["=", "+", "-", "/", "*"]:
                    indent += grammar_indent * 2
                # Good idea or bad idea?
                # elif indent >= 2 and line.lstrip()[:6] == 'return':
                #  indent -= grammar_indent
                elif line.count("(") > line.count(")"):
                    indent += grammar_indent * 2
            if indent:
                self.redo_add_change(("i", indent))
                self.redo()
        self.update_basic_scroll_position()

    def cursor_col_delta(self, to_row):
        if app.config.strict_debug:
            assert isinstance(to_row, int)
            assert 0 <= to_row < self.parser.row_count()
        line, line_len = self.parser.row_text_and_width(to_row)
        if self.goal_col <= line_len:
            return app.curses_util.floor_col(self.goal_col, line) - self.pen_col
        else:
            return line_len - self.pen_col

    def cursor_down(self):
        self.selection_none()
        self.cursor_move_down_or_end()

    def cursor_down_scroll(self):
        self.selection_none()
        self.scroll_down()

    def cursor_left(self):
        self.selection_none()
        self.cursor_move_left()

    def get_cursor_move(self, row_delta, col_delta):
        if app.config.strict_debug:
            assert isinstance(row_delta, int)
            assert isinstance(col_delta, int)
        return self.get_cursor_move_and_mark(row_delta, col_delta, 0, 0, 0)

    def cursor_move(self, row_delta, col_delta):
        self.cursor_move_and_mark(row_delta, col_delta, 0, 0, 0)

    def get_cursor_move_and_mark(
        self, row_delta, col_delta, mark_row_delta, mark_col_delta, selection_mode_delta
    ):
        if app.config.strict_debug:
            assert isinstance(row_delta, int)
            assert isinstance(col_delta, int)
            assert isinstance(mark_row_delta, int)
            assert isinstance(mark_col_delta, int)
            assert isinstance(selection_mode_delta, int)
        if self.pen_col + col_delta < 0:  # Catch cursor at beginning of line.
            col_delta = -self.pen_col
        self.goal_col = self.pen_col + col_delta
        return (
            "m",
            (row_delta, col_delta, mark_row_delta, mark_col_delta, selection_mode_delta),
        )

    def cursor_move_and_mark(
        self, row_delta, col_delta, mark_row_delta, mark_col_delta, selection_mode_delta
    ):
        if app.config.strict_debug:
            assert isinstance(row_delta, int)
            assert isinstance(col_delta, int)
        change = self.get_cursor_move_and_mark(
            row_delta, col_delta, mark_row_delta, mark_col_delta, selection_mode_delta
        )
        self.redo_add_change(change)
        self.redo()

    def cursor_move_scroll(self, row_delta, col_delta, scroll_row_delta, scroll_col_delta):
        self.update_scroll_position(scroll_row_delta, scroll_col_delta)
        self.redo_add_change(("m", (row_delta, col_delta, 0, 0, 0)))

    def unused_____cursor_move_down(self):
        if self.pen_row == self.parser.row_count() - 1:
            self.set_message("Bottom of file")
            return
        saved_goal = self.goal_col
        self.cursor_move(1, self.cursor_col_delta(self.pen_row + 1))
        self.goal_col = saved_goal
        self.adjust_horizontal_scroll()

    def cursor_move_down_or_end(self):
        saved_goal = self.goal_col
        if self.pen_row == self.parser.row_count() - 1:
            self.set_message("End of file")
            self.cursor_end_of_line()
        else:
            self.cursor_move(1, self.cursor_col_delta(self.pen_row + 1))
        self.goal_col = saved_goal
        self.adjust_horizontal_scroll()

    def adjust_horizontal_scroll(self):
        if self.view.scroll_col:
            width = self.parser.row_width(self.pen_row)
            if width < self.view.cols:
                # The whole line fits on screen.
                self.view.scroll_col = 0
            elif self.view.scroll_col == self.pen_col and self.pen_col == width:
                self.view.scroll_col = max(0, self.view.scroll_col - self.view.cols // 4)

    def cursor_move_left(self):
        if not self.parser.row_count():
            return
        row_col = self.parser.prior_char_row_col(self.pen_row, self.pen_col)
        if row_col is None:
            self.set_message("Top of file")
        else:
            self.cursor_move(*row_col)

    def cursor_move_right(self):
        if not self.parser.row_count():
            return
        row_col = self.parser.next_char_row_col(self.pen_row, self.pen_col)
        if row_col is None:
            self.set_message("Bottom of file")
        else:
            self.cursor_move(*row_col)

    def unused_____cursor_move_up(self):
        if self.pen_row <= 0:
            self.set_message("Top of file")
            return
        saved_goal = self.goal_col
        line_len = self.parser.row_width(self.pen_row - 1)
        if self.goal_col <= line_len:
            self.cursor_move(-1, self.goal_col - self.pen_col)
        else:
            self.cursor_move(-1, line_len - self.pen_col)
        self.goal_col = saved_goal
        self.adjust_horizontal_scroll()

    def cursor_move_to_begin(self):
        saved_goal = self.goal_col
        self.set_message("Top of file")
        self.cursor_move(-self.pen_row, -self.pen_col)
        self.goal_col = saved_goal
        self.update_basic_scroll_position()

    def cursor_move_up_or_begin(self):
        saved_goal = self.goal_col
        if self.pen_row <= 0:
            self.set_message("Top of file")
            self.cursor_move(0, -self.pen_col)
        else:
            self.cursor_move(-1, self.cursor_col_delta(self.pen_row - 1))
        self.goal_col = saved_goal
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
        line, line_width = self.parser.row_text_and_width(self.pen_row)
        if self.pen_col < line_width:
            pos = self.pen_col
            for segment in re.finditer(boundary, line):
                if segment.start() <= pos < segment.end():
                    pos = segment.end()
                    break
            self.cursor_move(0, pos - self.pen_col)
        elif self.pen_row + 1 < self.parser.row_count():
            self.cursor_move(1, -line_width)

    def cursor_right(self):
        self.selection_none()
        self.cursor_move_right()

    def cursor_select_down(self):
        if self.selection_mode == SelectionMode.NONE:
            self.selection_character()
        self.cursor_move_down_or_end()

    def cursor_select_down_scroll(self):
        """Move the line below the selection to above the selection."""
        upper_row, _, lower_row, _ = self.start_and_end()
        if lower_row + 1 >= self.parser.row_count():
            return
        begin = lower_row + 1
        end = lower_row + 2
        to = upper_row
        self.redo_add_change(("ml", (begin, end, to)))
        self.redo()

    def cursor_select_left(self):
        if self.selection_mode == SelectionMode.NONE:
            self.selection_character()
        self.cursor_move_left()

    def cursor_select_right(self):
        if self.selection_mode == SelectionMode.NONE:
            self.selection_character()
        self.cursor_move_right()

    def cursor_select_subword_left(self):
        if self.selection_mode == SelectionMode.NONE:
            self.selection_character()
        self.cursor_move_subword_left()
        self.cursor_move_and_mark(*self.extend_selection())

    def cursor_select_subword_right(self):
        if self.selection_mode == SelectionMode.NONE:
            self.selection_character()
        self.cursor_move_subword_right()
        self.cursor_move_and_mark(*self.extend_selection())

    def cursor_select_word_left(self):
        if self.selection_mode == SelectionMode.NONE:
            self.selection_character()
        self.do_cursor_move_left_to(app.regex.RE_WORD_BOUNDARY)
        self.cursor_move_and_mark(*self.extend_selection())

    def cursor_select_word_right(self):
        if self.selection_mode == SelectionMode.NONE:
            self.selection_character()
        self.do_cursor_move_right_to(app.regex.RE_WORD_BOUNDARY)
        self.cursor_move_and_mark(*self.extend_selection())

    def cursor_select_up(self):
        if self.selection_mode == SelectionMode.NONE:
            self.selection_character()
        self.cursor_move_up_or_begin()

    def cursor_select_up_scroll(self):
        """Move the line above the selection to below the selection."""
        upper_row, _, lower_row, _ = self.start_and_end()
        if upper_row == 0:
            return
        begin = upper_row - 1
        end = upper_row
        to = lower_row + 1
        self.redo_add_change(("ml", (begin, end, to)))
        self.redo()

    def cursor_end_of_line(self):
        line_len = self.parser.row_width(self.pen_row)
        self.cursor_move(0, line_len - self.pen_col)

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
        max_row = self.view.rows
        pen_row_delta = max_row
        scroll_row_delta = max_row
        num_lines = self.parser.row_count()
        if self.pen_row + max_row >= num_lines:
            pen_row_delta = num_lines - self.pen_row - 1
        if num_lines <= max_row:
            scroll_row_delta = -self.view.scroll_row
        elif num_lines <= 2 * max_row + self.view.scroll_row:
            scroll_row_delta = num_lines - self.view.scroll_row - max_row
        self.cursor_move_scroll(
            pen_row_delta,
            self.cursor_col_delta(self.pen_row + pen_row_delta),
            scroll_row_delta,
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
        max_row = self.view.rows
        pen_row_delta = -max_row
        scroll_row_delta = -max_row
        if self.pen_row < max_row:
            pen_row_delta = -self.pen_row
        if self.view.scroll_row + scroll_row_delta < 0:
            scroll_row_delta = -self.view.scroll_row
        cursor_col_delta = self.cursor_col_delta(self.pen_row + pen_row_delta)
        self.cursor_move_scroll(pen_row_delta, cursor_col_delta, scroll_row_delta, 0)
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
        max_row = self.view.rows
        row_delta = (
            min(
                max(0, self.parser.row_count() - max_row),
                max(0, self.pen_row - max_row // 2),
            )
            - self.view.scroll_row
        )
        self.cursor_move_scroll(0, 0, row_delta, 0)

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
        if self.selection_mode != SelectionMode.NONE:
            self.perform_delete()
        elif self.pen_col == self.parser.row_width(self.pen_row):
            if self.pen_row + 1 < self.parser.row_count():
                self.join_lines()
        else:
            self.del_ch()

    def delete_to_end_of_line(self):
        line, line_width = self.parser.row_text_and_width(self.pen_row)
        if self.pen_col == line_width:
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
        if self.selection_mode != SelectionMode.NONE:
            self.perform_delete()
        self.redo_add_change(("v", clip))
        self.redo()
        row_delta = len(clip) - 1
        if row_delta == 0:
            end_col = self.pen_col + app.curses_util.column_width(clip[0])
        else:
            end_col = app.curses_util.column_width(clip[-1])
        self.cursor_move(row_delta, end_col - self.pen_col)

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
        self.saved_at_redo_index = self.redo_index

    def file_load(self):
        app.log.info("file_load", self.full_path)
        input_file = None
        self.is_read_only = os.path.isfile(self.full_path) and not os.access(
            self.full_path, os.W_OK
        )
        if not os.path.exists(self.full_path):
            data = ""
            self.set_message("Creating new file")
        else:
            try:
                input_file = open(self.full_path)
                data = unicode(input_file.read())
                self.file_encoding = input_file.encoding
                self.set_message("Opened existing file")
                self.is_binary = False
            except Exception as e:
                # app.log.info(unicode(e))
                try:
                    input_file = open(self.full_path, "rb")
                    if 1:
                        binary_data = input_file.read()
                        long_hex = binascii.hexlify(binary_data).decode("utf-8")
                        hex_list = []
                        i = 0
                        width = 32
                        while i < len(long_hex):
                            hex_list.append(long_hex[i : i + width] + "\n")
                            i += width
                        data = "".join(hex_list)
                    else:
                        data = input_file.read()
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
            self.file_change_notified = False
        self.relative_path = os.path.relpath(self.full_path, os.getcwd())
        app.log.info("full_path", self.full_path)
        app.log.info("cwd", os.getcwd())
        app.log.info("relative_path", self.relative_path)
        self.file_filter(data)
        if input_file:
            input_file.close()
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
            self.parser.resume_at_row = 0
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
        # self.view.scroll_row, self.view.scroll_col =
        #     self.file_history.setdefault(
        #     'scroll', (0, 0))
        self.do_selection_mode(
            self.file_history.setdefault("selection_mode", SelectionMode.NONE)
        )
        self.marker_row, self.marker_col = self.file_history.setdefault("marker", (0, 0))
        if self.program.prefs.editor["save_undo"]:
            self.redo_chain = self.file_history.setdefault("redo_chain_compound", [])
            self.saved_at_redo_index = self.file_history.setdefault(
                "saved_at_redo_index_compound", 0
            )
            self.temp_change = self.file_history.setdefault("temp_change", None)
            self.redo_index = self.saved_at_redo_index
            self.old_redo_index = self.saved_at_redo_index
        if app.config.strict_debug:
            assert self.pen_row < self.parser.row_count(), self.pen_row
            assert self.marker_row < self.parser.row_count(), self.marker_row

        # Restore file bookmarks
        self.bookmarks = self.file_history.setdefault("bookmarks", [])

        # Store the file's info.
        self.last_checksum, self.last_file_size = app.history.get_file_info(self.full_path)

    def update_basic_scroll_position(self):
        """Sets scroll_row, scroll_col to the closest values that the view's
        position must be in order to see the cursor.

        Args:
          None.

        Returns:
          None.
        """
        if self.view is None:
            return
        # Row.
        max_row = self.view.rows
        if self.view.scroll_row > self.pen_row:
            self.view.scroll_row = self.pen_row
        elif self.pen_row >= self.view.scroll_row + max_row:
            self.view.scroll_row = self.pen_row - max_row + 1
        # Column.
        max_col = self.view.cols
        if self.view.scroll_col > self.pen_col:
            self.view.scroll_col = self.pen_col
        elif self.pen_col >= self.view.scroll_col + max_col:
            self.view.scroll_col = self.pen_col - max_col + 1

    def scroll_to_optimal_scroll_position(self):
        """Put the selection in the 'optimal' position in the view. What is
        optimal is defined by the "optimal_cursor_row" and "optimal_cursor_col"
        preferences.

        Args:
          None.

        Returns:
          A tuple of (scroll_row, scroll_col) representing where the view's
          optimal position should be.
        """
        if self.view is None:
            return
        top, left, bottom, right = self.start_and_end()
        # Row.
        max_rows = self.view.rows
        scroll_row = self.view.scroll_row
        height = bottom - top + 1
        extra_rows = max_rows - height
        if extra_rows > 0:
            optimal_row_ratio = self.program.prefs.editor["optimal_cursor_row"]
            scroll_row = max(
                0,
                min(
                    self.parser.row_count() - 1,
                    top - int(optimal_row_ratio * (max_rows - 1)),
                ),
            )
        else:
            scroll_row = top
        # Column.
        max_cols = self.view.cols
        scroll_col = self.view.scroll_col
        length = right - left + 1
        extra_cols = max_cols - length
        if extra_cols > 0:
            if right < max_cols:
                scroll_col = 0
            else:
                optimal_col_ratio = self.program.prefs.editor["optimal_cursor_col"]
                scroll_col = max(
                    0, min(right, left - int(optimal_col_ratio * (max_cols - 1)))
                )
        else:
            scroll_col = left
        self.view.scroll_row = scroll_row
        self.view.scroll_col = scroll_col

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
            self.view.scroll_col <= left and right < self.view.scroll_col + self.view.cols
        )
        vertically = (
            self.view.scroll_row <= top and bottom < self.view.scroll_row + self.view.rows
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
                if self.program.prefs.editor["on_save_strip_trailing_spaces"]:
                    self.strip_trailing_white_space()
                    self.compound_change_push()
                # Save user data that applies to read-only files into history.
                self.file_history["path"] = self.full_path
                self.file_history["pen"] = (self.pen_row, self.pen_col)
                if self.view is not None:
                    self.file_history["scroll"] = (
                        self.view.scroll_row,
                        self.view.scroll_col,
                    )
                self.file_history["marker"] = (self.marker_row, self.marker_col)
                self.file_history["selection_mode"] = self.selection_mode
                self.file_history["bookmarks"] = self.bookmarks
                if self.is_binary:
                    remove_whitespace = {
                        ord(" "): None,
                        ord("\n"): None,
                        ord("\r"): None,
                        ord("\t"): None,
                    }
                    output_data = binascii.unhexlify(
                        self.parser.data.translate(remove_whitespace)
                    )
                    output_file = open(self.full_path, "wb+")
                elif self.file_encoding is None:
                    output_data = self.parser.data
                    output_file = open(self.full_path, "w+", encoding="UTF-8")
                else:
                    output_data = self.parser.data
                    output_file = open(
                        self.full_path, "w+", encoding=self.file_encoding
                    )
                output_file.seek(0)
                output_file.truncate()
                output_file.write(output_data)
                output_file.close()
                # Save user data that applies to writable files.
                self.saved_at_redo_index = self.redo_index
                if self.program.prefs.editor["save_undo"]:
                    self.file_history["redo_chain_compound"] = self.redo_chain
                    self.file_history[
                        "saved_at_redo_index_compound"
                    ] = self.saved_at_redo_index
                    self.file_history["temp_change"] = self.temp_change
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
        end_col = col + length
        in_view = self.is_in_view(row, end_col, row, end_col)
        self.do_selection_mode(SelectionMode.NONE)
        self.cursor_move(row - self.pen_row, end_col - self.pen_col)
        self.do_selection_mode(mode)
        self.cursor_move(0, -length)
        if not in_view:
            self.scroll_to_optimal_scroll_position()

    def find(self, search_for, direction=0):
        """direction is -1 for find_prior, 0 for at pen, 1 for find_next."""
        if app.config.strict_debug:
            assert isinstance(search_for, unicode)
            assert isinstance(direction, int)
        app.log.info(search_for, direction)
        if not len(search_for):
            self.find_re = None
            self.do_selection_mode(SelectionMode.NONE)
            return
        editor_prefs = self.program.prefs.editor
        flags = 0
        flags |= editor_prefs.get("find_ignore_case") and re.IGNORECASE or 0
        flags |= editor_prefs.get("find_multi_line") and re.MULTILINE or 0
        flags |= editor_prefs.get("find_locale") and re.LOCALE or 0
        flags |= editor_prefs.get("find_dot_all") and re.DOTALL or 0
        flags |= editor_prefs.get("find_verbose") and re.VERBOSE or 0
        flags |= editor_prefs.get("find_unicode") and re.UNICODE or 0
        if not editor_prefs.get("find_use_regex"):
            search_for = re.escape(search_for)
        if editor_prefs.get("find_whole_word"):
            search_for = rf"\b{search_for}\b"
        # app.log.info(search_for, flags)
        with warnings.catch_warnings():
            # Ignore future warning with '[[' regex.
            warnings.simplefilter("ignore")
            # The saved re is also used for highlighting.
            self.find_re = re.compile(search_for, flags)
            self.find_back_re = re.compile(
                f"{search_for}(?!.*{search_for}.*)", flags
            )
        self.find_current_pattern(direction)

    def replace_found(self, replace_with):
        """direction is -1 for find_prior, 0 for at pen, 1 for find_next."""
        if app.config.strict_debug:
            assert isinstance(replace_with, unicode)
        if not self.find_re:
            return
        if self.program.prefs.editor.get("find_use_regex"):
            toReplace = "\n".join(self.get_selected_text())
            try:
                toReplace = self.find_re.sub(replace_with, toReplace)
            except re.error as e:
                # TODO(dschuyler): This is stomped by another set_message().
                self.set_message(str(e))
            self.edit_paste_data(toReplace)
        else:
            self.edit_paste_data(replace_with)

    def find_plain_text(self, text):
        search_for = re.escape(text)
        self.find_re = re.compile("()^" + search_for)
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
        split_cmd = cmd.split(separator, 3)
        if len(split_cmd) < 4:
            self.set_message("An exchange needs three " + separator + " separators")
            return
        _, find, replace, flags = split_cmd
        data = self.find_replace_text(find, replace, flags, self.parser.data)
        self.apply_document_update(data)

    def find_replace_text(self, find, replace, flags, text):
        flags = self.find_replace_flags(flags)
        return re.sub(find, replace, text, flags=flags)

    def apply_document_update(self, data):
        lines = self.do_data_to_lines(self.parser.data)
        diff = difflib.ndiff(lines, self.do_data_to_lines(data))
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
        local_re = self.find_re
        offset = self.pen_col + direction
        if direction < 0:
            local_re = self.find_back_re
        if local_re is None:
            app.log.info("local_re is None")
            return
        # Check part of current line.
        text = self.parser.row_text(self.pen_row)
        if direction >= 0:
            text = text[offset:]
        else:
            text = text[: self.pen_col]
            offset = 0
        # app.log.info('find() searching', repr(text))
        found = local_re.search(text)
        row_found = self.pen_row
        if not found:
            offset = 0
            row_count = self.parser.row_count()
            # To end of file.
            if direction >= 0:
                the_range = range(self.pen_row + 1, row_count)
            else:
                the_range = range(self.pen_row - 1, -1, -1)
            for i in the_range:
                found = local_re.search(self.parser.row_text(i))
                if found:
                    if 0:
                        for k in found.regs:
                            app.log.info("AAA", k[0], k[1])
                        app.log.info("b found on line", i, repr(found))
                    row_found = i
                    break
            if not found:
                # Wrap around to the opposite side of the file.
                self.set_message("Find wrapped around.")
                if direction >= 0:
                    the_range = range(self.pen_row)
                else:
                    the_range = range(row_count - 1, self.pen_row, -1)
                for i in the_range:
                    found = local_re.search(self.parser.row_text(i))
                    if found:
                        row_found = i
                        break
                if not found:
                    # Check the rest of the current line
                    if direction >= 0:
                        text = self.parser.row_text(self.pen_row)
                    else:
                        text = self.parser.row_text(self.pen_row)[self.pen_col :]
                        offset = self.pen_col
                    found = local_re.search(text)
                    row_found = self.pen_row
        if found:
            # app.log.info('c found on line', row_found, repr(found.regs))
            start = found.regs[0][0]
            end = found.regs[0][1]
            self.select_text(
                row_found,
                offset + start,
                end - start,
                SelectionMode.CHARACTER,
            )
            return
        app.log.info("find not found")
        self.do_selection_mode(SelectionMode.NONE)

    def find_again(self):
        """Find the current pattern, searching down the document."""
        self.find_current_pattern(1)

    def find_back(self):
        """Find the current pattern, searching up the document."""
        self.find_current_pattern(-1)

    def find_next(self, search_for):
        """Find a new pattern, searching down the document."""
        self.find(search_for, 1)

    def find_prior(self, search_for):
        """Find a new pattern, searching up the document."""
        self.find(search_for, -1)

    def indent(self):
        grammar = self.parser.grammar_at(self.pen_row, self.pen_col)
        indentation = (
            grammar.get("indent") or self.program.prefs.editor["indentation"]
        )
        indentation_length = len(indentation)
        if self.selection_mode == SelectionMode.NONE:
            self.vertical_insert(self.pen_row, self.pen_row, self.pen_col, indentation)
        else:
            self.indent_lines()
        self.cursor_move_and_mark(0, indentation_length, 0, indentation_length, 0)

    def indent_lines(self):
        """Indents all selected lines.

        Do not use for when the selection mode is SelectionMode.NONE since
        marker_row/marker_col currently do not get updated alongside
        pen_row/pen_col.
        """
        col = 0
        row = min(self.marker_row, self.pen_row)
        end_row = max(self.marker_row, self.pen_row)
        indentation = self.program.prefs.editor["indentation"]
        self.vertical_insert(row, end_row, col, indentation)

    def vertical_delete(self, row, end_row, col, text):
        self.redo_add_change(("vd", (text, row, end_row, col)))
        self.redo()
        if row <= self.marker_row <= end_row:
            self.cursor_move_and_mark(0, 0, 0, -len(text), 0)
        if row <= self.pen_row <= end_row:
            self.cursor_move_and_mark(0, -len(text), 0, 0, 0)

    def vertical_insert(self, row, end_row, col, text):
        self.redo_add_change(("vi", (text, row, end_row, col)))
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
            if self.program.prefs.editor["auto_insert_closing_character"]:
                pairs = {
                    ord("'"): "'",
                    ord('"'): '"',
                    ord("("): ")",
                    ord("{"): "}",
                    ord("["): "]",
                }
                skips = pairs.values()
                mate = pairs.get(ch)
                next_chr = self.parser.char_at(self.pen_row, self.pen_col)
                if unichr(ch) in skips and unichr(ch) == next_chr:
                    self.cursor_move(0, 1)
                elif mate is not None and (next_chr is None or next_chr.isspace()):
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

    def mouse_right_click(self, pane_row, pane_col, shift, ctrl, alt):
        app.log.info("right click at", pane_row, pane_col)
        screen_row = self.view.top + pane_row
        screen_col = self.view.left + pane_col
        self.view.present_modal(
            self.view.context_menu, screen_row, screen_col
        )
        self.view.change_focus_to(self.view.context_menu)

    def mouse_click(self, pane_row, pane_col, shift, ctrl, alt):
        if shift:
            if alt:
                self.selection_block()
            else:
                self.selection_character()
        else:
            self.selection_none()
        self.mouse_release(pane_row, pane_col, shift, ctrl, alt)

    def mouse_double_click(self, pane_row, pane_col, shift, ctrl, alt):
        app.log.info("double click", pane_row, pane_col)
        row = self.view.scroll_row + pane_row
        if row < self.parser.row_count() and self.parser.row_width(row):
            self.select_word_at(row, self.view.scroll_col + pane_col)

    def mouse_moved(self, pane_row, pane_col, shift, ctrl, alt):
        app.log.info(" mouse_moved", pane_row, pane_col, shift, ctrl, alt)
        if alt:
            self.selection_block()
        elif self.selection_mode == SelectionMode.NONE:
            self.selection_character()
        self.mouse_release(pane_row, pane_col, shift, ctrl, alt)

    def mouse_release(self, pane_row, pane_col, shift, ctrl, alt):
        app.log.info(" mouse release", pane_row, pane_col)
        if not self.parser.row_count():
            return
        virtual_row = self.view.scroll_row + pane_row
        row_count = self.parser.row_count()
        if virtual_row >= row_count:
            # Off the bottom of document.
            last_line = row_count - 1
            self.cursor_move(
                last_line - self.pen_row, self.parser.row_width(last_line) - self.pen_col
            )
            return
        row = max(0, min(virtual_row, row_count))
        col = max(0, self.view.scroll_col + pane_col)
        if self.selection_mode == SelectionMode.BLOCK:
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
        if self.selection_mode == SelectionMode.LINE:
            if self.pen_row + 1 == self.marker_row and row > self.pen_row:
                marker_row = -1
            elif self.pen_row == self.marker_row + 1 and row < self.pen_row:
                marker_row = 1
        elif self.selection_mode == SelectionMode.WORD:
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
        if self.selection_mode == SelectionMode.LINE:
            self.cursor_move_and_mark(*self.extend_selection())
        elif self.selection_mode == SelectionMode.WORD:
            if self.pen_row < self.marker_row or (
                self.pen_row == self.marker_row and self.pen_col < self.marker_col
            ):
                self.cursor_select_word_left()
            elif pane_col < row_width:
                self.cursor_select_word_right()

    def mouse_triple_click(self, pane_row, pane_col, shift, ctrl, alt):
        app.log.info("triple click", pane_row, pane_col)
        self.mouse_release(pane_row, pane_col, shift, ctrl, alt)
        self.select_line_at(self.view.scroll_row + pane_row)

    def scroll_window(self, rows, cols):
        self.cursor_move_scroll(rows, self.cursor_col_delta(self.pen_row - rows), -1, 0)
        self.redo()

    def mouse_wheel_down(self, shift, ctrl, alt):
        if not shift:
            self.selection_none()
        if self.program.prefs.editor["natural_scroll_direction"]:
            self.scroll_up()
        else:
            self.scroll_down()

    def scroll_up(self):
        if self.view.scroll_row == 0:
            self.set_message("Top of file")
            return
        max_row = self.view.rows
        cursor_delta = 0
        if self.pen_row >= self.view.scroll_row + max_row - 2:
            cursor_delta = self.view.scroll_row + max_row - 2 - self.pen_row
        self.update_scroll_position(-1, 0)
        if self.view.has_captive_cursor:
            self.cursor_move_scroll(
                cursor_delta, self.cursor_col_delta(self.pen_row + cursor_delta), 0, 0
            )
            self.redo()

    def mouse_wheel_up(self, shift, ctrl, alt):
        if not shift:
            self.selection_none()
        if self.program.prefs.editor["natural_scroll_direction"]:
            self.scroll_down()
        else:
            self.scroll_up()

    def scroll_down(self):
        max_row = self.view.rows
        if self.view.scroll_row + max_row >= self.parser.row_count():
            self.set_message("Bottom of file")
            return
        cursor_delta = 0
        if self.pen_row <= self.view.scroll_row + 1:
            cursor_delta = self.view.scroll_row - self.pen_row + 1
        self.update_scroll_position(1, 0)
        if self.view.has_captive_cursor:
            self.cursor_move_scroll(
                cursor_delta, self.cursor_col_delta(self.pen_row + cursor_delta), 0, 0
            )
            self.redo()

    def open_file_at_cursor(self):
        """
        Opens the file under cursor.
        """

        def open_file(path):
            text_buffer = self.view.program.buffer_manager.load_text_buffer(path)
            input_window = self.view.controller.current_input_window()
            input_window.set_text_buffer(text_buffer)
            self.change_to(input_window)
            self.set_message(f"Opened file {path}")

        text, link_type = self.parser.grammar_text_at(self.pen_row, self.pen_col)
        if link_type is None:
            self.set_message("Text is not a recognized file.")
            return
        if link_type in ("c<", 'c"'):
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
        next_mode = self.selection_mode + 1
        next_mode %= len(SelectionMode)
        self.do_selection_mode(next_mode)
        app.log.info("next_selection_mode", self.selection_mode)

    def no_op(self, ignored):
        pass

    def no_op_default(self, ignored, ignored2=None):
        pass

    def normalize(self):
        self.selection_none()
        self.find_re = None
        self.view.normalize()

    def parse_screen_maybe(self):
        begin = self.parser.resume_at_row
        end = self.view.scroll_row + self.view.rows + 1
        if end > begin + 100:
            # Call do_parse with an empty range.
            end = begin
        self.do_parse(begin, end)

    def parse_grammars(self):
        if not self.view:
            return
        scroll_row = self.view.scroll_row
        # If there is a gap, leave it to the background parsing.
        if self.parser.resume_at_row < scroll_row:
            return
        end = self.view.scroll_row + self.view.rows + 1
        self.do_parse(self.parser.resume_at_row, end)

    def do_selection_mode(self, mode):
        if self.selection_mode != mode:
            self.redo_add_change(
                (
                    "m",
                    (
                        0,
                        0,
                        self.pen_row - self.marker_row,
                        self.pen_col - self.marker_col,
                        mode - self.selection_mode,
                    ),
                )
            )
            self.redo()

    def cursor_select_line(self):
        """This function is used to select the line in which the cursor is in.

        Consecutive calls to this function will select subsequent lines.
        """
        if self.selection_mode != SelectionMode.LINE:
            self.selection_line()
        self.select_line_at(self.pen_row)

    def selection_all(self):
        self.do_selection_mode(SelectionMode.ALL)
        self.cursor_move_and_mark(*self.extend_selection())

    def selection_block(self):
        self.do_selection_mode(SelectionMode.BLOCK)

    def selection_character(self):
        self.do_selection_mode(SelectionMode.CHARACTER)

    def selection_line(self):
        self.do_selection_mode(SelectionMode.LINE)

    def selection_none(self):
        self.do_selection_mode(SelectionMode.NONE)

    def selection_word(self):
        self.do_selection_mode(SelectionMode.WORD)

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
                SelectionMode.LINE - self.selection_mode,
            )
        else:
            self.cursor_move_and_mark(
                row - self.pen_row,
                self.parser.row_width(row) - self.pen_col,
                0,
                -self.marker_col,
                SelectionMode.LINE - self.selection_mode,
            )

    def select_word_at(self, row, col):
        """row and col may be from a mouse click and may not actually land in
        the document text."""
        self.select_text(row, col, 0, SelectionMode.WORD)
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
        if self.selection_mode != SelectionMode.NONE:
            self.unindent_lines()
        else:
            indentation = self.program.prefs.editor["indentation"]
            indentation_length = len(indentation)
            line = self.parser.row_text(self.pen_row)
            start = self.pen_col - indentation_length
            if indentation == line[start : self.pen_col]:
                self.vertical_delete(self.pen_row, self.pen_row, start, indentation)

    def unindent_lines(self):
        indentation = self.program.prefs.editor["indentation"]
        indentation_length = len(indentation)
        row = min(self.marker_row, self.pen_row)
        end_row = max(self.marker_row, self.pen_row)
        # Collect a run of lines that can be unindented as a group.
        begin = 0
        i = 0
        for i in range(end_row + 1 - row):
            line, line_width = self.parser.row_text_and_width(row + i)
            if line_width < indentation_length or line[:indentation_length] != indentation:
                if begin < i:
                    # There is a run of lines that should be unindented.
                    self.vertical_delete(row + begin, row + i - 1, 0, indentation)
                # Skip this line (don't unindent).
                begin = i + 1
        if begin <= i:
            # There is one last run of lines that should be unindented.
            self.vertical_delete(row + begin, row + i, 0, indentation)

    def update_scroll_position(self, scroll_row_delta, scroll_col_delta):
        """This function updates the view's scroll position using the optional
        scroll_row_delta and scroll_col_delta arguments.

        Args:
          scroll_row_delta (int): The number of rows down to move the view.
          scroll_col_delta (int): The number of rows right to move the view.

        Returns:
          None
        """
        self.view.scroll_row += scroll_row_delta
        self.view.scroll_col += scroll_col_delta
