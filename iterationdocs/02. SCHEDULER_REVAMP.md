# Scheduler Revamp Plan (No-Code Design Spec)

## Purpose
This document defines the natural-language design changes needed to revamp PawPal scheduling from a single-minute budget model to a range-based availability model with explicit start/end timestamps for each scheduled activity.

The selected direction combines:
1. Repeatable time-range rows per day type (Idea 1)
2. A unified time-window model focused only on availability
3. Incremental wizard flow for data entry (Idea 6)

Scheduling engine target:
1. Full interval scheduling with explicit activity start and end timestamps (Approach 3)

---

## Product Behavior Goals
1. Users can add as many availability windows as needed.
2. Users can complete this setup through a guided wizard flow.
3. Scheduler output includes exact start and end times for each scheduled task.
4. Essential tasks are still prioritized first.
5. Optional tasks are still chosen by rank after essentials are placed.
6. Scheduling places tasks only inside configured availability windows.

---

## New Scheduling Model (Conceptual)
1. Day type remains category-based for now: weekday and weekend.
2. Each day type stores one interval collection: available windows.
3. Available windows are sorted chronologically and merged when adjacent or overlapping.
4. The merged set is the schedulable window set for that day type.
5. Tasks are placed into schedulable windows with explicit timestamps.
6. A task cannot be split across multiple windows in phase 1 (unless explicitly adopted later).
7. If a task cannot fit fully in any remaining window, it is unscheduled.

---

## Required Validation Rules
1. Window start must be earlier than window end.
2. Times must be within one day boundary (for example, 00:00 to 23:59 policy as defined by team).
3. Overlapping available windows should be merged.
4. Schedulable windows can be empty; scheduler should return no scheduled tasks and explain why.
5. Optional rank values must remain positive integers.

---

## Wizard UX Flow (Idea 6 + Idea 1, Available-Windows Only)
1. Step 1: Choose day type template to edit (weekday or weekend).
2. Step 2: Add one or more available windows using repeatable rows.
3. Step 3: Review merged schedulable windows and validate conflicts.
4. Step 4: Save template and repeat for other day type if needed.
5. Step 5: Generate schedule and show explicit timestamped task timeline.

UX requirements:
1. Every interval row has add and delete controls.
2. Users can add unlimited rows.
3. Validation feedback appears inline before save.
4. Review step clearly shows merged windows that will be used for scheduling.
5. Generated schedule explains skipped tasks (no fitting window, insufficient contiguous duration, lower priority).

---

## Scheduling Engine Behavior (Approach 3)
1. Build merged schedulable windows for selected day type.
2. Sort candidate tasks by policy:
- Essential tasks first (current behavior preserved)
- Optional tasks by rank and stable tie-break rules (current behavior preserved)
3. For each task, find earliest window with enough contiguous free time.
4. Place task with exact start and end timestamps.
5. Mark that occupied interval as unavailable for subsequent tasks.
6. Continue until all tasks are attempted.
7. Return structured output containing:
- Scheduled items with pet name, task name, start time, end time, duration, essential flag, optional rank
- Unscheduled items with reason

Tie-breaking and deterministic output:
1. Keep pet/task alphabetical tie-breakers where rank or policy ties occur.
2. Prefer earliest possible placement time for reproducible results.

---

## Object-by-Object Impact Assessment

### DayType
Impacted functions:
1. None required if weekday/weekend categories remain unchanged.

New methods needed:
1. None required.

Old methods to delete:
1. None.

Notes:
1. If future expansion to day-of-week is desired, this enum will be revisited.

### Task
Impacted functions:
1. `get_duration` remains core to placement checks.
2. Status-related methods remain useful for completion tracking.

New methods needed:
1. None strictly required if scheduling timestamps are stored in schedule output objects rather than on Task.
2. Optional future method to expose display label for timeline rows.

Old methods to delete:
1. None.

Notes:
1. Keep Task as task-definition data, not schedule-instance data, to avoid mutating canonical task objects.

### Pet
Impacted functions:
1. `list_tasks` continues as primary task source.
2. Task lookup and completion methods remain compatible.

New methods needed:
1. None required for core interval scheduling.

Old methods to delete:
1. None.

### Owner
Impacted functions to rewrite:
1. `__init__` currently accepts `weekday_available_minutes` and `weekend_available_minutes`; must shift to interval-based availability model.
2. `set_weekday_time` and `set_weekend_time` become obsolete under interval model.
3. `get_available_time` currently returns a single integer; must evolve to return interval collections or merged schedulable windows for the selected day type.

New methods needed:
1. Method to add available window for a day type.
2. Method to remove available window for a day type.
3. Method to list available windows for a day type.
4. Method to compute merged schedulable windows for a day type.
5. Method to validate and normalize windows (sort/merge/clean).

