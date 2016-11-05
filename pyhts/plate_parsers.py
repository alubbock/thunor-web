from helpers import guess_timepoint_hrs
import re


def parse_platefile_readerX(pd, quick_parse=False,
                            file_timepoint_guess_hrs=None):
    """
    Extracts high-level metadata from a platefile

    Data includes number of plates, assay types, plate names, number of well
    rows and cols.
    """
    pd = pd.replace('\r\n', '\n')

    plates = pd.split('Field Group\n\nBarcode:')
    plate_json = []

    for p in plates:
        if len(p.strip()) == 0:
            continue
        barcode_and_rest = p.split('\n', 1)
        barcode = barcode_and_rest[0].strip()

        plate_timepoint = guess_timepoint_hrs(barcode) or \
                          file_timepoint_guess_hrs

        # Each plate can have multiple assays
        assays = re.split('\n\s*\n', barcode_and_rest[1])
        assay_names = []

        well_cols = 0
        well_rows = 0
        well_values = {}

        for a in assays:
            a_strp = a.strip()
            if len(a_strp) == 0:
                continue

            well_lines = a.split('\n')
            assay_name = well_lines[0].strip()
            assay_names.append(assay_name)
            # @TODO: Throw an error if well rows and cols not same for all
            # assays
            well_cols = len(well_lines[1].split())
            # Minus 2: One for assay name, one for column headers
            well_rows = len(well_lines) - 2

            if not quick_parse:
                well_values[assay_name] = []
                # Read the actual well values
                for row in range(2, len(well_lines)):
                    well_values[assay_name] += [float(val) for val
                                                in well_lines[row].split(
                                                '\t')[1:-1]]

        plate_dict = {'well_cols': well_cols,
                      'well_rows': well_rows,
                      'name': barcode,
                      'timepoint_guess_hrs': plate_timepoint,
                      'assays': assay_names}

        if not quick_parse:
            plate_dict['well_values'] = well_values

        plate_json.append(plate_dict)

    if not plate_json:
        raise ValueError('File contains no readable plates')

    return plate_json
