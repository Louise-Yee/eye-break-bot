from dataclasses import dataclass


@dataclass
class ClockStatus:
    user_id: int
    clocked_in: bool
    breaks_taken: int
    breaks_missed: int
