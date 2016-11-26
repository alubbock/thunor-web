import plotly.offline as opy
import plotly.graph_objs as go
import numpy as np
import scipy.stats
import scipy.optimize
import seaborn as sns


def plot_dose_response(df, title=None):
    # Dataframe with time point as index
    traces = []

    colours = sns.color_palette("husl",
                                len(df.index.get_level_values(
                                    level='time').unique()))

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
        traces.append(go.Scatter(x=x_var,
                                 y=y_var,
                                 mode='markers',
                                 line={'color': this_colour},
                                 legendgroup=str(time),
                                 error_y=error_y,
                                 marker={'size': 5},
                                 name=str(time))
                     )
        # Convert to negative log space for numerical reasons
        x_var_log = -np.log(x_var)
        popt, pcov = scipy.optimize.curve_fit(ll4, x_var_log, y_var,
                                              maxfev=100000)
        x_interp = np.linspace(np.min(x_var_log), np.max(x_var_log), 50)
        y_interp = ll4(x_interp, *popt)
        traces.append(go.Scatter(x=np.exp(-x_interp),
                                 y=y_interp,
                                 legendgroup=str(time),
                                 showlegend=False,
                                 mode='lines',
                                 hoverinfo='skip',
                                 line={'shape': 'spline',
                                       'color': this_colour},
                                 name=str(time) + ' (interpolated)')
                     )

    data = go.Data(traces)
    layout = go.Layout(title=title or 'Dose/response',
                       font={'family': '"Helvetica Neue",Helvetica,Arial,'
                                       'sans-serif'},
                       xaxis={'title': 'Dose (M)',
                              'type': 'log'},
                       yaxis={'title': 'Assay Value'},
                       )
    figure = go.Figure(data=data, layout=layout)
    div = opy.plot(figure, auto_open=False, output_type='div',
                   show_link=False, include_plotlyjs=False)

    return div


def ll3u(x, b, c, e):
    return ll4(x, b=b, c=c, d=1, e=e)


def ll4(x, b, c, d, e):
    """
    @yannabraham from Github Gist
    https://gist.github.com/yannabraham/5f210fed773785d8b638

    This function is basically a copy of the LL.4 function from the R drc package with
     - b: hill slope
     - c: min response
     - d: max response
     - e: EC50
     """
    return c+(d-c)/(1+np.exp(b*(np.log(x)-np.log(e))))


def dip_rate(times, cell_counts):
    log2_cell_counts = np.log2(cell_counts)
    t_secs = [t.total_seconds() for t in times.index.get_level_values(0)]
    slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(
        t_secs, log2_cell_counts)
    return slope


def curve_fit(x, y, fit_fn=ll4, num_points=100):
    popt, pcov = scipy.optimize.curve_fit(fit_fn, x, y, maxfev=1000000)
