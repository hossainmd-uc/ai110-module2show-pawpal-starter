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


def test_owner_windows_merge_and_time_lookup_supports_enum_and_string():
    """Owner windows should normalize and total minutes should be retrievable by enum/string."""
    owner = Owner(
        "Alice",
        weekday_available_windows=[(480, 510), (500, 540), (600, 630)],
        weekend_available_windows=[(600, 660)],
    )

    assert owner.get_available_windows(DayType.WEEKDAY) == [(480, 540), (600, 630)]
    assert owner.get_available_time(DayType.WEEKDAY) == 90
    assert owner.get_available_time("weekend") == 60


def test_generate_owner_schedule_uses_shared_windows_essential_first_with_timestamps():
    """Owner schedule should share windows across pets, prioritize essential, and expose timestamps."""
    owner = Owner("Alice", weekday_available_windows=[(540, 600)])

    pet1 = Pet("Fluffy")
    pet2 = Pet("Spot")

    feed_fluffy = Task("Feed Fluffy", 15, is_essential=True)
    walk_spot = Task("Walk Spot", 30, is_essential=True)

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
    result = scheduler.generate_owner_schedule(owner, DayType.WEEKDAY)
    schedule = result.scheduled_by_pet

    assert [t.task.task_name for t in schedule["Fluffy"]] == ["Feed Fluffy"]
    assert [t.task.task_name for t in schedule["Spot"]] == ["Walk Spot", "Brush Spot"]

    assert schedule["Fluffy"][0].start_time == "09:00"
    assert schedule["Fluffy"][0].end_time == "09:15"
    assert schedule["Spot"][0].start_time == "09:15"
    assert schedule["Spot"][0].end_time == "09:45"
    assert schedule["Spot"][1].start_time == "09:45"
    assert schedule["Spot"][1].end_time == "09:50"

    assert [u.task.task_name for u in result.unscheduled_by_pet["Fluffy"]] == [
        "Groom Fluffy"
    ]


def test_non_selected_optional_task_is_not_scheduled():
    """Non-essential tasks must be selected optional to be considered."""
    owner = Owner("Ana", weekday_available_windows=[(480, 510)])
    pet = Pet("Mochi")
    med = Task("Medication", 10, is_essential=True)
    puzzle = Task("Puzzle Toy", 10, is_essential=False, optional_rank=1)

    pet.add_task(med)
    pet.add_task(puzzle)
    owner.add_pet(pet)

    scheduler = Scheduler()
    scheduled, unscheduled = scheduler.generate_schedule(owner, pet, "weekday")

    assert [item.task.task_name for item in scheduled] == ["Medication"]
    assert [item.task.task_name for item in unscheduled] == []


def test_task_must_fit_contiguous_window_not_total_sum():
    """A task should remain unscheduled if only fragmented time exists."""
    owner = Owner("Mina", weekday_available_windows=[(480, 490), (500, 510)])
    pet = Pet("Nori")
    long_walk = Task("Long Walk", 15, is_essential=True)
    pet.add_task(long_walk)
    owner.add_pet(pet)

    scheduler = Scheduler()
    result = scheduler.generate_owner_schedule(owner, DayType.WEEKDAY)

    assert result.scheduled_by_pet["Nori"] == []
    assert result.unscheduled_by_pet["Nori"][0].task.task_name == "Long Walk"


def test_duplicate_pet_names_are_rejected_case_insensitive():
    """Owner should reject pet names that collide ignoring case."""
    owner = Owner("Riley")
    owner.add_pet(Pet("Mochi"))

    with pytest.raises(ValueError):
        owner.add_pet(Pet("mochi"))
