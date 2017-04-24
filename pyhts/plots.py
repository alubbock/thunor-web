import plotly.offline as opy
import plotly.graph_objs as go
import numpy as np
import scipy.stats
import scipy.optimize
import scipy.interpolate
import seaborn as sns
from .helpers import format_dose
from django.conf import settings


SECONDS_IN_HOUR = 3600


def _get_plot_html(figure):
    """
    Gets plots HTML from plotly

    Can use the protected plotly API, which has more options but may be
    changed from version to version

    Parameters
    ----------
    figure

    Returns
    -------

    """
    if settings.USE_PLOTLY_PROTECTED_API:
        config = {
            'showLink': False,
            'displaylogo': False,
            'modeBarButtonsToRemove': ['sendDataToCloud', 'toImage'],
            'modeBarButtonsToAdd': [{
                'name': 'Save plot as SVG image',
                'icon': '__thunor_svg_icon__',
                'click': '__thunor_svg_fn__'
            },
            {
                'name': 'Save plot as PNG image',
                'icon': '__thunor_png_icon__',
                'click': '__thunor_png_fn__'
            }
            ]
        }
        plot_html, plot_div_id, width, height = opy.offline._plot_html(
            figure, config=config, validate=True, default_width='100%',
            default_height='100%', global_requirejs=False)
        plot_html = plot_html.replace('"__thunor_svg_icon__"',
                                      'Plotly.Icons[\'camera-retro\']')
        plot_html = plot_html.replace('"__thunor_png_icon__"',
                                      'Plotly.Icons[\'camera\']')
        plot_html = plot_html.replace('"__thunor_svg_fn__"',
                                      'pyHTS.views.plots.downloadSvg')
        plot_html = plot_html.replace('"__thunor_png_fn__"',
                                      'pyHTS.views.plots.downloadPng')
        return plot_html
    else:
        return opy.plot(figure, auto_open=False, output_type='div',
                        show_link=False, include_plotlyjs=False)


def adjusted_r_squared(r, n, p):
    """
    Calculate adjusted r-squared value from r value

    Parameters
    ----------
    r: float
        r value (between 0 and 1)
    n: int
        number of sample data points
    p: int
        number of free parameters used in fit

    Returns
    -------
    float
        Adjusted r-squared value
    """
    denom = n - p - 1
    if denom < 1:
        return np.nan
    return 1 - (1 - r ** 2) * ((n - 1) / denom)


def rmsd(predictions, targets):
    return np.linalg.norm(predictions - targets) / np.sqrt(len(predictions))


def tyson1(adj_r_sq, rmse, n):
    return adj_r_sq * ((1 - rmse) ** 2) * ((n - 3) ** 0.25)


def calculate_dip(df_timecourses, selector_fn=tyson1):
    t_hours = [t.total_seconds() / SECONDS_IN_HOUR for t
              in df_timecourses.index.get_level_values(level='timepoint')]
    assay_vals = np.log2(df_timecourses)
    n_total = len(t_hours)

    dip = None
    dip_selector = -np.inf
    # dip_best_i = None
    opt_list = []
    # print(t_secs)
    # print(list(assay_vals))
    if n_total < 3:
        return None
    for i in range(n_total - 2):
        x = t_hours[i:]
        y = assay_vals[i:]
        slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(
            x, y)

        n = len(x)
        adj_r_sq = adjusted_r_squared(r_value, n, 1)
        predictions = np.multiply(x, slope) + intercept
        rmse = rmsd(predictions, assay_vals[i:])
        new_dip_selector = selector_fn(adj_r_sq, rmse, n)
        opt_list.append(new_dip_selector)
        if new_dip_selector > dip_selector:
            dip_selector = new_dip_selector
            dip = slope
            # dip_best_i = i

    # print(opt_list)
    # print(dip_best_i)
    # print(dip)

    return dip


def per_well_control_dip(control):
    ctrl_dip_wells = []
    for well, well_dat in control.groupby(level='well_id'):
        t_hours_ctrl = [x.total_seconds() / 3600 for x in
                        well_dat.index.get_level_values(
                            well_dat.index.names.index('timepoint'))]

        ctrl_slope, ctrl_intercept, ctrl_r, ctrl_p, ctrl_std_err = \
            scipy.stats.linregress(
                t_hours_ctrl, np.log2(well_dat['value']))
        ctrl_dip_wells.append(ctrl_slope)

    return ctrl_dip_wells


