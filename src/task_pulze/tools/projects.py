from typing import Annotated, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from task_pulze.models import Deleted, Project
from task_pulze.todoist import call, collect, todoist
from task_pulze.tools.common import DELETE, READ, UPDATE, WRITE, Color, Limit, OptProjectId, ProjectId

Name = Annotated[str, Field(min_length=1, max_length=120)]
OptName = Annotated[str | None, Field(default=None, min_length=1, max_length=120)]
Description = Annotated[str | None, Field(default=None, max_length=16383)]
ViewStyle = Literal["list", "board", "calendar"]


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ)
    async def list_projects(ctx: Context, limit: Limit = 200) -> list[Project]:
        """List all active projects, including the Inbox."""
        api = todoist(ctx)
        projects = await collect(api.get_projects(), "Projects", limit)
        return [Project.from_sdk(p) for p in projects]

    @mcp.tool(annotations=READ)
    async def get_project(project_id: ProjectId, ctx: Context) -> Project:
        """Get one project."""
        api = todoist(ctx)
        return Project.from_sdk(await call(api.get_project(project_id), f"Project {project_id}"))

    @mcp.tool(annotations=WRITE)
    async def create_project(
        ctx: Context,
        name: Name,
        description: Description = None,
        parent_id: OptProjectId = None,
        color: Color = None,
        is_favorite: bool | None = None,
        view_style: ViewStyle | None = None,
    ) -> Project:
        """Create a project, optionally nested under parent_id."""
        api = todoist(ctx)
        project = await call(
            api.add_project(
                name=name,
                description=description,
                parent_id=parent_id,
                color=color,  # type: ignore[arg-type]
                is_favorite=is_favorite,
                view_style=view_style,
            ),
            "New project",
        )
        return Project.from_sdk(project)

    @mcp.tool(annotations=UPDATE)
    async def update_project(
        ctx: Context,
        project_id: ProjectId,
        name: OptName = None,
        description: Description = None,
        color: Color = None,
        is_favorite: bool | None = None,
        view_style: ViewStyle | None = None,
    ) -> Project:
        """Update a project's fields. Only the fields you pass are changed."""
        api = todoist(ctx)
        project = await call(
            api.update_project(
                project_id,
                name=name,
                description=description,
                color=color,  # type: ignore[arg-type]
                is_favorite=is_favorite,
                view_style=view_style,
            ),
            f"Project {project_id}",
        )
        return Project.from_sdk(project)

    @mcp.tool(annotations=UPDATE)
    async def archive_project(project_id: ProjectId, ctx: Context) -> Project:
        """Archive a project (it can be restored with unarchive_project)."""
        api = todoist(ctx)
        return Project.from_sdk(
            await call(api.archive_project(project_id), f"Project {project_id}")
        )

    @mcp.tool(annotations=UPDATE)
    async def unarchive_project(project_id: ProjectId, ctx: Context) -> Project:
        """Restore an archived project."""
        api = todoist(ctx)
        return Project.from_sdk(
            await call(api.unarchive_project(project_id), f"Project {project_id}")
        )

    @mcp.tool(annotations=DELETE)
    async def delete_project(project_id: ProjectId, ctx: Context) -> Deleted:
        """Permanently delete a project with all its sections and tasks. Prefer archive_project."""
        api = todoist(ctx)
        await call(api.delete_project(project_id), f"Project {project_id}")
        return Deleted(id=project_id)
