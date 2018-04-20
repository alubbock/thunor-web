from django.shortcuts import render, Http404
from django.http import JsonResponse, HttpResponse
from django.utils.html import strip_tags
from django.db.models import Q
from thunorweb.models import HTSDataset, CellLineTag, DrugTag
from thunor.plots import plot_time_course, plot_drc, plot_drc_params, \
    plot_ctrl_dip_by_plate, plot_plate_map, CannotPlotError, \
    IC_REGEX, EC_REGEX, E_REGEX, E_REL_REGEX
from thunor.curve_fit import AAFitWarning, fit_params_from_base
from thunor.viability import viability
from thunor.helpers import plotly_to_dataframe
from plotly.utils import PlotlyJSONEncoder
from thunorweb.pandas import df_doses_assays_controls, df_dip_rates, \
    df_ctrl_dip_rates, NoDataException, df_curve_fits
import warnings
from collections import defaultdict
from thunorweb.views import login_required_unless_public, _assert_has_perm
from thunorweb.views.plate_mapper import ajax_load_plate


@login_required_unless_public
def ajax_get_plot(request, file_type='json'):
    if file_type == 'csv':
        permission_required = 'download_data'
    else:
        permission_required = 'view_plots'

    try:
        plot_type = request.GET['plotType']

        dataset_id = int(request.GET['datasetId'])
        dataset2_id = request.GET.get('dataset2Id', None)
        if dataset2_id == "":
            dataset2_id = None
        if dataset2_id is not None:
            dataset2_id = int(dataset2_id)
        cell_line_id = request.GET.getlist('c')
        cell_line_tag_ids = request.GET.getlist('cT')
        aggregate_cell_lines = request.GET.get('aggregateCellLines', False) \
                               == "true"
        perm_query = Q(owner=None)
        if request.user.is_authenticated():
            perm_query |= Q(owner=request.user)
        if not cell_line_id and cell_line_tag_ids:
            cell_line_tag_base_query = CellLineTag.objects.filter(
                perm_query).filter(id__in=cell_line_tag_ids)
            if not aggregate_cell_lines:
                cell_line_id = cell_line_tag_base_query.values_list(
                    'cell_lines__id', flat=True).distinct()
            else:
                cell_line_tag_objs = cell_line_tag_base_query.values_list(
                    'tag_category', 'tag_name', 'cell_lines__id',
                    'cell_lines__name')
                cell_line_id = [cl[2] for cl in cell_line_tag_objs]
                cats = set(cl[0] for cl in cell_line_tag_objs)
                use_cats = len(cats) > 1
                # if not use_cats:
                #     (aggregate_cell_lines_group, ) = cats

                aggregate_cell_lines = defaultdict(list)
                for cl in cell_line_tag_objs:
                    tag_name = '{} [{}]'.format(cl[1], cl[0]) if use_cats \
                        else cl[1]
                    aggregate_cell_lines[tag_name].append(cl[3])
        drug_id = request.GET.getlist('d')
        drug_tag_ids = request.GET.getlist('dT')
        aggregate_drugs = request.GET.get('aggregateDrugs', False) == "true"
        if not drug_id and drug_tag_ids:
            drug_tag_base_query = DrugTag.objects.filter(
                perm_query).filter(id__in=drug_tag_ids)
            if not aggregate_drugs:
                drug_id = drug_tag_base_query.values_list(
                    'drugs__id', flat=True).distinct()
            else:
                drug_tag_objs = drug_tag_base_query.values_list(
                    'tag_category', 'tag_name', 'drugs__id',
                    'drugs__name')
                drug_id = [dr[2] for dr in drug_tag_objs]
                use_cats = len(set(dr[0] for dr in drug_tag_objs)) > 1

                aggregate_drugs = defaultdict(list)
                for dr in drug_tag_objs:
                    tag_name = '{} [{}]'.format(dr[1], dr[0]) if use_cats \
                        else dr[1]
                    aggregate_drugs[tag_name].append(dr[3])

        if plot_type != 'qc' and (not cell_line_id or not drug_id):
            return HttpResponse('Please enter at least one cell line and '
                                'drug', status=400)

        cell_line_id = [int(cl) for cl in cell_line_id]
        drug_ids = []
        for dr in drug_id:
            try:
                drug_ids.append(int(dr))
            except ValueError:
                drug_ids.append([int(d) for d in dr.split(",")])
        drug_id = drug_ids

        assay = request.GET.get('assayId')
        yaxis = request.GET.get('logTransform', 'None')

    except (KeyError, ValueError):
        raise Http404()

    try:
        dataset = HTSDataset.objects.get(pk=dataset_id)
    except HTSDataset.DoesNotExist:
        raise Http404()

    _assert_has_perm(request, dataset, permission_required)

    if plot_type == 'tc':
        if len(drug_id) > 1 or len(cell_line_id) > 1:
            return HttpResponse('Please select exactly one cell line and '
                                'drug for time course plot', status=400)

        try:
            df_data = df_doses_assays_controls(
                dataset=dataset,
                drug_id=drug_id,
                cell_line_id=cell_line_id,
                assay=assay
            )
        except NoDataException:
            return HttpResponse('No data found for this request. This '
                                'drug/cell line/assay combination may not '
                                'exist.', status=400)
        if assay is None:
            assay = df_data.assays.index.get_level_values('assay')[0]

        overlay_dip_fit = request.GET.get('overlayDipFit', 'false') == 'true'

        if overlay_dip_fit and assay != df_data.dip_assay_name:
            return HttpResponse('Can only overlay DIP rate on cell '
                                'proliferation assays', status=400)

        plot_fig = plot_time_course(
            df_data,
            log_yaxis=yaxis == 'log2',
            assay_name=assay,
            show_dip_fit=overlay_dip_fit,
            subtitle=dataset.name
        )
    elif plot_type in ('drc', 'drpar'):
        plot_fig = _dose_response_plot(request, dataset, dataset2_id,
                                       permission_required, drug_id,
                                       cell_line_id, plot_type,
                                       aggregate_cell_lines, aggregate_drugs)
        if isinstance(plot_fig, HttpResponse):
            return plot_fig
    elif plot_type == 'qc':
        qc_view = request.GET.get('qcView', None)
        if qc_view == 'ctrldipbox':
            ctrl_dip_data = df_ctrl_dip_rates(dataset_id)
            if ctrl_dip_data is None:
                return HttpResponse('No control wells were detected in this '
                                    'dataset.', status=400)
            plot_fig = plot_ctrl_dip_by_plate(ctrl_dip_data)
        elif qc_view == 'dipplatemap':
            plate_id = request.GET.get('plateId', None)
            try:
                plate_id = int(plate_id)
            except ValueError:
                return HttpResponse('Integer plateId required', status=400)
            pl_data = ajax_load_plate(request, plate_id,
                                      return_as_platedata=True,
                                      use_names=True)
            plot_fig = plot_plate_map(pl_data, color_by='dip_rates')
        else:
            return HttpResponse('Unimplemented QC view: {}'.format(qc_view),
                                status=400)
    else:
        return HttpResponse('Unimplemented plot type: %s' % plot_type,
                            status=400)

    as_attachment = request.GET.get('download', '0') == '1'

    if file_type == 'json':
        response = JsonResponse(plot_fig, encoder=PlotlyJSONEncoder)
    elif file_type == 'csv':
        response = HttpResponse(plotly_to_dataframe(plot_fig).to_csv(),
                                content_type='text/csv')
    elif file_type == 'html':
        response = render(request, 'plotly_plot.html',
            {'data': JsonResponse(plot_fig,
                                  encoder=PlotlyJSONEncoder).content})
    else:
        return HttpResponse('Unknown file type: %s' % file_type, status=400)

    if as_attachment:
        try:
            title = plot_fig['layout']['title']
        except KeyError:
            title = 'Plot'
        response['Content-Disposition'] = \
            'attachment; filename="{}.{}"'.format(strip_tags(title), file_type)

    return response


