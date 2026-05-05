from typing import Any

from django.db.models import Prefetch, Q
from django_scopes import scope

from pretix.base.models import (
    Customer,
    Item,
    Membership,
    MembershipType,
    Order,
    OrderPosition,
    Question,
    QuestionAnswer,
    QuestionOption,
    SubEvent,
    WaitingListEntry,
)
from .service_helpers import build_preview_page, build_waitlist_rows


class PretixDataProvider:
    """Encapsulate all direct pretix model reads and writes for the plugin."""

    def list_membership_types(self, organizer) -> list[MembershipType]:
        """List membership types for one organizer.

        Args:
            organizer: Organizer whose membership types should be loaded.
        Returns:
            An ordered list of `MembershipType` objects.
        """
        with scope(organizer=organizer):
            return list(organizer.membership_types.all().order_by("id"))

    def list_questions(self, event) -> list[Question]:
        """List choice-based questions that can filter imports.

        Args:
            event: Event whose questions should be loaded.
        Returns:
            An ordered list of eligible `Question` objects.
        """
        with scope(organizer=event.organizer):
            return list(
                event.questions.filter(
                    type__in=[Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE]
                )
                .prefetch_related("options")
                .order_by("position", "id")
            )

    def list_answered_import_questions(
        self,
        organizer,
        event,
        customer_ids: list[str],
    ) -> list[Question]:
        """List choice questions answered by a specific customer cohort.

        Args:
            organizer: Organizer owning the scoped query.
            event: Event whose questions and answers should be searched.
            customer_ids: Customer identifiers in the selected membership cohort.
        Returns:
            Choice questions with only the answer options used by that cohort.
        """
        if not customer_ids:
            return []

        with scope(organizer=organizer):
            answered_options = QuestionOption.objects.filter(
                answers__question__event=event,
                answers__orderposition__order__event=event,
                answers__orderposition__canceled=False,
                answers__orderposition__order__customer__identifier__in=customer_ids,
            ).distinct().order_by("position", "id")
            return list(
                Question.objects.filter(
                    event=event,
                    type__in=[Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE],
                    answers__orderposition__order__event=event,
                    answers__orderposition__canceled=False,
                    answers__orderposition__order__customer__identifier__in=customer_ids,
                )
                .distinct()
                .prefetch_related(Prefetch("options", queryset=answered_options))
                .order_by("position", "id")
            )

    def list_group_questions(self, event) -> list[Question]:
        """List text-based questions that can define grouping rules.

        Args:
            event: Event whose questions should be loaded.
        Returns:
            An ordered list of eligible `Question` objects.
        """
        with scope(organizer=event.organizer):
            return list(
                event.questions.filter(
                    type__in=[Question.TYPE_STRING, Question.TYPE_TEXT]
                ).order_by("position", "id")
            )

    def list_answered_group_questions(
        self,
        organizer,
        event,
        emails: list[str],
    ) -> list[Question]:
        """List text questions answered by people on the selected waitlist.

        Args:
            organizer: Organizer owning the scoped query.
            event: Event whose order answers should be searched.
            emails: Waitlist-entry emails relevant to the current selection.
        Returns:
            Text questions with at least one non-empty answer from the cohort.
        """
        if not emails:
            return []

        with scope(organizer=organizer):
            return list(
                Question.objects.filter(
                    event=event,
                    type__in=[Question.TYPE_STRING, Question.TYPE_TEXT],
                    answers__orderposition__order__event=event,
                    answers__orderposition__canceled=False,
                    answers__answer__gt="",
                )
                .filter(
                    Q(answers__orderposition__attendee_email__in=emails)
                    | Q(answers__orderposition__order__customer__email__in=emails)
                    | Q(answers__orderposition__order__email__in=emails)
                )
                .distinct()
                .order_by("position", "id")
            )

    def list_waitlist_items(self, event) -> list[Item]:
        """List waitlist-enabled items for one event.

        Args:
            event: Event whose items should be loaded.
        Returns:
            An ordered list of `Item` objects.
        """
        with scope(organizer=event.organizer):
            return list(
                event.items.filter(active=True, allow_waitinglist=True)
                .prefetch_related("variations")
                .order_by("position", "id")
            )

    def list_variations(self, item) -> list[Any]:
        """List active variations for one item.

        Args:
            item: Item whose active variations should be loaded.
        Returns:
            An ordered list of variation objects.
        """
        return list(item.variations.filter(active=True).order_by("position", "id"))

    def list_subevents(self, event) -> list[SubEvent]:
        """List active subevents for one event.

        Args:
            event: Event whose subevents should be loaded.
        Returns:
            An ordered list of `SubEvent` objects.
        """
        with scope(organizer=event.organizer):
            return list(event.subevents.filter(active=True).order_by("date_from", "id"))

    def get_subevent(self, event, subevent_id: int) -> SubEvent:
        """Load one active subevent by id.

        Args:
            event: Event that owns the subevent.
            subevent_id: Primary key of the desired subevent.
        Returns:
            The matching active `SubEvent`.
        """
        with scope(organizer=event.organizer):
            return event.subevents.get(pk=subevent_id, active=True)

    def list_memberships(
        self,
        organizer,
        membership_type_id: int,
        valid_for,
        include_testmode: bool = False,
    ) -> list[Membership]:
        """List active memberships eligible for import.

        Args:
            organizer: Organizer owning the memberships.
            membership_type_id: Membership type used to filter results.
            valid_for: Event or subevent used for `Membership.objects.active`.
            include_testmode: Whether testmode memberships are eligible.
        Returns:
            A list of active `Membership` objects.
        """
        with scope(organizer=organizer):
            qs = Membership.objects.active(valid_for).filter(
                customer__organizer=organizer,
                membership_type_id=membership_type_id,
            ).select_related("customer", "membership_type", "granted_in__order")
            if not include_testmode:
                qs = qs.filter(testmode=False)
            return list(qs)

    def get_matching_customer_ids(
        self,
        organizer,
        event,
        customer_ids: list[str],
        question_id: int,
        option_id: int,
    ) -> set[str]:
        """Find customers whose answers include one selected option.

        Args:
            organizer: Organizer owning the scoped query.
            event: Event whose orders should be searched.
            customer_ids: Candidate customer identifiers to match.
            question_id: Question being filtered.
            option_id: Required selected option id.
        Returns:
            A set of matching customer identifiers.
        """
        with scope(organizer=organizer):
            return set(
                QuestionAnswer.objects.filter(
                    question__event=event,
                    question_id=question_id,
                    options__id=option_id,
                    orderposition__order__event=event,
                    orderposition__order__customer__identifier__in=customer_ids,
                    orderposition__canceled=False,
                )
                .values_list("orderposition__order__customer__identifier", flat=True)
                .distinct()
            )

    def list_group_question_answers(
        self,
        organizer,
        event,
        question_id: int,
        emails: list[str] | None = None,
    ) -> list[QuestionAnswer]:
        """List non-empty answers for one grouping question.

        Args:
            organizer: Organizer owning the scoped query.
            event: Event whose answers should be searched.
            question_id: Group-question id to load answers for.
            emails: Optional participant emails used to narrow the query.
        Returns:
            An ordered list of `QuestionAnswer` objects.
        """
        if emails is not None and not emails:
            return []
        with scope(organizer=organizer):
            qs = QuestionAnswer.objects.filter(
                question__event=event,
                question_id=question_id,
                orderposition__order__event=event,
                orderposition__canceled=False,
            ).exclude(answer="")
            if emails:
                qs = qs.filter(
                    Q(orderposition__attendee_email__in=emails)
                    | Q(orderposition__order__customer__email__in=emails)
                    | Q(orderposition__order__email__in=emails)
                )
            return list(
                qs.select_related("orderposition__order__customer", "orderposition__order")
                .order_by("orderposition__order_id", "orderposition_id", "id")
            )

    def list_customers(self, organizer, customer_ids: list[str]) -> list[Customer]:
        """Load customers by identifier for one organizer.

        Args:
            organizer: Organizer owning the customers.
            customer_ids: Customer identifiers to fetch.
        Returns:
            An ordered list of `Customer` objects.
        """
        with scope(organizer=organizer):
            return list(
                Customer.objects.filter(
                    organizer=organizer,
                    identifier__in=customer_ids,
                )
                .only("identifier", "email", "name_cached", "name_parts", "locale", "phone")
                .order_by("identifier")
            )

    def list_waiting_list_entries(
        self,
        organizer,
        event,
        item: int,
        variation: int | None = None,
        subevent: int | None = None,
    ) -> list[WaitingListEntry]:
        """List voucher-less waiting-list entries for one target.

        Args:
            organizer: Organizer owning the scoped query.
            event: Event whose waiting list should be loaded.
            item: Item id of the waitlist target.
            variation: Optional variation id of the target.
            subevent: Optional subevent id of the target.
        Returns:
            An ordered list of `WaitingListEntry` objects.
        """
        with scope(organizer=organizer):
            return list(
                self._waiting_list_queryset(
                    event=event,
                    item=item,
                    variation=variation,
                    subevent=subevent,
                    include_vouchers=False,
                ).only(
                    "pk",
                    "email",
                    "locale",
                    "priority",
                    "created",
                    "name_cached",
                    "name_parts",
                )
            )

    def count_waiting_list_entries(
        self,
        organizer,
        event,
        item: int,
        variation: int | None = None,
        subevent: int | None = None,
    ) -> int:
        """Count voucher-less waiting-list entries for one target.

        Args:
            organizer: Organizer owning the scoped query.
            event: Event whose waiting list should be counted.
            item: Item id of the waitlist target.
            variation: Optional variation id of the target.
            subevent: Optional subevent id of the target.
        Returns:
            The total number of current waitlist entries for the target.
        """
        with scope(organizer=organizer):
            return self._waiting_list_queryset(
                event=event,
                item=item,
                variation=variation,
                subevent=subevent,
                include_vouchers=False,
            ).count()

    def waiting_list_import_statuses_by_email(
        self,
        organizer,
        event,
        item: int,
        variation: int | None = None,
        subevent: int | None = None,
    ) -> dict[str, str]:
        """Load import-blocking waitlist statuses keyed by normalized email.

        Args:
            organizer: Organizer owning the scoped query.
            event: Event whose waitlist should be searched.
            item: Item id of the waitlist target.
            variation: Optional variation id of the target.
            subevent: Optional subevent id of the target.
        Returns:
            A mapping of normalized email addresses to import status codes.
        """
        with scope(organizer=organizer):
            statuses: dict[str, str] = {}
            qs = self._waiting_list_queryset(
                    event=event,
                    item=item,
                    variation=variation,
                    subevent=subevent,
                    include_vouchers=True,
                ).select_related("voucher").exclude(email="").only(
                    "email",
                    "voucher__redeemed",
                    "voucher__max_usages",
                    "voucher__valid_until",
                )
            for entry in qs:
                email = entry.email.strip().lower() if entry.email else None
                if not email:
                    continue
                statuses[email] = self._waiting_list_entry_import_status(entry)
            return statuses

    def customer_ids_with_paid_tickets(
        self,
        organizer,
        event,
        customer_ids: list[str],
    ) -> set[str]:
        """Load customer ids that already own a paid admission ticket.

        Args:
            organizer: Organizer owning the scoped query.
            event: Event whose paid tickets should be searched.
            customer_ids: Candidate customer identifiers to check.
        Returns:
            Customer identifiers with a paid, non-canceled admission position.
        """
        if not customer_ids:
            return set()
        with scope(organizer=organizer):
            return set(
                OrderPosition.objects.filter(
                    order__event=event,
                    order__status=Order.STATUS_PAID,
                    order__customer__identifier__in=customer_ids,
                    canceled=False,
                    item__admission=True,
                    price__gt=0,
                )
                .values_list("order__customer__identifier", flat=True)
                .distinct()
            )

    def waiting_list_preview_page(
        self,
        organizer,
        event,
        item: int,
        variation: int | None = None,
        subevent: int | None = None,
        page: int = 1,
        per_page: int = 10,
    ):
        """Load one paginated waiting-list preview page from the database.

        Args:
            organizer: Organizer owning the scoped query.
            event: Event whose waiting list should be paginated.
            item: Item id of the waitlist target.
            variation: Optional variation id of the target.
            subevent: Optional subevent id of the target.
            page: 1-based page number to fetch.
            per_page: Number of rows to include per page.
        Returns:
            A `PreviewPage` built from the paginated query results.
        """
        with scope(organizer=organizer):
            qs = self._waiting_list_queryset(
                event=event,
                item=item,
                variation=variation,
                subevent=subevent,
                include_vouchers=False,
            ).only(
                "pk",
                "email",
                "locale",
                "priority",
                "created",
                "name_cached",
                "name_parts",
            )
            total = qs.count()
            pages = max(1, (total + per_page - 1) // per_page)
            page = min(max(page, 1), pages)
            start_index = (page - 1) * per_page
            entries = list(qs[start_index:start_index + per_page])
            return build_preview_page(
                build_waitlist_rows(entries),
                total,
                page,
                per_page,
            )

    def create_waiting_list_entry(
        self, organizer, event, payload: dict[str, Any], user=None
    ) -> WaitingListEntry:
        """Create one waiting-list entry from importer payload data.

        Args:
            organizer: Organizer owning the scoped write.
            event: Event whose waitlist should receive the entry.
            payload: Prepared entry fields and related customer data.
            user: User recorded in the waitlist log action.
        Returns:
            The saved `WaitingListEntry`.
        """
        with scope(organizer=organizer):
            customer = payload["customer"]
            entry = WaitingListEntry(
                event=event,
                subevent_id=payload.get("subevent"),
                email=payload["email"],
                item_id=payload["item"],
                variation_id=payload.get("variation"),
                locale=payload.get("locale") or "en",
                phone=payload.get("phone"),
                name_parts=payload.get("name_parts") or {},
            )
            if not entry.name_parts and payload.get("name"):
                entry.name_cached = payload["name"]
            if not entry.name_parts and getattr(customer, "name_parts", None):
                entry.name_parts = customer.name_parts
            entry.full_clean()
            entry.save()
            if payload.get("created"):
                entry.created = payload["created"]
                entry.save(update_fields=["created"])
            entry.log_action("pretix.event.orders.waitinglist.added", user=user)
            return entry

    def update_waiting_list_priorities(
        self,
        organizer,
        entries: list[WaitingListEntry],
        assignments: dict[int, int],
        user=None,
    ) -> int:
        """Persist new priorities for waiting-list entries.

        Args:
            organizer: Organizer owning the scoped write.
            entries: Entries eligible for updates.
            assignments: New priorities keyed by waitlist-entry id.
            user: User recorded in the waitlist log action.
        Returns:
            The number of entries whose priority changed.
        """
        updated = 0
        with scope(organizer=organizer):
            for entry in entries:
                new_priority = assignments.get(entry.pk)
                if new_priority is None or entry.priority == new_priority:
                    continue
                entry.priority = new_priority
                entry.save(update_fields=["priority"])
                entry.log_action(
                    "pretix.event.orders.waitinglist.changed",
                    user=user,
                    data={"priority": new_priority, "source": "waitlist_manager_randomize"},
                )
                updated += 1
        return updated

    def _waiting_list_queryset(
        self,
        *,
        event,
        item: int,
        variation: int | None,
        subevent: int | None,
        include_vouchers: bool,
    ):
        """Build the base queryset for waiting-list entries.

        Args:
            event: Event whose waiting list should be queried.
            item: Item id of the waitlist target.
            variation: Optional variation id of the target.
            subevent: Optional subevent id of the target.
            include_vouchers: Whether voucher-issued entries should be included.
        Returns:
            An ordered queryset for waitlist entries scoped to one target.
        """
        qs = WaitingListEntry.objects.filter(
            event=event,
            item_id=item,
            variation_id=variation,
            subevent_id=subevent,
        )
        if not include_vouchers:
            qs = qs.filter(voucher__isnull=True)
        return qs.order_by("-priority", "created", "pk")

    def _waiting_list_entry_import_status(self, entry: WaitingListEntry) -> str:
        """Resolve the import-blocking status for one waitlist entry.

        Args:
            entry: Waiting-list entry for the selected target.
        Returns:
            An import status code describing why the email is already covered.
        """
        if not entry.voucher_id:
            return "already_waiting"
        voucher = entry.voucher
        if voucher and voucher.redeemed >= voucher.max_usages:
            return "voucher_redeemed"
        return "voucher_assigned"
