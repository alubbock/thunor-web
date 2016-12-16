import re
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone
from datetime import timedelta, datetime
from .models import PlateFile, Plate, Well, WellMeasurement, CellLine, Drug,\
    WellDrug, PlateMap
from django.db import IntegrityError, transaction
import xlrd
import magic
from functools import wraps
import collections
import pandas
import io
import numpy as np
import math

class PlateFileParseException(Exception):
    pass


class PlateFileUnknownFormat(PlateFileParseException):
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
            self._get_well_sets_db([p.id for p in
                                    self._plate_objects.values()])

    def _get_well_sets_db(self, plate_ids):
        """ Reads Well primary keys into a local variable cache """
        for w in Well.objects.filter(
                plate_id__in=plate_ids).order_by(
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
    def parse_platefile_vanderbilt_hts(self):
        """
        Extracts data from a platefile in Vanderbilt HTS format

        This format includes annotations (cell lines, drugs, doses)

        Notes
        -----

        Limitations: assumes 384 well plate
        """
        self.file_format = 'Vanderbilt HTS Core'

        # Create plates (assume 384 well)
        # TODO: Check actual plate size
        pm = PlateMap(width=24, height=16)

        try:
            pd = pandas.read_csv(io.BytesIO(self._plate_data),
                                 encoding='utf8',
                                 dtype={
                                     'file_name': str,
                                     'well': str,
                                     'channel': str,
                                     'expt_class': str,
                                     'expt.date': str,
                                     'plate_name': str,
                                     'plate_id': str,
                                     'plate.name': str,
                                     'uid': str,
                                     'drug1': str,
                                     'drug1.conc': np.float64,
                                     'drug1.units': str,
                                     'cell.count': np.int64,
                                     'cell.line': str,
                                     'image.time': str
                                 },
                                 converters={
                                     'time': lambda t: timedelta(
                                         hours=float(t)),
                                     'well': lambda w: pm.well_name_to_id(w,
                                                           raise_error=False)
                                 },
                                 index_col=['plate_name', 'well']
                                 )
        except Exception as e:
            raise PlateFileParseException(e)

        # Sanity checks
        if 'drug2' in pd.columns.values:
            raise PlateFileParseException('{} format files with more than '
                                          'one drug are not yet '
                                          'supported'.format(self.file_format))

        drug_units = pd['drug1.units'].unique()
        for du in drug_units:
            if not isinstance(du, str) and math.isnan(du):
                continue

            if du != 'M':
                raise PlateFileParseException(
                    'Only supported drug concentration unit is M (not {})'.
                        format(du))

        # OK, we'll assume all is good and start hitting the DB
        self._create_db_platefile()

        # Get/create cell lines
        cell_lines = {}
        for cl in pd['cell.line'].unique():
            if not isinstance(cl, str):
                continue
            cl_obj, _ = CellLine.objects.get_or_create(name=cl)
            cell_lines[cl] = cl_obj.pk

        # Get/create drugs
        drugs = {}
        for dr in pd['drug1'].unique():
            if not isinstance(dr, str):
                continue
            dr_obj, _ = Drug.objects.get_or_create(name=dr)
            drugs[dr] = dr_obj.pk

        # Get/create plates
        plate_names = pd.index.get_level_values('plate_name').unique()
        plates_to_create = {}
        for pl_name in plate_names:
            if not isinstance(pl_name, str):
                continue

            if pl_name not in self._plate_objects.keys():
                plates_to_create[pl_name] = Plate(
                    dataset=self.dataset,
                    name=pl_name,
                    last_annotated=timezone.now(),
                    width=pm.width,
                    height=pm.height
                )

        # If any plates are not in the DB, now's the time...
        if plates_to_create:
            Plate.objects.bulk_create(plates_to_create.values())

            # Depending on DB backend, we may need to refetch to get the PKs
            # (Thankfully not PostgreSQL)
            if plates_to_create[list(plates_to_create)[0]].pk is None:
                for p in Plate.objects.filter(dataset_id=self.dataset.id):
                    self._plate_objects[p.name] = p
            else:
                # Otherwise, just add the plates into the local cache
                self._plate_objects.update(plates_to_create)

            # Create the well set objects
            well_sets_to_create = {}
            for pl_name in plate_names:
                if not isinstance(pl_name, str):
                    continue

                plate = self._plate_objects[pl_name]
                wells = self._well_sets.get(plate.id, None)

                if not wells:
                    pl_data = pd.loc[pl_name]
                    cell_lines_this_plate = {well: set(dat['cell.line']) for
                                             well, dat in
                                             pl_data.groupby(level='well')}

                    # Check for more than one cell line defined in same well
                    dup_wells = [well for well, cl in
                                 cell_lines_this_plate.items() if len(cl) > 1]
                    if any(dup_wells):
                        raise PlateFileParseException(
                            'Plate {} has more than one cell line defined for '
                            'well(s): {}'.format(pl_name, ",".join([
                                pm.well_id_to_name(d) for d in dup_wells])))

                    # Checks complete, create the wells
                    well_sets_to_create[plate.id] = []
                    for w in range(pm.num_wells):
                        cl_id = cell_lines_this_plate.get(w, None)
                        if cl_id is not None:
                            cl_id = cell_lines[list(cl_id)[0]]
                        well_sets_to_create[plate.id].append(
                            Well(plate_id=plate.id,
                                 well_num=w,
                                 cell_line_id=cl_id
                                 )
                        )

            # Run the DB query to create the well sets
            # Use a generator to avoid creating an intermediate list
            def well_generator():
                for plate_wells in well_sets_to_create.values():
                    for well in plate_wells:
                        yield well

            Well.objects.bulk_create(well_generator())

            # Again, on non-PostgreSQL datasets, we'll need to fetch the PKs
            if well_sets_to_create and \
                    well_sets_to_create[list(well_sets_to_create)[0]][0].pk\
                            is None:
                self._get_well_sets_db(well_sets_to_create.keys())
            else:
                for plate_id, well_objs in well_sets_to_create.items():
                    self._well_sets[plate_id] = [w.pk for w in well_objs]

        # Add WellDrugs and WellMeasurements
        well_drugs_to_create = []
        well_measurements_to_create = []
        for pl_name in plate_names:
            if not isinstance(pl_name, str):
                continue

            plate = self._plate_objects[pl_name]
            well_set = self._well_sets[plate.id]
            for well, dat in pd.loc[pl_name].groupby(level='well'):
                well_id = well_set[well]
                drug_name = dat['drug1'].unique()
                if len(drug_name) > 1:
                    raise PlateFileParseException(
                        'Plate {}, well {} has more than one drug defined in '
                        'drug1 column'.format(pl_name, pm.well_id_to_name(
                            well))
                    )
                drug_name = drug_name[0]
                drug_conc = dat['drug1.conc'].unique()
                if len(drug_conc) > 1:
                    raise PlateFileParseException(
                        'Plate {}, well {} has more than one drug '
                        'concentration defined in drug1.conc column'.format(
                            pl_name, pm.well_id_to_name(well))
                    )
                drug_conc = drug_conc[0]
                well_drugs_to_create.append(
                    WellDrug(
                        well_id=well_id,
                        drug_id=drugs[drug_name],
                        order=0,
                        dose=drug_conc
                    )
                )
                for _, measurement in dat.iterrows():
                    well_measurements_to_create.append(
                        WellMeasurement(
                            well_id=well_id,
                            assay='Cell count',
                            timepoint=measurement['time'],
                            value=measurement['cell.count']
                        )
                    )

        # Fire off the bulk DB queries... and we're done
        WellDrug.objects.bulk_create(well_drugs_to_create)
        WellMeasurement.objects.bulk_create(well_measurements_to_create)

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
            raise PlateFileUnknownFormat('Error opening file with UTF-8 '
                                         'encoding (does file contain '
                                         'non-standard characters?)')

        plates = pd.split('Field Group\n\nBarcode:')

        if len(plates) == 1:
            plates = pd.split('Barcode\n\nBarcode:')
            if len(plates) == 1:
                raise PlateFileUnknownFormat('File does not appear to be in '
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
            try:
                self.parse_platefile_synergy_neo()
            except PlateFileUnknownFormat:
                pass

            self.parse_platefile_vanderbilt_hts()
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
