import re
from django.core.files import File
from django.utils import timezone
from datetime import timedelta
from .models import PlateFile, Plate, Well, WellMeasurement, CellLine, Drug,\
    WellDrug
from django.db import IntegrityError, transaction
import xlrd
import magic
import collections
from thunor.io import read_vanderbilt_hts_single_df, read_hdf, PlateMap
import math
import pandas as pd


class PlateFileParseException(Exception):
    pass


class PlateFileUnknownFormat(PlateFileParseException):
    pass


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

    @transaction.atomic
    def parse_thunor_h5(self):
        self.file_format = 'HDF5'
        # TODO: Get plate size dynamically from file
        PLATE_WIDTH = 24
        PLATE_HEIGHT = 16

        df_data = read_hdf(self.plate_file.read())

        doses_unstacked = df_data.doses_unstacked()

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
        df_wells = df_data.doses.copy().reset_index()
        df_wells.set_index('well_id', inplace=True)
        plates_to_create = {}
        for row in df_wells.itertuples():
            pl_name = row.plate_id

            if pl_name not in self._plate_objects.keys():
                plates_to_create[pl_name] = Plate(
                    dataset=self.dataset,
                    name=pl_name,
                    last_annotated=timezone.now(),
                    width=PLATE_WIDTH,
                    height=PLATE_HEIGHT
                )

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

        # Create wells
        well_sets_to_create = collections.defaultdict(list)
        for row in df_wells.itertuples():
            pl_name = row.plate_id
            plate = self._plate_objects[pl_name]
            well_no = row.well_num
            wells = self._well_sets.get(plate.id, None)
            if not wells:
                if not well_sets_to_create[plate.id]:
                    for well_idx in range(PLATE_WIDTH * PLATE_HEIGHT):
                        well_sets_to_create[plate.id].append(Well(
                            plate_id=plate.id,
                            well_num=well_idx
                        ))

                well_sets_to_create[plate.id][well_no].cell_line_id = \
                    cell_lines[row.cell_line]

        # Add any control wells
        ctrl_idx_names = df_data.controls.index.names
        ctrl_plate_idx = ctrl_idx_names.index('plate')
        ctrl_assay_idx = ctrl_idx_names.index('assay')
        ctrl_timepoint_idx = ctrl_idx_names.index('timepoint')
        ctrl_cell_line_idx = ctrl_idx_names.index('cell_line')
        for row in df_data.controls.itertuples():
            pl_name = row.Index[ctrl_plate_idx]
            plate = self._plate_objects[pl_name]
            well_no = row.well_num

            well_sets_to_create[plate.id][well_no].cell_line_id = \
                cell_lines[row.Index[ctrl_cell_line_idx]]

        # Run the DB query to create the well sets
        # Use a generator to avoid creating an intermediate list
        def well_generator():
            for plate_wells in well_sets_to_create.values():
                for well in plate_wells:
                    yield well

        Well.objects.bulk_create(well_generator())

        # Again, on non-PostgreSQL datasets, we'll need to fetch the PKs
        if well_sets_to_create and \
                        well_sets_to_create[list(well_sets_to_create)[0]][
                            0].pk \
                        is None:
            self._get_well_sets_db(well_sets_to_create.keys())
        else:
            for plate_id, well_objs in well_sets_to_create.items():
                self._well_sets[plate_id] = [w.pk for w in well_objs]

        # Create welldrugs
        well_drugs_to_create = []
        for row in df_wells.itertuples():
            pl_name = row.plate_id
            plate = self._plate_objects[pl_name]
            well_num = row.well_num
            well_id = self._well_sets[plate.id][well_num]
            for order, drug in enumerate(row.drug):
                well_drugs_to_create.append(
                    WellDrug(
                        well_id=well_id,
                        drug_id=drugs[drug],
                        order=order,
                        dose=row.dose[order]
                    )
                )

        WellDrug.objects.bulk_create(well_drugs_to_create)

        # Create wellmeasurements from controls
        well_measurements_to_create = []
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
        assays = pd.merge(assays, df_wells[['plate_id', 'well_num']],
                          how='left', left_index=True, right_index=True)
        for row in assays.itertuples():
            pl_name = row.plate_id
            plate = self._plate_objects[pl_name]
            well_num = row.well_num
            well_id = self._well_sets[plate.id][well_num]
            well_measurements_to_create.append(WellMeasurement(
              well_id=well_id,
              assay=row.assay,
              timepoint=row.timepoint,
              value=row.value
            ))

        WellMeasurement.objects.bulk_create(well_measurements_to_create)

        self.dataset.save()

    @transaction.atomic
    def parse_platefile_vanderbilt_hts(self, sep='\t'):
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

        self.plate_file.file.seek(0)
        try:
            pd = read_vanderbilt_hts_single_df(self.plate_file.file, sep=sep)
        except Exception as e:
            raise PlateFileUnknownFormat(e)

        # Sanity checks
        if (pd['cell.count'] < 0).any():
            raise PlateFileParseException('cell.count contains negative '
                                          'values')

        if (pd['time'] < self._ZERO_TIMEDELTA).any():
            raise PlateFileParseException('time contains negative value(s)')

        drug_no = 1
        drug_nums = []
        while ('drug%d' % drug_no) in pd.columns.values:
            if (pd['drug%d.conc' % drug_no] < 0).any():
                raise PlateFileParseException('drug%d.conc contains negative '
                                              'value(s)' % drug_no)
            for du in pd['drug%d.units' % drug_no].unique():
                if not isinstance(du, str) and math.isnan(du):
                    continue

                if du != 'M':
                    raise PlateFileParseException(
                        'Only supported drug concentration unit is M (not {})'.
                            format(du))
            drug_nums.append(drug_no)
            drug_no += 1

        # Check for duplicate drugs in any row
        if len(drug_nums) == 2:
            # Ignore rows where both concentrations are zero
            dup_drugs = pd.loc[pd['drug1.conc'] != 0 | pd['drug2.conc'] !=
                               0, :]
            dup_drugs = dup_drugs.loc[pd['drug1'] == pd['drug2'], :]
            if not dup_drugs.empty:
                ind_val = dup_drugs.index.tolist()[0]
                well_name = pm.well_id_to_name(ind_val[1])
                raise PlateFileParseException(
                    '{} entries have the same drug listed in the same well, '
                    'e.g. plate "{}", well {}'.format(
                        len(dup_drugs),
                        ind_val[0],
                        well_name
                    )
                )

        # Check for duplicate time point definitions
        dup_timepoints = pd.set_index('time', append=True)
        if dup_timepoints.index.duplicated().any():
            dups =  dup_timepoints.loc[dup_timepoints.index.duplicated(),
                                       :].index.tolist()
            n_dups = len(dups)
            first_dup = dups[0]

            raise PlateFileParseException(
                'There are {} duplicate time points defined, e.g. plate "{}"'
                ', well {}, time {}'.format(
                    n_dups,
                    first_dup[0],
                    pm.well_id_to_name(first_dup[1]),
                    first_dup[2]
                )
            )

        # OK, we'll assume all is good and start hitting the DB
        self._create_db_platefile()

        # Get/create cell lines
        cell_lines = {}
        for cl in pd['cell.line'].unique():
            if not isinstance(cl, str):
                continue
            cl_obj, _ = CellLine.objects.get_or_create(
                name__iexact=cl,
                defaults={'name': cl}
            )
            cell_lines[cl] = cl_obj.pk

        # Get/create drugs
        drugs = {}
        for drug_no in drug_nums:
            for dr in pd['drug%d' % drug_no].unique():
                if not isinstance(dr, str):
                    continue
                dr_obj, _ = Drug.objects.get_or_create(
                    name__iexact=dr,
                    defaults={'name': dr}
                )
                drugs[dr] = dr_obj.pk

        # Get/create plates
        plate_names = [pn for pn in pd.index.get_level_values(
                       'upid').unique() if isinstance(pn, str)]
        plates_to_create = {}
        for pl_name in plate_names:
            if pl_name not in self._plate_objects.keys():
                if 'expt.id' in pd.columns.values:
                    expt_id = pd.loc[pl_name]['expt.id'].unique()
                    if len(expt_id) > 1:
                        raise PlateFileParseException('Plate %s contains '
                                                      'more than one '
                                                      'expt.id' % pl_name)
                    expt_id = expt_id[0]
                else:
                    expt_id = None

                if 'expt.date' in pd.columns.values:
                    expt_date = pd.loc[pl_name]['expt.date'].unique()
                    if len(expt_date) > 1:
                        raise PlateFileParseException('Plate %s contains '
                                                      'more than one '
                                                      'expt.date' % pl_name)
                    expt_date = expt_date[0]
                else:
                    expt_date = None

                plates_to_create[pl_name] = Plate(
                    dataset=self.dataset,
                    name=pl_name,
                    last_annotated=timezone.now(),
                    width=pm.width,
                    height=pm.height,
                    expt_id=expt_id,
                    expt_date=expt_date
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
            plate = self._plate_objects[pl_name]
            well_set = self._well_sets[plate.id]
            for well, dat in pd.loc[pl_name].groupby(level='well'):
                well_id = well_set[well]
                for drug_no in drug_nums:
                    drug_name = dat['drug%d' % drug_no].unique()
                    if len(drug_name) > 1:
                        raise PlateFileParseException(
                            'Plate {}, well {} has more than one drug defined '
                            'in drug%d column'.format(
                                pl_name, pm.well_id_to_name(well), drug_no
                            )
                        )
                    drug_name = drug_name[0]
                    drug_conc = dat['drug%d.conc' % drug_no].unique()
                    if len(drug_conc) > 1:
                        raise PlateFileParseException(
                            'Plate {}, well {} has more than one drug '
                            'concentration defined in drug%d.conc '
                            'column'.format(
                                pl_name, pm.well_id_to_name(well), drug_no
                            )
                        )
                    drug_conc = drug_conc[0]
                    if drug_conc != 0.0:
                        well_drugs_to_create.append(
                            WellDrug(
                                well_id=well_id,
                                drug_id=drugs[drug_name],
                                order=(drug_no - 1),
                                dose=drug_conc
                            )
                        )

                well_measurements_to_create.extend([
                    WellMeasurement(
                        well_id=well_id,
                        assay='Cell count',
                        timepoint=measurement.time,
                        value=measurement._1
                    )
                    for measurement in
                    dat[['time', 'cell.count']].itertuples(index=False)
                ])

        # Fire off the bulk DB queries...
        WellDrug.objects.bulk_create(well_drugs_to_create)
        WellMeasurement.objects.bulk_create(well_measurements_to_create)

        self.dataset.save()

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
                parsers = (self.parse_platefile_vanderbilt_hts,
                           self.parse_platefile_synergy_neo)
            else:
                parsers = (self.parse_platefile_synergy_neo,
                           self.parse_platefile_vanderbilt_hts)

            sep = '\t'
            first_line = file_first_kb.split('\n')[0]
            if ',' in first_line:
                sep = ','

            parsed = False
            for parser in parsers:
                try:
                    parser(sep=sep)
                    parsed = True
                    break
                except PlateFileUnknownFormat:
                    pass
            if not parsed:
                raise PlateFileParseException('File type not recognized. '
                                              'Please check the format.')
        elif file_type == 'hdf':
            self.parse_thunor_h5()
        else:
            raise PlateFileParseException('File type not supported: {}'.
                                          format(mimetype))

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
