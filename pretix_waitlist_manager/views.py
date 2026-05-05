from django.contrib import messages
from django.http import HttpResponseRedirect, JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import RedirectView, TemplateView, View

from pretix.control.permissions import EventPermissionRequiredMixin

from .forms import WaitlistImportForm, WaitlistRandomizeForm
from .services import (
    PretixDataProvider,
    WaitlistMembershipImporter,
    WaitlistRandomizer,
    build_group_question_choices,
    build_membership_type_choices,
    build_question_answer_choices,
    build_question_choices,
    build_subevent_choices,
    build_target_product_choices,
    parse_target_choice,
)
from .service_helpers import value


SECTION_SEND = "send"
SECTION_IMPORT = "import"
SECTION_RANDOMIZE = "randomize"
PREVIEW_ERROR = _("Preview could not be loaded for the current selection.")


def _positive_int(value, default: int = 1) -> int:
    """Return a sanitized positive integer.

    Args:
        value: Raw request value to parse.
        default: Fallback used for missing, invalid, or non-positive input.
    Returns:
        A positive integer suitable for pagination.
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default

class WaitlistManagerFormsMixin:
    """Build waitlist-manager forms, choices, and shared request helpers."""

    @property
    def provider(self) -> PretixDataProvider:
        """Return the data provider used by views in this request.

        Args:
            None.
        Returns:
            A new `PretixDataProvider` instance.
        """
        return PretixDataProvider()

    def _selected_value(
        self,
        *,
        field: str,
        data,
        initial,
        choices: list[tuple[str, str]],
        prefix: str,
    ) -> str:
        """Resolve one field value from bound data, initial data, or defaults.

        Args:
            field: Field name without prefix.
            data: Optional bound form data.
            initial: Optional initial form values.
            choices: Available field choices.
            prefix: Form prefix used in request data.
        Returns:
            The selected string value for the field.
        """
        if data:
            value_ = data.get(f"{prefix}-{field}")
            if value_ is not None:
                return value_
        if initial and initial.get(field) is not None:
            return str(initial[field])
        return choices[0][0] if choices else ""

    def _import_question_choices(
        self,
        organizer,
        event,
        membership_type_id: str | int | None,
    ) -> tuple[list[tuple[str, str]], dict[str, list[tuple[str, str]]]]:
        """Build import question and answer choices for one membership type.

        Args:
            organizer: Organizer owning the membership and answer queries.
            event: Event whose order answers should be searched.
            membership_type_id: Selected membership type id.
        Returns:
            Question choices and per-question answer choices.
        """
        if not membership_type_id:
            return build_question_choices([]), build_question_answer_choices([])

        memberships = self.provider.list_memberships(
            organizer,
            int(membership_type_id),
            event,
            include_testmode=True,
        )
        customer_ids = sorted(
            {
                value(value(membership, "customer"), "identifier")
                for membership in memberships
                if value(value(membership, "customer"), "identifier")
            }
        )
        answered_questions = self.provider.list_answered_import_questions(
            organizer,
            event,
            customer_ids,
        )
        return (
            build_question_choices(answered_questions),
            build_question_answer_choices(answered_questions),
        )

    def _randomize_group_question_choices(
        self,
        organizer,
        event,
        target_value: str | None,
        subevent_value: str | None,
    ) -> list[tuple[str, str]]:
        """Build group-question choices for one waitlist selection.

        Args:
            organizer: Organizer owning the waitlist and answer queries.
            event: Event whose waiting list and answers should be searched.
            target_value: Serialized waitlist target value.
            subevent_value: Serialized subevent id, if any.
        Returns:
            Group-question choices for the selected waitlist target.
        """
        if not target_value:
            return build_group_question_choices([])

        target = parse_target_choice(target_value)
        subevent_id = int(subevent_value) if subevent_value else None
        entries = self.provider.list_waiting_list_entries(
            organizer,
            event,
            item=target.item_id,
            variation=target.variation_id,
            subevent=subevent_id,
        )
        emails = sorted(
            {
                (value(entry, "email") or "").strip()
                for entry in entries
                if value(entry, "email")
            }
        )
        questions = self.provider.list_answered_group_questions(
            organizer,
            event,
            emails,
        )
        return build_group_question_choices(questions)

    def _resource_choices(self) -> dict[str, object]:
        """Collect all select-box choices required by the manager UI.

        Args:
            None. The organizer and event are read from `self.request`.
        Returns:
            A dict of form-choice lists keyed by field group.
        """
        cache = getattr(self, "_resource_choices_cache", None)
        if cache is not None:
            return cache

        organizer = self.request.organizer
        event = self.request.event

        membership_types = self.provider.list_membership_types(organizer)
        items = self.provider.list_waitlist_items(event)
        subevents = self.provider.list_subevents(event) if event.has_subevents else []

        variations_by_item = {}
        for item in items:
            if item.has_variations:
                variations_by_item[item.id] = self.provider.list_variations(item)

        target_choices = build_target_product_choices(items, variations_by_item)
        subevent_choices = build_subevent_choices(subevents)

        cache = {
            "membership_type_choices": build_membership_type_choices(membership_types),
            "target_choices": target_choices,
            "subevent_choices": subevent_choices,
        }
        self._resource_choices_cache = cache
        return cache

    def _default_initials(
        self, choices: dict[str, object]
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Build default form selections from the first available choice.

        Args:
            choices: Output from `_resource_choices`.
        Returns:
            A pair of initial-data dicts for the import and randomize forms.
        """
        import_initial = {}
        randomize_initial = {}
        membership_type_choices = choices["membership_type_choices"]
        if membership_type_choices:
            import_initial["membership_type"] = membership_type_choices[0][0]
        import_initial["question"] = ""
        import_initial["answer"] = ""
        for field in ("target", "subevent"):
            choice_key = f"{field}_choices"
            if choices[choice_key]:
                selected = choices[choice_key][0][0]
                import_initial[field] = selected
                randomize_initial[field] = selected
        randomize_initial["group_question"] = ""
        return import_initial, randomize_initial

    def get_import_form(self, data=None, initial=None):
        """Build the import form for GET or POST handling.

        Args:
            data: Optional bound form data.
            initial: Optional initial field values.
        Returns:
            A configured `WaitlistImportForm`.
        """
        choices = self._resource_choices()
        membership_type_id = self._selected_value(
            field="membership_type",
            data=data,
            initial=initial,
            choices=choices["membership_type_choices"],
            prefix="import",
        )
        question_choices, answer_choices_by_question = self._import_question_choices(
            self.request.organizer,
            self.request.event,
            membership_type_id,
        )
        form = WaitlistImportForm(
            data=data,
            prefix="import",
            initial=initial,
            membership_type_choices=choices["membership_type_choices"],
            question_choices=question_choices,
            answer_choices_by_question=answer_choices_by_question,
            target_choices=choices["target_choices"],
            subevent_choices=choices["subevent_choices"],
        )
        form.waitlist_manager_question_choices = question_choices
        form.waitlist_manager_answer_choices_by_question = answer_choices_by_question
        return form

    def get_randomize_form(self, data=None, initial=None):
        """Build the randomize form for GET or POST handling.

        Args:
            data: Optional bound form data.
            initial: Optional initial field values.
        Returns:
            A configured `WaitlistRandomizeForm`.
        """
        choices = self._resource_choices()
        target_value = self._selected_value(
            field="target",
            data=data,
            initial=initial,
            choices=choices["target_choices"],
            prefix="randomize",
        )
        subevent_value = self._selected_value(
            field="subevent",
            data=data,
            initial=initial,
            choices=choices["subevent_choices"],
            prefix="randomize",
        )
        form = WaitlistRandomizeForm(
            data=data,
            prefix="randomize",
            initial=initial,
            target_choices=choices["target_choices"],
            subevent_choices=choices["subevent_choices"],
            group_question_choices=self._randomize_group_question_choices(
                self.request.organizer,
                self.request.event,
                target_value,
                subevent_value if self.request.event.has_subevents else "",
            ),
        )
        form.waitlist_manager_group_question_choices = list(
            form.fields["group_question"].choices
        )
        return form

    def _optional_int(self, value: str | None) -> int | None:
        """Convert an optional form value to an integer.

        Args:
            value: Raw string value from cleaned form data.
        Returns:
            An integer when the value is present, otherwise `None`.
        """
        return int(value) if value else None

    def _run_import(self, form):
        """Execute an import request and emit the matching UI message.

        Args:
            form: A validated `WaitlistImportForm`.
        Returns:
            The `ImportResult` returned by the importer service.
        """
        importer = WaitlistMembershipImporter(self.provider)
        target = parse_target_choice(form.cleaned_data["target"])
        result = importer.run(
            organizer=self.request.organizer,
            event=self.request.event,
            membership_type_id=int(form.cleaned_data["membership_type"]),
            email_filter=form.cleaned_data.get("email"),
            question_id=self._optional_int(form.cleaned_data.get("question")),
            option_id=self._optional_int(form.cleaned_data.get("answer")),
            target=target,
            subevent_id=self._optional_int(form.cleaned_data.get("subevent")),
            exclude_paid_tickets=form.cleaned_data["exclude_paid_tickets"],
            include_testmode=form.cleaned_data["include_testmode"],
            dry_run=form.cleaned_data["dry_run"],
            user=self.request.user,
        )
        if form.cleaned_data["dry_run"]:
            messages.info(
                self.request,
                _("Dry run completed. No waitlist entries were created."),
            )
        else:
            messages.success(
                self.request,
                _("Import completed. %(count)s waitlist entries were created.")
                % {"count": result.added_count},
            )
        return result

    def _run_randomize(self, form):
        """Execute a waitlist randomization and emit a success message.

        Args:
            form: A validated `WaitlistRandomizeForm`.
        Returns:
            The `RandomizationResult` returned by the randomizer service.
        """
        randomizer = WaitlistRandomizer(self.provider)
        target = parse_target_choice(form.cleaned_data["target"])
        result = randomizer.run(
            organizer=self.request.organizer,
            event=self.request.event,
            target=target,
            subevent_id=self._optional_int(form.cleaned_data.get("subevent")),
            cutoff_date=form.cleaned_data.get("cutoff_date"),
            group_question_id=self._optional_int(
                form.cleaned_data.get("group_question")
            ),
            seed=form.cleaned_data.get("seed"),
            user=self.request.user,
        )
        messages.success(
            self.request,
            _(
                "Randomization completed. %(count)s waitlist entries were updated."
            )
            % {"count": result.updated_entries},
        )
        return result

    def _waitinglist_url(self) -> str:
        """Build the canonical event waiting-list URL.

        Args:
            None. The organizer and event are read from `self.request`.
        Returns:
            The absolute path for pretix's waiting-list control page.
        """
        return reverse(
            "control:event.orders.waitinglist",
            kwargs={
                "event": self.request.event.slug,
                "organizer": self.request.organizer.slug,
            },
        )

    def _plugin_url(self, name: str) -> str:
        """Resolve a plugin route for the current event.

        Args:
            name: Plugin route name relative to `pretix_waitlist_manager`.
        Returns:
            The absolute path for the requested plugin route.
        """
        return reverse(
            f"plugins:pretix_waitlist_manager:{name}",
            kwargs={
                "event": self.request.event.slug,
                "organizer": self.request.organizer.slug,
            },
        )

    def _manager_url(self, section: str) -> str:
        """Resolve the URL for one waitlist-management section.

        Args:
            section: One of the `SECTION_*` constants.
        Returns:
            The absolute path for the selected manager section.
        """
        if section == SECTION_SEND:
            return self._waitinglist_url()
        route_name = {
            SECTION_IMPORT: "import_page",
            SECTION_RANDOMIZE: "randomize_page",
        }[section]
        return self._plugin_url(route_name)

    def _manager_redirect(self, section: str) -> HttpResponseRedirect:
        """Redirect to one waitlist-management section page.

        Args:
            section: One of the `SECTION_*` constants.
        Returns:
            An `HttpResponseRedirect` to the selected section.
        """
        return HttpResponseRedirect(self._manager_url(section))

    def build_manager_context(self, *, import_form=None, randomize_form=None):
        """Build template context for one manager page.

        Args:
            import_form: Optional prebuilt import form.
            randomize_form: Optional prebuilt randomize form.
        Returns:
            A context dict with forms and action/preview URLs.
        """
        choices = self._resource_choices()
        import_initial, randomize_initial = self._default_initials(choices)
        import_form = import_form or self.get_import_form(initial=import_initial)
        randomize_form = randomize_form or self.get_randomize_form(
            initial=randomize_initial
        )
        context = {
            "import_form": import_form,
            "randomize_form": randomize_form,
            "import_preview_url": self._plugin_url("import_preview"),
            "import_options_url": self._plugin_url("import_options"),
            "randomize_preview_url": self._plugin_url("randomize_preview"),
            "randomize_options_url": self._plugin_url("randomize_options"),
            "import_action_url": self._plugin_url("run_import"),
            "randomize_action_url": self._plugin_url("run_randomize"),
        }
        return context