Old methods to delete:
1. `set_weekday_time`
2. `set_weekend_time`

Methods to deprecate or replace:
1. `get_available_time` should be replaced by interval-oriented retrieval and merged-window calculation methods.

### Scheduler
Impacted functions to rewrite:
1. `schedule_essential_tasks` currently takes `available_minutes`; must place tasks into time windows with timestamps.
2. `schedule_ranked_optional_tasks` currently takes `remaining_minutes`; must place tasks into remaining free intervals.
3. `generate_schedule` must return timestamped placements, not only ordered Task list.
4. `generate_owner_schedule` must maintain shared owner-time policy while placing tasks into explicit intervals across pets.
5. `calculate_remaining_minutes` becomes conceptually obsolete because free capacity is interval-based, not scalar.
6. `get_unscheduled_tasks` must include reason metadata (no fitting window, insufficient contiguous duration, lower priority not reached).

New methods needed:
1. Method to build merged schedulable windows from owner interval data.
2. Method to find earliest fitting interval for a given duration.
3. Method to reserve an interval segment after task placement.
4. Method to convert placement results into user-facing schedule records.
5. Method to compute unscheduled reasons in a deterministic way.

Old methods to delete:
1. `calculate_remaining_minutes` (replace with free-interval tracking).

Methods to deprecate or heavily alter:
1. Any method that assumes scalar minute budgets only.

---

## UI and State Impacts (app.py)

### Session State Changes
Current state fields likely to retire:
1. `weekday_minutes`
2. `weekend_minutes`

New state fields needed:
1. `weekday_available_windows`
2. `weekend_available_windows`
3. Wizard progress state (current step, validation state, draft rows)
4. Schedule output model with timestamped entries and unscheduled reasons

### Function-Level UI/State Impacts
Functions that must be updated:
1. `compute_state_hash`
- Must hash interval collections and wizard-relevant scheduling inputs instead of two minute totals.

2. `init_state`
- Must initialize interval collections and wizard state.
- Must stop initializing scalar minute totals.

3. `calculate_essential_time`
- Can remain for aggregate insights, but must not be treated as direct scheduling capacity check.
- Should be reframed as informational summary only.

4. `build_owner_from_state`
- Must construct Owner with available-window interval data per day type.

5. Owner setup UI block
- Replace numeric minute inputs with wizard flow:
  - add/remove available windows
  - review merged schedulable windows

6. Schedule generation UI block
- Must trigger interval-based scheduler.
- Must display explicit start/end timestamps per scheduled row.
- Must show unscheduled tasks with reasons.

7. Summary metrics and footer
- Replace scalar used-vs-remaining minute summary with timeline and window utilization summary.

### Display Changes
1. Per-pet schedule table should include start and end columns.
2. Optionally add a chronological combined timeline across all pets.
3. Keep change-diff feature, but compare timestamped entries rather than just task-name presence.

---

## Test Impacts
Files impacted:
1. `tests/test_pawpal.py`

Test categories to revise:
1. Owner availability tests must shift from integer minute assertions to interval assertions.
2. Scheduler tests must assert explicit start and end timestamps.
3. Essential-first behavior must still hold under interval constraints.
4. Optional ranking must still hold after essential placement.
5. New edge cases required:
- no contiguous interval large enough
- exact-fit interval placement
- deterministic tie-break ordering

Likely obsolete test assumptions:
1. Any assertion based only on total `available_minutes` or `remaining_minutes`.

---

## Migration and Compatibility Notes
1. This revamp is a behavioral schema change, not a cosmetic refactor.
2. Existing saved session/state formats using scalar minutes will need migration handling or reset behavior.
3. Cache keys must include interval payloads to avoid stale schedule reuse.
4. Documentation and README scheduling explanation should be updated to interval-based logic.

---

## Deletion Summary (High Confidence)
Methods that should be removed from active design:
1. Owner.set_weekday_time
2. Owner.set_weekend_time
3. Scheduler.calculate_remaining_minutes

Methods that should be retained but rewritten significantly:
1. Owner.__init__
2. Owner.get_available_time (or replaced)
3. Scheduler.schedule_essential_tasks
4. Scheduler.schedule_ranked_optional_tasks
5. Scheduler.generate_schedule
6. Scheduler.generate_owner_schedule
7. Scheduler.get_unscheduled_tasks

---

## Final Recommendation
Implement in phases while preserving deterministic behavior:
1. Data model and validation for available-window intervals.
2. Wizard UI for interval entry and review.
3. Window normalization and merged-window computation.
4. Explicit timestamp placement engine.
5. Timeline-oriented UI output with unscheduled reasons.
6. Test suite migration and expansion for interval edge cases.

This sequencing lowers risk while delivering the requested user-facing outcome: seamless multi-range input and explicit start/end task schedules.
