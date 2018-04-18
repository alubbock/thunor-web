from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files import File
import pkg_resources
import thunor.io
from thunorweb.models import HTSDataset
from thunorweb.plate_parsers import PlateFileParser
import io


class TestPlateParsers(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create(email='test@example.com')
        cls.d = HTSDataset.objects.create(name='test', owner=cls.user)

    # HDF parsing is tested elsewhere

    def test_parse_vanderbilt_csv(self):
        filename = pkg_resources.resource_filename(
            'thunor', 'testdata/hts007.h5')

        with io.StringIO() as csv_buffer:
            # convert HDF to CSV in memory
            thunor.io.write_vanderbilt_hts(
                df_data=thunor.io.read_hdf(filename),
                filename=csv_buffer,
                sep=','
            )

            csv_buffer.seek(0)

            pfp = PlateFileParser(File(csv_buffer, name='test.csv'),
                                  dataset=self.d)
            results = pfp.parse_all()

        assert len(results) == 1
        assert results[0]['success']
        assert results[0]['file_format'] == 'Vanderbilt HTS Core'
