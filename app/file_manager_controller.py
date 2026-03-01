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

try:
    unicode
except NameError:
    unicode = str
    unichr = chr

import os
import re
import time

import app.buffer_file
import app.config
import app.controller
import app.string

class DirectoryListController(app.controller.Controller):
    """Gather and prepare file directory information."""

    def __init__(self, view):
        if app.config.strict_debug:
            assert self is not view
        app.controller.Controller.__init__(self, view, "DirectoryListController")
        self.filter = None
        self.shown_directory = None

    def focus(self):
        self.on_change()
        app.controller.Controller.focus(self)

    def info(self):
        app.log.info("DirectoryListController command set")

    def on_change(self):
        pathInput = self.view.parent.pathWindow.controller.decoded_path()
        if self.shown_directory == pathInput:
            return
        self.shown_directory = pathInput
        app_prefs = self.view.program.prefs
        full_path, openToRow, openToColumn = app.buffer_file.path_row_column(
            pathInput, app_prefs.editor["baseDirEnv"]
        )
        full_path = app.buffer_file.expand_full_path(full_path)
        dirPath = full_path
        fileName = ""
        if len(pathInput) > 0 and pathInput[-1] != os.sep:
            dirPath, fileName = os.path.split(full_path)
            self.view.textBuffer.find_re = re.compile("()^" + re.escape(fileName))
        else:
            self.view.textBuffer.find_re = None
        dirPath = dirPath or "."
        if os.path.isdir(dirPath):
            showDotFiles = app_prefs.editor["filesShowDotFiles"]
            showSizes = app_prefs.editor["filesShowSizes"]
            showModified = app_prefs.editor["filesShowModifiedDates"]

            sortByName = app_prefs.editor["filesSortAscendingByName"]
            sortBySize = app_prefs.editor["filesSortAscendingBySize"]
            sortByModifiedDate = app_prefs.editor["filesSortAscendingByModifiedDate"]

            lines = []
            try:
                fileLines = []
                dirContents = os.listdir(dirPath)
                for dirItem in dirContents:
                    if not showDotFiles and dirItem[0] == ".":
                        continue
                    if self.filter is not None and not dirItem.startswith(self.filter):
                        continue
                    full_path = os.path.join(dirPath, dirItem)
                    if os.path.isdir(full_path):
                        dirItem += os.path.sep
                    iSize = None
                    iModified = 0
                    if showSizes and os.path.isfile(full_path):
                        iSize = os.path.getsize(full_path)
                    if showModified:
                        iModified = os.path.getmtime(full_path)
                    # Handle \r and similar characters in file paths.
                    encodedPath = app.string.path_encode(dirItem)
                    fileLines.append([encodedPath, iSize, iModified, dirItem])
                if sortBySize is not None:
                    # Sort by size.
                    fileLines.sort(
                        reverse=not sortBySize,
                        key=lambda x: x[1] if x[1] is not None else -1,
                    )
                elif sortByModifiedDate is not None:
                    # Sort by modification date.
                    fileLines.sort(reverse=not sortByModifiedDate, key=lambda x: x[2])
                else:
                    fileLines.sort(
                        reverse=not sortByName, key=lambda x: unicode.lower(x[0])
                    )
                lines = [
                    "%-40s  %16s  %24s"
                    % (
                        i[0],
                        "%s bytes" % (i[1],) if i[1] is not None else "",
                        time.strftime("%c", time.localtime(i[2])) if i[2] else "",
                    )
                    for i in fileLines
                ]
                self.view.contents = [i[3] for i in fileLines]
            except OSError as e:
                lines = ["Error opening directory."]
                lines.append(unicode(e))
            clip = ["./", "../"] + lines
        else:
            clip = [dirPath + ": not found"]
        self.view.textBuffer.replace_lines(tuple(clip))
        self.view.textBuffer.parse_screen_maybe()
        self.view.textBuffer.pen_row = 0
        self.view.textBuffer.pen_col = 0
        self.view.textBuffer.goal_col = 0
        self.view.scrollRow = 0
        self.view.scrollCol = 0
        self.filter = None

    def perform_open(self):
        self.open_file_or_dir(self.textBuffer.pen_row)

    def open_file_or_dir(self, row):
        if app.config.strict_debug:
            assert isinstance(row, int)
        path = self.path_for_row(row)
        # Clear the shown directory to trigger a refresh.
        self.shown_directory = None
        self.view.parent.pathWindow.controller.set_encoded_path(path)
        self.view.host.controller.perform_primary_action()

    def current_directory(self):
        pathController = self.view.parent.pathWindow.controller
        path = pathController.decoded_path()
        if len(path) > 0 and path[-1] != os.path.sep:
            path = os.path.dirname(path)
            # Test that path is non-empty and there's more than just a '/'.
            if len(path) > len(os.path.sep):
                path += os.path.sep
        if app.config.strict_debug:
            assert isinstance(path, unicode)
        return path

    def pass_default_to_path_input(self, ch, meta):
        pathInput = self.find_and_change_to("pathWindow")
        pathInput.controller.do_command(ch, meta)

    def path_for_row(self, row):
        if app.config.strict_debug:
            assert isinstance(row, int)
            assert row >= 0, row
        path = self.current_directory()
        if row == 0:
            return path + "./"
        elif row == 1:
            return path + "../"
        return path + self.view.contents[row - 2]

    def option_changed(self, name, value):
        self.shown_directory = None
        self.on_change()

    def set_filter(self, listFilter):
        self.filter = listFilter
        self.shown_directory = None  # Cause a refresh.

