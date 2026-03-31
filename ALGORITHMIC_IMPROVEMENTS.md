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
- Cache invalidation: Clear cache when pets/tasks are modified
- Memory usage: Limit cache size (e.g., keep only last 5 schedules)
- Cache should be per-session (already handled by `st.session_state`)

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

## 4. Minimum Duration Check

### Problem
When remaining time is very low (e.g., 5 minutes left), the algorithm still iterates through all remaining optional tasks, even if the shortest task requires more time than available.

### Proposed Solution
Track the minimum task duration among unscheduled tasks and skip iteration when remaining time is less than this minimum.

### Implementation Details

**In `pawpal_system.py` - `Scheduler.generate_owner_schedule()`:**
```python
def generate_owner_schedule(self, owner: Owner, day_type: DayType | str) -> Dict[str, List[Task]]:
    # ... existing essential task scheduling ...
    
    # Gather optional tasks
    optional_entries: List[tuple[Pet, Task]] = []
    min_optional_duration = float('inf')
    
    for pet in pets:
        for task in pet.list_tasks():
            if (not task.is_essential) and task.is_selected_optional:
                optional_entries.append((pet, task))
                min_optional_duration = min(min_optional_duration, task.get_duration())
    
    # Early exit if no task can possibly fit
    if optional_entries and remaining_minutes < min_optional_duration:
        return schedule_by_pet
    
    # Sort and schedule optional tasks
    optional_entries.sort(...)
    
    for pet, task in optional_entries:
        duration = task.get_duration()
        if duration <= remaining_minutes:
            schedule_by_pet[pet.pet_name].append(task)
            remaining_minutes -= duration
        # Optional: update min_optional_duration dynamically for tighter bounds
```

### Benefits
- **Saves comparisons**: Avoids unnecessary iteration when no tasks can fit
- **Smart optimization**: Particularly useful for tight time budgets
- **Minimal overhead**: Single pass to compute minimum

### Considerations
- Most beneficial when task durations vary significantly
- Could be extended to track minimum duration dynamically (update after each scheduled task)
- Trade-off: adds one extra pass for minimum calculation, but saves iterations

---

## 6. Batch Rank Updates

### Problem
The current UI requires users to update task rankings one at a time. For pet owners with many optional tasks, this becomes tedious and requires multiple page refreshes.

### Proposed Solution
Implement a batch ranking interface that allows users to reorder multiple tasks at once, either through drag-and-drop or a table with editable rank columns.

### Implementation Details

**Option A: Editable Dataframe (Simpler)**
```python
# In app.py, replace the ranking section with:
if optional_tasks:
    st.markdown("**Optional Task Ranking (Edit ranks directly)**")
    
    # Create editable dataframe
    rank_data = []
    for task in optional_tasks:
        rank_data.append({
            "Task": task["task_name"],
            "Current Rank": task["optional_rank"] if task["optional_rank"] else "",
            "New Rank": task["optional_rank"] if task["optional_rank"] else 1
        })
    
    edited_df = st.data_editor(
        rank_data,
        column_config={
            "Task": st.column_config.TextColumn("Task", disabled=True),
            "Current Rank": st.column_config.NumberColumn("Current Rank", disabled=True),
            "New Rank": st.column_config.NumberColumn("New Rank", min_value=1, max_value=len(optional_tasks))
        },
        hide_index=True,
        use_container_width=True
    )
    
    if st.button("Apply All Ranks"):
        for i, task in enumerate(optional_tasks):
            new_rank = edited_df.iloc[i]["New Rank"]
            task["optional_rank"] = int(new_rank)
        st.success(f"Updated ranks for {len(optional_tasks)} tasks")
```

**Option B: Simple Reorder Interface**
```python
# Allow users to reorder tasks by moving them up/down
st.markdown("**Reorder Optional Tasks (1 = highest priority)**")
for idx, task in enumerate(optional_tasks):
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    with col1:
        st.write(f"{idx + 1}. {task['task_name']}")
    with col2:
        if idx > 0 and st.button("↑", key=f"up_{task['task_name']}"):
            # Swap with previous task
            optional_tasks[idx], optional_tasks[idx-1] = optional_tasks[idx-1], optional_tasks[idx]
            # Update ranks
            for i, t in enumerate(optional_tasks):
                t["optional_rank"] = i + 1
            st.rerun()
    with col3:
        if idx < len(optional_tasks) - 1 and st.button("↓", key=f"down_{task['task_name']}"):
            # Swap with next task
            optional_tasks[idx], optional_tasks[idx+1] = optional_tasks[idx+1], optional_tasks[idx]
            # Update ranks
            for i, t in enumerate(optional_tasks):
                t["optional_rank"] = i + 1
            st.rerun()
```

### Benefits
- **Faster workflow**: Update multiple rankings in one action
- **Less clicking**: Reduces repetitive form submissions
- **Better UX**: More intuitive for managing task priorities
- **Visual feedback**: Users see rankings relative to each other

### Considerations
- Streamlit's drag-and-drop support is limited (requires third-party components)
- Editable dataframe is simpler and works well for this use case
- Consider validation to prevent duplicate ranks

---

## 7. Incremental Schedule Updates

### Problem
When a user marks a task as completed during the day, the entire schedule must be regenerated from scratch to redistribute the freed time to other tasks.

