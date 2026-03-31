from pawpal_system import *


def main():

    try:
        owner1 = Owner(
            owner_name="Alice",
            weekday_available_windows=[(480, 540)],
            weekend_available_windows=[(600, 720)],
        )
        task1 = Task(task_name="Feed Fluffy", duration_minutes=15, is_essential=True)
        task2 = Task(task_name="Walk Spot", duration_minutes=30, is_essential=True)
        task3 = Task(
            task_name="Groom Fluffy",
            duration_minutes=20,
            is_essential=False,
            optional_rank=1,
            is_selected_optional=True,
        )
        pet1 = Pet(pet_name="Fluffy", tasks=[task1, task3])
        pet2 = Pet(pet_name="Spot", tasks=[task2])

        owner1.add_pet(pet1)
        owner1.add_pet(pet2)

        scheduler = Scheduler()
        result = scheduler.generate_owner_schedule(
            owner=owner1, day_type=DayType.WEEKDAY
        )

        for pet_name, tasks in result.scheduled_by_pet.items():
            print(f"{pet_name} schedule:")
            if not tasks:
                print("  No tasks scheduled")
                continue
            for task in tasks:
                print(
                    f"  - {task.task.task_name} "
                    f"({task.start_time}-{task.end_time}, {task.task.duration_minutes} min)"
                )

        for pet_name, tasks in result.unscheduled_by_pet.items():
            if not tasks:
                continue
            print(f"{pet_name} unscheduled:")
            for item in tasks:
                print(f"  - {item.task.task_name}: {item.reason}")

    except (ValueError, TypeError) as e:
        print(f"Error: {e}")


main()
