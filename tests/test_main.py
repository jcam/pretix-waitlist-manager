from datetime import datetime, timedelta
from types import SimpleNamespace

from pretix_waitlist_manager.services import (
    WaitlistMembershipImporter,
    WaitlistRandomizer,
    WaitlistTarget,
    build_question_answer_choices,
    build_question_choices,
    build_target_product_choices,
    parse_target_choice,
)


class FakeProvider:
    def __init__(self):
        self.created_entries = []
        base = datetime(2026, 5, 1, 12, 0, 0)
        self.membership_created = base - timedelta(days=30)
        self.membership_fallback_created = base - timedelta(days=10)
        self.waitlist_entries = [
            SimpleNamespace(
                pk=1,
                email="two@example.org",
                name="Customer Two",
                locale="de",
                priority=0,
                created=base,
            ),
            SimpleNamespace(
                pk=2,
                email="wait@example.org",
                name="Waiting Person",
                locale="en",
                priority=0,
                created=base + timedelta(minutes=1),
            ),
            SimpleNamespace(
                pk=3,
                email="friend@example.org",
                name="Friend Person",
                locale="en",
                priority=0,
                created=base + timedelta(minutes=2),
            ),
        ]
        self.updated_priorities = {}
        self.paid_ticket_customer_ids = set()

    def get_subevent(self, event, subevent_id):
        assert event == "ev"
        assert subevent_id == 12
        return "subev"

    def list_memberships(self, organizer, membership_type_id, valid_for, include_testmode=False):
        assert organizer == "orga"
        assert membership_type_id == 7
        assert valid_for == "subev"
        assert include_testmode is False
        return [
            {
                "customer": {"identifier": "CUST1"},
                "granted_in": {"order": {"datetime": self.membership_created}},
                "date_start": self.membership_created + timedelta(days=1),
            },
            {
                "customer": {"identifier": "CUST2"},
                "granted_in": None,
                "date_start": self.membership_fallback_created,
            },
            {
                "customer": {"identifier": "CUST2"},
                "granted_in": {"order": {"datetime": self.membership_fallback_created + timedelta(days=5)}},
                "date_start": self.membership_fallback_created + timedelta(days=5),
            },
            {"customer": {"identifier": "CUST3"}},
        ]

    def get_matching_customer_ids(self, organizer, event, customer_ids, question_id, option_id):
        assert customer_ids == ["CUST1", "CUST2", "CUST3"]
        assert question_id == 10
        assert option_id == 21
        return {"CUST1", "CUST2"}

    def list_customers(self, organizer, customer_ids):
        return [
            {
                "identifier": customer_id,
                **{
                    "CUST1": {
                        "email": "one@example.org",
                        "name": "Customer One",
                        "locale": "en",
                    },
                    "CUST2": {
                        "email": "two@example.org",
                        "name": "Customer Two",
                        "locale": "de",
                    },
                    "CUST3": {
                        "email": "",
                        "name": "Customer Three",
                        "locale": "en",
                    },
                }[customer_id],
            }
            for customer_id in customer_ids
        ]

    def list_waiting_list_entries(self, organizer, event, item, variation=None, subevent=None):
        assert item == 5
        assert variation == 9
        assert subevent == 12
        return list(self.waitlist_entries)

    def count_waiting_list_entries(self, organizer, event, item, variation=None, subevent=None):
        return len(self.list_waiting_list_entries(organizer, event, item, variation, subevent))

    def waiting_list_import_statuses_by_email(self, organizer, event, item, variation=None, subevent=None):
        return {
            "two@example.org": "already_waiting",
        }

    def customer_ids_with_paid_tickets(self, organizer, event, customer_ids):
        return set(customer_ids).intersection(self.paid_ticket_customer_ids)

    def waiting_list_preview_page(self, organizer, event, item, variation=None, subevent=None, page=1, per_page=10):
        entries = self.list_waiting_list_entries(organizer, event, item, variation, subevent)
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        rows = [
            SimpleNamespace(
                email=entry.email,
                name=entry.name,
                locale=entry.locale,
                priority=entry.priority,
                created=entry.created,
            )
            for entry in entries[start_index:end_index]
        ]
        from pretix_waitlist_manager.service_helpers import build_preview_page
        return build_preview_page(rows, len(entries), page, per_page)

    def list_group_question_answers(self, organizer, event, question_id, emails=None):
        assert organizer == "orga"
        assert event == "ev"
        assert question_id == 42
        assert emails == ["friend@example.org", "two@example.org", "wait@example.org"]
        return [
            SimpleNamespace(
                answer="friend@example.org",
                orderposition=SimpleNamespace(
                    attendee_email=None,
                    order=SimpleNamespace(
                        email="wait@example.org",
                        customer=SimpleNamespace(email="wait@example.org"),
                    ),
                ),
            )
        ]

    def create_waiting_list_entry(self, organizer, event, payload, user=None):
        self.created_entries.append((payload, user))
        return payload

    def update_waiting_list_priorities(self, organizer, entries, assignments, user=None):
        self.updated_priorities = assignments.copy()
        for entry in entries:
            if entry.pk in assignments:
                entry.priority = assignments[entry.pk]
        return len(assignments)


