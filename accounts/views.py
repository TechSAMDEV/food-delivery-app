from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import CustomerRegistrationForm, StaffRegistrationForm, UserAddressForm


@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('store:menu_list')

    form = CustomerRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('store:menu_list')

    return render(request, 'registration/register.html', {'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def staff_register_view(request):
    if not (request.user.is_superuser or request.user.role == 'ADMIN'):
        return HttpResponseForbidden('Administrator access is required.')

    form = StaffRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(
            request,
            f'{user.get_role_display()} account "{user.username}" was created.',
        )
        return redirect('staff_register')

    return render(request, 'registration/staff_register.html', {'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def address_list_view(request):
    form = UserAddressForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        address = form.save(request.user)
        messages.success(request, f'Address "{address.address_line}" was saved.')
        return redirect('address_list')

    return render(request, 'registration/addresses.html', {
        'form': form,
        'addresses': request.user.addresses.order_by('-is_default', '-created_at'),
    })
