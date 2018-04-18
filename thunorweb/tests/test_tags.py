from django.test import TestCase
from thunorweb.models import CellLine, Drug, CellLineTag, DrugTag
from django.contrib.auth import get_user_model
from django.urls import reverse


HTTP_OK = 200


class TestPlateMapper(TestCase):
    @classmethod
    def setUpTestData(cls):
        UserModel = get_user_model()
        cls.user = UserModel.objects.create_user(
            email='test@example.com', password='test')

    def test_tag_editor_cell_lines(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:tag_editor',
                                       args=['cell_lines']))
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_tag_editor_drugs(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:tag_editor',
                                       args=['drugs']))
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_create_cell_line_tag(self):
        self.client.force_login(self.user)

        cl = CellLine.objects.create(name='test_cell_line')

        resp = self.client.post(reverse('thunorweb:ajax_assign_tag'),
                                {'tagName': 'testTag',
                                 'tagType': 'cl',
                                 'entityId': [cl.id]})
        self.assertEquals(resp.status_code, HTTP_OK)

        self.assertTrue(CellLineTag.objects.filter(
            tag_name='testTag', cell_line=cl).exists())

    def test_create_drug_tag(self):
        self.client.force_login(self.user)

        dr = Drug.objects.create(name='test_drug')

        resp = self.client.post(reverse('thunorweb:ajax_assign_tag'),
                                {'tagName': 'testTag',
                                 'tagType': 'drug',
                                 'entityId': [dr.id]})
        self.assertEquals(resp.status_code, HTTP_OK)

        self.assertTrue(DrugTag.objects.filter(
            tag_name='testTag', drug=dr).exists())
