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

import bisect
import glob
import os
import re

import app.log

class OsDictionary:
    def __init__(self):
        path = "/usr/share/dict/words"
        try:
            self.file = open(path, "r")
            self.file_length = self.file.seek(0, 2)  # Seek to end of file.
            self.page_size = 1024 * 8  # Arbitrary.
            # Add one to pick up any partial page at the end.
            self.file_pages = self.file_length // self.page_size + 1
        except IOError:
            self.file = None
        self.cache = {}
        self.known_offsets = []

    def check(self, word):
        if self.file is None:
            return False
        word = word.lower()
        r = self.cache.get(word)
        if r is not None:
            return r
        high = self.file_pages
        low = 0
        leash = 20  # Way more than should be necessary.
        try:
            while True:
                if not leash:
                    # There's likely a bug in this function if we hit this.
                    app.log.info("spelling leash", word)
                    return False
                leash -= 1
                page = low + (high - low) // 2
                self.file.seek(page * self.page_size)
                # Add 100 to catch any words that straddle a page.
                size = min(self.page_size + 100, self.file_length - page * self.page_size)
                if not size:
                    self.cache[word] = False
                    return False
                chunk = self.file.read(size)
                chunk = chunk[chunk.find("\n") : chunk.rfind("\n")]
                if not chunk:
                    self.cache[word] = False
                    return False
                words = chunk.split()
                if word < words[0].lower():
                    high = page
                    continue
                if word > words[-1].lower():
                    low = page
                    continue
                lower_words = [i.lower() for i in words]
                index = bisect.bisect_left(lower_words, word)
                if lower_words[index] == word:
                    self.cache[word] = True
                    return True
                self.cache[word] = False
                return False
        except IOError:
            return False

class Dictionary:
    def __init__(self, dictionary_list, path_prefs):
        self.os_dictionary = OsDictionary()
        self.path_prefs = path_prefs

        self.grammar_words = {}
        self.load_words(os.path.dirname(__file__))
        self.load_words(os.path.expanduser("~/.ci_edit/dictionaries"))

        words = set()
        for i in dictionary_list:
            words.update(self.grammar_words.get(i, set()))
        self.base_words = words
        self.path_words = set()

    def set_up_words_for_path(self, path):
        self.path_words = set()
        # app.log.info(repr(self.path_prefs))
        for k, v in self.path_prefs.items():
            if k in path:
                for i in v:
                    self.path_words.update(self.grammar_words.get(i, set()))

    def load_words(self, dir_path):
        dir_path = os.path.join(dir_path, "dictionary.")
        for path in glob.iglob(dir_path + "*.words"):
            if os.path.isfile(path):
                grammar_name = path[len(dir_path) : -len(".words")]
                with open(path, "r") as f:
                    lines = f.readlines()
                    index = 0
                    while not len(lines[index]) or lines[index][0] == "#":
                        index += 1
                    app.log.startup(len(lines) - index, "words from", path)
                    # TODO(dschuyler): Word contractions are hacked by storing
                    # the components of the contraction. So didn, doesn, and isn
                    # are considered 'words'.
                    self.grammar_words[grammar_name] = set(
                        [
                            p
                            for l in lines[index:]
                            for w in l.split()
                            for p in w.split("'")
                        ]
                    )

    def is_correct(self, word, grammar_name):
        if len(word) <= 1:
            return True
        words = self.base_words
        lower_word = word.lower()
        if word in words or lower_word in words:
            return True
        if lower_word in self.grammar_words.get(grammar_name, set()):
            return True
        if lower_word.startswith("sub") and lower_word[3:] in words:
            return True
        if lower_word.startswith("un") and lower_word[2:] in words:
            return True
        if lower_word in self.path_words:
            return True
        if 1:
            if len(word) == 2 and word[1] == "s" and word[0].isupper():
                # Upper case, with an 's' for plurality (e.g. PDFs).
                return True
        if 0:
            if len(re.sub("[A-Z]", "", word)) == 0:
                # All upper case.
                return True
        if 0:
            # TODO(dschuyler): This is an experiment. Considering a py specific
            # word list instead.
            if grammar_name == "py":
                # Handle run together (undelineated) words.
                if len(re.sub("[a-z]+", "", word)) == 0:
                    for i in range(len(word), 0, -1):
                        if word[:i] in words and word[i:] in words:
                            return True
        if 1:  # Experimental.
            # Fallback to the OS dictionary.
            return self.os_dictionary.check(word)
        # app.log.info(grammar_name, word)
        return False
