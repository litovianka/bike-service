from django import forms
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect
from django.db import transaction

from .models import CustomerProfile, Bike, ServiceOrder


# Pomocná funkcia – či je user admin / personál
def _is_staff(user):
    return user.is_staff or user.is_superuser


# ---------- FORMULÁRE ----------


class CustomerWithBikeForm(forms.Form):
    full_name = forms.CharField(
        label="Meno a priezvisko",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    email = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(attrs={"class": "form-control"})
    )
    phone = forms.CharField(
        label="Telefónne číslo",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    bike_name = forms.CharField(
        label="Bicykel (model / názov)",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    bike_serial = forms.CharField(
        label="Sériové číslo (S/N) – nepovinné",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )


class ServiceOrderCreateForm(forms.Form):
    bike = forms.ModelChoiceField(
        label="Bicykel",
        queryset=Bike.objects.select_related("customer").all(),
        widget=forms.Select(attrs={"class": "form-select"})
    )
    description = forms.CharField(
        label="Nahlásená vada",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Zobrazíme zákazníka + bike v selecte
        self.fields["bike"].label_from_instance = (
            lambda obj: f"{obj.customer.full_name} – {obj}"
        )


# ---------- VIEW: nový zákazník + prvý bicykel ----------


@login_required
@user_passes_test(_is_staff)
@transaction.atomic
def create_customer_with_bike(request):
    """
    Admin view:
    - vytvorí CustomerProfile (meno, email, telefón)
    - vytvorí k nemu jeden Bike (bicykel + S/N)
    Po uložení sa presmeruje na servisný panel.
    """
    if request.method == "POST":
        form = CustomerWithBikeForm(request.POST)
        if form.is_valid():
            # 1) Customer
            customer = CustomerProfile.objects.create(
                full_name=form.cleaned_data["full_name"],
                email=form.cleaned_data["email"],
                phone=form.cleaned_data["phone"],
            )

            # 2) Bike – ošetríme rôzne názvy polí v modeli
            bike = Bike(customer=customer)

            bike_fields = {f.name for f in Bike._meta.get_fields()}

            bike_name = form.cleaned_data["bike_name"]
            bike_serial = form.cleaned_data["bike_serial"]

            # názov bicykla
            if "name" in bike_fields:
                setattr(bike, "name", bike_name)
            elif "model" in bike_fields:
                setattr(bike, "model", bike_name)

            # sériové číslo
            if "serial_number" in bike_fields:
                setattr(bike, "serial_number", bike_serial)

            bike.save()

            return redirect("service_panel")
    else:
        form = CustomerWithBikeForm()

    return render(
        request,
        "admin_create_customer.html",
        {"form": form},
    )


# ---------- VIEW: nová servisná zákazka ----------


@login_required
@user_passes_test(_is_staff)
def create_service_order(request):
    """
    Admin view:
    - vytvorí novú servisnú zákazku pre vybraný bicykel
    - používa jedno univerzálne textové pole na 'nahlásenú vadu'
    Po uložení presmeruje na detail / úpravu servisnej zákazky.
    """
    if request.method == "POST":
        form = ServiceOrderCreateForm(request.POST)
        if form.is_valid():
            bike = form.cleaned_data["bike"]
            desc = form.cleaned_data["description"]

            order = ServiceOrder(bike=bike)

            # priradíme text do správneho poľa podľa modelu
            if hasattr(order, "description"):
                order.description = desc
            elif hasattr(order, "reported_issue"):
                order.reported_issue = desc

            order.save()

            # predpokladám, že názov url na detail je 'service_order_admin_detail'
            return redirect("service_order_admin_detail", order_id=order.id)
    else:
        form = ServiceOrderCreateForm()

    return render(
        request,
        "admin_create_service_order.html",
        {"form": form},
    )