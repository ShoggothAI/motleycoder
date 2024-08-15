import logging
import os
import os.path
import re
from collections import defaultdict
from pathlib import Path
from typing import Callable, List, Set

from diskcache import Cache

from ..repo import GitRepo


def python_file_filter(fname: str, with_tests: bool = False) -> bool:
    return fname.endswith(".py") and (with_tests or not "test_" in fname)


class FileGroup:
    """
    A FileGroup is a collection of files that we are parsing and monitoring for changes.
    This might be a git repo or a directory. If new files appear in it,
    we will see that as well using the get_all_filenames method.
    """

    CACHE_VERSION = 4
    TAGS_CACHE_DIR = f".aider.tags.cache.v{CACHE_VERSION}"

    def __init__(self, repo: GitRepo | None = None, root: str | None = None, filename_filter=None):
        # TODO: support other kinds of locations
        self.repo = repo
        if self.repo is None:
            if os.path.isdir(root):
                self.root = root
            else:
                raise ValueError("Must supply either a GitRepo or a valid root directory")
        else:
            self.root = self.repo.root

        if filename_filter is None:
            self.filename_filter = python_file_filter
        else:
            self.filename_filter = filename_filter

        self.load_tags_cache()
        self.warned_files = set()

        self.files_for_modification = set()
        self.edited_files = set()

    def abs_root_path(self, path):
        "Gives an abs path, which safely returns a full (not 8.3) windows path"
        res = Path(self.root) / path
        res = Path(res).resolve()
        return str(res)

    def get_all_filenames(self, with_tests: bool = False):
        """
        Get all the filenames in the group, including new files.
        :return: List of unique absolute file paths
        """
        if self.repo:
            files = self.repo.get_tracked_files()
            files = [self.abs_root_path(fname) for fname in files]
            files = [str(fname) for fname in files if os.path.isfile(str(fname))]

        else:
            files = [str(f) for f in Path(self.root).rglob("*") if f.is_file()]

        files = [
            str(f).replace("\\", "/")
            for f in files
            if self.filename_filter(f, with_tests=with_tests)
        ]

        return sorted(set(files))

    def validate_fnames(self, fnames: List[str], with_tests: bool = False) -> List[str]:
        cleaned_fnames = []
        for fname in fnames:
            if not self.filename_filter(str(fname), with_tests=with_tests):
                continue
            if Path(fname).is_file():
                cleaned_fnames.append(str(fname))
            else:
                if fname not in self.warned_files:
                    if Path(fname).exists():
                        logging.error(f"Repo-map can't include {fname}, it is not a normal file")
                    else:
                        logging.error(
                            f"Repo-map can't include {fname}, it doesn't exist (anymore?)"
                        )

                self.warned_files.add(fname)

        return cleaned_fnames

    def load_tags_cache(self):
        path = Path(self.root) / self.TAGS_CACHE_DIR
        if not path.exists():
            logging.warning(f"Tags cache not found, creating: {path}")
        self.TAGS_CACHE = Cache(str(path))

    def add_for_modification(self, rel_fname):
        self.files_for_modification.add(self.abs_root_path(rel_fname))

    def get_rel_fname(self, fname):
        return os.path.relpath(fname, self.root).replace("\\", "/")

    def save_tags_cache(self):
        pass

    def get_mtime(self, fname):
        try:
            return os.path.getmtime(fname)
        except FileNotFoundError:
            logging.error(f"File not found error: {fname}")

    def cached_function_call(self, fname: str, function: Callable, key: str | None = None):
        """
        Cache the result of a function call, refresh the cache if the file has changed.
        :param fname: the file to monitor for changes
        :param function: the function to apply to the file
        :param key: the key to use in the cache, if None, the function name is used
        :return: the function's result
        """
        # Check if the file is in the cache and if the modification time has not changed
        # TODO: this should be a decorator?
        file_mtime = self.get_mtime(fname)
        if file_mtime is None:
            return []

        cache_key = fname + "::" + (key or function.__name__)
        if cache_key in self.TAGS_CACHE and self.TAGS_CACHE[cache_key]["mtime"] == file_mtime:
            return self.TAGS_CACHE[cache_key]["data"]

        # miss!
        data = function(fname)

        # Update the cache
        self.TAGS_CACHE[cache_key] = {"mtime": file_mtime, "data": data}
        self.save_tags_cache()
        return data

    def get_file_mentions(self, content):
        words = set(word for word in content.split())

        # drop sentence punctuation from the end
        words = set(word.rstrip(",.!;:") for word in words)

        # strip away all kinds of quotes
        quotes = "".join(['"', "'", "`"])
        words = set(word.strip(quotes) for word in words)

        all_files = self.get_all_filenames()
        other_files = set(all_files) - set(self.files_for_modification)
        addable_rel_fnames = [self.get_rel_fname(f) for f in other_files]

        mentioned_rel_fnames = set()
        fname_to_rel_fnames = {}
        for rel_fname in addable_rel_fnames:
            if rel_fname in words:
                mentioned_rel_fnames.add(str(rel_fname))

            fname = os.path.basename(rel_fname)

            # Don't add basenames that could be plain words like "run" or "make"
            if "/" in fname or "." in fname or "_" in fname or "-" in fname:
                if fname not in fname_to_rel_fnames:
                    fname_to_rel_fnames[fname] = []
                fname_to_rel_fnames[fname].append(rel_fname)

        for fname, rel_fnames in fname_to_rel_fnames.items():
            if len(rel_fnames) == 1 and fname in words:
                mentioned_rel_fnames.add(rel_fnames[0])

        return self.clean_mentioned_filenames(mentioned_rel_fnames)

    def clean_mentioned_filenames(self, mentioned_filenames: Set[str]) -> Set[str]:
        all_files = self.get_all_filenames()
        clean_mentioned_filenames = []
        for mentioned_name in mentioned_filenames:
            for name in all_files:
                if mentioned_name in name:
                    clean_mentioned_filenames.append(name)
                    break
        return set(clean_mentioned_filenames)

    def get_rel_fnames_in_directory(self, abs_dir: str) -> List[str] | None:
        abs_dir = abs_dir.replace("\\", "/").rstrip("/")
        all_abs_files = self.get_all_filenames()
        # List all of the above files that are in abs_dir, but not in subdirectories of abs_dir
        matches = [
            f
            for f in all_abs_files
            if f.startswith(abs_dir) and f.count("/") == abs_dir.count("/") + 1
        ]
        rel_matches = [str(self.get_rel_fname(f)) for f in matches]
        return rel_matches

    def edit_file(self, file_path: str, search: str, replace: str):
        abs_path = self.abs_root_path(file_path)
        abs_path = Path(abs_path)

        if not abs_path.exists() and not search.strip():
            abs_path.touch()

        file_content = abs_path.read_text()

        new_content = replace_part(file_content, search, replace)

        if new_content and new_content != file_content:
            abs_path.write_text(new_content)
            return True
        else:
            return False


