from models.schedule import Schedule
from db import schedules as schedule_repo
from db import clock_status as clock_repo


def save_schedule(user_id: int, timezone: str, start_time: str, end_time: str) -> Schedule:
    schedule = Schedule(user_id=user_id, timezone=timezone, start_time=start_time, end_time=end_time)
    schedule_repo.save(schedule)
    return schedule


def remove_schedule(user_id: int) -> None:
    schedule_repo.delete(user_id)
    clock_repo.set_clocked_in(user_id, False)


def get_all_schedules() -> list[Schedule]:
    return schedule_repo.get_all()


def get_schedule(user_id: int) -> Schedule | None:
    return schedule_repo.get(user_id)
