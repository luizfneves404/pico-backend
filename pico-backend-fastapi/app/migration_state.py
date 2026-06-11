from asyncio import Task

_migration_task: Task[None] | None = None


def set_migration_task(task: Task[None]) -> None:
    global _migration_task
    _migration_task = task


def get_migration_task() -> Task[None]:
    if _migration_task is None:
        raise RuntimeError("Migration task is not set")
    return _migration_task
