from django import forms
from django.utils.translation import gettext_lazy as _


QUESTION_FILTER_EMPTY_CHOICE = ("", "No question filter")
ANSWER_FILTER_EMPTY_CHOICE = ("", "No answer filter")


def _apply_subevent_choices(field, subevent_choices) -> None:
    """Configure the shared subevent field for event and subevent modes.

    Args:
        field: The Django form field to configure.
        subevent_choices: Available subevent choices, if any.
    Returns:
        `None`. The field is mutated in place.
    """
    subevent_choices = subevent_choices or []
    if subevent_choices:
        field.choices = subevent_choices
        field.required = True
        field.help_text = _(
            "This event has subevents, so a target date is required."
        )
    else:
        field.choices = [("", _("This event has no subevents"))]


def _with_empty_choice(choices, empty_choice):
    """Prepend one empty choice when it is not already present.

    Args:
        choices: Existing Django choice tuples.
        empty_choice: The blank choice tuple to ensure.
    Returns:
        A normalized list of choices with the blank option first.
    """
    choices = list(choices or [])
    if choices and choices[0][0] == empty_choice[0]:
        return choices
    return [empty_choice] + choices


class WaitlistImportForm(forms.Form):
    """Collect filter options for importing members onto a waitlist."""

    membership_type = forms.ChoiceField(label=_("Membership type"))
    email = forms.CharField(
        required=False,
        label=_("Email filter"),
        help_text=_(
            "Leave blank to include all members in this membership type. Partial email matches are allowed."
        ),
    )
    question = forms.ChoiceField(label=_("Question filter"), required=False)
    answer = forms.ChoiceField(label=_("Required answer"), required=False)
    target = forms.ChoiceField(label=_("Target waitlist"))
    subevent = forms.ChoiceField(label=_("Event date"), required=False)
    exclude_paid_tickets = forms.TypedChoiceField(
        label=_("Exclude paid ticket holders"),
        required=False,
        initial="yes",
        choices=(
            ("yes", _("Yes")),
            ("no", _("No")),
        ),
        coerce=lambda value: value != "no",
        help_text=_(
            "Exclude customers who already have a paid admission ticket for this event. Free tickets do not count."
        ),
    )
    include_testmode = forms.BooleanField(
        required=False,
        label=_("Include test mode memberships"),
    )
    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Dry run only"),
        help_text=_("Preview matches without creating waiting list entries."),
    )

    def __init__(
        self,
        *args,
        membership_type_choices=None,
        question_choices=None,
        question_choices_by_membership=None,
        answer_choices_by_question=None,
        answer_choices_by_membership=None,
        target_choices=None,
        subevent_choices=None,
        **kwargs,
    ):
        """Initialize the import form with event-specific choice lists.

        Args:
            *args: Standard Django form positional arguments.
            membership_type_choices: Membership types available for filtering.
            question_choices: Questions available for filtering.
            question_choices_by_membership: Questions keyed by membership type id.
            answer_choices_by_question: Answer options keyed by question id.
            answer_choices_by_membership: Answer options keyed by membership type id.
            target_choices: Waitlist targets available for import.
            subevent_choices: Event dates available for selection.
            **kwargs: Standard Django form keyword arguments.
        Returns:
            `None`. The form instance is configured in place.
        """
        super().__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices or []
        self.fields["target"].choices = target_choices or []
        _apply_subevent_choices(self.fields["subevent"], subevent_choices)

        question_choices_by_membership = question_choices_by_membership or {}
        answer_choices_by_membership = answer_choices_by_membership or {}

        selected_membership = self._selected_membership_type(
            membership_type_choices or []
        )
        question_choices = question_choices or question_choices_by_membership.get(
            selected_membership, []
        )
        self.fields["question"].choices = _with_empty_choice(
            question_choices,
            QUESTION_FILTER_EMPTY_CHOICE,
        )

        answer_choices_by_question = answer_choices_by_question or (
            answer_choices_by_membership.get(selected_membership, {})
        )
        selected_question = self._selected_question(self.fields["question"].choices)
        self.fields["answer"].choices = _with_empty_choice(
            answer_choices_by_question.get(selected_question, []),
            ANSWER_FILTER_EMPTY_CHOICE,
        )

    def _selected_membership_type(self, membership_type_choices) -> str:
        """Resolve the currently selected membership type for question setup.

        Args:
            membership_type_choices: Available membership type choices for the form.
        Returns:
            The selected membership type id string, or an empty string.
        """
        if self.is_bound:
            return self.data.get(self.add_prefix("membership_type"), "") or ""
        if self.initial.get("membership_type"):
            return str(self.initial["membership_type"])
        if membership_type_choices:
            return membership_type_choices[0][0]
        return ""

    def _selected_question(self, question_choices) -> str:
        """Resolve the currently selected question for answer-field setup.

        Args:
            question_choices: Available question choices for the form.
        Returns:
            The selected question id string, or an empty string.
        """
        if self.is_bound:
            return self.data.get(self.add_prefix("question"), "") or ""
        if self.initial.get("question"):
            return str(self.initial["question"])
        if question_choices:
            return question_choices[0][0]
        return ""


