from django.shortcuts import render, redirect, Http404
from django.template.response import TemplateResponse
from django.contrib import auth
from .forms import CentredAuthForm, PlateFileForm
from django.views.generic.edit import FormView
from django.http import JsonResponse, HttpResponseBadRequest
from .models import PlateFile, CellLine
import re


def _handle_login(request):
    if request.method == 'POST':
        form = CentredAuthForm(data=request.POST)
        if form.is_valid():
            auth.login(request, form.get_user())
            return redirect('pyhts:home')
    else:
        form = CentredAuthForm()
    return render(request, 'registration/login.html', {'form': form})


def _quickparse_platefile(pd):
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
                           'assays': assay_names})

    if not plate_json:
        raise ValueError('File contains no readable plates')

    return plate_json


def _handle_platefile(pf):
    ## @TODO: Ensure file isn't too big, check filetype etc.
    pd = pf.read().replace('\r\n', '\n')
    return _quickparse_platefile(pd)


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

    def post(self, request, *args, **kwargs):
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        files = request.FILES.getlist('file_field')
        if form.is_valid():
            response = {'success': False}
            file_status = {}
            for f in files:
                try:
                    plates = _handle_platefile(f)
                    tpf = PlateFile(owner=request.user, file=f)
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


def ajax_get_plates(request, file_id):
    return JsonResponse({'names': _plates_names_file_id(request, file_id)})


def ajax_create_cellline(request):
    name = request.POST.get('name')
    if not name:
        return HttpResponseBadRequest()
    cl = CellLine.objects.get_or_create(name=name)
    all_cls = CellLine.objects.order_by('name').values_list('name', flat=True)
    return JsonResponse({'names': list(all_cls)})


def plate_designer(request):
    pf = PlateFile.objects.filter(process_date=None)
    #plates = _handle_platefile(pf.first().file)

    # @TODO: Handle case where pf is None

    plates = _plates_names_file_id(request, file_id=pf.first().id)
    response = TemplateResponse(request, 'plate_designer.html', {
        'rows': map(chr, range(65, 65+18)),
        'cols': range(1, 25),
        'plate_files': pf,
        'plates': plates,
        'cell_lines': CellLine.objects.order_by('name').values_list('name',
                                                                    flat=True)
    })
    return response
