var plots = function() {
    var ajax = require('./modules/ajax');

    $(".sortable-panels").sortable({
        tolerance: 'pointer',
        revert: 'invalid',
        handle: '.panel-heading',
        placeholder: 'panel-placeholder col-lg-12',
        forceHelperSize: false,
        forcePlaceholderSize: true,
        zIndex: 2000
    });

    var setColumns = function (numColsMd, numColsLg) {
        var numBScolsLg = Math.round(12 / numColsLg),
            numBScolsMd = Math.round(12 / numColsMd);
        $(".panel-container").removeClass('col-lg-3 col-lg-4 col-lg-6 ' +
            'col-lg-12 col-md-6 col-md-12').addClass
        ('col-lg-' + numBScolsLg + ' col-md-' + numBScolsMd);
        resizeGraphs();
        $(".sortable-panels").sortable('option', 'placeholder',
            'panel-placeholder col-lg-' + numBScolsLg +
            ' col-md-' + numBScolsMd);
        $("#hts-current-num-cols-lg").text(numColsLg + ' column' +
            (numColsLg > 1 ? 's' : ''));
        $("#hts-current-num-cols-md").text(numColsMd + ' column' +
            (numColsMd > 1 ? 's' : ''));
    };

    var resizeGraphs = function () {
        $(".plotly-graph-div").each(function (i, obj) {
            Plotly.Plots.resize(obj);
        });
    };

    $(window).resize(function () {
        clearTimeout($.data(this, 'resizeTimer'));
        $.data(this, 'resizeTimer', setTimeout(function () {
            resizeGraphs();
        }, 200));
    });

    $('#hts-num-cols-lg').find('li').click(function (e) {
        e.preventDefault();
        var lgCols = $(this).data('cols');
        var mdCols = lgCols >= 2 ? 2 : 1;
        setColumns(mdCols, lgCols);
    });

    $('#hts-num-cols-md').find('li').click(function () {
        var mdCols = $(this).data('cols');
        setColumns(mdCols, mdCols);
    });

    $('.panel-close-btn').on('click', function () {
        $(this).closest('.panel-container')[$(this).data('effect')](400,
            function () {
                $(this).remove();
            });
    });

    var pushOptionsToSelect = function ($select, optionList, selectedOption) {
        for (var i = 0; i < optionList.length; i++) {
            $select.append(
                '<option value="' + optionList[i].id + '"' +
                (optionList[i].id == selectedOption ? ' selected' : '') +
                '>' + optionList[i].name + '</option>'
            );
        }
        $select.selectpicker('refresh');
    };

    // Add new panel
    $('.new-plot-btn').click(function (eNewPlot) {
        var $newPanel = $('.panel-container:last').clone(true);
        var dat = $(eNewPlot.currentTarget).data();
        $newPanel.find('.panel').data(dat);

        var $dataPanel = $('.hts-change-data:last').clone();

        $.ajax({
            url: '/ajax/dataset/' + dat['datasetId'] + '/groupings/',
            type: 'GET',
            success: function (data) {
                pushOptionsToSelect(
                    $dataPanel.find('select.hts-change-cell-line'),
                    data.cellLines,
                    dat['cellLineId']);
                pushOptionsToSelect(
                    $dataPanel.find('select.hts-change-drug'),
                    data.drugs,
                    dat['drugId']);
                pushOptionsToSelect(
                    $dataPanel.find('select.hts-change-assay'),
                    data.assays,
                    dat['assayId']);
                pushOptionsToSelect(
                    $dataPanel.find('select.hts-change-control'),
                    data.controls,
                    dat['controlId']);
                $dataPanel.find('select.hts-error-bars').val
                (dat['errorBars']).selectpicker('refresh');
                $dataPanel.find('select.hts-log-transform').val
                (dat['logTransform']).selectpicker('refresh');
            },
            error: ajax.ajaxErrorCallback
        });

        $dataPanel.find('select').selectpicker();
        $dataPanel.find('form').submit(function (e) {
            var $this = $(e.currentTarget),
                $submit = $this.find('button[type=submit]');
            e.preventDefault();
            $.each($this.serializeArray(), function (i, ele) {
                $newPanel.data(ele.name, ele.value);
            });
            $submit.prop('disabled', true).text('Loading...');
            $.ajax({
                url: '/ajax/plot/?' + $this.serialize(),
                type: 'GET',
                dataType: 'html',
                success: function (data) {
                    var $panelBody = $newPanel.find('.panel-body');
                    $panelBody.children().not('.hts-change-data').remove();
                    $panelBody.append(data);
                    $dataPanel.slideUp();
                },
                error: ajax.ajaxErrorCallback,
                complete: function () {
                    $submit.prop('disabled', false).text('Submit');
                }
            });
        }).find('input[type=hidden]').each(function (i, obj) {
            $(obj).val(dat[$(obj).attr('name')]);
        });
        $dataPanel.prependTo(
            $newPanel.find('.panel-body')
        );

        $('#welcome-instructional').hide();
        $newPanel.appendTo('.sortable-panels').fadeIn(400, function () {
            $dataPanel.slideDown();
        });
    });

    // Change data panel
    $('.hts-change-data-btn').click(function (e) {
        $(e.currentTarget).closest('.panel').find('.hts-change-data')
            .slideToggle();
    });
};
module.exports = {activate: plots};
