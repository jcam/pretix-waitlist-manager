import json
from types import SimpleNamespace

from django.test import RequestFactory

from pretix_waitlist_manager.navigation import patch_event_navigation
from pretix_waitlist_manager.forms import WaitlistImportForm, WaitlistRandomizeForm
from pretix_waitlist_manager.service_helpers import build_preview_page
from pretix_waitlist_manager.service_types import (
    ImportPreviewResult,
    ImportResult,
    ImportRow,
    PreviewPage,
    RandomizationPreviewResult,
    RandomizationResult,
    WaitlistRow,
)
from pretix_waitlist_manager.views import (
    SECTION_IMPORT,
    SECTION_RANDOMIZE,
    WaitlistImportOptionsView,
    WaitlistImportPreviewView,
    WaitlistImportRunView,
    WaitlistManagerFormsMixin,
    WaitlistManagerView,
    WaitlistRandomizeOptionsView,
    WaitlistRandomizePreviewView,
    WaitlistRandomizeRunView,
)


def _request(method="get", path="/control/event/demo/preview/waitlist-manager/import/", data=None):
    rf = RequestFactory()
    request = getattr(rf, method.lower())(path, data=data or {})
    organizer = SimpleNamespace(slug="demo")
    request.organizer = organizer
    request.event = SimpleNamespace(
        slug="preview",
        organizer=organizer,
        has_subevents=False,
    )
    request.user = SimpleNamespace(is_authenticated=False, is_staff=False)
    request.eventpermset = {"event.orders:read", "event.orders:write"}
    return request


def _preview_page(rows, total=None, page=1, pages=1):
    total = len(rows) if total is None else total
    return PreviewPage(
        rows=rows,
        total=total,
        page=page,
        per_page=max(len(rows), 1),
        pages=pages,
        start=1 if total else 0,
        end=len(rows),
        has_previous=page > 1,
        has_next=page < pages,
        previous_page=page - 1 if page > 1 else None,
        next_page=page + 1 if page < pages else None,
    )


def _json(response):
    return json.loads(response.content)


class DummyProvider:
    def list_membership_types(self, organizer):
        return [{"id": 7, "name": {"en": "Gold"}}]

    def list_memberships(
        self, organizer, membership_type_id, valid_for, include_testmode=False
    ):
        assert membership_type_id == 7
        return [{"customer": {"identifier": "CUST1"}}]

    def list_answered_import_questions(self, organizer, event, customer_ids):
        if not customer_ids:
            return []
        assert customer_ids == ["CUST1"]
        return [
            {
                "id": 10,
                "type": "C",
                "question": {"en": "Meal"},
                "options": [{"id": 21, "answer": {"en": "Vegan"}}],
            }
        ]

    def list_group_questions(self, event):
        return [{"id": 42, "question": {"en": "Group emails"}}]

    def list_answered_group_questions(self, organizer, event, emails):
        return [{"id": 42, "question": {"en": "Group emails"}}] if emails else []

    def list_waitlist_items(self, event):
        return [SimpleNamespace(id=5, name={"en": "Target"}, has_variations=False)]

    def list_subevents(self, event):
        return []

    def list_variations(self, item):
        return []

    def list_waiting_list_entries(self, organizer, event, item, variation=None, subevent=None):
        return [SimpleNamespace(email="wait@example.org")]

    def count_waiting_list_entries(self, organizer, event, item, variation=None, subevent=None):
        return 1

    def waiting_list_import_statuses_by_email(self, organizer, event, item, variation=None, subevent=None):
        return {"wait@example.org": "already_waiting"}

    def customer_ids_with_paid_tickets(self, organizer, event, customer_ids):
        return set()

    def waiting_list_preview_page(self, organizer, event, item, variation=None, subevent=None, page=1, per_page=10):
        rows = [WaitlistRow(name="Queued", email="wait@example.org", locale="en", priority=0, created="2026-05-01 12:00")]
        return build_preview_page(rows, 1, page, per_page)