def test_parse_helpers():
    assert parse_target_choice("5:9") == WaitlistTarget(item_id=5, variation_id=9)
    assert parse_target_choice("5:") == WaitlistTarget(item_id=5, variation_id=None)


def test_build_question_and_answer_choices():
    questions = [
        {
            "id": 10,
            "type": "C",
            "question": {"en": "Meal"},
            "options": [{"id": 21, "answer": {"en": "Vegan"}}],
        },
        {
            "id": 11,
            "type": "S",
            "question": {"en": "Comment"},
            "options": [],
        },
    ]
    assert build_question_choices(questions) == [
        ("", "No question filter"),
        ("10", "Meal"),
    ]
    assert build_question_answer_choices(questions) == {
        "": [("", "No answer filter")],
        "10": [("", "No answer filter"), ("21", "Vegan")],
    }


def test_build_question_choices_uses_only_answered_options():
    questions = [
        {
            "id": 10,
            "type": "M",
            "question": {"en": "Ticket access"},
            "options": [
                {"id": 21, "answer": {"en": "Standard"}},
                {"id": 22, "answer": {"en": "VIP"}},
            ],
        }
    ]

    assert build_question_choices(questions) == [
        ("", "No question filter"),
        ("10", "Ticket access"),
    ]
    assert build_question_answer_choices(questions) == {
        "": [("", "No answer filter")],
        "10": [
            ("", "No answer filter"),
            ("21", "Standard"),
            ("22", "VIP"),
        ],
    }


def test_build_target_product_choices():
    items = [
        {"id": 1, "name": {"en": "Ticket"}, "has_variations": False},
        {"id": 2, "name": {"en": "Shirt"}, "has_variations": True},
    ]
    variations_by_item = {
        2: [
            {"id": 6, "value": {"en": "M"}},
            {"id": 7, "value": {"en": "L"}},
        ]
    }
    assert build_target_product_choices(items, variations_by_item) == [
        ("1:", "Ticket"),
        ("2:6", "Shirt / M"),
        ("2:7", "Shirt / L"),
    ]


def test_importer_dry_run_and_actual_import():
    provider = FakeProvider()
    importer = WaitlistMembershipImporter(provider)

    preview = importer.run(
        organizer="orga",
        event="ev",
        membership_type_id=7,
        email_filter=None,
        question_id=10,
        option_id=21,
        target=WaitlistTarget(item_id=5, variation_id=9),
        subevent_id=12,
        exclude_paid_tickets=True,
        dry_run=True,
    )

    assert preview.total_memberships == 4
    assert preview.distinct_customers == 3
    assert preview.matched_customers == 2
    assert preview.existing_waitlist_entries == 3
    assert preview.added_count == 0
    assert [row.status for row in preview.rows] == ["would_add", "already_waiting"]

    actual = importer.run(
        organizer="orga",
        event="ev",
        membership_type_id=7,
        email_filter=None,
        question_id=10,
        option_id=21,
        target=WaitlistTarget(item_id=5, variation_id=9),
        subevent_id=12,
        exclude_paid_tickets=True,
        dry_run=False,
    )

    assert actual.added_count == 1
    assert provider.created_entries == [
        (
            {
                "customer": {
                    "identifier": "CUST1",
                    "email": "one@example.org",
                    "name": "Customer One",
                    "locale": "en",
                },
                "created": provider.membership_created,
                "email": "one@example.org",
                "item": 5,
                "variation": 9,
                "locale": "en",
                "subevent": 12,
                "name": "Customer One",
                "phone": None,
                "name_parts": {},
            },
            None,
        )
    ]


def test_importer_without_question_filter_imports_all_members():
    provider = FakeProvider()
    importer = WaitlistMembershipImporter(provider)

    result = importer.run(
        organizer="orga",
        event="ev",
        membership_type_id=7,
        email_filter=None,
        question_id=None,
        option_id=None,
        target=WaitlistTarget(item_id=5, variation_id=9),
        subevent_id=12,
        exclude_paid_tickets=True,
        dry_run=True,
    )

    assert result.matched_customers == 3
    assert [row.status for row in result.rows] == [
        "would_add",
        "already_waiting",
        "missing_email",
    ]


