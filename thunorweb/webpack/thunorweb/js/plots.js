var ajax = require("./modules/ajax");
var ui = require("./modules/ui");
var datasetTable = require("./modules/dataset_table");

var getQueryStrings = function() {
    var sPageURL = window.location.search.substring(1),
        sURLVariables = sPageURL.split('&'),
        sParameterName,
        i,
        plotStrings = [],
        colsLg = 1,
        colsMd = 1;

    for (i = 0; i < sURLVariables.length; i++) {
        sParameterName = sURLVariables[i].split('=');

        if (sParameterName[0] === "plotdata" && sParameterName[1] !== undefined && plotStrings.length < 20) {
            plotStrings.push(decodeURIComponent(sParameterName[1]));
        }
        if (sParameterName[0] === "colsLg" && sParameterName[1] !== undefined) {
            colsLg = parseInt(sParameterName[1]);
            if(isNaN(colsLg)) colsLg = 1;
        }
        if (sParameterName[0] === "colsMd" && sParameterName[1] !== undefined) {
            colsMd = parseInt(sParameterName[1]);
            if(isNaN(colsMd)) colsMd = 1;
        }
    }

    return {plotStrings: plotStrings, colsLg: colsLg, colsMd: colsMd};
};

var updateURL = function() {
    if (!window.history.replaceState) return;

    var $newPlotBtn = $(".new-plot-btn");
    var datasetId = $newPlotBtn.data("datasetId");
    var url = ajax.url("view_plots") + '?';

    if (datasetId !== undefined && datasetId !== null && datasetId !== "") {
        url += 'dataset=' + $newPlotBtn.data("datasetId");
    }

    if (isDataset2active()) {
        var dataset2Id = $newPlotBtn.data("dataset2Id");
        if (dataset2Id !== undefined && dataset2Id !== null &&
            dataset2Id !== "") {
            url += '&dataset2=' + dataset2Id;
        }
    }

    url += '&colsLg=' + $("#hts-current-num-cols-lg").data("cols");
    url += '&colsMd=' + $("#hts-current-num-cols-md").data("cols");

    $(".sortable-panels").find("form").each(function(i, obj) {
        url += '&plotdata=' + encodeURIComponent($(obj).serialize());
    });

    window.history.replaceState(
      null,
      document.title,
      url
    );
};

var isDataset2active = function() {
    return $("input[name=secondDataset]").is(":checked");
};

