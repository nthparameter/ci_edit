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
"""Key bindings for the emacs-like editor."""

# For Python 2to3 support.

import curses
import curses.ascii
import os
import re

from app.curses_util import *
import app.controller
import app.log
import app.text_buffer

def parse_int(str):
    i = 0
    k = 0
    if len(str) > i and str[i] in ("+", "-"):
        i += 1
    k = i
    while len(str) > k and str[k].isdigit():
        k += 1
    if k > i:
        return int(str[:k])
    return 0

def test_parse_int():
    assert parse_int("0") == 0
    assert parse_int("0e") == 0
    assert parse_int("qwee") == 0
    assert parse_int("10") == 10
    assert parse_int("+10") == 10
    assert parse_int("-10") == -10
    assert parse_int("--10") == 0
    assert parse_int("--10") == 0

class EditText(app.controller.Controller):
    """An EditText is a base class for one-line controllers."""

    def __init__(self, view):
        app.controller.Controller.__init__(self, view, "EditText")
        self.document = None

    def set_text_buffer(self, text_buffer):
        text_buffer.lines = [""]
        self.command_set = {
            KEY_F1: self.info,
            CTRL_A: text_buffer.selection_all,
            CTRL_C: text_buffer.edit_copy,
            CTRL_H: text_buffer.backspace,
            KEY_BACKSPACE1: text_buffer.backspace,
            KEY_BACKSPACE2: text_buffer.backspace,
            KEY_BACKSPACE3: text_buffer.backspace,
            CTRL_Q: self.prg.quit,
            CTRL_S: self.save_document,
            CTRL_V: text_buffer.edit_paste,
            CTRL_X: text_buffer.edit_cut,
            CTRL_Y: text_buffer.redo,
            CTRL_Z: text_buffer.undo,
            # KEY_DOWN: text_buffer.cursor_down,
            KEY_LEFT: text_buffer.cursor_left,
            KEY_RIGHT: text_buffer.cursor_right,
            # KEY_UP: text_buffer.cursor_up,
        }

    def focus(self):
        app.log.info("EditText.focus", repr(self))
        self.command_default = self.text_buffer.insert_printable
        self.command_set = self.command_set

    def info(self):
        app.log.info("EditText command set")

    def save_document(self):
        app.log.info("save_document", self.document)
        if self.document and self.document.text_buffer:
            self.document.text_buffer.file_write()

    def unfocus(self):
        pass

