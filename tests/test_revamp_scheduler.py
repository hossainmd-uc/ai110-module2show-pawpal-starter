import pytest
from datetime import date

from pawpal_system import (
    DayType,
    DayOfWeek,
    Owner,
    Pet,
    RecurrenceType,
    Scheduler,
    Task,
    format_minute_of_day,
)


def test_format_minute_of_day_rejects_out_of_range_values():
    """Formatting should fail when minute values are outside the valid day boundary."""
    with pytest.raises(ValueError):
        format_minute_of_day(-1)
    with pytest.raises(ValueError):
        format_minute_of_day(1441)


def test_owner_get_windows_for_date_maps_weekday_and_weekend_correctly():
    """Owner date mapping should pick weekday windows for weekdays and weekend windows for weekends."""
    owner = Owner(
        "MapTest",
        weekday_available_windows=[(540, 600)],
        weekend_available_windows=[(600, 660)],
    )

    assert owner.get_day_type_for_date("2026-04-02") == DayType.WEEKDAY
    assert owner.get_day_type_for_date("2026-04-04") == DayType.WEEKEND
    assert owner.get_windows_for_date("2026-04-02") == [(540, 600)]
    assert owner.get_windows_for_date("2026-04-04") == [(600, 660)]


def test_task_next_occurrence_generation_matches_recurrence_type_rules():
    """Next occurrence generation should follow none-daily-weekly recurrence semantics."""
    none_task = Task(
        "One Off", 10, recurrence_type=RecurrenceType.NONE, due_date="2026-03-31"
    )
    daily_task = Task(
        "Daily", 10, recurrence_type=RecurrenceType.DAILY, due_date="2026-03-31"
    )
    weekly_task = Task(
        "Weekly",
        10,
        recurrence_type=RecurrenceType.WEEKLY,
        recurrence_day=DayOfWeek.TUESDAY,
        due_date="2026-03-31",
    )

    assert none_task.create_next_occurrence("2026-03-31") is None
    assert (
        daily_task.create_next_occurrence("2026-03-31").due_date.isoformat()
        == "2026-04-01"
    )
    assert (
        weekly_task.create_next_occurrence("2026-03-31").due_date.isoformat()
        == "2026-04-07"
    )


def test_list_due_occurrences_filters_out_completed_and_template_tasks():
    """Due occurrence listing should only include non-template incomplete occurrences for the selected date."""
    pet = Pet("FilterPet")
    active = Task("Active", 10, due_date="2026-04-02")
    completed = Task("Completed", 10, due_date="2026-04-02")
    template = Task("Template", 10, due_date="2026-04-02", is_template=True)

    completed.mark_completed("2026-04-02")
    pet.add_task(active)
    pet.add_task(completed)
    pet.add_task(template)

    due = pet.list_due_occurrences("2026-04-02")
    assert [task.task_name for task in due] == ["Active"]


def test_get_selected_ranked_optional_tasks_sorts_by_rank_then_name():
    """Optional task sorting should prioritize smaller rank values and then alphabetical names for ties."""
    scheduler = Scheduler()
    a = Task("Alpha", 5)
    b = Task("Beta", 5)
    c = Task("Gamma", 5)

    a.mark_non_essential(rank=2)
    b.mark_non_essential(rank=1)
    c.mark_non_essential(rank=2)

    ranked = scheduler.get_selected_ranked_optional_tasks([c, a, b])
    assert [task.task_name for task in ranked] == ["Beta", "Alpha", "Gamma"]


def test_generate_owner_schedule_for_date_returns_chronological_rows_per_pet():
    """Scheduled rows for each pet should be ordered by increasing start time."""
    owner = Owner("Chrono", weekday_available_windows=[(540, 610)])
    pet = Pet("ChronoPet")

    t1 = Task("First", 10, is_essential=True, due_date="2026-04-02")
    t2 = Task("Second", 15, is_essential=True, due_date="2026-04-02")
    t3 = Task("Third", 10, due_date="2026-04-02")
    t3.mark_non_essential(rank=1)

    pet.add_task(t1)
    pet.add_task(t2)
    pet.add_task(t3)
    owner.add_pet(pet)

    result = Scheduler().generate_owner_schedule_for_date(owner, "2026-04-02")
    starts = [row.start_minute for row in result.scheduled_by_pet["ChronoPet"]]

    assert starts == sorted(starts)
    assert [row.task.task_name for row in result.scheduled_by_pet["ChronoPet"]] == [
        "First",
        "Second",
        "Third",
    ]


def test_generate_owner_schedule_for_date_does_not_include_other_dates():
    """Date-scoped generation should only schedule occurrences whose due date equals the selected date."""
    owner = Owner("DateScope", weekday_available_windows=[(540, 600)])
    pet = Pet("DatePet")

    today = Task("Today", 10, is_essential=True, due_date="2026-04-02")
    tomorrow = Task("Tomorrow", 10, is_essential=True, due_date="2026-04-03")
    pet.add_task(today)
    pet.add_task(tomorrow)
    owner.add_pet(pet)

    result = Scheduler().generate_owner_schedule_for_date(owner, date(2026, 4, 2))
    assert [row.task.task_name for row in result.scheduled_by_pet["DatePet"]] == [
        "Today"
    ]


def test_catch_up_materializes_missing_daily_occurrences_until_target_date():
    """Catch-up should fill all missing daily occurrences through the requested target date."""
    pet = Pet("CatchDaily")
    seed = Task("Daily Seed", 10, recurrence_type="daily", due_date="2026-03-31")
    pet.add_task(seed)
    pet.complete_occurrence_and_regenerate(seed.occurrence_id, "2026-03-31")

    pet.ensure_occurrences_up_to("2026-04-03")
    due_dates = sorted(
        task.due_date.isoformat()
        for task in pet.list_tasks()
        if task.source_template_id == seed.source_template_id
    )

    assert due_dates == ["2026-03-31", "2026-04-01", "2026-04-02", "2026-04-03"]


def test_catch_up_materializes_missing_weekly_occurrences_until_target_date():
    """Catch-up should fill missing weekly occurrences in seven-day increments through target date."""
    pet = Pet("CatchWeekly")
    seed = Task(
        "Weekly Seed",
        10,
        recurrence_type="weekly",
        recurrence_day="tuesday",
        due_date="2026-03-31",
    )
    pet.add_task(seed)
    pet.complete_occurrence_and_regenerate(seed.occurrence_id, "2026-03-31")

    pet.ensure_occurrences_up_to("2026-04-21")
    due_dates = sorted(
        task.due_date.isoformat()
        for task in pet.list_tasks()
        if task.source_template_id == seed.source_template_id
    )

    assert due_dates == ["2026-03-31", "2026-04-07", "2026-04-14", "2026-04-21"]


def test_catch_up_and_generation_are_idempotent_for_same_target_date():
    """Repeated generation for the same target date should not duplicate recurring occurrences."""
    owner = Owner("IdemOwner", weekday_available_windows=[(540, 580)])
    pet = Pet("IdemPet")
    task = Task("Daily Pill", 5, recurrence_type="daily", due_date="2026-03-31")
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
