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

# For Python 2to3 support.

try:
    unicode
except NameError:
    unicode = str
    unichr = chr

import os

try:
    import Queue as queue
except ImportError:
    import queue
import signal
import sys
import threading
import time
import traceback

import app.config
import app.profile
import app.render

class InstructionQueue(queue.Queue):
    def __init__(self, *args, **keywords):
        queue.Queue.__init__(self, *args, **keywords)

    def get(self, *args, **keywords):
        result = queue.Queue.get(self, *args, **keywords)
        if app.config.strict_debug:
            assert isinstance(result, tuple), repr(result)
            assert isinstance(result[0], unicode), repr(result[0])
        return result[0], result[1]

    def empty(self, *args, **keywords):
        # This thread yield (time.sleep(0)) dramatically improves Python3
        # performance. Without this line empty() will be called far too often.
        time.sleep(0)
        return queue.Queue.empty(self, *args, **keywords)

    def put(self, instruction, message):
        if app.config.strict_debug:
            assert isinstance(instruction, unicode), repr(instruction)
        queue.Queue.put(self, (instruction, message))

class BackgroundThread(threading.Thread):
    def __init__(self, program_window, to_background, from_background, *args, **keywords):
        threading.Thread.__init__(self, *args, **keywords)
        self._programWindow = program_window
        self._toBackground = to_background
        self._fromBackground = from_background

    def get(self):
        return self._fromBackground.get()

    def has_message(self):
        return not self._fromBackground.empty()

    def has_user_event(self):
        return not self._toBackground.empty()

    def put(self, instruction, message):
        self._toBackground.put(instruction, message)

    def run(self):
        cmd_count = 0
        block = True
        pid = os.getpid()
        signal_number = signal.SIGUSR1
        program_window = self._programWindow
        while True:
            try:
                try:
                    instruction, message = self._toBackground.get(block)
                    # profile = app.profile.begin_python_profile()
                    if instruction == "quit":
                        app.log.info("bg received quit message")
                        return
                    elif instruction == "cmd_list":
                        app.log.info(program_window, message)
                        program_window.execute_command_list(message)
                    else:
                        assert False, instruction
                    block = program_window.short_time_slice()
                    program_window.render()
                    # debugging only: program_window.show_window_hierarchy()
                    cmd_count += len(message)
                    program_window.program.background_frame.set_cmd_count(cmd_count)
                    self._fromBackground.put(
                        "render", program_window.program.background_frame.grab_frame()
                    )
                    os.kill(pid, signal_number)
                    # app.profile.end_python_profile(profile)
                    time.sleep(0)  # See note in has_message().
                    if block or not self._toBackground.empty():
                        continue
                except queue.Empty:
                    pass
                block = program_window.long_time_slice()
                if block:
                    program_window.render()
                    program_window.program.background_frame.set_cmd_count(cmd_count)
                    self._fromBackground.put(
                        "render", program_window.program.background_frame.grab_frame()
                    )
                    os.kill(pid, signal_number)
            except Exception as e:
                app.log.exception(e)
                app.log.error("bg thread exception", e)
                error_type, value, traceback_info = sys.exc_info()
                out = traceback.format_exception(error_type, value, traceback_info)
                self._fromBackground.put("exception", out)
                os.kill(pid, signal_number)
                while True:
                    instruction, message = self._toBackground.get()
                    if instruction == "quit":
                        app.log.info("bg received quit message")
                        return

def startup_background(program_window):
    to_background = InstructionQueue()
    from_background = InstructionQueue()
    bg = BackgroundThread(program_window, to_background, from_background)
    bg.setName("ci_edit_bg")
    bg.setDaemon(True)
    bg.start()
    return bg
