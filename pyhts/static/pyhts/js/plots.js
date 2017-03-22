var ajax = require("./modules/ajax");
var ui = require("./modules/ui");

var downloadSvg = function(gd) {
    return downloadImage(gd, "svg");
};

var downloadPng = function(gd) {
    return downloadImage(gd, "png");
};

var downloadImage = function(gd, fmt) {
    // Plotly.Lib.notifier('Taking snapshot - this may take a few seconds', 'long');
    //
    // if(Plotly.Lib.isIE()) {
    //     Plotly.Lib.notifier('IE only supports svg.  Changing format to svg.', 'long');
    //     fmt = 'svg';
    // }

    var $gd = $(gd);
    var filename = $gd.find(".gtitle").text();
    var width = $gd.width();
    var height = $gd.height();

    Plotly.downloadImage(gd, {'format': fmt, 'filename': filename,
                              'width': width, 'height': height})
      .then(function(filename) {
          // Plotly.Lib.notifier('Snapshot succeeded - ' + filename, 'long');
      })
      .catch(function() {
          // Plotly.Lib.notifier('Sorry there was a problem downloading your' +
          //     ' snapshot!', 'long');
      });
};

var plots = function() {
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

    $(".panel-close-btn").on("click", function () {
        $(this).closest(".panel-container")[$(this).data("effect")](400,
            function () {
                $(this).remove();
            });
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
        if (len == 0) {
            $select.closest(".bootstrap-select").
                    find("span").first().text("No options available");
        } else {
            if (selectedOption === undefined) {
                $select.selectpicker("val", optionList[0].id);
            }
            $select.selectpicker("refresh");
        }
    };

    var setButtonGroupOptions = function($btnGroup, options) {
        var optionKeys = Object.keys(options);
        var numOptions = optionKeys.length;
        var $currentOptions = $btnGroup.find("label");
        var optionsDelta = $currentOptions.length - numOptions;
        var $lastOption = $currentOptions.last();
        if (optionsDelta != 0) {
            if(optionsDelta < 0) {
                var $newOption = $lastOption.clone().removeClass("active");
                $newOption.find("input").attr("checked", false).change(selectPlotType);
                for (var optI=optionsDelta; optI<0; optI++) {
                    $btnGroup.append($newOption.clone(true));
                }
            } else {
                // $btnGroup.find("label").last().addClass("active")
                //         .find("input").attr("checked", true);
                // $btnGroup.find("input").last().click();
                $currentOptions.slice(numOptions).remove();
                // if (!($btnGroup.find("input:checked").length)) {
                //     $btnGroup.find("label").first().click();
                // }
                // $btnGroup.button();
            }
            $btnGroup.removeClass("btn-group-1 btn-group-2 btn-group-3" +
                " btn-group-4").addClass("btn-group-"+numOptions);
            $currentOptions = $btnGroup.find("label");
        }
        for(var i=0; i<numOptions; i++) {
            var $optionI = $currentOptions.eq(i);
            $optionI.find("span").text(options[optionKeys[i]]);
            $optionI.find("input").val(optionKeys[i]);
        }
    };

    var setSelectPicker = function($selectPicker, newState) {
        $selectPicker.prop("disabled", !newState).selectpicker("refresh");
        $selectPicker.closest(".form-group").toggle(newState);
    };

    var setRadio = function($radioDiv, newState) {
        var lbls = $radioDiv.find("label");
        if(newState) {
            lbls.removeClass("disabled");
        } else {
            lbls.addClass("disabled");
        }
        $radioDiv.closest(".form-group").toggle(newState);
    };

    var setPlotType = function($dataPanel, plotType) {
        var setErrorBars = true;
        if (plotType == "dr3d") {
            setErrorBars = false;
        }
        setRadio($dataPanel.find(".hts-error-bars"), setErrorBars);
    };

    var selectPlotType = function(e) {
        var $target = $(e.target);
        var $dataPanel = $target.closest(".hts-change-data");
        var plotType = $dataPanel.find(".hts-plot-type").find("input:checked").val();
        setPlotType($dataPanel, plotType);
    };

    var setPlotCategory = function($dataPanel, plotMetaType) {
        var $drug = $dataPanel.find("select.hts-change-drug");
        var $cellLine = $dataPanel.find("select.hts-change-cell-line");
        var setCellLine = true, setDrug = true;
        if (plotMetaType == "cellline") {
            setDrug = false;
        } else if (plotMetaType == "drug") {
            setCellLine = false;
        }
        setSelectPicker($drug, setDrug);
        setSelectPicker($cellLine, setCellLine);
    };

    var selectPlotCategory = function(e) {
      var $target = $(e.target);
      var $dataPanel = $target.closest(".hts-change-data");
      var $btnGroup = $dataPanel.find(".hts-plot-type");
      var plotMetaType = $target.val();
      if(plotMetaType == "combo") {
          setButtonGroupOptions($btnGroup, {
              "dr2d": "Dose/Response",
              "tc": "Time Course",
              "dr3d": "3D Dose/Time/Response"
          });
      } else {
          setButtonGroupOptions($btnGroup, {"dip": "DIP Rate"});
      }
      setPlotCategory($dataPanel, plotMetaType);
      $btnGroup.find("label").first().button("toggle");
    };

    // Change data panel
    $(".hts-change-data-btn").click(function(e) {
        var $currentTgt = $(e.currentTarget);
        var $parentTgt = $currentTgt.parent();
        var $dataPanel = $currentTgt.closest(".panel").find(".hts-change-data");
        if($parentTgt.hasClass("open")) {
            $parentTgt.removeClass("open");
            $dataPanel.hide();
        } else {
            $parentTgt.addClass("open");
            $dataPanel.show();
        }
    });

    // Add new panel
    $(".new-plot-btn").click(function (eNewPlot) {
        var $newPanel = $(".panel-container:last").clone(true);
        var dat = $(eNewPlot.currentTarget).data();
        $newPanel.find(".panel").data(dat);

        var $dataPanel = $(".hts-change-data").last().clone();

        $dataPanel.find("input[name=plotMetaType]").change(selectPlotCategory);
        $dataPanel.find("input[name=plotType]").change(selectPlotType);

        $.ajax({
            url: ajax.url("dataset_groupings", dat["datasetId"]),
            type: "GET",
            success: function (data) {
                pushOptionsToSelect(
                    $dataPanel.find("select.hts-change-cell-line"),
                    data.cellLines,
                    dat["cellLineId"]);
                pushOptionsToSelect(
                    $dataPanel.find("select.hts-change-drug"),
                    data.drugs,
                    dat["drugId"]);
                pushOptionsToSelect(
                    $dataPanel.find("select.hts-change-assay"),
                    data.assays,
                    dat["assayId"]);
                pushOptionsToSelect(
                    $dataPanel.find("select.hts-change-control"),
                    data.controls,
                    dat["controlId"]);
                $dataPanel.find("select.hts-error-bars").val
                (dat["errorBars"]).selectpicker("refresh");
                $dataPanel.find("select.hts-log-transform").val
                (dat["logTransform"]).selectpicker("refresh");
            },
            error: ajax.ajaxErrorCallback
        });

        var $plotPanel = $newPanel.find(".panel-body");
        var $changeDataBtn = $newPanel.find(".hts-change-data-btn");
        $dataPanel.find("select").selectpicker();
        $dataPanel.find("form").submit(function (e) {
            $plotPanel.loadingOverlay("show");
            var $this = $(e.currentTarget),
                $submit = $this.find("button[type=submit]");
            e.preventDefault();
            $.each($this.serializeArray(), function (i, ele) {
                $newPanel.data(ele.name, ele.value);
            });
            $submit.prop("disabled", true).text("Loading...");
            $.ajax({
                url: ajax.url("get_plot") + "?" + $this.serialize(),
                type: "GET",
                dataType: "html",
                success: function (data) {
                    $plotPanel.find(".plotly-graph-div,script").remove();
                    $plotPanel.append(data);
                    $changeDataBtn.click();
                },
                error: ajax.ajaxErrorCallback,
                complete: function () {
                    $submit.prop("disabled", false).text("Show Plot");
                    $plotPanel.loadingOverlay("hide");
                }
            });
        }).find("input[type=hidden]").each(function (i, obj) {
            $(obj).val(dat[$(obj).attr("name")]);
        });
        $dataPanel.prependTo($plotPanel);

        $newPanel.prependTo(".sortable-panels").fadeIn(400, function () {
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