def plot_dip(df_doses, df_vals, df_controls, is_absolute=True,
             title=None, display_fit_params=False, fit_params_sort='ic50',
             **kwargs):
    # Dataframe with time point as index
    traces = []

    cell_lines = df_doses.index.get_level_values('cell_line').unique()
    drugs = df_doses.index.get_level_values('drug').unique()

    if len(cell_lines) > 1 and len(drugs) > 1:
        raise NotImplementedError()

    show_replicates = len(cell_lines) == 1 and len(drugs) == 1

    if len(drugs) > 1:
        group_by = 'drug'
        num_groups = len(drugs)
        try:
            control = df_controls.loc[cell_lines[0]]
            ctrl_dip_wells = per_well_control_dip(control)
        except KeyError:
            ctrl_dip_wells = []
    else:
        group_by = 'cell_line'
        num_groups = len(cell_lines)

    colours = sns.color_palette("husl", num_groups)

    HILL_FN = ll4

    annotations = []
    fit_params = []

    for group_name, dose_and_well_id in df_doses.groupby(level=group_by):
        c = colours.pop()
        this_colour = 'rgb(%d, %d, %d)' % (c[0] * 255, c[1] * 255, c[2] * 255)

        if group_by == 'cell_line':
            try:
                control = df_controls.loc[group_name]
                ctrl_dip_wells = per_well_control_dip(control)
            except (KeyError, AttributeError):
                ctrl_dip_wells = []

        dip_rates = []
        doses = []
        for dose, dose_dat in dose_and_well_id.groupby(level='dose'):
            for well in dose_dat['well_id']:
                doses.append(dose)
                dip_rates.append(calculate_dip(df_vals.loc[well, 'value']))

        doses = [np.min(doses) / 10] * len(ctrl_dip_wells) + doses
        dip_rates = ctrl_dip_wells + dip_rates

        popt = None
        emax = None
        y_val = np.mean(dip_rates)
        try:
            popt, pcov = scipy.optimize.curve_fit(HILL_FN,
                                                  doses,
                                                  dip_rates,
                                                  maxfev=100000)

            if popt[1] > popt[2]:
                # TODO: Maybe try another fit of some kind?
                popt = None
        except RuntimeError:
            pass

        if popt is not None:
            emax = popt[2]

        log_dose_min = int(np.floor(np.log10(min(doses[1:]))))
        log_dose_max = int(np.ceil(np.log10(max(doses))))

        dose_x_range = np.concatenate(
            # [np.arange(2, 11) * 10 ** dose_mag
            [0.5 * np.arange(3, 21) * 10 ** dose_mag
             for dose_mag in range(log_dose_min, log_dose_max + 1)], axis=0)

        dose_x_range = np.append([10 ** log_dose_min], dose_x_range, axis=0)

        divisor = 1
        popt_rel = None
        if not is_absolute or show_replicates or display_fit_params:
            if popt is None:
                divisor = y_val
                y_val = 1
            else:
                divisor = popt[2]
                if divisor <= 0:
                    # Cells not growing in control?
                    popt_rel = None
                else:
                    popt_rel = popt.copy()
                    popt_rel[1] /= divisor
                    popt_rel[2] = 1
        if not is_absolute:
            popt = popt_rel

        if popt is None:
            dip_rate_fit = [y_val] * len(dose_x_range)
        else:
            dip_rate_fit = HILL_FN(dose_x_range, *popt)

        traces.append(go.Scatter(x=dose_x_range,
                                 y=dip_rate_fit,
                                 mode='lines',
                                 line={'shape': 'spline',
                                       'color': this_colour,
                                       'dash': 5 if popt is None else 'solid',
                                       'width': 3},
                                 legendgroup=group_name,
                                 showlegend=not show_replicates,
                                 # hoverinfo='skip' if show_replicates else
                                 # 'all',
                                 name=group_name)
                     )

        if show_replicates:
            y_trace = dip_rates[1:]
            if not is_absolute:
                y_trace /= divisor
                ctrl_dip_wells /= divisor
            traces.append(go.Scatter(x=doses[1:],
                                     y=y_trace,
                                     mode='markers',
                                     line={'shape': 'spline',
                                           'color': this_colour,
                                           'width': 3},
                                     legendgroup=group_name,
                                     showlegend=False,
                                     name='Replicate',
                                     marker={'size': 5})
                          )
            traces.append(go.Scatter(x=[doses[0]] * len(ctrl_dip_wells),
                                     y=ctrl_dip_wells,
                                     mode='markers',
                                     line={'shape': 'spline',
                                           'color': 'black',
                                           'width': 3},
                                     hoverinfo='y+text',
                                     text='Control',
                                     legendgroup=group_name,
                                     showlegend=False,
                                     marker={'size': 5})
                          )

            if popt is not None:
                annotation_label = ''
                if popt[3] < np.max(dose_x_range):
                    annotation_label += 'EC50: {} '.format(format_dose(
                        popt[3], sig_digits=5
                    ))
                if popt_rel is not None:
                    ic50 = find_ic50(dose_x_range,
                                     HILL_FN(dose_x_range, *popt_rel))
                    if ic50:
                        annotation_label += 'IC50: {} '.format(format_dose(
                            ic50, sig_digits=5
                        ))
                if emax is not None:
                    annotation_label += 'Emax: {}'.format(format_dose(
                        emax, sig_digits=5
                    ))
                if annotation_label:
                    annotations.append({
                        'x': 0.5,
                        'y': 1.1,
                        'xref': 'paper',
                        'yref': 'paper',
                        'showarrow': False,
                        'text': annotation_label
                    })

        if display_fit_params:
            fit_params.append([group_name,  # Cell line or drug
                               emax,  # Emax
                               popt[3] if popt is not None else None,  # EC50
                               find_ic50(dose_x_range,
                                         HILL_FN(dose_x_range, *popt_rel)) if
                               popt_rel is not None else None          # IC50
                               ])

    if display_fit_params:
        sort_ind = {'emax': 1, 'ec50': 2}.get(fit_params_sort, 3)
        # Sort lists by chosen index, then transpose and unpack into separate
        # lists. The sort order key ensures that Nones appear at the start
        # of the sort.
        groups, emax_list, ec50_list, ic50_list = map(list, zip(
            *sorted(fit_params, key=lambda x: (x[sort_ind] is not None,
                                               x[sort_ind]))))

        data = [go.Bar(x=groups, y=emax_list, name='Emax'),
                go.Bar(x=groups, y=ec50_list, name='EC50'),
                go.Bar(x=groups, y=ic50_list, name='IC50')]
        layout = go.Layout(title=title,
                           barmode='group',
                           yaxis={'title': 'Dose (M)'})
    else:
        data = go.Data(traces)
        yaxis_title = 'Dose/Response'
        if not is_absolute:
            yaxis_title = 'Relative ' + yaxis_title
        layout = go.Layout(title=title,
                           hovermode='closest' if show_replicates else 'x',
                           xaxis={'title': 'Dose (M)',
                                  'type': 'log'},
                           yaxis={'title': yaxis_title},
                           annotations=annotations,
                           )

    figure = go.Figure(data=data, layout=layout)

    return _get_plot_html(figure)


