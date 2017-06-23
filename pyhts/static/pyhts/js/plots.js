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
                (optionList[i].id === selectedOption ? " selected" : "") +
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
        var plotType = $dataPanel.find("input[name=plotType]:checked").val();
        var showErrorBars = false,
            showAssay = true,
            showYaxisScale = true,
            showDipType = false,
            showDipParSort = false,
            showDipOverlay = $dataPanel.find("input[name=logTransform]:checked").val() === "log2";
        if (plotType === "dip") {
            showAssay = false;
            showYaxisScale = false;
            showDipType = true;
            showDipOverlay = false;
        }
        if (plotType === "dippar") {
            showAssay = false;
            showYaxisScale = false;
            showDipType = false;
            showDipParSort = true;
            showDipOverlay = false;
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
        setRadio($dataPanel.find(".hts-show-dip-fit"), showDipOverlay);
    };

    // Data panel events
    $("input[name=plotType]").change(function(e) {
        var $dataPanel = $(e.target).closest(".hts-change-data");
        setPlotType($dataPanel);
    });
    $("input[name=logTransform]").change(function(e) {
        var $dataPanel = $(e.target).closest(".hts-change-data");
        setRadio($dataPanel.find(".hts-show-dip-fit"),
            $dataPanel.find("input[name=logTransform]:checked").val() === "log2"
        );
    });
    $(".hts-change-data > form").submit(function (e) {
        var $plotPanel = $(this).closest(".plot-panel");
        var $plotPanelBody = $plotPanel.find(".panel-body");
        var $dataPanel = $plotPanelBody.find(".hts-change-data");
        var $changeDataBtn = $plotPanel.find(".hts-change-data-btn");
        $plotPanelBody.loadingOverlay("show");
        var $this = $(e.currentTarget),
            $submit = $this.find("button[type=submit]");
        e.preventDefault();
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

    function objectifyForm(formArray) {//serialize data function
      var returnArray = {};
      for (var i = 0; i < formArray.length; i++) {
          var name = formArray[i]["name"], value = formArray[i]["value"];
          if (returnArray.hasOwnProperty(name)) {
              var curVal = returnArray[name];
              if(!Array.isArray(curVal)) {
                  returnArray[name] = [curVal];
              }
              returnArray[name].push(value);
          } else {
              returnArray[name] = value;
          }
      }
      return returnArray;
    }

    var prepareDataPanel = function($plotPanel, defaultOptions) {
        var $dataPanel = $plotPanel.find(".hts-change-data");
        $dataPanel.find("select.hts-change-cell-line,select.hts-change-drug")
            .selectpicker(selectPickerOptionsSingle);
        $dataPanel.data("loaded", true);

        var datasetId;

        var $cellLineSelect = $dataPanel.find("select.hts-change-cell-line"),
            $drugSelect = $dataPanel.find("select.hts-change-drug");

        if(defaultOptions !== undefined) {
            // Set the dataset ID
            datasetId = defaultOptions["datasetId"];
            $dataPanel.find("input[name=datasetId]").val(datasetId);
        } else {
            datasetId = $dataPanel.find("input[name=datasetId]").val();
        }

        var populatePlotPanelOptions = function(data) {
            var clTitle = "Please select a cell line",
                drTitle = "Please select a drug";
            $cellLineSelect.selectpicker({title: clTitle})
                .attr("title", clTitle);
            pushOptionsToSelect(
                $cellLineSelect,
                data.cellLines);
            $drugSelect.selectpicker({title: drTitle})
                .attr("title", drTitle);
            pushOptionsToSelect(
                $drugSelect,
                data.drugs);
            pushOptionsToSelect(
                $dataPanel.find("select.hts-change-assay"),
                data.assays);

            if(!plotOptionsCache.hasOwnProperty(datasetId)) {
                plotOptionsCache[datasetId] = data;
            }

            if(defaultOptions !== undefined) {
                $dataPanel.find("input,select").each(function(i, obj) {
                    if(defaultOptions.hasOwnProperty(obj.name)) {
                        var $obj = $(obj);
                        var val = defaultOptions[obj.name];
                        if ($obj.prop("tagName").toLowerCase() === "select") {
                            $obj.selectpicker("val", val);
                        } else {
                            if (obj.type === "hidden") {
                                $obj.val(val);
                            } else if (obj.type === "radio" && $obj.val() === val) {
                                $obj.click();
                            }
                        }
                    }
                });
            }
        };

        if(plotOptionsCache.hasOwnProperty(datasetId)) {
            populatePlotPanelOptions(plotOptionsCache[datasetId]);
        } else {
            $.ajax({
                url: ajax.url("dataset_groupings", datasetId),
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
        var $newPanel = $(".panel-container").last().clone(true, true);

        // Plotly sets an HTML ID for the graph div, this will need changing
        // and the plotly javascript will need executing for the new div
        var $plotly = $panel.find(".plotly-graph-div");
        var $newPlotly = $plotly.clone();
        var oldPlotlyId = $newPlotly.attr("id");
        var newPlotlyId = uuid();
        $newPlotly.attr("id", newPlotlyId);
        var $newPlotlyScript = $plotly.parent().find("script").clone();
        var plotlyJS = $newPlotlyScript.html();
        if (plotlyJS !== undefined) {
            plotlyJS = plotlyJS.replace(oldPlotlyId, newPlotlyId);
            $newPlotlyScript.html(plotlyJS);
        }
        var $newPanelBody = $newPanel.find(".panel-body");
        $newPlotly.appendTo($newPanelBody);
        $newPlotlyScript.appendTo($newPanelBody);

        // Insert the panel, scroll to it and activate the plot javascript if
        // applicable
        $newPanel.insertAfter($panel).fadeIn(400);

        // The click events on the panel have to be fired after the panel
        // is added to the DOM or the bootstrap events don't fire properly
        var formData = objectifyForm($panel.find("form").serializeArray());
        prepareDataPanel($newPanel, formData);

        if($panel.find(".hts-change-data-btn").parent().hasClass("open")) {
            $newPanel.find(".hts-change-data-btn").click();
        }

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
        $plotPanel.find("input[name=datasetId]").val(
            $(eNewPlot.currentTarget).data("datasetId")
        );
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
