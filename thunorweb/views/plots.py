from django.shortcuts import render, Http404
from django.http import HttpResponse
from django.utils.html import strip_tags, escape
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.cache import cache
from thunorweb.models import HTSDataset, CellLineTag, DrugTag, CellLine, Drug
from thunor.plots import plot_time_course, plot_drc, \
    plot_drug_combination_heatmap, plot_drc_params, \
    plot_ctrl_dip_by_plate, plot_ctrl_cell_counts_by_plate, plot_plate_map, CannotPlotError, \
    IC_REGEX, EC_REGEX, E_REGEX, E_REL_REGEX
from thunor.config import plotly_template as default_plotly_template
from thunor.curve_fit import AAFitWarning, fit_params_from_base
from thunor.viability import viability
from thunor.helpers import plotly_to_dataframe
from plotly.utils import PlotlyJSONEncoder
from plotly.offline.offline import get_plotlyjs
from thunorweb.pandas import df_doses_assays_controls, df_dip_rates, \
    df_ctrl_dip_rates, NoDataException, df_curve_fits, df_control_wells
import warnings
import collections
from thunorweb.views import login_required_unless_public, _assert_has_perm
from thunorweb.views.plate_mapper import ajax_load_plate
from thunorweb.views.datasets import _get_celllinetag_permfilter, \
    _get_drugtag_permfilter, dataset_groupings, license_accepted, \
    LICENSE_UNSIGNED
from thunorweb.views.tags import TAG_EVERYTHING_ELSE
import json


SECONDS_TO_HOURS = 3600
MAX_COLOR_GROUPS = 10
TAG_EVERYTHING_ELSE_LABEL = 'Everything else'
ALLOWED_TEMPLATES = ('none', 'plotly_white', 'plotly_dark', 'presentation')


