from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from motleycrew.common import logger
from motleycrew.tools import MotleyTool

from motleycoder.codemap.file_group import FileGroup
from motleycoder.user_interface import UserInterface


class AddFilesToolInput(BaseModel):
    files: list[str] = Field(description="List of file paths to add to the chat.")


class AddFilesTool(MotleyTool):
    def __init__(
        self,
        file_group: FileGroup,
        user_interface: UserInterface,
        name: str = "add_files",
    ):
        self.file_group = file_group
        self.user_interface = user_interface

        langchain_tool = StructuredTool.from_function(
            func=self.add_files,
            name=name,
            description="""Add files to the list of files available for modification. 
            Only files that are already in the list of files available for modification can be modified.""",
            args_schema=AddFilesToolInput,
        )
        super().__init__(langchain_tool)

    def add_files(self, files: list[str]):
        added_files = []
        for file in files:
            if not self.user_interface.confirm(f"Add {file} to the list of modifiable files?"):
                continue

            abs_filename = self.file_group.abs_root_path(file)
            logger.info(f"Trying to add to the list of modifiable files: {abs_filename}")

            content = self.read_text_file(abs_filename)
            if content is None:
                logger.error(f"Error reading {abs_filename}, skipping it.")
                continue
            self.file_group.add_for_modification(file)
            added_files.append(file)
            logger.info(f"Added {abs_filename} to the list of modifiable files.")

        if not added_files:
            return "No files were added to the list of modifiable files."
        else:
            return (
                f"Added the following files to the list of modifiable files: {', '.join(added_files)}, "
                f"please use the `inspect_entity` tool to inspect them."
            )

    # Should be using the inspect_object_tool instead
    # def make_files_content_prompt(self, files):
    #     prompt = self.coder.gpt_prompts.files_content_prefix
    #     for filename, content in self.get_files_content(files):
    #         if not is_image_file(filename):
    #             prompt += "\n"
    #             prompt += filename
    #
    #             prompt += f"\n```\n"
    #             prompt += content
    #             prompt += f"```\n"
    #
    #     return prompt

    # def get_file_content(self, files: list[str]):
    #     for filename in files:
    #         abs_filename = self.coder.abs_root_path(filename)
    #         content = self.read_text_file(abs_filename)
    #
    #         if content is None:
    #             logger.warning(f"Error reading {filename}, dropping it from the chat.")
    #             self.coder.abs_fnames.remove(abs_filename)
    #         else:
    #             yield filename, content

    # TODO: move this to the FileGroup class
    def read_text_file(self, filename: str):
        try:
            with open(str(filename), "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"{filename}: file not found error")
        except IsADirectoryError:
            logger.error(f"{filename}: is a directory")
            return
        except UnicodeError as e:
            logger.error(f"{filename}: {e}")
            return
