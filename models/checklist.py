from dataclasses import dataclass


@dataclass
class Checklist:
    id: int
    user_id: int
    name: str


@dataclass
class ChecklistItem:
    id: int
    checklist_id: int
    text: str
    checked: bool
    position: int