class WaitlistRandomizeForm(forms.Form):
    """Collect options for randomizing an existing waitlist."""

    target = forms.ChoiceField(label=_("Waitlist"))
    subevent = forms.ChoiceField(label=_("Event date"), required=False)
    cutoff_date = forms.DateField(
        required=False,
        label=_("Cutoff date"),
        help_text=_("Only entries created on or before this date will be randomized."),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    group_question = forms.ChoiceField(
        required=False,
        label=_("Group question"),
        help_text=_(
            "If this answer contains one or more email addresses, grouped people receive the same priority."
        ),
    )
    seed = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(attrs={"data-ays-ignore": "1"}),
    )

    def __init__(
        self,
        *args,
        target_choices=None,
        subevent_choices=None,
        group_question_choices=None,
        group_question_choices_by_selection=None,
        **kwargs,
    ):
        """Initialize the randomize form with event-specific choice lists.

        Args:
            *args: Standard Django form positional arguments.
            target_choices: Waitlist targets available for randomization.
            subevent_choices: Event dates available for selection.
            group_question_choices: Questions that can define grouping rules.
            group_question_choices_by_selection: Questions keyed by target/subevent.
            **kwargs: Standard Django form keyword arguments.
        Returns:
            `None`. The form instance is configured in place.
        """
        super().__init__(*args, **kwargs)
        self.fields["target"].choices = target_choices or []
        _apply_subevent_choices(self.fields["subevent"], subevent_choices)

        group_question_choices_by_selection = group_question_choices_by_selection or {}
        selected_selection = self._selected_selection(
            target_choices or [], subevent_choices or []
        )
        self.fields["group_question"].choices = (
            group_question_choices_by_selection.get(selected_selection)
            or group_question_choices
            or [("", _("No group question"))]
        )

    def _selected_selection(self, target_choices, subevent_choices) -> str:
        """Resolve the current waitlist/subevent selection for group questions.

        Args:
            target_choices: Available target choices for the form.
            subevent_choices: Available subevent choices for the form.
        Returns:
            A serialized `target|subevent` selection key.
        """
        if self.is_bound:
            target = self.data.get(self.add_prefix("target"), "") or ""
            subevent = self.data.get(self.add_prefix("subevent"), "") or ""
            return f"{target}|{subevent}"
        target = str(self.initial.get("target", "")) if self.initial.get("target") else ""
        if not target and target_choices:
            target = target_choices[0][0]
        subevent = str(self.initial.get("subevent", "")) if self.initial.get("subevent") else ""
        if not subevent and subevent_choices:
            subevent = subevent_choices[0][0]
        return f"{target}|{subevent}"
