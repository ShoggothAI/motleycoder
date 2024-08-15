from typing import List

from grep_ast import TreeContext

from .tag import Tag


class RenderCode:
    def __init__(self):
        self.tree_cache = {}
        self.code_map = {}

    def to_tree(self, tags: List[Tag | tuple]) -> str:
        if not tags:
            return ""

        tags = sorted(tags, key=lambda x: tuple(x))

        cur_fname = None
        cur_abs_fname = None
        lois = None
        output = ""

        # add a bogus tag at the end so we trip the this_fname != cur_fname...
        dummy_tag = (None,)
        for tag in tags + [dummy_tag]:
            this_rel_fname = tag[0]

            # ... here ... to output the final real entry in the list
            if this_rel_fname != cur_fname:
                if lois is not None:
                    output += "\n"
                    output += cur_fname + ":\n"
                    output += self.render_tree(cur_fname, lois, code=self.code_map[cur_abs_fname])
                    lois = None
                elif cur_fname:
                    output += "\n" + cur_fname + "\n"
                if type(tag) is Tag:
                    lois = []
                    cur_abs_fname = tag.fname
                cur_fname = this_rel_fname

            if lois is not None:
                lois.append(tag.line)

        # truncate long lines, in case we get minified js or something else crazy
        output = "\n".join([line[:100] for line in output.splitlines()]) + "\n"

        return output

    def render_tree(self, rel_fname, lois, line_number: bool = True, code="") -> str:
        key = (rel_fname, tuple(sorted(lois)))

        if key in self.tree_cache:
            return self.tree_cache[key]

        if code and not code.endswith("\n"):
            code += "\n"

        context = TreeContext(
            rel_fname,
            code,
            color=False,
            line_number=line_number,
            child_context=False,
            last_line=False,
            margin=0,
            mark_lois=False,
            loi_pad=0,
            # header_max=30,
            show_top_of_file_parent_scope=False,
        )

        context.add_lines_of_interest(lois)
        context.add_context()
        res = context.format()
        self.tree_cache[key] = res
        return res

    @staticmethod
    def text_with_line_numbers(t: Tag) -> str:
        out = []
        for i, line in enumerate(t.text.split("\n")):
            re_line = f"{i+1+t.line:3}│{line}"
            out.append(re_line)
        return "\n".join(out)
