import plotly.offline as opy
from django.conf import settings


def get_plot_html(figure):
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