class InteractiveOpener(EditText):
    """Open a file to edit."""

    def __init__(self, prg, view, text_buffer):
        EditText.__init__(self, prg, view, text_buffer)
        self.document = view.host
        app.log.info("xxxxx", self.document)
        command_set = self.command_set.copy()
        command_set.update(
            {
                KEY_ESCAPE: self.change_to_input_window,
                KEY_F1: self.info,
                CTRL_I: self.tab_complete_extend,
                CTRL_J: self.create_or_open,
                CTRL_N: self.create_or_open,
                CTRL_O: self.create_or_open,
                CTRL_Q: self.prg.quit,
            }
        )
        self.command_set = command_set

    def focus(self):
        app.log.info("InteractiveOpener.focus")
        EditText.focus(self)
        # Create a new text buffer to display dir listing.
        self.view.host.set_text_buffer(text_buffer.TextBuffer(self.prg))

    def info(self):
        app.log.info("InteractiveOpener command set")

    def create_or_open(self):
        app.log.info("create_or_open")
        expanded_path = os.path.abspath(os.path.expanduser(self.text_buffer.lines[0]))
        if not os.path.isdir(expanded_path):
            self.view.host.set_text_buffer(
                self.prg.buffer_manager.load_text_buffer(expanded_path), self.view.host
            )
        self.change_to_input_window()

    def maybe_slash(self, expanded_path):
        if (
            self.text_buffer.lines[0]
            and self.text_buffer.lines[0][-1] != "/"
            and os.path.isdir(expanded_path)
        ):
            self.text_buffer.insert("/")

    def tab_complete_first(self):
        """Find the first file that starts with the pattern."""
        dir_path, file_name = os.path.split(self.lines[0])
        found_once = ""
        for i in os.listdir(os.path.expandvars(os.path.expanduser(dir_path)) or "."):
            if i.startswith(file_name):
                if found_once:
                    # Found more than one match.
                    return
                file_name = os.path.join(dir_path, i)
                if os.path.isdir(file_name):
                    file_name += "/"
                self.lines[0] = file_name
                self.on_change()
                return

    def tab_complete_extend(self):
        """Extend the selection to match characters in common."""
        dir_path, file_name = os.path.split(self.text_buffer.lines[0])
        expanded_dir = os.path.expandvars(os.path.expanduser(dir_path)) or "."
        matches = []
        if not os.path.isdir(expanded_dir):
            return
        for i in os.listdir(expanded_dir):
            if i.startswith(file_name):
                matches.append(i)
            else:
                app.log.info("not", i)
        if len(matches) <= 0:
            self.maybe_slash(expanded_dir)
            self.on_change()
            return
        if len(matches) == 1:
            self.text_buffer.insert(matches[0][len(file_name) :])
            self.maybe_slash(os.path.join(expanded_dir, matches[0]))
            self.on_change()
            return

        def find_common_prefix_length(prefix_len):
            count = 0
            ch = None
            for match in matches:
                if len(match) <= prefix_len:
                    return prefix_len
                if not ch:
                    ch = match[prefix_len]
                if match[prefix_len] == ch:
                    count += 1
            if count and count == len(matches):
                return find_common_prefix_length(prefix_len + 1)
            return prefix_len

        prefix_len = find_common_prefix_length(len(file_name))
        self.text_buffer.insert(matches[0][len(file_name) : prefix_len])
        self.on_change()

    def set_file_name(self, path):
        self.text_buffer.lines = [path]
        self.text_buffer.pen_col = len(path)
        self.text_buffer.goal_col = self.text_buffer.pen_col

    def on_change(self):
        path = os.path.expanduser(os.path.expandvars(self.text_buffer.lines[0]))
        dir_path, file_name = os.path.split(path)
        dir_path = dir_path or "."
        app.log.info("O.on_change", dir_path, file_name)
        if os.path.isdir(dir_path):
            lines = []
            for i in os.listdir(dir_path):
                if i.startswith(file_name):
                    lines.append(i)
            if len(lines) == 1 and os.path.isfile(os.path.join(dir_path, file_name)):
                self.view.host.set_text_buffer(
                    self.view.program.buffer_manager.load_text_buffer(
                        os.path.join(dir_path, file_name), self.view.host
                    )
                )
            else:
                self.view.host.text_buffer.lines = [
                    os.path.abspath(os.path.expanduser(dir_path)) + ":"
                ] + lines
        else:
            self.view.host.text_buffer.lines = [
                os.path.abspath(os.path.expanduser(dir_path)) + ": not found"
            ]

class InteractiveFind(EditText):
    """Find text within the current document."""

    def __init__(self, prg, view, text_buffer):
        EditText.__init__(self, prg, view, text_buffer)
        self.document = view.host
        self.command_set.update(
            {
                KEY_ESCAPE: self.change_to_input_window,
                KEY_F1: self.info,
                CTRL_F: self.find_next,
                CTRL_J: self.change_to_input_window,
                CTRL_R: self.find_prior,
                # CTRL_S: self.replacement_text_edit,
                KEY_DOWN: self.find_next,
                KEY_MOUSE: self.save_event_change_to_host_window,
                KEY_UP: self.find_prior,
            }
        )
        self.height = 1

    def find_next(self):
        self.find_cmd = self.document.text_buffer.find_next

    def find_prior(self):
        self.find_cmd = self.document.text_buffer.find_prior

    def focus(self):
        # self.document.status_line.hide()
        # self.document.resize_by(-self.height, 0)
        # self.view.host.move_by(-self.height, 0)
        # self.view.host.resize_by(self.height-1, 0)
        EditText.focus(self)
        self.find_cmd = self.document.text_buffer.find
        selection = self.document.text_buffer.get_selected_text()
        if selection:
            self.text_buffer.selection_all()
            self.text_buffer.insert_lines(selection)
        self.text_buffer.selection_all()
        app.log.info("find tb", self.text_buffer.pen_col)

    def info(self):
        app.log.info("InteractiveFind command set")

    def on_change(self):
        app.log.info("InteractiveFind.on_change")
        search_for = self.text_buffer.lines[0]
        try:
            self.find_cmd(search_for)
        except re.error as e:
            self.error = e.message
        self.find_cmd = self.document.text_buffer.find

    # def replacement_text_edit(self):
    #  pass

    def unfocus(self):
        app.log.info("unfocus Find")
        # self.hide()