def plot_dose_response_3d(df_doses, df_vals, df_controls, doublings=False,
                          assay_name='Assay', title='3D Dose/Response',
                          **kwargs):

    cell_lines = df_doses.index.get_level_values('cell_line').unique()
    drugs = df_doses.index.get_level_values('drug').unique()

    if len(cell_lines) != 1 or len(drugs) != 1:
        raise NotImplementedError()

    # First, combine the two dataframes to get (dose, timepoint) index with
    # assay value column
    df_doses.reset_index(level=['cell_line', 'drug'], drop=True,
                         inplace=True)
    df_doses.reset_index(level='dose', inplace=True)
    df_doses.set_index('well_id', inplace=True)
    df_vals.reset_index(level='timepoint', inplace=True)
    df_doses_vals = df_doses.join(df_vals)

    df_doses_vals.set_index(['timepoint', 'dose'], inplace=True)
    df_doses_vals.sort_index(inplace=True)

    # Next, calculate mean values per dose/timepoint
    df_means = df_doses_vals['value'].groupby(level=['timepoint',
                                                     'dose']).mean()

    # Convert to matrix form
    data_matrix = df_means.unstack()

    if doublings:
        data_matrix = np.log2(data_matrix)
        data_matrix -= data_matrix.iloc[0, :]

    # Convert nanoseconds to hours
    time_hrs = [t / np.timedelta64(1, 'h') for t in
                data_matrix.index.values]
    doses_M = data_matrix.columns.values

    scene = go.Scene(
        xaxis={'title': 'Dose (M)', 'type': 'log'},
        yaxis={'title': 'Time (hours)'},
        zaxis={'title': assay_name}
    )

    data = [
        go.Surface(
            x=doses_M,
            y=time_hrs,
            z=data_matrix.as_matrix(),
            colorscale='Viridis'
        )
    ]
    layout = go.Layout(
        title=title,
        # font={'family': '"Helvetica Neue",Helvetica,Arial,'
        #                 'sans-serif'},
        autosize=True,
        scene=scene,
        # width=500,
        # height=500,
        margin=dict(
            l=30,
            r=30,
            b=10,
            t=50
        )
    )
    figure = go.Figure(data=data, layout=layout)

    return _get_plot_html(figure)