class MultiMembershipDummyProvider(DummyProvider):
    def list_membership_types(self, organizer):
        return [
            {"id": 7, "name": {"en": "Gold"}},
            {"id": 8, "name": {"en": "Prereg"}},
        ]

    def list_memberships(
        self, organizer, membership_type_id, valid_for, include_testmode=False
    ):
        if membership_type_id == 8:
            return [{"customer": {"identifier": "CUST1"}}]
        return []


def test_import_form_without_subevents_uses_placeholder():
    form = WaitlistImportForm(
        membership_type_choices=[("7", "Gold")],
        question_choices_by_membership={"7": [("10", "Meal")]},
        answer_choices_by_membership={"7": {"10": [("21", "Vegan")]}},
        target_choices=[("5:", "Target")],
        subevent_choices=[],
    )

    assert form.fields["subevent"].required is False
    assert form.fields["subevent"].choices == [("", "This event has no subevents")]
    assert form.fields["email"].required is False
    assert form.fields["exclude_paid_tickets"].choices == [("yes", "Yes"), ("no", "No")]
    assert form.fields["question"].choices == [("", "No question filter"), ("10", "Meal")]
    assert form.fields["answer"].choices == [("", "No answer filter")]


def test_import_form_uses_selected_membership_question_choices():
    form = WaitlistImportForm(
        data={
            "import-membership_type": "8",
            "import-email": "cust",
            "import-question": "20",
            "import-answer": "30",
            "import-target": "5:",
            "import-subevent": "",
        },
        prefix="import",
        membership_type_choices=[("7", "Gold"), ("8", "Silver")],
        question_choices_by_membership={
            "7": [("10", "Meal")],
            "8": [("20", "Shirt size")],
        },
        answer_choices_by_membership={
            "7": {"10": [("21", "Vegan")]},
            "8": {"20": [("30", "Large")]},
        },
        target_choices=[("5:", "Target")],
        subevent_choices=[],
    )

    assert form.fields["question"].choices == [
        ("", "No question filter"),
        ("20", "Shirt size"),
    ]
    assert form.fields["answer"].choices == [("", "No answer filter"), ("30", "Large")]
    assert form.is_valid() is True


def test_randomize_form_with_subevents_requires_selection():
    form = WaitlistRandomizeForm(
        target_choices=[("5:", "Target")],
        subevent_choices=[("11", "Morning")],
        group_question_choices_by_selection={
            "5:|11": [("", "No group question"), ("42", "Group emails")]
        },
    )

    assert form.fields["subevent"].required is True
    assert form.fields["subevent"].choices == [("11", "Morning")]
    assert form.fields["group_question"].choices[1] == ("42", "Group emails")
    assert form.fields["seed"].widget.attrs["data-ays-ignore"] == "1"


def test_randomize_form_uses_selected_waitlist_group_questions():
    form = WaitlistRandomizeForm(
        data={
            "randomize-target": "6:",
            "randomize-subevent": "",
            "randomize-group_question": "99",
        },
        prefix="randomize",
        target_choices=[("5:", "Target"), ("6:", "Other target")],
        subevent_choices=[],
        group_question_choices_by_selection={
            "5:|": [("", "No group question"), ("42", "Group emails")],
            "6:|": [("", "No group question"), ("99", "Cabin roster")],
        },
    )

    assert form.fields["group_question"].choices[1] == ("99", "Cabin roster")


def test_waitlist_manager_redirect_points_to_import_tab():
    view = WaitlistManagerView()
    view.request = _request()

    assert view.get_redirect_url().endswith("/control/event/demo/preview/waitlist-manager/import/")


def test_default_initials_choose_first_membership_with_questions(monkeypatch):
    request = _request()
    monkeypatch.setattr(
        "pretix_waitlist_manager.views.PretixDataProvider", MultiMembershipDummyProvider
    )

    view = WaitlistImportPreviewView()
    view.request = request
    choices = view._resource_choices()
    import_initial, randomize_initial = view._default_initials(choices)

    assert import_initial["membership_type"] == "7"
    assert import_initial["question"] == ""
    assert import_initial["answer"] == ""
    assert randomize_initial["target"] == "5:"


