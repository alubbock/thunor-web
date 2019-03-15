from django.test import TestCase
from django.core.files import File
from thunorweb.plate_parsers import PlateFileParser
from thunorweb.models import HTSDataset, CellLine, Drug
from thunorweb.tests import get_thunor_test_file
from django.contrib.auth import get_user_model
from django.urls import reverse
import json


HTTP_OK = 200


class TestPlateMapper(TestCase):
    @classmethod
    def setUpTestData(cls):
        UserModel = get_user_model()
        cls.user = UserModel.objects.create_user(
            email='test@example.com', password='test')

        cls.d = HTSDataset.objects.create(owner=cls.user, name='test')
        hts007 = get_thunor_test_file('testdata/hts007.h5')
        try:
            f = File(hts007, name='hts007.h5')
            pfp = PlateFileParser(f, dataset=cls.d)
            results = pfp.parse_all()
        finally:
            hts007.close()

        assert len(results) == 1
        assert results[0]['success']
        assert results[0]['file_format'] == 'HDF5'

    def test_load_save_plate(self):
        plate_id = self.d.plate_set.first().id
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:ajax_load_plate',
                                       args=[plate_id]))
        self.assertEquals(resp.status_code, HTTP_OK)

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
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_create_cell_line(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('thunorweb:ajax_create_cellline'),
                                {'name': 'test_cell_line'})
        self.assertEquals(resp.status_code, HTTP_OK)

        self.assertTrue(CellLine.objects.filter(
            name='test_cell_line').exists())

    def test_create_drug(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('thunorweb:ajax_create_drug'),
                                {'name': 'test_drug'})
        self.assertEquals(resp.status_code, HTTP_OK)

        self.assertTrue(Drug.objects.filter(name='test_drug').exists())

    def test_plate_mapper(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:plate_mapper_dataset',
                                       args=[self.d.id]))
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_plate_mapper_no_dataset(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:plate_mapper'))
        self.assertEquals(resp.status_code, HTTP_OK)

        resp = self.client.get(reverse('thunorweb:plate_mapper', args=[384]))
        self.assertEquals(resp.status_code, HTTP_OK)
