# Changes Log

## Date
- 2026-03-30

## Summary
Implemented all previously identified relationship and logic fixes in `pawpal_system.py` and added this standalone log file.

## Detailed Changes

### 1) Implemented all class methods (replaced skeleton stubs)
- Added working behavior for:
  - `Task`
  - `Pet`
  - `Owner`
  - `Scheduler`

### 2) Added missing owner-to-pets relationship
- `Owner` now stores `pets`.
- Added methods:
  - `add_pet(pet)`
  - `remove_pet(pet)`
  - `list_pets()`

### 3) Added owner-level scheduling capability
- Added `Scheduler.generate_owner_schedule(owner, day_type)` to schedule all pets owned by one owner.

### 4) Added rank policy + deterministic tie handling
- `Scheduler.get_selected_ranked_optional_tasks(...)` now:
  - filters to selected non-essential tasks,
  - sorts by `optional_rank` ascending,
  - breaks ties alphabetically by task name.

### 5) Added day_type validation
- `Owner.get_available_time(day_type)` now validates input and only accepts:
  - `weekday`
  - `weekend`

### 6) Added explicit essential overflow policy
- `Scheduler.schedule_essential_tasks(...)` now documents and implements:
  - schedule essential tasks in order,
  - include only those that fit available minutes,
  - leave remaining essential tasks unscheduled.

### 7) Reduced repeated sorting work
- `Scheduler.generate_schedule(...)` sorts optional tasks once and reuses the result.

### 8) Improved data validation and consistency
- `Task` validation:
  - non-empty task name,
  - positive duration,
  - positive optional rank when provided.
- `Owner` validation:
  - non-empty owner name,
  - non-negative weekday/weekend minutes.
- `Pet` validation:
  - non-empty pet name,
  - duplicate task names blocked per pet.

### 9) Added unscheduled-task helper
- Added `Scheduler.get_unscheduled_tasks(all_tasks, scheduled_tasks)` to support transparency and UI explanations.

### 10) Switched owner-level scheduling to a shared time budget across all pets
- Updated `Scheduler.generate_owner_schedule(owner, day_type)` behavior:
  - uses one total daily budget from owner availability,
  - schedules essential tasks across all pets first,
  - schedules selected non-essential tasks next in global rank order,
  - subtracts each scheduled task from a single remaining-minutes pool.

### 11) Added unique pet-name guard per owner
- Updated `Owner.add_pet(pet)` to reject duplicate pet names (case-insensitive).
- Prevents key collisions in owner-level schedule output keyed by pet name.

### 12) Added DayType enum for safer day selection
- Added `DayType` enum with `WEEKDAY` and `WEEKEND` values.
- Updated owner/scheduler methods to accept `DayType | str` for backward compatibility.
- Added centralized day-type normalization and validation.

## Compatibility Note
- Existing UML methods remain available.
- Additional helper methods were added for relationship completeness and operational clarity.
