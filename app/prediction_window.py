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

import app.config
import app.cu_editor
import app.log
import app.text_buffer
import app.window

class PredictionList(app.window.Window):
    """This <tbd>."""

    def __init__(self, program, host):
        if app.config.strict_debug:
            assert host
            assert self is not host
        app.window.Window.__init__(self, program, host)
        self.host = host
        self.isFocusable = False
        self.controller = app.cu_editor.PredictionList(self)
        self.set_text_buffer(app.text_buffer.TextBuffer(self.program))
        # Set up table headers.
        color = host.program.color.get("top_info")
        self.optionsRow = app.window.OptionsSelectionWindow(self.program, self)
        self.optionsRow.set_parent(self)
        self.type_column = app.window.SortableHeaderWindow(
            self.program,
            self.optionsRow,
            "Type",
            "editor",
            "predictionSortAscendingByType",
            8,
        )
        label = app.window.LabelWindow(self.program, self.optionsRow, "|")
        label.set_parent(self.optionsRow)
        label.color = color
        self.nameColumn = app.window.SortableHeaderWindow(
            self.program,
            self.optionsRow,
            "Name",
            "editor",
            "predictionSortAscendingByName",
            -61,
        )
        label = app.window.LabelWindow(self.program, self.optionsRow, "|")
        label.set_parent(self.optionsRow)
        label.color = color
        self.status_column = app.window.SortableHeaderWindow(
            self.program,
            self.optionsRow,
            "Status ",
            "editor",
            "predictionSortAscendingByStatus",
            -7,
        )
        label = app.window.LabelWindow(self.program, self.optionsRow, "|")
        label.set_parent(self.optionsRow)
        label.color = color

    def highlight_line(self, row):
        self.textBuffer.pen_row = min(row, self.textBuffer.parser.row_count() - 1)
        self.textBuffer.pen_col = 0
        app.log.info(self.textBuffer.pen_row)

    def mouse_click(self, paneRow, paneCol, shift, ctrl, alt):
        self.highlight_line(self.scrollRow + paneRow)
        row = self.scrollRow + paneRow
        if row >= self.textBuffer.parser.row_count():
            return
        self.controller.open_file_or_dir(row)

    def mouse_double_click(self, paneRow, paneCol, shift, ctrl, alt):
        app.log.info()
        assert False

    # def mouse_moved(self, paneRow, paneCol, shift, ctrl, alt):
    #  app.log.info()

    # def mouse_release(self, paneRow, paneCol, shift, ctrl, alt):
    #  app.log.info()

    # def mouse_triple_click(self, paneRow, paneCol, shift, ctrl, alt):
    #  app.log.info()

    def mouse_wheel_down(self, shift, ctrl, alt):
        self.textBuffer.mouse_wheel_down(shift, ctrl, alt)

    def mouse_wheel_up(self, shift, ctrl, alt):
        self.textBuffer.mouse_wheel_up(shift, ctrl, alt)

    def update(self, items):
        # Filter the list. (The filter function is not used so as to edit the
        # list in place).
        app_prefs = self.program.prefs
        showOpen = app_prefs.editor["predictionShowOpenFiles"]
        showAlternate = app_prefs.editor["predictionShowAlternateFiles"]
        showRecent = app_prefs.editor["predictionShowRecentFiles"]
        if not (showOpen and showAlternate and showRecent):
            i = 0
            while i < len(items):
                if not showOpen and items[i][3] == "open":
                    items.pop(i)
                elif not showAlternate and items[i][3] == "alt":
                    items.pop(i)
                elif not showRecent and items[i][3] == "recent":
                    items.pop(i)
                else:
                    i += 1
        # Sort the list
        sortByPrediction = app_prefs.editor["predictionSortAscendingByPrediction"]
        sortByType = app_prefs.editor["predictionSortAscendingByType"]
        sortByName = app_prefs.editor["predictionSortAscendingByName"]
        sortByStatus = app_prefs.editor["predictionSortAscendingByStatus"]
        if sortByPrediction is not None:
            items.sort(reverse=not sortByPrediction, key=lambda x: x[4])
        elif sortByType is not None:
            items.sort(reverse=not sortByType, key=lambda x: x[3])
        elif sortByStatus is not None:
            items.sort(reverse=not sortByStatus, key=lambda x: x[2])
        elif sortByName is not None:
            items.sort(reverse=not sortByName, key=lambda x: x[1])
        # Write the lines to the text buffer.
        def fit_path_to_width(path, width):
            if len(path) < width:
                return path
            return path[-width:]

        if len(items) == 0:
            self.textBuffer.replace_lines(("",))
        else:
            self.textBuffer.replace_lines(
                tuple(
                    [
                        "%*s %*s %.*s"
                        % (
                            self.type_column.cols,
                            i[3],
                            -self.nameColumn.cols,
                            fit_path_to_width(i[1], self.nameColumn.cols),
                            self.status_column.cols,
                            i[2],
                        )
                        for i in items
                    ]
                )
            )
        self.textBuffer.parse_screen_maybe()  # TODO(dschuyler): Add test.
        self.textBuffer.cursor_move_to_begin()

    def on_pref_changed(self, category, name):
        self.controller.option_changed(category, name)
        app.window.Window.on_pref_changed(self, category, name)

    def reshape(self, top, left, rows, cols):
        """Change self and sub-windows to fit within the given rectangle."""
        app.log.detail("reshape", top, left, rows, cols)
        self.optionsRow.reshape(top, left, 1, cols)
        top += 1
        rows -= 1
        app.window.Window.reshape(self, top, left, rows, cols)

    def set_text_buffer(self, textBuffer):
        if app.config.strict_debug:
            assert textBuffer is not self.host.textBuffer
        textBuffer.line_limit_indicator = 0
        textBuffer.highlight_cursor_line = True
        textBuffer.highlight_trailing_whitespace = False
        app.window.Window.set_text_buffer(self, textBuffer)
        self.controller.set_text_buffer(textBuffer)

