import plotly.offline as opy
import plotly.graph_objs as go
import numpy as np
import scipy.stats
import scipy.optimize
import matplotlib.pyplot as plt


def plot_dose_response(df, smoothing='spline', title=None):
    # Dataframe with time point as index
    traces = []

    error_y = {}
    for time, stats in df.groupby(level='time'):
        if 'std' in stats:
            error_y = dict(
                type='data',
                array=list(stats['std'])
            )
        elif 'amax' in stats:
            error_y = dict(
                type='data',
                symmetric=False,
                array=list(stats['amax']),
                arrayminus=list(stats['amin'])
            )
        traces.append(go.Scatter(x=stats.index.get_level_values('dose'),
                                 y=list(stats['mean']),
                                 mode='lines+markers',
                                 error_y=error_y,
                                 marker={'size': 5},
                                 name=str(time),
                                 line=dict(
                                    shape=smoothing
                                )
                      ))

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


def plot_dose_response_mpl(df, title=None):
    fig, ax = plt.subplots()

    plt.errorbar([0, 10, 20], [20, 30, 40],
                 yerr=[5, 5, 5],
                 fmt='o')

    return opy.plot_mpl(fig, auto_open=False, output_type='div',
                        show_link=False, include_plotlyjs=False)


def ll3u(x, b, c, e):
    ll4(x, b=b, c=c, d=1, e=e)


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