def plot_time_course(df_doses, df_vals, df_controls,
                     doublings=False, assay_name='Assay', title=None,
                     **kwargs):
    traces = []

    colours = sns.color_palette("husl", len(df_doses.index.get_level_values(
        level='dose').unique()))

    # Controls
    if df_controls is not None:
        is_first_control = True
        for well_id, timecourse in df_controls.groupby(level='well_id'):
            timecourse = timecourse['value']
            if doublings:
                timecourse = np.log2(timecourse)
                timecourse -= timecourse[0]
            traces.append(go.Scatter(
                x=[t.total_seconds() / SECONDS_IN_HOUR for t in
                   timecourse.index.get_level_values('timepoint')],
                y=timecourse,
                mode='lines+markers',
                line={'color': 'black',
                      'shape': 'spline'},
                marker={'size': 5},
                name='Control',
                legendgroup='__Control',
                showlegend=is_first_control
            ))
            is_first_control = False

    # Experiment (non-control)
    for dose, wells in df_doses.groupby(level='dose'):
        c = colours.pop()
        this_colour = 'rgb(%d, %d, %d)' % (c[0] * 255, c[1] * 255, c[2] * 255)

        for well_idx, well_id in enumerate(wells['well_id']):
            timecourse = df_vals.loc[well_id, 'value']
            if doublings:
                timecourse = np.log2(timecourse)
                timecourse -= timecourse[0]
            traces.append(go.Scatter(
                x=[t.total_seconds() / SECONDS_IN_HOUR for t in
                   timecourse.index.get_level_values('timepoint')],
                y=timecourse,
                mode='lines+markers',
                line={'color': this_colour,
                      'shape': 'spline'},
                marker={'size': 5},
                name=format_dose(dose),
                legendgroup=str(dose),
                showlegend=well_idx == 0
            ))

    data = go.Data(traces)
    if doublings:
        assay_name = "Change in log2 {}".format(assay_name)
    layout = go.Layout(title=title,
                       xaxis={'title': 'Time (hours)',
                              'dtick': 12},
                       yaxis={'title': assay_name,
                              'type': None if doublings else 'log'},
                       )
    figure = go.Figure(data=data, layout=layout)

    return _get_plot_html(figure)


def ll3u(x, b, c, e):
    return ll4(x, b, c, 1, e)


def ll4(x, b, c, d, e):
    """
    @yannabraham from Github Gist
    https://gist.github.com/yannabraham/5f210fed773785d8b638

    This function is basically a copy of the LL.4 function from the R drc
    package with
     - b: hill slope
     - c: min response
     - d: max response
     - e: EC50
     """
    return c+(d-c)/(1+10**(b*(np.log10(x)-np.log10(e))))


def find_ic50(x_interp, y_interp):
    st, sc, sk = scipy.interpolate.splrep(x_interp, y_interp)
    hill_interpolate = scipy.interpolate.sproot((st, sc - .5, sk))
    if len(hill_interpolate) > 0:
        return hill_interpolate[0]
    else:
        return None


def extrapolate_time0(dat):
    means = dat.groupby(level=['time']).mean()
    return 2**scipy.stats.linregress(
        [t.item() for t in means.index.values],
        np.log2(list(means))).intercept
