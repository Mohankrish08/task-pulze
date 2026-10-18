from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from task_pulze.errors import InvalidRequestError
from task_pulze.models import Comment, Deleted
from task_pulze.todoist import call, collect, todoist
from task_pulze.tools.common import DELETE, READ, UPDATE, WRITE, CommentId, Limit, OptProjectId, OptTaskId

Content = Annotated[str, Field(min_length=1, max_length=15000, description="Markdown supported.")]


def _one_target(task_id: str | None, project_id: str | None) -> None:
    if (task_id is None) == (project_id is None):
        raise InvalidRequestError("Pass exactly one of task_id or project_id.")


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ)
    async def list_comments(
        ctx: Context,
        task_id: OptTaskId = None,
        project_id: OptProjectId = None,
        limit: Limit = 100,
    ) -> list[Comment]:
        """List comments on a task or a project. Pass exactly one of task_id or project_id."""
        _one_target(task_id, project_id)
        api = todoist(ctx)
        comments = await collect(
            api.get_comments(task_id=task_id, project_id=project_id), "Comments", limit
        )
        return [Comment.from_sdk(c) for c in comments]

    @mcp.tool(annotations=WRITE)
    async def add_comment(
        ctx: Context,
        content: Content,
        task_id: OptTaskId = None,
        project_id: OptProjectId = None,
    ) -> Comment:
        """Add a comment to a task or a project. Pass exactly one of task_id or project_id."""
        _one_target(task_id, project_id)
        api = todoist(ctx)
        comment = await call(
            api.add_comment(content=content, task_id=task_id, project_id=project_id),
            "New comment",
        )
        return Comment.from_sdk(comment)

    @mcp.tool(annotations=UPDATE)
    async def update_comment(comment_id: CommentId, content: Content, ctx: Context) -> Comment:
        """Replace the text of a comment."""
        api = todoist(ctx)
        comment = await call(
            api.update_comment(comment_id, content=content), f"Comment {comment_id}"
        )
        return Comment.from_sdk(comment)

    @mcp.tool(annotations=DELETE)
    async def delete_comment(comment_id: CommentId, ctx: Context) -> Deleted:
        """Permanently delete a comment."""
        api = todoist(ctx)
        await call(api.delete_comment(comment_id), f"Comment {comment_id}")
        return Deleted(id=comment_id)