@login_required_unless_public
def ajax_get_plot(request, file_type='json'):
    if file_type == 'csv':
        permission_required = 'download_data'
    else:
        permission_required = 'view_plots'

    try:
        plot_type = request.GET['plotType']
        template = request.GET.get('theme', default_plotly_template)
        if template not in ALLOWED_TEMPLATES:
            return HttpResponse('Please select an allowed template', status=400)

        dataset_id = int(request.GET['datasetId'])
        dataset2_id = request.GET.get('dataset2Id', None)
        if dataset2_id == "":
            dataset2_id = None
        if dataset2_id is not None:
            dataset2_id = int(dataset2_id)
        cell_line_id = request.GET.getlist('c')
        drug_id = request.GET.getlist('d')

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
    if not license_accepted(request, dataset):
        return HttpResponse(LICENSE_UNSIGNED.format(escape(dataset.name)),
                            status=400)

    if plot_type == 'tc':
        if len(drug_id) != 1 or len(cell_line_id) != 1:
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
            subtitle=dataset.name,
            template=template
        )
    elif plot_type in ('drc', 'drpar'):
        if all(isinstance(d, int) for d in drug_id):
            plot_fig = _dose_response_plot(request, dataset, dataset2_id,
                                           permission_required, drug_id,
                                           cell_line_id, plot_type, template)
        else:
            if dataset2_id is not None:
                return HttpResponse(
                    'Please select a single dataset at a time to view drug '
                    'combination heat plots', status=400)

            plot_fig = _drug_combination_heatmap(request, dataset,
                                                 drug_id, cell_line_id,
                                                 template)

        if isinstance(plot_fig, HttpResponse):
            return plot_fig
    elif plot_type == 'qc':
        qc_view = request.GET.get('qcView', None)
        if qc_view == 'ctrldipbox':
            ctrl_dip_data = df_ctrl_dip_rates(dataset_id)
            if ctrl_dip_data is None:
                return HttpResponse('No control wells with DIP rates '
                                    'available were detected in this '
                                    'dataset.', status=400)
            plot_fig = plot_ctrl_dip_by_plate(ctrl_dip_data, template=template)
        elif qc_view == 'ctrlcellbox':
            # Try to fetch from cache
            cache_key = f'dataset_{dataset_id}_plot_ctrlcellbox'
            cur_plotver = 1
            plot_cached = cache.get(cache_key)
            if plot_cached:
                plot_fig = plot_cached['plot_fig']
            if plot_cached is None or plot_cached['dataset_last_modified'] < dataset.modified_date or \
                    plot_cached['plot_version'] < cur_plotver:
                # Create plot
                groupings = dataset_groupings(dataset)
                if not groupings['singleTimepoint']:
                    return HttpResponse('This plot type is only available for '
                                        'single time-point datasets', status=400)
                try:
                    df_data = df_control_wells(
                        dataset_id=dataset,
                        assay=assay
                    )
                except NoDataException:
                    return HttpResponse('No data found for this request.',
                                        status=400)
                if (df_data['value'] == 100.0).all():
                    return HttpResponse('The raw data for this dataset is given as relative viability, so no control '
                                        'wells are available', status=400)

                plot_fig = plot_ctrl_cell_counts_by_plate(df_data, subtitle=dataset.name, template=template)

                # Push to cache
                cache.set(cache_key, {'dataset_last_modified': dataset.modified_date,
                                      'plot_version': cur_plotver,
                                      'plot_fig': plot_fig})

        elif qc_view == 'dipplatemap':
            plate_id = request.GET.get('plateId', None)
            try:
                plate_id = int(plate_id)
            except ValueError:
                return HttpResponse('Integer plateId required', status=400)
            pl_data = ajax_load_plate(request, plate_id,
                                      return_as_platedata=True,
                                      use_names=True)
            plot_fig = plot_plate_map(pl_data, color_by='dip_rates',
                                      template=template)
        else:
            return HttpResponse('Unimplemented QC view: {}'.format(
                escape(qc_view)), status=400)
    else:
        return HttpResponse('Unimplemented plot type: %s' %
                            escape(plot_type),
                            status=400)

    as_attachment = request.GET.get('download', '0') == '1'

    if file_type == 'json':
        j = json.dumps(plot_fig, cls=PlotlyJSONEncoder)
        response = HttpResponse(j, content_type='application/json')
    elif file_type == 'csv':
        response = HttpResponse(plotly_to_dataframe(plot_fig).to_csv(),
                                content_type='text/csv')
    elif file_type == 'html':
        template = 'plotly_plot{}.html'.format('_standalone' if
                                               as_attachment else '')
        context = {
            'data': json.dumps(plot_fig, cls=PlotlyJSONEncoder),
            'page_title': strip_tags(plot_fig['layout']['title']['text'])
        }
        if as_attachment:
            context['plotlyjs'] = get_plotlyjs()
        response = render(request, template, context)
    else:
        return HttpResponse('Unknown file type: %s' % escape(file_type), status=400)

    if as_attachment:
        try:
            title = plot_fig['layout']['title']['text']
        except KeyError:
            title = 'Plot'
        response['Content-Disposition'] = \
            'attachment; filename="{}.{}"'.format(strip_tags(title), file_type)

    return response


