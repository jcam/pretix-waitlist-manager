from .service_helpers import paginate_rows, value
from .service_types import ImportPreviewResult, ImportResult, ImportRow, WaitlistTarget


class WaitlistMembershipImporter:
    """Import eligible members onto a selected pretix waiting list."""

    def __init__(self, provider):
        """Store the data provider used for all importer queries.

        Args:
            provider: Provider exposing pretix model access methods.
        Returns:
            `None`. The importer stores the provider for later calls.
        """
        self.provider = provider

    def run(
        self,
        organizer,
        event,
        membership_type_id: int,
        question_id: int | None,
        option_id: int | None,
        target: WaitlistTarget,
        subevent_id: int | None = None,
        include_testmode: bool = False,
        dry_run: bool = True,
        user=None,
    ) -> ImportResult:
        """Execute one membership-to-waitlist import run.

        Args:
            organizer: Organizer owning the data scope.
            event: Event whose waitlist is being updated.
            membership_type_id: Membership type used to select members.
            question_id: Optional question whose answer filters members.
            option_id: Optional question option that must be selected.
            target: Selected waitlist item or variation.
            subevent_id: Optional subevent to scope the waitlist.
            include_testmode: Whether testmode memberships are eligible.
            dry_run: Whether to simulate without creating entries.
            user: User recorded in waitlist log actions.
        Returns:
            An `ImportResult` describing matches and created entries.
        """
        valid_for = self.provider.get_subevent(event, subevent_id) if subevent_id else event
        (
            memberships,
            customer_ids,
            matched_customers,
            membership_created_by_customer,
        ) = self._matched_customers(
            organizer=organizer,
            event=event,
            valid_for=valid_for,
            membership_type_id=membership_type_id,
            question_id=question_id,
            option_id=option_id,
            include_testmode=include_testmode,
        )
        existing_emails = self.provider.list_waiting_list_entry_emails(
            organizer,
            event,
            item=target.item_id,
            variation=target.variation_id,
            subevent=subevent_id,
        )
        existing_waitlist_entries = self.provider.count_waiting_list_entries(
            organizer,
            event,
            item=target.item_id,
            variation=target.variation_id,
            subevent=subevent_id,
        )

        rows: list[ImportRow] = []
        added_count = 0
        for customer, email, lowered_email, name, locale in self._customer_row_parts(
            matched_customers
        ):
            customer_id = value(customer, "identifier")
            status = self._import_status(
                email=email,
                lowered_email=lowered_email,
                existing_emails=existing_emails,
            )
            if status == "missing_email":
                rows.append(
                    ImportRow(
                        customer=customer_id,
                        email=None,
                        name=name,
                        locale=locale,
                        status=status,
                    )
                )
                continue
            if status == "already_waiting":
                rows.append(
                    ImportRow(
                        customer=customer_id,
                        email=email,
                        name=name,
                        locale=locale,
                        status=status,
                    )
                )
                continue
            if not dry_run:
                payload = {
                    "customer": customer,
                    "created": membership_created_by_customer.get(customer_id),
                    "email": email,
                    "item": target.item_id,
                    "variation": target.variation_id,
                    "locale": locale or "en",
                    "subevent": subevent_id,
                    "phone": value(customer, "phone"),
                    "name_parts": value(customer, "name_parts", {}),
                }
                if name:
                    payload["name"] = name
                self.provider.create_waiting_list_entry(
                    organizer, event, payload, user=user
                )
                existing_emails.add(lowered_email)
                added_count += 1
                status = "added"
            else:
                status = "would_add"

            rows.append(
                ImportRow(
                    customer=customer_id,
                    email=email,
                    name=name,
                    locale=locale,
                    status=status,
                )
            )

        return ImportResult(
            total_memberships=len(memberships),
            distinct_customers=len(customer_ids),
            matched_customers=len(matched_customers),
            existing_waitlist_entries=existing_waitlist_entries,
            added_count=added_count,
            rows=rows,
        )

    def _membership_created_by_customer(self, memberships) -> dict[str, object]:
        """Choose one queue timestamp per customer from their memberships.

        Args:
            memberships: Membership records eligible for import.
        Returns:
            A mapping of customer identifiers to the earliest usable datetime.
        """
        created_by_customer: dict[str, object] = {}
        for membership in memberships:
            customer_id = value(value(membership, "customer"), "identifier")
            if not customer_id:
                continue
            candidate = self._membership_created(membership)
            if candidate is None:
                continue
            current = created_by_customer.get(customer_id)
            if current is None or candidate < current:
                created_by_customer[customer_id] = candidate
        return created_by_customer

    def _membership_created(self, membership):
        """Resolve the historical queue datetime for one membership.

        Args:
            membership: Membership-like object being imported.
        Returns:
            The granting order datetime when available, otherwise the membership
            start datetime, or `None` if neither exists.
        """
        granted_in = value(membership, "granted_in")
        granted_order = value(granted_in, "order")
        return value(granted_order, "datetime") or value(membership, "date_start")

    def preview(
        self,
        organizer,
        event,
        membership_type_id: int,
        question_id: int | None,
        option_id: int | None,
        target: WaitlistTarget,
        subevent_id: int | None = None,
        include_testmode: bool = False,
        sample_size: int = 10,
        import_page: int = 1,
        current_waitlist_page: int = 1,
    ) -> ImportPreviewResult:
        """Build paginated preview data for an import request.

        Args:
            organizer: Organizer owning the data scope.
            event: Event whose waitlist is being previewed.
            membership_type_id: Membership type used to select members.
            question_id: Optional question whose answer filters members.
            option_id: Optional question option that must be selected.
            target: Selected waitlist item or variation.
            subevent_id: Optional subevent to scope the waitlist.
            include_testmode: Whether testmode memberships are eligible.
            sample_size: Rows shown per preview page.
            import_page: Requested page for candidate import rows.
            current_waitlist_page: Requested page for existing waitlist rows.
        Returns:
            An `ImportPreviewResult` for the import tab.
        """
        valid_for = self.provider.get_subevent(event, subevent_id) if subevent_id else event
        (
            _memberships,
            _customer_ids,
            matched_customers,
            _membership_created_by_customer,
        ) = self._matched_customers(
            organizer=organizer,
            event=event,
            valid_for=valid_for,
            membership_type_id=membership_type_id,
            question_id=question_id,
            option_id=option_id,
            include_testmode=include_testmode,
        )
        existing_emails = self.provider.list_waiting_list_entry_emails(
            organizer,
            event,
            item=target.item_id,
            variation=target.variation_id,
            subevent=subevent_id,
        )
        rows = [
            ImportRow(
                customer=customer_id,
                email=email,
                name=name,
                locale=locale,
                status=self._import_status(
                    email=email,
                    lowered_email=lowered_email,
                    existing_emails=existing_emails,
                ),
            )
            for customer, email, lowered_email, name, locale in self._customer_row_parts(
                matched_customers
            )
            for customer_id in [value(customer, "identifier")]
        ]
        return ImportPreviewResult(
            import_page=paginate_rows(rows, import_page, sample_size),
            current_waitlist_page=self.provider.waiting_list_preview_page(
                organizer,
                event,
                item=target.item_id,
                variation=target.variation_id,
                subevent=subevent_id,
                page=current_waitlist_page,
                per_page=sample_size,
            ),
        )

    def _matched_customers(
        self,
        *,
        organizer,
        event,
        valid_for,
        membership_type_id: int,
        question_id: int | None,
        option_id: int | None,
        include_testmode: bool,
    ):
        """Load memberships, matching customer ids, and matching customers.

        Args:
            organizer: Organizer owning the data scope.
            event: Event whose answers should be searched.
            valid_for: Event or subevent used to resolve active memberships.
            membership_type_id: Membership type used to select members.
            question_id: Optional question used to filter members.
            option_id: Optional option used to filter members.
            include_testmode: Whether testmode memberships are eligible.
        Returns:
            Memberships, distinct customer ids, matched customers, and created dates.
        """
        memberships = self.provider.list_memberships(
            organizer,
            membership_type_id,
            valid_for,
            include_testmode=include_testmode,
        )
        membership_created_by_customer = self._membership_created_by_customer(memberships)
        customer_ids = sorted(
            {
                value(value(membership, "customer"), "identifier")
                for membership in memberships
                if value(value(membership, "customer"), "identifier")
            }
        )
        if question_id and option_id:
            matching_customer_ids = self.provider.get_matching_customer_ids(
                organizer,
                event,
                customer_ids,
                question_id,
                option_id,
            )
        else:
            matching_customer_ids = set(customer_ids)
        matched_customers = self.provider.list_customers(
            organizer,
            sorted(matching_customer_ids),
        )
        return memberships, customer_ids, matched_customers, membership_created_by_customer

    def _customer_row_parts(self, matched_customers):
        """Yield common display fields used by import preview and execution.

        Args:
            matched_customers: Customer objects selected for the import.
        Returns:
            Tuples of customer object, email, normalized email, name, and locale.
        """
        for customer in matched_customers:
            email = (value(customer, "email") or "").strip() or None
            lowered_email = email.lower() if email else None
            name = value(customer, "name_cached") or value(customer, "name") or None
            locale = value(customer, "locale") or None
            yield customer, email, lowered_email, name, locale

    def _import_status(
        self,
        *,
        email: str | None,
        lowered_email: str | None,
        existing_emails: set[str],
    ) -> str:
        """Resolve the import status for one matched customer.

        Args:
            email: Raw customer email, if present.
            lowered_email: Normalized customer email, if present.
            existing_emails: Emails already on the target waitlist.
        Returns:
            One of the import preview status codes.
        """
        if not email:
            return "missing_email"
        if lowered_email in existing_emails:
            return "already_waiting"
        return "would_add"