class InteractiveGoto(EditText):
    """Jump to a particular line number."""

    def __init__(self, prg, view, text_buffer):
        EditText.__init__(self, prg, view, text_buffer)
        self.document = view.host
        command_set = self.command_set.copy()
        command_set.update(
            {
                KEY_ESCAPE: self.change_to_input_window,
                KEY_F1: self.info,
                CTRL_J: self.change_to_input_window,
                KEY_MOUSE: self.save_event_change_to_host_window,
                ord("b"): self.goto_bottom,
                ord("h"): self.goto_halfway,
                ord("t"): self.goto_top,
            }
        )
        self.command_set = command_set

    def focus(self):
        app.log.info("InteractiveGoto.focus")
        self.text_buffer.selection_all()
        self.text_buffer.insert(str(self.document.text_buffer.pen_row + 1))
        self.text_buffer.selection_all()
        EditText.focus(self)

    def info(self):
        app.log.info("InteractiveGoto command set")

    def goto_bottom(self):
        self.cursor_move_to(len(self.document.text_buffer.lines), 0)
        self.change_to_input_window()

    def goto_halfway(self):
        self.cursor_move_to(len(self.document.text_buffer.lines) // 2 + 1, 0)
        self.change_to_input_window()

    def goto_top(self):
        self.cursor_move_to(1, 0)
        self.change_to_input_window()

    def cursor_move_to(self, row, col):
        text_buffer = self.document.text_buffer
        pen_row = min(max(row - 1, 0), len(text_buffer.lines) - 1)
        app.log.info("cursor_move_to row", row, pen_row)
        text_buffer.cursor_move(
            pen_row - text_buffer.pen_row,
            col - text_buffer.pen_col,
            col - text_buffer.goal_col,
        )

    def on_change(self):
        goto_line = 0
        line = self.text_buffer.parser.row_text(0)
        goto_line, goto_col = (line.split(",") + ["0", "0"])[:2]
        self.cursor_move_to(parse_int(goto_line), parse_int(goto_col))

    # def unfocus(self):
    #  self.hide()

class CiEdit(app.controller.Controller):
    """Keyboard mappings for ci."""

    def __init__(self, prg, text_buffer):
        app.controller.Controller.__init__(self, prg, None, "CiEdit")
        app.log.info("CiEdit.__init__")
        self.text_buffer = text_buffer
        self.command_set_main = {
            CTRL_SPACE: self.switch_to_command_set_cmd,
            CTRL_A: text_buffer.cursor_start_of_line,
            CTRL_B: text_buffer.cursor_left,
            KEY_LEFT: self.cursor_left,
            CTRL_C: self.edit_copy,
            CTRL_D: self.delete,
            CTRL_E: self.cursor_end_of_line,
            CTRL_F: self.cursor_right,
            KEY_RIGHT: self.cursor_right,
            CTRL_H: self.backspace,
            KEY_BACKSPACE1: self.backspace,
            KEY_BACKSPACE2: self.backspace,
            KEY_BACKSPACE3: self.backspace,
            CTRL_J: self.carriage_return,
            CTRL_K: self.delete_to_end_of_line,
            CTRL_L: self.win.refresh,
            CTRL_N: self.cursor_down,
            KEY_DOWN: self.cursor_down,
            CTRL_O: self.split_line,
            CTRL_P: self.cursor_up,
            KEY_UP: self.cursor_up,
            CTRL_V: self.edit_paste,
            CTRL_X: self.edit_cut,
            CTRL_Y: self.redo,
            CTRL_Z: self.undo,
            CTRL_BACKSLASH: self.change_to_cmd_mode,
            # ord('/'): self.switch_to_command_set_cmd,
        }

        self.command_set_cmd = {
            ord("a"): self.switch_to_command_set_application,
            ord("f"): self.switch_to_command_set_file,
            ord("s"): self.switch_to_command_set_select,
            ord(";"): self.switch_to_command_set_main,
            ord("'"): self.marker_place,
        }

        self.command_set_application = {
            ord("q"): self.prg.quit,
            ord("t"): self.test,
            ord("w"): self.file_write,
            ord(";"): self.switch_to_command_set_main,
        }

        self.command_set_file = {
            ord("o"): self.switch_to_command_set_file_open,
            ord("w"): self.file_write,
            ord(";"): self.switch_to_command_set_main,
        }

        self.command_set_file_open = {
            ord(";"): self.switch_to_command_set_main,
        }

        self.command_set_select = {
            ord("a"): self.selection_all,
            ord("b"): self.selection_block,
            ord("c"): self.selection_character,
            ord("l"): self.selection_line,
            ord("x"): self.selection_none,
            ord(";"): self.switch_to_command_set_main,
        }

        self.command_default = self.insert_printable
        self.command_set = self.command_set_main

    def switch_to_command_set_main(self, ignored=1):
        self.log("ci main", repr(self.prg))
        self.command_default = self.insert_printable
        self.command_set = self.command_set_main

    def switch_to_command_set_cmd(self):
        self.log("ci cmd")
        self.command_default = self.text_buffer.no_op
        self.command_set = self.command_set_cmd

    def switch_to_command_set_application(self):
        self.log("ci application")
        self.command_default = self.text_buffer.no_op
        self.command_set = self.command_set_application

    def switch_to_command_set_file(self):
        self.command_default = self.text_buffer.no_op
        self.command_set = self.command_set_file

    def switch_to_command_set_file_open(self):
        self.log("switch_to_command_set_file_open")
        self.command_default = self.path_insert_printable
        self.command_set = self.command_set_file_open

    def switch_to_main_and_do_command(self, ch):
        self.log("switch_to_main_and_do_command")
        self.switch_to_command_set_main()
        self.do_command(ch)

    def switch_to_command_set_select(self):
        self.log("ci select")
        self.command_default = self.SwitchToMainAndDoCommand
        self.command_set = self.command_set_select
        self.selection_character()

class EmacsEdit(app.controller.Controller):
    """Emacs is a common Unix based text editor. This keyboard mapping is
    similar to basic Emacs commands."""

    def __init__(self, view):
        app.controller.Controller.__init__(self, view, "EditText")

    def focus(self):
        app.log.info("EmacsEdit.focus")
        self.command_default = self.text_buffer.insert_printable
        self.command_set = self.command_set_main

    def on_change(self):
        pass

    def set_text_buffer(self, text_buffer):
        app.log.info("EmacsEdit.set_text_buffer")
        self.text_buffer = text_buffer
        self.command_set_main = {
            KEY_F1: self.info,
            CTRL_A: text_buffer.cursor_start_of_line,
            CTRL_B: text_buffer.cursor_left,
            KEY_LEFT: text_buffer.cursor_left,
            CTRL_D: text_buffer.delete,
            CTRL_E: text_buffer.cursor_end_of_line,
            CTRL_F: text_buffer.cursor_right,
            KEY_RIGHT: text_buffer.cursor_right,
            # CTRL_H: text_buffer.backspace,
            KEY_BACKSPACE1: text_buffer.backspace,
            KEY_BACKSPACE2: text_buffer.backspace,
            KEY_BACKSPACE3: text_buffer.backspace,
            CTRL_J: text_buffer.carriage_return,
            CTRL_K: text_buffer.delete_to_end_of_line,
            CTRL_L: self.view.host.refresh,
            CTRL_N: text_buffer.cursor_down,
            KEY_DOWN: text_buffer.cursor_down,
            CTRL_O: text_buffer.split_line,
            CTRL_P: text_buffer.cursor_up,
            KEY_UP: text_buffer.cursor_up,
            CTRL_X: self.switch_to_command_set_x,
            CTRL_Y: text_buffer.redo,
            CTRL_Z: text_buffer.undo,
        }
        self.command_set = self.command_set_main

        self.commandSet_X = {
            CTRL_C: self.prg.quit,
        }

    def info(self):
        app.log.info("EmacsEdit Command set main")
        app.log.info(repr(self))

    def switch_to_command_set_x(self):
        self.log("emacs x")
        self.command_set = self.commandSet_X
