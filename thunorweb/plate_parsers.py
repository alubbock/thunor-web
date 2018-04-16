import re
from django.core.files import File
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from .models import PlateFile, Plate, Well, WellMeasurement, CellLine, Drug,\
    WellDrug
from django.db import IntegrityError, transaction
import xlrd
import magic
import collections
from thunor.io import _read_hdf_unstacked, \
    PlateMap, STANDARD_PLATE_SIZES, PlateFileParseException
import pandas as pd
import itertools


class PlateFileUnknownFormat(PlateFileParseException):
    pass


def _plate_size_selector(num_wells):
    for size in STANDARD_PLATE_SIZES:
        if num_wells < size:
            return size

    raise ValueError('Unsupported plate size: ' + num_wells)


class PlateFileParser(object):
    _ZERO_TIMEDELTA = timedelta(0)
    _RE_TIME_HOURS = r'(?P<time_hours>[0-9]+)[-_\s]*(h\W|hr|hour)'
    _RE_PLATE_TIME_HOURS = r'(?P<plate_id>.+)-' + _RE_TIME_HOURS
    regexes = {'time_hours': re.compile(_RE_TIME_HOURS, re.IGNORECASE),
               'plate_id_time_hours': re.compile(_RE_PLATE_TIME_HOURS,
                                                 re.IGNORECASE)}

    supported_extensions = {
        '.csv': 'text',
        '.tsv': 'text',
        '.txt': 'text',
        '.h5': 'hdf',
        '.hdf': 'hdf',
        '.hdf5': 'hdf',
        '.xlsx': 'excel'
    }

    supported_mimetypes = {'application/vnd.openxmlformats-officedocument'
                           '.spreadsheetml.sheet': 'excel',
                           'application/zip': 'excel',
                           'text/plain': 'text',
                           'text/x-fortran': 'text',
                           'application/x-hdf': 'hdf'
                           }

    def __init__(self, plate_files, dataset):
        if isinstance(plate_files, File):
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
        self._plate_objects = {}
        self._results = []
        self._well_sets = {}

        # Get existing well and plate objects
        for w in Well.objects.filter(
                plate__dataset_id=self.dataset.id).select_related('plate'):
            if w.plate.name not in self._plate_objects:
                self._plate_objects[w.plate.name] = w.plate
                self._well_sets[w.plate_id] = {}
            self._well_sets[w.plate_id][w.well_num] = w.pk

    def _get_well_sets_db(self, plate_ids):
        """ Reads Well primary keys into a local variable cache """
        for w in Well.objects.filter(
                plate_id__in=plate_ids):
            self._well_sets.setdefault(w.plate_id, {})[w.well_num] = w.pk

    def _create_db_platefile(self):
        self._db_platefile = PlateFile.objects.create(
            dataset=self.dataset, file=self.plate_file,
            file_format=self.file_format)

    def _has_more_platefiles(self):
        return self._plate_file_position < (len(self.all_plate_files) - 1)

    def _next_platefile(self):
        self._plate_file_position += 1
        self.plate_file = self.all_plate_files[self._plate_file_position]
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

    def _create_wells(self, df_data,
                      df_wells, cell_lines):
        well_sets_to_create = collections.defaultdict(list)

        # Expt wells
        for row in df_wells.itertuples():
            plate_id = self._plate_objects[row.plate].id
            if row.well_num not in self._well_sets.get(plate_id, {}):
                well_sets_to_create[plate_id].append(Well(
                    plate_id=plate_id,
                    well_num=row.well_num,
                    cell_line_id=cell_lines[row.cell_line]
                ))

        # Add any control wells
        if df_data.controls is not None:
            control_wells = df_data.controls['well_num'].reset_index([
                'cell_line', 'plate']).reset_index(drop=True).drop_duplicates()
            for w in control_wells.itertuples():
                pl_name = w.plate
                well_num = w.well_num
                plate_id = self._plate_objects[pl_name].id
                if well_num not in self._well_sets.get(plate_id, {}):
                    well_sets_to_create[plate_id].append(Well(
                        plate_id=plate_id,
                        well_num=well_num,
                        cell_line_id=cell_lines[w.cell_line]
                    ))

        # Flatten the well sets (n.b. bulk_create evaluates generators)
        try:
            first_well = next(iter(well_sets_to_create.values()))[0]
        except (KeyError, StopIteration):
            first_well = None
        Well.objects.bulk_create(itertools.chain.from_iterable(
            well_sets_to_create.values()),
            batch_size=settings.DB_MAX_BATCH_SIZE)

        # Again, on non-PostgreSQL datasets, we'll need to fetch the PKs
        if first_well and first_well.pk is None:
            self._get_well_sets_db(well_sets_to_create.keys())
        else:
            for plate_id, well_objs in well_sets_to_create.items():
                self._well_sets.setdefault(plate_id, {}).update({
                    w.well_num: w.pk for w in well_objs})

    def _create_welldrugs(self, df_wells, drug_nums, drugs):
        well_drugs_to_create = []
        for row in df_wells.itertuples():
            pl_name = row.plate
            plate = self._plate_objects[pl_name]
            well_num = row.well_num
            well_id = self._well_sets[plate.id][well_num]
            for order, d_num in enumerate(drug_nums):
                drug_name = getattr(row, 'drug%d' % d_num)

                if not pd.isnull(drug_name):
                    well_drugs_to_create.append(
                        WellDrug(
                            well_id=well_id,
                            drug_id=drugs[drug_name],
                            order=order,
                            dose=getattr(row, 'dose%d' % d_num)
                        )
                    )

        WellDrug.objects.bulk_create(well_drugs_to_create,
                                     batch_size=settings.DB_MAX_BATCH_SIZE)

    def _import_thunor(self, df_data):
        """ Import from a Thunor core dataset with unstacked doses """
        if settings.DATABASE_SETTING == 'postgres':
            # This is wrapped in an outer commit block, so we can gain a bit of
            # speed by not waiting for WAL in this inner transaction
            Well.objects.raw('SET LOCAL synchronous_commit TO OFF;')

        doses_unstacked = df_data.doses

        # Work out the max number of drugs in a combination
        drug_no = 1
        drug_nums = []
        while ('drug%d' % drug_no) in doses_unstacked.index.names:
            drug_nums.append(drug_no)
            drug_no += 1

        # Add drugs
        drugs = {}
        for drug_no in drug_nums:
            for dr in doses_unstacked.index.get_level_values(
                            'drug%d' % drug_no).unique():
                if not isinstance(dr, str):
                    continue
                dr_obj, _ = Drug.objects.get_or_create(
                    name__iexact=dr,
                    defaults={'name': dr}
                )
                drugs[dr] = dr_obj.pk

        # Add cell lines
        cell_lines = {}
        for cl in df_data.cell_lines:
            cl_obj, _ = CellLine.objects.get_or_create(
                name__iexact=cl,
                defaults={'name': cl}
            )
            cell_lines[cl] = cl_obj.pk

        # Create plates
        doses_unstacked.reset_index(inplace=True)
        df_wells = doses_unstacked
        df_wells.set_index('well_id', inplace=True)
        plates_to_create = {}

        # Get the plate sizes by the largest well number on each plate
        plate_sizes = df_wells.groupby('plate')['well_num'].max()
        if df_data.controls is not None:
            ctrl_plate_sizes = df_data.controls.groupby(
                'plate')['well_num'].max()
            plate_sizes = plate_sizes.to_frame().join(
                ctrl_plate_sizes, rsuffix='ctrl').max(axis=1)

        # Convert the plate sizes to one of (96, 384, 1536)
        plate_sizes = plate_sizes.apply(_plate_size_selector)
        plate_dims = {size: PlateMap.plate_size_from_num_wells(size)
                      for size in plate_sizes.unique()}

        plate_names = set(plate_sizes.index)

        for pl_name in sorted(plate_names):
            if pl_name not in self._plate_objects.keys():
                plate_size = plate_sizes.loc[pl_name]
                plate_width, plate_height = plate_dims[plate_size]
                plates_to_create[pl_name] = Plate(
                    dataset=self.dataset,
                    name=pl_name,
                    last_annotated=timezone.now(),
                    width=plate_width,
                    height=plate_height
                )

        if plates_to_create:
            Plate.objects.bulk_create(plates_to_create.values(),
                                      batch_size=settings.DB_MAX_BATCH_SIZE)

            # Depending on DB backend, we may need to refetch to get the PKs
            # (Thankfully not PostgreSQL)
            if plates_to_create[list(plates_to_create)[0]].pk is None:
                for p in Plate.objects.filter(dataset_id=self.dataset.id):
                    self._plate_objects[p.name] = p
            else:
                # Otherwise, just add the plates into the local cache
                self._plate_objects.update(plates_to_create)

        # Create wells
        self._create_wells(df_data, df_wells, cell_lines)

        # Create welldrugs
        self._create_welldrugs(df_wells, drug_nums, drugs)

        well_measurements_to_create = []

        # Create wellmeasurements from controls
        if df_data.controls is not None:
            ctrl_idx_names = df_data.controls.index.names
            ctrl_plate_idx = ctrl_idx_names.index('plate')
            ctrl_assay_idx = ctrl_idx_names.index('assay')
            ctrl_timepoint_idx = ctrl_idx_names.index('timepoint')
            for row in df_data.controls.itertuples():
                pl_name = row.Index[ctrl_plate_idx]
                plate = self._plate_objects[pl_name]
                well_num = row.well_num
                well_id = self._well_sets[plate.id][well_num]
                well_measurements_to_create.append(WellMeasurement(
                  well_id=well_id,
                  assay=row.Index[ctrl_assay_idx],
                  timepoint=row.Index[ctrl_timepoint_idx],
                  value=row.value
                ))

        # Create wellmeasurements from non-controls
        assays = df_data.assays.reset_index()
        assays.set_index('well_id', inplace=True)
        assays = pd.merge(assays, df_wells[['plate', 'well_num']],
                          how='left', left_index=True, right_index=True)
        for row in assays.itertuples():
            pl_name = row.plate
            plate = self._plate_objects[pl_name]
            well_num = row.well_num
            well_id = self._well_sets[plate.id][well_num]
            well_measurements_to_create.append(WellMeasurement(
              well_id=well_id,
              assay=row.assay,
              timepoint=row.timepoint,
              value=row.value
            ))

        WellMeasurement.objects.bulk_create(
            well_measurements_to_create,
            batch_size=settings.DB_MAX_BATCH_SIZE
        )

        self.dataset.save()

    @transaction.atomic
    def parse_thunor_h5(self):
        self.file_format = 'HDF5'

        df_data = _read_hdf_unstacked(self.plate_file.read())
        self._create_db_platefile()
        self.plate_file.close()

        self._import_thunor(df_data)

    @transaction.atomic
    def parser_thunor_vanderbilt_hts(self, sep='\t'):
        self.file_format = 'Vanderbilt HTS Core'

        from thunor.io import read_vanderbilt_hts
        self.plate_file.file.seek(0)
        try:
            df_data = read_vanderbilt_hts(self.plate_file.file, sep=sep,
                                          _unstacked=True)
        except KeyError as e:
            raise PlateFileUnknownFormat(e)

        self._create_db_platefile()
        self.plate_file.close()

        self._import_thunor(df_data)

    @transaction.atomic
    def parse_platefile_synergy_neo(self, sep='\t'):
        """
        Extracts data from a platefile

        Data includes number of plates, assay types, plate names, number of well
        rows and cols.
        """
        if sep != '\t':
            raise PlateFileUnknownFormat('Synergy Neo can only be parsed as '
                                         'tab-separated')

        self.file_format = 'Synergy Neo'
        pd = self.plate_file.read()
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

    @transaction.atomic
    def parse_platefile_imagexpress(self):
        self.file_format = 'ImageXpress'
        self.plate_file.file.seek(0)
        wb = xlrd.open_workbook(file_contents=self.plate_file.read())
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
        # TODO: Replace with sparse plate implementation
        if plate_name is None or plate_name == '':
            raise PlateFileParseException('Plate name must not be empty')

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
                self._well_sets[plate.id].update({
                    w.well_num: w.pk for w in wells})

        if plate.id not in self._well_sets:
            self._well_sets[plate.id].update({
                w.well_num: w.pk for w in plate.well_set.all()})

        return plate

    def parse_platefile(self):
        """
        Attempt to auto-detect platefile format and parse
        """
        # Try to use file extension
        file_type = None
        file_first_kb = None
        for ext, fmt in self.supported_extensions.items():
            if self.plate_file.name and self.plate_file.name.endswith(ext):
                file_type = fmt
                break

        if file_type is None:
            # Try to use MIME type
            file_first_kb = self.plate_file.read(1024)

            mimetype = magic.from_buffer(
                file_first_kb,
                mime=True
            )
            self.plate_file.file.seek(0)
            file_type = self.supported_mimetypes.get(mimetype, None)

        if file_type == 'excel':
            self.parse_platefile_imagexpress()
        elif file_type == 'text':
            if file_first_kb is None:
                file_first_kb = self.plate_file.read(1024)
            if not isinstance(file_first_kb, str):
                try:
                    file_first_kb = file_first_kb.decode('utf-8')
                except UnicodeDecodeError:
                    raise PlateFileUnknownFormat('Error opening file with '
                                                 'UTF-8 encoding (does file '
                                                 'contain non-standard '
                                                 'characters?)')
            if file_first_kb.find('cell.count') != -1 and file_first_kb.find(
                    'drug1.conc') != -1:
                parsers = (self.parser_thunor_vanderbilt_hts,
                           self.parse_platefile_synergy_neo)
            else:
                parsers = (self.parse_platefile_synergy_neo,
                           self.parser_thunor_vanderbilt_hts)

            sep = '\t'
            first_line = file_first_kb.split('\n')[0]
            if ',' in first_line:
                sep = ','

            for parser in parsers:
                try:
                    parser(sep=sep)
                    break
                except PlateFileUnknownFormat:
                    pass
            else:
                raise PlateFileParseException('File type not recognized. '
                                              'Please check the format.')
        elif file_type == 'hdf':
            self.parse_thunor_h5()
        else:
            raise PlateFileParseException('File type not supported: {}'.
                                          format(file_type or mimetype))

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
