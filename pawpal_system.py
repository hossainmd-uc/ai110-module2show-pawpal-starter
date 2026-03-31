"""PawPal+ core scheduling system based on the UML design."""

from __future__ import annotations

import heapq
from enum import Enum
from typing import Dict, List, Optional


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
    """Stores owner profile data, pets, and available care time by day type."""

    def __init__(
        self,
        owner_name: str,
        weekday_available_minutes: int = 0,
        weekend_available_minutes: int = 0,
    ) -> None:
        self.owner_name = ""
        self.weekday_available_minutes = 0
        self.weekend_available_minutes = 0
        self.pets: List[Pet] = []

        self.set_owner_name(owner_name)
        self.set_weekday_time(weekday_available_minutes)
        self.set_weekend_time(weekend_available_minutes)

    def set_owner_name(self, name: str) -> None:
        """Update owner name."""
        if not name.strip():
            raise ValueError("owner_name cannot be empty")
        self.owner_name = name.strip()

    def set_weekday_time(self, minutes: int) -> None:
        """Set available weekday minutes."""
        if minutes < 0:
            raise ValueError("weekday_available_minutes cannot be negative")
        self.weekday_available_minutes = int(minutes)

    def set_weekend_time(self, minutes: int) -> None:
        """Set available weekend minutes."""
        if minutes < 0:
            raise ValueError("weekend_available_minutes cannot be negative")
        self.weekend_available_minutes = int(minutes)

    def get_available_time(self, day_type: DayType | str) -> int:
        """Return available minutes for weekday or weekend."""
        normalized = _normalize_day_type(day_type)
        if normalized is DayType.WEEKDAY:
            return self.weekday_available_minutes
        if normalized is DayType.WEEKEND:
            return self.weekend_available_minutes
        raise ValueError("Unsupported day_type")

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
    """Builds schedules using owner availability and pet task metadata."""

    def schedule_essential_tasks(
        self, tasks: List[Task], available_minutes: int
    ) -> List[Task]:
        """
        Schedule essential tasks first in input order.

        Overflow policy: if all essential tasks cannot fit, include the ones that fit
        in order and leave the rest unscheduled.
        """
        if available_minutes < 0:
            raise ValueError("available_minutes cannot be negative")

        scheduled: List[Task] = []
        used_minutes = 0
        for task in tasks:
            if not task.is_essential:
                continue
            duration = task.get_duration()
            if used_minutes + duration <= available_minutes:
                scheduled.append(task)
                used_minutes += duration
        return scheduled

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
        self, ranked_optional_tasks: List[Task], remaining_minutes: int
    ) -> List[Task]:
        """Schedule ranked optional tasks that fit in remaining minutes."""
        if remaining_minutes < 0:
            raise ValueError("remaining_minutes cannot be negative")

        scheduled: List[Task] = []
        used_minutes = 0
        for task in ranked_optional_tasks:
            duration = task.get_duration()
            if used_minutes + duration <= remaining_minutes:
                scheduled.append(task)
                used_minutes += duration
        return scheduled

    def generate_schedule(
        self, owner: Owner, pet: Pet, day_type: DayType | str
    ) -> List[Task]:
        """Generate a full schedule for one pet and day type."""
        if owner.pets and pet not in owner.pets:
            raise ValueError("Selected pet is not associated with the owner")

        available_minutes = owner.get_available_time(day_type)
        tasks = pet.list_tasks()

        essential_scheduled = self.schedule_essential_tasks(tasks, available_minutes)
        remaining_minutes = self.calculate_remaining_minutes(
            available_minutes, essential_scheduled
        )

        # Sort optional tasks once and reuse to avoid repeated sorting work.
        ranked_optional_tasks = self.get_selected_ranked_optional_tasks(tasks)
        optional_scheduled = self.schedule_ranked_optional_tasks(
            ranked_optional_tasks, remaining_minutes
        )

        return essential_scheduled + optional_scheduled

    def generate_owner_schedule(
        self, owner: Owner, day_type: DayType | str
    ) -> Dict[str, List[Task]]:
        """
        Generate schedules for all pets with one shared owner time budget.

        Policy:
        1) Schedule essential tasks across all pets first.
        2) Use remaining time for selected non-essential tasks ranked globally.
        
        Optimizations:
        - #9: Lazy task lookup (build task index once)
        - #2: Early exit when time exhausted
        - #4: Min heap for efficient minimum duration tracking
        """
        pets = owner.list_pets()
        schedule_by_pet: Dict[str, List[Task]] = {pet.pet_name: [] for pet in pets}

        available_minutes = owner.get_available_time(day_type)
        remaining_minutes = available_minutes

        # #9: Build task index in single traversal (Lazy Task Lookup)
        essential_entries: List[tuple[Pet, Task]] = []
        optional_entries: List[tuple[Pet, Task]] = []
        duration_heap = []  # #4: Min heap for O(1) minimum duration lookup
        
        for pet in pets:
            for task in pet.list_tasks():
                if task.is_essential:
                    essential_entries.append((pet, task))
                elif task.is_selected_optional:
                    optional_entries.append((pet, task))
                    # Push to heap for minimum duration tracking
                    heapq.heappush(duration_heap, (
                        task.get_duration(),
                        pet.pet_name.lower(),
                        task.task_name.lower(),
                        id(task)
                    ))

        # Schedule essential tasks
        for pet, task in essential_entries:
            duration = task.get_duration()
            if duration <= remaining_minutes:
                schedule_by_pet[pet.pet_name].append(task)
                remaining_minutes -= duration

        # #2: Early exit if no time for optional tasks
        if remaining_minutes <= 0:
            return schedule_by_pet

        # Sort optional tasks by rank (for scheduling order)
        optional_entries.sort(
            key=lambda entry: (
                entry[1].optional_rank if entry[1].optional_rank is not None else 10**9,
                entry[0].pet_name.lower(),
                entry[1].task_name.lower(),
            )
        )

        # Track scheduled task IDs for heap maintenance
        scheduled_ids = set()

        # Schedule optional tasks with heap-based early exit
        for pet, task in optional_entries:
            # #4: Clean heap top - remove already-scheduled tasks
            while duration_heap and duration_heap[0][3] in scheduled_ids:
                heapq.heappop(duration_heap)
            
            # #4: O(1) minimum duration check via heap peek
            if duration_heap:
                min_duration = duration_heap[0][0]
                if remaining_minutes < min_duration:
                    # Early exit! No remaining task can fit
                    break
            
            # #2: Early exit if time exhausted
            if remaining_minutes <= 0:
                break
            
            # Try to schedule this task (in rank order)
            duration = task.get_duration()
            if duration <= remaining_minutes:
                schedule_by_pet[pet.pet_name].append(task)
                remaining_minutes -= duration
                scheduled_ids.add(id(task))

        return schedule_by_pet

    def calculate_remaining_minutes(
        self, available_minutes: int, scheduled_tasks: List[Task]
    ) -> int:
        """Compute remaining minutes after scheduling tasks."""
        if available_minutes < 0:
            raise ValueError("available_minutes cannot be negative")
        used_minutes = sum(task.get_duration() for task in scheduled_tasks)
        return max(0, available_minutes - used_minutes)

    def get_unscheduled_tasks(
        self, all_tasks: List[Task], scheduled_tasks: List[Task]
    ) -> List[Task]:
        """Return tasks that were not included in the final schedule."""
        scheduled_ids = {id(task) for task in scheduled_tasks}
        return [task for task in all_tasks if id(task) not in scheduled_ids]
