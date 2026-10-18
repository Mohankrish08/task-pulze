from datetime import datetime
from typing import Annotated, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from task_pulze.errors import InvalidRequestError
from task_pulze.models import Deleted, Reminder
from task_pulze.todoist import call, collect, todoist
from task_pulze.tools.common import DELETE, READ, WRITE, Limit, OptTaskId, ReminderId, TaskId


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ)
    async def list_reminders(
        ctx: Context, task_id: OptTaskId = None, limit: Limit = 100
    ) -> list[Reminder]:
        """List reminders, optionally only for one task. Reminders need Todoist Pro."""
        api = todoist(ctx)
        reminders = await collect(api.get_reminders(task_id=task_id), "Reminders", limit)
        return [Reminder.from_sdk(r) for r in reminders]

    @mcp.tool(annotations=WRITE)
    async def add_reminder(
        ctx: Context,
        task_id: TaskId,
        due_string: Annotated[
            str | None,
            Field(default=None, description="When to remind, e.g. 'tomorrow 9am'."),
        ] = None,
        due_datetime: Annotated[
            datetime | None, Field(default=None, description="Exact reminder time (ISO 8601).")
        ] = None,
        minutes_before_due: Annotated[
            int | None,
            Field(default=None, ge=0, description="Remind this many minutes before the due time."),
        ] = None,
        service: Literal["push", "email"] | None = None,
    ) -> Reminder:
        """Add a reminder to a task: either at a fixed time (due_string or due_datetime) or
        relative to the task's due time (minutes_before_due). Needs Todoist Pro."""
        absolute = due_string is not None or due_datetime is not None
        if absolute == (minutes_before_due is not None):
            raise InvalidRequestError(
                "Pass either a time (due_string or due_datetime) or minutes_before_due."
            )
        api = todoist(ctx)
        reminder = await call(
            api.add_reminder(
                task_id=task_id,
                reminder_type="absolute" if absolute else "relative",
                due_string=due_string,
                due_datetime=due_datetime,
                minute_offset=minutes_before_due,
                service=service,
            ),
            f"Reminder for task {task_id}",
        )
        return Reminder.from_sdk(reminder)

    @mcp.tool(annotations=DELETE)
    async def delete_reminder(reminder_id: ReminderId, ctx: Context) -> Deleted:
        """Delete a reminder."""
        api = todoist(ctx)
        await call(api.delete_reminder(reminder_id), f"Reminder {reminder_id}")
        return Deleted(id=reminder_id)
