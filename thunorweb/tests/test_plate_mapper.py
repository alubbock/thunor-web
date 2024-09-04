from django.test import TestCase
from thunorweb.models import HTSDataset, CellLine, Drug
from django.contrib.auth import get_user_model
from django.urls import reverse
import json


HTTP_OK = 200


class TestPlateMapper(TestCase):
    fixtures = ['testing-hts007-hcc1143.json']

    @classmethod
    def setUpTestData(cls):
        UserModel = get_user_model()
        cls.user = UserModel.objects.get(
            email='test@example.com')

        cls.d = HTSDataset.objects.get(owner=cls.user, name='test')

    def test_load_save_plate(self):
        plate_id = self.d.plate_set.first().id
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:ajax_load_plate',
                                       args=[plate_id]))
        self.assertEqual(resp.status_code, HTTP_OK)

        content = json.loads(resp.content)

        plate_data = {
            'plateId': content['plateMap']['plateId'],
            'wells': content['plateMap']['wells']
        }

        resp = self.client.post(
            reverse('thunorweb:ajax_save_plate'),
            json.dumps(plate_data),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, HTTP_OK)

    def test_create_cell_line(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('thunorweb:ajax_create_cellline'),
                                {'name': 'test_cell_line'})
        self.assertEqual(resp.status_code, HTTP_OK)

        self.assertTrue(CellLine.objects.filter(
            name='test_cell_line').exists())

    def test_create_drug(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('thunorweb:ajax_create_drug'),
                                {'name': 'test_drug'})
        self.assertEqual(resp.status_code, HTTP_OK)

        self.assertTrue(Drug.objects.filter(name='test_drug').exists())

    def test_plate_mapper(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:plate_mapper_dataset',
                                       args=[self.d.id]))
        self.assertEqual(resp.status_code, HTTP_OK)

    def test_plate_mapper_no_dataset(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:plate_mapper'))
        self.assertEqual(resp.status_code, HTTP_OK)

        resp = self.client.get(reverse('thunorweb:plate_mapper', args=[384]))
        self.assertEqual(resp.status_code, HTTP_OK)
