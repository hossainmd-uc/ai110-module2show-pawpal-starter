"""PawPal+ system skeleton based on the UML design."""

from __future__ import annotations

from typing import List, Optional


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
		self.task_name = task_name
		self.duration_minutes = duration_minutes
		self.is_essential = is_essential
		self.is_selected_optional = is_selected_optional
		self.optional_rank = optional_rank

	def set_duration(self, minutes: int) -> None:
		"""Set task duration in minutes."""
		raise NotImplementedError

	def mark_essential(self) -> None:
		"""Mark this task as essential and clear optional metadata."""
		raise NotImplementedError

	def mark_non_essential(self, rank: int) -> None:
		"""Mark this task as non-essential and set its optional rank."""
		raise NotImplementedError

	def select_optional(self) -> None:
		"""Include this non-essential task in optional scheduling."""
		raise NotImplementedError

	def unselect_optional(self) -> None:
		"""Exclude this non-essential task from optional scheduling."""
		raise NotImplementedError

	def get_duration(self) -> int:
		"""Return task duration in minutes."""
		raise NotImplementedError


class Pet:
	"""Stores pet identity and all associated care tasks."""

	def __init__(self, pet_name: str) -> None:
		self.pet_name = pet_name
		self.tasks: List[Task] = []

	def add_task(self, task: Task) -> None:
		"""Attach a task to this pet."""
		raise NotImplementedError

	def remove_task(self, task: Task) -> None:
		"""Remove a task from this pet."""
		raise NotImplementedError

	def list_tasks(self) -> List[Task]:
		"""Return all tasks linked to this pet."""
		raise NotImplementedError


class Owner:
	"""Stores owner profile data and available care time by day type."""

	def __init__(
		self,
		owner_name: str,
		weekday_available_minutes: int = 0,
		weekend_available_minutes: int = 0,
	) -> None:
		self.owner_name = owner_name
		self.weekday_available_minutes = weekday_available_minutes
		self.weekend_available_minutes = weekend_available_minutes

	def set_owner_name(self, name: str) -> None:
		"""Update owner name."""
		raise NotImplementedError

	def set_weekday_time(self, minutes: int) -> None:
		"""Set available weekday minutes."""
		raise NotImplementedError

	def set_weekend_time(self, minutes: int) -> None:
		"""Set available weekend minutes."""
		raise NotImplementedError

	def get_available_time(self, day_type: str) -> int:
		"""Return available minutes for 'weekday' or 'weekend'."""
		raise NotImplementedError


class Scheduler:
	"""Builds a schedule using owner availability and pet task metadata."""

	def schedule_essential_tasks(
		self, tasks: List[Task], available_minutes: int
	) -> List[Task]:
		"""Schedule essential tasks first within available minutes."""
		raise NotImplementedError

	def get_selected_ranked_optional_tasks(self, tasks: List[Task]) -> List[Task]:
		"""Return optional tasks that are selected, ordered by rank."""
		raise NotImplementedError

	def schedule_ranked_optional_tasks(
		self, ranked_optional_tasks: List[Task], remaining_minutes: int
	) -> List[Task]:
		"""Schedule ranked optional tasks that fit in remaining minutes."""
		raise NotImplementedError

	def generate_schedule(self, owner: Owner, pet: Pet, day_type: str) -> List[Task]:
		"""Generate a full schedule for the given day type."""
		raise NotImplementedError

	def calculate_remaining_minutes(
		self, available_minutes: int, scheduled_tasks: List[Task]
	) -> int:
		"""Compute remaining minutes after scheduling tasks."""
		raise NotImplementedError