def prepare_content_and_lines(content):
    if content and not content.endswith("\n"):
        content += "\n"
    lines = content.splitlines(keepends=True)

    lines_without_numbers = [re.sub(r"^\d+\s*│", "", line) for line in lines]
    return content, lines_without_numbers


def perfect_replace_part(orig_lines, search_lines, replace_lines):
    search_tup = tuple(search_lines)
    search_len = len(search_lines)

    for i in range(len(orig_lines) - search_len + 1):
        orig_tup = tuple(orig_lines[i : i + search_len])
        if search_tup == orig_tup:
            res = orig_lines[:i] + replace_lines + orig_lines[i + search_len :]
            return "".join(res)


def match_but_for_leading_whitespace(orig_chunk_lines, search_lines):
    num = len(orig_chunk_lines)

    # does the non-whitespace all agree?
    if not all(orig_chunk_lines[i].lstrip() == search_lines[i].lstrip() for i in range(num)):
        return

    # compute the offset of the first line independently
    first_line_offset = orig_chunk_lines[0][: len(orig_chunk_lines[0]) - len(search_lines[0])]

    # are they all offset the same?
    offset = set(
        orig_chunk_lines[i][: len(orig_chunk_lines[i]) - len(search_lines[i])]
        for i in range(1, num)
        if orig_chunk_lines[i].strip()
    )

    if len(offset) > 1:
        return

    return first_line_offset, offset.pop() if offset else ""


