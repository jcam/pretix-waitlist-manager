from functools import wraps

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from pretix.control import context as control_context
from pretix.control import navigation as control_navigation

from .views import SECTION_IMPORT, SECTION_RANDOMIZE, SECTION_SEND


def _waitlist_management_item(request) -> dict:
    """Build the event-sidebar group for waitlist-management pages.

    Args:
        request: Current Django request with event context.
    Returns:
        A navigation item dict with child entries for send, import, and randomize.
    """
    match = request.resolver_match
    send_url = reverse(
        "control:event.orders.waitinglist",
        kwargs={
            "event": request.event.slug,
            "organizer": request.event.organizer.slug,
        },
    )
    import_url = reverse(
        "plugins:pretix_waitlist_manager:import_page",
        kwargs={
            "event": request.event.slug,
            "organizer": request.event.organizer.slug,
        },
    )
    randomize_url = reverse(
        "plugins:pretix_waitlist_manager:randomize_page",
        kwargs={
            "event": request.event.slug,
            "organizer": request.event.organizer.slug,
        },
    )
    children = [
        {
            "label": _("Send vouchers"),
            "url": send_url,
            "active": bool(match and match.namespace == "control" and "event.orders.waitinglist" in match.url_name),
        }
    ]
    if "event.orders:write" in getattr(request, "eventpermset", set()):
        children.extend(
            [
                {
                    "label": _("Import"),
                    "url": import_url,
                    "active": bool(
                        match
                        and match.namespace == "plugins:pretix_waitlist_manager"
                        and match.url_name in {"index", "import_page", "run_import", "import_preview"}
                    ),
                },
                {
                    "label": _("Randomize"),
                    "url": randomize_url,
                    "active": bool(
                        match
                        and match.namespace == "plugins:pretix_waitlist_manager"
                        and match.url_name in {"randomize_page", "run_randomize", "randomize_preview"}
                    ),
                },
            ]
        )
    return {
        "label": _("Waitlist Management"),
        "url": {
            SECTION_SEND: send_url,
            SECTION_IMPORT: import_url,
            SECTION_RANDOMIZE: randomize_url,
        }[
            SECTION_IMPORT
            if "event.orders:write" in getattr(request, "eventpermset", set())
            else SECTION_SEND
        ],
        "active": any(child["active"] for child in children),
        "icon": "users",
        "children": children,
    }


def _remove_orders_waitinglist(nav: list[dict], waitinglist_url: str) -> None:
    """Remove pretix's built-in waiting-list child from the Orders menu.

    Args:
        nav: Event navigation list returned by pretix.
        waitinglist_url: Canonical URL of pretix's waiting-list page.
    Returns:
        `None`. The navigation structure is mutated in place.
    """
    for item in nav:
        children = item.get("children")
        if not children:
            continue
        item["children"] = [
            child for child in children if child.get("url") != waitinglist_url
        ]


def patch_event_navigation() -> None:
    """Patch pretix's event navigation to add a waitlist-management group.

    Args:
        None.
    Returns:
        `None`. pretix navigation functions are wrapped in place.
    """
    if getattr(control_navigation.get_event_navigation, "_waitlist_manager_patched", False):
        return

    original_get_event_navigation = control_navigation.get_event_navigation

    @wraps(original_get_event_navigation)
    def patched_get_event_navigation(request):
        """Build event navigation and move waiting-list links into a new group.

        Args:
            request: Current Django request with event context.
        Returns:
            The patched event-navigation list.
        """
        nav = original_get_event_navigation(request)
        if "event.orders:read" not in getattr(request, "eventpermset", set()):
            return nav

        waitinglist_url = reverse(
            "control:event.orders.waitinglist",
            kwargs={
                "event": request.event.slug,
                "organizer": request.event.organizer.slug,
            },
        )
        _remove_orders_waitinglist(nav, waitinglist_url)
        manager_item = _waitlist_management_item(request)

        insert_at = len(nav)
        for index, item in enumerate(nav):
            if item.get("icon") == "shopping-cart":
                insert_at = index + 1
                break
        nav.insert(insert_at, manager_item)
        return nav

    patched_get_event_navigation._waitlist_manager_patched = True
    control_navigation.get_event_navigation = patched_get_event_navigation
    control_context.get_event_navigation = patched_get_event_navigation
