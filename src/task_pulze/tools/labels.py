from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from task_pulze.models import Deleted, Label
from task_pulze.todoist import call, collect, todoist
from task_pulze.tools.common import DELETE, READ, UPDATE, WRITE, Color, LabelId, Limit

Name = Annotated[str, Field(min_length=1, max_length=60)]
OptName = Annotated[str | None, Field(default=None, min_length=1, max_length=60)]


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ)
    async def list_labels(ctx: Context, limit: Limit = 200) -> list[Label]:
        """List the user's personal labels."""
        api = todoist(ctx)
        labels = await collect(api.get_labels(), "Labels", limit)
        return [Label.from_sdk(label) for label in labels]

    @mcp.tool(annotations=WRITE)
    async def create_label(
        ctx: Context, name: Name, color: Color = None, is_favorite: bool | None = None
    ) -> Label:
        """Create a personal label."""
        api = todoist(ctx)
        label = await call(
            api.add_label(name=name, color=color, is_favorite=is_favorite),  # type: ignore[arg-type]
            "New label",
        )
        return Label.from_sdk(label)

    @mcp.tool(annotations=UPDATE)
    async def update_label(
        ctx: Context,
        label_id: LabelId,
        name: OptName = None,
        color: Color = None,
        is_favorite: bool | None = None,
    ) -> Label:
        """Update a label. Only the fields you pass are changed."""
        api = todoist(ctx)
        label = await call(
            api.update_label(label_id, name=name, color=color, is_favorite=is_favorite),  # type: ignore[arg-type]
            f"Label {label_id}",
        )
        return Label.from_sdk(label)

    @mcp.tool(annotations=DELETE)
    async def delete_label(label_id: LabelId, ctx: Context) -> Deleted:
        """Delete a label. Tasks keep existing but lose the label."""
        api = todoist(ctx)
        await call(api.delete_label(label_id), f"Label {label_id}")
        return Deleted(id=label_id)
