import re
from django.core.files.uploadedfile import UploadedFile
from datetime import timedelta, datetime
from .models import PlateFile, Plate, Well, WellMeasurement
from django.db import IntegrityError, transaction
import xlrd
import magic
from functools import wraps
import collections


class PlateFileParseException(Exception):
    pass


def _read_plate_decorator(func):
    def _decorator(self, *args, **kwargs):
        if self._plate_data is None:
            self._read_plate_data()

        with transaction.atomic():
            return func(self, *args, **kwargs)

    return wraps(func)(_decorator)


class PlateFileParser(object):
    _RE_TIME_HOURS = r'(?P<time_hours>[0-9]+)[-_\s]*(h\W|hr|hour)'
    _RE_PLATE_TIME_HOURS = r'(?P<plate_id>.+)-' + _RE_TIME_HOURS
    regexes = {'time_hours': re.compile(_RE_TIME_HOURS, re.IGNORECASE),
               'plate_id_time_hours': re.compile(_RE_PLATE_TIME_HOURS,
                                                 re.IGNORECASE)}

    supported_mimetypes = {'application/vnd.openxmlformats-officedocument'
                           '.spreadsheetml.sheet': 'excel',
                           'text/plain': 'text',
                           'text/x-fortran': 'text'
                           }

    def __init__(self, plate_files, dataset):
        if isinstance(plate_files, UploadedFile):
            self.all_plate_files = [plate_files, ]
        elif isinstance(plate_files, collections.Iterable):
            self.all_plate_files = plate_files
        else:
            raise PlateFileParseException('Cannot (yet) parse object of type: '
                                          '{}'.format(type(plate_files)))

        self._plate_file_position = -1
        self.plate_file = None
        self.dataset = dataset
        self.file_format = None
        self._db_platefile = None
        self._plate_data = None
        self._plate_objects = {}
        self._results = []
        self._well_sets = {}

        # Get existing plate objects
        for p in Plate.objects.filter(dataset_id=dataset.id):
            self._plate_objects[p.name] = p
        if self._plate_objects:
            for w in Well.objects.filter(
                    plate_id__in=[p.id for p in
                                  self._plate_objects.values()]).order_by(
                    'plate_id', 'well_num'):
                self._well_sets.setdefault(w.plate_id, []).append(w.pk)

    def _create_db_platefile(self):
        self._db_platefile = PlateFile.objects.create(
            dataset=self.dataset, file=self.plate_file,
            file_format=self.file_format)

    def _read_plate_data(self):
        # TODO: Ensure file isn't too big, check filetype etc.
        self.plate_file.open()
        self._plate_data = self.plate_file.read()

    def _has_more_platefiles(self):
        return self._plate_file_position < (len(self.all_plate_files) - 1)

    def _next_platefile(self):
        self._plate_file_position += 1
        self.plate_file = self.all_plate_files[self._plate_file_position]
        self._plate_data = None
        self._db_platefile = None

    @staticmethod
    def _str_universal_newlines(a_string):
        return a_string.replace('\r\n', '\n').replace('\r', '\n')

    @property
    def file_name(self):
        return self.plate_file.name

    @property
    def id(self):
        if self._db_platefile is None:
            return None
        return self._db_platefile.id

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
        self.file_format = 'Synergy Neo'
        pd = self._plate_data
        try:
            pd = self._str_universal_newlines(pd.decode('utf-8'))
        except UnicodeDecodeError:
            raise PlateFileParseException('Error opening file with UTF-8 '
                                          'encoding (does file contain '
                                          'non-standard characters?)')

        plates = pd.split('Field Group\n\nBarcode:')

        if len(plates) == 1:
            plates = pd.split('Barcode\n\nBarcode:')
            if len(plates) == 1:
                raise PlateFileParseException('File does not appear to be in '
                                              'Synergy Neo format')

        self._create_db_platefile()

        well_measurements = []

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

            plate = self._plate_objects.get(plate_name, None)

            # Each plate can have multiple assays
            assays = re.split('\n\s*\n', barcode_and_rest[1])

            for a in assays:
                a_strp = a.strip()
                if len(a_strp) == 0:
                    continue

                well_lines = a.split('\n')
                assay_name = well_lines[0].strip()
                well_cols = len(well_lines[1].split())
                # Minus 2: One for assay name, one for column headers
                well_rows = len(well_lines) - 2

                if plate is None:
                    plate = self._get_or_create_plate(plate_name,
                                                      well_cols, well_rows)

                # Check plate dimensions are as expected
                if well_cols != plate.width:
                    raise PlateFileParseException('Unexpected plate width on '
                                                  'plate with barcode {} '
                                                  '(expected: {}, got: {})'.
                                format(barcode, plate.width, well_cols))

                if well_rows != plate.height:
                    raise PlateFileParseException('Unexpected plate height on '
                                                  'plate with barcode {} '
                                                  '(expected: {}, got: {})'.
                                format(barcode, plate.height, well_rows))

                well_id = 0
                for row in range(2, len(well_lines)):
                    for val in well_lines[row].split('\t')[1:-1]:
                        well_measurements.append(WellMeasurement(
                            well_id=self._well_sets[plate.id][well_id],
                            timepoint=plate_timepoint,
                            assay=assay_name,
                            value=float(val)
                        ))
                        well_id += 1

        if not well_measurements:
            raise PlateFileParseException('File contains no readable '
                                          'plates')
        try:
            WellMeasurement.objects.bulk_create(well_measurements)
        except IntegrityError:
            raise PlateFileParseException('A file with the same plate, '
                                          'assay and time points has been '
                                          'uploaded to this dataset before')

    @_read_plate_decorator
    def parse_platefile_imagexpress(self):
        self.file_format = 'ImageXpress'
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
        scanning_wells = False
        plate = None
        well_id = 0
        well_measurements = []

        for row in range(ws.nrows):
            cell0_val = ws.cell(row, 0).value
            if cell0_val == 'Barcode':
                barcode = ws.cell(row, 1).value
                plate_name = None if barcode == 'N/A' else barcode.strip()
                scanning_wells = False
                well_id = 0
                col = 2
                assay_name = None
                while (assay_name is None or assay_name == '') and \
                                col < (ws.ncols - 1):
                    assay_name = ws.cell(row, col).value.strip()
                    col += 1
                if assay_name is None or assay_name == '':
                    raise PlateFileParseException('No assay name detected')
                continue

            if cell0_val == 'Plate Name':
                if plate_name is None:
                    plate_name = ws.cell(row, 1).value.split(' ', 1)[0]
                continue

            # if cell0_val == 'Plate ID':
            #     plate_name = str(ws.cell(row, 1).value)
            #     continue

            if cell0_val == '' and ws.cell(row, 1).value == 1:
                scanning_wells = True
                scan_row = row + 1
                while scan_row < ws.nrows and \
                                ws.cell(scan_row, 0).value != 'Barcode':
                    scan_row += 1
                well_rows = scan_row - row - 1

                plate = self._get_or_create_plate(plate_name,
                                                  well_cols, well_rows)
                continue

            if scanning_wells:
                for col in range(1, ws.ncols):
                    val = ws.cell(row, col).value
                    if val == '':
                        val = None
                    # print(self.dataset.id, self._db_platefile.id, plate.id,
                    #       well_id,
                    #       file_timepoint, assay_name)
                    well_measurements.append(WellMeasurement(
                        well_id=self._well_sets[plate.id][well_id],
                        timepoint=file_timepoint,
                        assay=assay_name,
                        value=val
                    ))
                    well_id += 1

        if not well_measurements:
            raise PlateFileParseException('File contains no readable '
                                          'plates')

        try:
            WellMeasurement.objects.bulk_create(well_measurements)
        except IntegrityError:
            raise PlateFileParseException('A file with the same plate, '
                                          'assay and time points has been '
                                          'uploaded to this dataset before')

    def _get_or_create_plate(self, plate_name, well_cols, well_rows):
        plate = self._plate_objects.get(plate_name, None)

        if plate is None:
            plate = Plate.objects.create(
                dataset=self.dataset,
                name=plate_name,
                width=well_cols,
                height=well_rows)
            self._plate_objects[plate.name] = plate

            wells = [Well(plate_id=plate.id, well_num=w) for w in
                     range(well_cols * well_rows)]
            Well.objects.bulk_create(wells)

            # Get the well IDs without an extra select, if the DB backend
            # supports this (just PostgreSQL as of Django 1.10)
            if wells[0].pk is not None:
                self._well_sets[plate.id] = [w.pk for w in wells]

        if plate.id not in self._well_sets:
            self._well_sets[plate.id] = list(
                plate.well_set.order_by('well_num').values_list(
                    'pk', flat=True))

        if len(self._well_sets[plate.id]) != well_cols * well_rows:
            raise PlateFileParseException(
                'Retrieved {} wells for plate {} (was expecting '
                '{})'.format(len(self._well_sets[plate.id]),
                             plate.id,
                             well_cols * well_rows
                             )
            )

        return plate

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

    def parse_all(self):
        self._results = []
        while self._has_more_platefiles():
            self._next_platefile()
            try:
                self.parse_platefile()
                self._results.append({'success': True,
                                      'file_format': self.file_format,
                                      'id': self.id,
                                      'file_name': self.file_name
                                      })
            except PlateFileParseException as e:
                self._results.append({'success': False, 'error': e})

        return self._results
