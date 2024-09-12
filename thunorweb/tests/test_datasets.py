from django.urls import reverse
from django.test import Client, TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from thunorweb.models import HTSDataset
import json
from thunorweb.tests import get_thunor_test_file

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNAUTHORIZED = 401
HTTP_REDIRECT = 302


class TestDatasetViews(TestCase):
    @classmethod
    def setUpTestData(cls):
        UserModel = get_user_model()
        cls.user = UserModel.objects.create_user(
            email='test@example.com', password='test')
        cls.other_user = UserModel.objects.create_user(
            email='test2@example.com', password='test')
        c = Client()
        c.force_login(cls.user)

        resp = c.post(reverse('thunorweb:ajax_create_dataset'),
                      {'name': 'test'})
        resp_json = json.loads(resp.content)
        dataset_id = resp_json['id']
        cls.d = HTSDataset.objects.get(pk=dataset_id)

        with open(get_thunor_test_file('testdata/hts007.h5'), 'rb') as hts007:
            response = c.post(reverse('thunorweb:ajax_upload_platefiles'),
                              {'file_field[]': hts007,
                               'dataset_id': cls.d.id})

        assert response.status_code == HTTP_OK
        assert cls.d.plate_set.count() == 16

    def test_rename_dataset(self):
        self.client.force_login(self.user)
        d = HTSDataset.objects.create(owner=self.user, name='test123')

        resp = self.client.post(reverse('thunorweb:ajax_rename_dataset'),
                                {'datasetId': d.id, 'datasetName': 'test456'})
        self.assertEqual(resp.status_code, HTTP_OK)

        d.refresh_from_db()
        self.assertEqual(d.name, 'test456')

    def test_delete_dataset(self):
        self.client.force_login(self.user)
        d = HTSDataset.objects.create(owner=self.user, name='test2')

        resp = self.client.post(reverse('thunorweb:ajax_delete_dataset'),
                                {'dataset_id': d.id})
        self.assertEqual(resp.status_code, HTTP_OK)

        self.assertIsNotNone(HTSDataset.objects.get(pk=d.id).deleted_date)

    def test_delete_platefile(self):
        platefile_id = self.d.platefile_set.first().id
        self.client.force_login(self.user)
        resp = self.client.post(reverse('thunorweb:ajax_delete_platefile'),
                                {'key': platefile_id})
        self.assertEqual(resp.status_code, HTTP_OK)

    def test_dataset_upload_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:plate_upload',
                                       args=[self.d.id]))
        self.assertEqual(resp.status_code, HTTP_OK)

    def test_download_hdf(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:download_dataset_hdf5',
                                  args=[self.d.id]))

        self.assertEqual(resp.status_code, HTTP_OK)
        self.assertEqual(resp['Content-Type'], 'application/x-hdf5')

    def test_download_hdf_access(self):
        self.check_view_access_status(
               reverse('thunorweb:download_dataset_hdf5', args=[self.d.id]))

    def test_download_dip_rates(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:download_dip_rates',
                                       args=[self.d.id]))

        self.assertEqual(resp.status_code, HTTP_OK)
        self.assertEqual(resp['Content-Type'], 'text/tab-separated-values')

    def test_download_dip_params_tsv(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:download_fit_params',
                                       args=[self.d.id, 'dip']))

        self.assertEqual(resp.status_code, HTTP_OK)
        self.assertEqual(resp['Content-Type'], 'text/tab-separated-values')

    def test_download_viability_params_tsv(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:download_fit_params',
                                       args=[self.d.id, 'viability']))

        self.assertEqual(resp.status_code, HTTP_OK)
        self.assertEqual(resp['Content-Type'], 'text/tab-separated-values')

    def test_download_params_tsv_access(self):
        for stat_type in ('dip', 'viability'):
            self.check_view_access_status(
                   reverse('thunorweb:download_fit_params',
                           args=[self.d.id, stat_type]))

    def test_view_dataset(self):
        self.check_view_access_status(
               reverse('thunorweb:view_dataset', args=[self.d.id]))

    def test_view_dataset_permissions(self):
        self.check_view_access_status(
               reverse('thunorweb:view_dataset_permissions', args=[self.d.id]))

    def test_ajax_get_dataset_groupings(self):
        self.check_view_access_status(
            reverse('thunorweb:ajax_dataset_groupings', args=[self.d.id])
        )

    def test_get_datasets_ajax(self):
        url = reverse('thunorweb:ajax_get_datasets')
        self.assertEqual(self.client.get(url).status_code, HTTP_UNAUTHORIZED)

        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, HTTP_OK)

    def test_assign_group(self):
        """ Make dataset public and check access"""
        self.client.force_login(self.user)
        public_grp = Group.objects.get(name='Public')
        resp = self.client.post(
            reverse('thunorweb:ajax_set_dataset_group_permission'),
            {'dataset_id': self.d.id,
             'group_id': public_grp.id,
             'perm_id': 'view_plots',
             'state': 'true'
             }
        )
        self.assertEqual(resp.status_code, HTTP_OK)

        # Log in as other user and check dataset access
        self.client.force_login(self.other_user)
        resp = self.client.get(reverse('thunorweb:view_dataset',
                                       args=[self.d.id]))
        self.assertEqual(resp.status_code, HTTP_OK)

        # Dataset should be visible in the public datasets list
        resp = self.client.get(reverse(
            'thunorweb:ajax_get_datasets_by_group', args=['Public']))
        resp_content = json.loads(resp.content)
        self.assertEqual(len(resp_content['data']), 1)

        # Other user should not have permission to change permissions on
        # this dataset
        resp = self.client.post(
            reverse('thunorweb:ajax_set_dataset_group_permission'),
            {'dataset_id': self.d.id,
             'group_id': public_grp.id,
             'perm_id': 'view_plots',
             'state': 'false'
             }
        )
        self.assertEqual(resp.status_code, HTTP_NOT_FOUND)

        # Revoke permission
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse('thunorweb:ajax_set_dataset_group_permission'),
            {'dataset_id': self.d.id,
             'group_id': public_grp.id,
             'perm_id': 'view_plots',
             'state': 'false'
             }
        )
        self.assertEqual(resp.status_code, HTTP_OK)

        # Check permission revoked as other user
        self.client.force_login(self.other_user)
        resp = self.client.get(reverse('thunorweb:view_dataset',
                                       args=[self.d.id]))
        self.assertEqual(resp.status_code, HTTP_NOT_FOUND)

        resp = self.client.get(reverse(
            'thunorweb:ajax_get_datasets_by_group', args=['Public']))
        resp_content = json.loads(resp.content)
        self.assertEqual(len(resp_content['data']), 0)

    def check_view_access_status(self, url):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, HTTP_REDIRECT)

        self.client.force_login(self.user)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, HTTP_OK)

        self.client.force_login(self.other_user)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, HTTP_NOT_FOUND)
        self.client.logout()
