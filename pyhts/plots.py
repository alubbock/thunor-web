import plotly.offline as opy
import plotly.graph_objs as go
import numpy as np
import scipy.stats
import scipy.optimize
import scipy.interpolate
import seaborn as sns
from .helpers import format_dose
from django.conf import settings


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
            'modeBarButtonsToRemove': ['sendDataToCloud']
        }
        plot_html, plot_div_id, width, height = opy.offline._plot_html(
            figure, config=config, validate=True, default_width='100%',
            default_height='100%', global_requirejs=False)
        return plot_html
    else:
        return opy.plot(figure, auto_open=False, output_type='div',
                   show_link=False, include_plotlyjs=False)

def plot_dose_response(df, log2=False, assay_name='Assay',
                       control_name=None, title=None, **kwargs):
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
    layout = go.Layout(title=title or 'Dose/response',
                       font={'family': '"Helvetica Neue",Helvetica,Arial,'
                                       'sans-serif'},
                       xaxis={'title': 'Dose (M)',
                              'type': 'log'},
                       yaxis={'title': yaxis_title},
                       )
    figure = go.Figure(data=data, layout=layout)

    return _get_plot_html(figure)


def plot_dose_response_3d(df, log2=False, assay_name='Assay',
                          control_name=None, title=None, **kwargs):

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
        title=title or '3D Dose/Response',
        font={'family': '"Helvetica Neue",Helvetica,Arial,'
                        'sans-serif'},
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
                    control_name=None, title=None, t0_extrapolated=False):
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
    layout = go.Layout(title=title or 'Time Course',
                       font={'family': '"Helvetica Neue",Helvetica,Arial,'
                                       'sans-serif'},
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


def dip_rate(times, cell_counts):
    log2_cell_counts = np.log2(cell_counts)
    t_secs = [t.total_seconds() for t in times.index.get_level_values(0)]
    slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(
        t_secs, log2_cell_counts)
    return slope