class WaitlistManagerView(EventPermissionRequiredMixin, RedirectView):
    """Redirect the legacy plugin URL into the import page."""

    permission = "event.orders:read"
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        """Build the redirect target for the legacy manager route.

        Args:
            *args: Unused redirect-view positional arguments.
            **kwargs: Unused redirect-view keyword arguments.
        Returns:
            The waitlist-manager import page URL.
        """
        helper = WaitlistManagerFormsMixin()
        helper.request = self.request
        return helper._manager_url(SECTION_IMPORT)


class WaitlistManagerPageView(
    EventPermissionRequiredMixin, WaitlistManagerFormsMixin, TemplateView
):
    """Render one full waitlist-manager page."""

    permission = "event.orders:write"

    def get_context_data(self, **kwargs):
        """Build page context for one manager section.

        Args:
            **kwargs: Base template context from Django's `TemplateView`.
        Returns:
            A context dict for the selected manager page.
        """
        context = super().get_context_data(**kwargs)
        context.update(self.build_manager_context())
        return context


class WaitlistImportPageView(WaitlistManagerPageView):
    """Render the full import page."""

    template_name = "pretix_waitlist_manager/import_page.html"


class WaitlistRandomizePageView(WaitlistManagerPageView):
    """Render the full randomize page."""

    template_name = "pretix_waitlist_manager/randomize_page.html"


