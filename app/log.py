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

screenLog = ["--- screen log ---"]
fullLog = ["--- begin log ---"]
enabledChannels = {
    "meta": True,
    #'mouse': True,
    "startup": True,
}
shouldWritePrintLog = False
startTime = time.time()

def get_lines():
    return screenLog

def parse_lines(frame, logChannel, *args):
    if not len(args):
        args = [""]
    msg = str(args[0])
    if 1:
        msg = f"{logChannel} {os.path.split(frame[1])[1]} {frame[2]} {frame[3]}: {msg}"
    prior = msg
    for i in args[1:]:
        if not len(prior) or prior[-1] != "\n":
            msg += " "
        prior = repr(i)  # unicode(i)
        msg += prior
    return msg.split("\n")

def channel_enable(logChannel, isEnabled):
    global fullLog, shouldWritePrintLog
    fullLog += [
        "%10s %10s: %s %r" % ("logging", "channel_enable", logChannel, isEnabled)
    ]
    if isEnabled:
        enabledChannels[logChannel] = isEnabled
        shouldWritePrintLog = True
    else:
        enabledChannels.pop(channel, None)

def channel(logChannel, *args):
    global fullLog, screenLog
    if logChannel in enabledChannels:
        lines = parse_lines(inspect.stack()[2], logChannel, *args)
        screenLog += lines
        fullLog += lines

def caller(*args):
    global fullLog, screenLog
    priorCaller = inspect.stack()[2]
    msg = (
        f"{os.path.split(priorCaller[1])[1]} {priorCaller[2]} {priorCaller[3]}",
    ) + args
    lines = parse_lines(inspect.stack()[1], "caller", *msg)
    screenLog += lines
    fullLog += lines

def exception(e, *args):
    global fullLog
    lines = parse_lines(inspect.stack()[1], "except", *args)
    fullLog += lines
    errorType, value, tracebackInfo = sys.exc_info()
    out = traceback.format_exception(errorType, value, tracebackInfo)
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
    global fullLog, screenLog
    callStack = inspect.stack()[1:]
    callStack.reverse()
    for i, frame in enumerate(callStack):
        line = [
            "stack %2d %14s %4s %s"
            % (i, os.path.split(frame[1])[1], frame[2], frame[3])
        ]
        screenLog += line
        fullLog += line
    if len(args):
        screenLog.append("stack    " + repr(args[0]))
        fullLog.append("stack    " + repr(args[0]))

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
    global fullLog, screenLog
    msg = str(args[0])
    prior = msg
    for i in args[1:]:
        if not len(prior) or prior[-1] != "\n":
            msg += " "
        prior = i  # unicode(i)
        msg += prior
    lines = msg.split("\n")
    screenLog += lines
    fullLog += lines

def debug(*args):
    global fullLog, screenLog
    if "debug" in enabledChannels:
        lines = parse_lines(inspect.stack()[1], "debug_@@@", *args)
        screenLog += lines
        fullLog += lines

def detail(*args):
    global fullLog
    if "detail" in enabledChannels:
        lines = parse_lines(inspect.stack()[1], "detail", *args)
        fullLog += lines

def error(*args):
    global fullLog
    lines = parse_lines(inspect.stack()[1], "error", *args)
    fullLog += lines

def when(*args):
    args = (time.time() - startTime,) + args
    channel("info", *args)

def wrapper(function, shouldWrite=True):
    global shouldWritePrintLog
    shouldWritePrintLog = shouldWrite
    r = -1
    try:
        try:
            r = function()
        except BaseException:
            shouldWritePrintLog = True
            errorType, value, tracebackInfo = sys.exc_info()
            out = traceback.format_exception(errorType, value, tracebackInfo)
            for i in out:
                error(i[:-1])
    finally:
        flush()
    return r

def write_to_file(path):
    full_path = app.buffer_file.expand_full_path(path)
    with open(full_path, "w+", encoding="UTF-8") as out:
        out.write("\n".join(fullLog) + "\n")

def flush():
    if shouldWritePrintLog:
        sys.stdout.write("\n".join(fullLog) + "\n")