def _process_aggreate(request, tag_type, tag_ids, aggregation, dataset_ids):
    if tag_type == 'cell_lines':
        TagClass = CellLineTag
        perm_filter = _get_celllinetag_permfilter(request)
    else:
        TagClass = DrugTag
        perm_filter = _get_drugtag_permfilter(request)

    tag_base_query = TagClass.objects.filter(perm_filter).filter(
        id__in=tag_ids).distinct()
    if not aggregation and TAG_EVERYTHING_ELSE not in tag_ids:
        return tag_base_query.values_list('{}__id'.format(tag_type),
                                          flat=True), aggregation

    tag_objs = tag_base_query.values_list(
        'tag_category', 'tag_name', '{}__id'.format(tag_type),
        '{}__name'.format(tag_type))
    entity_ids = [tag[2] for tag in tag_objs]
    cats = set(tag[0] for tag in tag_objs)
    use_cats = len(cats) > 1
    # if not use_cats:
    #     (aggregate_cell_lines_group, ) = cats

    agg = collections.defaultdict(list)
    for tag in tag_objs:
        tag_name = '{} [{}]'.format(tag[1], tag[0]) if use_cats \
            else tag[1]
        agg[tag_name].append(tag[3])

    aggregation = {}

    if TAG_EVERYTHING_ELSE in tag_ids:
        groupings = dataset_groupings(dataset_ids)
        ent_dict = {e['id']: e['name'] for e in groupings[
            'cellLines' if tag_type == 'cell_lines' else 'drugs']}
        all_ent_ids = set(ent_dict.keys())
        everything_else_ids = all_ent_ids.difference(entity_ids)
        everything_else_names = [name for eid, name in ent_dict.items() if
                                 eid in everything_else_ids]
        aggregation[TAG_EVERYTHING_ELSE_LABEL] = everything_else_names
        entity_ids = all_ent_ids

    for tag_name, vals in agg.items():
        aggregation[tag_name] = set(vals)

    return entity_ids, aggregation


def _make_tags_unique(tags):
    if len(tags) <= 1:
        return tags

    duplicates = collections.defaultdict(int)
    for tag_name, targets in tags.items():
        for target in targets:
            duplicates[target] += 1

    duplicates = {d: v for d, v in duplicates.items() if v > 1}
    if not duplicates:
        return tags

    new_tags = {}
    for tag_name in tags:
        new_tags[tag_name] = set(tags[tag_name]).difference(duplicates)

    label = 'Multiple'
    if len(tags) == 2 or (TAG_EVERYTHING_ELSE_LABEL in tags and
                          len(tags) == 3):
        label = 'Both'

    new_tags['{} tags'.format(label)] = duplicates.keys()

    return new_tags


def _drug_combination_heatmap(request, dataset, drug_id, cell_line_id,
                              template):
    if not all(isinstance(d, collections.Sequence) for d in drug_id):
        return HttpResponse(
            'Please select either one or more individual drugs, or a '
            'single drug combination', status=400)

    if len(drug_id) != 1:
        return HttpResponse('Please select only one drug combination '
                            'at a time', status=400)

    if len(cell_line_id) != 1:
        return HttpResponse('Please select a single cell line for drug '
                            'combination plots', status=400)

    color_by = request.GET.get('colorBy', 'off')
    if color_by != 'off':
        return HttpResponse('Color overlay must be set to default for drug '
                            'combination heat plots', status=400)

    response_metric = request.GET.get('drMetric', 'dip')
    if response_metric != 'dip':
        return HttpResponse('Viability drug combination plots are not '
                            'supported', status=400)

    dip_absolute = request.GET.get('drcType', 'rel') == 'abs'
    if dip_absolute:
        return HttpResponse('Must use relative DIP rate for drug combination '
                            'heat plots', status=400)

    try:
        ctrl_resp_data, expt_resp_data = df_dip_rates(
            dataset_id=dataset.id,
            drug_id=drug_id,
            cell_line_id=cell_line_id,
            use_dataset_names=True
        )
    except NoDataException:
        return HttpResponse(
            'No data found for this request. This '
            'drug/cell line/assay combination may not exist.', status=400)

    return plot_drug_combination_heatmap(
        ctrl_resp_data, expt_resp_data, template=template
    )


