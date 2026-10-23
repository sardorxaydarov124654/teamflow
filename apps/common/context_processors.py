def unread_notifications(request):
    """
    Adds sidebar/header counters to every template:
      * unread_notification_count - bell badge
      * my_open_task_count        - "Tasks" badge in the sidebar
      * plan_usage                - small plan card at the bottom of the sidebar
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    context = {
        "unread_notification_count": user.notifications.filter(is_read=False).count(),
        "my_open_task_count": user.assigned_tasks.exclude(status="done").count(),
    }

    company = user.company
    if company is not None:
        context["plan_usage"] = {
            "plan": company.get_plan_display(),
            "plan_code": company.plan,
            "projects": company.projects.count(),
            "project_limit": company.get_project_limit(),
            "users": company.members.filter(is_active=True).count(),
            "user_limit": company.get_user_limit(),
        }
    return context
