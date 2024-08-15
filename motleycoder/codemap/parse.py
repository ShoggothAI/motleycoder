import os
from typing import List

from grep_ast import filename_to_lang
from pygments.lexers import guess_lexer_for_filename
from pygments.token import Token
from pygments.util import ClassNotFound
from tree_sitter import Tree, Query, Node
from tree_sitter_languages import get_language
from tree_sitter_languages import get_parser  # noqa: E402

from motleycrew.common import logger
from .tag import Tag


def get_query(lang: str) -> Query | None:
    language = get_language(lang)
    # Load the tags queries
    here = os.path.dirname(__file__)
    scm_fname = os.path.realpath(os.path.join(here, "../queries", f"tree-sitter-{lang}-tags.scm"))
    if not os.path.exists(scm_fname):
        return None

    with open(scm_fname, "r") as file:
        query_scm = file.read()

    # Run the tags queries
    query = language.query(query_scm)
    return query


def ast_to_tags(
    full_file_code: str,
    tree: Tree,
    query: Query,
    rel_fname: str,
    fname: str,
    language: str | None = None,
) -> List[Tag]:
    # TODO: extract docstrings and comments to do RAG on
    captures = list(query.captures(tree.root_node))
    defs = []
    refs = []
    names = []

    for node, tag in captures:
        if tag.startswith("name"):
            names.append(node)
        elif tag.startswith("reference"):
            refs.append((node, "ref"))
        elif tag.startswith("definition"):
            defs.append((node, "def"))
        else:
            continue

    out = []
    for node, kind in defs + refs:
        name_node = node2namenode(node, names)
        if name_node is None:
            # logging.warning(f"Could not find name node for {node}")
            # TODO: should we populate these anyway, eg by parsing the text?
            continue

        parent_defs = get_def_parents(node, [d[0] for d in defs])
        parent_names = tuple([namenode2name(node2namenode(d, names)) for d in parent_defs])

        out.append(
            Tag(
                rel_fname=rel_fname.replace("\\", "/"),
                fname=fname.replace("\\", "/"),
                name=namenode2name(name_node),
                parent_names=parent_names,
                kind=kind,
                docstring=node2docstring(node, language) if kind == "def" else "",
                line=name_node.start_point[0],
                end_line=node.end_point[0],
                text=node.text.decode("utf-8"),
                byte_range=node.byte_range,
                language=language,
            )
        )

    return out


def node2docstring(node: Node, language: str) -> str:
    if language == "python":
        docstring = extract_python_docstring(node.text.decode("utf-8"))
        # TODO: check for more kinds of docstring-like comments
        if docstring is None:
            cmt = [(i, n) for i, n in enumerate(node.children) if n.type == "comment"]
            if len(cmt):
                docstring = cmt[0][1].text.decode("utf-8")
                for j, (i, n) in enumerate(cmt[1:]):
                    # only look for adjacent comments
                    if i - j - 1 == cmt[0][0]:
                        docstring += "\n" + n.text.decode("utf-8")
        return docstring if docstring is not None else ""
    else:
        logger.warning(f"Docstrings not yet implemented for {language}")
        return ""


def extract_python_docstring(code: str) -> str | None:
    import ast

    # Parse the code into an AST
    tree = ast.parse(code)

    # Initialize the docstring variable
    docstring = None

    # Traverse the AST to find the first function, method, or class definition
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Extract the docstring
            docstring = ast.get_docstring(node)
            break

    return docstring


def node2namenode(node: Node, name_nodes: List[Node]) -> Node | None:
    tmp = [n for n in name_nodes if n in node.children]

    if len(tmp) > 0:
        return tmp[0]

    # method calls
    tmp = [n for n in node.children if n.type == "attribute"]
    if len(tmp) == 0:
        logger.warning(f"Could not find name node for {node}")
        return None
    # method name
    tmp = [n for n in name_nodes if n in tmp[0].children]

    if len(tmp) == 0:
        logger.warning(f"Could not find name node for {node}")
        return None

    return tmp[0]


def namenode2name(node: Node | None) -> str:
    return node.text.decode("utf-8") if node else ""


def get_def_parents(node: Node, defs: List[Node]) -> List[Node]:
    dp = []
    while node.parent is not None:
        if node.parent in defs:
            dp.append(node.parent)
        node = node.parent
    return tuple(reversed(dp))


def refs_from_lexer(rel_fname, fname, code, language: str | None = None):
    try:
        lexer = guess_lexer_for_filename(fname, code)
    except ClassNotFound:
        return []

    tokens = list(lexer.get_tokens(code))
    tokens = [token[1] for token in tokens if token[0] in Token.Name]

    out = [
        Tag(
            rel_fname=rel_fname,
            fname=fname,
            name=token,
            kind="ref",
            line=-1,
            end_line=-1,
            text="",
            byte_range=(0, 0),
            language=language,
            docstring="",
        )
        for token in tokens
    ]
    return out


def get_tags_raw(fname, rel_fname, code) -> list[Tag]:
    lang = filename_to_lang(fname)
    if not lang:
        return []

    parser = get_parser(lang)

    if not code:
        return []

    ast = parser.parse(bytes(code, "utf-8"))
    query = get_query(lang)
    if not query:
        return []

    pre_tags = ast_to_tags(code, ast, query, rel_fname, fname, lang)

    saw = set([tag.kind for tag in pre_tags])
    if "ref" in saw or "def" not in saw:
        return pre_tags

    # We saw defs, without any refs
    # Some tags files only provide defs (cpp, for example)
    # Use pygments to backfill refs
    refs = refs_from_lexer(rel_fname, fname, code, lang)
    out = pre_tags + refs
    return out


def read_text(filename: str, encoding: str = "utf-8") -> str | None:
    try:
        with open(str(filename), "r", encoding=encoding) as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"{filename}: file not found error")
        return
    except IsADirectoryError:
        logger.error(f"{filename}: is a directory")
        return
    except UnicodeError as e:
        logger.error(f"{filename}: {e}")
        logger.error("Use encoding parameter to set the unicode encoding.")
        return
