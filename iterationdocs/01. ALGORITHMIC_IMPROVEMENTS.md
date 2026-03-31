# PawPal+ Algorithmic Improvements Proposal

This document outlines proposed algorithmic and logic improvements to enhance the efficiency and user experience of the PawPal+ scheduling system.

---

## 1. Cache Scheduling Results

### Problem
Currently, every schedule generation recalculates everything from scratch, even when the underlying data (owner config, pets, tasks) hasn't changed. This creates unnecessary computation when users toggle between weekday/weekend views or regenerate the same schedule multiple times.

### Proposed Solution
Implement a caching mechanism that stores computed schedules with a cache key based on:
- Owner configuration (name, weekday_minutes, weekend_minutes)
- Pets and their tasks (names, durations, priorities, completion status)
- Day type (weekday/weekend)

### Implementation Details

**In `app.py`:**
```python
import hashlib
import json

def compute_state_hash() -> str:
    """Generate hash of current scheduling state."""
    state = {
        "owner": st.session_state.owner_name,
        "weekday_mins": st.session_state.weekday_minutes,
        "weekend_mins": st.session_state.weekend_minutes,
        "pets": st.session_state.pets
    }
    return hashlib.md5(json.dumps(state, sort_keys=True).encode()).hexdigest()

# In init_state():
if "schedule_cache" not in st.session_state:
    st.session_state.schedule_cache = {}
```

**Schedule generation with cache:**
```python
cache_key = f"{compute_state_hash()}_{day_choice}"
if cache_key in st.session_state.schedule_cache:
    schedule = st.session_state.schedule_cache[cache_key]
    st.session_state.last_schedule = schedule
    st.session_state.last_day_type = day_choice
    st.success("Schedule retrieved from cache")
else:
    owner_model = build_owner_from_state()
    scheduler = Scheduler()
    schedule = scheduler.generate_owner_schedule(owner_model, day_choice)
    st.session_state.schedule_cache[cache_key] = schedule
    st.session_state.last_schedule = schedule
    st.session_state.last_day_type = day_choice
    st.success("Schedule generated")
```

### Benefits
- **Instant results**: Toggling between weekday/weekend without data changes is instant
- **Reduced computation**: Saves CPU cycles on redundant calculations
- **Better UX**: Faster response times improve user experience

### Considerations
- **Cache invalidation**: Clear cache when pets/tasks are modified (add/remove/complete tasks)
- **Memory usage**: Limit cache size (e.g., keep only last 5 schedules)
- **Cache should be per-session**: Already handled by `st.session_state`
- **Coordination with #7 (Incremental Updates)**: If implementing both, incremental updates must invalidate cache OR update cache simultaneously. Consider whether cache regeneration is faster than incremental update logic.
- **Hash computation**: The example hashes `st.session_state.pets` directly, but this contains Task objects. In practice, extract only serializable fields (task names, durations, completion status) for hashing.

---

## 2. Early Exit on Time Exhaustion

### Problem
The scheduling algorithm iterates through all optional tasks even when the remaining time budget is exhausted (0 minutes). This wastes computation on tasks that can never fit.

### Proposed Solution
Add an early exit condition that breaks out of optional task loops when remaining time reaches zero.

### Implementation Details

**In `pawpal_system.py` - `Scheduler.generate_owner_schedule()`:**
```python
# After essential task scheduling:
if remaining_minutes <= 0:
    return schedule_by_pet  # No time for optional tasks

# Before optional task loop:
for pet, task in optional_entries:
    if remaining_minutes <= 0:
        break  # No more time available
    duration = task.get_duration()
    if duration <= remaining_minutes:
        schedule_by_pet[pet.pet_name].append(task)
        remaining_minutes -= duration
```

### Benefits
- **Faster execution**: Reduces unnecessary iterations when time budget is tight
- **Cleaner logic**: Makes the algorithm's behavior more explicit
- **Scalability**: More impactful with larger task lists

### Considerations
- Minimal code change, no breaking changes
- Works well with current greedy scheduling approach

---

## 3. Pre-filter Completed Tasks