class FileManagerController(app.controller.Controller):
    """Create or open files."""

    def __init__(self, view):
        app.controller.Controller.__init__(self, view, "FileManagerController")

    def perform_primary_action(self):
        self.view.pathWindow.controller.perform_primary_action()

    def info(self):
        app.log.info("FileManagerController command set")

    def on_change(self):
        self.view.directory_list.controller.on_change()
        app.controller.Controller.on_change(self)

    def option_changed(self, name, value):
        self.view.directory_list.controller.shown_directory = None

    def pass_event_to_directory_list(self):
        self.view.directory_list.controller.do_command(self.savedCh, None)

class FilePathInputController(app.controller.Controller):
    """Manipulate path string."""

    def __init__(self, view):
        app.controller.Controller.__init__(self, view, "FilePathInputController")
        self.primary_actions = {
            "open": self.do_create_or_open,
            "saveAs": self.do_save_as,
            "selectDir": self.do_select_dir,
        }

    def perform_primary_action(self):
        path = self.decoded_path()
        if len(path) == 0:
            app.log.info("path is empty")
            return
        if path.endswith("/./"):
            # self.shown_directory = None
            self.set_encoded_path(path[:-2])
            return
        if path.endswith("/../"):
            path = os.path.dirname(path[:-4])
            if len(path) > len(os.path.sep):
                path += os.path.sep
            self.set_encoded_path(path)
            return

        self.primary_actions[self.view.parent.mode]()

    def do_create_or_open(self):
        decoded_path = self.decoded_path()
        if os.path.isdir(decoded_path):
            app.log.info("is dir", repr(decoded_path))
            return
        app_prefs = self.view.program.prefs
        path, openToRow, openToColumn = app.buffer_file.path_row_column(
            decoded_path, app_prefs.editor["baseDirEnv"]
        )
        if not os.access(path, os.R_OK):
            if os.path.isfile(path):
                app.log.info("File not readable.")
                return
        self.set_encoded_path("")
        textBuffer = self.view.program.buffer_manager.load_text_buffer(path)
        if textBuffer is None:
            return
        if openToRow is not None:
            textBuffer.pen_row = openToRow if openToRow > 0 else 0
        if openToColumn is not None:
            textBuffer.pen_col = openToColumn if openToColumn > 0 else 0
            textBuffer.goal_col = textBuffer.pen_col
        # assert textBuffer.parser
        inputWindow = self.current_input_window()
        inputWindow.set_text_buffer(textBuffer)
        textBuffer.scroll_to_optimal_scroll_position()
        self.change_to(inputWindow)

    def do_save_as(self):
        path = self.decoded_path()
        if os.path.isdir(path):
            return
        inputWindow = self.current_input_window()
        tb = inputWindow.textBuffer
        tb.set_file_path(path)
        self.change_to(inputWindow)
        if not len(path):
            tb.set_message("File not saved (file name was empty).")
            return
        if not tb.is_safe_to_write():
            self.view.change_focus_to(inputWindow.confirmOverwrite)
            return
        tb.file_write()
        self.set_encoded_path("")

    def do_select_dir(self):
        # TODO(dschuyler): not yet implemented.
        self.set_encoded_path("")
        self.change_to_input_window()

    def decoded_path(self):
        if app.config.strict_debug:
            assert self.view.textBuffer is self.textBuffer
        return app.string.path_decode(self.textBuffer.parser.row_text(0))

    def set_encoded_path(self, path):
        if app.config.strict_debug:
            assert isinstance(path, unicode)
            assert self.view.textBuffer is self.textBuffer
        self.textBuffer.replace_lines((app.string.path_encode(path),))
        self.textBuffer.parse_document()

    def info(self):
        app.log.info("FilePathInputController command set")

    def maybe_slash(self, expandedPath):
        # TODO Maybe just get the last character instead.
        line = self.textBuffer.parser.row_text(0)
        if line and line[-1] != "/" and os.path.isdir(expandedPath):
            self.textBuffer.insert("/")

    def on_change(self):
        self.get_named_window("directory_list").controller.on_change()
        app.controller.Controller.on_change(self)

    def option_changed(self, name, value):
        self.get_named_window("directory_list").controller.shown_directory = None

    def pass_event_to_directory_list(self):
        directory_list = self.find_and_change_to("directory_list")
        directory_list.controller.do_command(self.savedCh, None)

    def tab_complete_extend(self):
        """Extend the selection to match characters in common."""
        decoded_path = self.decoded_path()
        expandedPath = os.path.expandvars(os.path.expanduser(decoded_path))
        dirPath, fileName = os.path.split(expandedPath)
        expandedDir = dirPath or "."
        matches = []
        if not os.path.isdir(expandedDir):
            return
        for i in os.listdir(expandedDir):
            if i.startswith(fileName):
                matches.append(i)
        if len(matches) <= 0:
            self.maybe_slash(expandedDir)
            self.on_change()
            return
        if len(matches) == 1:
            self.set_encoded_path(decoded_path + matches[0][len(fileName) :])
            self.maybe_slash(os.path.join(expandedDir, matches[0]))
            self.on_change()
            return

        def find_common_prefix_length(prefixLen):
            count = 0
            ch = None
            for match in matches:
                if len(match) <= prefixLen:
                    return prefixLen
                if not ch:
                    ch = match[prefixLen]
                if match[prefixLen] == ch:
                    count += 1
            if count and count == len(matches):
                return find_common_prefix_length(prefixLen + 1)
            return prefixLen

        prefixLen = find_common_prefix_length(len(fileName))
        self.set_encoded_path(decoded_path + matches[0][len(fileName) : prefixLen])
        if expandedPath == os.path.expandvars(os.path.expanduser(self.decoded_path())):
            # No further expansion found.
            self.get_named_window("directory_list").controller.set_filter(fileName)
        self.on_change()