def test_import_run_view_dry_run_redirects_and_reports(monkeypatch):
    request = _request(
        method="post",
        data={
            "import-membership_type": "7",
            "import-email": "one@",
            "import-question": "10",
            "import-answer": "21",
            "import-target": "5:",
            "import-subevent": "",
            "import-exclude_paid_tickets": "yes",
            "import-dry_run": "on",
        },
    )
    messages = []
    calls = {}

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.PretixDataProvider", DummyProvider
    )
    monkeypatch.setattr(
        "pretix_waitlist_manager.views.messages.info",
        lambda request, message: messages.append(("info", str(message))),
    )

    class DummyImporter:
        def __init__(self, provider):
            calls["provider"] = provider

        def run(self, **kwargs):
            calls["kwargs"] = kwargs
            return ImportResult(1, 1, 1, 0, 0, [])

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.WaitlistMembershipImporter", DummyImporter
    )

    view = WaitlistImportRunView()
    view.request = request
    response = view.post(request)

    assert response.status_code == 302
    assert response["Location"].endswith("/control/event/demo/preview/waitlist-manager/import/")
    assert calls["kwargs"]["dry_run"] is True
    assert calls["kwargs"]["email_filter"] == "one@"
    assert calls["kwargs"]["exclude_paid_tickets"] is True
    assert calls["kwargs"]["question_id"] == 10
    assert calls["kwargs"]["option_id"] == 21
    assert messages == [("info", "Dry run completed. No waitlist entries were created.")]


def test_import_run_view_accepts_blank_question_filter(monkeypatch):
    request = _request(
        method="post",
        data={
            "import-membership_type": "7",
            "import-email": "",
            "import-question": "",
            "import-answer": "",
            "import-target": "5:",
            "import-subevent": "",
            "import-exclude_paid_tickets": "no",
            "import-dry_run": "on",
        },
    )
    calls = {}

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.PretixDataProvider", DummyProvider
    )
    monkeypatch.setattr(
        "pretix_waitlist_manager.views.messages.info",
        lambda request, message: None,
    )

    class DummyImporter:
        def __init__(self, provider):
            calls["provider"] = provider

        def run(self, **kwargs):
            calls["kwargs"] = kwargs
            return ImportResult(1, 1, 1, 0, 0, [])

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.WaitlistMembershipImporter", DummyImporter
    )

    view = WaitlistImportRunView()
    view.request = request
    response = view.post(request)

    assert response.status_code == 302
    assert calls["kwargs"]["email_filter"] == ""
    assert calls["kwargs"]["exclude_paid_tickets"] is False
    assert calls["kwargs"]["question_id"] is None
    assert calls["kwargs"]["option_id"] is None


def test_randomize_run_view_redirects_and_reports(monkeypatch):
    request = _request(
        method="post",
        data={
            "randomize-target": "5:",
            "randomize-subevent": "",
            "randomize-group_question": "42",
            "randomize-seed": "123",
        },
    )
    messages = []
    calls = {}

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.PretixDataProvider", DummyProvider
    )
    monkeypatch.setattr(
        "pretix_waitlist_manager.views.messages.success",
        lambda request, message: messages.append(("success", str(message))),
    )

    class DummyRandomizer:
        def __init__(self, provider):
            calls["provider"] = provider

        def run(self, **kwargs):
            calls["kwargs"] = kwargs
            return RandomizationResult(4, 4, 2, 1, 123)

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.WaitlistRandomizer", DummyRandomizer
    )

    view = WaitlistRandomizeRunView()
    view.request = request
    response = view.post(request)

    assert response.status_code == 302
    assert response["Location"].endswith("/control/event/demo/preview/waitlist-manager/randomize/")
    assert calls["kwargs"]["group_question_id"] == 42
    assert messages == [("success", "Randomization completed. 4 waitlist entries were updated.")]


