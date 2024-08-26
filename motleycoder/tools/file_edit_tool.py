import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tools import StructuredTool

from motleycoder.codemap.file_group import FileGroup
from motleycoder.codemap.repomap import RepoMap
from motleycoder.linter import Linter
from motleycoder.prompts import MotleyCoderPrompts
from motleycoder.user_interface import UserInterface
from motleycrew.common import logger
from motleycrew.tools import MotleyTool

if TYPE_CHECKING:
    pass


class FileEditToolInput(BaseModel):
    file_path: str = Field(description="The file path to edit.")
    language: str = Field(description="The programming language of the file.")
    search: str = Field(description="The SEARCH block.")
    replace: str = Field(description="The REPLACE block.")


class FileEditTool(MotleyTool):
    def __init__(
        self,
        file_group: FileGroup,
        user_interface: UserInterface,
        repo_map: RepoMap,
        prompts: Optional[MotleyCoderPrompts] = None,
        linter: Optional[Linter] = None,
        name: str = "edit_file",
    ):
        # TODO: replace coder with specific components
        self.file_group = file_group
        self.user_interface = user_interface
        self.repo_map = repo_map

        self.prompts = prompts
        self.linter = linter

        langchain_tool = StructuredTool.from_function(
            func=self.edit_file,
            name=name,
            description="Make changes to a file using a *SEARCH/REPLACE* block.",
            args_schema=FileEditToolInput,
        )
        super().__init__(langchain_tool)

    def edit_file(self, file_path: str, language: str, search: str, replace: str) -> str:
        error_message = self.edit_file_inner(file_path, search, replace)
        if error_message:  # TODO: max_reflections
            return error_message

        if self.prompts:
            return self.prompts.file_edit_success.format(file_path=file_path)

        return f"Successfully edited file {file_path}."

    def prepare_file_for_edit(self, file_path: str):
        abs_path = self.file_group.abs_root_path(file_path)
        if abs_path not in self.file_group.files_for_modification:
            if not self.user_interface.confirm(f"Add {file_path} to the list of modifiable files?"):
                raise Exception(
                    f"The user rejected adding {file_path} to the list of modifiable files."
                )

            self.file_group.add_for_modification(file_path)

        if not Path(abs_path).exists():
            if not self.user_interface.confirm(f"Allow creation of new file {file_path}?"):
                raise Exception(f"User rejected creation of new file {file_path}.")

            Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
            Path(abs_path).touch()

    def invalidate_tag_graphs(self, file_path: str):
        if not self.repo_map.tag_graphs:
            return

        for files, graph in self.repo_map.tag_graphs.copy().items():
            if file_path in files:
                self.repo_map.tag_graphs.pop(files)

    def edit_file_inner(self, file_path: str, search: str, replace: str) -> str:
        if not search or search[-1] != "\n":
            search += "\n"
        if not replace or replace[-1] != "\n":
            replace += "\n"

        logger.info(
            f"""Trying to edit file {file_path}
<<<<<<< SEARCH
{search}=======
{replace}>>>>>>> REPLACE
"""
        )

        try:
            self.prepare_file_for_edit(file_path)
        except Exception as err:
            logger.error(f"Error preparing file for edit: {err}")
            return "Cannot edit file: " + str(err)

        try:
            # self.coder.dirty_commit()  # Add the file to the repo if it's not already there
            result, close_match = self.file_group.edit_file(file_path, search, replace)
            # self.git_repo.commit_changes(f"Edit file {file_path}")
        except Exception as err:
            logger.warning("Exception while updating file:")
            logger.warning(str(err))

            traceback.print_exc()
            return str(err)

        if not result:
            res = (
                f"## SearchReplaceNoExactMatch: This SEARCH argument failed to exactly match "
                f"lines in {file_path}"
            )
            if close_match:
                res += (
                    f"\nDid you mean to match some of these actual lines from {file_path}?\n"
                    f"```\n{close_match}\n```"
                )
            return res

        self.file_group.edited_files.add(file_path)
        self.invalidate_tag_graphs(file_path)

        if self.linter:
            errors = self.linter.lint(self.file_group.abs_root_path(file_path))
            if errors:
                logger.error(f"Lint errors in {file_path}: {errors}")
                if self.user_interface.confirm("Attempt to fix lint errors?"):
                    return errors


if __name__ == "__main__":
    from motleycoder.codemap.repomap import RepoMap
    from motleycoder.repo import GitRepo

    repo_path = "/Users/whimo/codegen/motleycrew"

    repo = GitRepo(repo_path)
    file_group = FileGroup(repo)

    repo_map = RepoMap(
        root=repo.root,
        llm_name="gpt-4o",
        repo_content_prefix=None,
        file_group=file_group,
        cache_graphs=True,
    )

    tool = FileEditTool(
        file_group=file_group,
        user_interface=UserInterface(yes=True),
        linter=Linter(),
        repo_map=repo_map,
        prompts=MotleyCoderPrompts(),
    )
    print(
        tool.edit_file(
            file_path="motleycrew/agents/parent.py",
            language="python",
            search="""from motleycrew import MotleyCrew""",
            replace="""from motleycrew import MotleyCrew
    from a import b
""",
        )
    )