def test_importer_prefers_order_datetime_and_falls_back_to_membership_start():
    provider = FakeProvider()
    importer = WaitlistMembershipImporter(provider)

    created = importer._membership_created_by_customer(provider.list_memberships("orga", 7, "subev"))

    assert created["CUST1"] == provider.membership_created
    assert created["CUST2"] == provider.membership_fallback_created


def test_importer_email_filter_uses_case_insensitive_substring_match():
    provider = FakeProvider()
    importer = WaitlistMembershipImporter(provider)

    result = importer.run(
        organizer="orga",
        event="ev",
        membership_type_id=7,
        email_filter=" One@Ex ",
        question_id=None,
        option_id=None,
        target=WaitlistTarget(item_id=5, variation_id=9),
        subevent_id=12,
        exclude_paid_tickets=True,
        dry_run=True,
    )

    assert result.matched_customers == 1
    assert [row.email for row in result.rows] == ["one@example.org"]


def test_importer_blocks_paid_ticket_holders_when_enabled():
    provider = FakeProvider()
    provider.paid_ticket_customer_ids = {"CUST1"}
    importer = WaitlistMembershipImporter(provider)

    result = importer.run(
        organizer="orga",
        event="ev",
        membership_type_id=7,
        email_filter=None,
        question_id=None,
        option_id=None,
        target=WaitlistTarget(item_id=5, variation_id=9),
        subevent_id=12,
        exclude_paid_tickets=True,
        dry_run=True,
    )

    assert [row.status for row in result.rows] == [
        "has_paid_ticket",
        "already_waiting",
        "missing_email",
    ]


def test_import_preview_uses_samples_and_waitlist_rows():
    provider = FakeProvider()
    importer = WaitlistMembershipImporter(provider)

    preview = importer.preview(
        organizer="orga",
        event="ev",
        membership_type_id=7,
        email_filter=None,
        question_id=10,
        option_id=21,
        target=WaitlistTarget(item_id=5, variation_id=9),
        subevent_id=12,
        exclude_paid_tickets=True,
        sample_size=1,
    )

    assert preview.import_page.total == 2
    assert len(preview.import_page.rows) == 1
    assert preview.import_page.rows[0].status == "would_add"
    assert preview.current_waitlist_page.total == 3
    assert len(preview.current_waitlist_page.rows) == 1
    assert preview.current_waitlist_page.rows[0].email == "two@example.org"

    second_page = importer.preview(
        organizer="orga",
        event="ev",
        membership_type_id=7,
        email_filter=None,
        question_id=10,
        option_id=21,
        target=WaitlistTarget(item_id=5, variation_id=9),
        subevent_id=12,
        exclude_paid_tickets=True,
        sample_size=1,
        import_page=2,
        current_waitlist_page=2,
    )
    assert second_page.import_page.page == 2
    assert second_page.import_page.rows[0].status == "already_waiting"
    assert second_page.current_waitlist_page.page == 2
    assert second_page.current_waitlist_page.rows[0].email == "wait@example.org"


def test_randomizer_groups_related_entries_and_respects_seed():
    provider = FakeProvider()
    randomizer = WaitlistRandomizer(provider)

    preview = randomizer.preview(
        organizer="orga",
        event="ev",
        target=WaitlistTarget(item_id=5, variation_id=9),
        subevent_id=12,
        group_question_id=42,
        seed=1234,
    )

    assert preview.total_entries == 3
    assert preview.eligible_entries == 3
    assert preview.grouped_clusters == 1
    assert preview.grouped_entries == 2

    assert preview.before_page.rows[0].created is not None
    after_priorities = {row.email: row.priority for row in preview.after_page.rows}
    assert after_priorities["wait@example.org"] == after_priorities["friend@example.org"]

    paged_preview = randomizer.preview(
        organizer="orga",
        event="ev",
        target=WaitlistTarget(item_id=5, variation_id=9),
        subevent_id=12,
        group_question_id=42,
        seed=1234,
        sample_size=1,
        before_page=2,
        after_page=2,
    )
    assert paged_preview.before_page.page == 2
    assert paged_preview.after_page.page == 2

    result = randomizer.run(
        organizer="orga",
        event="ev",
        target=WaitlistTarget(item_id=5, variation_id=9),
        subevent_id=12,
        group_question_id=42,
        seed=1234,
    )

    assert result.updated_entries == 3
    assert provider.updated_priorities[2] == provider.updated_priorities[3]
