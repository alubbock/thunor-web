from django.test import TestCase
from thunorweb.models import CellLine, Drug, CellLineTag, DrugTag
from django.contrib.auth import get_user_model
from django.urls import reverse
import json
import io


HTTP_OK = 200

CSV = """tag_name,tag_category,cell_line
tag1,tagcat,1321N1
tag1,tagcat,2004
"""


class TestTags(TestCase):
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

    def test_cell_line_tag_crud(self):
        self.client.force_login(self.user)

        cl = CellLine.objects.create(name='test_cell_line')

        # Create
        resp = self.client.post(reverse('thunorweb:ajax_create_tag'),
                                {'tagName': 'testTag',
                                 'tagCategory': '',
                                 'tagType': 'cl'})
        self.assertEquals(resp.status_code, HTTP_OK)
        resp_json = json.loads(resp.content)
        tag_id = resp_json['tagId']

        self.assertTrue(CellLineTag.objects.filter(id=tag_id).exists())

        # Assign
        resp = self.client.post(reverse('thunorweb:ajax_assign_tag'),
                                {'tagId': tag_id,
                                 'tagType': 'cl',
                                 'entityId': [cl.id]})
        self.assertEquals(resp.status_code, HTTP_OK)
        self.assertEquals(
            list(CellLineTag.objects.get(id=tag_id).cell_lines.all()),
            [cl]
        )

        # Rename
        resp = self.client.post(reverse('thunorweb:ajax_rename_tag'),
                                {'tagId': tag_id,
                                 'tagType': 'cl',
                                 'tagCategory': '',
                                 'tagName': 'testTagNew'})
        self.assertEquals(resp.status_code, HTTP_OK)
        self.assertTrue(CellLineTag.objects.filter(
            tag_name='testTagNew', tag_category='', id=tag_id).exists())

        # Delete
        resp = self.client.post(reverse('thunorweb:ajax_delete_tag'),
                                {'tagId': tag_id,
                                 'tagType': 'cl'})
        self.assertEquals(resp.status_code, HTTP_OK)
        self.assertFalse(CellLineTag.objects.filter(id=tag_id).exists())

    def test_drug_tag_crud(self):
        self.client.force_login(self.user)

        dr = Drug.objects.create(name='test_drug')

        # Create
        resp = self.client.post(reverse('thunorweb:ajax_create_tag'),
                                {'tagName': 'testTag',
                                 'tagCategory': '',
                                 'tagType': 'drug'})
        self.assertEquals(resp.status_code, HTTP_OK)
        resp_json = json.loads(resp.content)
        tag_id = resp_json['tagId']

        self.assertTrue(DrugTag.objects.filter(id=tag_id).exists())

        # Assign
        resp = self.client.post(reverse('thunorweb:ajax_assign_tag'),
                                {'tagId': tag_id,
                                 'tagType': 'drug',
                                 'entityId': [dr.id]})
        self.assertEquals(resp.status_code, HTTP_OK)
        self.assertEquals(
            list(DrugTag.objects.get(id=tag_id).drugs.all()),
            [dr]
        )

        # Rename
        resp = self.client.post(reverse('thunorweb:ajax_rename_tag'),
                                {'tagId': tag_id,
                                 'tagType': 'drug',
                                 'tagCategory': '',
                                 'tagName': 'testTagNew'})
        self.assertEquals(resp.status_code, HTTP_OK)
        self.assertTrue(DrugTag.objects.filter(
            tag_name='testTagNew', tag_category='', id=tag_id).exists())

        # Delete
        resp = self.client.post(reverse('thunorweb:ajax_delete_tag'),
                                {'tagId': tag_id,
                                 'tagType': 'drug'})
        self.assertEquals(resp.status_code, HTTP_OK)
        self.assertFalse(DrugTag.objects.filter(id=tag_id).exists())

    def test_upload_cell_line_tags(self):
        CellLine.objects.create(name='1321N1')
        CellLine.objects.create(name='2004')

        csv_bytes = io.BytesIO(CSV.encode())
        csv_bytes.name = 'test.csv'
        self.client.force_login(self.user)
        response = self.client.post(reverse('thunorweb:ajax_upload_tagfile',
                                            args=['cell_lines']),
                                    {'tagfiles[]': csv_bytes})
        self.assertEquals(response.status_code, HTTP_OK)
        self.assertEquals(CellLineTag.objects.filter(
            tag_category='tagcat').count(), 1)

    def test_upload_drug_tags(self):
        Drug.objects.create(name='1321N1')
        Drug.objects.create(name='2004')

        csv_bytes = io.BytesIO(CSV.replace('cell_line','drug').encode())
        csv_bytes.name = 'test.csv'
        self.client.force_login(self.user)
        response = self.client.post(reverse('thunorweb:ajax_upload_tagfile',
                                            args=['drugs']),
                                    {'tagfiles[]': csv_bytes})
        self.assertEquals(response.status_code, HTTP_OK)
        self.assertEquals(DrugTag.objects.filter(
            tag_category='tagcat').count(), 1)