class PredictionInputWindow(app.window.Window):
    def __init__(self, program, host):
        if app.config.strict_debug:
            assert host
            assert issubclass(host.__class__, app.window.ActiveWindow), host
        app.window.Window.__init__(self, program, host)
        self.host = host
        self.controller = app.cu_editor.PredictionInputController(self)
        self.set_text_buffer(app.text_buffer.TextBuffer(self.program))

    def get_path(self):
        return self.textBuffer.parser.row_text(0)

    def set_path(self, path):
        self.textBuffer.replace_lines((path,))

    def set_text_buffer(self, textBuffer):
        textBuffer.line_limit_indicator = 0
        textBuffer.highlight_trailing_whitespace = False
        app.window.Window.set_text_buffer(self, textBuffer)
        self.controller.set_text_buffer(textBuffer)

class PredictionWindow(app.window.Window):
    def __init__(self, program, host):
        app.window.Window.__init__(self, program, host)

        self.showTips = False
        self.controller = app.cu_editor.PredictionController(self)
        self.set_text_buffer(app.text_buffer.TextBuffer(self.program))

        self.title_row = app.window.OptionsRow(self.program, self)
        self.title_row.add_label(" ci   ")
        self.title_row.set_parent(self)

        self.prediction_input_window = PredictionInputWindow(self.program, self)
        self.prediction_input_window.set_parent(self)

        self.prediction_list = PredictionList(self.program, self)
        self.prediction_list.set_parent(self)

        if 1:
            self.optionsRow = app.window.RowWindow(self.program, self, 2)
            self.optionsRow.set_parent(self)
            colorPrefs = host.program.color
            self.optionsRow.color = colorPrefs.get("top_info")
            label = app.window.LabelWindow(self.program, self.optionsRow, "Show:")
            label.color = colorPrefs.get("top_info")
            label.set_parent(self.optionsRow)
            toggle = app.window.OptionsToggle(
                self.program,
                self.optionsRow,
                "open",
                "editor",
                "predictionShowOpenFiles",
            )
            toggle.color = colorPrefs.get("top_info")
            toggle = app.window.OptionsToggle(
                self.program,
                self.optionsRow,
                "alternates",
                "editor",
                "predictionShowAlternateFiles",
            )
            toggle.color = colorPrefs.get("top_info")
            toggle = app.window.OptionsToggle(
                self.program,
                self.optionsRow,
                "recent",
                "editor",
                "predictionShowRecentFiles",
            )
            toggle.color = colorPrefs.get("top_info")

        self.messageLine = app.window.LabelWindow(self.program, self, "")
        self.messageLine.set_parent(self)

    def bring_child_to_front(self, child):
        # The PredictionWindow window doesn't reorder children.
        pass

    def focus(self):
        self.reattach()
        self.parent.layout()
        app.window.Window.focus(self)
        self.change_focus_to(self.prediction_input_window)

    def get_path(self):
        return self.prediction_input_window.get_path()

    def on_pref_changed(self, category, name):
        self.prediction_list.controller.option_changed(category, name)
        app.window.Window.on_pref_changed(self, category, name)

    def reshape(self, top, left, rows, cols):
        """Change self and sub-windows to fit within the given rectangle."""
        app.window.Window.reshape(self, top, left, rows, cols)
        self.title_row.reshape(top, left, 1, cols)
        top += 1
        rows -= 1
        self.prediction_input_window.reshape(top, left, 1, cols)
        top += 1
        rows -= 1
        self.messageLine.reshape(top + rows - 1, left, 1, cols)
        rows -= 1
        self.optionsRow.reshape(top + rows - 1, left, 1, cols)
        rows -= 1
        self.prediction_list.reshape(top, left, rows, cols)

    def set_path(self, path):
        self.prediction_input_window.set_path(path)

    def unfocus(self):
        app.window.Window.unfocus(self)
        self.detach()
