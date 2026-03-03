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

import curses
import curses.ascii
import fcntl
import os
import signal
import struct
import sys
import termios
import unicodedata

import app.config

# Strings are found using the curses_key_name() function.
# Constants are found using the curses.getch() function.

# Tuple events are preceded by an escape (27).
BRACKETED_PASTE_BEGIN = (91, 50, 48, 48, 126)  # i.e. "[200~"
BRACKETED_PASTE_END = (91, 50, 48, 49, 126)  # i.e. "[201~"
BRACKETED_PASTE = (b"terminal_paste",)  # Pseudo event type.

UNICODE_INPUT = (b"unicode_input",)  # Pseudo event type.

CTRL_AT = b"^@"  # 0x00
CTRL_SPACE = b"^@"  # 0x00
CTRL_A = b"^A"  # 0x01
CTRL_B = b"^B"  # 0x02
CTRL_C = b"^C"  # 0x03
CTRL_D = b"^D"  # 0x04
CTRL_E = b"^E"  # 0x05
CTRL_F = b"^F"  # 0x06
CTRL_G = b"^G"  # 0x07
CTRL_H = b"^H"  # 0x08
CTRL_I = b"^I"  # 0x09
CTRL_J = b"^J"  # 0x0a
CTRL_K = b"^K"  # 0x0b
CTRL_L = b"^L"  # 0x0c
CTRL_M = b"^M"  # 0x0d
CTRL_N = b"^N"  # 0x0e
CTRL_O = b"^O"  # 0x0f
CTRL_P = b"^P"  # 0x10
CTRL_Q = b"^Q"  # 0x11
CTRL_R = b"^R"  # 0x12
CTRL_S = b"^S"  # 0x13
CTRL_T = b"^T"  # 0x14
CTRL_U = b"^U"  # 0x15
CTRL_V = b"^V"  # 0x16
CTRL_W = b"^W"  # 0x17
CTRL_X = b"^X"  # 0x18
CTRL_Y = b"^Y"  # 0x19
CTRL_Z = b"^Z"  # 0x1a
CTRL_OPEN_BRACKET = b"^["  # 0x1b
CTRL_BACKSLASH = b"^\\"  # 0x1c
CTRL_CLOSE_BRACKET = b"^]"  # 0x1d
CTRL_CARROT = b"^^"  # 0x1e
CTRL_UNDERBAR = b"^_"  # 0x1f
CTRL_BACKSPACE = b"^BACKSPACE"

KEY_ALT_A = 165
KEY_ALT_B = 171
KEY_ALT_C = 167
KEY_ALT_S = 159
KEY_ALT_SHIFT_PAGE_DOWN = b"NXT4"
KEY_ALT_SHIFT_PAGE_UP = b"PRV4"
KEY_BACKSPACE1 = curses.ascii.BS  # 8
KEY_BACKSPACE2 = curses.ascii.DEL  # 127
KEY_BACKSPACE3 = curses.KEY_BACKSPACE  # 263
KEY_BTAB = curses.KEY_BTAB
KEY_DELETE = curses.KEY_DC
KEY_END = curses.KEY_END
KEY_ESCAPE = curses.ascii.ESC
KEY_HOME = curses.KEY_HOME
KEY_PAGE_DOWN = curses.KEY_NPAGE
KEY_PAGE_UP = curses.KEY_PPAGE
KEY_SEND = curses.KEY_SEND
KEY_SHIFT_PAGE_DOWN = curses.KEY_SNEXT
KEY_SHIFT_PAGE_DOWN_STR = b"kNXT"
KEY_SHIFT_PAGE_UP = curses.KEY_SPREVIOUS
KEY_SHIFT_PAGE_UP_STR = b"kPRV"
KEY_SHOME = curses.KEY_SHOME

if sys.platform == "darwin":
    KEY_ALT_LEFT = (91, 49, 59, 57, 68)
    KEY_ALT_RIGHT = (91, 49, 59, 57, 67)
    KEY_ALT_SHIFT_LEFT = (
        91,
        49,
        59,
        49,
        48,
        68,
    )
    KEY_ALT_SHIFT_RIGHT = (
        91,
        49,
        59,
        49,
        48,
        67,
    )
else:
    KEY_ALT_LEFT = b"LFT3"
    KEY_ALT_RIGHT = b"RIT3"
    KEY_ALT_SHIFT_LEFT = b"LFT4"
    KEY_ALT_SHIFT_RIGHT = b"RIT4"

