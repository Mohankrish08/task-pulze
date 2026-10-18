from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
UPDATE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
DELETE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
)

_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


def _id(what: str) -> object:
    return Field(description=f"Todoist {what} ID.", pattern=_ID_PATTERN)


TaskId = Annotated[str, _id("task")]
ProjectId = Annotated[str, _id("project")]
SectionId = Annotated[str, _id("section")]
LabelId = Annotated[str, _id("label")]
CommentId = Annotated[str, _id("comment")]
ReminderId = Annotated[str, _id("reminder")]

OptProjectId = Annotated[str | None, Field(default=None, pattern=_ID_PATTERN)]
OptSectionId = Annotated[str | None, Field(default=None, pattern=_ID_PATTERN)]
OptTaskId = Annotated[str | None, Field(default=None, pattern=_ID_PATTERN)]

Limit = Annotated[int, Field(ge=1, le=500, description="Maximum number of items to return.")]

Color = Annotated[
    str | None,
    Field(default=None, description="Todoist color name, e.g. 'red', 'blue', 'grey'."),
]
