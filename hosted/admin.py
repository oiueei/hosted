"""Where the operator answers the requests.

Registered on `admin.site`, which `config/urls.py` has already turned into an
`OTPAdminSite` — so approving somebody needs the second factor like everything
else in there. Nothing about this app weakens that.
"""

from django.contrib import admin, messages

from .emails import send_creator_validation_decision_email
from .models import CreatorValidation


@admin.register(CreatorValidation)
class CreatorValidationAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "created", "resolved")
    list_filter = ("status", "created")
    search_fields = ("user__email", "user__name", "who", "intent")
    # The two answers are the whole decision, and they are not editable here:
    # this is a record of what somebody wrote, and an operator who could rewrite
    # it would be deciding on a version of the request that was never sent.
    readonly_fields = ("user", "who", "intent", "created", "resolved")
    fields = ("user", "who", "intent", "status", "note", "created", "resolved")
    ordering = ("-created",)
    actions = ("approve", "reject")

    @admin.action(description="Approve — grant community collections, lending and renting")
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
