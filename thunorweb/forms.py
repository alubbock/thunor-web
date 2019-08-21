from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from allauth.account import forms as allauth_forms
from django import forms, VERSION
from django.contrib.auth import get_user_model
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.models import Group


class CentredAuthForm(allauth_forms.LoginForm):
    def __init__(self, *args, **kwargs):
        super(CentredAuthForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_class = 'form-vertical'
        self.helper.add_input(Submit('submit', 'Log in',
                                     css_class='btn-block'))


class AddEmailForm(allauth_forms.AddEmailForm):
    def __init__(self, *args, **kwargs):
        super(AddEmailForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_class = 'form-vertical'
        self.helper.add_input(Submit('action_add', 'Add email'))


class ResetPasswordForm(allauth_forms.ResetPasswordForm):
    def __init__(self, *args, **kwargs):
        super(ResetPasswordForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_class = 'form-vertical'
        self.helper.add_input(Submit('submit', 'Submit'))


class SetPasswordFrom(allauth_forms.SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super(SetPasswordFrom, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_class = 'form-vertical'
        self.helper.add_input(Submit('submit', 'Change password'))


class ResetPasswordKeyForm(allauth_forms.ResetPasswordKeyForm):
    def __init__(self, *args, **kwargs):
        super(ResetPasswordKeyForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_class = 'form-vertical'
        self.helper.add_input(Submit('submit', 'Change password'))


class ChangePasswordForm(allauth_forms.ChangePasswordForm):
    def __init__(self, *args, **kwargs):
        super(ChangePasswordForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_class = 'form-vertical'
        self.helper.add_input(Submit('submit', 'Change password'))


class SignUpForm(allauth_forms.SignupForm):
    def __init__(self, *args, **kwargs):
        super(SignUpForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.fields['email'].widget.attrs.update({'autofocus': 'autofocus'})
        self.helper.form_class = 'form-vertical'
        self.helper.add_input(Submit('submit', 'Sign Up',
                                     css_class='btn-block'))


class GroupAdminForm(forms.ModelForm):
    class Meta:
        model = Group
        exclude = []

    # Add list of users to group selection form
    users = forms.ModelMultipleChoiceField(
         queryset=get_user_model().objects.all(),
         required=False,
         widget=FilteredSelectMultiple('users', False,
                                       attrs={'readonly': True}),
         label='Users'
    )

    def __init__(self, *args, **kwargs):
        super(GroupAdminForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['users'].initial = self.instance.user_set.all()

    def save_m2m(self):
        self.instance.user_set.set(self.cleaned_data['users'])

    def save(self, *args, **kwargs):
        instance = super(GroupAdminForm, self).save()
        self.save_m2m()
        return instance
