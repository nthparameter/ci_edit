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
    # Python2.
    unicode

    def bytes_to_unicode(chars):
        chars = "".join([chr(i) for i in chars])
        return chars.decode("utf-8")

except NameError:
    unicode = str
    unichr = chr

    def bytes_to_unicode(values):
        return bytes(values).decode("utf-8")

assert bytes_to_unicode((226, 143, 176)) == "⏰"

import cProfile
import pstats

try:
    import cPickle as pickle
except ImportError:
    import pickle
import curses
import locale
import io
import os
import struct
import sys
import time
import traceback

import app.background
import app.buffer_file
import app.buffer_manager
import app.clipboard
import app.color
import app.curses_util
import app.help
import app.history
import app.log
import app.prefs
import app.program_window
import app.render
import app.spelling
import app.window

user_console_message = None

def user_message(*args):
    global user_console_message
    if not user_console_message:
        user_console_message = ""
    args = [str(i) for i in args]
    user_console_message += " ".join(args) + "\n"

class CiProgram:
    """This is the main editor program. It holds top level information and runs
    the main loop. The CiProgram is intended as a singleton.
    The program interacts with a single top-level ProgramWindow."""

    def __init__(self):
        app.log.startup("Python version ", sys.version)
        self.prefs = app.prefs.Prefs()
        self.color = app.color.Colors(self.prefs.color)
        self.dictionary = app.spelling.Dictionary(
            self.prefs.dictionaries["base"], self.prefs.dictionaries["path_match"]
        )
        self.clipboard = app.clipboard.Clipboard()
        # There is a background frame that is being build up/created. Once it's
        # completed it becomes the new front frame that will be drawn on the
        # screen. This frees up the background frame to begin drawing the next
        # frame (similar to, but not exactly like double buffering video).
        self.background_frame = app.render.Frame()
        self.front_frame = None
        self.history = app.history.History(self.prefs.user_data.get("history_path"))
        self.buffer_manager = app.buffer_manager.BufferManager(self, self.prefs)
        self.curses_screen = None
        self.debug_mouse_event = (0, 0, 0, 0, 0)
        self.exiting = False
        self.ch = 0
        self.bg = None

    def set_up_curses(self, curses_screen):
        self.curses_screen = curses_screen
        curses.mousemask(-1)
        curses.mouseinterval(0)
        # Enable mouse tracking in xterm.
        sys.stdout.write("\033[?1002;h")
        # sys.stdout.write('\033[?1005;h')
        curses.meta(1)
        # Access ^c before shell does.
        curses.raw()
        # Enable Bracketed Paste Mode.
        sys.stdout.write("\033[?2004;h")
        # Push the escape codes out to the terminal. (Whether this is needed
        # seems to vary by platform).
        sys.stdout.flush()
        try:
            curses.start_color()
            if not curses.has_colors():
                user_message("This terminal does not support color.")
                self.quit_now()
            else:
                curses.use_default_colors()
        except curses.error as e:
            app.log.error(e)
        app.log.startup("curses.COLORS", curses.COLORS)
        if 0:
            assert curses.COLORS == 256
            assert curses.can_change_color() == 1
            assert curses.has_colors() == 1
            app.log.detail("color_content:")
            for i in range(0, curses.COLORS):
                app.log.detail("color", i, ": ", curses.color_content(i))
            for i in range(16, curses.COLORS):
                curses.init_color(i, 500, 500, i * 787 % 1000)
            app.log.detail("color_content, after:")
            for i in range(0, curses.COLORS):
                app.log.detail("color", i, ": ", curses.color_content(i))
        if 1:
            # rows, cols = self.curses_screen.getmaxyx()
            curses_window = self.curses_screen
            curses_window.leaveok(1)  # Don't update cursor position.
            curses_window.scrollok(0)
            curses_window.timeout(10)
            curses_window.keypad(1)
            app.window.main_curses_window = curses_window

    def command_loop(self):
        # Cache the thread setting.
        useBgThread = self.prefs.editor["useBgThread"]
        cmd_count = 0
        # Track the time needed to handle commands and render the UI.
        # (A performance measurement).
        self.main_loop_time = 0
        self.main_loop_time_peak = 0
        self.curses_window_get_ch = app.window.main_curses_window.getch
        if self.prefs.startup["time_startup"]:
            # When running a timing of the application startup, push a CTRL_Q
            # onto the curses event messages to simulate a full startup with a
            # GUI render.
            curses.ungetch(17)
        start = time.time()
        # The first render, to get something on the screen.
        if useBgThread:
            self.bg.put("cmd_list", [])
        else:
            self.program_window.short_time_slice()
            self.program_window.render()
            self.background_frame.set_cmd_count(0)
        # This is the 'main loop'. Execution doesn't leave this loop until the
        # application is closing down.
        while not self.exiting:
            if 0:
                profile = cProfile.Profile()
                profile.enable()
                self.refresh(draw_list, cursor, cmd_count)
                profile.disable()
                output = io.StringIO()
                stats = pstats.Stats(profile, stream=output).sort_stats("cumulative")
                stats.print_stats()
                app.log.info(output.getvalue())
            self.main_loop_time = time.time() - start
            if self.main_loop_time > self.main_loop_time_peak:
                self.main_loop_time_peak = self.main_loop_time
            # Gather several commands into a batch before doing a redraw.
            # (A performance optimization).
            cmd_list = []
            while not len(cmd_list):
                if not useBgThread:
                    (
                        draw_list,
                        cursor,
                        frame_cmd_count,
                    ) = self.background_frame.grab_frame()
                    if frame_cmd_count is not None:
                        self.front_frame = (draw_list, cursor, frame_cmd_count)
                if self.front_frame is not None:
                    draw_list, cursor, frame_cmd_count = self.front_frame
                    self.refresh(draw_list, cursor, frame_cmd_count)
                    self.front_frame = None
                for _ in range(5):
                    event_info = None
                    if self.exiting:
                        return
                    ch = self.get_ch()
                    # assert isinstance(ch, int), type(ch)
                    if ch == curses.ascii.ESC:
                        # Some keys are sent from the terminal as a sequence of
                        # bytes beginning with an Escape character. To help
                        # reason about these events (and apply event handler
                        # callback functions) the sequence is converted into
                        # tuple.
                        key_sequence = []
                        n = self.get_ch()
                        while n != curses.ERR:
                            key_sequence.append(n)
                            n = self.get_ch()
                        # app.log.info('sequence\n', key_sequence)
                        # Check for Bracketed Paste Mode begin.
                        paste_begin = app.curses_util.BRACKETED_PASTE_BEGIN
                        if tuple(key_sequence[: len(paste_begin)]) == paste_begin:
                            ch = app.curses_util.BRACKETED_PASTE
                            key_sequence = key_sequence[len(paste_begin) :]
                            paste_end = (
                                curses.ascii.ESC,
                            ) + app.curses_util.BRACKETED_PASTE_END
                            while tuple(key_sequence[-len(paste_end) :]) != paste_end:
                                # app.log.info('waiting in paste mode')
                                n = self.get_ch()
                                if n != curses.ERR:
                                    key_sequence.append(n)
                            key_sequence = key_sequence[: -(len(paste_end))]
                            event_info = struct.pack(
                                "B" * len(key_sequence), *key_sequence
                            ).decode("utf-8")
                        else:
                            ch = tuple(key_sequence)
                        if not ch:
                            # The sequence was empty, so it looks like this
                            # Escape wasn't really the start of a sequence and
                            # is instead a stand-alone Escape. Just forward the
                            # esc.
                            ch = curses.ascii.ESC
                    elif type(ch) is int and 160 <= ch < 257:
                        # Start of utf-8 character.
                        u = None
                        if (ch & 0xE0) == 0xC0:
                            # Two byte utf-8.
                            b = self.get_ch()
                            u = bytes_to_unicode((ch, b))
                        elif (ch & 0xF0) == 0xE0:
                            # Three byte utf-8.
                            b = self.get_ch()
                            c = self.get_ch()
                            u = bytes_to_unicode((ch, b, c))
                        elif (ch & 0xF8) == 0xF0:
                            # Four byte utf-8.
                            b = self.get_ch()
                            c = self.get_ch()
                            d = self.get_ch()
                            u = bytes_to_unicode((ch, b, c, d))
                        assert u is not None
                        event_info = u
                        ch = app.curses_util.UNICODE_INPUT
                    if ch != curses.ERR:
                        self.ch = ch
                        if ch == curses.KEY_MOUSE:
                            # On Ubuntu, Gnome terminal, curses.getmouse() may
                            # only be called once for each KEY_MOUSE. Subsequent
                            # calls will throw an exception. So getmouse is
                            # (only) called here and other parts of the code use
                            # the event_info list instead of calling getmouse.
                            self.debug_mouse_event = curses.getmouse()
                            event_info = (self.debug_mouse_event, time.time())
                        cmd_list.append((ch, event_info))
            start = time.time()
            if len(cmd_list):
                if useBgThread:
                    self.bg.put("cmd_list", cmd_list)
                else:
                    self.program_window.execute_command_list(cmd_list)
                    self.program_window.short_time_slice()
                    self.program_window.render()
                    cmd_count += len(cmd_list)
                    self.background_frame.set_cmd_count(cmd_count)

    def process_background_messages(self):
        while self.bg.has_message():
            instruction, message = self.bg.get()
            if instruction == "exception":
                for line in message:
                    user_message(line[:-1])
                self.quit_now()
                return
            elif instruction == "render":
                # It's unlikely that more than one frame would be present in the
                # queue. If/when it happens, only the las/most recent frame
                # matters.
                self.front_frame = message
            else:
                assert False

    def get_ch(self):
        """Get an input character (or event) from curses."""
        if self.exiting:
            return -1
        ch = self.curses_window_get_ch()
        # The background thread can send a notice at any getch call.
        while ch == 0:
            if self.bg is not None:
                # Hmm, will ch ever equal 0 when self.bg is None?
                self.process_background_messages()
            if self.exiting:
                return -1
            ch = self.curses_window_get_ch()
        return ch

    def startup(self):
        """A second init-like function. Called after command line arguments are
        parsed."""
        if app.config.strict_debug:
            assert issubclass(self.__class__, app.ci_program.CiProgram), self
        self.program_window = app.program_window.ProgramWindow(self)
        top, left = app.window.main_curses_window.getyx()
        rows, cols = app.window.main_curses_window.getmaxyx()
        self.program_window.reshape(top, left, rows, cols)
        self.program_window.input_window.startup()
        self.program_window.focus()

    def parse_args(self):
        """Interpret the command line arguments."""
        app.log.startup("isatty", sys.stdin.isatty())
        debug_redo = False
        show_log_window = False
        cli_files = []
        open_to_line = None
        profile = False
        read_stdin = not sys.stdin.isatty()
        take_all = False  # Take all args as file paths.
        time_startup = False
        num_colors = min(curses.COLORS, 256)
        if os.getenv("CI_EDIT_SINGLE_THREAD"):
            self.prefs.editor["useBgThread"] = False
        for i in sys.argv[1:]:
            if not take_all and i[:1] == "+":
                open_to_line = int(i[1:])
                continue
            if not take_all and i[:2] == "--":
                if i == "--debug_redo":
                    debug_redo = True
                elif i == "--profile":
                    profile = True
                elif i == "--log":
                    show_log_window = True
                elif i == "--d":
                    app.log.channel_enable("debug", True)
                elif i == "--m":
                    app.log.channel_enable("mouse", True)
                elif i == "--p":
                    app.log.channel_enable("info", True)
                    app.log.channel_enable("debug", True)
                    app.log.channel_enable("detail", True)
                    app.log.channel_enable("error", True)
                elif i == "--parser":
                    app.log.channel_enable("parser", True)
                elif i == "--single_thread":
                    self.prefs.editor["useBgThread"] = False
                elif i == "--startup":
                    app.log.channel_enable("startup", True)
                elif i == "--time_startup":
                    time_startup = True
                elif i == "--":
                    # All remaining args are file paths.
                    take_all = True
                elif i == "--help":
                    user_message(app.help.docs["command line"])
                    self.quit_now()
                elif i == "--keys":
                    user_message(app.help.docs["key bindings"])
                    self.quit_now()
                elif i == "--clear_history":
                    self.history.clear_user_history()
                    self.quit_now()
                elif i == "--eight_colors":
                    num_colors = 8
                elif i == "--version":
                    user_message(app.help.docs["version"])
                    self.quit_now()
                elif i.startswith("--"):
                    user_message("unknown command line argument", i)
                    self.quit_now()
                continue
            if i == "-":
                read_stdin = True
            else:
                cli_files.append({"path": unicode(i)})
        # If there's no line specified, try to reinterpret the paths.
        if open_to_line is None:
            decoded_paths = []
            for file in cli_files:
                path, open_to_row, open_to_column = app.buffer_file.path_row_column(
                    file["path"], self.prefs.editor["base_dir_env"]
                )
                decoded_paths.append(
                    {"path": path, "row": open_to_row, "col": open_to_column}
                )
            cli_files = decoded_paths
        self.prefs.startup = {
            "debug_redo": debug_redo,
            "show_log_window": show_log_window,
            "cli_files": cli_files,
            "open_to_line": open_to_line,
            "profile": profile,
            "read_stdin": read_stdin,
            "time_startup": time_startup,
            "num_colors": num_colors,
        }
        self.show_log_window = show_log_window

    def quit_now(self):
        """Set the intent to exit the program. The actual exit will occur a bit
        later."""
        app.log.info()
        self.exiting = True

    def refresh(self, draw_list, cursor, cmd_count):
        """Paint the draw_list to the screen in the main thread."""
        curses_window = app.window.main_curses_window
        # Ask curses to hold the back buffer until curses refresh().
        curses_window.noutrefresh()
        curses.curs_set(0)  # Hide cursor.
        for i in draw_list:
            try:
                curses_window.addstr(*i)
            except curses.error:
                app.log.error("failed to draw", repr(i))
                pass
        if cursor is not None:
            curses.curs_set(1)  # Show cursor.
            try:
                curses_window.leaveok(0)  # Do update cursor position.
                curses_window.move(cursor[0], cursor[1])  # Move cursor.
                # Calling refresh will draw the cursor.
                curses_window.refresh()
                curses_window.leaveok(1)  # Don't update cursor position.
            except curses.error:
                app.log.error("failed to move cursor", repr(i))
                pass
        # This is a workaround to allow background processing (and parser screen
        # redraw) to interact well with the test harness. The intent is to tell
        # the test that the screen includes all commands executed up to N.
        if hasattr(curses_window, "test_rendered_command_count"):
            curses_window.test_rendered_command_count(cmd_count)

    def make_home_dirs(self, home_path):
        try:
            if not os.path.isdir(home_path):
                os.makedirs(home_path)
            self.dir_backups = os.path.join(home_path, "backups")
            if not os.path.isdir(self.dir_backups):
                os.makedirs(self.dir_backups)
            self.dir_prefs = os.path.join(home_path, "prefs")
            if not os.path.isdir(self.dir_prefs):
                os.makedirs(self.dir_prefs)
            user_dictionaries = os.path.join(home_path, "dictionaries")
            if not os.path.isdir(user_dictionaries):
                os.makedirs(user_dictionaries)
        except Exception as e:
            app.log.exception(e)

    def run(self):
        self.parse_args()
        self.set_up_palette()
        home_path = self.prefs.user_data.get("home_path")
        self.make_home_dirs(home_path)
        self.history.load_user_history()
        app.curses_util.hack_curses_fixes()
        self.startup()
        if self.prefs.editor["useBgThread"]:
            self.bg = app.background.startup_background(self.program_window)
        if self.prefs.startup.get("profile"):
            profile = cProfile.Profile()
            profile.enable()
            self.command_loop()
            profile.disable()
            output = io.StringIO()
            stats = pstats.Stats(profile, stream=output).sort_stats("cumulative")
            stats.print_stats()
            app.log.info(output.getvalue())
        else:
            self.command_loop()
        if self.prefs.editor["useBgThread"]:
            self.bg.put("quit", None)
            self.bg.join()

    def set_up_palette(self):
        def apply_palette(name):
            palette = self.prefs.palette[name]
            foreground = palette["foreground_indexes"]
            background = palette["background_indexes"]
            for i in range(1, self.prefs.startup["num_colors"]):
                curses.init_pair(i, foreground[i], background[i])

        def two_tries(primary, fallback):
            try:
                apply_palette(primary)
                app.log.startup("Primary color scheme applied")
            except curses.error:
                try:
                    apply_palette(fallback)
                    app.log.startup("Fallback color scheme applied")
                except curses.error:
                    app.log.startup("No color scheme applied")

        self.color.colors = self.prefs.startup["num_colors"]
        if self.prefs.startup["num_colors"] == 0:
            app.log.startup("using no colors")
        elif self.prefs.startup["num_colors"] == 8:
            self.prefs.color = self.prefs.color8
            app.log.startup("using 8 colors")
            two_tries(self.prefs.editor["palette8"], "default8")
        elif self.prefs.startup["num_colors"] == 16:
            self.prefs.color = self.prefs.color16
            app.log.startup("using 16 colors")
            two_tries(self.prefs.editor["palette16"], "default16")
        elif self.prefs.startup["num_colors"] == 256:
            self.prefs.color = self.prefs.color256
            app.log.startup("using 256 colors")
            two_tries(self.prefs.editor["palette"], "default")
        else:
            raise Exception(
                "unknown palette color count " + repr(self.prefs.startup["num_colors"])
            )

    if 1:  # For unit tests/debugging.

        def get_document_selection(self):
            """This is primarily for testing."""
            tb = self.program_window.input_window.text_buffer
            return (tb.pen_row, tb.pen_col, tb.marker_row, tb.marker_col, tb.selection_mode)

        def get_selection(self):
            """This is primarily for testing."""
            tb = self.program_window.focused_window.text_buffer
            return (tb.pen_row, tb.pen_col, tb.marker_row, tb.marker_col, tb.selection_mode)

