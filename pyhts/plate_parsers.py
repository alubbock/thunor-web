import re
from django.core.files.uploadedfile import UploadedFile
from datetime import timedelta, datetime
from .models import PlateFile, Plate, WellMeasurement
from django.db import IntegrityError, transaction


class PlateFileParseException(Exception):
    pass


_RE_TIME_HOURS = r'(?P<time_hours>[0-9]+)[-_\s]*(h\W|hr|hour)'
_RE_PLATE_TIME_HOURS = r'(?P<plate_id>.+)-' + _RE_TIME_HOURS
regexes = {'time_hours': re.compile(_RE_TIME_HOURS, re.IGNORECASE),
           'plate_id_time_hours': re.compile(_RE_PLATE_TIME_HOURS,
                                             re.IGNORECASE)}


def extract_timepoint(string):
    """
    Tries to extract a numeric time point from a string
    """
    tp = regexes['time_hours'].search(string)
    return timedelta(hours=int(tp.group('time_hours'))) if tp else None


def extract_plate_and_timepoint(string):
    """
    Tries to extract a plate name and time point from a string
    """
    tp = regexes['plate_id_time_hours'].match(string)
    return {'plate': tp.group('plate_id'),
            'timepoint': timedelta(hours=int(tp.group('time_hours')))} if tp \
        else None


def parse_platefile_readerX(pd, platefile, dataset, file_timepoint=None):
    """
    Extracts data from a platefile

    Data includes number of plates, assay types, plate names, number of well
    rows and cols.
    """
    plates = pd.split('Field Group\n\nBarcode:')

    wells = []

    for p in plates:
        if len(p.strip()) == 0:
            continue
        barcode_and_rest = p.split('\n', 1)
        barcode = barcode_and_rest[0].strip()

        plate_and_timepoint = extract_plate_and_timepoint(barcode)

        if not plate_and_timepoint:
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
                    dataset=dataset,
                    name=plate_name,
                    defaults={'plate_file': platefile, 'width': well_cols,
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
            raise PlateFileParseException('File contains no readable plates')

        if len(wells) % (well_cols * well_rows) != 0:
            raise PlateFileParseException('Extracted an unexpected number of '
                                          'wells from plate (plate: %s, wells:'
                                          ' %d)'.format(plate_name,
                                                        len(wells)))

    WellMeasurement.objects.bulk_create(wells)


def _str_universal_newlines(a_string):
    return a_string.replace('\r\n', '\n').replace('\r', '\n')


def parse_platefile(pf, dataset):
    # TODO: Ensure file isn't too big, check filetype etc.
    timepoint = extract_timepoint(pf.name)

    if isinstance(pf, UploadedFile):
        try:
            pf.open()
            pd = _str_universal_newlines(pf.read().decode('utf-8'))
        except UnicodeDecodeError:
            raise PlateFileParseException('Error opening file with UTF-8 '
                                          'encoding (does file contain '
                                          'invalid characters?)')
    else:
        raise PlateFileParseException('Cannot parse object of type: '
                                      '{}'.format(type(pf)))

    platefile = PlateFile(file=pf)
    platefile.save()

    try:
        with transaction.atomic():
            return parse_platefile_readerX(pd,
                                           platefile=platefile,
                                           dataset=dataset,
                                           file_timepoint=timepoint)
    except IntegrityError:
        raise PlateFileParseException('A file with the same plate and '
                                      'timepoints has been uploaded to this '
                                      'dataset before')
