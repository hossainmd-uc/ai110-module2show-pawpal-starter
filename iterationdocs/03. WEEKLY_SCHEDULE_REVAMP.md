# Daily/Weekly Recurrence Revamp Plan (No-Code Design Spec)

## Purpose
This document defines the required natural-language changes to support recurring pet-care tasks, specifically:
1. Daily recurrence
2. Weekly recurrence (with a required day selection)

It also defines how schedule generation should support date-level filtering, while preserving the existing weekday/weekend availability-window model.

---

## Product Direction
1. Keep availability setup as weekday/weekend windows (this remains sufficient for time capacity).
2. Add recurrence metadata to tasks so a task can repeat automatically.
3. On completion of a recurring task, automatically create the next occurrence.
4. Allow users to filter generated schedules by specific date.
5. For weekly tasks, require a specific day assignment.

Core design principle:
1. A task template defines recurrence rules.
2. A task occurrence is the concrete instance that appears on a schedule and can be completed.
3. A real calendar date is the internal source of truth for every occurrence.

---

## Recurrence Model

### Recurrence types
1. None (one-time task)
2. Daily
3. Weekly

### Weekly day requirement
1. If recurrence is weekly, user must choose one day:
- Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, or Sunday
2. If recurrence is daily, no specific day field is required.
3. If recurrence is none, no recurrence day is required.

### Task lifecycle concepts
1. Template task: reusable definition with recurrence settings.
2. Occurrence task: generated instance for a specific date/day context.
3. Completion event: marks an occurrence done.
4. Regeneration: if recurrence applies, next occurrence is created automatically.

### Real-date internal model (required)
1. Every occurrence stores a due_date (for example, 2026-03-31).
2. Day name (Monday-Sunday) is derived from due_date for filtering and weekly matching.
3. Day type (weekday/weekend) is derived from due_date for availability-window selection.
4. Recurrence generation always advances from date to date:
- Daily: due_date + 1 day
- Weekly: due_date + 7 days
5. Recurrence day on weekly templates is a rule field, while due_date is the concrete schedule field.

---

## Scheduling and Date Filtering Behavior

### Why a date concept is needed
Even with weekday/weekend availability windows, recurrence requires date-aware filtering (with derived day context) so the app can decide:
1. Which recurring templates are due for the selected date
2. Which occurrences should appear in the generated schedule

### Proposed day flow
1. User picks a target date in the scheduling section (primary control).
2. UI can still show a derived day label (Monday-Sunday) for readability.
3. System maps that date to day type:
- Monday-Friday -> weekday windows
- Saturday-Sunday -> weekend windows
4. Scheduler receives:
- target_date (for recurrence eligibility and occurrence matching)
- day_type (for availability windows)
5. Scheduler includes only due tasks for that date.
6. Output can be filtered by selected date and displayed with exact start/end times.

### Recurrence eligibility rules
1. Daily task is eligible when due_date matches selected date.
2. Weekly task is eligible when due_date matches selected date.
3. One-time task is eligible if due_date matches selected date and it is not completed.
4. Completed recurring occurrences are excluded from current schedule; next occurrence appears when due.

---

## Backend Impact Assessment

### Backend essentials (must-have)
These are required for a reliable recurrence system even if the UX is excellent.

1. Canonical date field on occurrences
- Every schedulable task occurrence must store `due_date`.
- `due_date` is the single source of truth for schedule inclusion.

2. Recurrence rule engine
- Daily recurrence creates the next occurrence at `due_date + 1 day`.
- Weekly recurrence creates the next occurrence at `due_date + 7 days`.
- Weekly templates require a valid weekly day rule at creation time.

3. Template/occurrence separation
- Templates define recurrence and static task metadata.
- Occurrences represent executable work items for a concrete date.
- Scheduler only consumes occurrences.

4. Completion-triggered regeneration
- Completing a recurring occurrence automatically creates exactly one next occurrence.
- Non-recurring occurrences do not regenerate.

5. Idempotency and duplicate protection
- Use a uniqueness rule on `source_template_id + due_date` for active occurrences.
- Repeated completion events must not create duplicate next occurrences.

6. Atomic write behavior
- Marking complete and creating the next occurrence must succeed/fail together.
- If the second write fails, completion should not remain partially committed.

7. Date-to-day-type mapping
- Derive weekday/weekend from `due_date`.
- Use derived day type to select availability windows.

