import hashlib
import json
from datetime import time

import streamlit as st

from pawpal_system import DayType, Owner, Pet, Scheduler, Task


def to_minute_of_day(value: time) -> int:
    """Convert a time object into minutes-from-midnight."""
    return int(value.hour) * 60 + int(value.minute)


def from_minute_of_day(minute: int) -> time:
    """Convert minutes-from-midnight into a time object."""
    return time(hour=(minute // 60), minute=(minute % 60))


def format_window(window: tuple[int, int]) -> str:
    """Format one availability window for display."""
    start, end = window
    return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"


def normalize_windows(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort and merge overlapping/adjacent windows for UI state."""
    if not windows:
        return []
    sorted_windows = sorted(windows, key=lambda item: (item[0], item[1]))
    merged = [sorted_windows[0]]
    for start, end in sorted_windows[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def windows_total_minutes(windows: list[tuple[int, int]]) -> int:
    """Return total minutes in a normalized windows list."""
    return sum(end - start for start, end in windows)


def compute_state_hash() -> str:
    """
    Generate hash of current scheduling state for caching.
    #1: Cache Scheduling Results
    """
    # Extract only serializable data for hashing
    pets_data = {}
    for pet_name, pet_info in st.session_state.pets.items():
        pets_data[pet_name] = {
            "tasks": [
                {
                    "name": t["task_name"],
                    "duration": t["duration_minutes"],
                    "essential": t["is_essential"],
                    "rank": t.get("optional_rank"),
                    "completed": t.get("is_completed", False),
                }
                for t in pet_info["tasks"]
            ]
        }

    state = {
        "owner": st.session_state.owner_name,
        "weekday_windows": st.session_state.weekday_available_windows,
        "weekend_windows": st.session_state.weekend_available_windows,
        "pets": pets_data,
    }
    return hashlib.md5(json.dumps(state, sort_keys=True).encode()).hexdigest()


def init_state() -> None:
    """Initialize persistent UI state containers once."""
    if "owner_name" not in st.session_state:
        st.session_state.owner_name = "Jordan"
    if "weekday_available_windows" not in st.session_state:
        st.session_state.weekday_available_windows = [(540, 600)]
    if "weekend_available_windows" not in st.session_state:
        st.session_state.weekend_available_windows = [(600, 720)]
    if "pets" not in st.session_state:
        st.session_state.pets = {}
    if "last_schedule" not in st.session_state:
        st.session_state.last_schedule = None
    if "last_unscheduled" not in st.session_state:
        st.session_state.last_unscheduled = None
    if "last_day_type" not in st.session_state:
        st.session_state.last_day_type = DayType.WEEKDAY.value
    # #1: Cache for schedules
    if "schedule_cache" not in st.session_state:
        st.session_state.schedule_cache = {}
    # #10: Previous schedule for diff highlighting
    if "previous_schedule" not in st.session_state:
        st.session_state.previous_schedule = None
    if "window_editor_day" not in st.session_state:
        st.session_state.window_editor_day = DayType.WEEKDAY.value


def calculate_essential_time() -> tuple[int, int]:
    """
    Return total essential task duration for (weekday, weekend).
    #11: Precompute Total Essential Time
    Runs on every Streamlit page rerun (automatically updates).
    """
    weekday_essential = 0
    weekend_essential = 0

    for pet_data in st.session_state.pets.values():
        for task in pet_data["tasks"]:
            if task["is_essential"] and not task.get("is_completed", False):
                duration = int(task["duration_minutes"])
                weekday_essential += duration
                weekend_essential += duration

    return weekday_essential, weekend_essential


def calculate_capacity_minutes() -> tuple[int, int]:
    """Return total available minutes from weekday/weekend windows."""
    weekday_capacity = windows_total_minutes(st.session_state.weekday_available_windows)
    weekend_capacity = windows_total_minutes(st.session_state.weekend_available_windows)
    return weekday_capacity, weekend_capacity


def build_owner_from_state() -> Owner:
    """Create runtime Owner/Pet/Task objects from session state."""
    owner = Owner(
        owner_name=st.session_state.owner_name,
        weekday_available_windows=list(st.session_state.weekday_available_windows),
        weekend_available_windows=list(st.session_state.weekend_available_windows),
    )

    for pet_name, pet_data in st.session_state.pets.items():
        pet = Pet(pet_name=pet_name)
        for task_data in pet_data["tasks"]:
            task = Task(
                task_name=task_data["task_name"],
                duration_minutes=int(task_data["duration_minutes"]),
                is_essential=bool(task_data["is_essential"]),
                is_selected_optional=bool(task_data["is_selected_optional"]),
                optional_rank=task_data["optional_rank"],
            )
            if bool(task_data.get("is_completed", False)):
                task.mark_completed()
            pet.add_task(task)
        owner.add_pet(pet)

    return owner


def task_rows_for_pet(pet_data: dict) -> list[dict]:
    """Return a simple table-friendly view for one pet's tasks."""
    rows = []
    for task in pet_data["tasks"]:
        rows.append(
            {
                "task": task["task_name"],
                "minutes": task["duration_minutes"],
                "essential": task["is_essential"],
                "selected_optional": task["is_selected_optional"],
                "optional_rank": task["optional_rank"],
                "status": "completed" if task.get("is_completed", False) else "pending",
            }
        )
    return rows


st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")
init_state()

st.title("PawPal+")
st.caption(
    "Owner-driven scheduling across all pets: essential tasks first, then ranked optional tasks."
)

st.subheader("1) Owner Setup")
with st.form("owner_name_form"):
    owner_name = st.text_input("Owner name", value=st.session_state.owner_name)
    if st.form_submit_button("Save owner profile"):
        clean_name = (owner_name or "").strip()
        if not clean_name:
            st.error("Owner name cannot be empty")
        else:
            st.session_state.owner_name = clean_name
            st.success("Owner profile saved")

st.markdown("Availability windows")
editor_day = st.radio(
    "Wizard step 1: Choose day template",
    options=[DayType.WEEKDAY.value, DayType.WEEKEND.value],
    index=0 if st.session_state.window_editor_day == DayType.WEEKDAY.value else 1,
    horizontal=True,
)
st.session_state.window_editor_day = editor_day

selected_key = (
    "weekday_available_windows"
    if editor_day == DayType.WEEKDAY.value
    else "weekend_available_windows"
)

with st.form(f"add_window_form_{editor_day}"):
    st.caption("Wizard step 2: Add one available time window")
    col1, col2 = st.columns(2)
    with col1:
        start_time = st.time_input(
            "Start",
            value=time(9, 0),
            step=900,
            key=f"start_{editor_day}",
        )
    with col2:
        end_time = st.time_input(
            "End",
            value=time(10, 0),
            step=900,
            key=f"end_{editor_day}",
        )
    if st.form_submit_button("Add available window"):
        start_minute = to_minute_of_day(start_time)
        end_minute = to_minute_of_day(end_time)
        if end_minute <= start_minute:
            st.error("End time must be after start time")
        else:
            windows = list(st.session_state[selected_key])
            windows.append((start_minute, end_minute))
            st.session_state[selected_key] = normalize_windows(windows)
            st.success("Window added")

current_windows = st.session_state[selected_key]
if current_windows:
    st.caption("Wizard step 3: Review and manage current windows")
    st.write(", ".join(format_window(window) for window in current_windows))
    remove_choice = st.selectbox(
        "Remove a window",
        options=["(none)"] + [format_window(window) for window in current_windows],
        key=f"remove_window_{editor_day}",
    )
    if st.button("Remove selected window", disabled=(remove_choice == "(none)")):
        st.session_state[selected_key] = [
            window
            for window in current_windows
            if format_window(window) != remove_choice
        ]
        st.success("Window removed")
else:
    st.info("No windows defined yet for this day type.")

weekday_capacity, weekend_capacity = calculate_capacity_minutes()
summary_col1, summary_col2 = st.columns(2)
with summary_col1:
    st.metric("Weekday available", f"{weekday_capacity} min")
with summary_col2:
    st.metric("Weekend available", f"{weekend_capacity} min")

st.divider()
st.subheader("2) Pet Management")
col_add, col_remove = st.columns(2)

with col_add:
    with st.form("add_pet_form"):
        new_pet_name = st.text_input("New pet name")
        if st.form_submit_button("Add pet"):
            name = new_pet_name.strip()
            if not name:
                st.error("Pet name cannot be empty")
            elif name.lower() in {p.lower() for p in st.session_state.pets.keys()}:
                st.error("A pet with that name already exists")
            else:
                st.session_state.pets[name] = {"tasks": []}
                st.success(f"Added pet: {name}")

with col_remove:
    pet_names = list(st.session_state.pets.keys())
    remove_target = st.selectbox("Remove pet", options=["(none)"] + pet_names)
    if st.button("Remove selected pet", disabled=(remove_target == "(none)")):
        st.session_state.pets.pop(remove_target, None)
        st.success(f"Removed pet: {remove_target}")

if not st.session_state.pets:
    st.info("Add at least one pet to continue.")
else:
    st.divider()
    st.subheader("3) Task Management")

    selected_pet_for_tasks = st.selectbox(
        "Select pet", options=list(st.session_state.pets.keys())
    )
    selected_pet_data = st.session_state.pets[selected_pet_for_tasks]

    with st.form("add_task_form"):
        task_name = st.text_input("Task name")
        col1, col2 = st.columns(2)
        with col1:
            duration_minutes = st.number_input(
                "Duration (minutes)", min_value=1, max_value=480, value=15
            )
        with col2:
            is_essential = st.checkbox("Essential task", value=True)
        submit_task = st.form_submit_button("Add task")

        if submit_task:
            clean_name = task_name.strip()
            if not clean_name:
                st.error("Task name cannot be empty")
            elif clean_name.lower() in {
                t["task_name"].lower() for t in selected_pet_data["tasks"]
            }:
                st.error("A task with that name already exists for this pet")
            else:
                selected_pet_data["tasks"].append(
                    {
                        "task_name": clean_name,
                        "duration_minutes": int(duration_minutes),
                        "is_essential": bool(is_essential),
                        "is_selected_optional": not bool(is_essential),
                        "optional_rank": None,
                        "is_completed": False,
                    }
                )
                st.success(f"Added task '{clean_name}' to {selected_pet_for_tasks}")

    st.markdown("Current tasks")
    rows = task_rows_for_pet(selected_pet_data)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)

        optional_tasks = [
            t for t in selected_pet_data["tasks"] if not t["is_essential"]
        ]
        st.markdown("Optional Task Ranking")
        if optional_tasks:
            rank_col1, rank_col2, rank_col3 = st.columns(3)
            with rank_col1:
                rank_target = st.selectbox(
                    "Optional task",
                    options=[t["task_name"] for t in optional_tasks],
                    key=f"rank_target_{selected_pet_for_tasks}",
                )
            with rank_col2:
                rank_options = list(range(1, len(optional_tasks) + 1))
                current_rank = next(
                    (
                        t["optional_rank"]
                        for t in optional_tasks
                        if t["task_name"] == rank_target
                    ),
                    None,
                )
                default_index = 0
                if current_rank in rank_options:
                    default_index = rank_options.index(current_rank)

                rank_value = st.selectbox(
                    "Set rank (1 = highest)",
                    options=rank_options,
                    index=default_index,
                    key=f"rank_value_{selected_pet_for_tasks}",
                )
            with rank_col3:
                if st.button("Apply rank", key=f"apply_rank_{selected_pet_for_tasks}"):
                    for task in selected_pet_data["tasks"]:
                        if (
                            task["task_name"] == rank_target
                            and not task["is_essential"]
                        ):
                            task["optional_rank"] = int(rank_value)
                            break
                    st.success(f"Rank for '{rank_target}' set to {int(rank_value)}")
        else:
            st.caption(
                "No non-essential tasks yet. Add some tasks and uncheck Essential."
            )

        task_names = [t["task_name"] for t in selected_pet_data["tasks"]]
        action_col1, action_col2, action_col3 = st.columns(3)
        with action_col1:
            completion_target = st.selectbox("Task status target", options=task_names)
            if st.button("Mark completed"):
                for task in selected_pet_data["tasks"]:
                    if task["task_name"] == completion_target:
                        task["is_completed"] = True
                        break
                st.success(f"Marked '{completion_target}' as completed")
        with action_col2:
            reopen_target = st.selectbox("Reopen task", options=task_names)
            if st.button("Mark pending"):
                for task in selected_pet_data["tasks"]:
                    if task["task_name"] == reopen_target:
                        task["is_completed"] = False
                        break
                st.success(f"Marked '{reopen_target}' as pending")
        with action_col3:
            delete_target = st.selectbox("Remove task", options=task_names)
            if st.button("Delete task"):
                selected_pet_data["tasks"] = [
                    t
                    for t in selected_pet_data["tasks"]
                    if t["task_name"] != delete_target
                ]
                st.success(f"Deleted task '{delete_target}'")
    else:
        st.info("No tasks for this pet yet.")

    st.divider()
    st.subheader("4) Generate Shared-Time Schedule")

    weekday_essential, weekend_essential = calculate_essential_time()
    weekday_capacity, weekend_capacity = calculate_capacity_minutes()

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Weekday Essential Tasks", f"{weekday_essential} min")
        if weekday_essential > weekday_capacity:
            st.error(
                f"Exceeds available time by {weekday_essential - weekday_capacity} min"
            )
        else:
            remaining = weekday_capacity - weekday_essential
            st.success(f"{remaining} min available after essentials")

    with col2:
        st.metric("Weekend Essential Tasks", f"{weekend_essential} min")
        if weekend_essential > weekend_capacity:
            st.error(
                f"Exceeds available time by {weekend_essential - weekend_capacity} min"
            )
        else:
            remaining = weekend_capacity - weekend_essential
            st.success(f"{remaining} min available after essentials")

    day_choice = st.radio(
        "Day type",
        options=[DayType.WEEKDAY.value, DayType.WEEKEND.value],
        index=0 if st.session_state.last_day_type == DayType.WEEKDAY.value else 1,
        horizontal=True,
    )

    if st.button("Generate owner schedule"):
        try:
            cache_key = f"{compute_state_hash()}_{day_choice}"

            if cache_key in st.session_state.schedule_cache:
                schedule_result = st.session_state.schedule_cache[cache_key]
                st.session_state.previous_schedule = st.session_state.last_schedule
                st.session_state.last_schedule = schedule_result.scheduled_by_pet
                st.session_state.last_unscheduled = schedule_result.unscheduled_by_pet
                st.session_state.last_day_type = day_choice
                st.success("Schedule retrieved from cache")
            else:
                owner_model = build_owner_from_state()
                scheduler = Scheduler()
                schedule_result = scheduler.generate_owner_schedule(
                    owner_model, day_choice
                )

                st.session_state.schedule_cache[cache_key] = schedule_result

                st.session_state.previous_schedule = st.session_state.last_schedule
                st.session_state.last_schedule = schedule_result.scheduled_by_pet
                st.session_state.last_unscheduled = schedule_result.unscheduled_by_pet
                st.session_state.last_day_type = day_choice

                if len(st.session_state.schedule_cache) > 5:
                    oldest_key = next(iter(st.session_state.schedule_cache))
                    st.session_state.schedule_cache.pop(oldest_key)

                st.success("Schedule generated")
        except ValueError as exc:
            st.error(f"Could not generate schedule: {exc}")

    if st.session_state.last_schedule is not None:
        st.markdown("Generated schedule")
        day_capacity = (
            weekday_capacity
            if st.session_state.last_day_type == DayType.WEEKDAY.value
            else weekend_capacity
        )

        added_tasks = {}
        removed_tasks = {}

        if st.session_state.previous_schedule is not None:
            prev = st.session_state.previous_schedule
            curr = st.session_state.last_schedule

            for pet_name in curr.keys():
                prev_task_names = {t.task.task_name for t in prev.get(pet_name, [])}
                curr_task_names = {t.task.task_name for t in curr.get(pet_name, [])}

                added_tasks[pet_name] = curr_task_names - prev_task_names
                removed_tasks[pet_name] = prev_task_names - curr_task_names

        used_minutes = 0
        for pet_name, tasks in st.session_state.last_schedule.items():
            with st.expander(f"{pet_name} schedule", expanded=True):
                if not tasks:
                    st.write("No tasks scheduled")
                    continue
                pet_rows = []
                for task in tasks:
                    used_minutes += task.task.get_duration()
                    row = {
                        "task": task.task.task_name,
                        "start": task.start_time,
                        "end": task.end_time,
                        "minutes": task.task.get_duration(),
                        "essential": task.task.is_essential,
                        "optional_rank": task.task.optional_rank,
                        "status": task.task.get_status(),
                    }

                    if task.task.task_name in added_tasks.get(pet_name, set()):
                        row["change"] = "Added"
                    else:
                        row["change"] = "Same"

                    pet_rows.append(row)
                st.dataframe(pet_rows, use_container_width=True, hide_index=True)

                unscheduled_items = (
                    st.session_state.last_unscheduled.get(pet_name, [])
                    if st.session_state.last_unscheduled
                    else []
                )
                if unscheduled_items:
                    unscheduled_rows = [
                        {
                            "task": item.task.task_name,
                            "minutes": item.task.get_duration(),
                            "essential": item.task.is_essential,
                            "reason": item.reason,
                        }
                        for item in unscheduled_items
                    ]
                    st.markdown("Unscheduled tasks")
                    st.dataframe(
                        unscheduled_rows, use_container_width=True, hide_index=True
                    )

        total_removed = sum(len(tasks) for tasks in removed_tasks.values())
        if total_removed > 0:
            with st.expander(f"{total_removed} task(s) removed from previous schedule"):
                for pet_name, task_names in removed_tasks.items():
                    if task_names:
                        st.write(f"**{pet_name}**: {', '.join(task_names)}")

        remaining_minutes = max(0, int(day_capacity) - int(used_minutes))
        st.info(
            f"Total available: {day_capacity} min | Used: {used_minutes} min | Remaining: {remaining_minutes} min"
        )
