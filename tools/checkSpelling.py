#!/usr/bin/env python3

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

import glob
import os
import pprint
import re
import sys
from fnmatch import fnmatch

ciEditDir = os.path.dirname(os.path.dirname(__file__))
sys.path.append(ciEditDir)
import app.regex
import app.spelling

print("checking spelling")

doValues = False
root = (len(sys.argv) > 1 and sys.argv[1]) or "."
filePattern = (len(sys.argv) > 2 and sys.argv[2]) or "*.*"

kReWords = re.compile(r"""(\w+)""")
# The first group is a hack to allow upper case pluralized, e.g. URLs.
RE_SUBWORDS = re.compile(
    r"((?:[A-Z]{2,}s\b)|(?:[A-Z][a-z]+)|(?:[A-Z]+(?![a-z]))|(?:[a-z]+))"
)

kReIgnoreDirs = re.compile(r"""/\.git/""")
kReIgnoreFiles = re.compile(
    r"""\.(pyc|pyo|png|a|jpg|tif|mp3|mp4|cpuperf|dylib|avi|so|plist|raw|webm)$"""
)
kReIncludeFiles = re.compile(r"""\.(cc)$""")
assert kReIgnoreDirs.search("/apple/.git/orange")
assert kReIgnoreFiles.search("/apple.pyc")

dictionary_list = glob.glob(os.path.join(ciEditDir, "app/dictionary.*.words"))
dictionary_list = [os.path.basename(i)[11:-6] for i in dictionary_list]
print(pprint.pprint(dictionary_list))
path_prefs = []
dictionary = app.spelling.Dictionary(dictionary_list, path_prefs)
assert dictionary.is_correct("has", "cpp")

def handle_file(file_name, unrecognizedWords):
    # print(file_name, end="")
    try:
        with open(file_name, "r") as f:
            data = f.read()
            if not data:
                return
            for sre in RE_SUBWORDS.finditer(data):
                # print(repr(sre.groups()))
                word = sre.groups()[0].lower()
                if not dictionary.is_correct(word, "cpp"):
                    if word not in unrecognizedWords:
                        print(word, end=",")
                    unrecognizedWords.add(word)
    except UnicodeDecodeError:
        print("Error decoding:", file_name)

def walk_tree(root):
    unrecognizedWords = set()
    for (dir_path, dirNames, fileNames) in os.walk(root):
        if kReIgnoreDirs.search(dir_path):
            continue
        for file_name in filter(lambda x: fnmatch(x, filePattern), fileNames):
            if kReIgnoreFiles.search(file_name):
                continue
            if kReIncludeFiles.search(file_name):
                handle_file(os.path.join(dir_path, file_name), unrecognizedWords)
    if unrecognizedWords:
        print("found", file_name)
        print(unrecognizedWords)
        print()
    return unrecognizedWords

if os.path.isfile(root):
    print(handle_file(root))
elif os.path.isdir(root):
    words = sorted(walk_tree(root))
    for i in words:
        print(i)
else:
    print("root is not a file or directory")

print("---- end ----")
