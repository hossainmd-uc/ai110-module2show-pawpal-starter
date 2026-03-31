import pytest
import sys
from datetime import date
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


def test_daily_completion_creates_next_occurrence():
    """Completing a daily occurrence should auto-create exactly one next day occurrence."""
    pet = Pet("Mochi")
    task = Task(
        "Feed Mochi",
        10,
        is_essential=True,
        recurrence_type="daily",
        due_date="2026-03-31",
    )
    pet.add_task(task)

    next_item = pet.complete_occurrence_and_regenerate(task.occurrence_id, "2026-03-31")

    assert next_item is not None
    assert next_item.due_date.isoformat() == "2026-04-01"
    assert next_item.source_template_id == task.source_template_id


def test_weekly_completion_creates_same_weekday_next_week():
    """Completing a weekly occurrence should create a +7-day successor."""
    pet = Pet("Nori")
    task = Task(
        "Brush Coat",
        15,
        recurrence_type="weekly",
        recurrence_day="tuesday",
        due_date="2026-03-31",
    )
    pet.add_task(task)

    next_item = pet.complete_occurrence_and_regenerate(task.occurrence_id, "2026-03-31")

    assert next_item is not None
    assert next_item.due_date.isoformat() == "2026-04-07"


def test_schedule_for_date_uses_catchup_when_days_skipped():
    """Date scheduling should materialize missing recurring occurrences up to selected date."""
    owner = Owner("Alex", weekday_available_windows=[(540, 600)])
    pet = Pet("Pico")
    task = Task(
        "Medication",
        10,
        is_essential=True,
        recurrence_type="daily",
        due_date="2026-03-31",
    )
    pet.add_task(task)
    pet.complete_occurrence_and_regenerate(task.occurrence_id, "2026-03-31")
    owner.add_pet(pet)

    scheduler = Scheduler()
    result = scheduler.generate_owner_schedule_for_date(owner, "2026-04-02")

    assert [t.task.task_name for t in result.scheduled_by_pet["Pico"]] == ["Medication"]
    assert result.scheduled_by_pet["Pico"][0].task.due_date.isoformat() == "2026-04-02"


def test_weekly_task_requires_recurrence_day():
    """Weekly recurrence should require an explicit recurrence day."""
    with pytest.raises(ValueError):
        Task("Weekly Groom", 20, recurrence_type="weekly", due_date="2026-03-31")


def test_daily_task_rejects_recurrence_day():
    """Only weekly recurrence can carry recurrence_day metadata."""
    with pytest.raises(ValueError):
        Task(
            "Daily Feed",
            10,
            recurrence_type="daily",
            recurrence_day="monday",
            due_date="2026-03-31",
        )


def test_complete_occurrence_and_regenerate_is_idempotent():
    """Repeated completion calls should not create duplicate successors."""
    pet = Pet("Mochi")
    occurrence = Task(
        "Feed Mochi",
        10,
        recurrence_type="daily",
        due_date="2026-03-31",
    )
    pet.add_task(occurrence)

    created = pet.complete_occurrence_and_regenerate(
        occurrence.occurrence_id, "2026-03-31"
    )
    repeated = pet.complete_occurrence_and_regenerate(
        occurrence.occurrence_id, "2026-03-31"
    )

    assert created is not None
    assert repeated is None
    matching_next = [
        task
        for task in pet.list_tasks()
        if task.source_template_id == occurrence.source_template_id
        and task.due_date == date.fromisoformat("2026-04-01")
    ]
    assert len(matching_next) == 1


def test_daily_catchup_materializes_missing_each_day_until_target():
    """Daily catch-up should create every missing date up to target date."""
    pet = Pet("Nova")
    first = Task(
        "Meds",
        10,
        recurrence_type="daily",
        due_date="2026-03-31",
    )
    pet.add_task(first)
    pet.complete_occurrence_and_regenerate(first.occurrence_id, "2026-03-31")

    pet.ensure_occurrences_up_to("2026-04-03")

    due_dates = sorted(
        task.due_date.isoformat()
        for task in pet.list_tasks()
        if task.source_template_id == first.source_template_id
    )
    assert due_dates == [
        "2026-03-31",
        "2026-04-01",
        "2026-04-02",
        "2026-04-03",
    ]


def test_weekly_catchup_materializes_in_7_day_steps():
    """Weekly catch-up should only materialize +7 day recurrence boundaries."""
    pet = Pet("Rex")
    first = Task(
        "Weekly Bath",
        20,
        recurrence_type="weekly",
        recurrence_day="tuesday",
        due_date="2026-03-31",
    )
    pet.add_task(first)
    pet.complete_occurrence_and_regenerate(first.occurrence_id, "2026-03-31")

    pet.ensure_occurrences_up_to("2026-04-21")

    due_dates = sorted(
        task.due_date.isoformat()
        for task in pet.list_tasks()
        if task.source_template_id == first.source_template_id
    )
    assert due_dates == [
        "2026-03-31",
        "2026-04-07",
        "2026-04-14",
        "2026-04-21",
    ]


def test_generate_schedule_for_date_only_includes_due_date_occurrences():
    """Date-scoped scheduling must ignore occurrences due on other dates."""
    owner = Owner("Kai", weekday_available_windows=[(540, 600)])
    pet = Pet("Luna")
    due_today = Task(
        "Today Task",
        10,
        is_essential=True,
        recurrence_type="none",
        due_date="2026-04-02",
    )
    due_other_day = Task(
        "Other Day Task",
        10,
        is_essential=True,
        recurrence_type="none",
        due_date="2026-04-03",
    )
    pet.add_task(due_today)
    pet.add_task(due_other_day)
    owner.add_pet(pet)

    scheduler = Scheduler()
    result = scheduler.generate_owner_schedule_for_date(owner, "2026-04-02")

    assert [t.task.task_name for t in result.scheduled_by_pet["Luna"]] == ["Today Task"]


def test_generate_schedule_for_date_uses_weekend_windows_when_date_is_weekend():
    """Weekend target dates should use weekend windows, not weekday windows."""
    # 2026-04-04 is Saturday.
    owner = Owner(
        "Ira",
        weekday_available_windows=[(540, 600)],
        weekend_available_windows=[(600, 660)],
    )
    pet = Pet("Era")
    task = Task(
        "Walk Era",
        15,
        is_essential=True,
        due_date="2026-04-04",
    )
    pet.add_task(task)
    owner.add_pet(pet)

    scheduler = Scheduler()
    result = scheduler.generate_owner_schedule_for_date(owner, "2026-04-04")

    assert result.scheduled_by_pet["Era"][0].start_time == "10:00"
    assert result.scheduled_by_pet["Era"][0].end_time == "10:15"


def test_repeated_generation_with_catchup_does_not_duplicate_occurrences():
    """Repeated schedule generation should keep catch-up idempotent."""
    owner = Owner("Zed", weekday_available_windows=[(540, 600)])
    pet = Pet("Poe")
    task = Task(
        "Pill",
        5,
        is_essential=True,
        recurrence_type="daily",
        due_date="2026-03-31",
    )
    pet.add_task(task)
    pet.complete_occurrence_and_regenerate(task.occurrence_id, "2026-03-31")
    owner.add_pet(pet)
    scheduler = Scheduler()

    scheduler.generate_owner_schedule_for_date(owner, "2026-04-03")
    scheduler.generate_owner_schedule_for_date(owner, "2026-04-03")

    due_dates = [
        t.due_date.isoformat()
        for t in pet.list_tasks()
        if t.source_template_id == task.source_template_id
    ]
    assert len(due_dates) == len(set(due_dates))