class WaitlistImportOptionsView(
    EventPermissionRequiredMixin, WaitlistManagerFormsMixin, View
):
    """Return import question and answer choices for one membership type."""

    permission = "event.orders:read"

    def get(self, request, *args, **kwargs):
        """Render import options as JSON for asynchronous select loading.

        Args:
            request: The incoming Django request.
            *args: Unused view positional arguments.
            **kwargs: Unused view keyword arguments.
        Returns:
            A `JsonResponse` containing question and answer choices.
        """
        membership_type_id = request.GET.get("membership_type")
        question_choices, answer_choices_by_question = self._import_question_choices(
            request.organizer,
            request.event,
            membership_type_id,
        )
        return JsonResponse(
            {
                "question_choices": question_choices,
                "answer_choices_by_question": answer_choices_by_question,
            }
        )


class WaitlistRandomizeOptionsView(
    EventPermissionRequiredMixin, WaitlistManagerFormsMixin, View
):
    """Return randomize group-question choices for one waitlist selection."""

    permission = "event.orders:read"

    def get(self, request, *args, **kwargs):
        """Render randomize group-question choices as JSON.

        Args:
            request: The incoming Django request.
            *args: Unused view positional arguments.
            **kwargs: Unused view keyword arguments.
        Returns:
            A `JsonResponse` containing group-question choices.
        """
        target_value = request.GET.get("target")
        subevent_value = request.GET.get("subevent")
        choices = self._randomize_group_question_choices(
            request.organizer,
            request.event,
            target_value,
            subevent_value if request.event.has_subevents else "",
        )
        return JsonResponse({"group_question_choices": choices})


