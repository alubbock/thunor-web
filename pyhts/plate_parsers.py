import re
from django.core.files.uploadedfile import UploadedFile
from datetime import timedelta, datetime
from .models import PlateFile, Plate, WellMeasurement
from django.db import IntegrityError, transaction
import xlrd
import magic
from functools import wraps


class PlateFileParseException(Exception):
    pass


def _read_plate_decorator(func):
    def _decorator(self, *args, **kwargs):
        if self._plate_data is None:
            self._read_plate_data()

        try:
            with transaction.atomic():
                return func(self, *args, **kwargs)
        except IntegrityError:
            raise PlateFileParseException('A file with the same plate and '
                                          'timepoints has been uploaded '
                                          'to this dataset before')

    return wraps(func)(_decorator)


class PlateFileParser(object):
    _RE_TIME_HOURS = r'(?P<time_hours>[0-9]+)[-_\s]*(h\W|hr|hour)'
    _RE_PLATE_TIME_HOURS = r'(?P<plate_id>.+)-' + _RE_TIME_HOURS
    regexes = {'time_hours': re.compile(_RE_TIME_HOURS, re.IGNORECASE),
               'plate_id_time_hours': re.compile(_RE_PLATE_TIME_HOURS,
                                                 re.IGNORECASE)}

    supported_mimetypes = {'application/vnd.openxmlformats-officedocument'
                           '.spreadsheetml.sheet': 'excel',
                           'text/plain': 'text'
                           }

    def __init__(self, plate_file, dataset=None):
        if not isinstance(plate_file, UploadedFile):
            raise PlateFileParseException('Cannot (yet) parse object of type: '
                                          '{}'.format(type(plate_file)))

        self.plate_file = plate_file
        self.dataset = dataset
        self._db_platefile = None
        self._plate_data = None

    def _create_db_platefile(self):
        self._db_platefile = PlateFile(file=self.plate_file)
        self._db_platefile.save()

    def _read_plate_data(self):
        # TODO: Ensure file isn't too big, check filetype etc.
        self.plate_file.open()
        self._plate_data = self.plate_file.read()

    @staticmethod
    def _str_universal_newlines(a_string):
        return a_string.replace('\r\n', '\n').replace('\r', '\n')

    @property
    def file_name(self):
        return self.plate_file.name

    @classmethod
    def extract_timepoint(cls, string):
        """
        Tries to extract a numeric time point from a string
        """
        tp = cls.regexes['time_hours'].search(string)
        return timedelta(hours=int(tp.group('time_hours'))) if tp else None


    @classmethod
    def extract_plate_and_timepoint(cls, string):
        """
        Tries to extract a plate name and time point from a string
        """
        tp = cls.regexes['plate_id_time_hours'].match(string)
        return {'plate': tp.group('plate_id'),
                'timepoint': timedelta(hours=int(tp.group('time_hours')))} if tp \
            else None

    @_read_plate_decorator
    def parse_platefile_synergy_neo(self):
        """
        Extracts data from a platefile

        Data includes number of plates, assay types, plate names, number of well
        rows and cols.
        """
        pd = self._plate_data
        try:
            pd = self._str_universal_newlines(pd.decode('utf-8'))
        except UnicodeDecodeError:
            raise PlateFileParseException('Error opening file with UTF-8 '
                                          'encoding (does file contain '
                                          'invalid characters?)')

        plates = pd.split('Field Group\n\nBarcode:')

        if len(plates) == 1:
            raise PlateFileParseException('File does not appear to be in '
                                          'Synergy Neo format')

        self._create_db_platefile()

        wells = []

        for p in plates:
            if len(p.strip()) == 0:
                continue
            barcode_and_rest = p.split('\n', 1)
            barcode = barcode_and_rest[0].strip()

            plate_and_timepoint = self.extract_plate_and_timepoint(barcode)

            if plate_and_timepoint is None:
                raise PlateFileParseException('Unable to parse timepoint for '
                                              'barcode {} or from plate file '
                                              'name'.format(barcode))

            plate_name = plate_and_timepoint['plate']
            plate_timepoint = plate_and_timepoint['timepoint']

            # Each plate can have multiple assays
            assays = re.split('\n\s*\n', barcode_and_rest[1])

            well_cols = 0
            well_rows = 0

            plate = None

            for a in assays:
                a_strp = a.strip()
                if len(a_strp) == 0:
                    continue

                well_lines = a.split('\n')
                assay_name = well_lines[0].strip()
                # TODO: Throw an error if well rows and cols not same for all
                # assays
                well_cols = len(well_lines[1].split())
                # Minus 2: One for assay name, one for column headers
                well_rows = len(well_lines) - 2

                if plate is None:
                    plate, _ = Plate.objects.update_or_create(
                        dataset=self.dataset,
                        name=plate_name,
                        defaults={'plate_file': self._db_platefile,
                                  'width': well_cols,
                                  'height': well_rows})

                # Read the actual well values
                well_id = 0
                for row in range(2, len(well_lines)):
                    for val in well_lines[row].split('\t')[1:-1]:
                        wells.append(WellMeasurement(plate=plate,
                                                     well=well_id,
                                                     timepoint=plate_timepoint,
                                                     assay=assay_name,
                                                     value=float(val)
                                                     ))
                        well_id += 1

            if not wells:
                raise PlateFileParseException('File contains no readable '
                                              'plates')

            if len(wells) % (well_cols * well_rows) != 0:
                raise PlateFileParseException('Extracted an unexpected number '
                                              'of wells from plate (plate: %s,'
                                              ' wells: %d)'.format(plate_name,
                                                                   len(wells)))

        WellMeasurement.objects.bulk_create(wells)

    @_read_plate_decorator
    def parse_platefile_imagexpress(self):
        wb = xlrd.open_workbook(file_contents=self._plate_data)
        if wb.nsheets != 1:
            raise PlateFileParseException('Excel workbooks with more than one '
                                          'worksheet are not currently '
                                          'supported')
        ws = wb.sheet_by_index(0)

        self._create_db_platefile()

        file_timepoint = self.extract_timepoint(self.file_name)

        if file_timepoint is None:
            raise PlateFileParseException('Unable to parse time point from '
                                          'file name')

        assay_name = None
        plate_name = None
        well_cols = ws.ncols - 1
        wells = []
        scanning_wells = False
        plate = None
        well_id = 0

        for row in range(ws.nrows):
            cell0_val = ws.cell(row, 0).value
            if cell0_val == 'Barcode':
                scanning_wells = False
                well_id = 0
                col = 2
                assay_name = None
                while (assay_name is None or assay_name == '') and \
                                col < (ws.ncols - 1):
                    assay_name = str(ws.cell(row, col).value)
                    col += 1
                if assay_name is None or assay_name == '':
                    raise PlateFileParseException('No assay name detected')
                continue

            if cell0_val == 'Plate ID':
                plate_name = ws.cell(row, 1).value
                continue

            if cell0_val == '' and ws.cell(row, 1).value == 1:
                scanning_wells = True
                scan_row = row + 1
                while scan_row < (ws.nrows - 1) and ws.cell(scan_row,
                                                            0) != 'Barcode':
                    scan_row += 1
                well_rows = scan_row - row
                if plate is None:
                    plate, _ = Plate.objects.update_or_create(
                        dataset=self.dataset,
                        name=plate_name,
                        defaults={'plate_file': self._db_platefile,
                                  'width': well_cols,
                                  'height': well_rows})
                continue

            if scanning_wells:
                for col in range(1, ws.ncols):
                    wells.append(WellMeasurement(plate=plate,
                                                 well=well_id,
                                                 timepoint=file_timepoint,
                                                 assay=assay_name,
                                                 value=ws.cell(row, col).value
                                                 ))
                    well_id += 1

        if not wells:
            raise PlateFileParseException('File contains no readable '
                                          'plates')

        WellMeasurement.objects.bulk_create(wells)

    def parse_platefile(self):
        """
        Attempt to auto-detect platefile format and parse
        """
        if not self._plate_data:
            self._read_plate_data()

        mimetype = magic.from_buffer(self._plate_data, mime=True)
        file_type = self.supported_mimetypes.get(mimetype, None)

        if not file_type:
            raise PlateFileParseException('File type not supported: {}'.
                                          format(mimetype))

        if file_type == 'excel':
            self.parse_platefile_imagexpress()
        elif file_type == 'text':
            self.parse_platefile_synergy_neo()
        else:
            raise NotImplementedError()
