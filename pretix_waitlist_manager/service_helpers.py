import re
from typing import Any

from pretix.base.models import Question, WaitingListEntry

from .service_types import PreviewPage, WaitlistRow, WaitlistTarget

EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
RANDOM_PRIORITY_MAX = 2_000_000_000


def value(obj: Any, field: str, default: Any = None) -> Any:
    """Read one attribute from either a dict or an object.

    Args:
        obj: Source object or dict.
        field: Attribute or key name to read.
        default: Value returned when the field is missing.
    Returns:
        The extracted value or the provided default.
    """
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def iter_related(value_or_manager: Any) -> list[Any]:
    """Materialize a related-manager or iterable into a plain list.

    Args:
        value_or_manager: A Django related manager, iterable, or `None`.
    Returns:
        A list of related objects, or an empty list.
    """
    if value_or_manager is None:
        return []
    if hasattr(value_or_manager, "all"):
        return list(value_or_manager.all())
    return list(value_or_manager)


def normalize_email(raw: str | None) -> str | None:
    """Normalize an email address for comparisons.

    Args:
        raw: Raw email string, possibly empty.
    Returns:
        A lowercase trimmed email, or `None` when empty.
    """
    if not raw:
        return None
    normalized = raw.strip().lower()
    return normalized or None


def localized_label(value_or_i18n: Any, fallback: str = "") -> str:
    """Render a localized label from a pretix i18n field or plain value.

    Args:
        value_or_i18n: Pretix i18n dict, plain string, or arbitrary object.
        fallback: Text to use when no displayable value is present.
    Returns:
        A display string suitable for form labels.
    """
    if value_or_i18n is None:
        return fallback
    if isinstance(value_or_i18n, dict):
        for locale in ("en", "en-us", "en_US"):
            if value_or_i18n.get(locale):
                return str(value_or_i18n[locale])
        for candidate in value_or_i18n.values():
            if candidate:
                return str(candidate)
        return fallback
    if isinstance(value_or_i18n, str):
        return value_or_i18n
    rendered = str(value_or_i18n)
    return rendered if rendered else fallback


def parse_target_choice(value_: str) -> WaitlistTarget:
    """Parse an `item_id:variation_id` waitlist target value.

    Args:
        value_: Serialized form choice value.
    Returns:
        A `WaitlistTarget` describing the selected waitlist.
    """
    item_id, variation_id = value_.split(":", 1)
    return WaitlistTarget(
        item_id=int(item_id),
        variation_id=int(variation_id) if variation_id else None,
    )


def build_question_choices(questions: list[Any]) -> list[tuple[str, str]]:
    """Build form choices for selectable import questions.

    Args:
        questions: Question-like objects with choice options.
    Returns:
        A list of `(value, label)` tuples for Django choice fields.
    """
    choices: list[tuple[str, str]] = [("", "No question filter")]
    for question in questions:
        if value(question, "type") not in {
            Question.TYPE_CHOICE,
            Question.TYPE_CHOICE_MULTIPLE,
            "C",
            "M",
        }:
            continue
        question_label = localized_label(
            value(question, "question"),
            fallback=f"Question #{value(question, 'id')}",
        )
        choices.append((str(value(question, "id")), question_label))
    return choices


def build_question_answer_choices(
    questions: list[Any],
) -> dict[str, list[tuple[str, str]]]:
    """Build per-question answer choices for the import form.

    Args:
        questions: Question-like objects with choice options.
    Returns:
        A mapping of question id strings to `(value, label)` answer choices.
    """
    choices_by_question: dict[str, list[tuple[str, str]]] = {
        "": [("", "No answer filter")]
    }
    for question in questions:
        question_id = str(value(question, "id"))
        if value(question, "type") not in {
            Question.TYPE_CHOICE,
            Question.TYPE_CHOICE_MULTIPLE,
            "C",
            "M",
        }:
            continue
        choices_by_question[question_id] = [("", "No answer filter")] + [
            (
                str(value(option, "id")),
                localized_label(
                    value(option, "answer"),
                    fallback=f"Option #{value(option, 'id')}",
                ),
            )
            for option in iter_related(value(question, "options", []))
        ]
    return choices_by_question


def build_group_question_choices(questions: list[Any]) -> list[tuple[str, str]]:
    """Build form choices for grouping-question selection.

    Args:
        questions: Question-like objects that may define email groups.
    Returns:
        A list of `(value, label)` tuples including the empty option.
    """
    choices = [("", "No group question")]
    for question in questions:
        choices.append(
            (
                str(value(question, "id")),
                localized_label(
                    value(question, "question"),
                    fallback=f"Question #{value(question, 'id')}",
                ),
            )
        )
    return choices


