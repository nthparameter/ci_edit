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

try:
    unicode
except NameError:
    unicode = str
    unichr = chr

import curses.ascii
import os
import re
import sys
import threading
import time
import traceback

import third_party.pyperclip as clipboard

import app.config
import app.log
import app.selectable

# Keys to tuples within |parser_nodes|.
# Reference to a prefs grammar dictionary.
PARSER_GRAMMAR = 0
# The current grammar begins at byte offset |PARSER_BEGIN| in the source data.
PARSER_BEGIN = 1
# An index into the parser_nodes list to the prior (or parent) grammar.
PARSER_PRIOR = 2
# Some characters display wider (or narrower) than others. Visual is a running
# display offset. E.g. if the first character in some utf-8 data is a double
# width and 3 bytes long the PARSER_BEGIN = 0, and PARSER_VISUAL = 0; the second character
# will start at PARSER_BEGIN = 3, PARSER_VISUAL = 2.
PARSER_VISUAL = 3

class ParserNode:
    """A parser node represents a span of grammar. i.e. from this point to that
    point is HTML. Another parser node would represent the next segment, of
    grammar (maybe JavaScript, CSS, comment, or quoted string for example."""

    def __init__(self, grammar, begin, prior, visual):
        self.grammar = grammar
        # Offset from start of file.
        self.begin = begin
        # Index of prior grammar (like a stack of grammars).
        self.prior = prior
        # Visible width on screen (double wide chars, and tabs).
        self.visual = visual

    def debug_log(self, out, indent, data):
        out(
            "%sParserNode %26s prior %4s, b%4d, v%4d %s"
            % (
                indent,
                self.grammar.get("name", "None"),
                self.prior,
                self.begin,
                self.visual,
                repr(data[self.begin : self.begin + 15])[1:-1],
            )
        )