class WaitlistManagerActionView(EventPermissionRequiredMixin, WaitlistManagerFormsMixin, View):
    """Handle one POST-only manager action and return to its tab."""

    permission = "event.orders:write"
    error_message = ""
    section = ""

    def build_form(self, data, initial):
        """Build the bound form for this action view.

        Args:
            data: Submitted POST payload.
            initial: Initial values derived from available choices.
        Returns:
            A bound Django form for the action.
        """
        raise NotImplementedError

    def default_initial(self, choices):
        """Extract initial values for this action's form.

        Args:
            choices: Output from `_resource_choices`.
        Returns:
            A dict of initial values for the action form.
        """
        raise NotImplementedError

    def run_valid_form(self, form):
        """Execute the action for a validated form.

        Args:
            form: A validated action form.
        Returns:
            The service result produced by the action.
        """
        raise NotImplementedError

    def post(self, request, *args, **kwargs):
        """Validate, run, and redirect a manager POST action.

        Args:
            request: The incoming Django request.
            *args: Unused view positional arguments.
            **kwargs: Unused view keyword arguments.
        Returns:
            A redirect back to the tab associated with this action.
        """
        choices = self._resource_choices()
        form = self.build_form(
            data=request.POST,
            initial=self.default_initial(choices),
        )
        if form.is_valid():
            self.run_valid_form(form)
        else:
            messages.error(request, self.error_message)
        return self._manager_redirect(self.section)


