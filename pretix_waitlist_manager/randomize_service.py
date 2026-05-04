import random
import secrets
from datetime import date

from pretix.base.models import QuestionAnswer, WaitingListEntry

from .service_helpers import (
    EMAIL_PATTERN,
    RANDOM_PRIORITY_MAX,
    build_waitlist_rows,
    normalize_email,
    paginate_rows,
    value,
)
from .service_types import RandomizationPreviewResult, RandomizationResult, WaitlistTarget


class WaitlistRandomizer:
    """Assign randomized priorities to waiting-list entries."""

    def __init__(self, provider):
        """Store the data provider used for randomization work.

        Args:
            provider: Provider exposing pretix model access methods.
        Returns:
            `None`. The randomizer stores the provider for later calls.
        """
        self.provider = provider

    def new_seed(self) -> int:
        """Generate a non-zero seed suitable for reproducible shuffles.

        Args:
            None.
        Returns:
            A random integer seed below `RANDOM_PRIORITY_MAX`.
        """
        return secrets.randbelow(RANDOM_PRIORITY_MAX - 1) + 1

    def preview(
        self,
        organizer,
        event,
        target: WaitlistTarget,
        subevent_id: int | None = None,
        cutoff_date: date | None = None,
        group_question_id: int | None = None,
        sample_size: int = 10,
        before_page: int = 1,
        after_page: int = 1,
        seed: int | None = None,
    ) -> RandomizationPreviewResult:
        """Build before/after preview data for a randomization request.

        Args:
            organizer: Organizer owning the data scope.
            event: Event whose waitlist is being previewed.
            target: Selected waitlist item or variation.
            subevent_id: Optional subevent to scope the waitlist.
            cutoff_date: Optional latest creation date to include.
            group_question_id: Optional question used to cluster entries.
            sample_size: Rows shown per preview page.
            before_page: Requested page for the current waitlist order.
            after_page: Requested page for the randomized order.
            seed: Optional fixed seed for reproducible output.
        Returns:
            A `RandomizationPreviewResult` for the randomize tab.
        """
        entries, eligible_entries, assignments, grouped_clusters, grouped_entries, seed = self._plan(
            organizer=organizer,
            event=event,
            target=target,
            subevent_id=subevent_id,
            cutoff_date=cutoff_date,
            group_question_id=group_question_id,
            seed=seed,
        )
        after_entries = sorted(
            entries,
            key=lambda entry: (
                -assignments.get(entry.pk, entry.priority),
                entry.created,
                entry.pk,
            ),
        )
        return RandomizationPreviewResult(
            before_page=paginate_rows(
                build_waitlist_rows(entries),
                before_page,
                sample_size,
            ),
            after_page=paginate_rows(
                build_waitlist_rows(after_entries, assignments=assignments),
                after_page,
                sample_size,
            ),
            total_entries=len(entries),
            eligible_entries=len(eligible_entries),
            grouped_entries=grouped_entries,
            grouped_clusters=grouped_clusters,
            seed=seed,
        )

    def run(
        self,
        organizer,
        event,
        target: WaitlistTarget,
        subevent_id: int | None = None,
        cutoff_date: date | None = None,
        group_question_id: int | None = None,
        seed: int | None = None,
        user=None,
    ) -> RandomizationResult:
        """Persist randomized priorities for eligible waitlist entries.

        Args:
            organizer: Organizer owning the data scope.
            event: Event whose waitlist is being updated.
            target: Selected waitlist item or variation.
            subevent_id: Optional subevent to scope the waitlist.
            cutoff_date: Optional latest creation date to include.
            group_question_id: Optional question used to cluster entries.
            seed: Optional fixed seed for reproducible output.
            user: User recorded in waitlist log actions.
        Returns:
            A `RandomizationResult` describing the update.
        """
        entries, eligible_entries, assignments, grouped_clusters, grouped_entries, seed = self._plan(
            organizer=organizer,
            event=event,
            target=target,
            subevent_id=subevent_id,
            cutoff_date=cutoff_date,
            group_question_id=group_question_id,
            seed=seed,
        )
        updated = self.provider.update_waiting_list_priorities(
            organizer,
            entries,
            assignments,
            user=user,
        )
        return RandomizationResult(
            updated_entries=updated,
            eligible_entries=len(eligible_entries),
            grouped_entries=grouped_entries,
            grouped_clusters=grouped_clusters,
            seed=seed,
        )

    def _plan(
        self,
        organizer,
        event,
        target: WaitlistTarget,
        subevent_id: int | None,
        cutoff_date: date | None,
        group_question_id: int | None,
        seed: int | None,
    ) -> tuple[list[WaitingListEntry], list[WaitingListEntry], dict[int, int], int, int, int]:
        """Plan one randomization without mutating the database.

        Args:
            organizer: Organizer owning the data scope.
            event: Event whose waitlist is being planned.
            target: Selected waitlist item or variation.
            subevent_id: Optional subevent to scope the waitlist.
            cutoff_date: Optional latest creation date to include.
            group_question_id: Optional question used to cluster entries.
            seed: Optional fixed seed for reproducible output.
        Returns:
            A tuple of entries, eligible entries, assignments, cluster count,
            grouped-entry count, and the seed used.
        """
        entries = self.provider.list_waiting_list_entries(
            organizer,
            event,
            item=target.item_id,
            variation=target.variation_id,
            subevent=subevent_id,
        )
        eligible_entries = [
            entry
            for entry in entries
            if cutoff_date is None or entry.created.date() <= cutoff_date
        ]
        if seed is None:
            seed = self.new_seed()
        if not eligible_entries:
            return entries, eligible_entries, {}, 0, 0, seed

        component_members = self._build_component_members(
            organizer=organizer,
            event=event,
            eligible_entries=eligible_entries,
            group_question_id=group_question_id,
        )
        priorities = random.Random(seed).sample(
            range(1, RANDOM_PRIORITY_MAX),
            len(component_members),
        )

        assignments: dict[int, int] = {}
        grouped_clusters = 0
        grouped_entries = 0
        for component_key, priority in zip(component_members, priorities):
            members = component_members[component_key]
            if len(members) > 1:
                grouped_clusters += 1
                grouped_entries += len(members)
            for entry in members:
                assignments[entry.pk] = priority
        return entries, eligible_entries, assignments, grouped_clusters, grouped_entries, seed

    def _build_component_members(
        self,
        organizer,
        event,
        eligible_entries: list[WaitingListEntry],
        group_question_id: int | None,
    ) -> dict[str, list[WaitingListEntry]]:
        """Group eligible entries into randomization components.

        Args:
            organizer: Organizer owning the data scope.
            event: Event whose waitlist is being grouped.
            eligible_entries: Entries eligible for randomization.
            group_question_id: Optional question used to cluster entries.
        Returns:
            A mapping of component keys to grouped waitlist entries.
        """
        if not group_question_id:
            return {f"entry:{entry.pk}": [entry] for entry in eligible_entries}

        eligible_emails = sorted(
            {
                entry.email.strip()
                for entry in eligible_entries
                if entry.email and entry.email.strip()
            }
        )
        root_by_email = self._group_roots(
            self.provider.list_group_question_answers(
                organizer,
                event,
                group_question_id,
                emails=eligible_emails,
            )
        )
        component_members: dict[str, list[WaitingListEntry]] = {}
        for entry in eligible_entries:
            component_key = root_by_email.get(normalize_email(entry.email)) or f"entry:{entry.pk}"
            component_members.setdefault(component_key, []).append(entry)
        return component_members

    def _group_roots(self, answers: list[QuestionAnswer]) -> dict[str, str]:
        """Build union-find roots for linked email addresses.

        Args:
            answers: Group-question answers containing email references.
        Returns:
            A mapping of each seen email to its component root.
        """
        parent: dict[str, str] = {}

        def find(value_: str) -> str:
            """Resolve one email address to its component root.

            Args:
                value_: Email address already present in the union-find graph.
            Returns:
                The canonical root email for that component.
            """
            parent.setdefault(value_, value_)
            if parent[value_] != value_:
                parent[value_] = find(parent[value_])
            return parent[value_]

        def union(left: str, right: str) -> None:
            """Merge two email addresses into the same component.

            Args:
                left: First email in the component.
                right: Second email in the component.
            Returns:
                `None`. The union-find graph is mutated in place.
            """
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        for answer in answers:
            emails = self._emails_from_answer(answer)
            if len(emails) < 2:
                continue
            for email in emails[1:]:
                union(emails[0], email)

        return {email: find(email) for email in parent}

    def _emails_from_answer(self, answer: QuestionAnswer) -> list[str]:
        """Extract normalized participant emails from one group answer.

        Args:
            answer: One `QuestionAnswer` that may mention grouped emails.
        Returns:
            A sorted list of normalized email addresses.
        """
        emails = {
            normalized
            for candidate in EMAIL_PATTERN.findall(answer.answer or "")
            if (normalized := normalize_email(candidate))
        }
        owner_candidates = [
            normalize_email(value(answer.orderposition, "attendee_email")),
            normalize_email(value(value(answer.orderposition, "order"), "email")),
            normalize_email(
                value(value(value(answer.orderposition, "order"), "customer"), "email")
            ),
        ]
        for candidate in owner_candidates:
            if candidate:
                emails.add(candidate)
                break
        return sorted(emails)