class Parser:
    """A parser generates a set of grammar segments (ParserNode objects)."""

    def __init__(self, app_prefs):
        self.app_prefs = app_prefs
        self._defaultGrammar = app_prefs.grammars["none"]
        self.data = ""
        self.empty_node = ParserNode({}, None, None, 0)
        self.end_node = ({}, sys.maxsize, sys.maxsize, sys.maxsize)
        self.resume_at_row = 0
        self.pause_at_row = 0
        # A row on screen will consist of one or more ParserNodes. When a
        # ParserNode is returned from the parser it will be an instance of
        # ParserNode, but internally tuples are used in place of ParserNodes.
        # This makes for some ugly code, but the performance difference (~5%) is
        # worth it.
        self.parser_nodes = [({}, 0, None, 0)]
        # Each entry in |self.rows| is an index into the |self.parser_nodes|
        # array to the parerNode that begins that row.
        self.rows = [0]  # Row parser_nodes index.
        app.log.parser("__init__")

    def backspace(self, row, col):
        """Delete the character prior to |row, col|.
        Return the new (row, col) position."""
        self._fully_parse_to(row)
        offset = self.data_offset(row, col)
        if offset == 0:
            # Top of file, nothing to do.
            return row, col
        if offset is None:
            # Bottom of file (or past end of line, but assuming end of file).
            offset = len(self.data)
        ch = self.data[offset - 1]
        if ch == "\n":
            row -= 1
            col = self.row_width(row)
        elif ch == "\t":
            col += self.prior_char_row_col(row, col)[1]
        elif app.curses_util.is_double_width(ch):
            col -= 2
        else:
            col -= 1
        self.data = self.data[: offset - 1] + self.data[offset:]
        self._begin_parsing_at(row)
        if app.config.strict_debug:
            assert isinstance(self.data, unicode)
            assert row >= 0
            assert col >= 0
        return row, col

    def data_offset(self, row, col):
        """Return the offset within self.data (as unicode, not utf-8) for the
        start of the character at (row, col).

        Normally this will be the character the cursor is 'on' when
        using a block cursor; or to the 'right' of the when using a vertical
        cursor. I.e. it would be the character deleted by the 'del' key.

        Returns: offset (int) into self.data buffer; or None if (row, col) is
            outside the document.
        """
        self._fully_parse_to(row)
        if row >= len(self.rows):
            return None
        row_index = self.rows[row]
        node = self.parser_nodes[row_index]
        if row + 1 < len(self.rows):
            next_line_node = self.parser_nodes[self.rows[row + 1]]
            if col >= next_line_node[PARSER_VISUAL] - node[PARSER_VISUAL]:
                # The requested column is past the end of the line.
                return None
        elif row + 1 == len(self.rows):
            # On the last row.
            if col >= self.parser_nodes[-1][PARSER_VISUAL] - node[PARSER_VISUAL]:
                # The requested column is past the end of the line.
                return None
        else:
            # The requested column is past the end of the document.
            return None
        subnode = self.parser_nodes[row_index + self.grammar_index_from_row_col(row, col)]
        subnode_col = subnode[PARSER_VISUAL] - node[PARSER_VISUAL]
        subnode_col_delta = col - subnode_col
        offset = subnode[PARSER_BEGIN]
        if self.data[offset] == "\t":
            tab_width = 8
            floored_tab_grammar_col = subnode_col // tab_width * tab_width
            offset += (col - floored_tab_grammar_col) // tab_width
        elif app.curses_util.is_double_width(self.data[offset]):
            char_width = 2
            offset += subnode_col_delta // char_width
        else:
            offset += subnode_col_delta
        return offset

    def data_offset_row_col(self, offset):
        """Get the (row, col) for the given data |offset| or None if the offset
        is beyond the file."""
        if app.config.strict_debug:
            assert isinstance(offset, int)
            assert offset >= 0
        # Binary search to find the row, then the col.
        nodes = self.parser_nodes
        if offset >= nodes[-1][PARSER_BEGIN]:
            return None
        # Determine the row.
        rows = self.rows
        low = 0
        high = len(rows) - 1
        while True:
            row = (high + low) // 2
            if offset >= nodes[rows[row + 1]][PARSER_BEGIN]:
                low = row
            elif offset < nodes[rows[row]][PARSER_BEGIN]:
                high = row
            else:
                break
        # Determine the col.
        low = rows[row]
        high = rows[row + 1]
        while True:
            index = (high + low) // 2
            if offset >= nodes[index + 1][PARSER_BEGIN]:
                low = index
            elif offset < nodes[index][PARSER_BEGIN]:
                high = index
            else:
                break
        col = nodes[index][PARSER_VISUAL] - nodes[rows[row]][PARSER_VISUAL]
        remaining_offset = offset - nodes[index][PARSER_BEGIN]
        if remaining_offset > 0:
            ch = self.data[nodes[index][PARSER_BEGIN]]
            if ch == "\t":
                tab_width = self.app_prefs.editor.get("tab_size", 8)
                # Add the (potentially) fractional tab.
                col += app.curses_util.char_width(ch, col, tab_width)
                # Add the remaining tabs.
                col += tab_width * (remaining_offset - 1)
            else:
                col += app.curses_util.char_width(ch, col) * remaining_offset
        return row, col

    def default_grammar(self):
        return self._defaultGrammar

    def delete_block(self, upper_row, upper_col, lower_row, lower_col):
        for row in range(lower_row, upper_row - 1, -1):
            begin = self.data_offset(row, upper_col)
            end = self.data_offset(row, lower_col)
            if end is None:
                if begin is not None:
                    self.data = self.data[:begin]
            else:
                self.data = self.data[:begin] + self.data[end:]
        self._begin_parsing_at(upper_row)

    def delete_char(self, row, col):
        """Delete the character after (or "at") |row, col|."""
        self._fully_parse_to(row)
        offset = self.data_offset(row, col)
        if offset is None:
            # Bottom of file, nothing to do.
            return
        self.data = self.data[:offset] + self.data[offset + 1 :]
        self._begin_parsing_at(row)

    def delete_range(self, upper_row, upper_col, lower_row, lower_col):
        begin = self.data_offset(upper_row, upper_col)
        end = self.data_offset(lower_row, lower_col)
        if end is None:
            if begin is not None:
                self.data = self.data[:begin]
        else:
            self.data = self.data[:begin] + self.data[end:]
        self._begin_parsing_at(upper_row)

    def text_range(self, upper_row, upper_col, lower_row, lower_col):
        begin = self.data_offset(upper_row, upper_col)
        end = self.data_offset(lower_row, lower_col)
        if end is None:
            if begin is not None:
                return self.data[begin:]
        return self.data[begin:end]

    def grammar_index_from_row_col(self, row, col):
        """
        tip: as an optimization, check if |col == 0| prior to calling. The
            result will always be zero (so the call can be avoided).

        Returns:
            index. |index| may then be passed to grammar_at_index().
        """
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            assert row >= 0
            assert col >= 0
        self._fully_parse_to(row)
        if app.config.strict_debug:
            assert row < len(self.rows), (row, len(self.rows), repr(self.data))
        if row == len(self.rows) - 1:
            # The last line.
            assert row + 1 >= len(self.rows)
            gl = self.parser_nodes[self.rows[row] :] + [self.end_node]
        else:
            gl = self.parser_nodes[self.rows[row] : self.rows[row + 1]] + [self.end_node]
        offset = gl[0][PARSER_VISUAL] + col
        # Binary search to find the node for the column.
        low = 0
        high = len(gl) - 1
        while True:
            index = (high + low) // 2
            if offset >= gl[index + 1][PARSER_VISUAL]:
                low = index
            elif offset < gl[index][PARSER_VISUAL]:
                high = index
            else:
                # assert index < len(gl)  # Never return index to self.end_node.
                return index

    def grammar_at(self, row, col):
        """Get the grammar at row, col.
        It's more efficient to use grammar_index_from_row_col() and grammar_at_index()
        individually if grammars are requested contiguously. This function is
        just for one-off needs.
        """
        self._fully_parse_to(row)
        grammar_index = self.grammar_index_from_row_col(row, col)
        node, _, _, _ = self.grammar_at_index(row, col, grammar_index)
        return node.grammar

    def grammar_at_index(self, row, col, index):
        """Call grammar_index_from_row_col() to get the index parameter.

        Returns:
            (node, preceding, remaining, eol). |proceeding| and |remaining| are
            relative to the |col| parameter.
        """
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            assert isinstance(index, int)
            assert row < len(self.rows), row
        self._fully_parse_to(row)
        eol = True
        final_result = (self.empty_node, 0, 0, eol)
        row_index = self.rows[row]
        if row_index + index + 1 >= len(self.parser_nodes):
            return final_result
        next_offset = self.parser_nodes[row_index + index + 1][PARSER_VISUAL]
        offset = self.parser_nodes[row_index][PARSER_VISUAL] + col
        remaining = next_offset - offset
        if remaining < 0:
            return final_result
        node = self.parser_nodes[row_index + index]
        eol = False
        return ParserNode(*node), offset - node[PARSER_VISUAL], remaining, eol

    def grammar_text_at(self, row, col):
        """Get the run of text for the given position."""
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            assert row < len(self.rows), row
        self._fully_parse_to(row)
        row_index = self.rows[row]
        grammar_index = self.grammar_index_from_row_col(row, col)
        node = self.parser_nodes[row_index + grammar_index]
        next_node = self.parser_nodes[row_index + grammar_index + 1]
        return (
            self.data[node[PARSER_BEGIN] : next_node[PARSER_BEGIN]],
            node[PARSER_GRAMMAR].get("link_type"),
        )

    def in_document(self, row, col):
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            assert row >= 0
            assert col >= 0
        self._fully_parse_to(row)
        return row < len(self.rows) and col < self.parser_nodes[self.rows[row]][PARSER_VISUAL]

    def insert(self, row, col, text):
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            assert isinstance(text, unicode)
            assert row >= 0
            assert col >= 0
            assert len(text) > 0
        offset = self.data_offset(row, col)
        if offset is None:
            row = len(self.rows) - 1
            self.data += text
        else:
            self.data = self.data[:offset] + text + self.data[offset:]
        self._begin_parsing_at(row)

    def insert_block(self, row, col, lines):
        for i in range(len(lines) - 1, -1, -1):
            offset = self.data_offset(row + i, col)
            if offset is None:
                self.data += lines[i]
            else:
                self.data = self.data[:offset] + lines[i] + self.data[offset:]
        self._begin_parsing_at(row)

    def insert_lines(self, row, col, lines):
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            # assert isinstance(lines, tuple)
            assert row >= 0
            assert col >= 0
            assert len(lines) > 0
        text = "\n".join(lines)
        self.insert(row, col, text)

    def next_char_row_col(self, row, col):
        """Get the next column value for the character to the right.
        Returns: None if there is no remaining characters.
                 or (row, col) deltas of the next character in the document.
        """
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            assert row >= 0
            assert col >= 0
            assert len(self.rows) > 0
        self._fully_parse_to(row)
        ch = self.char_at(row, col)
        if ch is None:
            return (1, -col) if self.in_document(row + 1, 0) else None
        return 0, app.curses_util.char_width(ch, col)

    def prior_char_row_col(self, row, col):
        """Get the prior column value for the character to the left.
        Returns: None if there is no remaining characters.
                 or (row, col) deltas of the next character in the document.
        """
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            assert row >= 0
            assert col >= 0
            assert len(self.rows) > 0
        self._fully_parse_to(row)
        if col == 0:
            if row == 0:
                return None
            return (-1, self.row_width(row - 1))
        return 0, app.curses_util.prior_char_col(col, self.row_text(row)) - col

    def parse(self, bg_thread, data, grammar, begin_row, end_row):
        """
        Args:
          data (string): The file contents. The document.
          grammar (object): The initial grammar (often determined by the file
              extension). If |begin_row| is not zero then grammar is ignored.
          begin_row (int): is the first row (which is line number - 1) in data
              that is has changed since the previous parse of this data. Pass
              zero to parse the entire document. If begin_row >= len(data) then
              no parse is done.
          end_row (int): The row to stop parsing. This stops the parser from
              going over the entire file if, for example, only 100 rows out of
              a million rows are needed (which can save a lot of cpu time).
        """
        if app.config.strict_debug:
            assert bg_thread is None or isinstance(bg_thread, threading.Thread)
            assert isinstance(data, unicode), type(data)
            assert isinstance(grammar, dict)
            assert isinstance(begin_row, int)
            assert isinstance(end_row, int)
            assert begin_row >= 0
            assert end_row >= 0
            assert isinstance(self.app_prefs, app.prefs.Prefs)
        self._defaultGrammar = grammar
        self.empty_node = ParserNode(grammar, None, None, 0)
        self.data = data
        self._begin_parsing_at(begin_row)
        self._fully_parse_to(end_row, bg_thread)
        # self.debug_check_lines(app.log.parser, data)
        # start_time = time.time()
        if app.log.enabled_channels.get("parser", False):
            self.debug_log(app.log.parser, data)
        # app.log.startup('parsing took', time.time() - start_time)

    def _begin_parsing_at(self, begin_row):
        if app.config.strict_debug:
            assert isinstance(begin_row, int)
            assert begin_row >= 0, begin_row
            assert isinstance(self.resume_at_row, int)
            assert self.resume_at_row >= 0, self.resume_at_row
        if begin_row > self.resume_at_row:
            # Already beginning at an earlier row.
            return
        if begin_row > 0:
            # Trim partially parsed data.
            if begin_row < len(self.rows):
                self.parser_nodes = self.parser_nodes[: self.rows[begin_row]]
                self.rows = self.rows[:begin_row]
            self.resume_at_row = len(self.rows)
        else:
            # Parse the whole file.
            self.parser_nodes = [(self.default_grammar(), 0, None, 0)]
            self.rows = [0]
            self.resume_at_row = 0

    def _fast_line_parse(self, grammar):
        """If there's not enough time to thoroughly parse the file, identify the
        lines so that the document can still be edited.
        """
        data = self.data
        offset = self.parser_nodes[-1][PARSER_BEGIN]
        limit = len(data)
        if offset == limit:
            # Already parsed to end of data.
            return
        visual = self.parser_nodes[-1][PARSER_VISUAL]

        # Track the |visual| value for the start of the line. The difference
        # between |visual| and |visual_start_col| is the column index of the line.
        visual_start_col = 0
        while True:
            while offset < limit and data[offset] != "\n":
                if data[offset] < "ᄀ":
                    # The char is less than the first double width character.
                    # (An optimization to avoid calling char_width().)
                    visual += 1
                else:
                    # From here on, the width of the character is messy to
                    # determine, ask an authority.
                    visual += app.curses_util.char_width(
                        data[offset], visual - visual_start_col
                    )
                offset += 1
            if offset >= limit:
                # The document is missing the last new-line.
                if self.parser_nodes[-1][PARSER_BEGIN] != limit:
                    # Add a terminating (end) node.
                    self.parser_nodes.append((grammar, limit, None, visual))
                break
            visual_start_col = visual
            offset += 1
            visual += 1
            self.rows.append(len(self.parser_nodes))
            self.parser_nodes.append((grammar, offset, None, visual))

    def _fully_parse_to(self, end_row, bg_thread=None):
        """Parse up to and including |end_row|."""
        if app.config.strict_debug:
            assert isinstance(end_row, int)
            assert end_row >= 0
            assert bg_thread is None or isinstance(bg_thread, threading.Thread)
        # To parse |end_row| go one past because of the exclusive end of range.
        self.pause_at_row = end_row + 1
        if self.pause_at_row <= self.resume_at_row:
            # Already parsed to that row.
            return
        self._begin_parsing_at(self.resume_at_row)
        if len(self.rows) <= self.pause_at_row:
            self._build_grammar_list(bg_thread)
        self._fast_line_parse(self.default_grammar())
        if app.config.strict_debug:
            assert self.resume_at_row >= 0
            assert self.resume_at_row <= len(self.rows)
            if bg_thread is not None and end_row <= len(self.rows):
                assert self.resume_at_row >= end_row + 1, (self.resume_at_row, end_row)

    def row_count(self):
        self._fast_line_parse(self.default_grammar())
        return len(self.rows)

    def row_text(self, row, begin_col=None, end_col=None):
        """Get the text for |row|.

        Args:
            row (int): row is zero based.
            begin_col (int): subindex within the row (similar to a slice).
            end_col (int): subindex within the row (similar to a slice).

        Returns:
            document text (unicode)
        """
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert begin_col is None or isinstance(begin_col, int)
            assert end_col is None or isinstance(end_col, int)
            assert row >= 0
            assert isinstance(self.data, unicode)
        self._fully_parse_to(row)
        if begin_col is end_col is None:
            begin = self.parser_nodes[self.rows[row]][PARSER_BEGIN]
            if row + 1 >= len(self.rows):
                return self.data[begin:]
            end = self.parser_nodes[self.rows[row + 1]][PARSER_BEGIN]
            if len(self.data) and self.data[end - 1] == "\n":
                end -= 1
            return self.data[begin:end]

        if begin_col >= 0:
            begin = self.data_offset(row, begin_col)
        else:
            width = self.row_width(row)
            begin = self.data_offset(row, width + begin_col)

        if begin is None:
            return ""

        if end_col is None:
            end = self.data_offset(row + 1, 0)
        elif end_col < 0:
            width = self.row_width(row)
            end = self.data_offset(row, width + end_col)
        else:
            width = self.row_width(row)
            if end_col >= width:
                end_col = width
            end = self.data_offset(row, end_col)

        if end is None:
            end = len(self.data)
        if end > 0 and self.data[end - 1] == "\n":
            end -= 1

        return self.data[begin:end]

    def char_at(self, row, col):
        """Get the character at |row|, |col|.

        Args:
            row (int): zero based index into list of rows.
            col (int): zero based visual offset from start of line.

        Returns:
            character (unicode) or None if row, col is outside of the document.
        """
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert isinstance(col, int)
            assert isinstance(self.data, unicode)
            assert row >= 0
            assert col >= 0
        self._fully_parse_to(row)
        if row > len(self.rows):
            return None
        string, width = self.row_text_and_width(row)
        if col > width:
            return None
        return app.curses_util.char_at_column(col, string)

    def row_text_and_width(self, row):
        """Get the character data and the visual/display column width of those
        characters.

        If the text is all ASCII then len(text) will equal the column width. If
        there are double wide characters (e.g. Chinese or some emoji) the column
        width may be larger than len(text).

        Args:
            row (int): the row index is zero based (so it's line number - 1).

        Returns:
            (text, column_width) (tuple)
        """
        if app.config.strict_debug:
            assert isinstance(row, int)
        self._fully_parse_to(row)
        begin = self.parser_nodes[self.rows[row]][PARSER_BEGIN]
        visual = self.parser_nodes[self.rows[row]][PARSER_VISUAL]
        if row + 1 < len(self.rows):
            end = self.parser_nodes[self.rows[row + 1]][PARSER_BEGIN]
            visual_end = self.parser_nodes[self.rows[row + 1]][PARSER_VISUAL]
            if len(self.data) and self.data[end - 1] == "\n":
                end -= 1
                visual_end -= 1
        else:
            # There is a sentinel node at the end that records the end of
            # document.
            last_node = self.parser_nodes[-1]
            end = last_node[PARSER_BEGIN]
            visual_end = last_node[PARSER_VISUAL]
        return self.data[begin:end], visual_end - visual

    def row_width(self, row):
        """Get the visual/display column width of a row.

        If the text is all ASCII then len(text) will equal the column width. If
        there are double wide characters (e.g. Chinese or some emoji) the column
        width may be larger than len(text).

        Args:
            row (int): the row index is zero based (so it's `line_number - 1`).

        Returns:
            column_width (int)
        """
        if app.config.strict_debug:
            assert isinstance(row, int)
        if row < 0:
            row = len(self.rows) + row
        self._fully_parse_to(row)
        visual = self.parser_nodes[self.rows[row]][PARSER_VISUAL]
        if row + 1 < len(self.rows):
            end = self.parser_nodes[self.rows[row + 1]][PARSER_BEGIN]
            visual_end = self.parser_nodes[self.rows[row + 1]][PARSER_VISUAL]
            if len(self.data) and self.data[end - 1] == "\n":
                visual_end -= 1
        else:
            # There is a sentinel node at the end that records the end of
            # document.
            last_node = self.parser_nodes[-1]
            visual_end = last_node[PARSER_VISUAL]
        return visual_end - visual

    def _build_grammar_list(self, bg_thread):
        """The guts of the parser. This is where the heavy lifting is done.

        This code can be interrupted (by |bg_thread|) and resumed (by calling it
        again).
        """
        app_prefs = self.app_prefs
        # An arbitrary limit to avoid run-away looping.
        leash = 50000
        top_node = self.parser_nodes[-1]
        cursor = top_node[PARSER_BEGIN]
        visual = top_node[PARSER_VISUAL]
        # If we are at the start of a grammar, skip the 'begin' part of the
        # grammar.
        if 0:
            if (
                len(self.parser_nodes) == 1
                or (top_node[PARSER_GRAMMAR] is not self.parser_nodes[-2][PARSER_GRAMMAR])
                and top_node[PARSER_GRAMMAR].get("end") is not None
            ):
                begin_regex = top_node[PARSER_GRAMMAR].get("begin")
                if begin_regex is not None:
                    sre = re.match(begin_regex, self.data[cursor:])
                    if sre is not None:
                        assert False
                        cursor += sre.regs[0][1]
                        # Assumes single-wide characters.
                        visual += sre.regs[0][1]
        while len(self.rows) <= self.pause_at_row:
            if not leash:
                # app.log.error('grammar likely caught in a loop')
                break
            leash -= 1
            if bg_thread and bg_thread.has_user_event():
                break
            subdata = self.data[cursor:]
            found = self.parser_nodes[-1][PARSER_GRAMMAR].get("match_re").search(subdata)
            if not found:
                # app.log.info('parser exit, match not found')
                # todo(dschuyler): mark parent grammars as unterminated (if they
                # expect be terminated). e.g. unmatched string quote or xml tag.
                if cursor != len(self.data):
                    # The last bit of the last line.
                    self.parser_nodes.append(
                        (top_node[PARSER_GRAMMAR], cursor, top_node[PARSER_PRIOR], visual)
                    )
                break
            index = -1
            found_groups = found.groups()
            for k in found_groups:
                index += 1
                if k is not None:
                    break
            reg = found.regs[index + 1]
            if index == 0:
                # Found escaped value.
                cursor += reg[1]
                visual += reg[1]
                continue
            if index == len(found_groups) - 1:
                # Found new line.
                child = (
                    self.parser_nodes[-1][PARSER_GRAMMAR],
                    cursor + reg[1],
                    self.parser_nodes[-1][PARSER_PRIOR],
                    visual + reg[1],
                )
                cursor += reg[1]
                visual += reg[1]
                self.rows.append(len(self.parser_nodes))
            elif index == len(found_groups) - 2:
                # Found potentially double wide characters.
                top_node = self.parser_nodes[-1]
                reg_begin, reg_end = reg
                width = app.curses_util.char_width
                if reg_begin > 0:
                    # Add single wide characters.
                    self.parser_nodes.append(
                        (top_node[PARSER_GRAMMAR], cursor, top_node[PARSER_PRIOR], visual)
                    )
                    cursor += reg_begin
                    visual += reg_begin
                    reg_end -= reg_begin
                    reg_begin = 0
                while reg_begin < reg_end:
                    # Check for zero width characters.
                    while (
                        reg_begin < reg_end
                        and width(self.data[cursor + reg_begin], 0) == 0
                    ):
                        reg_begin += 1
                    if reg_begin > 0:
                        # Add zero width characters.
                        self.parser_nodes.append(
                            (top_node[PARSER_GRAMMAR], cursor, top_node[PARSER_PRIOR], visual)
                        )
                        cursor += reg_begin
                        reg_end -= reg_begin
                        reg_begin = 0
                    # Check for single wide characters.
                    while (
                        reg_begin < reg_end
                        and width(self.data[cursor + reg_begin], 0) == 1
                    ):
                        reg_begin += 1
                    if reg_begin > 0:
                        # Add single wide characters.
                        self.parser_nodes.append(
                            (top_node[PARSER_GRAMMAR], cursor, top_node[PARSER_PRIOR], visual)
                        )
                        cursor += reg_begin
                        visual += reg_begin
                        reg_end -= reg_begin
                        reg_begin = 0
                    # Check for double wide characters.
                    while (
                        reg_begin < reg_end
                        and width(self.data[cursor + reg_begin], 0) == 2
                    ):
                        reg_begin += 1
                    if reg_begin > 0:
                        # Add double wide characters.
                        self.parser_nodes.append(
                            (top_node[PARSER_GRAMMAR], cursor, top_node[PARSER_PRIOR], visual)
                        )
                        cursor += reg_begin
                        visual += reg_begin * 2
                        reg_end -= reg_begin
                        reg_begin = 0
                continue
            elif index == len(found_groups) - 3:
                # Found variable width (tab) character.
                top_node = self.parser_nodes[-1]
                reg_begin, reg_end = reg
                # First, add any preceding single wide characters.
                if reg_begin > 0:
                    self.parser_nodes.append(
                        (top_node[PARSER_GRAMMAR], cursor, top_node[PARSER_PRIOR], visual)
                    )
                    cursor += reg_begin
                    visual += reg_begin
                    # Remove the regular text from reg values.
                    reg_end -= reg_begin
                    reg_begin = 0
                # Add tabs grammar; store the variable width characters.
                row_start = self.parser_nodes[self.rows[-1]][PARSER_VISUAL]
                col = visual - row_start
                # Advance to the next tab stop.
                self.parser_nodes.append(
                    (app_prefs.grammars["tabs"], cursor, top_node[PARSER_PRIOR], visual)
                )
                cursor += reg_end
                visual = row_start + ((col + 8) // 8 * 8)
                visual += (reg_end - 1) * 8
                # Resume current grammar; store the variable width characters.
                child = (top_node[PARSER_GRAMMAR], cursor, top_node[PARSER_PRIOR], visual)
            elif index == 1:
                # Found end of current grammar section (an 'end').
                child = (
                    self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_GRAMMAR],
                    cursor + reg[1],
                    self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_PRIOR],
                    visual + reg[1],
                )
                cursor = child[PARSER_BEGIN]
                visual += reg[1]
                if subdata[reg[1] - 1] == "\n":
                    # This 'end' ends with a new line.
                    self.rows.append(len(self.parser_nodes))
            else:
                [
                    contains_grammar_index_limit,
                    next_grammar_index_limit,
                    error_index_limit,
                    keyword_index_limit,
                    type_index_limit,
                    special_index_limit,
                ] = self.parser_nodes[-1][PARSER_GRAMMAR]["index_limits"]
                if index < contains_grammar_index_limit:
                    # A new grammar within this grammar (a 'contains').
                    if subdata[reg[0]] == "\n":
                        # This 'begin' begins with a new line.
                        self.rows.append(len(self.parser_nodes))
                    prior_grammar = self.parser_nodes[-1][PARSER_GRAMMAR].get(
                        "match_grammars", []
                    )[index]
                    if prior_grammar["end"] is None:
                        # Found single regex match (a leaf grammar).
                        self.parser_nodes.append(
                            (
                                prior_grammar,
                                cursor + reg[0],
                                len(self.parser_nodes) - 1,
                                visual + reg[0],
                            )
                        )
                        # Resume the current grammar.
                        child = (
                            self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_GRAMMAR],
                            cursor + reg[1],
                            self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_PRIOR],
                            visual + reg[1],
                        )
                    else:
                        if prior_grammar.get("end_key"):
                            # A dynamic end tag.
                            here_key = re.search(
                                prior_grammar["end_key"], subdata[reg[0] :]
                            ).groups()[0]
                            markers = prior_grammar["markers"]
                            markers[1] = prior_grammar["end"].replace(
                                r"\0", re.escape(here_key)
                            )
                            prior_grammar["match_re"] = re.compile(
                                app.regex.join_re_list(markers)
                            )
                        child = (
                            prior_grammar,
                            cursor + reg[0],
                            len(self.parser_nodes) - 1,
                            visual + reg[0],
                        )
                    cursor += reg[1]
                    visual += reg[1]
                elif index < next_grammar_index_limit:
                    # A new grammar follows this grammar (a 'begin').
                    if subdata[reg[0]] == "\n":
                        # This 'begin' begins with a new line.
                        self.rows.append(len(self.parser_nodes))
                    prior_grammar = self.parser_nodes[-1][PARSER_GRAMMAR].get(
                        "match_grammars", []
                    )[index]
                    if prior_grammar.get("end_key"):
                        # A dynamic end tag.
                        here_key = re.search(
                            prior_grammar["end_key"], subdata[reg[0] :]
                        ).groups()[0]
                        markers = prior_grammar["markers"]
                        markers[1] = prior_grammar["end"].replace(
                            r"\0", re.escape(here_key)
                        )
                        prior_grammar["match_re"] = re.compile(
                            app.regex.join_re_list(markers)
                        )
                    child = (
                        prior_grammar,
                        cursor + reg[0],
                        len(self.parser_nodes) - 2,
                        visual + reg[0],
                    )
                    cursor += reg[1]
                    visual += reg[1]
                elif index < error_index_limit:
                    # A special doesn't change the node_index.
                    self.parser_nodes.append(
                        (
                            app_prefs.grammars["error"],
                            cursor + reg[0],
                            len(self.parser_nodes) - 1,
                            visual + reg[0],
                        )
                    )
                    # Resume the current grammar.
                    child = (
                        self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_GRAMMAR],
                        cursor + reg[1],
                        self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_PRIOR],
                        visual + reg[1],
                    )
                    cursor += reg[1]
                    visual += reg[1]
                elif index < keyword_index_limit:
                    # A keyword doesn't change the node_index.
                    self.parser_nodes.append(
                        (
                            app_prefs.grammars["keyword"],
                            cursor + reg[0],
                            len(self.parser_nodes) - 1,
                            visual + reg[0],
                        )
                    )
                    # Resume the current grammar.
                    child = (
                        self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_GRAMMAR],
                        cursor + reg[1],
                        self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_PRIOR],
                        visual + reg[1],
                    )
                    cursor += reg[1]
                    visual += reg[1]
                elif index < type_index_limit:
                    # A type doesn't change the node_index.
                    self.parser_nodes.append(
                        (
                            app_prefs.grammars["type"],
                            cursor + reg[0],
                            len(self.parser_nodes) - 1,
                            visual + reg[0],
                        )
                    )
                    # Resume the current grammar.
                    child = (
                        self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_GRAMMAR],
                        cursor + reg[1],
                        self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_PRIOR],
                        visual + reg[1],
                    )
                    cursor += reg[1]
                    visual += reg[1]
                elif index < special_index_limit:
                    # A special doesn't change the node_index.
                    self.parser_nodes.append(
                        (
                            app_prefs.grammars["special"],
                            cursor + reg[0],
                            len(self.parser_nodes) - 1,
                            visual + reg[0],
                        )
                    )
                    # Resume the current grammar.
                    child = (
                        self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_GRAMMAR],
                        cursor + reg[1],
                        self.parser_nodes[self.parser_nodes[-1][PARSER_PRIOR]][PARSER_PRIOR],
                        visual + reg[1],
                    )
                    cursor += reg[1]
                    visual += reg[1]
                else:
                    app.log.error("invalid grammar index")
            self.parser_nodes.append(child)
        self.resume_at_row = len(self.rows)

    def _print_last_node(self, msg):
        node = self.parser_nodes[-1]
        print(
            "_print_node",
            node[0]["name"],
            node[1],
            node[2],
            node[3],
            msg,
            repr(self.data),
        )

    def _print_node(self, node, msg):
        print("_print_node", node[0]["name"], node[1], node[2], node[3], msg)

    def debug_log(self, out, data):
        out("parser debug:")
        out("RowList ----------------", len(self.rows))
        for i, start in enumerate(self.rows):
            if i + 1 < len(self.rows):
                end = self.rows[i + 1]
            else:
                end = len(self.parser_nodes)
            out("row", i, "(line", str(i + 1) + ") index", start, "to", end)
            for node in self.parser_nodes[start:end]:
                if node is None:
                    out("a None")
                    continue
                node_begin = node[PARSER_BEGIN]
                out(
                    "  ParserNode %26s prior %4s, b%4d, v%4d, %s"
                    % (
                        node[PARSER_GRAMMAR].get("name", "None"),
                        node[PARSER_PRIOR],
                        node_begin,
                        node[PARSER_VISUAL],
                        repr(data[node_begin : node_begin + 15])[1:-1],
                    )
                )

    def debug_check_lines(self, out, data):
        """Debug test that all the lines were recognized by the parser. This is
        very slow, so it's normally disabled.
        """
        # Check that all the lines got identified.
        lines = data.split("\n")
        if out is not None:
            out(lines)
        assert len(lines) == self.row_count()
        for i, line in enumerate(lines):
            parsed_line, column_width = self.row_text_and_width(i)
            assert line == parsed_line, "\nexpected:{}\n  actual:{}".format(
                repr(line), repr(parsed_line)
            )
            parsed_line = self.row_text(i)
            assert line == parsed_line, f"\nexpected:{line}\n  actual:{parsed_line}"

            if out is not None:
                out("----------- ", line)
            pieced_line = ""
            k = 0
            grammar_index = 0
            while True:
                node, preceding, remaining, eol = self.grammar_at_index(
                    i, k, grammar_index
                )
                grammar_index += 1
                pieced_line += line[k - preceding : k + remaining]
                if out is not None:
                    out(i, preceding, remaining, i, k, pieced_line)
                if eol:
                    assert pieced_line == line, "\nexpected:{}\n  actual:{}".format(
                        repr(line), repr(pieced_line)
                    )
                    break
                k += remaining
