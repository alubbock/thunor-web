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
              in df_timecourses.index.get_level_values(0)]
    assay_vals = np.log2(df_timecourses['value'])
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


def plot_dip(df_doses, df_vals, df_controls, is_absolute=True,
             title=None):
    # Dataframe with time point as index
    traces = []

    cell_lines = df_doses.index.levels[df_doses.index.names.index('cell_line')]

    show_replicates = len(cell_lines) == 1

    colours = sns.color_palette("husl", len(cell_lines))
    HILL_FN = ll4

    for cell_line, dose_and_well_id in df_doses.groupby(level='cell_line'):
        c = colours.pop()
        this_colour = 'rgb(%d, %d, %d)' % (c[0] * 255, c[1] * 255, c[2] * 255)

        control = df_controls.loc[cell_line]
        ctrl_dip_plates = []
        for plate, plate_dat in control.groupby(level='plate'):
            t_hours_ctrl = [x.total_seconds() / 3600 for x in
                            plate_dat.index.get_level_values(
                               plate_dat.index.names.index('timepoint'))]

            ctrl_slope, ctrl_intercept, ctrl_r, ctrl_p, ctrl_std_err = \
                scipy.stats.linregress(
                t_hours_ctrl, np.log2(plate_dat['value']))
            ctrl_dip_plates.append(ctrl_slope)

        ctrl_dip = np.mean(ctrl_dip_plates)

        dip_rates = []
        doses = []
        for dose, dose_dat in dose_and_well_id.groupby(level='dose'):
            for well in dose_dat['well_id']:
                doses.append(dose)
                dip_rates.append(calculate_dip(df_vals.loc[well]))

        doses = [min(doses) / 10] + doses
        dip_rates = [ctrl_dip] + dip_rates

        popt, pcov = scipy.optimize.curve_fit(HILL_FN,
                                              doses,
                                              dip_rates,
                                              maxfev=100000)

        log_dose_min = int(np.floor(np.log10(min(doses[1:]))))
        log_dose_max = int(np.ceil(np.log10(max(doses))))

        dose_x_range = np.concatenate(
            # [np.arange(2, 11) * 10 ** dose_mag
            [0.5 * np.arange(3, 21) * 10 ** dose_mag
             for dose_mag in range(log_dose_min, log_dose_max + 1)], axis=0)

        dose_x_range = np.append([10 ** log_dose_min], dose_x_range, axis=0)

        divisor = 1
        if not is_absolute:
            divisor = popt[2]
            popt[1] /= divisor
            popt[2] = 1

        dip_rate_fit = HILL_FN(dose_x_range, *popt)

        traces.append(go.Scatter(x=dose_x_range,
                                 y=dip_rate_fit,
                                 mode='lines',
                                 line={'shape': 'spline',
                                       'color': this_colour,
                                       'width': 3},
                                 legendgroup=cell_line,
                                 showlegend=not show_replicates,
                                 # hoverinfo='skip' if show_replicates else
                                 # 'all',
                                 name=cell_line)
                     )

        if show_replicates:
            y_trace = dip_rates[1:]
            if not is_absolute:
                y_trace /= divisor
                ctrl_dip_plates /= divisor
            traces.append(go.Scatter(x=doses[1:],
                                     y=y_trace,
                                     mode='markers',
                                     line={'shape': 'spline',
                                           'color': this_colour,
                                           'width': 3},
                                     legendgroup=cell_line,
                                     showlegend=False,
                                     name='Replicate',
                                     marker={'size': 5})
                          )
            traces.append(go.Scatter(x=[doses[0]] * len(ctrl_dip_plates),
                                     y=ctrl_dip_plates,
                                     mode='markers',
                                     line={'shape': 'spline',
                                           'color': 'black',
                                           'width': 3},
                                     hoverinfo='y+text',
                                     text='Control',
                                     legendgroup=cell_line,
                                     showlegend=False,
                                     marker={'size': 5})
                          )

    data = go.Data(traces)
    yaxis_title = 'DIP Rate'
    if not is_absolute:
        yaxis_title = 'Relative ' + yaxis_title
    layout = go.Layout(title=title,
                       hovermode='closest' if show_replicates else 'x',
                       xaxis={'title': 'Dose (M)',
                              'type': 'log'},
                       yaxis={'title': yaxis_title},
                       )
    figure = go.Figure(data=data, layout=layout)

    return _get_plot_html(figure)


