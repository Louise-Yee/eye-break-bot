from dataclasses import dataclass


@dataclass
class Schedule:
    user_id: int
    timezone: str
    start_time: str
    end_time: str
