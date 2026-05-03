from django.urls import re_path

from .views import (
    WaitlistImportPageView,
    WaitlistImportPreviewView,
    WaitlistImportRunView,
    WaitlistManagerView,
    WaitlistRandomizePageView,
    WaitlistRandomizePreviewView,
    WaitlistRandomizeRunView,
)

urlpatterns = [
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/waitlist-manager/$",
        WaitlistManagerView.as_view(),
        name="index",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/waitlist-manager/import/$",
        WaitlistImportPageView.as_view(),
        name="import_page",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/waitlist-manager/import-preview$",
        WaitlistImportPreviewView.as_view(),
        name="import_preview",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/waitlist-manager/import$",
        WaitlistImportRunView.as_view(),
        name="run_import",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/waitlist-manager/randomize/$",
        WaitlistRandomizePageView.as_view(),
        name="randomize_page",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/waitlist-manager/randomize-preview$",
        WaitlistRandomizePreviewView.as_view(),
        name="randomize_preview",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/waitlist-manager/randomize$",
        WaitlistRandomizeRunView.as_view(),
        name="run_randomize",
    ),
]