def plot_dose_response(df, log2=False, assay_name='Assay',
                       control_name=None, title='Dose/response', **kwargs):
    # Dataframe with time point as index
    traces = []

    colours = sns.color_palette("husl",
                                len(df.index.get_level_values(
                                    level='time').unique()))
    HILL_FN = ll4

    error_y = {}
    for time, stats in df.groupby(level='time'):
        c = colours.pop()
        this_colour = 'rgb(%d, %d, %d)' % (c[0] * 255, c[1] * 255, c[2] * 255)
        if 'std' in stats:
            error_y = dict(
                type='data',
                array=list(stats['std']),
                color=this_colour
            )
        elif 'amax' in stats:
            error_y = dict(
                type='data',
                symmetric=False,
                array=list(stats['amax']),
                arrayminus=list(stats['amin']),
                color=this_colour
            )
        x_var = stats.index.get_level_values('dose').values
        y_var = list(stats['mean'])
        # Fit hill curve
        x_interp = None
        ic50_str = '<span style="color:darkred">N/A</span>'
        ec50_str = ic50_str
        if len(x_var) > 1:
            try:
                popt, pcov = scipy.optimize.curve_fit(HILL_FN,
                                                      x_var,
                                                      np.power(2, y_var) if log2
                                                            else y_var,
                                                      maxfev=100000)

                dose_range = (np.min(x_var), np.max(x_var))
                ec50 = popt[-1]
                ec50_str = format_dose(ec50, sig_digits=5)
                if ec50 < dose_range[0] or ec50 > dose_range[1]:
                    ec50_str = '<span style="color:darkorange">{' \
                               '}</span>'.format(
                        ec50_str)

                x_interp = np.logspace(np.log10(dose_range[0]),
                                       np.log10(dose_range[1]),
                                       50)
                y_interp = HILL_FN(x_interp, *popt)

                ic50 = find_ic50(x_interp, y_interp)
                ic50_str = format_dose(ic50, sig_digits=5)
                if ic50 is None:
                    ic50_str = '<em>{}</em>'.format(ic50_str)
            except RuntimeError:
                pass

        traces.append(go.Scatter(x=x_var,
                                 y=y_var,
                                 mode='markers',
                                 line={'color': this_colour},
                                 legendgroup=str(time),
                                 error_y=error_y,
                                 marker={'size': 5},
                                 name='{}<br>IC50: {}<br>EC50: {}'.format(
                                     time, ic50_str, ec50_str))
                     )

        if x_interp is not None:
            traces.append(go.Scatter(x=x_interp,
                                     y=np.log2(y_interp) if log2 else y_interp,
                                     legendgroup=str(time),
                                     showlegend=False,
                                     mode='lines',
                                     hoverinfo='skip',
                                     line={'shape': 'spline',
                                           'color': this_colour},
                                     name=str(time) + ' (interpolated)')
                         )

    data = go.Data(traces)
    if control_name:
        yaxis_title = '{} rel. to {}'.format(assay_name, control_name)
    else:
        yaxis_title = assay_name
    if log2:
        yaxis_title = 'log2({})'.format(yaxis_title)
    layout = go.Layout(title=title,
                       # font={'family': '"Helvetica Neue",Helvetica,Arial,'
                       #                 'sans-serif'},
                       xaxis={'title': 'Dose (M)',
                              'type': 'log'},
                       yaxis={'title': yaxis_title},
                       )
    figure = go.Figure(data=data, layout=layout)

    return _get_plot_html(figure)


def plot_dose_response_3d(df, log2=False, assay_name='Assay',
                          control_name=None, title='3D Dose/Response',
                          **kwargs):

    data_matrix = df['mean'].unstack()
    # Convert nanoseconds to hours
    time_hrs = [t / 3600e9 for t in data_matrix.index.values]
    doses_M = data_matrix.columns.values

    if control_name:
        zaxis_title = '{} rel. to {}'.format(assay_name, control_name)
    else:
        zaxis_title = assay_name
    if log2:
        zaxis_title = 'log2({})'.format(zaxis_title)

    scene = go.Scene(
        xaxis={'title': 'Dose (M)', 'type': 'log'},
        yaxis={'title': 'Time (hours)'},
        zaxis={'title': zaxis_title}
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


def plot_timecourse(df, log2=False, assay_name='Assay',
                    control_name=None, title='Time Course',
                    t0_extrapolated=False):
    # Dataframe with time point as index
    traces = []

    colours = sns.color_palette("husl",
                                len(df.index.get_level_values(
                                    level='dose').unique()))

    error_y = {}
    for dose, stats in df.groupby(level='dose'):
        c = colours.pop()
        this_colour = 'rgb(%d, %d, %d)' % (c[0] * 255, c[1] * 255, c[2] * 255)
        if 'std' in stats:
            error_y = dict(
                type='data',
                array=list(stats['std']),
                color=this_colour
            )
        elif 'amax' in stats:
            error_y = dict(
                type='data',
                symmetric=False,
                array=list(stats['amax']),
                arrayminus=list(stats['amin']),
                color=this_colour
            )
        # Convert from ns to hours
        x_var = [t / 3600e9 for t in stats.index.get_level_values(
            'time').values]
        y_var = list(stats['mean'])
        if t0_extrapolated:
            traces.append(go.Scatter(x=[0, x_var[0]],
                                     y=[0 if log2 else 1, y_var[0]],
                                     mode='lines+markers',
                                     line={'color': this_colour,
                                           'shape': 'spline',
                                           'dash': 'dash'},
                                     marker={'size': 5},
                                     legendgroup=str(dose),
                                     hoverinfo='skip',
                                     showlegend=False)
                          )
        traces.append(go.Scatter(x=x_var,
                                 y=y_var,
                                 mode='lines+markers',
                                 line={'color': this_colour,
                                       'shape': 'spline'},
                                 error_y=error_y,
                                 marker={'size': 5},
                                 legendgroup=str(dose),
                                 name=format_dose(dose))
                     )

    data = go.Data(traces)
    if control_name:
        yaxis_title = '{} rel. to {}'.format(assay_name, control_name)
    else:
        yaxis_title = assay_name
    if log2:
        yaxis_title = 'log2({})'.format(yaxis_title)
    layout = go.Layout(title=title,
                       # font={'family': '"Helvetica Neue",Helvetica,Arial,'
                       #                 'sans-serif'},
                       xaxis={'title': 'Time (hours)'},
                       yaxis={'title': yaxis_title},
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
    # return c+(d-c)/(1+np.exp(b*(np.log(x)-np.log(e))))
    return c+(d-c)/(1+10**(b*(np.log10(x)-np.log10(e))))


def find_ic50(x_interp, y_interp):
    st, sc, sk = scipy.interpolate.splrep(x_interp, y_interp)
    hill_interpolate = scipy.interpolate.sproot((st, sc - .5, sk))
    if len(hill_interpolate) > 0:
        return hill_interpolate[0]
    else:
        return None