if "SSH_CLIENT" in os.environ:
    KEY_ALT_LEFT = (98,)  # Need a better way to sort this out.
    KEY_ALT_RIGHT = (102,)  # ditto

KEY_CTRL_DOWN = b"DN5"
KEY_CTRL_SHIFT_DOWN = b"DN6"
KEY_CTRL_LEFT = b"LFT5"
KEY_CTRL_SHIFT_LEFT = b"LFT6"
KEY_CTRL_RIGHT = b"RIT5"
KEY_CTRL_SHIFT_RIGHT = b"RIT6"
KEY_CTRL_UP = b"UP5"
KEY_CTRL_SHIFT_UP = b"UP6"

KEY_F1 = curses.KEY_F1
KEY_F2 = curses.KEY_F2
KEY_F3 = curses.KEY_F3
KEY_F4 = curses.KEY_F4
KEY_F5 = curses.KEY_F5
KEY_F6 = curses.KEY_F6
KEY_F7 = curses.KEY_F7
KEY_F8 = curses.KEY_F8
KEY_F9 = curses.KEY_F9
KEY_F10 = curses.KEY_F10
KEY_SHIFT_F1 = curses.KEY_F13
KEY_SHIFT_F2 = curses.KEY_F14
KEY_SHIFT_F3 = curses.KEY_F15
KEY_SHIFT_F4 = curses.KEY_F16
KEY_SHIFT_F5 = curses.KEY_F17
KEY_SHIFT_F6 = curses.KEY_F18
KEY_SHIFT_F7 = curses.KEY_F19
KEY_SHIFT_F8 = curses.KEY_F20
KEY_SHIFT_F9 = curses.KEY_F21
KEY_SHIFT_F10 = curses.KEY_F22

KEY_SHIFT_DOWN = curses.KEY_SF
KEY_DOWN = curses.KEY_DOWN
KEY_SHIFT_UP = curses.KEY_SR
KEY_UP = curses.KEY_UP
KEY_LEFT = curses.KEY_LEFT
KEY_SHIFT_LEFT = curses.KEY_SLEFT
KEY_RIGHT = curses.KEY_RIGHT
KEY_SHIFT_RIGHT = curses.KEY_SRIGHT

KEY_MOUSE = curses.KEY_MOUSE
KEY_RESIZE = curses.KEY_RESIZE

def mouse_button_name(button_state):
    """Curses debugging. Prints readable name for state of mouse buttons."""
    result = ""
    if button_state & curses.BUTTON1_RELEASED:
        result += "BUTTON1_RELEASED"
    if button_state & curses.BUTTON1_PRESSED:
        result += "BUTTON1_PRESSED"
    if button_state & curses.BUTTON1_CLICKED:
        result += "BUTTON1_CLICKED"
    if button_state & curses.BUTTON1_DOUBLE_CLICKED:
        result += "BUTTON1_DOUBLE_CLICKED"

    if button_state & curses.BUTTON2_RELEASED:
        result += "BUTTON2_RELEASED"
    if button_state & curses.BUTTON2_PRESSED:
        result += "BUTTON2_PRESSED"
    if button_state & curses.BUTTON2_CLICKED:
        result += "BUTTON2_CLICKED"
    if button_state & curses.BUTTON2_DOUBLE_CLICKED:
        result += "BUTTON2_DOUBLE_CLICKED"

    if button_state & curses.BUTTON3_RELEASED:
        result += "BUTTON3_RELEASED"
    if button_state & curses.BUTTON3_PRESSED:
        result += "BUTTON3_PRESSED"
    if button_state & curses.BUTTON3_CLICKED:
        result += "BUTTON3_CLICKED"
    if button_state & curses.BUTTON3_DOUBLE_CLICKED:
        result += "BUTTON3_DOUBLE_CLICKED"

    if button_state & curses.BUTTON4_RELEASED:
        result += "BUTTON4_RELEASED"
    if button_state & curses.BUTTON4_PRESSED:
        result += "BUTTON4_PRESSED"
    if button_state & curses.BUTTON4_CLICKED:
        result += "BUTTON4_CLICKED"
    if button_state & curses.BUTTON4_DOUBLE_CLICKED:
        result += "BUTTON4_DOUBLE_CLICKED"

    if button_state & curses.REPORT_MOUSE_POSITION:
        result += "REPORT_MOUSE_POSITION"

    if button_state & curses.BUTTON_SHIFT:
        result += " SHIFT"
    if button_state & curses.BUTTON_CTRL:
        result += " CTRL"
    if button_state & curses.BUTTON_ALT:
        result += " ALT"
    return result