8. Day-aware scheduler entrypoints
- Scheduler API should accept `target_date`.
- Task candidate collection must be filtered by `due_date == target_date` before placement.

9. Query/index support
- Retrieval must efficiently support lookups by `due_date`, `is_completed`, and `source_template_id`.
- This is required for day views and future multi-day views.

10. Auditing and traceability
- Persist completion date/time and linkage between completed occurrence and generated successor.
- Keep an append-only completion log for debugging and user trust.

11. Backward compatibility and migration
- Legacy tasks default to `recurrence_type = none`.
- Legacy tasks missing `due_date` are assigned during migration.
- Migration should be deterministic and rerunnable safely.

12. Cache correctness
- Cache keys must include `target_date` and recurrence-relevant state.
- Completion/regeneration must invalidate schedule cache for affected dates.

13. Catch-up recurrence support
- Before generating a schedule for `target_date`, materialize missing recurring occurrences up to `target_date`.
- Catch-up must be deterministic and idempotent.

### DayType and day concepts
Modifications:
1. Keep existing DayType enum for availability windows.
2. Add a separate day-of-week concept for recurrence filtering.

New additions needed:
1. DayOfWeek enum (or equivalent constant set) for Monday-Sunday.
2. Utility mapping function from DayOfWeek to DayType.
3. Date utility helpers for due-date arithmetic and weekday derivation.

No deletions required:
1. Existing weekday/weekend categories remain valid.

### Task object changes
Modifications needed:
1. Extend Task to carry recurrence metadata.
2. Distinguish template-level fields from occurrence-level fields.

New fields (conceptual):
1. recurrence_type: none | daily | weekly
2. recurrence_day: optional day-of-week (required when weekly)
3. is_template: identifies template task definition
4. source_template_id: links occurrence to its template
5. due_date: identifies the exact calendar day an occurrence is schedulable
6. completed_at_date: calendar date when the occurrence was completed (for idempotency and audit)

New methods suggested:
1. validate_recurrence_configuration
2. is_due_on_date(target_date)
3. create_next_occurrence(current_date)
4. clone_as_occurrence(target_date)

Methods to modify:
1. mark_completed should support recurrence handling trigger.
2. get_status may need richer states (pending, completed, skipped, archived).

Potential deletions/deprecations:
1. No immediate deletions required in Task.
2. Any logic that assumes a task is a single permanent object should be deprecated in favor of template + occurrence lifecycle.

### Pet object changes
Modifications needed:
1. Separate storage for templates and active occurrences, or support a unified collection with type flags.
2. Lookup methods should support retrieval by template ID and occurrence ID.

New methods suggested:
1. add_task_template
2. add_task_occurrence
3. list_due_occurrences(target_date)
4. complete_occurrence_and_regenerate(occurrence_id, current_date)
5. ensure_occurrences_up_to(target_date)

Methods to modify:
1. add_task and list_tasks semantics should be clarified to avoid mixing templates and occurrences unintentionally.

Potential deletions/deprecations:
1. None mandatory, but generic task collection methods may need to be split for clarity.

### Owner object changes
Modifications needed:
1. Maintain existing availability window methods.
2. Add methods that return windows based on selected date via day-type mapping.

New methods suggested:
1. get_windows_for_date(target_date)
2. get_day_type_for_date(target_date)

Potential deletions/deprecations:
1. None required if existing day_type APIs remain in use.

### Scheduler object changes
Modifications needed:
1. Accept target_date as an explicit scheduler input.
2. Filter candidates to due tasks for that date.
3. Keep explicit timestamp placement behavior from current interval scheduling.
4. Include recurrence context in schedule output (template source, recurrence type).

New methods suggested:
1. collect_due_tasks_for_date(owner, target_date)
2. filter_by_recurrence(tasks, target_date)
3. generate_schedule_for_date(owner, target_date)
4. ensure_recurring_catch_up(owner, target_date)

Methods to modify:
1. generate_schedule should become date-aware.
2. generate_owner_schedule should become date-aware and recurrence-aware.
3. unscheduled-reason logic should include recurrence-related reasons when relevant.

Potential deletions/deprecations:
1. Any scheduler entrypoint that only understands day_type without a concrete date should be deprecated.

---

## Completion and Auto-Generation Flow