def replace_part_with_missing_leading_whitespace(orig_lines, search_lines, replace_lines):
    # GPT often messes up leading whitespace.
    # It usually does it uniformly across the ORIG and UPD blocks.
    # Either omitting all leading whitespace, or including only some of it.

    # Outdent everything in part_lines and replace_lines by the max fixed amount possible
    leading = [len(p) - len(p.lstrip()) for p in search_lines if p.strip()] + [
        len(p) - len(p.lstrip()) for p in replace_lines if p.strip()
    ]

    if leading and min(leading):
        num_leading = min(leading)
        search_lines = [p[num_leading:] if p.strip() else p for p in search_lines]
        replace_lines = [p[num_leading:] if p.strip() else p for p in replace_lines]

    # can we find an exact match not including the leading whitespace
    num_search_lines = len(search_lines)

    for i in range(len(orig_lines) - num_search_lines + 1):
        add_leading = match_but_for_leading_whitespace(
            orig_lines[i : i + num_search_lines], search_lines
        )

        if add_leading is None:
            continue

        first_line_add, tail_lines_add = add_leading

        replace_lines = [first_line_add + replace_lines[0]] + [
            tail_lines_add + rline if rline.strip() else rline for rline in replace_lines[1:]
        ]
        orig_lines = orig_lines[:i] + replace_lines + orig_lines[i + num_search_lines :]
        return "".join(orig_lines)


def replace_with_dotdotdots(orig, search, replace):
    """
    See if the edit block has ... lines.
    If not, return none.

    If yes, try and do a perfect edit with the ... chunks.
    If there's a mismatch or otherwise imperfect edit, raise ValueError.

    If perfect edit succeeds, return the updated whole.
    """

    dots_re = re.compile(r"(^\s*\.\.\.\n)", re.MULTILINE | re.DOTALL)

    search_pieces = re.split(dots_re, search)
    replace_pieces = re.split(dots_re, replace)

    if len(search_pieces) != len(replace_pieces):
        raise ValueError("Unpaired ... in SEARCH/REPLACE block")

    if len(search_pieces) == 1:
        # no dots in this edit block, just return None
        return

    # Compare odd strings in search_pieces and replace_pieces
    all_dots_match = all(
        search_pieces[i] == replace_pieces[i] for i in range(1, len(search_pieces), 2)
    )

    if not all_dots_match:
        raise ValueError("Unmatched ... in SEARCH/REPLACE block")

    search_pieces = [search_pieces[i] for i in range(0, len(search_pieces), 2)]
    replace_pieces = [replace_pieces[i] for i in range(0, len(replace_pieces), 2)]

    pairs = zip(search_pieces, replace_pieces)
    for search, replace in pairs:
        if not search and not replace:
            continue

        if not search and replace:
            if not orig.endswith("\n"):
                orig += "\n"
            orig += replace
            continue

        if orig.count(search) == 0:
            raise ValueError
        if orig.count(search) > 1:
            raise ValueError

        orig = orig.replace(search, replace, 1)

    return orig


def replace_part(text, search, replace):
    if not text:
        text = ""

    if not search or search[-1] != "\n":
        search += "\n"
    if not replace or replace[-1] != "\n":
        replace += "\n"

    if not search.strip():
        return text + replace

    orig_content, orig_lines = prepare_content_and_lines(text)
    search_content, search_lines = prepare_content_and_lines(search)
    replace_content, replace_lines = prepare_content_and_lines(replace)

    result = perfect_replace_part(orig_lines, search_lines, replace_lines)
    if result:
        return result

    result = replace_part_with_missing_leading_whitespace(orig_lines, search_lines, replace_lines)
    if result:
        return result

    try:
        return replace_with_dotdotdots(orig_content, search, replace)
    except ValueError:
        return None


def get_ident_filename_matches(idents, all_rel_fnames: List[str], max_ident_len=2):
    all_fnames = defaultdict(set)
    for fname in all_rel_fnames:
        base = Path(fname).with_suffix("").name.lower()
        if len(base) >= max_ident_len:
            all_fnames[base].add(fname)

    matches = set()
    for ident in idents:
        if len(ident) < max_ident_len:
            continue
        matches.update(all_fnames[ident.lower()])

    return matches


def get_ident_mentions(text):
    # Split the string on any character that is not alphanumeric
    # \W+ matches one or more non-word characters (equivalent to [^a-zA-Z0-9_]+)
    words = set(re.split(r"\W+", text))
    return words
