from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Submit, Layout
from crispy_forms.bootstrap import FormActions
from django.contrib.auth.forms import AuthenticationForm


class CentredAuthForm(AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super(CentredAuthForm, self).__init__(request, *args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_class = 'form-vertical'
        self.helper.layout = Layout(
            Field('username', placeholder='Email address'),
            Field('password', placeholder='Password'),
            FormActions(
                Submit('submit', 'Log in', css_class="btn-primary"),
            )
        )
        self.helper.form_show_labels = False
