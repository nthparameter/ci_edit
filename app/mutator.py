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

import os
import re

import app.buffer_file
from app.curses_util import column_width
import app.log
import app.selectable

# If a change is in |noOpInstructions| then it has no real effect.
noOpInstructions = set(
    [
        ("m", (0, 0, 0, 0, 0)),
    ]
)

def add_vectors(a, b):
    """Add two list-like objects, pair-wise."""
    return tuple([a[i] + b[i] for i in range(len(a))])

class Mutator(app.selectable.Selectable):
    """Track and enact changes to a body of text."""

    def __init__(self, program):
        app.selectable.Selectable.__init__(self, program)
        self.__compoundChange = []
        # |old_redo_index| is used to store the redo index before an action
        # occurs, so we know where to insert the compound change.
        self.old_redo_index = 0
        self.debug_redo = False
        self.find_re = None
        self.find_back_re = None
        self.file_extension = None
        self.full_path = ""
        self.file_stat = None
        self.goal_col = 0
        self.is_read_only = False
        self.pen_grammar = None
        self.relativePath = ""
        self.redo_chain = []
        # |tempChange| is used to store cursor view actions without trimming
        # redo_chain.
        self.tempChange = None
        # |process_temp_change| is True if tempChange is not None and needs to be
        # processed.
        self.process_temp_change = False
        # |stall_next_redo| is True if the next call to redo() should do nothing.
        self.stall_next_redo = False
        # |redoIndex| may be equal to len(self.redo_chain) (must be <=).
        self.redoIndex = 0
        # |saved_at_redo_index| may be > len(self.redo_chain).
        self.saved_at_redo_index = 0
        self.should_reparse = False

    def compound_change_push(self):
        # app.log.info('compound_change_push')
        if self.__compoundChange:
            self.redoIndex = self.old_redo_index
            self.redo_chain = self.redo_chain[: self.redoIndex]
            changes = tuple(self.__compoundChange)
            change = changes[0]
            handledChange = False
            # Combine changes. Assumes d, i, n, and m consist of only 1 change.
            if (
                len(self.redo_chain)
                and self.redo_chain[-1][0][0] == change[0]
                and len(self.redo_chain[-1]) == 1
            ):
                if change[0] in ("d", "i"):
                    change = (change[0], self.redo_chain[-1][0][1] + change[1])
                    self.redo_chain[-1] = (change,)
                    handledChange = True
                elif change[0] == "f":
                    # Fences have no arguments to merge.
                    handledChange = True
                elif change[0] == "n":
                    newCursorChange = change[2]
                    newCarriageReturns = change[1]
                    oldCursorChange = self.redo_chain[-1][0][2]
                    oldCarriageReturns = self.redo_chain[-1][0][1]
                    change = (
                        change[0],
                        oldCarriageReturns + newCarriageReturns,
                        ("m", add_vectors(newCursorChange[1], oldCursorChange[1])),
                    )
                    self.redo_chain[-1] = (change,)
                    handledChange = True
                elif change[0] == "m":
                    change = (
                        change[0],
                        add_vectors(self.redo_chain[-1][0][1], change[1]),
                    )
                    if change in noOpInstructions:
                        self.redoIndex -= 1
                        self.redo_chain.pop()
                    else:
                        self.redo_chain[-1] = (change,)
                    handledChange = True
            if not handledChange:
                self.redo_chain.append(changes)
                self.redoIndex += 1
        self.__compoundChange = []
        self.old_redo_index = self.redoIndex

    def cursor_grammar_name(self):
        """inefficient test hack. wip on parser"""
        if not self.parser:
            return "no parser"
        index = self.parser.grammar_index_from_row_col(self.pen_row, self.pen_col)
        self.pen_grammar = self.parser.grammar_at_index(self.pen_row, self.pen_col, index)[
            0
        ]
        if self.pen_grammar is None:
            return "None"
        return self.pen_grammar.grammar.get("name", "unknown")

    def is_dirty(self):
        """Whether the buffer contains non-trivial changes since the last save."""
        clean = self.saved_at_redo_index >= 0 and (
            self.saved_at_redo_index == self.redoIndex
            or (
                self.redoIndex + 1 == self.saved_at_redo_index
                and self.redoIndex < len(self.redo_chain)
                and self.redo_chain[self.redoIndex][0] == "m"
            )
            or (
                self.redoIndex - 1 == self.saved_at_redo_index
                and self.redoIndex > 0
                and self.redo_chain[self.redoIndex - 1][0] == "m"
            )
        )
        return not clean

    def is_safe_to_write(self):
        """Determine whether writing the file to self.full_path is likely to
        overwrite data.

        Returns true if the file is not yet written or if the file has not been
        changed since it was read.
        """
        if not os.path.exists(self.full_path):
            return True
        if self.file_stat is None:
            return False
        s1 = os.stat(self.full_path)
        s2 = self.file_stat
        if 0:
            app.log.info("st_mode", s1.st_mode, s2.st_mode)
            app.log.info("st_ino", s1.st_ino, s2.st_ino)
            app.log.info("st_dev", s1.st_dev, s2.st_dev)
            app.log.info("st_uid", s1.st_uid, s2.st_uid)
            app.log.info("st_gid", s1.st_gid, s2.st_gid)
            app.log.info("st_size", s1.st_size, s2.st_size)
            app.log.info("st_mtime", s1.st_mtime, s2.st_mtime)
            app.log.info("st_ctime", s1.st_ctime, s2.st_ctime)
        return (
            s1.st_mode == s2.st_mode
            and s1.st_ino == s2.st_ino
            and s1.st_dev == s2.st_dev
            and s1.st_uid == s2.st_uid
            and s1.st_gid == s2.st_gid
            and s1.st_size == s2.st_size
            and s1.st_mtime == s2.st_mtime
            and s1.st_ctime == s2.st_ctime
        )

    def set_file_path(self, path):
        """Set the location where this file will be written.

        `path` may be full, relative, or contain env vars.
        """
        self.full_path = app.buffer_file.expand_full_path(path)

    def __do_move_lines(self, begin, end, to):
        lines = self.parser.text_range(begin, 0, end, 0)
        self.parser.delete_range(begin, 0, end, 0)
        count = end - begin
        if begin < to:
            assert end < to
            assert self.pen_row < to
            to -= count
            self.pen_row -= count
            if self.selectionMode != app.selectable.SELECTION_NONE:
                assert self.marker_row < to + count
                assert self.marker_row >= count
                self.marker_row -= count
        else:
            assert end > to
            assert self.pen_row >= to
            self.pen_row += count
            if self.selectionMode != app.selectable.SELECTION_NONE:
                assert self.marker_row >= to
                self.marker_row += count
        self.parser.insert_lines(to, 0, lines.split("\n"))

    def __do_vertical_insert(self, change):
        text, row, endRow, col = change[1]
        self.parser.insert_block(row, col, [text] * (endRow - row + 1))

    def __do_vertical_delete(self, change):
        text, row, endRow, col = change[1]
        self.parser.delete_block(row, col, endRow, col + len(text))

    def __redo_move(self, change):
        assert self.pen_row + change[1][0] >= 0, f"{self.pen_row} {change[1][0]}"
        assert self.pen_col + change[1][1] >= 0, f"{self.pen_col} {change[1][1]}"
        self.pen_row += change[1][0]
        self.pen_col += change[1][1]
        self.marker_row += change[1][2]
        self.marker_col += change[1][3]
        self.selectionMode += change[1][4]

    def print_redo_state(self, out):
        out("---- Redo State begin ----")
        out(
            "procTemp %d temp %r"
            % (
                self.process_temp_change,
                self.tempChange,
            )
        )
        out(
            "redoIndex %3d savedAt %3d depth %3d"
            % (self.redoIndex, self.saved_at_redo_index, len(self.redo_chain))
        )
        index = len(self.redo_chain)
        while index > 0:
            if index == self.redoIndex:
                out("  -----> next redo ^; next undo v")
            if index == self.saved_at_redo_index:
                out("  <saved>")
            index -= 1
            out(f"    {repr(self.redo_chain[index])}")
        out("---- Redo State end ----")

    def redo(self):
        """Replay the next action on the redo_chain."""
        assert 0 <= self.redoIndex <= len(self.redo_chain)
        if self.stall_next_redo:
            self.stall_next_redo = False
            return
        if self.process_temp_change:
            self.process_temp_change = False
            self.__redo_move(self.tempChange)
            self.update_basic_scroll_position()
            return
        if self.tempChange:
            self.__undo_move(self.tempChange)
            self.tempChange = None
            self.update_basic_scroll_position()
        while self.redoIndex < len(self.redo_chain):
            changes = self.redo_chain[self.redoIndex]
            self.redoIndex += 1
            for change in changes:
                self.__redo_change(change)
            # Stop redoing if we redo a non-trivial action
            if not (
                (changes[0][0] == "f" or changes[0][0] == "m") and len(changes) == 1
            ):
                self.should_reparse = True
                break
        self.update_basic_scroll_position()

    def __redo_change(self, change):
        if change[0] == "b":  # Redo backspace.
            self.pen_row, self.pen_col = self.parser.backspace(self.pen_row, self.pen_col)
        elif change[0] == "bw":  # Redo backspace word.
            width = column_width(change[1])
            self.parser.delete_range(
                self.pen_row, self.pen_col - width, self.pen_row, self.pen_col
            )
            self.pen_col -= width
        elif change[0] == "d":  # Redo delete character.
            self.parser.delete_char(self.pen_row, self.pen_col)
        elif change[0] == "dr":  # Redo delete range.
            self.do_delete(*change[1])
        elif change[0] == "ds":  # Redo delete selection.
            self.do_delete_selection()
        elif change[0] == "f":  # Redo fence.
            pass
        elif change[0] == "i":  # Redo insert.
            self.parser.insert(self.pen_row, self.pen_col, change[1])
            self.pen_col += column_width(change[1])
            self.goal_col = self.pen_col
        elif change[0] == "j":  # Redo join lines (delete \n).
            self.parser.delete_char(self.pen_row, self.pen_col)
        elif change[0] == "ld":  # Redo line diff.
            assert False  # Not used.
            lines = []
            index = 0
            for ii in change[1]:
                if type(ii) is type(0):
                    for line in self.parser.textLines(index, index + ii):
                        lines.append(line)
                    index += ii
                elif ii[0] == "+":
                    lines.append(ii[2:])
                elif ii[0] == "-":
                    index += 1
            self.parser.data = lines.join("\n")
            firstChangedRow = change[1][0] if type(change[1][0]) is type(0) else 0
        elif change[0] == "m":  # Redo move
            self.__redo_move(change)
        elif change[0] == "ml":  # Redo move lines
            begin, end, to = change[1]
            self.__do_move_lines(begin, end, to)
        elif change[0] == "n":  # Redo split lines (insert \n).
            self.parser.insert(self.pen_row, self.pen_col, "\n")
            self.__redo_move(change[2])
        elif change[0] == "v":  # Redo paste.
            self.insert_lines(change[1])
        elif change[0] == "vb":  # Redo vertical backspace.
            assert False  # Not yet used.
            width = column_width(change[1][0])
            self.parser.delete_block(
                self.pen_row,
                self.pen_col - width,
                self.pen_row + len(change[1]),
                self.pen_col,
            )
            self.pen_col -= width
        elif change[0] == "vd":  # Redo vertical delete.
            self.__do_vertical_delete(change)
        elif change[0] == "vi":  # Redo vertical insert.
            self.__do_vertical_insert(change)
        else:
            app.log.info("ERROR: unknown redo.")
        return False

    def redo_add_change(self, change):
        """
        Push a change onto the end of the redo_chain. Call redo() to enact the
        change.
        """
        if app.config.strict_debug:
            assert isinstance(change, tuple), change
        if self.debug_redo:
            app.log.info("redo_add_change", change)
        # Handle new trivial actions, which are defined as standalone cursor
        # moves.
        if change[0] == "m" and not self.__compoundChange:
            if self.tempChange:
                # Combine new change with the existing tempChange.
                change = (change[0], add_vectors(self.tempChange[1], change[1]))
                self.__undo_change(self.tempChange)
                self.__tempChange = change
            if change in noOpInstructions:
                self.stall_next_redo = True
                self.process_temp_change = False
                self.tempChange = None
                self.update_basic_scroll_position()
                return
            self.process_temp_change = True
            self.tempChange = change
        else:
            # Trim and combine main redo_chain with tempChange
            # if there is a non-trivial action.
            # We may lose the saved at when trimming.
            if self.redoIndex < self.saved_at_redo_index:
                self.saved_at_redo_index = -1
            self.redo_chain = self.redo_chain[: self.redoIndex]
            if self.tempChange:
                # If previous action was a cursor move, we can merge it with
                # tempChange.
                if (
                    len(self.redo_chain)
                    and self.redo_chain[-1][0][0] == "m"
                    and len(self.redo_chain[-1]) == 1
                ):
                    combinedChange = (
                        "m",
                        add_vectors(self.tempChange[1], self.redo_chain[-1][0][1]),
                    )
                    if combinedChange in noOpInstructions:
                        self.redo_chain.pop()
                        self.redoIndex -= 1
                        self.old_redo_index -= 1
                    else:
                        self.redo_chain[-1] = (combinedChange,)
                else:
                    self.redo_chain.append((self.tempChange,))
                    self.redoIndex += 1
                    self.old_redo_index += 1
                self.tempChange = None
            # Accumulating changes together as a unit.
            self.__compoundChange.append(change)
            self.redo_chain.append((change,))
        if self.debug_redo:
            app.log.info("--- redoIndex", self.redoIndex)
            for i, c in enumerate(self.redo_chain):
                app.log.info("%2d:" % i, repr(c))
            app.log.info("tempChange", repr(self.tempChange))

    def __undo_move(self, change):
        """Undo the action of a cursor move"""
        self.pen_row -= change[1][0]
        self.pen_col -= change[1][1]
        self.marker_row -= change[1][2]
        self.marker_col -= change[1][3]
        self.selectionMode -= change[1][4]
        assert self.pen_row >= 0, self.pen_row
        assert self.pen_col >= 0, self.pen_col

    def undo(self):
        """Undo a set of redo nodes."""
        assert 0 <= self.redoIndex <= len(self.redo_chain)
        # If tempChange is active, undo it first to fix cursor position.
        if self.tempChange:
            self.__undo_move(self.tempChange)
            self.tempChange = None
        while self.redoIndex > 0:
            self.redoIndex -= 1
            changes = self.redo_chain[self.redoIndex]
            if self.debug_redo:
                app.log.info("undo", self.redoIndex, repr(changes))
            if (changes[0][0] == "f" or changes[0][0] == "m") and len(changes) == 1:
                # Undo if the last edit was a cursor move.
                self.__undo_change(changes[0])
            else:
                self.should_reparse = True
                # Undo previous non-trivial edit
                for change in reversed(changes):
                    self.__undo_change(change)
                break
        self.process_temp_change = False

    def __undo_change(self, change):
        if change[0] == "b":
            self.parser.insert(self.pen_row, self.pen_col, change[1])
            position = self.parser.next_char_row_col(self.pen_row, self.pen_col)
            if position is not None:
                self.pen_row += position[0]
                self.pen_col += position[1]
        elif change[0] == "bw":  # Undo backspace word.
            self.parser.insert(self.pen_row, self.pen_col, change[1])
            self.pen_col += column_width(change[1])
        elif change[0] == "d":
            self.parser.insert(self.pen_row, self.pen_col, change[1])
        elif change[0] == "dr":  # Undo delete range.
            self.insert_lines_at(
                change[1][0],
                change[1][1],
                change[2],
                app.selectable.SELECTION_CHARACTER,
            )
        elif change[0] == "ds":  # Undo delete selection.
            self.insert_lines(change[1])
        elif change[0] == "f":  # Undo fence.
            pass
        elif change[0] == "i":  # Undo insert.
            width = column_width(change[1])
            self.parser.delete_range(
                self.pen_row, self.pen_col - width, self.pen_row, self.pen_col
            )
            self.pen_col -= width
            self.goal_col = self.pen_col
        elif change[0] == "j":  # Undo join lines.
            self.parser.insert(self.pen_row, self.pen_col, "\n")
        elif change[0] == "ld":  # Undo line diff.
            assert False  # Not used.
            lines = []
            index = 0
            for ii in change[1]:
                if type(ii) is type(0):
                    for line in self.parser.textLines(index, index + ii):
                        lines.append(line)
                    index += ii
                elif ii[0] == "+":
                    index += 1
                elif ii[0] == "-":
                    lines.append(ii[2:])
            self.parser.data = lines.join("\n")
            firstChangedRow = change[1][0] if type(change[1][0]) is type(0) else 0
        elif change[0] == "m":
            self.__undo_move(change)
        elif change[0] == "ml":
            # Undo move lines
            begin, end, to = change[1]
            count = end - begin
            if begin < to:
                self.__do_move_lines(to - 1, to + count - 1, begin + count - 1)
            else:
                self.__do_move_lines(to, to + count, begin + count)
        elif change[0] == "n":
            # Undo split lines.
            self.__undo_move(change[2])
            self.parser.backspace(self.pen_row + 1, 0)
        elif change[0] == "v":  # undo paste
            clip = change[1]
            if len(clip) == 1:
                self.parser.delete_range(
                    self.pen_row,
                    self.pen_col,
                    self.pen_row + len(clip) - 1,
                    self.pen_col + len(clip[-1]),
                )
            else:
                self.parser.delete_range(
                    self.pen_row, self.pen_col, self.pen_row + len(clip) - 1, len(clip[-1])
                )
        elif change[0] == "vb":  # Undo vertical backspace.
            assert False  # Not yet used.
            self.parser.insert_block(self.pen_row, self.pen_col, change[1])
            self.pen_col += column_width(change[1][0])
        elif change[0] == "vd":  # Undo vertical delete
            self.__do_vertical_insert(change)
        elif change[0] == "vi":  # Undo vertical insert
            self.__do_vertical_delete(change)
        else:
            app.log.info("ERROR: unknown undo.")

    def update_basic_scroll_position(self):
        pass
