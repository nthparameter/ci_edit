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

try:
    unicode
except NameError:
    unicode = str
    unichr = chr

import curses

import app.curses_util
import app.log
import app.window

class DebugWindow(app.window.ActiveWindow):
    def __init__(self, program, host):
        app.window.ActiveWindow.__init__(self, program, host)

    def debug_draw(self, program, win):
        """Draw real-time debug information to the screen."""
        textBuffer = win.textBuffer
        self.writeLineRow = 0
        intent = "noIntent"
        if hasattr(win, "userIntent"):
            intent = win.userIntent
        color = program.color.get("debug_window")
        self.write_line(
            "   cRow %3d    cCol %2d goal_col %2d  %s"
            % (
                win.textBuffer.pen_row,
                win.textBuffer.pen_col,
                win.textBuffer.goal_col,
                intent,
            ),
            color,
        )
        self.write_line(
            "   pRow %3d    pCol %2d chRow %4d"
            % (textBuffer.pen_row, textBuffer.pen_col, textBuffer.debug_upper_changed_row),
            color,
        )
        self.write_line(
            " mkrRow %3d  mkrCol %2d sm %d"
            % (textBuffer.marker_row, textBuffer.marker_col, textBuffer.selectionMode),
            color,
        )
        self.write_line(
            "scrlRow %3d scrlCol %2d lines %3d"
            % (win.scrollRow, win.scrollCol, textBuffer.parser.row_count()),
            color,
        )
        y, x = win.top, win.left
        maxRow, maxCol = win.rows, win.cols
        self.write_line(
            "y %2d x %2d maxRow %d maxCol %d baud %d color %d"
            % (y, x, maxRow, maxCol, curses.baudrate(), curses.can_change_color()),
            color,
        )
        screenRows, screenCols = program.cursesScreen.getmaxyx()
        self.write_line(
            "scr rows %d cols %d mlt %f/%f pt %f"
            % (
                screenRows,
                screenCols,
                program.mainLoopTime,
                program.mainLoopTimePeak,
                textBuffer.parser_time,
            ),
            color,
        )
        self.write_line(
            "ch %3s %s"
            % (program.ch, app.curses_util.curses_key_name(program.ch) or "UNKNOWN"),
            color,
        )
        self.write_line(f"win {win!r}", color)
        self.write_line(f"foc {program.programWindow.focusedWindow!r}", color)
        self.write_line(f"tb {textBuffer!r}", color)
        (id, mouseCol, mouseRow, mouseZ, bState) = program.debugMouseEvent
        self.write_line(
            "mouse id %d, mouseCol %d, mouseRow %d, mouseZ %d"
            % (id, mouseCol, mouseRow, mouseZ),
            color,
        )
        self.write_line(
            "bState %s %d" % (app.curses_util.mouse_button_name(bState), bState), color
        )
        self.write_line(f"start_and_end {textBuffer.start_and_end()!r}", color)

class DebugUndoWindow(app.window.ActiveWindow):
    def __init__(self, program, host):
        app.window.ActiveWindow.__init__(self, program, host)

    def debug_undo_draw(self, win):
        """Draw real-time debug information to the screen."""
        textBuffer = win.textBuffer
        self.writeLineRow = 0
        # Display some of the redo chain.
        colorPrefs = win.program.color
        redoColorA = colorPrefs.get(100)
        self.write_line(
            "procTemp %d temp %r"
            % (
                textBuffer.process_temp_change,
                textBuffer.tempChange,
            ),
            redoColorA,
        )
        self.write_line(
            "redoIndex %3d savedAt %3d depth %3d"
            % (
                textBuffer.redoIndex,
                textBuffer.saved_at_redo_index,
                len(textBuffer.redo_chain),
            ),
            redoColorA,
        )
        redoColorB = colorPrefs.get(101)
        split = 8
        for i in range(textBuffer.redoIndex - split, textBuffer.redoIndex):
            text = i >= 0 and repr(textBuffer.redo_chain[i]) or ""
            self.write_line(unicode(text), redoColorB)
        redoColorC = colorPrefs.get(1)
        for i in range(textBuffer.redoIndex, textBuffer.redoIndex + split - 1):
            text = i < len(textBuffer.redo_chain) and textBuffer.redo_chain[i] or ""
            self.write_line(unicode(text), redoColorC)
