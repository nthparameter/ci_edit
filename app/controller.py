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
"""Manager for key bindings."""

import curses
import curses.ascii
import json
import os

import app.config
import app.curses_util
import app.log
import app.selectable
from app.selectable import SelectionMode

# import app.window

class Controller:
    """A Controller is a keyboard mapping from keyboard/mouse events to editor
    commands."""

    def __init__(self, view, name):
        if app.config.strict_debug:
            assert issubclass(self.__class__, Controller)
            assert issubclass(view.__class__, app.window.Window)
        self.view = view
        self.command_default = None
        self.command_set = None
        self.text_buffer = None
        self.name = name

    def parent_controller(self):
        view = self.view.parent
        while view is not None:
            if view.controller is not None:
                return view.controller
            view = view.parent

    def change_to_confirm_close(self):
        self.find_and_change_to("confirm_close")

    def change_to_confirm_overwrite(self):
        self.find_and_change_to("confirm_overwrite")

    def change_to_file_manager_window(self, *args):
        self.find_and_change_to("file_manager_window")

    def change_to_confirm_quit(self):
        self.find_and_change_to("interactive_quit")

    def change_to_host_window(self, *args):
        host = self.get_named_window("input_window")
        if app.config.strict_debug:
            assert issubclass(self.view.__class__, app.window.Window), self.view
            assert issubclass(host.__class__, app.window.Window), host
        self.view.change_focus_to(host)

    def change_to_input_window(self, *args):
        self.find_and_change_to("input_window")

    def change_to_find(self):
        self.find_and_change_to("interactive_find")

    def change_to_find_prior(self):
        curses.ungetch(self.saved_ch)
        self.find_and_change_to("interactive_find")

    def change_to_goto(self):
        self.find_and_change_to("interactive_goto")

    def change_to_palette_window(self):
        self.find_and_change_to("palette_window")

    def change_to_popup(self):
        self.find_and_change_to("popup_window")

    def change_to_prediction(self):
        self.find_and_change_to("prediction_window")
        # self.find_and_change_to('interactive_prediction')

    def change_to_prompt(self):
        self.find_and_change_to("interactive_prompt")

    def change_to_quit(self):
        self.find_and_change_to("interactive_quit")

    def change_to_save_as(self):
        view = self.get_named_window("file_manager_window")
        view.set_mode("save_as")
        view.bring_to_front()
        view.change_focus_to(view)

    def create_new_text_buffer(self):
        buffer_manager = self.view.program.buffer_manager
        self.view.set_text_buffer(buffer_manager.new_text_buffer())

    def open_preferences(self):
        prefs_dir = os.path.expanduser("~/.ci_edit/prefs")
        prefs_path = os.path.join(prefs_dir, "editor.json")
        if not os.path.isdir(prefs_dir):
            os.makedirs(prefs_dir)
        if not os.path.isfile(prefs_path):
            with open(prefs_path, "w") as f:
                f.write(json.dumps(
                    {
                        "color_scheme": "default",
                        "show_line_numbers": True,
                        "tabs_to_spaces": True,
                        "tab_width": 4,
                    },
                    indent=4,
                ) + "\n")
        text_buffer = self.view.program.buffer_manager.load_text_buffer(prefs_path)
        input_window = self.current_input_window()
        input_window.set_text_buffer(text_buffer)
        self.find_and_change_to("input_window")

    def do_command(self, ch, meta):
        # Check the command_set for the input with both its string and integer
        # representation.
        self.saved_ch = ch

        cmd = self.command_set.get(ch) or self.command_set.get(
            app.curses_util.curses_key_name(ch)
        )

        if cmd:
            cmd()
        else:
            self.command_default(ch, meta)
        self.text_buffer.compound_change_push()

    def get_named_window(self, window_name):
        view = self.view
        while view is not None:
            if hasattr(view, window_name):
                return getattr(view, window_name)
            view = view.parent
        app.log.fatal(window_name + " not found")
        return None

    def current_input_window(self):
        return self.get_named_window("input_window")

    def find_and_change_to(self, window_name):
        window = self.get_named_window(window_name)
        window.bring_to_front()
        self.view.change_focus_to(window)
        return window

    def change_to(self, window):
        window.bring_to_front()
        self.view.change_focus_to(window)

    def focus(self):
        pass

    def confirmation_prompt_finish(self, *args):
        window = self.get_named_window("input_window")
        window.user_intent = "edit"
        window.bring_to_front()
        self.view.change_focus_to(window)

    def __close_host_file(self, host):
        """Close the current file and switch to another or create an empty
        file."""
        buffer_manager = host.program.buffer_manager
        buffer_manager.close_text_buffer(host.text_buffer)
        host.user_intent = "edit"
        tb = buffer_manager.get_unsaved_buffer()
        if not tb:
            tb = buffer_manager.next_buffer()
            if not tb:
                tb = buffer_manager.new_text_buffer()
        host.set_text_buffer(tb)

    def close_file(self):
        app.log.info()
        host = self.get_named_window("input_window")
        self.__close_host_file(host)
        self.confirmation_prompt_finish()

    def close_or_confirm_close(self):
        """If the file is clean, close it. If it is dirty, prompt the user
        about whether to lose unsaved changes."""
        host = self.get_named_window("input_window")
        tb = host.text_buffer
        if not tb.is_dirty():
            self.__close_host_file(host)
            return
        if host.user_intent == "edit":
            host.user_intent = "close"
        self.change_to_confirm_close()

    def initiate_close(self):
        """Called from input window controller."""
        self.view.user_intent = "close"
        tb = self.view.text_buffer
        if not tb.is_dirty():
            self.__close_host_file(self.view)
            return
        self.view.change_focus_to(self.view.confirm_close)

    def initiate_quit(self):
        """Called from input window controller."""
        self.view.user_intent = "quit"
        tb = self.view.text_buffer
        if tb.is_dirty():
            self.view.change_focus_to(self.view.interactive_quit)
            return
        buffer_manager = self.view.program.buffer_manager
        tb = buffer_manager.get_unsaved_buffer()
        if tb:
            self.view.set_text_buffer(tb)
            self.view.change_focus_to(self.view.interactive_quit)
            return
        buffer_manager.debug_log()
        self.view.quit_now()

    def initiate_save(self):
        """Called from input window controller."""
        self.view.user_intent = "edit"
        tb = self.view.text_buffer
        if tb.full_path:
            if not tb.is_safe_to_write():
                self.view.change_focus_to(self.view.confirm_overwrite)
                return
            tb.file_write()
            return
        self.change_to_save_as()

    def overwrite_host_file(self):
        """Close the current file and switch to another or create an empty
        file.
        """
        host = self.get_named_window("input_window")
        host.text_buffer.file_write()
        if host.user_intent == "quit":
            self.quit_or_switch_to_confirm_quit()
            return
        if host.user_intent == "close":
            self.__close_host_file(host)
        self.change_to_host_window()

    def next_focusable_window(self):
        window = self.view.next_focusable_window(self.view)
        if window is not None:
            self.view.change_focus_to(window)
        return window is not None

    def prior_focusable_window(self):
        window = self.view.prior_focusable_window(self.view)
        if window is not None:
            self.view.change_focus_to(window)
        return window is not None

    def write_or_confirm_overwrite(self):
        """Ask whether the file should be overwritten."""
        app.log.debug()
        host = self.get_named_window("input_window")
        tb = host.text_buffer
        if not tb.is_safe_to_write():
            self.change_to_confirm_overwrite()
            return
        tb.file_write()
        # TODO(dschuyler): Is there a deeper issue here that necessitates saving
        # the message? Does this only need to wrap the change_to_host_window()?
        # Store the save message so it is not overwritten.
        save_message = tb.message
        if host.user_intent == "quit":
            self.quit_or_switch_to_confirm_quit()
            return
        if host.user_intent == "close":
            self.__close_host_file(host)
        self.change_to_host_window()
        tb.message = save_message  # Restore the save message.

    def quit_or_switch_to_confirm_quit(self):
        app.log.debug(self, self.view)
        host = self.get_named_window("input_window")
        tb = host.text_buffer
        host.user_intent = "quit"
        if tb.is_dirty():
            self.change_to_confirm_quit()
            return
        buffer_manager = self.view.program.buffer_manager
        tb = buffer_manager.get_unsaved_buffer()
        if tb:
            host.set_text_buffer(tb)
            self.change_to_confirm_quit()
            return
        buffer_manager.debug_log()
        host.quit_now()

    def save_or_change_to_save_as(self):
        app.log.debug()
        host = self.get_named_window("input_window")
        if app.config.strict_debug:
            assert issubclass(self.__class__, Controller), self
            assert issubclass(self.view.__class__, app.window.Window), self
            assert issubclass(host.__class__, app.window.Window), self
            assert self.view.text_buffer is self.text_buffer
            assert self.view.text_buffer is not host.text_buffer
        if host.text_buffer.full_path:
            self.write_or_confirm_overwrite()
            return
        self.change_to_save_as()

    def on_change(self):
        pass

    def save_event_change_to_host_window(self, *args):
        curses.ungetch(self.saved_ch)
        host = self.get_named_window("input_window")
        host.bring_to_front()
        self.view.change_focus_to(host)

    def set_text_buffer(self, text_buffer):
        if app.config.strict_debug:
            assert issubclass(
                text_buffer.__class__, app.text_buffer.TextBuffer
            ), text_buffer
            assert self.view.text_buffer is text_buffer
        self.text_buffer = text_buffer

    def unfocus(self):
        pass

