from models.checklist import Checklist, ChecklistItem
from db import checklists as checklist_repo


def create_checklist(user_id: int, name: str) -> Checklist:
    return checklist_repo.create(user_id, name)


def get_checklist(user_id: int, name: str) -> Checklist | None:
    return checklist_repo.get_by_name(user_id, name)


def get_all_checklists(user_id: int) -> list[Checklist]:
    return checklist_repo.get_all(user_id)


def delete_checklist(checklist_id: int) -> None:
    checklist_repo.delete(checklist_id)


def add_item(checklist_id: int, text: str) -> ChecklistItem:
    return checklist_repo.add_item(checklist_id, text)


def get_items(checklist_id: int) -> list[ChecklistItem]:
    return checklist_repo.get_items(checklist_id)


def toggle_item(item_id: int, checked: bool) -> None:
    checklist_repo.toggle_item(item_id, checked)


def reset_items(checklist_id: int) -> None:
    checklist_repo.reset_items(checklist_id)
