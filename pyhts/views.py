from django.shortcuts import render, redirect, Http404
from django.template.response import TemplateResponse
from django.contrib import auth
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from .forms import CentredAuthForm, PlateFileForm
from django.views.generic.edit import FormView
from django.http import JsonResponse, HttpResponseBadRequest
from .models import HTSDataset, PlateFile, CellLine, Drug
import re
from math import sqrt
from itertools import cycle
from numpy import repeat


def _handle_login(request):
    if request.method == 'POST':
        form = CentredAuthForm(data=request.POST)
        if form.is_valid():
            auth.login(request, form.get_user())
            return redirect('pyhts:home')
    else:
        form = CentredAuthForm()
    return render(request, 'registration/login.html', {'form': form})


def _quickparse_platefile(pd, file_timepoint_guess_hrs=None):
    """
    Extracts high-level metadata from a platefile

    Data includes number of plates, assay types, plate names, number of well
    rows and cols.
    """
    plates = pd.split('Field Group\n\nBarcode:')
    plate_json = []

    for p in plates:
        if len(p.strip()) == 0:
            continue
        barcode_and_rest = p.split('\n', 1)
        barcode = barcode_and_rest[0].strip()

        plate_timepoint = _guess_timepoint_hrs(barcode) or file_timepoint_guess_hrs

        # Each plate can have multiple assays
        assays = re.split('\n\s*\n', barcode_and_rest[1])
        assay_names = []

        well_cols = 0
        well_rows = 0

        for a in assays:
            a_strp = a.strip()
            if len(a_strp) == 0:
                continue

            well_lines = a.split('\n')
            assay_names.append(well_lines[0].strip())
            # @TODO: Throw an error if well rows and cols not same for all
            # assays
            well_cols = len(well_lines[1].split())
            # Minus 2: One for assay name, one for column headers
            well_rows = len(well_lines) - 2

        plate_json.append({'well_cols': well_cols,
                           'well_rows': well_rows,
                           'name': barcode,
                           'timepoint_guess_hrs': plate_timepoint,
                           'assays': assay_names})

    if not plate_json:
        raise ValueError('File contains no readable plates')

    return plate_json


def _guess_timepoint_hrs(string):
    tp_guess = re.search(r'(?i)([0-9]+)[-_\s]*(h\W|hr|hour)', string)
    return int(tp_guess.group(1)) if tp_guess else None


def _handle_platefile(pf):
    # TODO: Ensure file isn't too big, check filetype etc.

    file_timepoint_guess = _guess_timepoint_hrs(pf.name)

    pd = pf.read().replace('\r\n', '\n')
    return _quickparse_platefile(pd,
                                 file_timepoint_guess_hrs=file_timepoint_guess)


def home(request):
    if not request.user.is_authenticated:
        return _handle_login(request)

    return render(request, 'home.html')


def logout(request):
    auth.logout(request)
    return redirect('pyhts:home')


class PlateUpload(FormView):
    form_class = PlateFileForm
    template_name = 'plate_upload.html'

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(PlateUpload, self).dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        dataset_id = request.POST.get('dataset_id')
        files = request.FILES.getlist('file_field')
        if form.is_valid():
            response = {'success': False}

            dataset = HTSDataset(owner=request.user, id=dataset_id)
            if not dataset:
                form.add_error('dataset_id', 'Dataset %s does not exist or '
                                             'you do not have access' %
                                             dataset_id)
                return JsonResponse({'success': False, 'errors':
                                    form.errors.as_json()})

            file_status = {}
            for f in files:
                try:
                    plates = _handle_platefile(f)
                    tpf = PlateFile(dataset=dataset, file=f)
                    tpf.save()
                    response['success'] = True
                    file_status[tpf.id] = {'success': True,
                                           'name': f.name,
                                           'message': '{} plates detected'
                                                      .format(len(plates)),
                                           'plates': plates
                                           }
                except ValueError as ve:
                    file_status['_failed'] = {'success': False,
                                              'name': f.name,
                                              'message': ve.message}
            response['files'] = file_status
            return JsonResponse(response)
        else:
            return JsonResponse({'success': False, 'errors':
                                form.errors.as_json()})


def _plates_names_file_id(request, file_id):
    pf = PlateFile.objects.get(id=file_id)
    if not pf or pf.owner_id != request.user.id:
        raise Http404
    pdata = _handle_platefile(pf.file)
    pnames = [p['name'] for p in pdata]
    return pnames


@login_required
def ajax_get_plates(request, file_id):
    return JsonResponse({'names': _plates_names_file_id(request, file_id)})


@login_required
def ajax_create_dataset(request):
    name = request.POST.get('name')
    if not name:
        return HttpResponseBadRequest()
    dset = HTSDataset.objects.create(owner=request.user, name=name)
    return JsonResponse({'name': dset.name, 'id': dset.id})


@login_required
def ajax_create_cellline(request):
    name = request.POST.get('name')
    if not name:
        return HttpResponseBadRequest()
    cl = CellLine.objects.get_or_create(name=name)
    all_cls = CellLine.name_list()
    return JsonResponse({'names': list(all_cls)})


@login_required
def ajax_create_drug(request):
    name = request.POST.get('name')
    if not name:
        return HttpResponseBadRequest()
    dr = Drug.objects.get_or_create(name=name)
    all_drugs = Drug.name_list()
    return JsonResponse({'names': list(all_drugs)})

@login_required
def plate_designer(request):
    pf = PlateFile.objects.filter(process_date=None)
    #plates = _handle_platefile(pf.first().file)

    # @TODO: Handle case where pf is None

    plates = _plates_names_file_id(request, file_id=pf.first().id)

    # @TODO: Handle other plate sizes
    num_wells = 384
    num_rows = int(sqrt(num_wells / 1.5))
    num_cols = int(num_wells / num_rows)

    row_iterator = map(chr, range(65, 65 + num_rows))
    col_iterator = range(1, num_cols + 1)

    def well_generator(number_of_wells):
        row_it = iter(repeat(row_iterator, num_cols))
        col_it = cycle(col_iterator)
        for i in range(number_of_wells):
            yield {'well': i,
                   'row': row_it.next(),
                   'col': col_it.next()}

    response = TemplateResponse(request, 'plate_designer.html', {
        'num_wells': num_wells,
        'wells': well_generator(num_wells),
        'rows_range': row_iterator,
        'cols_range': col_iterator,
        'plate_files': pf,
        'plates': plates,
        'cell_lines': CellLine.name_list(),
        'drugs': Drug.name_list()
    })
    return response
