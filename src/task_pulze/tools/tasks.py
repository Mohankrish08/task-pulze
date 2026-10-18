from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from task_pulze.errors import InvalidRequestError
from task_pulze.models import Deleted, Done, Priority, Task, priority_to_api
from task_pulze.todoist import call, collect, todoist
from task_pulze.tools.common import (
    DELETE,
    READ,
    UPDATE,
    WRITE,
    Limit,
    OptProjectId,
    OptSectionId,
    OptTaskId,
    TaskId,
)

Content = Annotated[str, Field(min_length=1, max_length=500, description="Task title.")]
Description = Annotated[str | None, Field(default=None, max_length=16383)]
Labels = Annotated[list[str] | None, Field(default=None, description="Label names.")]
DueString = Annotated[
    str | None,
    Field(
        default=None,
        max_length=150,
        description="Natural-language due date, e.g. 'tomorrow 5pm', 'every friday'.",
    ),
]
DueDate = Annotated[date | None, Field(default=None, description="All-day due date.")]
DueDatetime = Annotated[
    datetime | None, Field(default=None, description="Due date and time (ISO 8601).")
]
Deadline = Annotated[date | None, Field(default=None, description="Hard deadline date.")]
Duration = Annotated[int | None, Field(default=None, ge=1, description="Estimated duration.")]
DurationUnit = Literal["minute", "day"]


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ)
    async def list_tasks(
        ctx: Context,
        project_id: OptProjectId = None,
        section_id: OptSectionId = None,
        parent_id: OptTaskId = None,
        label: str | None = None,
        limit: Limit = 100,
    ) -> list[Task]:
        """List active tasks, optionally filtered by project, section, parent task or label."""
        api = todoist(ctx)
        tasks = await collect(
            api.get_tasks(
                project_id=project_id, section_id=section_id, parent_id=parent_id, label=label
            ),
            "Tasks",
            limit,
        )
        return [Task.from_sdk(t) for t in tasks]

    @mcp.tool(annotations=READ)
    async def search_tasks(
        ctx: Context,
        query: Annotated[
            str,
            Field(
                min_length=1,
                max_length=1024,
                description=(
                    "Todoist filter query, e.g. 'today', 'overdue', 'today | overdue', "
                    "'7 days', 'p1', '#Work & @urgent', 'no date', 'search: report'."
                ),
            ),
        ],
        limit: Limit = 100,
    ) -> list[Task]:
        """Find active tasks with a Todoist filter query. Use it to review today's schedule,
        overdue work, upcoming tasks, priorities, or tasks by project/label."""
        api = todoist(ctx)
        tasks = await collect(api.filter_tasks(query=query), "Tasks", limit)
        return [Task.from_sdk(t) for t in tasks]

    @mcp.tool(annotations=READ)
    async def get_task(task_id: TaskId, ctx: Context) -> Task:
        """Get the full details of one active task."""
        api = todoist(ctx)
        return Task.from_sdk(await call(api.get_task(task_id), f"Task {task_id}"))

    @mcp.tool(annotations=WRITE)
    async def create_task(
        ctx: Context,
        content: Content,
        description: Description = None,
        project_id: OptProjectId = None,
        section_id: OptSectionId = None,
        parent_id: OptTaskId = None,
        labels: Labels = None,
        priority: Priority | None = None,
        due_string: DueString = None,
        due_date: DueDate = None,
        due_datetime: DueDatetime = None,
        deadline_date: Deadline = None,
        duration: Duration = None,
        duration_unit: DurationUnit | None = None,
    ) -> Task:
        """Create a task. Without project_id it goes to the Inbox. Set only one of
        due_string, due_date or due_datetime."""
        api = todoist(ctx)
        task = await call(
            api.add_task(
                content=content,
                description=description,
                project_id=project_id,
                section_id=section_id,
                parent_id=parent_id,
                labels=labels,
                priority=priority_to_api(priority) if priority else None,
                due_string=due_string,
                due_date=due_date,
                due_datetime=due_datetime,
                deadline_date=deadline_date,
                duration=duration,
                duration_unit=duration_unit if duration else None,
            ),
            "New task",
        )
        return Task.from_sdk(task)

    @mcp.tool(annotations=WRITE)
    async def quick_add_task(
        ctx: Context,
        text: Annotated[
            str,
            Field(
                min_length=1,
                max_length=1000,
                description="Todoist quick-add text, e.g. 'Pay rent every 1st #Home p1 @bills'.",
            ),
        ],
    ) -> Task:
        """Create a task from natural language, parsing #project, @label, p1-p4 and dates."""
        api = todoist(ctx)
        return Task.from_sdk(await call(api.add_task_quick(text=text), "New task"))

    @mcp.tool(annotations=UPDATE)
    async def update_task(
        ctx: Context,
        task_id: TaskId,
        content: Annotated[str | None, Field(default=None, min_length=1, max_length=500)] = None,
        description: Description = None,
        labels: Labels = None,
        priority: Priority | None = None,
        due_string: DueString = None,
        due_date: DueDate = None,
        due_datetime: DueDatetime = None,
        deadline_date: Deadline = None,
        duration: Duration = None,
        duration_unit: DurationUnit | None = None,
    ) -> Task:
        """Update a task's fields. Only the fields you pass are changed. Use due_string
        'no date' to remove the due date. To move a task, use move_task."""
        api = todoist(ctx)
        task = await call(
            api.update_task(
                task_id,
                content=content,
                description=description,
                labels=labels,
                priority=priority_to_api(priority) if priority else None,
                due_string=due_string,
                due_date=due_date,
                due_datetime=due_datetime,
                deadline_date=deadline_date,
                duration=duration,
                duration_unit=duration_unit if duration else None,
            ),
            f"Task {task_id}",
        )
        return Task.from_sdk(task)

    @mcp.tool(annotations=UPDATE)
    async def complete_task(task_id: TaskId, ctx: Context) -> Done:
        """Mark a task as done. Recurring tasks move to their next date."""
        api = todoist(ctx)
        await call(api.complete_task(task_id), f"Task {task_id}")
        return Done(id=task_id)

    @mcp.tool(annotations=UPDATE)
    async def reopen_task(task_id: TaskId, ctx: Context) -> Done:
        """Reopen a completed task."""
        api = todoist(ctx)
        await call(api.uncomplete_task(task_id), f"Task {task_id}")
        return Done(id=task_id)

    @mcp.tool(annotations=UPDATE)
    async def move_task(
        task_id: TaskId,
        ctx: Context,
        project_id: OptProjectId = None,
        section_id: OptSectionId = None,
        parent_id: OptTaskId = None,
    ) -> Done:
        """Move a task to another project, section, or under a parent task. Pass exactly one."""
        if sum(x is not None for x in (project_id, section_id, parent_id)) != 1:
            raise InvalidRequestError("Pass exactly one of project_id, section_id or parent_id.")
        api = todoist(ctx)
        await call(
            api.move_task(
                task_id, project_id=project_id, section_id=section_id, parent_id=parent_id
            ),
            f"Task {task_id}",
        )
        return Done(id=task_id)

    @mcp.tool(annotations=DELETE)
    async def delete_task(task_id: TaskId, ctx: Context) -> Deleted:
        """Permanently delete a task and its sub-tasks. Prefer complete_task for finished work."""
        api = todoist(ctx)
        await call(api.delete_task(task_id), f"Task {task_id}")
        return Deleted(id=task_id)

    @mcp.tool(annotations=READ)
    async def list_completed_tasks(
        ctx: Context,
        since: Annotated[
            datetime | None,
            Field(default=None, description="Start (ISO 8601). Default: 7 days ago."),
        ] = None,
        until: Annotated[
            datetime | None, Field(default=None, description="End (ISO 8601). Default: now.")
        ] = None,
        limit: Limit = 100,
    ) -> list[Task]:
        """List tasks completed in a time window (max ~3 months), for reviews and reports."""
        # Small buffer so tasks completed seconds ago aren't lost to clock skew.
        until = until or datetime.now(UTC) + timedelta(minutes=5)
        since = since or until - timedelta(days=7)
        if since >= until:
            raise InvalidRequestError("'since' must be before 'until'.")
        api = todoist(ctx)
        tasks = await collect(
            api.get_completed_tasks_by_completion_date(since=since, until=until),
            "Completed tasks",
            limit,
        )
        return [Task.from_sdk(t) for t in tasks]
