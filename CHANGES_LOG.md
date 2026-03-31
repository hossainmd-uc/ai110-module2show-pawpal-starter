# Changes Log

## Date - 2026-03-31
### Major Revamp 1: Scheduler Timing System Revamp

**Files**: `pawpal_system.py`, `app.py`, `tests/test_pawpal.py`, `SCHEDULER_REVAMP.md`

- Replaced scalar weekday/weekend minute budgeting with normalized availability windows.
- Added explicit timestamp placement (`start`/`end`) for scheduled tasks.
- Updated owner-level scheduling to consume one shared window pool across all pets.
- Added date-aware schedule generation entrypoints and retained legacy APIs for compatibility.
- Updated UI to configure windows and render timestamped schedules.
- Expanded tests to verify weekday/weekend timing behavior, contiguous-fit constraints, and deterministic scheduling.

**Outcome**:
- Scheduler now produces precise task time ranges and supports richer time modeling.

### Major Revamp 2: Daily/Weekly Recurrence + Date-Based Scheduling Revamp

**Files**: `pawpal_system.py`, `app.py`, `tests/test_pawpal.py`, `DAILY/WEEKLY_SCHEDULE_REVAMP.md`

- Added recurrence model (`none`, `daily`, `weekly`) with required weekly day metadata.
- Introduced occurrence-level `due_date` as the canonical scheduling key.
- Implemented completion-triggered next-occurrence generation:
  - daily: `+1 day`
  - weekly: `+7 days`
- Added deterministic catch-up generation so skipped dates still materialize missing occurrences up to selected date.
- Made task actions occurrence-specific by ID to prevent same-name ambiguity across dates.
- Expanded recurrence edge-case test suite (idempotency, catch-up, due-date filtering, weekend mapping).

**Outcome**:
- App now supports robust recurring task lifecycle management while preserving predictable, date-scoped schedule generation.

---

## Date - 2026-03-31
### Algorithmic Improvements Implementation

Implemented 6 algorithmic optimizations from ALGORITHMIC_IMPROVEMENTS.md proposal:

#### 1. Cache Scheduling Results (#1)
**Files**: `app.py`
- Added `compute_state_hash()` to generate MD5 hash of scheduling state
- Added `schedule_cache` to session state
- Modified schedule generation to check cache before computing
- Cache key format: `{state_hash}_{day_type}`
- Automatic cache size limiting (max 5 schedules)
- **Benefit**: Instant schedule retrieval when toggling weekday/weekend without data changes

#### 2. Early Exit on Time Exhaustion (#2)
**Files**: `pawpal_system.py`
- Added early exit when `remaining_minutes <= 0` after essential tasks
- Added early exit in optional task loop when time exhausted
- **Benefit**: Avoids unnecessary iteration when no tasks can fit

#### 3. Min Heap for Dynamic Minimum Duration Tracking (#4)
**Files**: `pawpal_system.py`
- Added `import heapq` for heap operations
- Build min heap of task durations during optional task gathering
- Lazy deletion strategy using `scheduled_ids` set
- O(1) minimum duration check via `heap[0]`
- **Benefit**: Efficient early exit when smallest remaining task won't fit

#### 4. Lazy Task Lookup Dictionary (#9)
**Files**: `pawpal_system.py`
- Refactored to build task index in single traversal
- Separate `essential_entries` and `optional_entries` built simultaneously
- Eliminated redundant pet/task iterations
- **Benefit**: O(n) instead of O(2n) for task gathering

#### 5. Schedule Diff Highlighting (#10)
**Files**: `app.py`
- Added `previous_schedule` to session state
- Calculate added/removed tasks when previous schedule exists
- Display "🆕 Added" or "✓ Same" indicators in schedule table
- Show expandable section for removed tasks
- **Benefit**: Users immediately see schedule changes

#### 6. Precompute Total Essential Time (#11)
**Files**: `app.py`
- Added `calculate_essential_time()` function
- Display weekday/weekend essential time totals before generate button
- Show ⚠️ warnings when essential tasks exceed available time
- Show ✓ remaining time for optional tasks
- **Benefit**: Proactive feedback prevents scheduling failures

### Implementation Notes
- **Held off**: #3 (Pre-filter Completed), #6 (Hybrid Priority System), #7 (Incremental Updates), #8 (Smart Defaults) per dependency analysis
- All code changes maintain backward compatibility
- Syntax validated successfully

---

## Date - 2026-03-30
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
