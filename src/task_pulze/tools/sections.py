from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from task_pulze.models import Deleted, Section
from task_pulze.todoist import call, collect, todoist
from task_pulze.tools.common import DELETE, READ, UPDATE, WRITE, Limit, OptProjectId, ProjectId, SectionId

Name = Annotated[str, Field(min_length=1, max_length=2048)]


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ)
    async def list_sections(
        ctx: Context, project_id: OptProjectId = None, limit: Limit = 200
    ) -> list[Section]:
        """List sections, optionally only those in one project."""
        api = todoist(ctx)
        sections = await collect(api.get_sections(project_id=project_id), "Sections", limit)
        return [Section.from_sdk(s) for s in sections]

    @mcp.tool(annotations=WRITE)
    async def create_section(name: Name, project_id: ProjectId, ctx: Context) -> Section:
        """Create a section in a project."""
        api = todoist(ctx)
        section = await call(api.add_section(name=name, project_id=project_id), "New section")
        return Section.from_sdk(section)

    @mcp.tool(annotations=UPDATE)
    async def rename_section(section_id: SectionId, name: Name, ctx: Context) -> Section:
        """Rename a section."""
        api = todoist(ctx)
        section = await call(api.update_section(section_id, name=name), f"Section {section_id}")
        return Section.from_sdk(section)

    @mcp.tool(annotations=DELETE)
    async def delete_section(section_id: SectionId, ctx: Context) -> Deleted:
        """Permanently delete a section and all tasks in it."""
        api = todoist(ctx)
        await call(api.delete_section(section_id), f"Section {section_id}")
        return Deleted(id=section_id)
