from django import forms
from django.utils.translation import gettext_lazy as _


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


class WaitlistImportForm(forms.Form):
    """Collect filter options for importing members onto a waitlist."""

    membership_type = forms.ChoiceField(label=_("Membership type"))
    question = forms.ChoiceField(label=_("Question filter"))
    answer = forms.ChoiceField(label=_("Required answer"))
    target = forms.ChoiceField(label=_("Target waitlist"))
    subevent = forms.ChoiceField(label=_("Event date"), required=False)
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
        answer_choices_by_question=None,
        target_choices=None,
        subevent_choices=None,
        **kwargs,
    ):
        """Initialize the import form with event-specific choice lists.

        Args:
            *args: Standard Django form positional arguments.
            membership_type_choices: Membership types available for filtering.
            question_choices: Questions available for filtering.
            answer_choices_by_question: Answer options keyed by question id.
            target_choices: Waitlist targets available for import.
            subevent_choices: Event dates available for selection.
            **kwargs: Standard Django form keyword arguments.
        Returns:
            `None`. The form instance is configured in place.
        """
        super().__init__(*args, **kwargs)
        self.fields["membership_type"].choices = membership_type_choices or []
        self.fields["question"].choices = question_choices or []
        self.fields["target"].choices = target_choices or []
        _apply_subevent_choices(self.fields["subevent"], subevent_choices)

        answer_choices_by_question = answer_choices_by_question or {}
        selected_question = self._selected_question(question_choices or [])
        self.fields["answer"].choices = answer_choices_by_question.get(
            selected_question, []
        )

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
        widget=forms.HiddenInput(),
    )

    def __init__(
        self,
        *args,
        target_choices=None,
        subevent_choices=None,
        group_question_choices=None,
        **kwargs,
    ):
        """Initialize the randomize form with event-specific choice lists.

        Args:
            *args: Standard Django form positional arguments.
            target_choices: Waitlist targets available for randomization.
            subevent_choices: Event dates available for selection.
            group_question_choices: Questions that can define grouping rules.
            **kwargs: Standard Django form keyword arguments.
        Returns:
            `None`. The form instance is configured in place.
        """
        super().__init__(*args, **kwargs)
        self.fields["target"].choices = target_choices or []
        self.fields["group_question"].choices = group_question_choices or [
            ("", _("No group question"))
        ]
        _apply_subevent_choices(self.fields["subevent"], subevent_choices)
