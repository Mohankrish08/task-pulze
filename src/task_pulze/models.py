"""Tool output schemas, decoupled from the Todoist SDK's dataclasses."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field
from todoist_api_python import models as sdk

Priority = Literal["P1", "P2", "P3", "P4"]


def _iso(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date | datetime):
        return value.isoformat()
    return str(value)


def priority_to_api(priority: Priority) -> int:
    return 5 - int(priority[1])


class Due(BaseModel):
    date: str = Field(description="Due date (YYYY-MM-DD) or ISO 8601 datetime.")
    string: str = Field(description="Human-readable due text, e.g. 'every monday'.")
    is_recurring: bool
    timezone: str | None = None

    @classmethod
    def from_sdk(cls, due: sdk.Due | None) -> Due | None:
        if due is None:
            return None
        return cls(
            date=_iso(due.date) or "",
            string=due.string,
            is_recurring=due.is_recurring,
            timezone=due.timezone,
        )


class Task(BaseModel):
    id: str
    content: str = Field(description="Task title.")
    description: str
    url: str
    project_id: str
    section_id: str | None = None
    parent_id: str | None = Field(default=None, description="Set when this is a sub-task.")
    labels: list[str] = Field(default_factory=list)
    priority: Priority = Field(description="P1 is most urgent, P4 is normal.")
    due: Due | None = None
    deadline: str | None = None
    duration: str | None = Field(default=None, description="e.g. '30 minute' or '2 day'.")
    assignee_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def from_sdk(cls, task: sdk.Task) -> Task:
        return cls(
            id=task.id,
            content=task.content,
            description=task.description,
            url=task.url,
            project_id=task.project_id,
            section_id=task.section_id,
            parent_id=task.parent_id,
            labels=list(task.labels or []),
            priority=f"P{5 - task.priority}",  # type: ignore[arg-type]
            due=Due.from_sdk(task.due),
            deadline=_iso(task.deadline.date) if task.deadline else None,
            duration=f"{task.duration.amount} {task.duration.unit}" if task.duration else None,
            assignee_id=task.assignee_id,
            created_at=_iso(task.created_at),
            updated_at=_iso(task.updated_at),
            completed_at=_iso(task.completed_at),
        )


class Project(BaseModel):
    id: str
    name: str
    description: str
    url: str
    parent_id: str | None = None
    color: str
    is_favorite: bool
    is_archived: bool
    is_shared: bool
    is_inbox: bool
    view_style: str

    @classmethod
    def from_sdk(cls, project: sdk.Project) -> Project:
        return cls(
            id=project.id,
            name=project.name,
            description=project.description,
            url=project.url,
            parent_id=project.parent_id,
            color=project.color,
            is_favorite=project.is_favorite,
            is_archived=project.is_archived,
            is_shared=project.is_shared,
            is_inbox=bool(project.is_inbox_project),
            view_style=project.view_style,
        )


class Section(BaseModel):
    id: str
    name: str
    project_id: str
    order: int

    @classmethod
    def from_sdk(cls, section: sdk.Section) -> Section:
        return cls(
            id=section.id, name=section.name, project_id=section.project_id, order=section.order
        )


class Label(BaseModel):
    id: str
    name: str
    color: str
    is_favorite: bool

    @classmethod
    def from_sdk(cls, label: sdk.Label) -> Label:
        return cls(id=label.id, name=label.name, color=label.color, is_favorite=label.is_favorite)


class Comment(BaseModel):
    id: str
    content: str
    posted_at: str | None = None
    poster_id: str
    task_id: str | None = None
    project_id: str | None = None
    attachment_url: str | None = None

    @classmethod
    def from_sdk(cls, comment: sdk.Comment) -> Comment:
        attachment = comment.attachment
        return cls(
            id=comment.id,
            content=comment.content,
            posted_at=_iso(comment.posted_at),
            poster_id=comment.poster_id,
            task_id=comment.task_id,
            project_id=comment.project_id,
            attachment_url=(attachment.file_url or attachment.url) if attachment else None,
        )


class Reminder(BaseModel):
    id: str
    task_id: str
    type: str = Field(description="'absolute' (fixed time) or 'relative' (before the due time).")
    due: Due | None = None
    minute_offset: int | None = None
    service: str | None = None

    @classmethod
    def from_sdk(cls, reminder: sdk.Reminder) -> Reminder:
        return cls(
            id=reminder.id,
            task_id=reminder.task_id,
            type=reminder.type,
            due=Due.from_sdk(reminder.due),
            minute_offset=reminder.minute_offset,
            service=reminder.service,
        )


class Deleted(BaseModel):
    id: str
    deleted: bool = True


class Done(BaseModel):
    id: str
    ok: bool = True