var downloadImage = function(gd, fmt) {
    var $gd = $(gd);
    var filename = $gd.find(".gtitle").text();
    var width = $gd.width();
    var height = $gd.height();
    var scale = (fmt === "png") ? 4 : 1;

    Plotly.downloadImage(gd, {"format": fmt, "filename": filename,
                              "width": width, "height": height,
                              "scale": scale
                             });
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

var selectPickerTagOptions = {
  title: "Please select a tag",
  countSelectedText: function(n, N) {
    return n + " of " + N + " tags selected";
  },
  selectedTextFormat: "count > 4",
  actionsBox: true
};

var plots = function() {
    var plotOptionsCache = {};

    var truncateDatasetName = function(datasetName) {
        return datasetName.length > 20 ?
            datasetName.substr(0, 17) + "..." : datasetName;
    };

    $.fn.selectpicker.Constructor.DEFAULTS.iconBase = "fa";
    $.fn.selectpicker.Constructor.DEFAULTS.tickIcon = "fa-check";

    $("#change-dataset-modal").on("show.bs.modal", function(e) {
        var $target = $(e.target);
        $target.data("datasetTarget", $(e.relatedTarget).data("dataset"));
        $target.data("datasetChanged", false);
        if(!$target.data("initialised")) {
            $target.data("initialised", true);
            datasetTable.initDatasetTable(function (data, type, full, meta) {
                return "<a class=\"select-dataset\" data-dataset-id=\""
                        + full.id + "\" data-dataset-name=\"" + full.name +
                        "\" href=\"\">" + full.name + "</a>";
            },
            function() {
                $("a[class=select-dataset]").click(function(e2) {
                    e2.preventDefault();
                    var $this = $(e2.target);
                    var dataset = $target.data("datasetTarget");
                    $(".new-plot-btn").data(dataset + "Id",
                        $this.data("datasetId")
                    );
                    $("#" + dataset + "-name").text(truncateDatasetName($this.data("datasetName")));
                    $target.data("datasetChanged", true);
                    updateURL();
                    $("#change-dataset-modal").modal("hide");
                });
            });
        }
    }).on("hide.bs.modal", function(e) {
       var $target = $(e.target);
       if($target.data("datasetChanged") === true && $target.data("addPlot") === true) {
           $target.data("addPlot", false);
           $(".new-plot-btn").click();
       }
    });

    $("input[name=secondDataset]").bootstrapSwitch({
        "onSwitchChange": function (event, state) {
            var $dataset2Btn = $("#dataset2-btn").data('active', state);
            if (state) {
                $dataset2Btn.show();
                if($(".new-plot-btn").data("dataset2Id") === undefined) {
                    $dataset2Btn.click();
                }
            } else {
                $dataset2Btn.hide();
            }
            updateURL();
        }
    });

    var adjustZindexes = function() {
        $('.sortable-panels').find('.hts-change-data').each(function(i, obj) {
            obj.style.zIndex = 1999 - i;
        });
    };


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
        },
        update: adjustZindexes
    });

    var setColumns = function (numColsMd, numColsLg) {
        var numBScolsLg = Math.round(12 / numColsLg);
        var numBScolsMd = Math.round(12 / numColsMd);
        $(".panel-container").removeClass("col-lg-3 col-lg-4 col-lg-6 " +
            "col-lg-12 col-md-6 col-md-12").addClass
        ("col-lg-" + numBScolsLg + " col-md-" + numBScolsMd);
        resizeGraphs();
        $(".sortable-panels").sortable("option", "placeholder",
            "panel-placeholder col-lg-" + numBScolsLg +
            " col-md-" + numBScolsMd);
        $("#hts-current-num-cols-lg").text(numColsLg + " column" +
            (numColsLg > 1 ? "s" : "")).data("cols", numColsLg);
        $("#hts-current-num-cols-md").text(numColsMd + " column" +
            (numColsMd > 1 ? "s" : "")).data("cols", numColsMd);
    };

    var resizeGraphs = function () {
        $(".plotly-graph-div.loaded").each(function (i, obj) {
            Plotly.Plots.resize(obj);
        });
    };

    $(window).resize(function () {
        clearTimeout($.data(window, "resizeTimer"));
        $.data(window, "resizeTimer", setTimeout(function () {
            resizeGraphs();
        }, 200));
    });

    $("#hts-num-cols-lg").find("li").click(function (e) {
        e.preventDefault();
        var lgCols = $(e.currentTarget).data("cols");
        var mdCols = lgCols >= 2 ? 2 : 1;
        setColumns(mdCols, lgCols);
        updateURL();
    });

    $("#hts-num-cols-md").find("li").click(function (e) {
        e.preventDefault();
        var mdCols = $(e.currentTarget).data("cols");
        setColumns(mdCols, mdCols);
        updateURL();
    });

    var parseOption = function(option) {
        var $newOption = $("<option></option>");
        $newOption.val(option.id);
        $newOption.text(option.name);
        if (option.hasOwnProperty("public") && option.public) {
            $newOption.prepend("<i class=\"fa fa-users\"></i> ");
        }
        return $newOption;
    };

    var parseOptGroup = function (optGroup) {
        var $newOptgroup = $("<optgroup></optgroup>");
        $newOptgroup.attr('label', optGroup.optgroup);
        for (var i=0,len=optGroup.options.length; i < len; i++) {
            $newOptgroup.append(parseOption(optGroup.options[i]));
        }
        return $newOptgroup;
    };

    var pushOptionsToSelect = function ($select, optionList, selectedOption) {
        var len = optionList.length;
        var combinations = [];
        for (var i = 0; i < len; i++) {
            if(Array.isArray(optionList[i].id)) {
                var $newOption = $("<option></option>");
                $newOption.val(optionList[i].id.join(","));
                $newOption.text(optionList[i].name.join(" & "));
                combinations.push($newOption);
            } else {
                if(optionList[i].hasOwnProperty("optgroup")) {
                    $select.append(parseOptGroup(optionList[i]));
                } else {
                    $select.append(parseOption(optionList[i]));
                }
            }
        }
        var numCombos = combinations.length;
        if (numCombos > 0) {
            var $comboGrp = $("<optgroup label=\"Combinations\"></optgroup>");
            for (var i = 0; i < numCombos; i++) {
                $comboGrp.append(combinations[i]);
            }
            $select.append($comboGrp);
        }
        if (len === 0) {
            $select.selectpicker({title: "No options available"});
        } else {
            if (selectedOption === undefined) {
                $select.selectpicker("val",
                    Array.isArray(optionList[0].id) ? optionList[0].id.join(",") : optionList[0].id);
            } else {
                $select.val(selectedOption);
            }
        }
        $select.selectpicker("refresh");
    };

    var setSelectPicker = function($selectPicker, newState) {
        $selectPicker.prop("disabled", !newState).selectpicker("refresh");
        $selectPicker.closest(".form-group").toggle(newState);
    };

    var setRadio = function($radioDiv, newState) {
        $radioDiv.find("input[type=radio]").prop("disabled", !newState);
        $radioDiv.closest(".form-group").toggle(newState);
    };

    var setPlotType = function($dataPanel) {
        var plotType = $dataPanel.find("input[name=plotType]:checked").val();
        $dataPanel.removeClass (function (index, className) {
            return (className.match (/(^|\s)plot-type-\S+/g) || []).join(" ");
        }).addClass("plot-type-"+plotType);

        // Disable non-active form components
        var showPanels = [".hidden-tc", ".hidden-drc", ".hidden-drpar", ".hidden-qc"];
        var thisHiddenPanel = ".hidden-" + plotType;
        showPanels.splice(showPanels.indexOf(thisHiddenPanel), 1);
        showPanels = showPanels.join(",");
        // text, hidden, radio, select
        $dataPanel.find(thisHiddenPanel).find("input,select").not(".no-disable,[type=checkbox]").prop("disabled", true);
        $dataPanel.find(showPanels).not(thisHiddenPanel).find("input,select").not(".no-disable,[type=checkbox]").prop("disabled", false);
        // checkbox
        $dataPanel.find(thisHiddenPanel).find("input[type=checkbox]").bootstrapSwitch("disabled", true);
        $dataPanel.find(showPanels).find("input[type=checkbox]").bootstrapSwitch("disabled", false);

        if (plotType === "qc") {
            $dataPanel.find("select[name=plateId]").selectpicker("refresh");
        } else if (plotType === "drpar") {
            $dataPanel.find("select.drpar-select").selectpicker("refresh");
        }

        // Select multiple cell lines/drugs or not
        var $changeCL = $dataPanel.find("select.hts-change-cell-line"),
            $changeDrug = $dataPanel.find("select.hts-change-drug"),
            $changeCLDrug = $changeCL.add($changeDrug),
            $actionBtns = $dataPanel.find(
                "div.hts-change-cell-line,div.hts-change-drug"
            ).find(".bs-actionsbox"),
            $optgroupDrugCombos =
                $changeDrug.find("optgroup[label=Combinations]");
        if (plotType === "tc") {
            // Need to manually set value to avoid buggy behaviour
            var clVal = $changeCL.val()[0],
                drVal = $changeDrug.val()[0];

            $changeCL.selectpicker("val", clVal);
            $changeDrug.selectpicker("val", drVal);

            // Enable drug combinations
            $optgroupDrugCombos.prop("disabled", false);

            $actionBtns.hide();

            $changeCLDrug.selectpicker(selectPickerOptionsSingle);

            $dataPanel.find(".name-tag-switch").find('input[value=off]').click();
            $changeCLDrug.trigger("hide.bs.select");
        } else {
            // Disable drug combinations
            $optgroupDrugCombos.find("option:selected")
                .prop("selected", false);
            $optgroupDrugCombos.prop("disabled", true);
            $actionBtns.show();
            $changeCLDrug.selectpicker(selectPickerOptionsMultiple);
        }
        $changeCLDrug.selectpicker("refresh");
        // $('select.tag-select').selectpicker(selectPickerTagOptions).selectpicker("render").selectpicker("refresh");
        // Only enable drug combos on timecourse plot for now
        var $toggleDRparTwoSwitch = $dataPanel.find("input[name=drParTwoToggle]");
        var $toggleDRparOrderSwitch = $dataPanel.find("input[name=drParOrderToggle]");
        if (plotType === "drpar") {
            toggleDRparTwoSwitch($toggleDRparTwoSwitch, $toggleDRparTwoSwitch.prop("checked"));
            toggleDRparOrderSwitch($toggleDRparOrderSwitch, $toggleDRparOrderSwitch.prop("checked"));
        } else {
            setRadio($dataPanel.find(".hts-aggregate"), false);
        }
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
    $("input[name=qcView]").change(function(e) {
        var $target = $(e.target);
        var $dataPanel = $target.closest(".hts-change-data");
        $dataPanel.find("select[name=plateId]").closest(".form-group").toggle(
            $target.val() === "dipplatemap");
    });
    $("input[name=drMetric]").change(function(e) {
        var $target = $(e.target);
        var $dataPanel = $target.closest(".hts-change-data");
        var $drcTypeBox = $dataPanel.find("input[name=drcType]").closest(".form-group");
        if($target.val() === "viability") {
            $drcTypeBox.slideUp();
            $dataPanel.find("option.dip-metric").prop("disabled", true).closest("select").selectpicker("refresh");
        } else {
            $drcTypeBox.slideDown();
            $dataPanel.find("option.dip-metric").prop("disabled", false).closest("select").selectpicker("refresh");
        }
    });
    $(".name-tag-switch").find("input[type=radio]").change(function() {
        var $this = $(this);
        var selectName;
        var $formGroup = $this.closest(".cl-or-drug");
        if ($this.val() === "on") {
            selectName = $this.attr('name') === 'useCellLineTags' ? 'd' : 'c';
            var $select = $formGroup.closest(".hts-change-data").find("select[name="+selectName+"]");
            var $options = $select.find("option");
            $options.filter(".option-limited").removeClass("option-limited");
            $options.filter(".option-unavailable").removeClass("option-unavailable");
            $select.selectpicker('refresh');
            $formGroup.find(".tag-select").prop("disabled", false).selectpicker("show").selectpicker("refresh");
            $formGroup.find(".name-select").prop("disabled", true).selectpicker("hide");
        } else {
            selectName = $this.attr('name') === 'useCellLineTags' ? 'c' : 'd';
            $formGroup.closest(".hts-change-data").find("select[name="+selectName+"]").trigger("hide.bs.select");
            $formGroup.find(".tag-select").prop("disabled", true).selectpicker("hide");
            $formGroup.find(".name-select").prop("disabled", false).selectpicker("show").selectpicker("refresh");
        }
    });
    $(".btn-group").on("click", ".disabled", function(e) {
        e.preventDefault();
        return false;
    });
    $(".hts-change-data > form").submit(function (e) {
        e.preventDefault();
        var $form = $(e.currentTarget);

        if($form.data("force")) {
            $form.data("force", false);
        } else {
            var numCellLines = $form.find("select[name=c]:enabled")
                .find("option:selected").length;
            var numDrugs = $form.find("select[name=d]:enabled")
                .find("option:selected").length;
            var plotType = $form.find("input[name=plotType]:checked").val();
            var numTraces = numCellLines * numDrugs;

            if (plotType === "drc" && numTraces > 100 ||
                plotType === "drpar" && numTraces > 1000) {
                ui.okCancelModal({
                    title: "Large plot requested",
                    text: "The plot you've requested has up to " +
                    numTraces + " cell line/drug combinations. This may slow" +
                    " down your browser and/or take some time to load." +
                    "<br><br>Continue?",
                    onOKHide: function () {
                        $form.data("force", true).submit();
                    },
                    okLabel: "Show Plot"
                });
                return;
            }
        }

        var $plotPanel = $(this).closest(".plot-panel");
        var $plotPanelBody = $plotPanel.find(".panel-body");
        $plotPanelBody.loadingOverlay("show");
        var $submit = $form.find("button[type=submit]");
        toggleDataPanel($plotPanel, false);

        $submit.prop("disabled", true).text("Loading...");
        $.ajax({
            url: ajax.url("get_plot") + "?" + $form.serialize(),
            type: "GET",
            dataType: "json",
            success: function (data) {
                createPlot(
                    $plotPanelBody.find(".plotly-graph-div").addClass("loaded"),
                    data
                );
                updateURL();
            },
            error: function(jqXHR, textStatus, thrownError) {
                ajax.ajaxErrorCallback(jqXHR, textStatus, thrownError);
                toggleDataPanel($plotPanel, true);
            },
            complete: function () {
                $submit.prop("disabled", false).text("Show Plot");
                $plotPanelBody.loadingOverlay("hide");
            }
        });
    });
    // End data panel events

    var createPlot = function($element, data) {
        $element.empty().data("plotly", data);
        Plotly.newPlot(
            $element[0],
            data.data,
            data.layout,
            {
                showLink: false,
                displaylogo: false,
                modeBarButtonsToRemove: ["sendDataToCloud", "toImage"]
            }
        );

        $element[0].addEventListener('touchenter', plotlyTouchHandler);
        $element[0].addEventListener('touchleave', plotlyTouchHandler);
        $element[0].addEventListener('touchstart', plotlyTouchHandler);
        $element[0].addEventListener('touchmove', plotlyTouchHandler);
        $element[0].addEventListener('touchend', plotlyTouchHandler);
    };

    var setViabilityOnly = function($dataPanel) {
        var $vaxis = $dataPanel.find('input[name=logTransform]');
        var $drMetric = $dataPanel.find('input[name=drMetric]');

        $drMetric.filter('[value=viability]').prop('checked', true).trigger('change').closest('.form-group').hide();
        $vaxis.filter('[value=None]').prop('checked', true).closest('.form-group').hide();

        $dataPanel.find('input[name=qcView]').prop('disabled', true)
            .closest('label').addClass('disabled');

        $dataPanel.find('.hts-drc-type').closest('.form-group').remove();
        $dataPanel.find(".hts-show-dip-fit").closest('.form-group').remove();

        $dataPanel.find(".dataset-badges").html('<span' +
            ' class="badge">1x <i class="fa fa-clock-o"></i></span>');
    };

    var toggleDataPanel = function($panel, showIfTrue) {
        var $parentTgt = $panel.find(".hts-change-data-btn").parent();
        var $dataPanel = $panel.find(".hts-change-data");
        if($parentTgt.hasClass("open") && (showIfTrue === undefined || !showIfTrue)) {
            $parentTgt.removeClass("open");
            $dataPanel.hide();
        } else if (!$parentTgt.hasClass("open") && (showIfTrue === undefined || showIfTrue)) {
            if($dataPanel.data("loaded") === false) {
                prepareDataPanel($panel);
            }
            $parentTgt.addClass("open");
            $dataPanel.show();
            $dataPanel.find("select:enabled").selectpicker("refresh");
        }
    };

    // Plot panel events
    $(".hts-change-data-btn").parent().click(function(e) {
        toggleDataPanel($(e.currentTarget).closest(".plot-panel"));
    });

    $(".hts-download-btn").parent().on("show.bs.dropdown", function(e) {
        toggleDataPanel($(e.currentTarget).closest(".plot-panel"), false);
    });
    $("a[data-download]").click(function(e) {
        e.preventDefault();
        var $this = $(e.currentTarget),
            action = $this.data("download"),
            $panel = $this.closest(".plot-panel");
        // check plot loaded
        var $plotDiv = $panel.find(".plotly-graph-div.loaded");
        if(!$plotDiv.length) {
            ui.okModal({title: "Plot not loaded",
                        text: "Please load a plot first, using the Change" +
                        " Plot menu"});
            return;
        }
        // process download
        switch (action) {
            case "svg":
            case "png":
                return downloadImage($plotDiv[0], action);
            case "json":
                window.location = ajax.url("get_plot") + "?" +
                    $panel.find("form").serialize() + "&download=1";
                return;
            case "csv":
                window.location = ajax.url("get_plot_csv") + "?" +
                    $panel.find("form").serialize() + "&download=1";
                return;
            case "html":
                window.location = ajax.url("get_plot_html") + "?" +
                    $panel.find("form").serialize() + "&download=1";
                return;
        }
    });

    var objectifyForm = function(formArray) {
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
    };

    var toggleDRparTwoSwitch = function($toggleSwitch, state) {
        var $dataPanel = $toggleSwitch.closest(".hts-change-data");
        if(state) {
            var $drParOrder = $dataPanel.find("input[name=drParOrderToggle]");
            $drParOrder.bootstrapSwitch("state", false, true);
            $drParOrder.closest(".hts-drpar-group").find(".hts-drpar-entry").slideUp();
        }
        setRadio($dataPanel.find(".hts-aggregate"), !state);
        var $group = $toggleSwitch.closest(".hts-drpar-group");
        var $buttons = $group.find(".hts-drpar-entry");
        if(state) {
            $buttons.slideDown();
        } else {
            $buttons.slideUp();
        }
    };

    var toggleDRparOrderSwitch = function($toggleSwitch, state) {
        var $dataPanel = $toggleSwitch.closest(".hts-change-data");
        if(state) {
            var $parTwoToggle = $dataPanel.find("input[name=drParTwoToggle]");
            $parTwoToggle.bootstrapSwitch("state", false, true);
            $parTwoToggle.closest(".hts-drpar-group").find(".hts-drpar-entry").slideUp();
            setRadio($dataPanel.find(".hts-aggregate"), true);
        }
        var $group = $toggleSwitch.closest(".hts-drpar-group");
        var $buttons = $group.find(".hts-drpar-entry");
        if(state) {
            $buttons.slideDown();
        } else {
            $buttons.slideUp();
        }
    };

    var prepareDataPanel = function($plotPanel, defaultOptions, autoSubmit) {
        var $dataPanel = $plotPanel.find(".hts-change-data");

        $dataPanel.find("input.drParTwoToggle").bootstrapSwitch({
            "onSwitchChange": function(event, state) {
                toggleDRparTwoSwitch($(event.currentTarget), state);
            }
        });
        $dataPanel.find("input.drParOrderToggle").bootstrapSwitch({
            "onSwitchChange": function(event, state) {
                toggleDRparOrderSwitch($(event.currentTarget), state);
            }
        });

        $dataPanel.find("select[name=c],select[name=d]")
            .selectpicker(selectPickerOptionsSingle);
        $dataPanel.find("select.drpar-select")
            .on("changed.bs.select", function(e) {
                var $target = $(e.target);
                var $customBox = $target.closest(".hts-drpar-group").find(".hts-drpar-custom");
                if($target.val().indexOf("_custom") !== -1) {
                    $customBox.slideDown().find("input[type=text]").focus();
                } else {
                    $customBox.slideUp();
                }
        });
        $dataPanel.find(".hts-drpar-custom,.hts-viability-time").find("input[type=text]").focus(
            function() { $(this).select(); }
        );

        $dataPanel.data("loaded", true);

        var datasetId, dataset2Id;

        var $cellLineSelect = $dataPanel.find("select[name=c]"),
            $drugSelect = $dataPanel.find("select[name=d]"),
            $clTagSelect = $dataPanel.find("select[name=cT]"),
            $drTagSelect = $dataPanel.find("select[name=dT]"),
            $assaySelect = $dataPanel.find("select[name=assayId]"),
            $plateSelect = $dataPanel.find("select[name=plateId]");

        if(defaultOptions !== undefined) {
            // Set the dataset ID
            datasetId = defaultOptions["datasetId"];
            $dataPanel.find("input[name=datasetId]").val(datasetId);
            dataset2Id = defaultOptions["dataset2Id"];
            $dataPanel.find("input[name=dataset2Id]").val(dataset2Id);
        } else {
            datasetId = $dataPanel.find("input[name=datasetId]").val();
            dataset2Id = $dataPanel.find("input[name=dataset2Id]").val();
            setPlotType($dataPanel);
        }

        var datasetGroupingsIds = datasetId;
        var multiDataset = false;
        if (dataset2Id !== undefined && dataset2Id !== null &&
            dataset2Id !== "") {
            multiDataset = true;
            datasetGroupingsIds += "," + dataset2Id;
            $dataPanel.find("input[name=plotType]").filter("[class=no-multi-dataset]").parent().remove();
            $dataPanel.find(".hts-plot-type").removeClass("btn-group-3")
                .addClass("btn-group-2").find("input[name=plotType]").first()
                .click();
        }

        var populatePlotPanelOptions = function(data) {
            $dataPanel.find("span[class=dataset-name]").text(data.datasets[0]['name']);
            var dualDataset = false;
            if(dataset2Id !== undefined && dataset2Id !== null && dataset2Id !== "") {
                dualDataset = true;
                $dataPanel.find("span[class=dataset2-name]").text(data.datasets[1]['name']);
                $dataPanel.find("span[class=dataset2-name-container]").show();
            }
            if(data.singleTimepoint !== false) {
                setViabilityOnly($dataPanel);
            }
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
                $assaySelect,
                $.map(data.assays, function(a){return a;}));
            pushOptionsToSelect(
                $plateSelect,
                data.plates);
            if (!multiDataset && data.assays[0].length > 1) {
                setSelectPicker($assaySelect, true);
            }
            $clTagSelect.prop("disabled", true).selectpicker(selectPickerTagOptions).selectpicker("hide");
            pushOptionsToSelect(
                $clTagSelect,
                data.cellLineTags
            );
            $drTagSelect.prop("disabled", true).selectpicker(selectPickerTagOptions).selectpicker("hide");
            pushOptionsToSelect(
                $drTagSelect,
                data.drugTags
            );
            // grey out drugs not available for current cell line
            if (data.hasOwnProperty('missingCombinations')) {
                if(!data.hasOwnProperty('missingCombinationsCL')) {
                    data.missingCombinationsCL = {};
                    data.missingCombinationsDR = {};
                    for (var i = 0, len = data.missingCombinations.length; i < len; i++) {
                        var cl = data.missingCombinations[i][0];
                        var dr = data.missingCombinations[i][1].join(',');
                        if (!data.missingCombinationsCL.hasOwnProperty(cl)) {
                            data.missingCombinationsCL[cl] = [];
                        }
                        data.missingCombinationsCL[cl].push(dr);
                        if (!data.missingCombinationsDR.hasOwnProperty(dr)) {
                            data.missingCombinationsDR[dr] = [];
                        }
                        data.missingCombinationsDR[dr].push(cl);
                    }
                }

                $cellLineSelect.on('hide.bs.select', function (e) {
                    var $target = $(e.target);
                    var cellLines = $target.selectpicker('val');
                    var drugsMissing = {};
                    var clLen = cellLines.length;
                    for (var c=0;c<clLen;c++) {
                        var cellLine = cellLines[c];
                        if(data.missingCombinationsCL.hasOwnProperty(cellLine)) {
                            var drugList = data.missingCombinationsCL[cellLine];
                            for(var d=0,dLen=drugList.length;d<dLen;d++) {
                                var drugStr = drugList[d];
                                if (drugsMissing.hasOwnProperty(drugStr)) {
                                    drugsMissing[drugStr]++;
                                } else {
                                    drugsMissing[drugStr] = 1;
                                }
                            }
                        }
                    }
                    var $options = $drugSelect.find("option");
                    $options.filter(".option-unavailable").removeClass("option-unavailable");
                    $options.filter(".option-limited").removeClass("option-limited");
                    for (var dm in drugsMissing) {
                        if (drugsMissing.hasOwnProperty(dm)) {
                            var $thisOptions = $options.filter("[value=" + dm + "]");
                            if (!dualDataset && drugsMissing[dm] === clLen) {
                                $thisOptions.addClass("option-unavailable");
                            } else {
                                $thisOptions.addClass("option-limited")
                            }
                        }
                    }
                    $drugSelect.selectpicker("refresh");
                });

                $drugSelect.on('hide.bs.select', function (e) {
                    var $target = $(e.target);
                    var drugs = $target.selectpicker('val');
                    var cellLinesMissing = {};
                    var drLen = drugs.length;
                    for (var d=0;d<drLen;d++) {
                        var drug = drugs[d];
                        if(data.missingCombinationsDR.hasOwnProperty(drug)) {
                            var cellLineList = data.missingCombinationsDR[drug];
                            for(var c=0,clLen=cellLineList.length;c<clLen;c++) {
                                var clStr = cellLineList[c];
                                if (cellLinesMissing.hasOwnProperty(clStr)) {
                                    cellLinesMissing[clStr]++;
                                } else {
                                    cellLinesMissing[clStr] = 1;
                                }
                            }
                        }
                    }
                    var $options = $cellLineSelect.find("option");
                    $options.filter(".option-unavailable").removeClass("option-unavailable");
                    $options.filter(".option-limited").removeClass("option-limited");
                    for (var cm in cellLinesMissing) {
                        if (cellLinesMissing.hasOwnProperty(cm)) {
                            var $thisOptions = $options.filter("[value=" + cm + "]");
                            if (!dualDataset && cellLinesMissing[cm] === drLen) {
                                $thisOptions.addClass("option-unavailable");
                            } else {
                                $thisOptions.addClass("option-limited")
                            }
                        }
                    }
                    $cellLineSelect.selectpicker("refresh");
                });
            }

            if(plotOptionsCache[datasetGroupingsIds] === 'PENDING') {
                plotOptionsCache[datasetGroupingsIds] = data;
            }

            if(defaultOptions !== undefined) {
                $dataPanel.find("input,select").each(function(i, obj) {
                    if(defaultOptions.hasOwnProperty(obj.name)) {
                        var $obj = $(obj);
                        var val = defaultOptions[obj.name];
                        if ($obj.prop("tagName").toLowerCase() === "select") {
                            $obj.selectpicker("val", val).trigger("changed.bs.select");
                        } else {
                            if (obj.type === "hidden" || obj.type === "text") {
                                $obj.val(val);
                            } else if (obj.type === "radio" && $obj.val() === val) {
                                $obj.click();
                            } else if (obj.type === "checkbox" && val === "on") {
                                $obj.bootstrapSwitch("state", true);
                            }
                        }
                    }
                });
            }

            if (autoSubmit === true) {
                $dataPanel.find("form").submit();
            }

            $cellLineSelect.add($drugSelect).trigger('hide.bs.select');
        };

        var waitForAjaxQuery = function() {
            if(!plotOptionsCache.hasOwnProperty(datasetGroupingsIds)) {
                $plotPanel.find(".panel-body").loadingOverlay("hide");
                return;
            }
            if(plotOptionsCache[datasetGroupingsIds] !== 'PENDING') {
                return populatePlotPanelOptions(plotOptionsCache[datasetGroupingsIds]);
            }
            setTimeout(waitForAjaxQuery, 200);
        };

        if(plotOptionsCache.hasOwnProperty(datasetGroupingsIds)) {
            waitForAjaxQuery();
        } else {
            plotOptionsCache[datasetGroupingsIds] = 'PENDING';
            $.ajax({
                url: ajax.url("dataset_groupings", datasetGroupingsIds),
                type: "GET",
                success: populatePlotPanelOptions,
                error: function(jqXHR, textStatus, errorThrown) {
                    delete plotOptionsCache[datasetGroupingsIds];
                    $plotPanel.find(".panel-close-btn").trigger("click");
                    if(jqXHR.status === 404) {
                        ui.okModal({title: "Dataset not found",
                                    text: "The requested dataset does not " +
                                    "exist, or you don't have access to it. " +
                                    "Check you're logged with the correct " +
                                    "account, or request access from the " +
                                    "dataset owner." });
                    } else {
                        ajax.ajaxErrorCallback(jqXHR, textStatus, errorThrown);
                    }
                }
            });
        }
    };

    $(".panel-close-btn").on("click", function () {
        var $this = $(this);
        var $container = $this.closest(".panel-container");
        $container[$this.data("effect")](400,
            function () {
                Plotly.purge($container.find(".plotly-graph-div")[0]);
                $container.remove();
                if($(".panel-container").length === 1) {
                    $("#quickstart").fadeIn();
                }
                updateURL();
            });
    });

    $(".panel-newwin-btn").click(function() {
       window.open(
           ajax.url("get_plot_html") + "?" + $(this).closest(".plot-panel").find("form").serialize(),
           '',
           'height=400,width=600,scrollbars=no,status=no,menubar=no'
       );
    });

    $(".panel-copy-btn").on("click", function() {
        var $panel = $(this).closest(".panel-container");
        var $newPanel = $(".panel-container").last().clone(true, true);
        var $newPlotly = $newPanel.find(".plotly-graph-div");

        // Insert the panel, add the plot
        $newPanel.insertAfter($panel).fadeIn(400);
        // The plot has to be added after being added to the DOM in order
        // for size to be calculated correctly
        var plotData = $panel.find(".plotly-graph-div").data("plotly");
        if (plotData) {
            createPlot($newPlotly, plotData);
            $newPlotly.addClass("loaded");
        }

        // The click events on the panel have to be fired after the panel
        // is added to the DOM or the bootstrap events don't fire properly
        var formData = objectifyForm($panel.find("form").serializeArray());
        prepareDataPanel($newPanel, formData);

        if($panel.find(".hts-change-data-btn").parent().hasClass("open")) {
            $newPanel.find(".hts-change-data-btn").click();
        }

        updateURL();

        $("html, body").animate({
            scrollTop: $newPanel.offset().top
        }, 400);
        adjustZindexes();
    });

    // Add new panel
    var $newPlotBtn = $(".new-plot-btn");
    $newPlotBtn.click(function () {
        var datasetId = $newPlotBtn.data("datasetId");
        if(datasetId === "") {
            $("#change-dataset-modal")
                .data("addPlot", true);
            $("#dataset-btn").click();
            return;
        }
        var dataset2active = isDataset2active();
        var dataset2Id;
        if (dataset2active) {
            dataset2Id = $newPlotBtn.data("dataset2Id");
            if (datasetId === dataset2Id) {
                return ui.okModal({
                    title: "Datasets are the same",
                    text: "Please select two different datasets for" +
                    " comparison, or turn off the second dataset."
                });
            }
        }
        if($newPlotBtn.data("dataset2Id") === undefined && dataset2active) {
            return ui.okModal({title: "Second dataset not selected",
                text: "Please select a second dataset using the button" +
                " left of the Add Plot button, or remove the second dataset."
            })
        }
        var $plotPanel = $(".panel-container").last().clone(true, true);
        $plotPanel.find("input[name=datasetId]").val(datasetId);
        var $dataset2Id = $plotPanel.find("input[name=dataset2Id]");
        if (dataset2active) {
            $dataset2Id.val(dataset2Id);
        } else {
            $dataset2Id.prop("disabled", true);
        }
        var $changeDataBtn = $plotPanel.find(".hts-change-data-btn");

        $("#quickstart").hide();
        $plotPanel.prependTo(".sortable-panels").fadeIn(400, function () {
            $changeDataBtn.click();
        });
        adjustZindexes();
    });

    function plotlyTouchHandler(event)
    {
        // console.log(`touchHandler triggered for event ${event.type}`);
        var touches = event.changedTouches,
            first = touches[0],
            type = "";
        switch(event.type)
        {
          case "touchenter": type = "mouseover"; break;
          case "touchleave": type = "mouseout";  break;
          case "touchstart": type = "mousedown"; break;
          case "touchmove":  type = "mousemove"; break;
          case "touchend":   type = "mouseup";   break;
          default:           return;
        }

        var opts = {
          bubbles: true,
          screenX: first.screenX,
          screenY: first.screenY,
          clientX: first.clientX,
          clientY: first.clientY
        };

        var simulatedEvent = new MouseEvent(type, opts);

        first.target.dispatchEvent(simulatedEvent);
        event.preventDefault();
    }

    var queryStrings = getQueryStrings();
    var plotStrings = queryStrings.plotStrings;
    setColumns(queryStrings.colsMd, queryStrings.colsLg);

    //restore any plots
    if (plotStrings.length) {
        var $panelTemplate = $(".panel-container").last();
        var $showPlotDelayedMsg = $(".show-plot-delayed");
        var showWarning = false;
        for (var i = 0; i < plotStrings.length; i++) {
            var formData = {};
            try {
                var plotStringData = plotStrings[i].split("&");
                for (var j = 0; j < plotStringData.length; j++) {
                    var keyValuePair = plotStringData[j].split("=");
                    if(typeof formData[keyValuePair[0]] === 'undefined') {
                        formData[keyValuePair[0]] = decodeURIComponent(keyValuePair[1]);
                    } else {
                        if (typeof formData[keyValuePair[0]] === 'string') {
                            formData[keyValuePair[0]] = [formData[keyValuePair[0]]];
                        }
                        formData[keyValuePair[0]].push(decodeURIComponent(keyValuePair[1]));
                    }
                }
            } catch(e) {
                // Ignore
                console.log(e);
                showWarning = true;
            }
            if(!$.isEmptyObject(formData)) {
                if(!formData.hasOwnProperty('datasetId') || formData['datasetId'] === '') {
                    showWarning = true;
                } else {
                    var $plotPanel = $panelTemplate.clone(true, true);
                    var showByDefault = i < 4;
                    if (!showByDefault) {
                        $showPlotDelayedMsg.clone().appendTo($plotPanel.find(".plotly-graph-div"));
                    }
                    $plotPanel.appendTo(".sortable-panels").show();
                    prepareDataPanel($plotPanel, formData, showByDefault);
                    if (showByDefault) {
                        $plotPanel.find(".panel-body").loadingOverlay("show");
                    }
                }
            }
        }
        if(showWarning) {
            ui.okModal({
                'title': 'Error decoding URL',
                'text': 'There was an error decoding the URL, which means' +
                ' the plots cannot be loaded. If you clicked on a link to' +
                ' load this page, try copying and pasting the URL instead.'
            });
            $('#quickstart').show();
        } else {
            $(".show-plot-delayed").not(":last").show().find("button").click(function () {
                $(this).closest(".plot-panel").find(".hts-change-data > form").submit();
            });
            adjustZindexes();
        }
    } else {
        $("#quickstart").show();
    }
};
module.exports = {
    activate: plots
};
