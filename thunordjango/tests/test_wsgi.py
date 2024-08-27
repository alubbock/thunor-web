from django.test import RequestFactory
from django.test import TestCase

from thunordjango.wsgi import application


class TestHandler(TestCase):
    def test_handles_request(self):
        rf = RequestFactory()
        application.resolve_request(rf.get("/"))
