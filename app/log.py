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

import inspect
import os
import sys
import time
import traceback

import app.buffer_file

screen_log = ["--- screen log ---"]
full_log = ["--- begin log ---"]
enabled_channels = {
    "meta": True,
    #'mouse': True,
    "startup": True,
}
should_write_print_log = False
start_time = time.time()

def get_lines():
    return screen_log

def parse_lines(frame, log_channel, *args):
    if not len(args):
        args = [""]
    msg = str(args[0])
    if 1:
        msg = f"{log_channel} {os.path.split(frame[1])[1]} {frame[2]} {frame[3]}: {msg}"
    prior = msg
    for i in args[1:]:
        if not len(prior) or prior[-1] != "\n":
            msg += " "
        prior = repr(i)  # unicode(i)
        msg += prior
    return msg.split("\n")

def channel_enable(log_channel, is_enabled):
    global full_log, should_write_print_log
    full_log += [
        f"{'logging':>10} {'channel_enable':>10}: {log_channel} {is_enabled!r}"
    ]
    if is_enabled:
        enabled_channels[log_channel] = is_enabled
        should_write_print_log = True
    else:
        enabled_channels.pop(channel, None)

def channel(log_channel, *args):
    global full_log, screen_log
    if log_channel in enabled_channels:
        lines = parse_lines(inspect.stack()[2], log_channel, *args)
        screen_log += lines
        full_log += lines

def caller(*args):
    global full_log, screen_log
    prior_caller = inspect.stack()[2]
    msg = (
        f"{os.path.split(prior_caller[1])[1]} {prior_caller[2]} {prior_caller[3]}",
    ) + args
    lines = parse_lines(inspect.stack()[1], "caller", *msg)
    screen_log += lines
    full_log += lines

def exception(e, *args):
    global full_log
    lines = parse_lines(inspect.stack()[1], "except", *args)
    full_log += lines
    error_type, value, traceback_info = sys.exc_info()
    out = traceback.format_exception(error_type, value, traceback_info)
    for i in out:
        error(i[:-1])

def check_failed(prefix, a, op, b):
    stack(f"failed {prefix} {a!r} {op} {b!r}")
    raise Exception("fatal error")

def check_ge(a, b):
    if a >= b:
        return
    check_failed("check_ge", a, ">=", b)

def check_gt(a, b):
    if a > b:
        return
    check_failed("check_lt", a, "<", b)

def check_le(a, b):
    if a <= b:
        return
    check_failed("check_le", a, "<=", b)

def check_lt(a, b):
    if a < b:
        return
    check_failed("check_lt", a, "<", b)

def stack(*args):
    global full_log, screen_log
    call_stack = inspect.stack()[1:]
    call_stack.reverse()
    for i, frame in enumerate(call_stack):
        line = [
            "stack %2d %14s %4s %s"
            % (i, os.path.split(frame[1])[1], frame[2], frame[3])
        ]
        screen_log += line
        full_log += line
    if len(args):
        screen_log.append("stack    " + repr(args[0]))
        full_log.append("stack    " + repr(args[0]))

def info(*args):
    channel("info", *args)

def meta(*args):
    """Log information related to logging."""
    channel("meta", *args)

def mouse(*args):
    channel("mouse", *args)

def parser(*args):
    channel("parser", *args)

def startup(*args):
    channel("startup", *args)

def quick(*args):
    global full_log, screen_log
    msg = str(args[0])
    prior = msg
    for i in args[1:]:
        if not len(prior) or prior[-1] != "\n":
            msg += " "
        prior = i  # unicode(i)
        msg += prior
    lines = msg.split("\n")
    screen_log += lines
    full_log += lines

def debug(*args):
    global full_log, screen_log
    if "debug" in enabled_channels:
        lines = parse_lines(inspect.stack()[1], "debug_@@@", *args)
        screen_log += lines
        full_log += lines

def detail(*args):
    global full_log
    if "detail" in enabled_channels:
        lines = parse_lines(inspect.stack()[1], "detail", *args)
        full_log += lines

def error(*args):
    global full_log
    lines = parse_lines(inspect.stack()[1], "error", *args)
    full_log += lines

def when(*args):
    args = (time.time() - start_time,) + args
    channel("info", *args)

def wrapper(function, should_write=True):
    global should_write_print_log
    should_write_print_log = should_write
    r = -1
    try:
        try:
            r = function()
        except BaseException:
            should_write_print_log = True
            error_type, value, traceback_info = sys.exc_info()
            out = traceback.format_exception(error_type, value, traceback_info)
            for i in out:
                error(i[:-1])
    finally:
        flush()
    return r

def write_to_file(path):
    full_path = app.buffer_file.expand_full_path(path)
    with open(full_path, "w+", encoding="UTF-8") as out:
        out.write("\n".join(full_log) + "\n")

def flush():
    if should_write_print_log:
        sys.stdout.write("\n".join(full_log) + "\n")
