from models.clock_status import ClockStatus
from db import clock_status as clock_repo


def clock_in(user_id: int) -> None:
    clock_repo.set_clocked_in(user_id, True)
    clock_repo.reset_breaks(user_id)


def clock_out(user_id: int) -> None:
    clock_repo.set_clocked_in(user_id, False)


def get_status(user_id: int) -> ClockStatus:
    return clock_repo.get(user_id)


def get_clocked_in_users() -> list[int]:
    return clock_repo.get_clocked_in_users()
