from typing import Any

from django_scopes import scope

from pretix.base.models import (
    Customer,
    Item,
    Membership,
    MembershipType,
    Question,
    QuestionAnswer,
    SubEvent,
    WaitingListEntry,
)


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
    ) -> list[QuestionAnswer]:
        """List non-empty answers for one grouping question.

        Args:
            organizer: Organizer owning the scoped query.
            event: Event whose answers should be searched.
            question_id: Group-question id to load answers for.
        Returns:
            An ordered list of `QuestionAnswer` objects.
        """
        with scope(organizer=organizer):
            return list(
                QuestionAnswer.objects.filter(
                    question__event=event,
                    question_id=question_id,
                    orderposition__order__event=event,
                    orderposition__canceled=False,
                )
                .exclude(answer="")
                .select_related("orderposition__order__customer", "orderposition__order")
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
                ).order_by("identifier")
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
                WaitingListEntry.objects.filter(
                    event=event,
                    item_id=item,
                    variation_id=variation,
                    subevent_id=subevent,
                    voucher__isnull=True,
                ).order_by("-priority", "created", "pk")
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