def curses_key_name(key_code):
    try:
        return curses.keyname(key_code)
    except Exception:
        pass
    return None

def column_to_index(column, string):
    """If the visual cursor is on |column|, which index of the string is the
    cursor on?"""
    if app.config.strict_debug:
        assert isinstance(column, int)
        assert isinstance(string, unicode)
    if not string:
        return None
    index_limit = len(string) - 1
    col_cursor = 0
    index = 0
    for ch in string:
        col_cursor += char_width(ch, col_cursor)
        if col_cursor > column:
            break
        index += 1
        if index > index_limit:
            return None
    return index

def char_at_column(column, string):
    """If the visual cursor is on |column|, which index of the string is the
    cursor on?"""
    if app.config.strict_debug:
        assert isinstance(column, int)
        assert isinstance(string, unicode)
    index = column_to_index(column, string)
    if index is not None:
        return string[index]
    return None

def fit_to_rendered_width(column, width, string):
    """With |width| character cells (columns) available, how much of |string|
    can I render? The start |column| is required to calculate tab stops.

    The result can vary for double-wide characters, zero-width characters, and
    tabs. For plain, printable ASCII, the result will always be the lesser of
    |width| or len(string).
    """
    if app.config.strict_debug:
        assert isinstance(width, int)
        assert isinstance(string, unicode)
    index_limit = len(string)
    index = 0
    for i in string:
        cols = char_width(i, column)
        width -= cols
        column += cols
        if width < 0 or index >= index_limit:
            break
        index += 1
    return index

def rendered_find_iter(string, begin_col, end_col, char_groups, numbers, eol_spaces):
    """Get a slice (similar to `string[begin_col:end_col]`) based on the rendered
    width of the string.

    Note: char_groups cannot (currently) contain double width characters.

    Returns:
      tuple of (sub_str, column, index, id)
    """
    if app.config.strict_debug:
        assert isinstance(string, unicode)
        assert isinstance(begin_col, int)
        assert isinstance(end_col, int)
    column = 0
    index = 0
    limit = len(string)
    while index < limit:
        if column >= end_col:
            break
        c = string[index]
        if column >= begin_col:
            if numbers and c in "0123456789":
                sre = app.regex.RE_NUMBERS.match(string[index:])
                begin = index
                length = min(sre.regs[0][1], end_col - column)
                index += length
                yield string[begin:index], column, length, len(char_groups)
                column += length
            else:
                for id, group in enumerate(char_groups):
                    if c in group:
                        begin = index
                        while index < limit and string[index] in group:
                            index += 1
                        # if
                        yield string[begin:index], column, index - begin, id
                        column += index - begin
                        break
                else:
                    column += char_width(c, column)
                    index += 1
        else:
            column += char_width(c, column)
            index += 1
    if eol_spaces and limit and string[-1] == " ":
        index = limit - 1
        while index and string[index - 1] == " ":
            index -= 1
        yield string[index:], index, index, len(char_groups) + 1

def rendered_sub_str(string, begin_col, end_col=None):
    """
    Get a slice (similar to `string[begin_col:end_col]`) based on the rendered
    width of the string. If columns begin_col or end_col land in the middle of a
    double-wide character, a space is used to pad the result.

    Negative columns are not supported. (Just haven't implemented it).

    Args:
      string: The string to slice.
      begin_col: The first column of text (inclusive).
      end_col: The last column of text (exclusive). Omit parameter for
              end-of-line (similar to `string[begin_col:]`).

    Returns:
      unicode string
    """
    if end_col is None:
        end_col = sys.maxsize
    if app.config.strict_debug:
        assert isinstance(string, unicode)
        assert isinstance(begin_col, int)
        assert isinstance(end_col, int)
    column = 0
    i = 0
    limit = len(string)
    output = []
    while column < begin_col:
        if i >= limit:
            # The |string| is entirely before |begin_col|.
            return ""
        ch = string[i]
        column += char_width(ch, column)
        i += 1
        if column > begin_col:
            # Split the leading character.
            padding_width = column - begin_col
            output.append(" " * padding_width)
    while i < limit and column < end_col:
        ch = string[i]
        last_char_width = char_width(ch, column)
        column += last_char_width
        i += 1
        if column > end_col:
            # Split the trailing character.
            padding_width = min(end_col - (column - last_char_width), last_char_width - 1)
            output.append(" " * padding_width)
        else:
            if ch == "\t":
                output.append(" " * last_char_width)
            else:
                output.append(ch)
    return "".join(output)

