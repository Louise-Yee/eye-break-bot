from db import clock_status as clock_repo


def record_break(user_id: int, took: bool) -> None:
    clock_repo.record_break(user_id, took)
