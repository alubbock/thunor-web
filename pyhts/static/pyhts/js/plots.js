var ajax = require("./modules/ajax");
var ui = require("./modules/ui");

var downloadSvg = function(gd) {
    return downloadImage(gd, "svg");
};

var downloadPng = function(gd) {
    return downloadImage(gd, "png");
};

var downloadImage = function(gd, fmt) {
    var $gd = $(gd);
    var filename = $gd.find(".gtitle").text();
    var width = $gd.width();
    var height = $gd.height();

    Plotly.downloadImage(gd, {"format": fmt, "filename": filename,
                              "width": width, "height": height});
};

var uuid = function() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g,
        function(c) {
            var r = Math.random()*16|0, v = c === "x" ? r : (r&0x3|0x8);
            return v.toString(16);
        }
    );
};

var selectPickerOptionsMultiple = {
  countSelectedText: function(n, N) {
    return n + " of " + N + " selected";
  },
  selectedTextFormat: "count > 4",
  maxOptions: false
};

var selectPickerOptionsSingle = {
  actionsBox: true,
  maxOptions: 1
};


var plots = function() {
    var plotOptionsCache = {};

    $(".sortable-panels").sortable({
        tolerance: "pointer",
        revert: "invalid",
        handle: ".panel-heading",
        placeholder: "panel-placeholder",
        forceHelperSize: false,
        forcePlaceholderSize: true,
        zIndex: 2000,
        activate: function( event, ui ) {
          $(ui.placeholder).height($(ui.helper).height());
        }
    });

    var setColumns = function (numColsMd, numColsLg) {
        var numBScolsLg = Math.round(12 / numColsLg),
            numBScolsMd = Math.round(12 / numColsMd);
        $(".panel-container").removeClass("col-lg-3 col-lg-4 col-lg-6 " +
            "col-lg-12 col-md-6 col-md-12").addClass
        ("col-lg-" + numBScolsLg + " col-md-" + numBScolsMd);
        resizeGraphs();
        $(".sortable-panels").sortable("option", "placeholder",
            "panel-placeholder col-lg-" + numBScolsLg +
            " col-md-" + numBScolsMd);
        $("#hts-current-num-cols-lg").text(numColsLg + " column" +
            (numColsLg > 1 ? "s" : ""));
        $("#hts-current-num-cols-md").text(numColsMd + " column" +
            (numColsMd > 1 ? "s" : ""));
    };

    var resizeGraphs = function () {
        $(".plotly-graph-div").each(function (i, obj) {
            Plotly.Plots.resize(obj);
        });
    };

    $(window).resize(function () {
        clearTimeout($.data(this, "resizeTimer"));
        $.data(this, "resizeTimer", setTimeout(function () {
            resizeGraphs();
        }, 200));
    });

    $("#hts-num-cols-lg").find("li").click(function (e) {
        e.preventDefault();
        var lgCols = $(this).data("cols");
        var mdCols = lgCols >= 2 ? 2 : 1;
        setColumns(mdCols, lgCols);
    });

    $("#hts-num-cols-md").find("li").click(function () {
        var mdCols = $(this).data("cols");
        setColumns(mdCols, mdCols);
    });

    var pushOptionsToSelect = function ($select, optionList, selectedOption) {
        var len = optionList.length;
        for (var i = 0; i < len; i++) {
            $select.append(
                "<option value=\"" + optionList[i].id + "\"" +
                (optionList[i].id == selectedOption ? " selected" : "") +
                ">" + optionList[i].name + "</option>"
            );
        }
        if (len === 0) {
            $select.closest(".bootstrap-select").
                    find("span").first().text("No options available");
        } else {
            if (selectedOption === undefined) {
                $select.selectpicker("val", optionList[0].id);
            }
            $select.selectpicker("refresh");
        }
    };

    var setSelectPicker = function($selectPicker, newState) {
        $selectPicker.prop("disabled", !newState).selectpicker("refresh");
        $selectPicker.closest(".form-group").toggle(newState);
    };

    var setRadio = function($radioDiv, newState) {
        var radio = $radioDiv.find("input[type=radio]");
        if(newState) {
            radio.prop("disabled", false);
        } else {
            radio.prop("disabled", true);
        }
        $radioDiv.closest(".form-group").toggle(newState);
    };

    var setPlotType = function($dataPanel) {
        var plotType = $dataPanel.find(".hts-plot-type").find("input:checked").val();
        var showErrorBars = false,
            showAssay = true,
            showYaxisScale = true,
            showDipType = false,
            showDipParSort = false;
        if (plotType === "dip") {
            showAssay = false;
            showYaxisScale = false;
            showDipType = true;
        }
        if (plotType === "dippar") {
            showAssay = false;
            showYaxisScale = false;
            showDipType = false;
            showDipParSort = true;
        }

        // Only show assay selection if the dataset contains more than one
        // assay
        var $changeAssay = $dataPanel.find("select.hts-change-assay");
        if (showAssay && $changeAssay.length <= 1) {
            showAssay = false;
        }

        // Select multiple cell lines/drugs or not
        var $changeCL = $dataPanel.find("select.hts-change-cell-line"),
            $changeDrug = $dataPanel.find("select.hts-change-drug"),
            $changeCLDrug = $changeCL.add($changeDrug),
            $actionBtns = $dataPanel.find(
                "div.hts-change-cell-line,div.hts-change-drug"
            ).find(".bs-actionsbox");
        if (plotType === "tc") {
            // Need to manually set value to avoid buggy behaviour
            var clVal = $changeCL.val()[0],
                drVal = $changeDrug.val()[0];

            $changeCL.selectpicker("val", clVal);
            $changeDrug.selectpicker("val", drVal);

            $changeCLDrug
                .selectpicker(selectPickerOptionsSingle)
                .selectpicker("refresh");
            $actionBtns.hide();
        } else {
            $changeCLDrug
                .selectpicker(selectPickerOptionsMultiple)
                .selectpicker("refresh")
                .selectpicker("render");
            $actionBtns.show();
        }
        setSelectPicker($dataPanel.find(".hts-change-assay"), showAssay);
        setRadio($dataPanel.find(".hts-log-transform"), showYaxisScale);
        setRadio($dataPanel.find(".hts-dip-type"), showDipType);
        setRadio($dataPanel.find(".hts-error-bars"), showErrorBars);
        setRadio($dataPanel.find(".hts-dippar-sort"), showDipParSort);
    };

    var selectPlotType = function(e) {
        var $dataPanel = $(e.target).closest(".hts-change-data");
        setPlotType($dataPanel);
    };

    // Data panel events
    $("input[name=plotType]").change(selectPlotType);
    $(".hts-change-data > form").submit(function (e) {
        var $plotPanel = $(this).closest(".plot-panel");
        var $plotPanelBody = $plotPanel.find(".panel-body");
        var $dataPanel = $plotPanelBody.find(".hts-change-data");
        var $changeDataBtn = $plotPanel.find(".hts-change-data-btn");
        $plotPanelBody.loadingOverlay("show");
        var $this = $(e.currentTarget),
            $submit = $this.find("button[type=submit]");
        e.preventDefault();
        $.each($this.serializeArray(), function (i, ele) {
            $plotPanel.data(ele.name, ele.value);
        });
        $submit.prop("disabled", true).text("Loading...");
        $.ajax({
            url: ajax.url("get_plot") + "?" + $this.serialize(),
            type: "GET",
            dataType: "html",
            success: function (data) {
                $plotPanelBody.find(".plotly-graph-div,script").remove();
                $plotPanelBody.append(data);
                $changeDataBtn.click();
                $dataPanel.data("loaded", "true");
            },
            error: ajax.ajaxErrorCallback,
            complete: function () {
                $submit.prop("disabled", false).text("Show Plot");
                $plotPanelBody.loadingOverlay("hide");
            }
        });
    });
    // End data panel events

    // Plot panel events
    $(".hts-change-data-btn").click(function(e) {
        var $currentTgt = $(e.currentTarget);
        var $parentTgt = $currentTgt.parent();
        var $dataPanel = $currentTgt.closest(".panel").find(".hts-change-data");
        if($parentTgt.hasClass("open")) {
            $parentTgt.removeClass("open");
            $dataPanel.hide();
        } else {
            if($dataPanel.data("loaded") === false) {
                prepareDataPanel($dataPanel.closest(".plot-panel"));
            }
            $parentTgt.addClass("open");
            $dataPanel.show();
        }
    });

    var prepareDataPanel = function($plotPanel) {
        var $dataPanel = $plotPanel.find(".hts-change-data");
        $dataPanel.find("select.hts-change-cell-line,select.hts-change-drug")
            .selectpicker(selectPickerOptionsSingle);
        $dataPanel.data("loaded", true);
        var dat = $plotPanel.find(".panel").data();
        $dataPanel.find("input[type=hidden]").each(function (i, obj) {
            $(obj).val(dat[$(obj).attr("name")]);
        });

        var $cellLineSelect = $dataPanel.find("select.hts-change-cell-line"),
            $drugSelect = $dataPanel.find("select.hts-change-drug");

        var populatePlotPanelOptions = function(data) {
            var clTitle = "Please select a cell line",
                drTitle = "Please select a drug";
            $cellLineSelect.selectpicker({title: clTitle})
                .attr("title", clTitle);
            pushOptionsToSelect(
                $cellLineSelect,
                data.cellLines,
                dat["cellLineId"]);
            $drugSelect.selectpicker({title: drTitle})
                .attr("title", drTitle);
            pushOptionsToSelect(
                $drugSelect,
                data.drugs,
                dat["drugId"]);
            pushOptionsToSelect(
                $dataPanel.find("select.hts-change-assay"),
                data.assays,
                dat["assayId"]);

            if(!plotOptionsCache.hasOwnProperty(dat["datasetId"])) {
                plotOptionsCache[dat["datasetId"]] = data;
            }
        };

        if(plotOptionsCache.hasOwnProperty(dat["datasetId"])) {
            populatePlotPanelOptions(plotOptionsCache[dat["datasetId"]]);
        } else {
            $.ajax({
                url: ajax.url("dataset_groupings", dat["datasetId"]),
                type: "GET",
                success: populatePlotPanelOptions,
                error: ajax.ajaxErrorCallback
            });
        }
    };

    $(".panel-close-btn").on("click", function () {
        $(this).closest(".panel-container")[$(this).data("effect")](400,
            function () {
                $(this).remove();
            });
    });

    $(".panel-copy-btn").on("click", function() {
        var $panel = $(this).closest(".panel-container");
        var $newPanel = $panel.clone(true, true);

        // The selectpickers need reinitialising after a clone
        $newPanel.find(".bootstrap-select").replaceWith(function() {
            return $("select", this).removeData("selectpicker");
        });
        setPlotType($newPanel.find(".hts-change-data"));
        var $newSelects = $newPanel.find("select");
        $panel.find("select").each(function(i, obj) {
            $newSelects.eq(i).selectpicker("val", $(obj).val());
        });

        // The drag/drop sets manual co-ordinates, so these need removing too,
        // except for the display element
        $newPanel.removeAttr("style").css("display", "block");

        // Plotly sets an HTML ID for the graph div, this will need changing
        // and the plotly javascript will need executing for the new div
        var $plotly = $newPanel.find(".plotly-graph-div");
        var oldPlotlyId = $plotly.attr("id");
        var newPlotlyId = uuid();
        $plotly.attr("id", newPlotlyId);
        var $plotlyScript = $plotly.parent().find("script");
        var plotlyJS = $plotlyScript.html();
        if (plotlyJS !== undefined) {
            plotlyJS = plotlyJS.replace(oldPlotlyId, newPlotlyId);
            $plotlyScript.html(plotlyJS);
        }

        $newPanel.insertAfter($panel).fadeIn(400);
        $("html, body").animate({
            scrollTop: $newPanel.offset().top
        }, 400);
        if(plotlyJS !== undefined) {
            setTimeout(new Function(plotlyJS), 1);
        }
    });

    // Add new panel
    $(".new-plot-btn").click(function (eNewPlot) {
        var $plotPanel = $(".panel-container").last().clone(true, true);
        var dat = $(eNewPlot.currentTarget).data();
        $plotPanel.find(".panel").data(dat);
        var $changeDataBtn = $plotPanel.find(".hts-change-data-btn");

        $plotPanel.prependTo(".sortable-panels").fadeIn(400, function () {
            $changeDataBtn.click();
        });
    }).first().click();
};
module.exports = {
    activate: plots,
    downloadSvg: downloadSvg,
    downloadPng: downloadPng,
    downloadImage: downloadImage
};