def wrapped_ci(curses_screen):
    try:
        prg = CiProgram()
        prg.set_up_curses(curses_screen)
        prg.run()
    except Exception:
        user_message("---------------------------------------")
        user_message("Super sorry, something went very wrong.")
        user_message("Please create a New Issue and paste this info there.\n")
        error_type, value, traceback_info = sys.exc_info()
        out = traceback.format_exception(error_type, value, traceback_info)
        for i in out:
            user_message(i[:-1])
            # app.log.error(i[:-1])

def run_ci():
    locale.setlocale(locale.LC_ALL, "")
    try:
        # Reduce the delay waiting for escape sequences.
        os.environ.setdefault("ESCDELAY", "1")
        curses.wrapper(wrapped_ci)
    finally:
        app.log.flush()
        app.log.write_to_file("~/.ci_edit/recent_log")
        # Disable Bracketed Paste Mode.
        sys.stdout.write("\033[?2004l")
        # Disable mouse tracking in xterm.
        sys.stdout.write("\033[?1002;l")
        sys.stdout.flush()
    if user_console_message:
        full_path = app.buffer_file.expand_full_path("~/.ci_edit/user_console_message")
        with open(full_path, "w+") as f:
            f.write(user_console_message)
        sys.stdout.write(user_console_message + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    run_ci()