def test_import_preview_view_returns_html_and_uses_page_params(monkeypatch):
    request = _request(
        data={
            "import-membership_type": "7",
            "import-email": "one@",
            "import-question": "10",
            "import-answer": "21",
            "import-target": "5:",
            "import-subevent": "",
            "import-exclude_paid_tickets": "yes",
            "import_page": "2",
            "current_waitlist_page": "3",
        }
    )
    calls = {}

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.PretixDataProvider", DummyProvider
    )

    class DummyImporter:
        def __init__(self, provider):
            calls["provider"] = provider

        def preview(self, **kwargs):
            calls["kwargs"] = kwargs
            return ImportPreviewResult(
                import_page=_preview_page(
                    [
                        ImportRow(
                            customer="CUST1",
                            email="one@example.org",
                            name="Customer One",
                            locale="en",
                            status="would_add",
                        )
                    ],
                    total=11,
                    page=2,
                    pages=2,
                ),
                current_waitlist_page=_preview_page(
                    [
                        WaitlistRow(
                            name="Queued",
                            email="queue@example.org",
                            locale="en",
                            priority=0,
                            created="2026-05-01 12:00",
                        )
                    ],
                    total=21,
                    page=3,
                    pages=3,
                ),
            )

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.WaitlistMembershipImporter", DummyImporter
    )

    view = WaitlistImportPreviewView()
    view.request = request
    response = view.get(request)
    payload = _json(response)

    assert response.status_code == 200
    assert calls["kwargs"]["email_filter"] == "one@"
    assert calls["kwargs"]["exclude_paid_tickets"] is True
    assert calls["kwargs"]["import_page"] == 2
    assert calls["kwargs"]["current_waitlist_page"] == 3
    assert payload["question_choices"] == [["", "No question filter"], ["10", "Meal"]]
    assert payload["answer_choices_by_question"]["10"] == [["", "No answer filter"], ["21", "Vegan"]]
    assert "Customer One" in payload["html"]
    assert "Page 2 of 2" in payload["html"]


def test_import_preview_view_accepts_blank_question_filter(monkeypatch):
    request = _request(
        data={
            "import-membership_type": "7",
            "import-email": "",
            "import-question": "",
            "import-answer": "",
            "import-target": "5:",
            "import-subevent": "",
            "import-exclude_paid_tickets": "no",
        }
    )
    calls = {}

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.PretixDataProvider", DummyProvider
    )

    class DummyImporter:
        def __init__(self, provider):
            calls["provider"] = provider

        def preview(self, **kwargs):
            calls["kwargs"] = kwargs
            return ImportPreviewResult(
                import_page=_preview_page([]),
                current_waitlist_page=_preview_page([]),
            )

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.WaitlistMembershipImporter", DummyImporter
    )

    view = WaitlistImportPreviewView()
    view.request = request
    response = view.get(request)
    payload = _json(response)

    assert response.status_code == 200
    assert calls["kwargs"]["email_filter"] == ""
    assert calls["kwargs"]["exclude_paid_tickets"] is False
    assert calls["kwargs"]["question_id"] is None
    assert calls["kwargs"]["option_id"] is None
    assert payload["question_choices"] == [["", "No question filter"], ["10", "Meal"]]
    assert "No matching customers for the current selection." in payload["html"]


def test_import_options_view_returns_membership_scoped_choices(monkeypatch):
    request = _request(
        path="/control/event/demo/preview/waitlist-manager/import-options",
        data={"membership_type": "7"},
    )

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.PretixDataProvider", DummyProvider
    )

    view = WaitlistImportOptionsView()
    view.request = request
    payload = _json(view.get(request))

    assert payload["question_choices"] == [["", "No question filter"], ["10", "Meal"]]
    assert payload["answer_choices_by_question"] == {
        "": [["", "No answer filter"]],
        "10": [["", "No answer filter"], ["21", "Vegan"]],
    }


def test_randomize_preview_view_returns_error_for_invalid_form(monkeypatch):
    request = _request(
        data={
            "randomize-subevent": "",
        }
    )
    monkeypatch.setattr(
        "pretix_waitlist_manager.views.PretixDataProvider", DummyProvider
    )

    view = WaitlistRandomizePreviewView()
    view.request = request
    response = view.get(request)
    payload = _json(response)

    assert response.status_code == 200
    assert payload["seed"] is None
    assert "group_question_choices" not in payload
    assert "Preview could not be loaded for the current selection." in payload["html"]


