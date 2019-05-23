from django.shortcuts import render, redirect, Http404
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.conf import settings
from guardian.shortcuts import ObjectPermissionChecker
from thunorweb.models import HTSDataset
from django.contrib import auth
from allauth.account.views import password_reset


def _assert_has_perm(request, dataset, perm_required):
    if dataset.deleted_date is not None:
        raise Http404()
    if not settings.LOGIN_REQUIRED and not \
            request.user.is_authenticated:
        anon_group = Group.objects.get(name='Public')
        anon_perm_checker = ObjectPermissionChecker(anon_group)
        if not anon_perm_checker.has_perm(perm_required, dataset):
            raise Http404()
    elif dataset.owner_id != request.user.id and not \
            request.user.has_perm(
                perm_required, dataset):
        raise Http404()


def login_required_unless_public(func):
    def wrap(*args, **kwargs):
        if settings.LOGIN_REQUIRED:
            return login_required(func)(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    return wrap


def handler404(request):
    if request.is_ajax():
        return JsonResponse({}, status=404)
    else:
        return render(request, 'error404.html', status=404)


def handler500(request):
    if request.is_ajax():
        return JsonResponse({'error': 'Internal server error'}, status=500)
    else:
        return render(request, 'error500.html', status=500)


@login_required_unless_public
def home(request):
    user_has_datasets = HTSDataset.objects.filter(
        owner=request.user.id, deleted_date=None).exists()
    return render(request, 'home.html', {'user_has_datasets':
                                         user_has_datasets,
                                         'back_link': False})


@login_required
def my_account(request):
    return render(request, 'my_account.html')


def reset_password(request):
    if settings.EMAIL_ENABLED:
        return password_reset(request)
    else:
        return render(request, 'password_reset_manually.html')


def logout(request):
    auth.logout(request)
    return redirect('thunorweb:home')
