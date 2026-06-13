from datetime import datetime

user_last_reminded: dict[int, datetime] = {}
clock_in_prompted: set[int] = set()
