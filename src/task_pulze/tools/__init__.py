from mcp.server.fastmcp import FastMCP

from task_pulze.tools import comments, labels, projects, reminders, sections, tasks


def register_all(mcp: FastMCP) -> None:
    for module in (tasks, projects, sections, labels, comments, reminders):
        module.register(mcp)
