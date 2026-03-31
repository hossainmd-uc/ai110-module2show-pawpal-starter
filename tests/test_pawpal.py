import pytest
import sys
from pathlib import Path

# Allow direct execution (python tests/test_pawpal.py) to resolve project modules.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pawpal_system import DayType, Owner, Pet, Scheduler, Task


def test_task_completion_status_changes():
    """Task status should move between pending and completed."""
    task = Task(task_name="Feed the dog", duration_minutes=15, is_essential=True)

    assert task.get_status() == "pending"
    task.mark_completed()
    assert task.get_status() == "completed"
    task.mark_incomplete()
    assert task.get_status() == "pending"


def test_pet_add_task_increases_count_and_lookup_works():
    """Adding a task should increase count and make the task retrievable by name."""
    pet = Pet("Buddy")
    initial_count = len(pet.list_tasks())
    task = Task(task_name="Take a walk", duration_minutes=20)

    pet.add_task(task)

    assert len(pet.list_tasks()) == initial_count + 1
    assert pet.get_task_by_name("take a walk") is task


def test_owner_day_type_accepts_enum_and_string():
    """Owner time lookup should support both enum and string day types."""
    owner = Owner("Alice", weekday_available_minutes=60, weekend_available_minutes=120)

    assert owner.get_available_time(DayType.WEEKDAY) == 60
    assert owner.get_available_time("weekend") == 120


def test_generate_owner_schedule_uses_shared_budget_essential_first():
    """Owner schedule should share one budget across pets and prioritize essential tasks."""
    owner = Owner("Alice", weekday_available_minutes=50, weekend_available_minutes=100)

    pet1 = Pet("Fluffy")
    pet2 = Pet("Spot")

    # Essential tasks consume 45 minutes total.
    feed_fluffy = Task("Feed Fluffy", 15, is_essential=True)
    walk_spot = Task("Walk Spot", 30, is_essential=True)

    # Optional tasks: only one 5-minute slot should remain.
    groom_fluffy = Task("Groom Fluffy", 20)
    groom_fluffy.mark_non_essential(rank=1)
    brush_spot = Task("Brush Spot", 5)
    brush_spot.mark_non_essential(rank=2)

    pet1.add_task(feed_fluffy)
    pet1.add_task(groom_fluffy)
    pet2.add_task(walk_spot)
    pet2.add_task(brush_spot)

    owner.add_pet(pet1)
    owner.add_pet(pet2)

    scheduler = Scheduler()
    schedule = scheduler.generate_owner_schedule(owner, DayType.WEEKDAY)

    assert [t.task_name for t in schedule["Fluffy"]] == ["Feed Fluffy"]
    assert [t.task_name for t in schedule["Spot"]] == ["Walk Spot", "Brush Spot"]


def test_non_selected_optional_task_is_not_scheduled():
    """Non-essential tasks must be selected optional to be considered."""
    owner = Owner("Ana", weekday_available_minutes=30)
    pet = Pet("Mochi")
    med = Task("Medication", 10, is_essential=True)
    puzzle = Task("Puzzle Toy", 10, is_essential=False, optional_rank=1)
    # puzzle is non-essential but not selected optional yet.

    pet.add_task(med)
    pet.add_task(puzzle)
    owner.add_pet(pet)

    scheduler = Scheduler()
    tasks = scheduler.generate_schedule(owner, pet, "weekday")

    assert [t.task_name for t in tasks] == ["Medication"]


def test_duplicate_pet_names_are_rejected_case_insensitive():
    """Owner should reject pet names that collide ignoring case."""
    owner = Owner("Riley")
    owner.add_pet(Pet("Mochi"))

    with pytest.raises(ValueError):
        owner.add_pet(Pet("mochi"))