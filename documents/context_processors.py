from .models import is_sector_admin


def admin_panel_access(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"can_access_admin_panel": False}
    if user.is_staff or user.is_superuser:
        return {"can_access_admin_panel": True}
    return {"can_access_admin_panel": is_sector_admin(user)}
