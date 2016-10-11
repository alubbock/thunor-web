from django.shortcuts import render, redirect
from django.template.response import TemplateResponse
from django.contrib import auth
from .forms import CentredAuthForm


def _handle_login(request):
    if request.method == 'POST':
        form = CentredAuthForm(data=request.POST)
        if form.is_valid():
            auth.login(request, form.get_user())
            return redirect('pyhts:home')
    else:
        form = CentredAuthForm()
    return render(request, 'registration/login.html', {'form': form})


def home(request):
    if not request.user.is_authenticated:
        return _handle_login(request)

    return render(request, 'home.html')


def logout(request):
    auth.logout(request)
    return redirect('pyhts:home')


def plate_designer(request):
    response = TemplateResponse(request, 'plate_designer.html', {
        'rows': map(chr, range(65, 65+18)),
        'cols': range(1, 25),
    })
    return response