def _dose_response_plot(request, dataset, dataset2_id,
                        permission_required, drug_id, cell_line_id,
                        plot_type, aggregate_cell_lines,
                        aggregate_drugs):
    dataset_id = dataset.id
    response_metric = request.GET.get('drMetric', 'dip')
    if response_metric not in ('dip', 'viability'):
        return HttpResponse('Unknown metric. Supported values: dip or '
                            'viability.', status=400)
    if dataset2_id is not None:
        try:
            dataset2 = HTSDataset.objects.get(pk=dataset2_id)
        except HTSDataset.DoesNotExist:
            raise Http404()

        _assert_has_perm(request, dataset2, permission_required)

        if dataset.name == dataset2.name:
            return HttpResponse(
                'Cannot compare two datasets with the same '
                'name. Please rename one of the datasets.',
                status=400)

    def _setup_dr_par(name, needs_toggle=False):
        if needs_toggle and \
                request.GET.get(name + 'Toggle', 'off') != 'on':
            return None
        par_name = request.GET.get(name, None)
        if par_name is not None and '_custom' in par_name:
            rep_value = request.GET.get(name + 'Custom', None)
            if int(rep_value) < 0:
                raise ValueError()
            par_name = par_name.replace('_custom', rep_value)
        return par_name

    try:
        dr_par = _setup_dr_par('drPar')
    except ValueError:
        return HttpResponse('Parameter custom value '
                            'needs to be a positive integer', status=400)

    try:
        dr_par_two = _setup_dr_par('drParTwo', needs_toggle=True)
    except ValueError:
        return HttpResponse('Parameter two custom value '
                            'needs to be a positive integer', status=400)

    try:
        dr_par_order = _setup_dr_par('drParOrder', needs_toggle=True)
    except ValueError:
        return HttpResponse('Parameter order custom value '
                            'needs to be a positive integer', status=400)

    # Work out any non-standard parameters we need to calculate
    # e.g. non-standard IC concentrations
    ic_concentrations = set()
    ec_concentrations = set()
    e_values = set()
    e_rel_values = set()
    regexes = {IC_REGEX: ic_concentrations,
               EC_REGEX: ec_concentrations,
               E_REGEX: e_values,
               E_REL_REGEX: e_rel_values
               }
    need_aa = False
    need_hill = False
    need_emax = False
    for param in (dr_par, dr_par_two, dr_par_order):
        if param is None:
            continue
        if param == 'aa':
            need_aa = True
            continue
        if param == 'hill':
            need_hill = True
            continue
        if param.startswith('emax'):
            need_emax = True
            continue
        for regex, value_list in regexes.items():
            match = regex.match(param)
            if not match:
                continue
            try:
                value = int(match.groups(0)[0])
                if value < 0 or value > 100:
                    raise ValueError()
                value_list.add(value)
            except ValueError:
                return HttpResponse('Invalid custom value - must be '
                                    'an integer between 1 and 100',
                                    status=400)

    dataset_ids = dataset_id if dataset2_id is None else [dataset_id,
                                                          dataset2_id]

    # Fit Hill curves and compute parameters
    try:
        base_params = df_curve_fits(dataset_ids, response_metric,
                                    drug_id, cell_line_id)
    except NoDataException:
        return HttpResponse(
            'No data found for this request. This drug/cell '
            'line/assay combination may not exist.', status=400)

    if plot_type == 'drc' and len(drug_id) == 1 and len(
            cell_line_id) == 1:
        try:
            if response_metric == 'dip':
                ctrl_resp_data, expt_resp_data = df_dip_rates(
                    dataset_id=dataset_ids,
                    drug_id=drug_id,
                    cell_line_id=cell_line_id,
                    use_dataset_names=True
                )
            else:
                datasets = dataset if not dataset2_id else [dataset,
                                                            dataset2]
                expt_resp_data, ctrl_resp_data = _get_viability_scores(
                    datasets,
                    drug_id,
                    cell_line_id,
                    viability_time=base_params._viability_time
                )
        except NoDataException:
            return HttpResponse(
                'No data found for this request. This '
                'drug/cell line/assay combination may not exist.', status=400)
        fit_params = fit_params_from_base(
            base_params,
            ctrl_resp_data=ctrl_resp_data,
            expt_resp_data=expt_resp_data,
            custom_ic_concentrations={50},
            custom_ec_concentrations={50},
            include_emax=True,
            include_response_values=True
        )
    else:
        with warnings.catch_warnings(record=True) as w:
            fit_params = fit_params_from_base(
                base_params,
                include_response_values=False,
                custom_ic_concentrations=ic_concentrations,
                custom_ec_concentrations=ec_concentrations,
                custom_e_values=e_values,
                include_aa=need_aa,
                include_hill=need_hill,
                include_emax=need_emax
            )
            # Currently only care about warnings if plotting AA
            if plot_type == 'drpar' and (dr_par == 'aa' or
                                         dr_par_two == 'aa'):
                w = [i for i in w if issubclass(i.category, AAFitWarning)]
                if w:
                    return HttpResponse(w[0].message, status=400)

    if plot_type == 'drpar':
        if dr_par is None:
            return HttpResponse('Dose response parameter is a required field',
                                status=400)
        try:
            plot_fig = plot_drc_params(
                fit_params,
                fit_param=dr_par,
                fit_param_compare=dr_par_two,
                fit_param_sort=dr_par_order,
                aggregate_cell_lines=aggregate_cell_lines,
                aggregate_drugs=aggregate_drugs,
                multi_dataset=dataset2_id is not None
            )
        except CannotPlotError as e:
            return HttpResponse(e, status=400)
    else:
        dip_absolute = request.GET.get('drcType', 'rel') == 'abs'
        plot_fig = plot_drc(
            fit_params,
            is_absolute=dip_absolute
        )

    return plot_fig