class MainController:
    """The different keyboard mappings are different controllers. This class
    manages a collection of keyboard mappings and allows the user to switch
    between them."""

    def __init__(self, view):
        if app.config.strict_debug:
            assert issubclass(view.__class__, app.window.Window)
        self.view = view
        self.command_default = None
        self.command_set = None
        self.controllers = {}
        self.controller = None

    def add(self, controller):
        self.controllers[controller.name] = controller
        self.controller = controller

    def current_input_window(self):
        return self.controller.current_input_window()

    def do_command(self, ch, meta):
        self.controller.do_command(ch, meta)

    def focus(self):
        app.log.info("MainController.focus")
        self.controller.focus()
        if 0:
            self.command_default = self.controller.command_default
            command_set = self.controller.command_set.copy()
            command_set.update(
                {
                    app.curses_util.KEY_F2: self.next_controller,
                }
            )
            self.controller.command_set = command_set

    def on_change(self):
        tb = self.view.text_buffer
        if tb.message is None and tb.selection_mode != SelectionMode.NONE:
            char_count, line_count = tb.count_selected()
            tb.set_message(
                f"{char_count} characters ({line_count} lines) selected"
            )
        self.controller.on_change()

    def next_controller(self):
        app.log.info("next_controller")
        if 0:
            if self.controller is self.controllers["cua_plus"]:
                app.log.info("MainController.next_controller cua")
                self.controller = self.controllers["cua"]
            elif self.controller is self.controllers["cua"]:
                app.log.info("MainController.next_controller emacs")
                self.controller = self.controllers["emacs"]
            elif self.controller is self.controllers["emacs"]:
                app.log.info("MainController.next_controller vi")
                self.controller = self.controllers["vi"]
            else:
                app.log.info("MainController.next_controller cua")
                self.controller = self.controllers["cua"]
            self.controller.set_text_buffer(self.text_buffer)
            self.focus()

    def set_text_buffer(self, text_buffer):
        app.log.info("MainController.set_text_buffer", self.controller)
        if app.config.strict_debug:
            assert issubclass(text_buffer.__class__, app.text_buffer.TextBuffer)
        self.text_buffer = text_buffer
        self.controller.set_text_buffer(text_buffer)

    def unfocus(self):
        self.controller.unfocus()