Recommended workflow:
1. User marks an occurrence complete.
2. System checks recurrence_type.
3. If recurrence_type is none:
- close occurrence only.
4. If recurrence_type is daily:
- generate next daily occurrence with due_date = current_date + 1 day and link to same template.
5. If recurrence_type is weekly:
- generate next weekly occurrence with due_date = current_date + 7 days.
6. Persist completion and new occurrence atomically so no duplicates are created.

Safety constraints:
1. Prevent duplicate next-occurrence generation when user clicks complete repeatedly.
2. Ensure idempotent completion behavior using occurrence IDs and completion timestamps.
3. Enforce uniqueness on source_template_id + due_date for active occurrences.
4. Ensure completion + regeneration are transactional or transaction-like in behavior.

### Catch-up recurrence policy (required)
This keeps assignment requirements intact while supporting skipped dates.

1. On completion, create only the immediate next occurrence.
- Daily recurrence: `+1 day`
- Weekly recurrence: `+7 days`

2. Before generating a schedule for a selected date, run a catch-up step.
- Ensure recurring occurrences exist up to `target_date`.
- If user skipped dates, create missing occurrences in order.

3. Schedule output remains date-specific.
- After catch-up, place only tasks where `due_date == target_date`.

4. Catch-up must be idempotent and duplicate-safe.
- Re-running catch-up cannot create duplicate occurrences.
- Continue enforcing uniqueness on `source_template_id + due_date`.

5. Preserve history and avoid over-generation.
- Keep prior missed dates visible in history/backlog if desired.
- Do not generate occurrences beyond `target_date` in catch-up mode.

### Example: daily task when user skips dates
1. Daily occurrence due `2026-03-31` is completed.
2. Immediate successor due `2026-04-01` is created.
3. User generates schedule for `2026-04-02` without opening `2026-04-01`.
4. Catch-up creates the missing `2026-04-02` occurrence if absent.
5. Scheduler for `2026-04-02` includes the `2026-04-02` occurrence.

### Example: weekly task when user skips dates
1. Weekly occurrence due `2026-03-31` is completed.
2. Immediate successor due `2026-04-07` is created.
3. User jumps to `2026-04-21`.
4. Catch-up ensures intermediate weekly occurrences exist (`2026-04-14`, `2026-04-21`) if missing.
5. Scheduler for `2026-04-21` includes only occurrences due on `2026-04-21`.

---

## Data and State Model Changes (app state)

Current model gap:
1. Session state currently centers on generic task records without recurrence lifecycle.

New state fields needed:
1. selected_date (primary schedule filter)
2. recurrence_defaults for task-creation forms
3. task_templates per pet
4. active_occurrences per pet
5. completed_occurrence_log
6. last_generated_date
7. recurrence_generation_guard (to prevent duplicate creation on reruns)
8. optional derived_day_name (display only, derived from selected_date)

State fields to modify:
1. Existing task lists should evolve into template + occurrence model, or include explicit task_kind metadata.

Potential state deletions/deprecations:
1. Flat task-only structures without recurrence metadata should be deprecated.

---

## UI/UX Changes

### Task creation/editing UI
Add inputs:
1. Recurrence type selector: none, daily, weekly.
2. Weekly day selector (visible only when weekly is chosen).
3. Optional preview text:
- Daily: repeats every day
- Weekly: repeats every <day>

Validation UX:
1. Require day selection when weekly is selected.
2. Show inline errors for invalid recurrence combinations.

### Scheduling UI
Add controls:
1. Date filter selector (primary).
2. Display derived day name and day type mapping (weekday/weekend) for clarity.

Schedule display updates:
1. Keep explicit start/end columns.
2. Add recurrence columns:
- recurrence_type
- recurrence_day (if weekly)
3. Optionally group by:
- due on selected date
- completed on selected date
- unscheduled on selected date

### Completion UX
When user completes a recurring task:
1. Show confirmation message that next occurrence was created.
2. Provide a small audit trail entry (completed occurrence -> generated next occurrence).

---

## Test Suite Impact

Files impacted:
1. tests/test_pawpal.py