> **⚠️ Implementation Note**: Consider implementing **#1 (Cache Scheduling Results)** first. Pre-filtering changes what gets scheduled, which should trigger cache invalidation. Coordinating these ensures cache remains valid.

### Problem
Completed tasks are still processed during scheduling loops. They get evaluated, compared, and included in iterations even though they should never be scheduled.

### Proposed Solution
Filter out completed tasks at the beginning of scheduling methods, before any iteration logic.

### Implementation Details

**In `pawpal_system.py` - `Scheduler.generate_schedule()`:**
```python
def generate_schedule(self, owner: Owner, pet: Pet, day_type: DayType | str) -> List[Task]:
    """Generate a full schedule for one pet and day type."""
    if owner.pets and pet not in owner.pets:
        raise ValueError("Selected pet is not associated with the owner")

    available_minutes = owner.get_available_time(day_type)
    
    # Filter out completed tasks immediately
    tasks = [task for task in pet.list_tasks() if not task.is_completed]
    
    essential_scheduled = self.schedule_essential_tasks(tasks, available_minutes)
    # ... rest of method
```

**In `Scheduler.generate_owner_schedule()`:**
```python
# When gathering essential tasks:
for pet in pets:
    for task in pet.list_tasks():
        if task.is_essential and not task.is_completed:  # Add completion check
            essential_entries.append((pet, task))

# When gathering optional tasks:
for pet in pets:
    for task in pet.list_tasks():
        if (not task.is_essential) and task.is_selected_optional and not task.is_completed:
            optional_entries.append((pet, task))
```

### Benefits
- **Reduced iteration overhead**: Fewer tasks to process = faster execution
- **Logical correctness**: Completed tasks should never be rescheduled
- **Scales well**: More impactful as owners complete more tasks throughout the day

### Considerations
- Straightforward implementation
- May want to track completed tasks separately for reporting purposes
- Consider adding a "show completed tasks" toggle in UI for visibility

---

## 4. Min Heap for Dynamic Minimum Duration Tracking

### Problem
When remaining time is very low (e.g., 5 minutes left), the algorithm still iterates through all remaining optional tasks, even if the shortest task requires more time than available. A naive approach of recalculating the minimum after each scheduled task requires O(n) time per check, which is inefficient.

### Proposed Solution
Use a **min heap** data structure to maintain dynamic access to the minimum task duration. A min heap provides O(1) access to the minimum element and automatically updates when tasks are scheduled, enabling efficient early exit checks without repeatedly scanning all tasks.

### Implementation Details

**Add import at top of `pawpal_system.py`:**
```python
import heapq
```

**In `Scheduler.generate_owner_schedule()`:**
```python
def generate_owner_schedule(self, owner: Owner, day_type: DayType | str) -> Dict[str, List[Task]]:
    """
    Generate schedules using min heap for efficient minimum duration tracking.
    """
    pets = owner.list_pets()
    schedule_by_pet: Dict[str, List[Task]] = {pet.pet_name: [] for pet in pets}
    
    available_minutes = owner.get_available_time(day_type)
    remaining_minutes = available_minutes
    
    # Schedule essential tasks (unchanged)
    essential_entries: List[tuple[Pet, Task]] = []
    for pet in pets:
        for task in pet.list_tasks():
            if task.is_essential:
                essential_entries.append((pet, task))
    
    for pet, task in essential_entries:
        duration = task.get_duration()
        if duration <= remaining_minutes:
            schedule_by_pet[pet.pet_name].append(task)
            remaining_minutes -= duration
    
    # Build optional tasks list AND min heap simultaneously
    optional_entries: List[tuple[Pet, Task]] = []
    duration_heap = []  # Min heap: (duration, pet_name, task_name, task_id)
    
    for pet in pets:
        for task in pet.list_tasks():
            if (not task.is_essential) and task.is_selected_optional:
                optional_entries.append((pet, task))
                # Push to heap for O(1) minimum lookup
                heapq.heappush(duration_heap, (
                    task.get_duration(),
                    pet.pet_name.lower(),
                    task.task_name.lower(),
                    id(task)  # Unique identifier for lazy deletion
                ))
    
    # Sort optional tasks by rank (determines scheduling order)
    optional_entries.sort(
        key=lambda entry: (
            entry[1].optional_rank if entry[1].optional_rank is not None else 10**9,
            entry[0].pet_name.lower(),
            entry[1].task_name.lower(),
        )
    )
    
    # Track scheduled task IDs for lazy heap maintenance
    scheduled_ids = set()
    
    # Schedule optional tasks with heap-based early exit
    for pet, task in optional_entries:
        # Clean heap top: remove already-scheduled tasks from heap top
        while duration_heap and duration_heap[0][3] in scheduled_ids:
            heapq.heappop(duration_heap)
        
        # O(1) minimum duration check via heap peek
        if duration_heap:
            min_duration = duration_heap[0][0]
            if remaining_minutes < min_duration:
                # Early exit! No remaining task can fit
                break
        
        # Try to schedule this task (in rank order)
        duration = task.get_duration()
        if duration <= remaining_minutes:
            schedule_by_pet[pet.pet_name].append(task)
            remaining_minutes -= duration
            scheduled_ids.add(id(task))  # Mark as scheduled (lazy deletion)
    
    return schedule_by_pet
```

