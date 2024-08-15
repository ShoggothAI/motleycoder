import os
import warnings
from typing import List, Set, Optional, Callable

from langchain_core.pydantic_v1 import BaseModel, Field
from motleycrew.common import logger

from .file_group import (
    FileGroup,
    get_ident_mentions,
    get_ident_filename_matches,
)
from .graph import TagGraph, build_tag_graph, only_defs  # noqa: F402
from .map_args import RepoMapArgs
from .parse import get_tags_raw, read_text  # noqa: F402
from .rank import rank_tags_new, rank_tags  # noqa: F402
from .render import RenderCode

# tree_sitter is throwing a FutureWarning
warnings.simplefilter("ignore", category=FutureWarning)


class RepoMap:
    def __init__(
        self,
        map_tokens: int = 1024,
        root: Optional[str] = None,
        token_count: Optional[Callable] = None,
        repo_content_prefix: Optional[str] = None,
        verbose: bool = False,
        file_group: FileGroup = None,
        use_old_ranking: bool = False,
        cache_graphs: bool = False,
    ):
        self.verbose = verbose
        self.use_old_ranking = use_old_ranking

        if not root:
            root = os.getcwd()
        self.root = root

        self.max_map_tokens = map_tokens

        self.token_count = token_count
        self.repo_content_prefix = repo_content_prefix
        self.file_group = file_group
        self.code_renderer = RenderCode()
        self.tag_graphs = {} if cache_graphs else None

    def get_repo_map(
        self,
        args: RepoMapArgs,
    ):
        if self.max_map_tokens <= 0:
            return
        if not args.other_fnames:
            return

        try:
            ranked_tags = self.get_ranked_tags(args=args)
            files_listing = self.find_best_tag_tree(ranked_tags=ranked_tags)
        except RecursionError:
            logger.error("Disabling repo map, git repo too large?")
            self.max_map_tokens = 0
            return

        if not files_listing:
            return

        num_tokens = self.token_count(files_listing)
        if self.verbose:
            logger.info(f"Repo-map: {num_tokens/1024:.1f} k-tokens")

        if self.repo_content_prefix and args.add_prefix:
            repo_content = self.repo_content_prefix
        else:
            repo_content = ""

        repo_content += files_listing
        return repo_content

    def get_tag_graph(
        self, abs_fnames: List[str] | None = None, with_tests: bool = False
    ) -> TagGraph:
        if not abs_fnames:
            abs_fnames = self.file_group.get_all_filenames(with_tests=with_tests)
        clean_fnames = self.file_group.validate_fnames(abs_fnames, with_tests=with_tests)

        if self.tag_graphs is not None:
            for files, graph in self.tag_graphs.items():
                if not set(clean_fnames).difference(set(files)):
                    return graph

        # If no caching or cached graph not found, construct it
        all_tags = []
        code_map = {}
        for fname in clean_fnames:
            code, tags = self.tags_from_filename(fname)
            all_tags += tags
            code_map[fname] = code

        raw_graph = build_tag_graph(all_tags, code_map)
        graph = only_defs(raw_graph)

        if self.tag_graphs is not None:
            self.tag_graphs[tuple(clean_fnames)] = graph
        return graph

    def tags_from_filename(self, fname):
        def get_tags_raw_function(fname):
            code = read_text(fname)
            rel_fname = self.file_group.get_rel_fname(fname)
            data = get_tags_raw(fname, rel_fname, code)
            assert isinstance(data, list)
            return code, data

        return self.file_group.cached_function_call(fname, get_tags_raw_function)

    def get_ranked_tags(
        self,
        args: RepoMapArgs,
    ):

        # Check file names for validity
        fnames = sorted(set(args.chat_fnames).union(set(args.other_fnames)))
        cleaned = self.file_group.validate_fnames(fnames)

        # All the source code parsing happens here
        tag_graph = self.get_tag_graph(cleaned)
        self.code_renderer.code_map = tag_graph.code_renderer.code_map

        tags = list(tag_graph.nodes)

        if self.use_old_ranking:
            other_rel_fnames = [self.file_group.get_rel_fname(fname) for fname in args.other_fnames]
            ranked_tags = rank_tags(tags, args=args, other_rel_fnames=other_rel_fnames)
        else:
            ranked_tags = rank_tags_new(
                tag_graph,
                args=args,
            )

        return ranked_tags

    def find_best_tag_tree(
        self,
        ranked_tags: list,
    ):
        """Does a binary search over the number of tags to include in the map,
        to find the largest map that fits within the token limit.
        """
        num_tags = len(ranked_tags)
        lower_bound = 0
        upper_bound = num_tags
        best_tree = None
        best_tree_tokens = 0

        # Guess a small starting number to help with giant repos
        middle = min(self.max_map_tokens // 25, num_tags)

        while lower_bound <= upper_bound:
            used_tags = [tag for tag in ranked_tags[:middle]]
            tree = self.code_renderer.to_tree(used_tags)
            num_tokens = self.token_count(tree)

            if self.max_map_tokens > num_tokens > best_tree_tokens:
                best_tree = tree
                best_tree_tokens = num_tokens

            if num_tokens < self.max_map_tokens:
                lower_bound = middle + 1
            else:
                upper_bound = middle - 1

            middle = (lower_bound + upper_bound) // 2

        return best_tree

    def repo_map_from_message(
        self,
        message: str,
        mentioned_entities: Set[str] | None = None,
        add_prefix: bool = False,
        llm=None,
    ) -> str:
        all_files = self.file_group.get_all_filenames()
        added_files = self.file_group.files_for_modification
        other_files = set(all_files) - set(added_files)

        if llm is not None:
            search_terms = search_terms_from_message(message, llm)
        else:
            search_terms = set()

        mentioned_fnames = self.file_group.get_file_mentions(message)
        mentioned_idents = get_ident_mentions(message)

        all_rel_fnames = [self.file_group.get_rel_fname(f) for f in all_files]
        mentioned_fnames.update(get_ident_filename_matches(mentioned_idents, all_rel_fnames))

        args = RepoMapArgs(
            chat_fnames=added_files or {},
            other_fnames=other_files or {},
            mentioned_fnames=mentioned_fnames or {},
            mentioned_idents=mentioned_idents or {},
            mentioned_entities=mentioned_entities or {},
            search_terms=search_terms,
            add_prefix=add_prefix,
        )

        repo_content = self.get_repo_map(args)

        # fall back to global repo map if files in chat are disjoint from rest of repo
        if not repo_content:
            args.chat_fnames = set()
            args.other_fnames = set(all_files)

            repo_content = self.get_repo_map(args)

        # fall back to completely unhinted repo
        if not repo_content:
            args = RepoMapArgs(search_terms=search_terms, add_prefix=add_prefix)

            repo_content = self.get_repo_map(args)

        return repo_content


def search_terms_from_message(message: str, llm) -> Set[str]:
    search_prompt = f"""You are an expert bug fixer. You are given a bug report. 
        Return a JSON list of at most 10 strings extracted from the bug report, that should be used
        in a full-text search of the codebase to find the part of the code that needs to be modified. 
        Select at most 10 strings that are most likely to be unique to the part of the code that needs to be modified.
        ONLY extract strings that you could expect to find verbatim in the code, especially function names,
        class names, and error messages. 
        For method calls, such as `foo.bar()`, extract `.bar(` 

        For error messages, extract the bits of the error message that are likely to be found VERBATIM in the code, 
        for example "File not found: " rather than "File not found: /amger/gae/doc.tcx"; 
        return "A string is required" rather than "A string is required, not 'MyWeirdClassName'".

        Here is the problem description:
        {message}"""

    class ListOfStrings(BaseModel):
        strings: List[str] = Field(
            description="List of full-text search strings to find the part of the code that needs to be modified."
        )

    out = llm.with_structured_output(ListOfStrings).invoke(search_prompt)
    re_out = [x.split(".")[-1] for x in out.strings]
    re_out = sum([x.split(",") for x in re_out], [])
    return set(re_out)
