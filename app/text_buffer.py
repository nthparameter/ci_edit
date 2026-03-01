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

import curses
import re
import sys

import app.actions
import app.curses_util
import app.regex
import app.log
import app.parser
import app.selectable

class TextBuffer(app.actions.Actions):
    """The TextBuffer adds the drawing/rendering to the BackingTextBuffer."""

    def __init__(self, program):
        app.actions.Actions.__init__(self, program)
        self.line_limit_indicator = 0
        self.highlight_re = None
        self.highlight_cursor_line = False
        self.highlight_trailing_whitespace = True
        self.should_reparse = False

    def check_scroll_to_cursor(self, window):
        """Move the selected view rectangle so that the cursor is visible."""
        max_row, max_col = window.rows, window.cols
        #     self.pen_row >= self.view.scroll_row + max_row 1 0
        rows = 0
        if self.view.scroll_row > self.pen_row:
            rows = self.pen_row - self.view.scroll_row
            app.log.error(
                "AAA self.view.scroll_row > self.pen_row",
                self.view.scroll_row,
                self.pen_row,
                self,
            )
        elif self.pen_row >= self.view.scroll_row + max_row:
            rows = self.pen_row - (self.view.scroll_row + max_row - 1)
            app.log.error(
                "BBB self.pen_row >= self.view.scroll_row + max_row cRow",
                self.pen_row,
                "sRow",
                self.view.scroll_row,
                "max_row",
                max_row,
                self,
            )
        cols = 0
        if self.view.scroll_col > self.pen_col:
            cols = self.pen_col - self.view.scroll_col
            app.log.error(
                "CCC self.view.scroll_col > self.pen_col",
                self.view.scroll_col,
                self.pen_col,
                self,
            )
        elif self.pen_col >= self.view.scroll_col + max_col:
            cols = self.pen_col - (self.view.scroll_col + max_col - 1)
            app.log.error(
                "DDD self.pen_col >= self.scroll_col + max_col",
                self.pen_col,
                self.view.scroll_col,
                max_col,
                self,
            )
        assert not rows
        assert not cols
        self.update_scroll_position(rows, cols)

    def draw(self, window):
        if self.view.rows <= 0 or self.view.cols <= 0:
            return
        if not self.view.program.prefs.editor["useBgThread"]:
            if self.should_reparse:
                self.parse_grammars()
                self.should_reparse = False
        if self.view.has_captive_cursor:
            self.check_scroll_to_cursor(window)
        rows, cols = window.rows, window.cols
        color_pref = self.view.color_pref
        color_delta = 32 * 4
        # color_delta = 4
        if 0:
            for i in range(rows):
                window.add_str(i, 0, "?" * cols, color_pref(120))
        if 0:
            # Draw window with no concern for sub-rectangles.
            self.draw_text_area(window, 0, 0, rows, cols, 0)
        elif 1:
            split_row = rows
            split_col = max(0, self.line_limit_indicator - self.view.scroll_col)
            if self.line_limit_indicator <= 0 or split_col >= cols:
                # Draw only left side.
                self.draw_text_area(window, 0, 0, split_row, cols, 0)
            elif 0 < split_col < cols:
                # Draw both sides.
                self.draw_text_area(window, 0, 0, split_row, split_col, 0)
                self.draw_text_area(
                    window, 0, split_col, split_row, cols - split_col, color_delta
                )
            else:
                # Draw only right side.
                assert split_col <= 0
                self.draw_text_area(
                    window, 0, split_col, split_row, cols - split_col, color_delta
                )
        else:
            # Draw debug checker board.
            split_row = rows // 2
            split_col = 17
            self.draw_text_area(window, 0, 0, split_row, split_col, 0)
            self.draw_text_area(
                window, 0, split_col, split_row, cols - split_col, color_delta
            )
            self.draw_text_area(
                window, split_row, 0, rows - split_row, split_col, color_delta
            )
            self.draw_text_area(
                window, split_row, split_col, rows - split_row, cols - split_col, 0
            )
        # Blank screen past the end of the buffer.
        color = color_pref("outside_document")
        end_of_text = min(max(self.parser.row_count() - self.view.scroll_row, 0), rows)
        for i in range(end_of_text, rows):
            window.add_str(i, 0, " " * cols, color)

    def draw_text_area(self, window, top, left, rows, cols, color_delta):
        start_row = self.view.scroll_row + top
        end_row = start_row + rows
        start_col = self.view.scroll_col + left
        end_col = start_col + cols
        app_prefs = self.view.program.prefs
        default_color = app_prefs.color["default"]
        spell_checking = app_prefs.editor.get("spell_checking", True)
        color_pref = self.view.color_pref
        spelling = self.program.dictionary
        spelling.set_up_words_for_path(self.full_path)
        if self.parser:
            # Highlight grammar.
            row_limit = min(max(self.parser.row_count() - start_row, 0), rows)
            for i in range(row_limit):
                line, rendered_width = self.parser.row_text_and_width(start_row + i)
                k = start_col
                if k == 0:
                    # When rendering from column 0 the grammar index is always
                    # zero.
                    grammar_index = 0
                else:
                    # When starting mid-line, find starting grammar index.
                    grammar_index = self.parser.grammar_index_from_row_col(
                        start_row + i, k
                    )
                while k < end_col:
                    (node, preceding, remaining, eol) = self.parser.grammar_at_index(
                        start_row + i, k, grammar_index
                    )
                    grammar_index += 1
                    if remaining == 0 and not eol:
                        continue
                    remaining = min(rendered_width - k, remaining)
                    length = min(end_col - k, remaining)
                    color = color_pref(
                        node.grammar.get("color_index", default_color), color_delta
                    )
                    if eol or length <= 0:
                        window.add_str(
                            top + i, left + k - start_col, " " * (end_col - k), color
                        )
                        break
                    window.add_str(
                        top + i,
                        left + k - start_col,
                        app.curses_util.rendered_sub_str(line, k, k + length),
                        color,
                    )
                    sub_start = k - preceding
                    sub_end = k + remaining
                    sub_line = line[sub_start:sub_end]
                    if spell_checking and node.grammar.get("spelling", True):
                        # Highlight spelling errors
                        grammar_name = node.grammar.get("name", "unknown")
                        misspelling_color = color_pref("misspelling", color_delta)
                        for found in re.finditer(app.regex.RE_SUBWORDS, sub_line):
                            reg = found.regs[0]  # Mispelllled word
                            offset_start = sub_start + reg[0]
                            offset_end = sub_start + reg[1]
                            if start_col < offset_end and offset_start < end_col:
                                word = line[offset_start:offset_end]
                                if not spelling.is_correct(word, grammar_name):
                                    if start_col > offset_start:
                                        offset_start += start_col - offset_start
                                    word_fragment = line[
                                        offset_start : min(end_col, offset_end)
                                    ]
                                    window.add_str(
                                        top + i,
                                        left + offset_start - start_col,
                                        word_fragment,
                                        misspelling_color,
                                    )
                    k += length
        else:
            # For testing, draw without parser.
            row_limit = min(max(self.parser.row_count() - start_row, 0), rows)
            for i in range(row_limit):
                line = self.parser.row_text(start_row + i)[start_col:end_col]
                window.add_str(
                    top + i,
                    left,
                    line + " " * (cols - len(line)),
                    color_pref("default", color_delta),
                )
        self.draw_overlays(window, top, left, rows, cols, color_delta)
        if 0:  # Experiment: draw our own cursor.
            if start_row <= self.pen_row < end_row and start_col <= self.pen_col < end_col:
                window.add_str(
                    self.pen_row - start_row, self.pen_col - start_col, "X", 200
                )

    def draw_overlays(self, window, top, left, max_row, max_col, color_delta):
        start_row = self.view.scroll_row + top
        end_row = self.view.scroll_row + top + max_row
        start_col = self.view.scroll_col + left
        end_col = self.view.scroll_col + left + max_col
        row_limit = min(max(self.parser.row_count() - start_row, 0), max_row)
        color_pref = self.view.color_pref
        if 1:
            # Highlight brackets.
            # Highlight numbers.
            # Highlight space ending lines.
            colors = (
                color_pref("bracket", color_delta),
                color_pref("number", color_delta),
                color_pref("trailing_space", color_delta),
            )
            for i in range(row_limit):
                line = self.parser.row_text(start_row + i)
                highlight_trailing_whitespace = self.highlight_trailing_whitespace and not (
                    start_row + i == self.pen_row and self.pen_col == len(line)
                )
                for s, column, _, index in app.curses_util.rendered_find_iter(
                    line,
                    start_col,
                    end_col,
                    ("[]{}()",),
                    True,
                    highlight_trailing_whitespace,
                ):
                    window.add_str(
                        top + i, column - self.view.scroll_col, s, colors[index]
                    )
        if 1:
            # Match brackets.
            if (
                self.parser.row_count() > self.pen_row
                and len(self.parser.row_text(self.pen_row)) > self.pen_col
            ):
                ch = app.curses_util.char_at_column(
                    self.pen_col, self.parser.row_text(self.pen_row)
                )
                matching_bracket_row_col = self.get_matching_bracket_row_col()
                if matching_bracket_row_col is not None:
                    matching_bracket_row = matching_bracket_row_col[0]
                    matching_bracket_col = matching_bracket_row_col[1]
                    window.add_str(
                        top + self.pen_row - start_row,
                        self.pen_col - self.view.scroll_col,
                        ch,
                        color_pref("matching_bracket", color_delta),
                    )
                    character_finder = {
                        "(": ")",
                        "[": "]",
                        "{": "}",
                        ")": "(",
                        "]": "[",
                        "}": "{",
                    }
                    opp_character = character_finder[ch]
                    window.add_str(
                        top + matching_bracket_row - start_row,
                        matching_bracket_col - self.view.scroll_col,
                        opp_character,
                        color_pref("matching_bracket", color_delta),
                    )
        if self.highlight_cursor_line:
            # Highlight the whole line at the cursor location.
            if self.view.has_focus and start_row <= self.pen_row < start_row + row_limit:
                line = self.parser.row_text(self.pen_row)[start_col:end_col]
                window.add_str(
                    top + self.pen_row - start_row,
                    left,
                    line,
                    color_pref("current_line", color_delta),
                )
        if self.find_re is not None:
            # Highlight find.
            for i in range(row_limit):
                line = self.parser.row_text(start_row + i)[start_col:end_col]
                for k in self.find_re.finditer(line):
                    reg = k.regs[0]
                    # for ref in k.regs[1:]:
                    window.add_str(
                        top + i,
                        left + reg[0],
                        line[reg[0] : reg[1]],
                        color_pref("found_find", color_delta),
                    )
        if row_limit and self.selection_mode != app.selectable.SELECTION_NONE:
            # Highlight selected text.
            color_selected = color_pref("selected")
            upper_row, upper_col, lower_row, lower_col = self.start_and_end()
            if 1:
                sel_start_col = max(upper_col, start_col)
                sel_end_col = min(lower_col, end_col)
                start = max(0, min(upper_row - start_row, max_row))
                end = max(0, min(lower_row - start_row, max_row))
                if self.selection_mode == app.selectable.SELECTION_BLOCK:
                    if not (
                        lower_row < start_row
                        or upper_row >= end_row
                        or lower_col < start_col
                        or upper_col >= end_col
                    ):
                        # There is an overlap.
                        for i in range(start, end + 1):
                            line = self.parser.row_text(start_row + i)[
                                sel_start_col:sel_end_col
                            ]
                            window.add_str(top + i, sel_start_col, line, color_selected)
                elif (
                    self.selection_mode == app.selectable.SELECTION_ALL
                    or self.selection_mode == app.selectable.SELECTION_CHARACTER
                    or self.selection_mode == app.selectable.SELECTION_LINE
                    or self.selection_mode == app.selectable.SELECTION_WORD
                ):
                    if not (lower_row < start_row or upper_row >= end_row):
                        # There is an overlap.
                        # Go one row past the selection or to the last line.
                        for i in range(
                            start, min(end + 1, self.parser.row_count() - start_row)
                        ):
                            line = self.parser.row_text(start_row + i)
                            line += " "  # Maybe do: "\\n".
                            # TODO(dschuyler): This is essentially
                            # left + (upper_col or (scroll_col + left)) -
                            #    scroll_col - left
                            # which seems like it could be simplified.
                            pane_col = left + sel_start_col - start_col
                            if i == lower_row - start_row and i == upper_row - start_row:
                                # Selection entirely on one line.
                                text = app.curses_util.rendered_sub_str(
                                    line, sel_start_col, sel_end_col
                                )
                                window.add_str(top + i, pane_col, text, color_selected)
                            elif i == lower_row - start_row:
                                # End of multi-line selection.
                                text = app.curses_util.rendered_sub_str(
                                    line, start_col, sel_end_col
                                )
                                window.add_str(top + i, left, text, color_selected)
                            elif i == upper_row - start_row:
                                # Start of multi-line selection.
                                text = app.curses_util.rendered_sub_str(
                                    line, sel_start_col, end_col
                                )
                                window.add_str(top + i, pane_col, text, color_selected)
                            else:
                                # Middle of multi-line selection.
                                text = app.curses_util.rendered_sub_str(
                                    line, start_col, end_col
                                )
                                window.add_str(top + i, left, text, color_selected)