### How It Works

#### Visual Example:
```
Initial state:
  Heap: [10, 15, 20, 25, 30]  (Feed, Groom, Train, Play, Walk)
  Remaining: 50 min
  Min check: 50 >= 10 ✓ Continue scheduling

After scheduling Walk (30 min, rank 1):
  Heap: [10, 15, 20, 25, 30*]  (*marked in scheduled_ids)
  Remaining: 20 min
  Min check: 20 >= 10 ✓ Continue

After scheduling Feed (10 min, rank 2):
  Heap: [15, 20, 25]  (cleaned automatically when peeking)
  Remaining: 10 min
  Min check: 10 < 15 ✗ EARLY EXIT!
  Result: Skipped checking Play, Groom, Train - saved 3 iterations
```

#### Lazy Deletion Strategy:
Instead of removing tasks from the heap immediately (expensive O(n) operation), we:
1. Mark scheduled tasks in a `scheduled_ids` set
2. Clean the heap top when checking minimum (only removes what's necessary)
3. Heap naturally maintains correct minimum as we go

### Benefits
- **O(1) minimum lookup**: Just peek at `heap[0]` instead of scanning all tasks
- **Automatic updates**: Heap structure maintains minimum as tasks are scheduled
- **Efficient lazy deletion**: Only clean heap when needed, not after every schedule
- **Scalability**: O(n log n) total complexity vs O(n²) with naive recalculation
- **Early exit optimization**: Can exit immediately when no task can fit

### Time Complexity Analysis

| Operation | Naive Approach | Min Heap Approach |
|-----------|---------------|-------------------|
| Initial setup | O(n) | O(n log n) heapify |
| Check minimum (each iteration) | O(n) | **O(1)** peek |
| Total scheduling | O(n²) | **O(n log n)** |

For 100 optional tasks:
- Naive: ~10,000 operations
- Min heap: ~664 operations (15x faster!)

### Considerations
- **Heap overhead**: Adds O(n log n) setup time, but pays off with O(1) lookups
- **Lazy deletion**: Uses slightly more memory (heap retains scheduled tasks temporarily)
- **When most beneficial**: Large task lists with varying durations and tight time budgets
- **Python's heapq**: Built-in, no external dependencies needed
- **Alternative**: Could use `SortedList` from `sortedcontainers` for cleaner code (requires pip install)

### Alternative: SortedList (Optional Enhancement)

If willing to add a dependency:
```python
from sortedcontainers import SortedList

# In generate_owner_schedule():
durations = SortedList(task.get_duration() for pet, task in optional_entries)

# O(1) minimum check
if durations and remaining_minutes < durations[0]:
    break

# O(log n) removal when scheduling
durations.remove(scheduled_task.get_duration())
```

This provides cleaner syntax but requires an external library (`pip install sortedcontainers`).

---

## 6. Hybrid Priority System (3-Tier Groups + Batch Ranking)

### Problem
**Current system limitations:**
- Pure numerical ranking (1-N) is tedious for many tasks ("Is this rank 7 or 8?")
- Single task-at-a-time updates require multiple page refreshes
- No semantic meaning to rank numbers (what does "rank 5" mean?)
- Cognitive load increases with task count

### Proposed Solution
Replace pure numerical ranking with a **hybrid 3-tier + ranking system**:

**Structure:**
- **3 Priority Groups**: High (🔴), Medium (🟡), Low (🟢) for semantic categorization
- **Ranks within groups**: 1, 2, 3, etc. for precise ordering
- **Batch editing interface**: Group-based editors with color coding

**Example:**
```
🔴 HIGH PRIORITY
  1. Brush teeth
  2. Training session

🟡 MEDIUM PRIORITY
  1. Groom fur
  2. Play time

🟢 LOW PRIORITY
  1. Spa treatment
```

### Implementation Details

**Data Model Changes (`pawpal_system.py`):**
```python
class Task:
    def __init__(
        self,
        task_name: str,
        duration_minutes: int,
        is_essential: bool = False,
        priority_group: str = "medium",  # "high", "medium", "low"
        rank_in_group: Optional[int] = None,  # Rank within priority group
    ):
        # ... existing code ...
        if not is_essential:
            self.priority_group = priority_group
            self.rank_in_group = rank_in_group
```

**Scheduling Logic:**
```python
def get_selected_ranked_optional_tasks(self, tasks: List[Task]) -> List[Task]:
    """Sort by: 1) priority group, 2) rank within group, 3) task name."""
    priority_order = {"high": 1, "medium": 2, "low": 3}
    
    def rank_key(task: Task) -> tuple[int, int, str]:
        priority = priority_order.get(task.priority_group or "medium", 2)
        rank = task.rank_in_group if task.rank_in_group is not None else 10**9
        return (priority, rank, task.task_name.lower())
    
    filtered = [t for t in tasks if (not t.is_essential) and t.is_selected_optional]
    return sorted(filtered, key=rank_key)
```

**UI Changes (`app.py`):**
- Task creation: Priority selector (🔴🟡🟢) instead of single numeric rank
- Ranking interface: Grouped expandable sections (one per priority level)
- Batch operations: Editable dataframe per priority group, move tasks between groups
- Visual display: Color-coded badges showing "🔴 High #1" instead of just "Rank 1"

### Benefits
- **Reduced cognitive load**: "High priority #2" vs "Rank 7" is more meaningful
- **Faster categorization**: Choose priority tier first (3 options vs 15)
- **Easier reordering**: Manage 2-3 tasks per tier instead of 15 total
- **Batch operations**: Move all low tasks to medium, auto-sort alphabetically
- **Visual clarity**: Color coding provides instant feedback
- **Flexible precision**: Simple users use tiers only, power users fine-tune ranks

### Considerations
- **Migration strategy**: Auto-convert existing `optional_rank` to tier + rank (top 33% → high, etc.)
- **Backward compatibility**: Default existing tasks to "medium" priority
- **UI complexity**: Slightly more complex than single list, but significantly better UX
- **Phased rollout option**: Start with pure 3-tier (alphabetical within tiers), add ranks in v2

### Alternative Approaches Considered
- **Pure numerical** (current): Precise but tedious, no semantic meaning
- **Pure 3-tier**: Simple but lacks precise ordering (needs tie-breaking)
- **Hybrid** (recommended): Best balance of simplicity and control

---

## 7. Incremental Schedule Updates

> **⚠️ Implementation Note**: This proposal is tightly coupled with **#1 (Cache Scheduling Results)**. When implementing together:
> - Incremental updates should **invalidate the cache** for the current day type
> - OR update both the displayed schedule AND the cached version simultaneously
> - Cache key should include completed task state to avoid stale cache hits
> - Consider: Is incremental update + cache invalidation faster than just regenerating with cache?

### Problem
When a user marks a task as completed during the day, the entire schedule must be regenerated from scratch to redistribute the freed time to other tasks.

### Proposed Solution
Implement incremental updates that:
1. Remove the completed task from the cached schedule
2. Recalculate freed time
3. Attempt to schedule additional optional tasks with the freed time
4. Only regenerate fully if needed

**Integration with Cache (#1):**
- Option A: Incremental update invalidates cache, next generation will re-cache
- Option B: Incremental update modifies both displayed schedule and cache simultaneously
- Option C: Skip incremental updates if cache exists - just invalidate and regenerate (simpler)

### Implementation Details

**Add incremental update method in `Scheduler`:**
```python
def update_schedule_after_completion(
    self,
    current_schedule: Dict[str, List[Task]],
    completed_task: Task,
    owner: Owner,
    day_type: DayType | str
) -> Dict[str, List[Task]]:
    """
    Update schedule incrementally after task completion.
    Returns updated schedule or None if full regeneration needed.
    """
    # Find and remove completed task
    pet_name = None
    for pname, tasks in current_schedule.items():
        if completed_task in tasks:
            pet_name = pname
            tasks.remove(completed_task)
            break
    
    if pet_name is None:
        return current_schedule  # Task not in schedule
    
    # Calculate freed time
    freed_minutes = completed_task.get_duration()
    
    # Gather unscheduled optional tasks
    scheduled_task_ids = {id(task) for tasks in current_schedule.values() for task in tasks}
    unscheduled_optional = []
    
    for pet in owner.list_pets():
        for task in pet.list_tasks():
            if (not task.is_essential 
                and task.is_selected_optional 
                and not task.is_completed
                and id(task) not in scheduled_task_ids):
                unscheduled_optional.append((pet, task))
    
    # Sort by rank (same logic as generate_owner_schedule)
    unscheduled_optional.sort(
        key=lambda entry: (
            entry[1].optional_rank if entry[1].optional_rank is not None else 10**9,
            entry[0].pet_name.lower(),
            entry[1].task_name.lower(),
        )
    )
    
    # Try to schedule additional tasks with freed time
    for pet, task in unscheduled_optional:
        duration = task.get_duration()
        if duration <= freed_minutes:
            current_schedule[pet.pet_name].append(task)
            freed_minutes -= duration
    
    return current_schedule
```

**In `app.py`, when marking completed:**
```python
if st.button("Mark completed"):
    for task in selected_pet_data["tasks"]:
        if task["task_name"] == completion_target:
            task["is_completed"] = True
            
            # Incremental update if schedule exists
            if st.session_state.last_schedule is not None:
                owner_model = build_owner_from_state()
                # Find the task object
                for pet in owner_model.list_pets():
                    try:
                        task_obj = pet.get_task_by_name(completion_target)
                        scheduler = Scheduler()
                        updated_schedule = scheduler.update_schedule_after_completion(
                            st.session_state.last_schedule,
                            task_obj,
                            owner_model,
                            st.session_state.last_day_type
                        )
                        st.session_state.last_schedule = updated_schedule
                        break
                    except ValueError:
                        continue
            break
    st.success(f"Marked '{completion_target}' as completed")
```

### Benefits
- **Instant updates**: No full regeneration needed
- **Better UX**: Schedule updates immediately without "Generate" button
- **Preserves context**: Other scheduled tasks remain in place
- **Smart redistribution**: Automatically fills freed time with next-best optional tasks

### Considerations
- More complex implementation than full regeneration
- May need to handle edge cases (essential tasks completed, etc.)
- Consider whether to automatically trigger update vs. requiring user action

---

## 8. Smart Default Rankings

> **⚠️ Implementation Note**: Hold off on this proposal until **#6 (Hybrid Priority System)** is implemented. This proposal assumes pure numerical ranking. If using the 3-tier priority system, smart defaults need to assign both `priority_group` and `rank_in_group` instead of just `optional_rank`.

### Problem
New optional tasks are created with `optional_rank = None`, requiring manual ranking before they participate in scheduling. This creates friction for users adding multiple tasks.

### Proposed Solution
Automatically assign sensible default ranks to new optional tasks:
- **Option A**: Assign `max(existing_ranks) + 1` (append to end)
- **Option B**: Assign alphabetically (insert in sorted order)
- **Option C**: Let user choose default behavior in settings

### Implementation Details

**In `app.py` - task creation:**
```python
if submit_task:
    clean_name = task_name.strip()
    if not clean_name:
        st.error("Task name cannot be empty")
    elif clean_name.lower() in {
        t["task_name"].lower() for t in selected_pet_data["tasks"]
    }:
        st.error("A task with that name already exists for this pet")
    else:
        # Calculate smart default rank for optional tasks
        default_rank = None
        if not is_essential:
            existing_optional_ranks = [
                t["optional_rank"] 
                for t in selected_pet_data["tasks"] 
                if not t["is_essential"] and t["optional_rank"] is not None
            ]
            if existing_optional_ranks:
                default_rank = max(existing_optional_ranks) + 1
            else:
                default_rank = 1  # First optional task
        
        selected_pet_data["tasks"].append(
            {
                "task_name": clean_name,
                "duration_minutes": int(duration_minutes),
                "is_essential": bool(is_essential),
                "is_selected_optional": not bool(is_essential),
                "optional_rank": default_rank,  # Smart default instead of None
                "is_completed": False,
            }
        )
        st.success(f"Added task '{clean_name}' to {selected_pet_for_tasks}" + 
                  (f" with rank {default_rank}" if default_rank else ""))
```

**Alternative: Interactive rank assignment at creation:**
```python
with col2:
    is_essential = st.checkbox("Essential task", value=True)
    
    # Show rank selector if not essential
    if not is_essential:
        optional_tasks_count = len([
            t for t in selected_pet_data["tasks"] if not t["is_essential"]
        ])
        suggested_rank = optional_tasks_count + 1
        rank_for_new = st.number_input(
            f"Priority rank (suggested: {suggested_rank})",
            min_value=1,
            value=suggested_rank,
            help="1 = highest priority"
        )
```

### Benefits
- **Reduced friction**: Tasks are immediately usable without manual ranking
- **Sensible defaults**: Appending to end is intuitive for most users
- **Still customizable**: Users can adjust ranks later if needed
- **Better onboarding**: New users don't need to understand ranking system immediately

### Considerations
- Should still allow users to modify ranks after creation
- Consider showing a hint/tooltip explaining the ranking system
- May want to add "bulk re-rank" feature (e.g., "reset to alphabetical order")

---

## 9. Lazy Task Lookup Dictionary

### Problem
In `generate_owner_schedule()`, the algorithm iterates through all pets and their tasks multiple times (once for essentials, once for optionals). For owners with many pets and tasks, this creates redundant list traversals.

### Proposed Solution
Build a single comprehensive task index at the start of `generate_owner_schedule()`, then reference it for lookups rather than repeatedly traversing pet lists.

### Implementation Details

**In `pawpal_system.py` - `Scheduler.generate_owner_schedule()`:**
```python
def generate_owner_schedule(self, owner: Owner, day_type: DayType | str) -> Dict[str, List[Task]]:
    """
    Generate schedules for all pets with one shared owner time budget.
    """
    pets = owner.list_pets()
    schedule_by_pet: Dict[str, List[Task]] = {pet.pet_name: [] for pet in pets}
    
    available_minutes = owner.get_available_time(day_type)
    remaining_minutes = available_minutes
    
    # Build comprehensive task index (single traversal)
    task_index: Dict[str, List[tuple[Pet, Task, str]]] = {
        "essential": [],
        "optional": []
    }
    
    for pet in pets:
        for task in pet.list_tasks():
            if task.is_essential:
                task_index["essential"].append((pet, task, "essential"))
            elif task.is_selected_optional:
                task_index["optional"].append((pet, task, "optional"))
    
    # Schedule essential tasks (no more pet.list_tasks() calls)
    for pet, task, _ in task_index["essential"]:
        duration = task.get_duration()
        if duration <= remaining_minutes:
            schedule_by_pet[pet.pet_name].append(task)
            remaining_minutes -= duration
    
    # Sort and schedule optional tasks
    task_index["optional"].sort(
        key=lambda entry: (
            entry[1].optional_rank if entry[1].optional_rank is not None else 10**9,
            entry[0].pet_name.lower(),
            entry[1].task_name.lower(),
        )
    )
    
    for pet, task, _ in task_index["optional"]:
        duration = task.get_duration()
        if duration <= remaining_minutes:
            schedule_by_pet[pet.pet_name].append(task)
            remaining_minutes -= duration
    
    return schedule_by_pet
```

### Benefits
- **Single traversal**: Build index once instead of multiple pet/task iterations
- **Cleaner code**: Separation of concerns (gather vs. process)
- **Easier to extend**: Adding new task categories is simpler
- **Performance**: O(n) instead of O(2n) for task gathering

### Considerations
- Minimal code change with good performance benefit
- Index could be extended to include additional metadata (durations, etc.)
- Works well with other optimizations (pre-filtering, early exit)

---

## 10. Schedule Diff Highlighting

### Problem
When owners modify tasks or time availability and regenerate the schedule, they can't easily see what changed. They have to manually compare the new schedule against memory of the old one.

### Proposed Solution
Store the previous schedule and provide visual highlighting of:
- Tasks that were **added** (newly scheduled)
- Tasks that were **removed** (no longer scheduled)
- Tasks that **stayed the same**

### Implementation Details

**In `app.py` - update session state to track previous schedule:**
```python
def init_state() -> None:
    # ... existing initialization ...
    if "last_schedule" not in st.session_state:
        st.session_state.last_schedule = None
    if "previous_schedule" not in st.session_state:
        st.session_state.previous_schedule = None
```

**When generating schedule:**
```python
if st.button("Generate owner schedule"):
    try:
        owner_model = build_owner_from_state()
        scheduler = Scheduler()
        schedule = scheduler.generate_owner_schedule(owner_model, day_choice)
        
        # Store previous for comparison
        st.session_state.previous_schedule = st.session_state.last_schedule
        st.session_state.last_schedule = schedule
        st.session_state.last_day_type = day_choice
        
        st.success("Schedule generated")
    except ValueError as exc:
        st.error(f"Could not generate schedule: {exc}")
```

**Display with diff highlighting:**
```python
if st.session_state.last_schedule is not None:
    st.markdown("Generated schedule")
    
    # Calculate diff if previous schedule exists
    added_tasks = {}
    removed_tasks = {}
    
    if st.session_state.previous_schedule is not None:
        prev = st.session_state.previous_schedule
        curr = st.session_state.last_schedule
        
        for pet_name in curr.keys():
            prev_task_names = {t.task_name for t in prev.get(pet_name, [])}
            curr_task_names = {t.task_name for t in curr.get(pet_name, [])}
            
            added_tasks[pet_name] = curr_task_names - prev_task_names
            removed_tasks[pet_name] = prev_task_names - curr_task_names
    
    # Display schedule with highlighting
    for pet_name, tasks in st.session_state.last_schedule.items():
        with st.expander(f"{pet_name} schedule", expanded=True):
            if not tasks:
                st.write("No tasks scheduled")
                continue
            
            pet_rows = []
            for task in tasks:
                row = {
                    "task": task.task_name,
                    "minutes": task.get_duration(),
                    "essential": task.is_essential,
                    "optional_rank": task.optional_rank,
                    "status": task.get_status(),
                }
                
                # Add change indicator
                if task.task_name in added_tasks.get(pet_name, set()):
                    row["change"] = "🆕 Added"
                elif task.task_name in removed_tasks.get(pet_name, set()):
                    row["change"] = "❌ Removed"
                else:
                    row["change"] = "✓ Same"
                
                pet_rows.append(row)
            
            st.dataframe(pet_rows, use_container_width=True, hide_index=True)
    
    # Show removed tasks summary
    total_removed = sum(len(tasks) for tasks in removed_tasks.values())
    if total_removed > 0:
        with st.expander(f"⚠️ {total_removed} task(s) removed from previous schedule"):
            for pet_name, task_names in removed_tasks.items():
                if task_names:
                    st.write(f"**{pet_name}**: {', '.join(task_names)}")
```

### Benefits
- **Immediate feedback**: Users see impact of changes instantly
- **Better understanding**: Clarifies why schedule changed
- **Confidence**: Users know their changes were applied correctly
- **Debugging**: Helps identify unexpected schedule behavior

### Considerations
- Adds visual clutter if too prominent
- Consider making diff view toggleable
- May want to add "Undo" button to revert to previous schedule
- Color coding (green/red) could enhance visibility

---

## 11. Precompute Total Essential Time

### Problem
Users aren't warned when their essential tasks exceed available time until after schedule generation. This can be frustrating when trying to fit everything in.

### Proposed Solution
Calculate total essential task duration upfront and display a warning if it exceeds available time for the selected day type.

**When this runs:** On every Streamlit page rerun (automatically updates whenever tasks are added, removed, completed, or time availability changes).

### Implementation Details

**Add helper function in `app.py`:**
```python
def calculate_essential_time() -> tuple[int, int]:
    """Return total essential task duration for (weekday, weekend)."""
    weekday_essential = 0
    weekend_essential = 0
    
    for pet_data in st.session_state.pets.values():
        for task in pet_data["tasks"]:
            if task["is_essential"] and not task.get("is_completed", False):
                duration = int(task["duration_minutes"])
                # Could be extended to handle day-specific tasks
                weekday_essential += duration
                weekend_essential += duration
    
    return weekday_essential, weekend_essential
```

**Display warning before schedule generation:**
```python
st.divider()
st.subheader("4) Generate Shared-Time Schedule")

# Calculate and display time analysis
weekday_essential, weekend_essential = calculate_essential_time()

col1, col2 = st.columns(2)
with col1:
    st.metric("Weekday Essential Tasks", f"{weekday_essential} min")
    if weekday_essential > st.session_state.weekday_minutes:
        st.error(f"⚠️ Exceeds available time by {weekday_essential - st.session_state.weekday_minutes} min")
    else:
        remaining = st.session_state.weekday_minutes - weekday_essential
        st.success(f"✓ {remaining} min remaining for optional tasks")

with col2:
    st.metric("Weekend Essential Tasks", f"{weekend_essential} min")
    if weekend_essential > st.session_state.weekend_minutes:
        st.error(f"⚠️ Exceeds available time by {weekend_essential - st.session_state.weekend_minutes} min")
    else:
        remaining = st.session_state.weekend_minutes - weekend_essential
        st.success(f"✓ {remaining} min remaining for optional tasks")

day_choice = st.radio(
    "Day type",
    options=[DayType.WEEKDAY.value, DayType.WEEKEND.value],
    index=0 if st.session_state.last_day_type == DayType.WEEKDAY.value else 1,
    horizontal=True,
)
```

**Alternative: Show per-pet breakdown:**
```python
with st.expander("Essential Time Breakdown by Pet"):
    for pet_name, pet_data in st.session_state.pets.items():
        essential_for_pet = sum(
            task["duration_minutes"] 
            for task in pet_data["tasks"] 
            if task["is_essential"] and not task.get("is_completed", False)
        )
        st.write(f"**{pet_name}**: {essential_for_pet} min")
```

### Benefits
- **Proactive feedback**: Users know about time constraints before generating schedule
- **Better planning**: Helps owners adjust essential tasks or time availability
- **Reduced frustration**: No surprises about tasks not fitting
- **Educational**: Helps users understand time budgeting

### Considerations
- Should update dynamically when tasks are modified
- Could extend to show per-pet essential time breakdown
- Consider adding suggestions (e.g., "Consider making Task X optional")
- May want to add quick-fix buttons (e.g., "Add 30 min to weekday time")

---

## Summary of Impacts

### Quick Wins (Easy Implementation, High Impact)
- **#3**: Pre-filter Completed Tasks
- **#8**: Smart Default Rankings  
- **#11**: Precompute Total Essential Time

### Performance Optimizations (Medium Implementation, High Impact)
- **#1**: Cache Scheduling Results
- **#2**: Early Exit on Time Exhaustion
- **#4**: Min Heap for Dynamic Minimum Duration Tracking
- **#9**: Lazy Task Lookup Dictionary

### UX Enhancements (Higher Implementation, High User Value)
- **#6**: Hybrid Priority System (3-Tier + Batch Ranking)
- **#7**: Incremental Schedule Updates
- **#10**: Schedule Diff Highlighting

---

## Next Steps

1. Review each proposal and mark which ones to implement
2. Prioritize based on:
   - Implementation complexity
   - Expected user impact
   - Code maintainability
3. Create implementation plan with testing strategy for selected changes
4. Consider backward compatibility for data structure changes

