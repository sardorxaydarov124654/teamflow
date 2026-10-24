import re
from datetime import date

from django import forms


def luhn_valid(number: str) -> bool:
    total, flip = 0, False
    for ch in reversed(number):
        d = int(ch)
        if flip:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        flip = not flip
    return total % 10 == 0


def detect_brand(number: str) -> str:
    if number.startswith("8600"):
        return "Uzcard"
    if number.startswith("9860"):
        return "Humo"
    if number.startswith("4"):
        return "Visa"
    if re.match(r"^(5[1-5]|2(2[2-9]|[3-6]\d|7[01]|720))", number):
        return "Mastercard"
    if number.startswith(("34", "37")):
        return "Amex"
    return "Card"


class CardForm(forms.Form):
    """Card details. Validated in memory only — see PaymentMethod for what is stored."""

    card_number = forms.CharField(
        label="Card number",
        max_length=23,
        widget=forms.TextInput(
            attrs={"inputmode": "numeric", "autocomplete": "cc-number",
                   "placeholder": "0000 0000 0000 0000", "data-card-number": ""}
        ),
    )
    holder_name = forms.CharField(
        label="Cardholder name", max_length=120,
        widget=forms.TextInput(attrs={"autocomplete": "cc-name", "placeholder": "AS ON CARD"}),
    )
    expiry = forms.CharField(
        label="Expiry (MM/YY)", max_length=5,
        widget=forms.TextInput(
            attrs={"inputmode": "numeric", "autocomplete": "cc-exp",
                   "placeholder": "MM/YY", "data-card-expiry": ""}
        ),
    )
    cvv = forms.CharField(
        label="CVV / CVC", max_length=4,
        widget=forms.PasswordInput(
            attrs={"inputmode": "numeric", "autocomplete": "cc-csc", "placeholder": "•••"},
            render_value=False,
        ),
    )

    def clean_card_number(self):
        number = re.sub(r"[\s-]", "", self.cleaned_data["card_number"])
        if not number.isdigit() or not 13 <= len(number) <= 19:
            raise forms.ValidationError("Enter a valid card number.")
        if not luhn_valid(number):
            raise forms.ValidationError("This card number is not valid.")
        return number

    def clean_expiry(self):
        value = self.cleaned_data["expiry"].strip()
        m = re.match(r"^(\d{1,2})\s*/\s*(\d{2}|\d{4})$", value)
        if not m:
            raise forms.ValidationError("Use the MM/YY format.")
        month, year = int(m.group(1)), int(m.group(2))
        if year < 100:
            year += 2000
        if not 1 <= month <= 12:
            raise forms.ValidationError("Month must be between 01 and 12.")
        today = date.today()
        if (year, month) < (today.year, today.month):
            raise forms.ValidationError("This card has expired.")
        return month, year

    def clean_cvv(self):
        cvv = self.cleaned_data["cvv"].strip()
        if not cvv.isdigit() or len(cvv) not in (3, 4):
            raise forms.ValidationError("CVV must be 3 or 4 digits.")
        return cvv

    def clean_holder_name(self):
        return self.cleaned_data["holder_name"].strip().upper()

    def save_for(self, company):
        """Persist ONLY the safe fields; the number and CVV are dropped here."""
        from .models import PaymentMethod

        number = self.cleaned_data["card_number"]
        month, year = self.cleaned_data["expiry"]
        method, _ = PaymentMethod.objects.update_or_create(
            company=company,
            defaults={
                "holder_name": self.cleaned_data["holder_name"],
                "brand": detect_brand(number),
                "last4": number[-4:],
                "exp_month": month,
                "exp_year": year,
            },
        )
        return method
