from typing import TYPE_CHECKING

from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from typing import List, Optional

from motleycrew.common import logger
from motleycrew.tools import MotleyTool

from aider.codemap.repomap import RepoMap
from aider.codemap.render import RenderCode
from aider.codemap.tag import Tag

if TYPE_CHECKING:
    from .motleycrew_coder import MotleyCrewCoder


class GetFullTextToolInput(BaseModel):
    entity_name: Optional[str] = Field(description="Name of the entity to inspect.", default=None)
    file_name: Optional[str] = Field(
        description="Full or partial name of the file(s) to inspect", default=None
    )
    first_line: Optional[int] = Field(
        description="First line of the code snippet to return", default=None
    )


class GetFullTextTool(MotleyTool):
    def __init__(self, repo_map: RepoMap):
        self.repo_map = repo_map
        self.requested_tags = set()

        langchain_tool = StructuredTool.from_function(
            func=self.get_full_text,
            name="Get_Full_Text",
            description=""""Get the full code text of the entity with a given name. 
            Valid entities are function names, class names,
            method names prefixed with class, like `Foo.bar`. 
            You can restrict your search to specific files by supplying the optional file_name argument.
            Do NOT use this tool to inspect whole files - use the inspect_entity tool for that.
            You MUST supply at least the entity_name.
            """,
            args_schema=GetFullTextToolInput,
        )
        super().__init__(langchain_tool)

    def get_full_text(
        self,
        entity_name: Optional[str] = None,
        file_name: Optional[str] = None,
        first_line: Optional[int] = None,
    ) -> str:
        if entity_name is None:
            return "Please make sure to supply an entity name as an input to this tool"

        entity_name = entity_name.replace("()", "")

        if (entity_name, file_name) in self.requested_tags:
            return "You've already requested that one!"
        else:
            self.requested_tags.add((entity_name, file_name))

        tag_graph = self.repo_map.get_tag_graph()

        re_tags = tag_graph.get_tags_from_entity_name(entity_name, file_name)

        if not re_tags:  # maybe it was an explicit import?
            return f"Definition of entity {entity_name}  not found in the repo"
        elif len(re_tags) == 1:
            return RenderCode.text_with_line_numbers(re_tags[0])
        else:
            # Can get multiple tags eg when requesting a whole file
            if isinstance(first_line, int):
                sort = sorted(re_tags, key=lambda x: abs(x.line - first_line))
                return RenderCode.text_with_line_numbers(sort[0])

            return """Your query matches more than one entity, see the summary of the matches below.
            Please refine your query to match only one entity.
            """ + tag_graph.code_renderer.to_tree(
                re_tags
            )
