"""The id of a task: what one looks like, and what its letter and its number say.

Plan tasks are T1, T2, ...; fixes for failing CI checks are C1, C2, ...; review remediation of
finding Fn is Rn. The task domain keys its rows by this id, and a contract command belongs to the
task whose id starts the command's own.
"""

TASK_ID_PATTERN = r'^[TCR][0-9]{1,6}$'
PLAN_TASK = 'T'


def is_plan_task(task_id: str) -> bool:
    return task_id.startswith(PLAN_TASK)


def task_number(task_id: str) -> int:
    return int(task_id[1:])
