"""Where the operator answers the requests.

Registered on `admin.site`, which `config/urls.py` has already turned into an
`OTPAdminSite` — so approving somebody needs the second factor like everything
else in there. Nothing about this app weakens that.
"""

from django.contrib import admin, messages
from django.contrib.admin.widgets import AdminTextareaWidget
from django.utils import timezone

from .emails import send_creator_validation_decision_email
from .models import CreatorValidation

# What the two free-text columns say for a row the operator creates by hand and leaves them
# empty in. The request itself was written in a Tally form and lives there (see `tally.py`);
# the operator may copy its two answers here, and when they do not, an explicit marker reads
# better in the list and in the edit form than two empty cells would — and needs no
# migration to allow them.
SENT_THROUGH_TALLY = "(enviado por Tally)"


@admin.register(CreatorValidation)
class CreatorValidationAdmin(admin.ModelAdmin):
    """Where the operator answers — and, since requests arrive through Tally, opens a row.

    A request is written in a Tally form now, not in a page of ours, so there is nothing
    in this table until the operator makes a row for the person: **Add**, find the account
    by its email (autocomplete: `core.UserAdmin` searches `email`), copy the two answers
    from Tally into Who and Intent, pick the status and, if useful, a note. The row is the
    record the policy reads, and the answers copied into it keep why each decision was
    taken in the database and not only in a third party's service. Left empty they say
    `SENT_THROUGH_TALLY`. They are the operator's copy, so they can be corrected afterwards
    and the admin's History keeps each change; changing them mails nobody. The answer —
    the actions below, or a status chosen on the form — is mailed to the person as it
    always was.
    """

    list_display = ("user", "status", "created", "resolved")
    list_filter = ("status", "created")
    search_fields = ("user__email", "user__name", "who", "intent")
    autocomplete_fields = ("user",)
    # Once a row exists, the account and the two moments are its own and are not editable
    # here. The two answers are: they are the operator's copy of what was written in Tally,
    # a copy can have a typo, and the History of this admin records every change to it.
    # (A new row has nothing to protect: see `get_readonly_fields`.)
    readonly_fields = ("user", "created", "resolved")
    fields = ("user", "who", "intent", "status", "note", "created", "resolved")
    ordering = ("-created",)
    actions = ("approve", "reject")

    def get_fields(self, request, obj=None):
        """A new row asks for the person, the two answers, the status and a note.

        The timestamps are the row's own to fill.
        """
        if obj is None:
            return ("user", "who", "intent", "status", "note")
        return super().get_fields(request, obj)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """The two answers are paragraphs, not a line: a textarea, with the column's limit."""
        if db_field.name in ("who", "intent"):
            kwargs["widget"] = AdminTextareaWidget(attrs={"rows": 3})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        """On a new row the two answers are optional; once the row exists they are not.

        The columns are not `blank=True` and no migration is made for it, so the
        relaxation is the form's: left empty, they are filled in with
        `SENT_THROUGH_TALLY` (`save_model`). An existing row's answers stay required, so a
        correction cannot blank one by accident.
        """
        form = super().get_form(request, obj, **kwargs)
        if obj is None:
            for name in ("who", "intent"):
                form.base_fields[name].required = False
        return form

    def get_readonly_fields(self, request, obj=None):
        """Everything is editable on a new row (the person to choose), as before after it."""
        if obj is None:
            return ()
        return super().get_readonly_fields(request, obj)

    def save_model(self, request, obj, form, change):
        """Fill a hand-made row in, and announce a decision made on the form.

        A row created here with no answers typed in is marked as sent through Tally. And
        **a status chosen on the form is a decision like an action's**: it
        stamps when, and the person is told — a new row made already approved, or a
        refusal turned into a yes. Changing only the note, or leaving the status as it
        was, is nobody's business but the operator's. Moving back to pending clears the
        stamp, as the old request page did when somebody asked again.

        ``resolved`` is set here rather than through ``resolve()``, which would also
        blank the note the operator has just typed.
        """
        if not change:
            obj.who = obj.who or SENT_THROUGH_TALLY
            obj.intent = obj.intent or SENT_THROUGH_TALLY
        decided = "status" in form.changed_data and obj.status != CreatorValidation.Status.PENDING
        if decided:
            obj.resolved = timezone.now()
        elif obj.status == CreatorValidation.Status.PENDING:
            obj.resolved = None
        super().save_model(request, obj, form, change)
        if decided:
            send_creator_validation_decision_email(obj)

    @admin.action(
        description="Approve — grant community collections, lending, renting and reservations"
    )
    def approve(self, request, queryset):
        self._resolve(request, queryset, CreatorValidation.Status.APPROVED)

    @admin.action(description="Reject")
    def reject(self, request, queryset):
        self._resolve(request, queryset, CreatorValidation.Status.REJECTED)

    def _resolve(self, request, queryset, status):
        """One at a time on purpose — `resolve()` stamps each row's own moment.

        A bulk `queryset.update()` would be one query, and would also skip the
        timestamp and let somebody approve fifty requests without reading one.
        The whole point of this table is that a person read a sentence.

        **The answer is mailed from here**, which is where the answer happens.
        Only when the status actually changed: re-running the action over rows
        that already say what you just told them is how a second click becomes a
        second email, and the row that did not move has nothing new to announce.
        """
        told = 0
        for validation in queryset:
            changed = validation.status != status
            validation.resolve(status)
            if changed:
                send_creator_validation_decision_email(validation)
                told += 1
        self.message_user(
            request,
            f"{queryset.count()} request(s) marked {status}; {told} answered by email.",
            messages.SUCCESS,
        )