def test_randomize_preview_view_returns_seed_and_page_params(monkeypatch):
    request = _request(
        data={
            "randomize-target": "5:",
            "randomize-subevent": "",
            "randomize-group_question": "42",
            "randomize-seed": "987",
            "before_page": "2",
            "after_page": "4",
        }
    )
    calls = {}

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.PretixDataProvider", DummyProvider
    )

    class DummyRandomizer:
        def __init__(self, provider):
            calls["provider"] = provider

        def preview(self, **kwargs):
            calls["kwargs"] = kwargs
            return RandomizationPreviewResult(
                before_page=_preview_page(
                    [
                        WaitlistRow(
                            name="Before",
                            email="before@example.org",
                            locale="en",
                            priority=1,
                            created="2026-05-01 12:00",
                        )
                    ],
                    total=12,
                    page=2,
                    pages=3,
                ),
                after_page=_preview_page(
                    [
                        WaitlistRow(
                            name="After",
                            email="after@example.org",
                            locale="en",
                            priority=999,
                            created="2026-05-01 12:00",
                        )
                    ],
                    total=12,
                    page=3,
                    pages=3,
                ),
                total_entries=12,
                eligible_entries=9,
                grouped_entries=4,
                grouped_clusters=2,
                seed=987,
            )

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.WaitlistRandomizer", DummyRandomizer
    )

    view = WaitlistRandomizePreviewView()
    view.request = request
    response = view.get(request)
    payload = _json(response)

    assert calls["kwargs"]["before_page"] == 2
    assert calls["kwargs"]["after_page"] == 4
    assert payload["seed"] == 987
    assert payload["group_question_choices"] == [
        ["", "No group question"],
        ["42", "Group emails"],
    ]
    assert "Preview seed: 987" in payload["html"]
    assert "Registered" in payload["html"]


def test_randomize_options_view_returns_selection_scoped_group_questions(monkeypatch):
    request = _request(
        path="/control/event/demo/preview/waitlist-manager/randomize-options",
        data={"target": "5:", "subevent": ""},
    )

    monkeypatch.setattr(
        "pretix_waitlist_manager.views.PretixDataProvider", DummyProvider
    )

    view = WaitlistRandomizeOptionsView()
    view.request = request
    payload = _json(view.get(request))

    assert payload["group_question_choices"] == [
        ["", "No group question"],
        ["42", "Group emails"],
    ]


def test_patch_event_navigation_moves_waitinglist_out_of_orders(monkeypatch):
    import pretix.control.context as context_module
    import pretix.control.navigation as navigation_module

    waitinglist_url = "/control/event/demo/preview/waitinglist/"
    request = _request(path=waitinglist_url)
    request.resolver_match = SimpleNamespace(
        namespace="control",
        url_name="event.orders.waitinglist",
    )

    original_nav = [
        {
            "label": "Orders",
            "url": "/control/event/demo/preview/orders/",
            "icon": "shopping-cart",
            "children": [
                {"label": "Overview", "url": "/control/event/demo/preview/orders/", "active": False},
                {"label": "Waiting list", "url": waitinglist_url, "active": True},
            ],
        },
        {"label": "Vouchers", "url": "/control/event/demo/preview/vouchers/", "children": []},
    ]

    monkeypatch.setattr(navigation_module, "get_event_navigation", lambda request: list(original_nav))
    monkeypatch.setattr(context_module, "get_event_navigation", lambda request: list(original_nav))

    patch_event_navigation()
    patched_nav = navigation_module.get_event_navigation(request)

    orders_item = patched_nav[0]
    manager_item = patched_nav[1]

    assert all(child["url"] != waitinglist_url for child in orders_item["children"])
    assert manager_item["label"] == "Waitlist Management"
    assert manager_item["active"] is True
    assert [child["label"] for child in manager_item["children"]] == [
        "Send vouchers",
        "Import",
        "Randomize",
    ]
    assert manager_item["children"][0]["url"] == waitinglist_url
    assert context_module.get_event_navigation is navigation_module.get_event_navigation
