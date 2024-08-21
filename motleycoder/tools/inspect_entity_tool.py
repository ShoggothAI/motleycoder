import os.path
from collections import deque
from pathlib import Path
from typing import Optional

from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tools import StructuredTool

from motleycoder.codemap.file_group import FileGroup
from motleycoder.codemap.repomap import RepoMap
from motleycoder.repo import GitRepo
from motleycrew.tools import MotleyTool


class InspectObjectToolInput(BaseModel):
    entity_name: Optional[str] = Field(description="Name of the entity to inspect.", default=None)
    file_name: Optional[str] = Field(
        description="Full or partial name of the file(s) to inspect", default=None
    )


class InspectEntityTool(MotleyTool):
    def __init__(
        self,
        repo_map: RepoMap,
        show_other_files: bool = False,
        max_lines_long=400,
        max_lines_short=50,
        block_identical_calls=2,
    ):
        self.repo_map = repo_map
        self.show_other_files = show_other_files
        self.max_lines_long = max_lines_long
        self.max_lines_short = max_lines_short

        self.requested_tags = deque(maxlen=block_identical_calls)

        langchain_tool = StructuredTool.from_function(
            func=self.get_object_summary,
            name="inspect_entity",
            description=""""Get the code of the entity with a given name, 
            including summary of the entities it references. Valid entities 
            are function names, class names, method names (prefix them by method name to disambiguate, like "Foo.bar")

            ONLY supply the file name/relative path if you need it to disambiguate the entity name,
            or if you want to inspect a whole file; in all other cases, just supply the entity name.
            You can also supply a partial file or directory name to get all files whose relative paths
            contain the partial name you supply.
            You can also request a whole file by name by omitting the entity name.
            """,
            args_schema=InspectObjectToolInput,
        )
        super().__init__(langchain_tool)

    def get_object_summary(
        self, entity_name: Optional[str] = None, file_name: Optional[str] = None
    ) -> str:
        entity_name = entity_name or None
        file_name = file_name or None

        if entity_name is None and file_name is None:
            return "Please supply either the file name or the entity name"

        if entity_name is not None:
            entity_name = entity_name.strip().replace("()", "")

        if (entity_name, file_name) in self.requested_tags:
            return (
                "You've already requested this entity recently, its contents are visible above. "
                "Please use existing information or request a different entity."
            )
        else:
            self.requested_tags.append((entity_name, file_name))

        tag_graph = self.repo_map.get_tag_graph(with_tests=True)

        if not entity_name:
            abs_file_path = self.repo_map.file_group.abs_root_path(file_name)
            try:
                file_content = Path(abs_file_path).read_text()
            except FileNotFoundError:
                return f"File {file_name} not found in the repo"
            except IsADirectoryError:
                files = self.repo_map.file_group.get_rel_fnames_in_directory(
                    abs_file_path, level=None
                )
                return f"{file_name} is a directory. Files in it:\n{"\n".join(sorted(files))}"

            if not file_content:
                return f"File {file_name} is empty"

            return tag_graph.get_file_representation(
                file_name=abs_file_path,
                file_content=file_content,
            )

        out = ""

        # TODO: if file_name is a directory, just list the files in it?
        re_tags = tag_graph.get_tags_from_entity_name(entity_name, file_name)
        if not len(re_tags) and entity_name is not None and "." in entity_name:
            entity_name_short = entity_name.split(".")[-1]
            out += f"Entity {entity_name} not found, searching for {entity_name_short}...\n"
            re_tags = tag_graph.get_tags_from_entity_name(entity_name_short, file_name)

        if not re_tags:  # maybe it was an explicit import?
            if entity_name is not None:
                out += (
                    f"Definition of entity {entity_name} not found in the repo. "
                    f"You can specify the entity name more broadly or omit it "
                    f"for reading the whole file."
                )
                if file_name is None or self.to_dir(file_name) is None:
                    return out  # Absolutely no directories to work with
                else:
                    candidate_dirs = [self.to_dir(file_name)]
            else:
                return f"File {file_name} not found in the repo"

        elif all(
            tag.fname == re_tags[0].fname and tag.full_name == re_tags[0].full_name
            for tag in re_tags
        ):
            repr_parts = [
                tag_graph.get_tag_representation(
                    t,
                    parent_details=True,
                    max_lines=self.max_lines_long,
                    force_include_full_text=True,
                )
                for t in re_tags
            ]
            out += "\n".join(repr_parts)
            candidate_dirs = [self.to_dir(t.fname) for t in re_tags]
        else:  # Can get multiple tags eg when requesting a whole file
            # TODO: this could be neater
            repr_parts = [
                tag_graph.get_tag_representation(
                    t, parent_details=False, max_lines=self.max_lines_short
                )
                for t in re_tags
            ]
            repr = "\n".join(repr_parts)

            if len(repr.split("\n")) < self.max_lines_long:
                out += repr
            else:
                repr = tag_graph.code_renderer.to_tree(re_tags)
                if len(repr.split("\n")) < self.max_lines_long:
                    out += repr
                else:
                    fnames = sorted(list(set(t.rel_fname for t in re_tags)))

                    out += (
                        "There are too many matches for the given query in the repo. "
                        "You can narrow down the search by specifying the file and/or entity name "
                        "more precisely. Here are the files that match the query:\n"
                    )
                    out += "\n".join(fnames)

            candidate_dirs = list(set([self.to_dir(t.fname) for t in re_tags]))

        files = set(
            sum(
                [self.repo_map.file_group.get_rel_fnames_in_directory(d) for d in candidate_dirs],
                [],
            )
        )

        mentioned_fnames = set([t.fname for t in re_tags])
        other_fnames = files - mentioned_fnames
        if other_fnames and self.show_other_files:
            out += "\nOther files in same directory(s):\n" + "\n".join(sorted(list(other_fnames)))
        return out

    def to_dir(self, rel_fname: str) -> str:
        abs_dir = self.repo_map.file_group.abs_root_path(rel_fname)
        if os.path.isfile(abs_dir):
            abs_dir = os.path.dirname(abs_dir)
        if os.path.isdir(abs_dir):
            return abs_dir
        else:
            return None


if __name__ == "__main__":
    from motleycoder.codemap.repomap import RepoMap

    repo_path = "/home/ubuntu/pytest"

    repo = GitRepo(repo_path)
    file_group = FileGroup(repo)

    repo_map = RepoMap(
        root=repo.root,
        llm_name="gpt-4o",
        repo_content_prefix=None,
        file_group=file_group,
        cache_graphs=True,
    )

    tool = InspectEntityTool(repo_map)
    print(
        tool.get_object_summary(
            file_name="src/_pytest/assertion/util.py",
            entity_name="_compare_eq_sequence",
        )
    )