New test categories required:
1. Recurrence validation
- weekly requires day
- daily ignores recurrence day
2. Due filtering
- daily creates next due_date on next day
- weekly creates next due_date on plus seven days
3. Completion regeneration
- daily completion creates next daily occurrence
- weekly completion creates next weekly occurrence
- no recurrence creates none
4. Idempotency
- repeated completion does not create duplicate next occurrences
- repeated completion returns same successor reference when one already exists
5. Atomicity behavior
- if successor creation fails, completion is rolled back or treated as failed
6. Uniqueness constraints
- source_template_id + due_date cannot produce two active occurrences
7. Cache invalidation behavior
- completion/regeneration invalidates affected date cache entries
8. Day mapping
- Monday-Friday uses weekday windows
- Saturday-Sunday uses weekend windows
- selected_date reliably derives day name and day type
9. Scheduler integration
- due tasks only are considered for placement
- explicit timestamps still correct under recurrence filtering
10. Catch-up behavior
- when user skips dates, recurring occurrences are materialized up to selected date
- repeated generation remains idempotent (no duplicate occurrences)

Existing tests to modify:
1. Tests assuming static task lists without recurrence metadata.
2. Tests invoking scheduler without a target_date parameter.

Potential obsolete assertions:
1. Assertions that equate task identity with a single persistent object (no template/occurrence split).

---

## Migration and Compatibility Notes
1. Existing tasks without recurrence metadata should default to recurrence_type = none.
2. Existing completed recurring tasks cannot regenerate correctly unless migrated to template/occurrence model.
3. Introduce migration script or first-run normalization for legacy session payloads.
4. For legacy tasks with no due_date, initialize due_date using a deterministic migration rule (for example, task created date; fallback to migration run date).
5. Cache keys must include selected_date and recurrence-relevant data.

---

## Deletions, Modifications, and Additions Summary

Deletions/deprecations (recommended):
1. Scheduler methods that accept only day_type and not target_date should be deprecated.
2. Flat task list assumptions should be deprecated in favor of recurrence-aware task lifecycle.

Major modifications:
1. Task: recurrence metadata and due-day logic.
2. Pet: template/occurrence storage semantics.
3. Scheduler: date-aware due filtering and recurrence-aware schedule generation.
4. App state: track selected_date and recurrence structures.
5. UI: recurrence controls + date filter + completion audit.

Major additions:
1. Day-of-week abstraction.
2. Recurrence rule validation.
3. Completion-triggered next occurrence generation.
4. Recurrence-focused tests and idempotency protections.
5. Date-based occurrence model and date-derivation utilities.

---

## Recommended Implementation Phases

Phase 1: Data model foundations
1. Add recurrence fields and day-of-week abstractions.
2. Add validation rules for recurrence configuration.
3. Add template vs occurrence representation.

Phase 2: Scheduler integration
1. Add target_date input to scheduling entrypoints.
2. Filter due tasks by recurrence before placement.
3. Preserve explicit start/end interval placement.
4. Add deterministic pre-schedule catch-up up to `target_date`.

Phase 3: Completion workflow
1. Implement complete-and-regenerate logic.
2. Add duplicate-guard/idempotent protections.
3. Add unscheduled reason extensions for recurrence context.
4. Add atomic write safeguards for completion + successor creation.

Phase 4: UI/state updates
1. Add recurrence controls in task forms.
2. Add date filter in schedule generation section.
3. Update schedule tables with recurrence fields.
4. Add user feedback for auto-generated next occurrences.

Phase 5: Testing and migration
1. Expand tests for recurrence/date filtering/idempotency.
2. Add compatibility handling for legacy tasks.
3. Verify cache behavior with selected_date and recurrence inputs.

---

## Backend Readiness Checklist
All items should be true before release.

1. Every active occurrence has a valid `due_date`.
2. Weekly templates always have a valid weekly day rule.
3. Scheduler accepts `target_date` and ignores non-due occurrences.
4. Completion of recurring tasks generates exactly one successor.
5. Duplicate successor creation is prevented by both logic and uniqueness constraints.
6. Completion/regeneration path is atomic from a user-observable perspective.
7. Weekday/weekend windows are derived from `due_date`, not manually selected in scheduler internals.
8. Cache invalidation occurs for impacted dates after completion/regeneration.
9. Migration path for legacy tasks has test coverage.
10. Audit trail can explain when and why a successor was generated.
11. Skipped-date generation still shows recurring tasks correctly via catch-up policy.

---

## Final Recommendation
Your instinct is correct: weekday/weekend availability can stay as-is, but scheduling must become date-aware for recurrence.

The cleanest long-term design is:
1. Keep availability windows by day type.
2. Add recurrence and day-of-week metadata to task definitions.
3. Schedule occurrences (not templates) for a selected date.
4. On completion of recurring occurrences, auto-generate the next due occurrence.

This gives users a clear daily workflow, supports weekly specificity, and keeps your current interval scheduler architecture intact.