class WaitlistImportRunView(WaitlistManagerActionView):
    """Persist imported members onto the selected waitlist."""

    error_message = _("The import form is incomplete or invalid.")
    section = SECTION_IMPORT

    def build_form(self, data, initial):
        """Build the bound import form.

        Args:
            data: Submitted POST payload.
            initial: Initial values derived from available choices.
        Returns:
            A bound `WaitlistImportForm`.
        """
        return self.get_import_form(data=data, initial=initial)

    def default_initial(self, choices):
        """Return the default initial values for the import action.

        Args:
            choices: Output from `_resource_choices`.
        Returns:
            The initial-value dict for the import form.
        """
        import_initial, _ = self._default_initials(choices)
        return import_initial

    def run_valid_form(self, form):
        """Run the import action for a validated form.

        Args:
            form: A validated `WaitlistImportForm`.
        Returns:
            The `ImportResult` produced by `_run_import`.
        """
        return self._run_import(form)


class WaitlistRandomizeRunView(WaitlistManagerActionView):
    """Persist randomized priorities for the selected waitlist."""

    error_message = _("The randomization form is incomplete or invalid.")
    section = SECTION_RANDOMIZE

    def build_form(self, data, initial):
        """Build the bound randomize form.

        Args:
            data: Submitted POST payload.
            initial: Initial values derived from available choices.
        Returns:
            A bound `WaitlistRandomizeForm`.
        """
        return self.get_randomize_form(data=data, initial=initial)

    def default_initial(self, choices):
        """Return the default initial values for the randomize action.

        Args:
            choices: Output from `_resource_choices`.
        Returns:
            The initial-value dict for the randomize form.
        """
        _, randomize_initial = self._default_initials(choices)
        return randomize_initial

    def run_valid_form(self, form):
        """Run the randomize action for a validated form.

        Args:
            form: A validated `WaitlistRandomizeForm`.
        Returns:
            The `RandomizationResult` produced by `_run_randomize`.
        """
        return self._run_randomize(form)


