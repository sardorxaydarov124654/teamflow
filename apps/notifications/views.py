from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Notification


@login_required
def notifications_list_view(request):
    notifications = Notification.objects.filter(user=request.user)
    show = request.GET.get("show", "all")
    if show == "unread":
        notifications = notifications.filter(is_read=False)
    return render(
        request,
        "notifications/list.html",
        {"notifications": notifications[:100], "show": show},
    )


@login_required
def notification_open_view(request, pk):
    """Mark a notification read and jump to the task it refers to (if any)."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    task_id = (notification.data or {}).get("task_id")
    if task_id:
        return redirect("tasks:detail", pk=task_id)
    return redirect("notifications:list")


@login_required
def notification_mark_read_view(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if request.method == "POST":
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return redirect("notifications:list")


@login_required
def notifications_mark_all_read_view(request):
    if request.method == "POST":
        updated = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        messages.success(request, f"Marked {updated} notification(s) as read.")
    return redirect("notifications:list")