if sys.version_info[0] == 2:

    def char_width(ch, column, tab_width=8):
        if ch == "\t":
            return tab_width - (column % tab_width)
        elif ch == "" or ch < " ":
            return 0
        elif ch < "ᄀ":
            # Optimization.
            return 1
        elif unicodedata.east_asian_width(ch) in ("F", r"W"):
            return 2
        return 1

    def is_double_width(ch):
        if ch == "" or ch < "ᄀ":
            # Optimization.
            return False
        width = unicodedata.east_asian_width(ch)
        if width in ("F", "W"):
            return True
        return False

    def is_zero_width(ch):
        return ch == "" or ch < " "  # or unicodedata.east_asian_width(ch) == "N"

else:

    def char_width(ch, column, tab_width=8):
        if ch == "\t":
            return tab_width - (column % tab_width)
        elif ch == "" or ch < " ":
            return 0
        elif ch < "ᄀ":
            # Optimization.
            return 1
        elif unicodedata.east_asian_width(ch) == "W":
            return 2
        return 1

    def is_double_width(ch):
        if ch == "" or ch < "ᄀ":
            # Optimization.
            return False
        return unicodedata.east_asian_width(ch) == "W"

    def is_zero_width(ch):
        return ch == "" or ch < " "  # or unicodedata.east_asian_width(ch) == "N"

def floor_col(column, line):
    """Round off the column so that it aligns with the start of a character.
    For lines without multi-column characters the result will equal |column|.
    If |column| is midway in a multi-column character the result will be less
    than |column| (i.e. rounding the column number downward).
    """
    if app.config.strict_debug:
        assert isinstance(column, int)
        assert isinstance(line, unicode)
    floor_column = 0
    for ch in line:
        width = char_width(ch, floor_column)
        if floor_column + width > column:
            return floor_column
        floor_column += width
    return floor_column

def prior_char_col(column, line):
    """Return the start column of the character before |column|."""
    if app.config.strict_debug:
        assert isinstance(column, int)
        assert isinstance(line, unicode)
    if column == 0:
        return None
    prior_column = 0
    for ch in line:
        width = char_width(ch, prior_column)
        if prior_column + width >= column:
            return prior_column
        prior_column += width
    return None

def column_width(string):
    """When rendering |string| how many character cells will be used? For ASCII
    characters this will equal len(string). For many Chinese characters and
    emoji the value will be greater than len(string), since many of them use two
    cells.
    """
    if app.config.strict_debug:
        assert isinstance(string, unicode)
    width = 0
    for i in string:
        width += char_width(i, width)
    return width

def wrap_lines(lines, indent, width):
    """Word wrap lines of text.

    Args:
      lines (list of unicode): input text.
      indent (unicode): will be added as a prefix to each line of output.
      width (int): is the column limit for the strings. Each double-wide
        character counts as two columns.

    Returns:
      List of strings
    """
    if app.config.strict_debug:
        assert isinstance(lines, tuple), repr(lines)
        assert len(lines) == 0 or isinstance(lines[0], unicode)
        assert isinstance(indent, unicode), repr(path)
        assert isinstance(width, int), repr(int)
    # There is a textwrap library in Python, but I was having trouble getting it
    # to do exactly what I desired. It may be useful to revisit textwrap later.
    words = " ".join(lines).split()
    output = [indent]
    indent_len = column_width(indent)
    index = 0
    while index < len(words):
        line_len = column_width(output[-1])
        word = words[index]
        word_len = column_width(word)
        if line_len == indent_len and line_len + word_len < width:
            output[-1] += word
        elif line_len + word_len + 1 < width:
            output[-1] += " " + word
        else:
            output.append(indent + word)
        index += 1
    return output

# This is built-in in Python 3.
# In Python 2 it's done by hand.
def terminal_size():
    h, w = struct.unpack(
        b"HHHH", fcntl.ioctl(0, termios.TIOCGWINSZ, struct.pack(b"HHHH", 0, 0, 0, 0))
    )[:2]
    return h, w

def hack_curses_fixes():
    if sys.platform == "darwin":

        def window_changed_handler(signum, frame):
            curses.ungetch(curses.KEY_RESIZE)

        signal.signal(signal.SIGWINCH, window_changed_handler)

    def wake_getch(signum, frame):
        curses.ungetch(0)

    signal.signal(signal.SIGUSR1, wake_getch)
