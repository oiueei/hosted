"""The two questions this deployment asks before handing out the wider product."""

from django import forms

from .models import CreatorValidation


class RequestAccessForm(forms.ModelForm):
    """Two free-text answers, and deliberately nothing else.

    The temptation is a tidy form — a dropdown of collection types, a checkbox
    for "I have read the rules" — and it would collect nothing worth reading.
    **The answer in somebody's own words is the filter**; a form that can be
    completed without writing a sentence is a form that lets everyone through
    while looking like a gate.
    """

    class Meta:
        model = CreatorValidation
        fields = ["who", "intent"]
        labels = {
            "who": "Who are you?",
            "intent": "What are you planning to run here?",
        }
        help_texts = {
            "who": "A couple of lines is plenty. Where you are, what you do, who you do it with.",
            "intent": (
                "The group you have in mind and what would be shared in it — "
                "and, if you mean to lend or rent, what sort of things."
            ),
        }
        widgets = {
            "who": forms.Textarea(attrs={"rows": 4, "maxlength": 512}),
            "intent": forms.Textarea(attrs={"rows": 6, "maxlength": 1024}),
        }

    def clean_who(self):
        return self._require_a_sentence("who")

    def clean_intent(self):
        return self._require_a_sentence("intent")

    def _require_a_sentence(self, field):
        """Refuse the empty gesture — "hi", "..." — that answers nothing.

        Not a quality bar: a short honest answer passes. It is the difference
        between a request somebody can decide on and one they would have to
        write back about, which wastes the asker's time more than ours.
        """
        value = (self.cleaned_data.get(field) or "").strip()
        if len(value) < 20:
            raise forms.ValidationError(
                "Tell us a little more — a sentence or two is enough to go on."
            )
        return value
