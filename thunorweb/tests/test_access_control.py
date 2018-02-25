from django.test import TestCase, Client, override_settings
from django.urls import reverse

HTTP_OK = 200


class TestAccessControl(TestCase):
    def setUp(self):
        self.client = Client()

    @override_settings(LOGIN_REQUIRED=True)
    def test_access_home(self):
        response = self.client.get(reverse('thunorweb:home'))

        self.assertRedirects(response, '{}?next={}'.format(
            reverse('account_login'), reverse('thunorweb:home')))

    @override_settings(LOGIN_REQUIRED=False)
    def test_access_home_anon(self):
        response = self.client.get(reverse('thunorweb:home'))
        self.assertEqual(response.status_code, HTTP_OK)