def _get_viability_scores(datasets, drug_id, cell_line_id, viability_time):
    try:
        df_data = df_doses_assays_controls(
            dataset=datasets,
            drug_id=drug_id,
            cell_line_id=cell_line_id,
            assay=None,
            use_dataset_names=True
        )
    except NoDataException:
        return HttpResponse(
            'No viability data found for this request. '
            'This drug/cell line/time point combination '
            'may not exist.', status=400)
    try:
        expt_resp_data, ctrl_resp_data = viability(
            df_data, time_hrs=viability_time,
            include_controls=True
        )
    except NotImplementedError as e:
        return HttpResponse(e, status=400)
    if expt_resp_data['viability'].isnull().values.all():
        return HttpResponse('No viability for this time point. The '
                            'nearest time point to the time entered '
                            'is '
                            'used, but there must be control well '
                            'measurements from the same time.',
                            status=400)

    return expt_resp_data, ctrl_resp_data


@login_required_unless_public
def plots(request):
    # Check the dataset exists
    dataset_id = request.GET.get('dataset', None)
    dataset2_id = request.GET.get('dataset2', None)
    dataset = None
    dataset2 = None
    if dataset_id is not None:
        try:
            dataset_id = int(dataset_id)
            if dataset2_id is not None:
                dataset2_id = int(dataset2_id)
        except ValueError:
            raise Http404()

        datasets = HTSDataset.objects.in_bulk([dataset_id, dataset2_id])

        if not datasets:
            raise Http404()

        dataset = datasets[dataset_id]
        if dataset2_id in datasets:
            dataset2 = datasets[dataset2_id]

        _assert_has_perm(request, dataset, 'view_plots')

    return render(request, 'plots.html', {'default_dataset': dataset,
                                          'second_dataset': dataset2,
                                          'navbar_hide_dataset': True})