### Proposed Solution
Implement incremental updates that:
1. Remove the completed task from the cached schedule
2. Recalculate freed time
3. Attempt to schedule additional optional tasks with the freed time
4. Only regenerate fully if needed

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

## 12. Task Priority Groups

### Problem
The current system has only two priority levels: essential (must do) and optional (nice to have). Real-world pet care often has more nuance (e.g., important but not critical tasks).

### Proposed Solution
Introduce priority groups/tiers within optional tasks:
- **High priority** (optional but important)
- **Medium priority** (helpful but flexible)
- **Low priority** (nice to have if time permits)

Tasks within the same priority group are then sub-ranked numerically.

### Implementation Details

**Update `Task` class in `pawpal_system.py`:**
```python
class TaskPriority(Enum):
    """Priority levels for optional tasks."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class Task:
    def __init__(
        self,
        task_name: str,
        duration_minutes: int,
        is_essential: bool = False,
        is_selected_optional: bool = False,
        optional_rank: Optional[int] = None,
        priority_group: str = "medium",  # New parameter
    ) -> None:
        # ... existing initialization ...
        self.priority_group = priority_group if not is_essential else None
    
    def set_priority_group(self, priority: str) -> None:
        """Set priority group for optional tasks."""
        if self.is_essential:
            raise ValueError("Essential tasks don't have priority groups")
        if priority not in ["high", "medium", "low"]:
            raise ValueError("Priority must be high, medium, or low")
        self.priority_group = priority
```

**Update scheduling logic to consider priority groups:**
```python
def get_selected_ranked_optional_tasks(self, tasks: List[Task]) -> List[Task]:
    """
    Return selected non-essential tasks ordered by priority group, then rank.
    
    Sort order:
    1. Priority group (high -> medium -> low)
    2. Optional rank within group
    3. Task name (tie-breaker)
    """
    priority_order = {"high": 1, "medium": 2, "low": 3}
    
    def rank_key(task: Task) -> tuple[int, int, str]:
        priority = priority_order.get(task.priority_group or "medium", 2)
        rank = task.optional_rank if task.optional_rank is not None else 10**9
        return (priority, rank, task.task_name.lower())
    
    filtered = [
        task
        for task in tasks
        if (not task.is_essential) and task.is_selected_optional
    ]
    return sorted(filtered, key=rank_key)
```

**Update UI in `app.py`:**
```python
with st.form("add_task_form"):
    task_name = st.text_input("Task name")
    col1, col2 = st.columns(2)
    with col1:
        duration_minutes = st.number_input(
            "Duration (minutes)", min_value=1, max_value=480, value=15
        )
    with col2:
        is_essential = st.checkbox("Essential task", value=True)
    
    # Add priority group selector for optional tasks
    if not is_essential:
        priority_group = st.selectbox(
            "Priority Level",
            options=["high", "medium", "low"],
            index=1,  # Default to medium
            help="High = important but not essential, Medium = helpful, Low = nice to have"
        )
    
    submit_task = st.form_submit_button("Add task")
```

**Display priority in task table:**
```python
def task_rows_for_pet(pet_data: dict) -> list[dict]:
    """Return a simple table-friendly view for one pet's tasks."""
    rows = []
    for task in pet_data["tasks"]:
        priority_display = ""
        if not task["is_essential"]:
            priority = task.get("priority_group", "medium")
            priority_icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            priority_display = f"{priority_icons.get(priority, '⚪')} {priority.title()}"
        
        rows.append(
            {
                "task": task["task_name"],
                "minutes": task["duration_minutes"],
                "essential": task["is_essential"],
                "priority": priority_display if not task["is_essential"] else "N/A",
                "rank": task.get("optional_rank", ""),
                "status": "completed" if task.get("is_completed", False) else "pending",
            }
        )
    return rows
```

### Benefits
- **More nuanced scheduling**: Better reflects real-world task priorities
- **Easier bulk management**: Group similar tasks without fine-grained ranking
- **User-friendly**: Many users find categories easier than numeric rankings
- **Flexible**: Can still use numeric ranks within each priority group

### Considerations
- More complex than binary essential/optional system
- May be overkill for users with few tasks
- Consider making this an optional "advanced" feature
- Requires UI changes to support priority selection/editing
- Backward compatibility: existing tasks default to "medium" priority

---

## Summary of Impacts

### Quick Wins (Easy Implementation, High Impact)
- **#3**: Pre-filter Completed Tasks
- **#8**: Smart Default Rankings  
- **#11**: Precompute Total Essential Time

### Performance Optimizations (Medium Implementation, High Impact)
- **#1**: Cache Scheduling Results
- **#2**: Early Exit on Time Exhaustion
- **#4**: Minimum Duration Check
- **#9**: Lazy Task Lookup Dictionary

### UX Enhancements (Higher Implementation, High User Value)
- **#6**: Batch Rank Updates
- **#7**: Incremental Schedule Updates
- **#10**: Schedule Diff Highlighting

### Advanced Features (Complex Implementation, Situational Value)
- **#12**: Task Priority Groups

---

## Next Steps

1. Review each proposal and mark which ones to implement
2. Prioritize based on:
   - Implementation complexity
   - Expected user impact
   - Code maintainability
3. Create implementation plan with testing strategy for selected changes
4. Consider backward compatibility for data structure changes

