# service/forms.py
from django import forms

from .models import Bike, CustomerProfile, ServiceOrder, Ticket, TicketMessage


class CustomerQuickCreateForm(forms.Form):
    full_name = forms.CharField(label="Meno a priezvisko", max_length=200)
    email = forms.EmailField(label="E-mail")
    phone_number = forms.CharField(
        label="Telefónne číslo", max_length=50, required=False
    )

    bike_brand = forms.CharField(label="Bicykel značka", max_length=120, required=False)
    bike_model = forms.CharField(label="Bicykel model", max_length=120, required=False)
    bike_serial_number = forms.CharField(
        label="Sériové číslo", max_length=120, required=False
    )


# spätná kompatibilita pre starší import vo views.py
QuickCustomerWithBikeForm = CustomerQuickCreateForm


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = CustomerProfile
        fields = ["full_name", "email", "phone_number"]


class BikeCreateForm(forms.ModelForm):
    class Meta:
        model = Bike
        fields = ["customer", "brand", "model", "serial_number"]


class ServiceOrderCreateForm(forms.ModelForm):
    class Meta:
        model = ServiceOrder
        fields = ["bike", "status", "issue_description", "work_done", "price"]


class ServiceOrderUpdateForm(forms.ModelForm):
    class Meta:
        model = ServiceOrder
        fields = ["status", "issue_description", "work_done", "price"]


# spätná kompatibilita ak niekde používaš starší názov
ServiceOrderUpdateFormAdmin = ServiceOrderUpdateForm


class TicketCreateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["subject"]


class TicketMessageForm(forms.ModelForm):
    class Meta:
        model = TicketMessage
        fields = ["message"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 4}),
        }
