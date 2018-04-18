from django.test import TestCase, Client
import pkg_resources
from thunorweb.models import HTSDataset, CellLine, CellLineTag, Drug, DrugTag
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
        cls.other_user = UserModel.objects.create_user(
            email='test2@example.com', password='test')
        filename = pkg_resources.resource_filename(
            'thunor', 'testdata/hts007.h5')
        c = Client()
        c.force_login(cls.user)

        resp = c.post(reverse('thunorweb:ajax_create_dataset'),
                      {'name': 'test'})
        resp_json = json.loads(resp.content)
        dataset_id = resp_json['id']
        cls.d = HTSDataset.objects.get(pk=dataset_id)

        with open(filename, 'rb') as src:
            response = c.post(reverse('thunorweb:ajax_upload_platefiles'),
                                  {'file_field[]': src, 'dataset_id':
                                      cls.d.id})

        assert response.status_code == HTTP_OK

        # Create some cell line and drug tags
        entities_per_tag = 3
        num_tags = 3
        cell_lines = CellLine.objects.all()
        cltags = []
        for tag_num in range(num_tags):
            for cell_line_idx in range(tag_num * entities_per_tag,
                                       tag_num * (entities_per_tag + 1)):
                cltags.append(CellLineTag(
                    tag_name='tag{}'.format(tag_num),
                    cell_line=cell_lines[cell_line_idx],
                    owner=cls.user
                ))
        CellLineTag.objects.bulk_create(cltags)

        drugs = Drug.objects.all()
        drtags = []
        for tag_num in range(num_tags):
            for drug_idx in range(tag_num * entities_per_tag,
                                  tag_num * (entities_per_tag + 1)):
                drtags.append(DrugTag(
                    tag_name='tag{}'.format(tag_num),
                    drug=drugs[drug_idx],
                    owner=cls.user
                ))
        DrugTag.objects.bulk_create(drtags)

        # Get the dataset groupings
        response = c.get(reverse('thunorweb:ajax_dataset_groupings',
                                 args=[cls.d.id]))
        assert response.status_code == HTTP_OK
        cls.groupings = json.loads(response.content)

    def test_plots_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('thunorweb:plots'),
                               {'dataset': self.d.id})
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_time_course(self):
        self.client.force_login(self.user)
        url = reverse('thunorweb:ajax_plot', args=['json'])
        resp = self.client.get(
            url,
            {'plotType': 'tc',
             'datasetId': self.d.id,
             'c': self.groupings['cellLines'][0]['id'],
             'd': self.groupings['drugs'][0]['id'],
             'assay': self.groupings['dipAssay'],
             'overlayDipFit': 'true',
             'logTransform': 'log2'
             }
        )
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_single_drc_dip(self):
        self.client.force_login(self.user)
        url = reverse('thunorweb:ajax_plot', args=['json'])
        resp = self.client.get(
            url,
            {'plotType': 'drc',
             'datasetId': self.d.id,
             'c': self.groupings['cellLines'][0]['id'],
             'd': self.groupings['drugs'][0]['id'],
             'assay': self.groupings['dipAssay'],
             'drMetric': 'dip'
             }
        )
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_single_drc_viability(self):
        self.client.force_login(self.user)
        url = reverse('thunorweb:ajax_plot', args=['json'])
        resp = self.client.get(
            url,
            {'plotType': 'drc',
             'datasetId': self.d.id,
             'c': self.groupings['cellLines'][0]['id'],
             'd': self.groupings['drugs'][0]['id'],
             'assay': self.groupings['dipAssay'],
             'drMetric': 'viability'
             }
        )
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_ic50_bar_plot_all_cell_lines(self):
        self.client.force_login(self.user)
        url = reverse('thunorweb:ajax_plot', args=['json'])
        argdict = {
            'plotType': 'drpar',
            'datasetId': self.d.id,
            'c': [c['id'] for c in self.groupings['cellLines']],
            'd': self.groupings['drugs'][0]['id'],
            'drMetric': 'dip',
            'drPar': 'ic50'
        }
        resp = self.client.get(
            url,
            argdict
        )
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_ic50_ec50_scatter_plot_all_cell_lines(self):
        self.client.force_login(self.user)
        url = reverse('thunorweb:ajax_plot', args=['json'])
        argdict = {
            'plotType': 'drpar',
            'datasetId': self.d.id,
            'c': [c['id'] for c in self.groupings['cellLines']],
            'd': self.groupings['drugs'][0]['id'],
            'drMetric': 'dip',
            'drPar': 'ic50',
            'drParTwo': 'ec50',
            'drParOrder': 'emax_obs'
        }
        resp = self.client.get(
            url,
            argdict
        )
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_ic50_ec50_box_plot_tags(self):
        self.client.force_login(self.user)
        url = reverse('thunorweb:ajax_plot', args=['json'])
        argdict = {
            'plotType': 'drpar',
            'datasetId': self.d.id,
            'cellLineTags': [c['id'] for c in self.groupings['cellLineTags']],
            'drugTags': [d['id'] for d in self.groupings['drugTags']],
            'drMetric': 'dip',
            'drPar': 'ic50',
            'drParOrder': 'emax_obs'
        }
        resp = self.client.get(
            url,
            argdict
        )
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_qc_dip_boxplot(self):
        self.client.force_login(self.user)
        url = reverse('thunorweb:ajax_plot', args=['json'])
        resp = self.client.get(
            url,
            {'plotType': 'qc',
             'qcView': 'ctrldipbox',
             'datasetId': self.d.id
             }
        )
        self.assertEquals(resp.status_code, HTTP_OK)

    def test_qc_dip_plate_map(self):
        self.client.force_login(self.user)
        url = reverse('thunorweb:ajax_plot', args=['json'])
        resp = self.client.get(
            url,
            {'plotType': 'qc',
             'qcView': 'dipplatemap',
             'datasetId': self.d.id,
             'plateId': self.d.plate_set.first().id
             }
        )
        self.assertEquals(resp.status_code, HTTP_OK)
