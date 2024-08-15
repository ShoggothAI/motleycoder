from typing import List

from langchain_core.pydantic_v1 import BaseModel
from langchain_core.tools import StructuredTool

from motleycoder.codemap.file_group import FileGroup
from motleycrew.tools import MotleyTool


class GetModifiableFilesToolInput(BaseModel):
    pass


class GetModifiableFilesTool(MotleyTool):
    def __init__(self, file_group: FileGroup, name: str = "get_modifiable_files"):

        langchain_tool = StructuredTool.from_function(
            func=self.get_modifiable_files,
            name=name,
            description="Get the relative paths files that can be modified.",
            args_schema=GetModifiableFilesToolInput,
        )
        super().__init__(langchain_tool)

        self.file_group = file_group

    def get_modifiable_files(self) -> List[str]:
        files = self.file_group.files_for_modification
        return [self.file_group.get_rel_fname(file) for file in files]
