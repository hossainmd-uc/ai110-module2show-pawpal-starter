"""PawPal+ core scheduling system based on the UML design."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


class DayType(Enum):
    """Supported owner schedule day categories."""

    WEEKDAY = "weekday"
    WEEKEND = "weekend"


def _normalize_day_type(day_type: DayType | str) -> DayType:
    """Convert user input into a validated DayType enum value."""
    if isinstance(day_type, DayType):
        return day_type
    if isinstance(day_type, str):
        normalized = day_type.strip().lower()
        if normalized == DayType.WEEKDAY.value:
            return DayType.WEEKDAY
        if normalized == DayType.WEEKEND.value:
            return DayType.WEEKEND
    raise ValueError(
        "day_type must be DayType.WEEKDAY, DayType.WEEKEND, 'weekday', or 'weekend'"
    )


def _validate_window(start_minute: int, end_minute: int) -> tuple[int, int]:
    """Validate one availability window as minutes-from-midnight."""
    start = int(start_minute)
    end = int(end_minute)
    if start < 0 or end < 0:
        raise ValueError("window times cannot be negative")
    if start >= 24 * 60 or end > 24 * 60:
        raise ValueError("window times must be within a single day")
    if end <= start:
        raise ValueError("window end must be greater than start")
    return (start, end)


def _normalize_windows(windows: List[tuple[int, int]]) -> List[tuple[int, int]]:
    """Sort and merge overlapping or adjacent availability windows."""
    validated = [_validate_window(start, end) for start, end in windows]
    if not validated:
        return []

    validated.sort(key=lambda pair: (pair[0], pair[1]))
    merged: List[tuple[int, int]] = [validated[0]]

    for start, end in validated[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    return merged


def format_minute_of_day(minute: int) -> str:
    """Convert minutes-from-midnight into HH:MM 24-hour time."""
    if minute < 0 or minute > 24 * 60:
        raise ValueError("minute must be between 0 and 1440")
    hours = minute // 60
    mins = minute % 60
    return f"{hours:02d}:{mins:02d}"


@dataclass(frozen=True)
class ScheduledTask:
    """A scheduled task instance with explicit start and end times."""

    task: Task
    start_minute: int
    end_minute: int

    @property
    def start_time(self) -> str:
        return format_minute_of_day(self.start_minute)

    @property
    def end_time(self) -> str:
        return format_minute_of_day(self.end_minute)


@dataclass(frozen=True)
class UnscheduledTask:
    """A task that could not be scheduled and why."""

    task: Task
    reason: str


@dataclass(frozen=True)
class OwnerScheduleResult:
    """All scheduling output for a generated owner schedule."""

    scheduled_by_pet: Dict[str, List[ScheduledTask]]
    unscheduled_by_pet: Dict[str, List[UnscheduledTask]]


class Task:
    """Represents a single pet-care task and its scheduling metadata."""

    def __init__(
        self,
        task_name: str,
        duration_minutes: int,
        is_essential: bool = False,
        is_selected_optional: bool = False,
        optional_rank: Optional[int] = None,
    ) -> None:
        if not task_name.strip():
            raise ValueError("task_name cannot be empty")

        self.task_name = task_name.strip()
        self.duration_minutes = 0
        self.set_duration(duration_minutes)

        self.is_essential = bool(is_essential)
        self.is_selected_optional = bool(is_selected_optional)
        self.optional_rank = optional_rank
        self.is_completed = False

        if self.is_essential:
            self.mark_essential()
        else:
            if self.optional_rank is not None and self.optional_rank <= 0:
                raise ValueError("optional_rank must be a positive integer")

    def set_duration(self, minutes: int) -> None:
        """Set task duration in minutes."""
        if minutes <= 0:
            raise ValueError("duration_minutes must be greater than 0")
        self.duration_minutes = int(minutes)

    def mark_essential(self) -> None:
        """Mark this task as essential and clear optional metadata."""
        self.is_essential = True
        self.is_selected_optional = False
        self.optional_rank = None

    def mark_non_essential(self, rank: int) -> None:
        """Mark this task as non-essential and set its optional rank."""
        if rank <= 0:
            raise ValueError("rank must be a positive integer")
        self.is_essential = False
        self.is_selected_optional = True
        self.optional_rank = int(rank)

    def select_optional(self) -> None:
        """Include this non-essential task in optional scheduling."""
        if self.is_essential:
            raise ValueError("Essential tasks cannot be selected as optional")
        self.is_selected_optional = True

    def unselect_optional(self) -> None:
        """Exclude this non-essential task from optional scheduling."""
        self.is_selected_optional = False

    def get_duration(self) -> int:
        """Return task duration in minutes."""
        return self.duration_minutes

    def mark_completed(self) -> None:
        """Mark this task as completed by the user."""
        self.is_completed = True

    def mark_incomplete(self) -> None:
        """Reset this task to incomplete."""
        self.is_completed = False

    def get_status(self) -> str:
        """Return completion status label for display."""
        return "completed" if self.is_completed else "pending"


class Pet:
    """Stores pet identity and all associated care tasks."""

    def __init__(self, pet_name: str, tasks: Optional[List[Task]] = None) -> None:
        if not pet_name.strip():
            raise ValueError("pet_name cannot be empty")
        self.pet_name = pet_name.strip()
        self.tasks: List[Task] = tasks if tasks is not None else []
        self._tasks_by_name: Dict[str, Task] = {}

    def add_task(self, task: Task) -> None:
        """Attach a task to this pet."""
        key = task.task_name.lower()
        if key in self._tasks_by_name:
            raise ValueError(f"Task '{task.task_name}' already exists for this pet")
        self.tasks.append(task)
        self._tasks_by_name[key] = task

    def remove_task(self, task: Task) -> None:
        """Remove a task from this pet."""
        key = task.task_name.lower()
        existing = self._tasks_by_name.pop(key, None)
        if existing is None:
            raise ValueError(f"Task '{task.task_name}' not found for this pet")
        self.tasks.remove(existing)

    def list_tasks(self) -> List[Task]:
        """Return all tasks linked to this pet."""
        return list(self.tasks)

    def get_task_by_name(self, task_name: str) -> Task:
        """Find a task by name (case-insensitive)."""
        key = task_name.strip().lower()
        task = self._tasks_by_name.get(key)
        if task is None:
            raise ValueError(f"Task '{task_name}' not found for this pet")
        return task

    def complete_task(self, task_name: str) -> None:
        """Mark a named task as completed."""
        task = self.get_task_by_name(task_name)
        task.mark_completed()

    def reopen_task(self, task_name: str) -> None:
        """Mark a named task as incomplete."""
        task = self.get_task_by_name(task_name)
        task.mark_incomplete()


class Owner:
    """Stores owner profile data, pets, and available care windows by day type."""

    def __init__(
        self,
        owner_name: str,
        weekday_available_windows: Optional[List[Tuple[int, int]]] = None,
        weekend_available_windows: Optional[List[Tuple[int, int]]] = None,
    ) -> None:
        self.owner_name = ""
        self.weekday_available_windows: List[tuple[int, int]] = []
        self.weekend_available_windows: List[tuple[int, int]] = []
        self.pets: List[Pet] = []

        self.set_owner_name(owner_name)
        self.set_available_windows(
            DayType.WEEKDAY,
            weekday_available_windows if weekday_available_windows else [],
        )
        self.set_available_windows(
            DayType.WEEKEND,
            weekend_available_windows if weekend_available_windows else [],
        )

    def set_owner_name(self, name: str) -> None:
        """Update owner name."""
        if not name.strip():
            raise ValueError("owner_name cannot be empty")
        self.owner_name = name.strip()

    def set_available_windows(
        self, day_type: DayType | str, windows: List[Tuple[int, int]]
    ) -> None:
        """Replace all available windows for a day type."""
        normalized = _normalize_day_type(day_type)
        merged = _normalize_windows(list(windows))
        if normalized is DayType.WEEKDAY:
            self.weekday_available_windows = merged
            return
        if normalized is DayType.WEEKEND:
            self.weekend_available_windows = merged
            return
        raise ValueError("Unsupported day_type")

    def add_available_window(
        self, day_type: DayType | str, start_minute: int, end_minute: int
    ) -> None:
        """Add one available window and re-normalize."""
        normalized = _normalize_day_type(day_type)
        start, end = _validate_window(start_minute, end_minute)
        existing = self.get_available_windows(normalized)
        self.set_available_windows(normalized, existing + [(start, end)])

    def remove_available_window(
        self, day_type: DayType | str, start_minute: int, end_minute: int
    ) -> None:
        """Remove one exact available window."""
        normalized = _normalize_day_type(day_type)
        target = _validate_window(start_minute, end_minute)
        existing = self.get_available_windows(normalized)
        if target not in existing:
            raise ValueError("Window not found")
        updated = [window for window in existing if window != target]
        self.set_available_windows(normalized, updated)

    def get_available_windows(self, day_type: DayType | str) -> List[tuple[int, int]]:
        """Return normalized available windows for day type."""
        normalized = _normalize_day_type(day_type)
        if normalized is DayType.WEEKDAY:
            return list(self.weekday_available_windows)
        if normalized is DayType.WEEKEND:
            return list(self.weekend_available_windows)
        raise ValueError("Unsupported day_type")

    def get_schedulable_windows(self, day_type: DayType | str) -> List[tuple[int, int]]:
        """Return windows used by scheduler for a day type."""
        return self.get_available_windows(day_type)

    def get_available_time(self, day_type: DayType | str) -> int:
        """Return total available minutes across all normalized windows."""
        windows = self.get_available_windows(day_type)
        return sum(end - start for start, end in windows)

    def add_pet(self, pet: Pet) -> None:
        """Associate a pet with this owner."""
        if any(
            existing.pet_name.lower() == pet.pet_name.lower() for existing in self.pets
        ):
            raise ValueError(
                f"A pet named '{pet.pet_name}' is already associated with {self.owner_name}"
            )
        self.pets.append(pet)

    def remove_pet(self, pet: Pet) -> None:
        """Remove a pet association from this owner."""
        if pet not in self.pets:
            raise ValueError(
                f"Pet '{pet.pet_name}' is not associated with {self.owner_name}"
            )
        self.pets.remove(pet)

    def list_pets(self) -> List[Pet]:
        """Return pets associated with this owner."""
        return list(self.pets)


class Scheduler:
    """Builds schedules using owner availability windows and pet task metadata."""

    def _find_earliest_fit(
        self, free_windows: List[tuple[int, int]], duration: int
    ) -> Optional[int]:
        """Return index of earliest window that can fit duration contiguously."""
        for index, (start, end) in enumerate(free_windows):
            if end - start >= duration:
                return index
        return None

    def _reserve_window_slice(
        self, free_windows: List[tuple[int, int]], window_index: int, duration: int
    ) -> tuple[int, int]:
        """Reserve from start of selected free window and update free windows."""
        start, end = free_windows[window_index]
        reserved_start = start
        reserved_end = start + duration

        if reserved_end == end:
            free_windows.pop(window_index)
        else:
            free_windows[window_index] = (reserved_end, end)

        return (reserved_start, reserved_end)

    def schedule_essential_tasks(
        self, tasks: List[Task], free_windows: List[tuple[int, int]]
    ) -> tuple[List[ScheduledTask], List[UnscheduledTask]]:
        """
        Schedule essential tasks first in input order with explicit timestamps.

        Overflow policy: include essential tasks that fit contiguously and mark
        remaining ones unscheduled.
        """
        scheduled: List[ScheduledTask] = []
        unscheduled: List[UnscheduledTask] = []
        for task in tasks:
            if not task.is_essential:
                continue
            duration = task.get_duration()
            window_index = self._find_earliest_fit(free_windows, duration)
            if window_index is None:
                unscheduled.append(
                    UnscheduledTask(
                        task=task,
                        reason="No available time window can fit this essential task",
                    )
                )
                continue
            start_minute, end_minute = self._reserve_window_slice(
                free_windows, window_index, duration
            )
            scheduled.append(
                ScheduledTask(
                    task=task,
                    start_minute=start_minute,
                    end_minute=end_minute,
                )
            )
        return (scheduled, unscheduled)

    def get_selected_ranked_optional_tasks(self, tasks: List[Task]) -> List[Task]:
        """
        Return selected non-essential tasks ordered by rank.

        Tie-break policy: smaller rank first; ties resolved alphabetically by
        task_name for deterministic behavior.
        """

        def rank_key(task: Task) -> tuple[int, str]:
            rank = task.optional_rank if task.optional_rank is not None else 10**9
            return (rank, task.task_name.lower())

        filtered = [
            task
            for task in tasks
            if (not task.is_essential) and task.is_selected_optional
        ]
        return sorted(filtered, key=rank_key)

    def schedule_ranked_optional_tasks(
        self, ranked_optional_tasks: List[Task], free_windows: List[tuple[int, int]]
    ) -> tuple[List[ScheduledTask], List[UnscheduledTask]]:
        """Schedule ranked optional tasks that fit in remaining free windows."""
        scheduled: List[ScheduledTask] = []
        unscheduled: List[UnscheduledTask] = []
        for task in ranked_optional_tasks:
            duration = task.get_duration()
            window_index = self._find_earliest_fit(free_windows, duration)
            if window_index is None:
                unscheduled.append(
                    UnscheduledTask(
                        task=task,
                        reason="No remaining contiguous availability for optional task",
                    )
                )
                continue
            start_minute, end_minute = self._reserve_window_slice(
                free_windows, window_index, duration
            )
            scheduled.append(
                ScheduledTask(
                    task=task,
                    start_minute=start_minute,
                    end_minute=end_minute,
                )
            )
        return (scheduled, unscheduled)

    def generate_schedule(
        self, owner: Owner, pet: Pet, day_type: DayType | str
    ) -> tuple[List[ScheduledTask], List[UnscheduledTask]]:
        """Generate a full schedule for one pet and day type."""
        if owner.pets and pet not in owner.pets:
            raise ValueError("Selected pet is not associated with the owner")

        free_windows = owner.get_schedulable_windows(day_type)
        tasks = pet.list_tasks()

        essential_scheduled, essential_unscheduled = self.schedule_essential_tasks(
            tasks, free_windows
        )

        ranked_optional_tasks = self.get_selected_ranked_optional_tasks(tasks)
        optional_scheduled, optional_unscheduled = self.schedule_ranked_optional_tasks(
            ranked_optional_tasks, free_windows
        )

        return (
            essential_scheduled + optional_scheduled,
            essential_unscheduled + optional_unscheduled,
        )

    def generate_owner_schedule(
        self, owner: Owner, day_type: DayType | str
    ) -> OwnerScheduleResult:
        """
        Generate schedules for all pets with one shared owner window budget.

        Policy:
        1) Schedule essential tasks across all pets first.
        2) Use remaining windows for selected non-essential tasks ranked globally.

        Optimizations:
        - #9: Lazy task lookup (build task index once)
        - #2: Early exit when time exhausted
        - #4: Min heap for efficient minimum duration tracking
        """
        pets = owner.list_pets()
        schedule_by_pet: Dict[str, List[ScheduledTask]] = {
            pet.pet_name: [] for pet in pets
        }
        unscheduled_by_pet: Dict[str, List[UnscheduledTask]] = {
            pet.pet_name: [] for pet in pets
        }

        free_windows = owner.get_schedulable_windows(day_type)

        essential_entries: List[tuple[Pet, Task]] = []
        optional_entries: List[tuple[Pet, Task]] = []
        duration_heap = []

        for pet in pets:
            for task in pet.list_tasks():
                if task.is_essential:
                    essential_entries.append((pet, task))
                elif task.is_selected_optional:
                    optional_entries.append((pet, task))
                    heapq.heappush(
                        duration_heap,
                        (
                            task.get_duration(),
                            pet.pet_name.lower(),
                            task.task_name.lower(),
                            id(task),
                        ),
                    )

        # Schedule essential tasks in insertion order.
        for pet, task in essential_entries:
            duration = task.get_duration()
            window_index = self._find_earliest_fit(free_windows, duration)
            if window_index is None:
                unscheduled_by_pet[pet.pet_name].append(
                    UnscheduledTask(
                        task=task,
                        reason="No available time window can fit this essential task",
                    )
                )
                continue
            start_minute, end_minute = self._reserve_window_slice(
                free_windows, window_index, duration
            )
            schedule_by_pet[pet.pet_name].append(
                ScheduledTask(
                    task=task,
                    start_minute=start_minute,
                    end_minute=end_minute,
                )
            )

        if not free_windows:
            for pet, task in optional_entries:
                unscheduled_by_pet[pet.pet_name].append(
                    UnscheduledTask(
                        task=task,
                        reason="No remaining contiguous availability for optional task",
                    )
                )
            return OwnerScheduleResult(
                scheduled_by_pet=schedule_by_pet,
                unscheduled_by_pet=unscheduled_by_pet,
            )

        optional_entries.sort(
            key=lambda entry: (
                entry[1].optional_rank if entry[1].optional_rank is not None else 10**9,
                entry[0].pet_name.lower(),
                entry[1].task_name.lower(),
            )
        )

        scheduled_ids = set()

        for pet, task in optional_entries:
            while duration_heap and duration_heap[0][3] in scheduled_ids:
                heapq.heappop(duration_heap)

            if duration_heap:
                min_duration = duration_heap[0][0]
                if all((end - start) < min_duration for start, end in free_windows):
                    break

            if not free_windows:
                break

            duration = task.get_duration()
            window_index = self._find_earliest_fit(free_windows, duration)
            if window_index is None:
                unscheduled_by_pet[pet.pet_name].append(
                    UnscheduledTask(
                        task=task,
                        reason="No remaining contiguous availability for optional task",
                    )
                )
                continue
            start_minute, end_minute = self._reserve_window_slice(
                free_windows, window_index, duration
            )
            schedule_by_pet[pet.pet_name].append(
                ScheduledTask(
                    task=task,
                    start_minute=start_minute,
                    end_minute=end_minute,
                )
            )
            scheduled_ids.add(id(task))

        remaining_optional_ids = {
            id(task) for _, task in optional_entries if id(task) not in scheduled_ids
        }
        for pet, task in optional_entries:
            if id(task) in remaining_optional_ids and not any(
                uns.task is task for uns in unscheduled_by_pet[pet.pet_name]
            ):
                unscheduled_by_pet[pet.pet_name].append(
                    UnscheduledTask(
                        task=task,
                        reason="No remaining contiguous availability for optional task",
                    )
                )

        return OwnerScheduleResult(
            scheduled_by_pet=schedule_by_pet,
            unscheduled_by_pet=unscheduled_by_pet,
        )

    def get_unscheduled_tasks(
        self, all_tasks: List[Task], scheduled_tasks: List[ScheduledTask]
    ) -> List[Task]:
        """Return tasks that were not included in the final schedule."""
        scheduled_ids = {id(item.task) for item in scheduled_tasks}
        return [task for task in all_tasks if id(task) not in scheduled_ids]
