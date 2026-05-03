from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WaitlistTarget:
    """Selected waitlist target.

    Inputs:
        `item_id` is the item primary key and `variation_id` is optional.
    Outputs:
        Immutable target metadata passed to importer and randomizer services.
    """

    item_id: int
    variation_id: int | None = None


@dataclass(frozen=True)
class ImportRow:
    """One candidate row in the import preview or result.

    Inputs:
        Customer identity, contact data, locale, and an import status code.
    Outputs:
        Immutable preview/result row data for templates and tests.
    """

    customer: str
    email: str | None
    name: str | None
    locale: str | None
    status: str


@dataclass(frozen=True)
class WaitlistRow:
    """One rendered waiting-list row for preview tables.

    Inputs:
        Contact data, locale, assigned priority, and registration timestamp.
    Outputs:
        Immutable preview row data for import and randomize templates.
    """

    email: str | None
    name: str | None
    locale: str | None
    priority: int
    created: Any


@dataclass(frozen=True)
class ImportResult:
    """Summary of one import execution.

    Inputs:
        Aggregate counts and the full set of `ImportRow` records.
    Outputs:
        Immutable import result data for messaging, previews, and tests.
    """

    total_memberships: int
    distinct_customers: int
    matched_customers: int
    existing_waitlist_entries: int
    added_count: int
    rows: list[ImportRow]


@dataclass(frozen=True)
class PreviewPage:
    """One paginated slice of preview data.

    Inputs:
        Page rows plus pagination counts and navigation flags.
    Outputs:
        Immutable page metadata consumed by preview templates.
    """

    rows: list[Any]
    total: int
    page: int
    per_page: int
    pages: int
    start: int
    end: int
    has_previous: bool
    has_next: bool
    previous_page: int | None
    next_page: int | None


@dataclass(frozen=True)
class ImportPreviewResult:
    """Paginated preview payload for the import tab.

    Inputs:
        Candidate import rows and current waitlist rows as `PreviewPage`s.
    Outputs:
        Immutable preview payload for the import template.
    """

    import_page: PreviewPage
    current_waitlist_page: PreviewPage


@dataclass(frozen=True)
class RandomizationPreviewResult:
    """Paginated preview payload for the randomize tab.

    Inputs:
        Before/after pages, counts, grouping metrics, and the applied seed.
    Outputs:
        Immutable preview payload for the randomize template.
    """

    before_page: PreviewPage
    after_page: PreviewPage
    total_entries: int
    eligible_entries: int
    grouped_entries: int
    grouped_clusters: int
    seed: int


@dataclass(frozen=True)
class RandomizationResult:
    """Summary of one persisted randomization run.

    Inputs:
        Update counts, grouping metrics, and the applied seed.
    Outputs:
        Immutable randomization result data for messaging and tests.
    """

    updated_entries: int
    eligible_entries: int
    grouped_entries: int
    grouped_clusters: int
    seed: int