class WaitlistManagerPreviewView(
    EventPermissionRequiredMixin, WaitlistManagerFormsMixin, View
):
    """Render one AJAX preview panel for the manager UI."""

    permission = "event.orders:read"
    preview_template_name = ""
    include_seed = False

    def build_form(self, data):
        """Build the bound form for this preview.

        Args:
            data: Query-string payload for the preview request.
        Returns:
            A bound Django form.
        """
        raise NotImplementedError

    def build_preview_payload(self, request, form) -> dict[str, object]:
        """Build the preview payload for a validated preview form.

        Args:
            request: The incoming Django request.
            form: A validated preview form.
        Returns:
            A dict containing at least a `preview` object and optional extras.
        """
        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        """Render preview HTML and optional metadata as JSON.

        Args:
            request: The incoming Django request.
            *args: Unused view positional arguments.
            **kwargs: Unused view keyword arguments.
        Returns:
            A `JsonResponse` containing rendered preview HTML.
        """
        form = self.build_form(data=request.GET)
        payload: dict[str, object] = {"preview": None}
        if form.is_valid():
            payload.update(self.build_preview_payload(request, form))
            error = None
        else:
            error = PREVIEW_ERROR
        preview = payload.pop("preview")

        html = render_to_string(
            self.preview_template_name,
            {"preview": preview, "error": error},
            request=request,
        )
        response = {"html": html}
        response.update(payload)
        if self.include_seed and "seed" not in response:
            response["seed"] = None
        return JsonResponse(response)


class WaitlistImportPreviewView(WaitlistManagerPreviewView):
    """Render the membership-import preview panes."""

    preview_template_name = "pretix_waitlist_manager/import_preview.html"

    def build_form(self, data):
        """Build the bound import preview form.

        Args:
            data: Query-string payload for the preview request.
        Returns:
            A bound `WaitlistImportForm`.
        """
        return self.get_import_form(data=data)

    def build_preview_payload(self, request, form) -> dict[str, object]:
        """Build preview data for the import tab.

        Args:
            request: The incoming Django request.
            form: A validated `WaitlistImportForm`.
        Returns:
            A payload dict containing the import preview result.
        """
        return {
            "preview": WaitlistMembershipImporter(self.provider).preview(
                organizer=request.organizer,
                event=request.event,
                membership_type_id=int(form.cleaned_data["membership_type"]),
                email_filter=form.cleaned_data.get("email"),
                question_id=self._optional_int(form.cleaned_data.get("question")),
                option_id=self._optional_int(form.cleaned_data.get("answer")),
                target=parse_target_choice(form.cleaned_data["target"]),
                subevent_id=self._optional_int(form.cleaned_data.get("subevent")),
                exclude_paid_tickets=form.cleaned_data["exclude_paid_tickets"],
                include_testmode=form.cleaned_data["include_testmode"],
                import_page=_positive_int(request.GET.get("import_page")),
                current_waitlist_page=_positive_int(
                    request.GET.get("current_waitlist_page")
                ),
            ),
            "question_choices": list(form.waitlist_manager_question_choices),
            "answer_choices_by_question": form.waitlist_manager_answer_choices_by_question,
        }


class WaitlistRandomizePreviewView(WaitlistManagerPreviewView):
    """Render the randomization before/after preview panes."""

    preview_template_name = "pretix_waitlist_manager/randomize_preview.html"
    include_seed = True

    def build_form(self, data):
        """Build the bound randomize preview form.

        Args:
            data: Query-string payload for the preview request.
        Returns:
            A bound `WaitlistRandomizeForm`.
        """
        return self.get_randomize_form(data=data)

    def build_preview_payload(self, request, form) -> dict[str, object]:
        """Build preview data for the randomize tab.

        Args:
            request: The incoming Django request.
            form: A validated `WaitlistRandomizeForm`.
        Returns:
            A payload dict containing the preview result and active seed.
        """
        preview = WaitlistRandomizer(self.provider).preview(
            organizer=request.organizer,
            event=request.event,
            target=parse_target_choice(form.cleaned_data["target"]),
            subevent_id=self._optional_int(form.cleaned_data.get("subevent")),
            cutoff_date=form.cleaned_data.get("cutoff_date"),
            group_question_id=self._optional_int(
                form.cleaned_data.get("group_question")
            ),
            before_page=_positive_int(request.GET.get("before_page")),
            after_page=_positive_int(request.GET.get("after_page")),
            seed=form.cleaned_data.get("seed"),
        )
        return {
            "preview": preview,
            "seed": preview.seed,
            "group_question_choices": list(form.waitlist_manager_group_question_choices),
        }
