import plotly.offline as opy
import plotly.graph_objs as go
import pandas as pd
import numpy as np


def dose_response(df, title=None):
    # Dataframe with time point as index
    traces = []

    for tp, x in df.groupby(level=0):
        traces.append(go.Scatter(x=np.log10(x.index.get_level_values('dose')),
                                 y=list(x['value']),
                                 marker={'symbol': 104,
                                         'size': "10"},
                                 mode="lines",
                                 name=str(tp)))

    data = go.Data(traces)
    layout = go.Layout(title=title or 'Dose/response',
                       font={'family': '"Helvetica Neue",Helvetica,Arial,'
                                       'sans-serif'},
                       xaxis={'title': 'Dose'},
                       yaxis={'title': 'Assay Value'},
                       )
    figure = go.Figure(data=data, layout=layout)
    div = opy.plot(figure, auto_open=False, output_type='div',
                   show_link=False, include_plotlyjs=False)

    return div