def _dose_response_plot(request, dataset, dataset2_id,
                        permission_required, drug_id, cell_line_id,
                        plot_type, template=default_plotly_template):
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

    datasets = dataset if not dataset2_id else [dataset,
                                                dataset2]

    color_by = request.GET.get('colorBy', 'off')
    if color_by == 'off':
        color_by = None

    drug_tag_ids = [int(dt) for dt in request.GET.getlist('dT')]
    color_groups = None
    aggregate_drugs = request.GET.get('aggregateDrugs', False) == "true"
    if not drug_id and drug_tag_ids:
        drug_id, drug_groups = _process_aggreate(
            request, 'drugs', drug_tag_ids,
            aggregate_drugs or color_by == 'dr',
            datasets
        )
        if aggregate_drugs:
            aggregate_drugs = drug_groups
        if color_by == 'dr':
            color_groups = drug_groups

    cell_line_tag_ids = [int(ct) for ct in request.GET.getlist('cT')]
    aggregate_cell_lines = request.GET.get('aggregateCellLines', False) \
                           == "true"
    if not cell_line_id and cell_line_tag_ids:
        cell_line_id, cell_line_groups = _process_aggreate(
            request, 'cell_lines', cell_line_tag_ids,
            aggregate_cell_lines or color_by == 'cl',
            datasets
        )
        if aggregate_cell_lines:
            aggregate_cell_lines = cell_line_groups
        if color_by == 'cl':
            color_groups = cell_line_groups

    if color_groups:
        color_groups = _make_tags_unique(color_groups)
    elif color_by == 'cl':
        # The tags will just be the cell lines themselves
        color_groups = {cl.name: [cl.name] for cl in CellLine.objects.filter(
            id__in=cell_line_id).order_by('name')}
    elif color_by == 'dr':
        # Ditto for drugs
        color_groups = {dr.name: [dr.name] for dr in Drug.objects.filter(
            id__in=drug_id).order_by('name')}

    if color_groups and len(color_groups) > MAX_COLOR_GROUPS:
        return HttpResponse(
            'Cannot plot using more than {} unique colors. Please remove '
            'some entries or turn off coloring to proceed.'.format(
                MAX_COLOR_GROUPS),
            status=400
        )

    if not cell_line_id:
        return HttpResponse('Please enter at least one cell line',
                            status=400)
    if not drug_id:
        return HttpResponse('Please enter at least one drug',
                            status=400)

    response_metric = request.GET.get('drMetric', 'dip')
    if response_metric not in ('dip', 'viability', 'compare'):
        return HttpResponse('Unknown metric. Supported values: dip, '
                            'viability, compare.', status=400)

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

    # 'compare' plots are only available for one dataset and metric
    if response_metric == 'compare':
        if dataset2_id is not None:
            return HttpResponse('"compare" mode not compatible with two '
                                'datasets', status=400)
        if dr_par_two is not None:
            return HttpResponse('Parameter two not available with "compare" '
                                'mode', status=400)
        if dr_par_order is not None:
            return HttpResponse('Parameter order not available with "compare" '
                                'mode', status=400)
        if plot_type == 'drc':
            return HttpResponse('Dose response curves not available with '
                                '"compare" mode', status=400)

        if dr_par.endswith('_rel'):
            return HttpResponse('Relative metrics are not available with '
                                '"compare" mode', status=400)

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
    need_einf = False
    for param_idx, param in enumerate((dr_par, dr_par_two, dr_par_order)):
        if param is None:
            continue
        if param == 'label' and param_idx == 2:
            continue
        if param == 'aa_obs':
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
        if param == 'einf':
            need_einf = True
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
                break
            except ValueError:
                return HttpResponse('Invalid custom value - must be '
                                    'an integer between 1 and 100',
                                    status=400)
        else:
            return HttpResponse('Unknown parameter: {}'.format(param),
                                status=400)

    dataset_ids = dataset.id if dataset2_id is None else [dataset.id,
                                                          dataset2_id]

    # Fit Hill curves and compute parameters
    if response_metric == 'compare':
        all_metrics = ('dip', 'viability')
    else:
        all_metrics = (response_metric, )

    try:
        base_params = [df_curve_fits(
            dataset_ids, metric, drug_id, cell_line_id)
            for metric in all_metrics]
    except NoDataException:
        return HttpResponse(
            'No data found for this request. This drug/cell '
            'line/assay combination may not exist.', status=400)

    include_response_values = False

    ctrl_resp_data = None
    expt_resp_data = None
    if plot_type == 'drc':
        single_drug = len(
            base_params[0].index.get_level_values('drug').unique()) == 1
        single_cl = len(
            base_params[0].index.get_level_values('cell_line').unique()) \
                    == 1
        if single_cl and single_drug:
            try:
                if response_metric == 'dip':
                    ctrl_resp_data, expt_resp_data = df_dip_rates(
                        dataset_id=dataset_ids,
                        drug_id=drug_id,
                        cell_line_id=cell_line_id,
                        use_dataset_names=True
                    )
                else:
                    expt_resp_data, ctrl_resp_data = _get_viability_scores(
                        datasets,
                        drug_id,
                        cell_line_id,
                        viability_time=base_params[0]._viability_time.total_seconds() / SECONDS_TO_HOURS
                    )
            except NoDataException:
                return HttpResponse(
                    'No data found for this request. This drug/'
                    'cell line/assay combination may not exist.', status=400)
            include_response_values = True
            need_emax = True
            ic_concentrations = {50}
            ec_concentrations = {50}

    with warnings.catch_warnings(record=True) as w:
        fit_params = [fit_params_from_base(
            base_param_set,
            ctrl_resp_data=ctrl_resp_data,
            expt_resp_data=expt_resp_data,
            include_response_values=include_response_values,
            custom_ic_concentrations=ic_concentrations,
            custom_ec_concentrations=ec_concentrations,
            custom_e_values=e_values,
            include_aa=need_aa,
            include_hill=need_hill,
            include_emax=need_emax,
            include_einf=need_einf
        ) for base_param_set in base_params]
        # Currently only care about warnings if plotting AA
        if plot_type == 'drpar' and (dr_par == 'aa' or
                                     dr_par_two == 'aa'):
            w = [i for i in w if issubclass(i.category, AAFitWarning)]
            if w:
                return HttpResponse(w[0].message, status=400)

    if response_metric == 'compare':
        # Create new dataframe
        import pandas as pd
        fit_params = pd.concat(
            [fit_params[0]['label'],
             fit_params[0][dr_par], fit_params[1][dr_par]],
            join='inner',
            axis=1
        )
        fit_params.columns = ['label',
                              'dip__{}'.format(dr_par),
                              'viability__{}'.format(dr_par)]
        fit_params._viability_time = base_params[1]._viability_time
        fit_params._drmetric = 'compare'
        dr_par, dr_par_two = fit_params.columns[1:]
    else:
        fit_params = fit_params[0]

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
                color_by=color_by,
                color_groups=color_groups,
                multi_dataset=dataset2_id is not None,
                template=template
            )
        except CannotPlotError as e:
            return HttpResponse(str(e), status=400)
    else:
        dip_absolute = request.GET.get('drcType', 'rel') == 'abs'
        plot_fig = plot_drc(
            fit_params,
            is_absolute=dip_absolute,
            color_by=color_by,
            color_groups=color_groups,
            template=template
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
        return HttpResponse(str(e), status=400)
    if expt_resp_data['viability'].isnull().values.all():
        return HttpResponse('No viability for this time point. The '
                            'nearest time point to the time entered '
                            'is '
                            'used, but there must be control well '
                            'measurements from the same time.',
                            status=400)

    return expt_resp_data, ctrl_resp_data


@login_required_unless_public
@ensure_csrf_cookie
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

        try:
            dataset = datasets[dataset_id]
            if dataset2_id in datasets:
                dataset2 = datasets[dataset2_id]
        except KeyError:
            raise Http404()

        _assert_has_perm(request, dataset, 'view_plots')

    return render(request, 'plots.html', {'default_dataset': dataset,
                                          'second_dataset': dataset2,
                                          'navbar_hide_dataset': True})