def build_membership_type_choices(membership_types: list[Any]) -> list[tuple[str, str]]:
    """Build form choices for membership types.

    Args:
        membership_types: Membership-type-like objects.
    Returns:
        A list of `(value, label)` tuples for Django choice fields.
    """
    return [
        (
            str(value(membership_type, "id")),
            localized_label(
                value(membership_type, "name"),
                fallback=f"Membership type #{value(membership_type, 'id')}",
            ),
        )
        for membership_type in membership_types
    ]


def build_target_product_choices(
    items: list[Any],
    variations_by_item: dict[int, list[Any]],
) -> list[tuple[str, str]]:
    """Build form choices for waitlist-capable items and variations.

    Args:
        items: Item-like objects that allow waiting lists.
        variations_by_item: Active variations keyed by item id.
    Returns:
        A list of `(value, label)` tuples for target selection.
    """
    choices: list[tuple[str, str]] = []
    for item in items:
        item_id = value(item, "id")
        item_label = localized_label(value(item, "name"), fallback=f"Item #{item_id}")
        if value(item, "has_variations"):
            for variation in variations_by_item.get(item_id, []):
                variation_label = localized_label(
                    value(variation, "value"),
                    fallback=f"Variation #{value(variation, 'id')}",
                )
                choices.append(
                    (
                        f"{item_id}:{value(variation, 'id')}",
                        f"{item_label} / {variation_label}",
                    )
                )
        else:
            choices.append((f"{item_id}:", item_label))
    return choices


def build_subevent_choices(subevents: list[Any]) -> list[tuple[str, str]]:
    """Build form choices for subevents or dated event instances.

    Args:
        subevents: Subevent-like objects.
    Returns:
        A list of `(value, label)` tuples for the subevent field.
    """
    choices: list[tuple[str, str]] = []
    for subevent in subevents:
        label = localized_label(value(subevent, "name"))
        if not label:
            label = value(subevent, "date_from", f"Subevent #{value(subevent, 'id')}")
        elif value(subevent, "date_from"):
            label = f"{label} ({value(subevent, 'date_from')})"
        choices.append((str(value(subevent, "id")), label))
    return choices


def build_waitlist_rows(
    entries: list[WaitingListEntry],
    assignments: dict[int, int] | None = None,
) -> list[WaitlistRow]:
    """Convert waiting-list entries into preview rows.

    Args:
        entries: Waiting-list-entry-like objects.
        assignments: Optional priority overrides keyed by entry id.
    Returns:
        A list of `WaitlistRow` preview objects.
    """
    assignments = assignments or {}
    return [
        WaitlistRow(
            email=value(entry, "email") or None,
            name=value(entry, "name_cached") or value(entry, "name") or None,
            locale=value(entry, "locale") or None,
            priority=int(assignments.get(entry.pk, value(entry, "priority", 0)) or 0),
            created=value(entry, "created"),
        )
        for entry in entries
    ]


def build_preview_page(
    rows: list[Any],
    total: int,
    page: int,
    per_page: int,
) -> PreviewPage:
    """Construct preview pagination metadata for a pre-sliced row list.

    Args:
        rows: Rows already limited to the requested page.
        total: Total row count across all pages.
        page: 1-based page number requested by the caller.
        per_page: Number of rows intended per page.
    Returns:
        A `PreviewPage` for templates and preview JSON payloads.
    """
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(page, 1), pages)
    start_index = (page - 1) * per_page
    end_index = min(start_index + len(rows), total)
    return PreviewPage(
        rows=rows,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        start=start_index + 1 if total else 0,
        end=end_index,
        has_previous=page > 1,
        has_next=page < pages,
        previous_page=page - 1 if page > 1 else None,
        next_page=page + 1 if page < pages else None,
    )


def paginate_rows(rows: list[Any], page: int, per_page: int) -> PreviewPage:
    """Slice a list into one preview page with navigation metadata.

    Args:
        rows: Full ordered row list to paginate.
        page: 1-based page number requested by the caller.
        per_page: Number of rows to include per page.
    Returns:
        A `PreviewPage` describing the selected slice.
    """
    total = len(rows)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(page, 1), pages)
    start_index = (page - 1) * per_page
    end_index = min(start_index + per_page, total)
    return build_preview_page(rows[start_index:end_index], total, page, per_page)
