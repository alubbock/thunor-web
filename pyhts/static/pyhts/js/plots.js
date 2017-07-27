var ajax = require("./modules/ajax");
var ui = require("./modules/ui");
var datasetTable = require("./modules/dataset_table");

var downloadImage = function(gd, fmt) {
    var $gd = $(gd);
    var filename = $gd.find(".gtitle").text();
    var width = $gd.width();
    var height = $gd.height();

    Plotly.downloadImage(gd, {"format": fmt, "filename": filename,
                              "width": width, "height": height});
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

    $.fn.selectpicker.Constructor.DEFAULTS.iconBase = "fa";
    $.fn.selectpicker.Constructor.DEFAULTS.tickIcon = "fa-check";

    $("#change-dataset-modal").on("show.bs.modal", function(e) {
        var $target = $(e.target);
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
                    $(".new-plot-btn").data("datasetId",
                        $this.data("datasetId")
                    );
                    $("#dataset-name").text($this.data("datasetName"));
                    $target.data("datasetChanged", true);
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
            (numColsLg > 1 ? "s" : ""));
        $("#hts-current-num-cols-md").text(numColsMd + " column" +
            (numColsMd > 1 ? "s" : ""));
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
    });

    $("#hts-num-cols-md").find("li").click(function (e) {
        var mdCols = $(e.currentTarget).data("cols");
        setColumns(mdCols, mdCols);
    });

    var pushOptionsToSelect = function ($select, optionList, selectedOption) {
        var len = optionList.length;
        for (var i = 0; i < len; i++) {
            var $newOption = $("<option></option>");
            $newOption.val(optionList[i].id);
            $newOption.text(optionList[i].name);
            $select.append($newOption);
        }
        if (len === 0) {
            $select.closest(".bootstrap-select").
                    find("span").first().text("No options available");
        } else {
            if (selectedOption === undefined) {
                $select.selectpicker("val", optionList[0].id);
            } else {
                $select.val(selectedOption);
            }
            $select.selectpicker("refresh");
        }
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

            $dataPanel.find("button.names-link").click();
            $actionBtns.hide();
        } else {
            $changeCLDrug
                .selectpicker(selectPickerOptionsMultiple)
                .selectpicker("refresh")
                .selectpicker("render");

            $actionBtns.show();
        }
        var $toggleDipparTwoSwitch = $dataPanel.find("input[name=dipParTwoToggle]");
        var $toggleDipparOrderSwitch = $dataPanel.find("input[name=dipParOrderToggle]");
        if (plotType === "dippar") {
            toggleDipparTwoSwitch($toggleDipparTwoSwitch, $toggleDipparTwoSwitch.prop("checked"));
            toggleDipparOrderSwitch($toggleDipparOrderSwitch, $toggleDipparOrderSwitch.prop("checked"));
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
    $(".tags-link").click(function() {
        var $this = $(this).addClass("active");
        var $formGroup = $this.closest(".form-group");
        $formGroup.find(".names-link").removeClass("active");
        $formGroup.find(".tag-select").prop("disabled", false).selectpicker("refresh").selectpicker("show");
        $formGroup.find(".name-select").prop("disabled", true).selectpicker("hide");
    });
    $(".names-link").click(function() {
        var $this = $(this).addClass("active");
        var $formGroup = $this.closest(".form-group");
        $formGroup.find(".tags-link").removeClass("active");
        $formGroup.find(".tag-select").prop("disabled", true).selectpicker("hide");
        $formGroup.find(".name-select").prop("disabled", false).selectpicker("refresh").selectpicker("show");
    });
    $(".hts-change-data > form").submit(function (e) {
        e.preventDefault();
        var $form = $(e.currentTarget);

        if($form.data("force")) {
            $form.data("force", false);
        } else {
            var numCellLines = $form.find("select[name=cellLineId]:enabled")
                .find("option:selected").length;
            var numDrugs = $form.find("select[name=drugId]:enabled")
                .find("option:selected").length;
            var plotType = $form.find("input[name=plotType]:checked").val();
            var numTraces = numCellLines * numDrugs;

            if (plotType === "dip" && numTraces > 100 ||
                plotType === "dippar" && numTraces > 1000) {
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
        var $changeDataBtn = $plotPanel.find(".hts-change-data-btn");
        $plotPanelBody.loadingOverlay("show");
        var $submit = $form.find("button[type=submit]");

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
                $changeDataBtn.click();
            },
            error: ajax.ajaxErrorCallback,
            complete: function () {
                $submit.prop("disabled", false).text("Show Plot");
                $plotPanelBody.loadingOverlay("hide");
            }
        });
    });
    // End data panel events

    var createPlot = function($element, data) {
        $element.data("plotly", data);
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

    var toggleDipparTwoSwitch = function($toggleSwitch, state) {
        var $dataPanel = $toggleSwitch.closest(".hts-change-data");
        if(state) {
            var $dipParOrder = $dataPanel.find("input[name=dipParOrderToggle]");
            $dipParOrder.bootstrapSwitch("state", false, true);
            $dipParOrder.closest(".hts-dippar-group").find(".hts-dippar-entry").slideUp();
        }
        setRadio($dataPanel.find(".hts-aggregate"), !state);
        var $group = $toggleSwitch.closest(".hts-dippar-group");
        var $buttons = $group.find(".hts-dippar-entry");
        if(state) {
            $buttons.slideDown();
        } else {
            $buttons.slideUp();
        }
    };

    var toggleDipparOrderSwitch = function($toggleSwitch, state) {
        var $dataPanel = $toggleSwitch.closest(".hts-change-data");
        if(state) {
            var $parTwoToggle = $dataPanel.find("input[name=dipParTwoToggle]");
            $parTwoToggle.bootstrapSwitch("state", false, true);
            $parTwoToggle.closest(".hts-dippar-group").find(".hts-dippar-entry").slideUp();
            setRadio($dataPanel.find(".hts-aggregate"), true);
        }
        var $group = $toggleSwitch.closest(".hts-dippar-group");
        var $buttons = $group.find(".hts-dippar-entry");
        if(state) {
            $buttons.slideDown();
        } else {
            $buttons.slideUp();
        }
    };

    var prepareDataPanel = function($plotPanel, defaultOptions) {
        var $dataPanel = $plotPanel.find(".hts-change-data");

        $dataPanel.find("input.dipParTwoToggle").bootstrapSwitch({
            "onSwitchChange": function(event, state) {
                toggleDipparTwoSwitch($(event.currentTarget), state);
            }
        });
        $dataPanel.find("input.dipParOrderToggle").bootstrapSwitch({
            "onSwitchChange": function(event, state) {
                toggleDipparOrderSwitch($(event.currentTarget), state);
            }
        });

        $dataPanel.find("select[name=cellLineId],select[name=drugId]")
            .selectpicker(selectPickerOptionsSingle);
        $dataPanel.find(".hts-dippar-select").find("select")
            .selectpicker().on("changed.bs.select", function(e) {
                var $target = $(e.target);
                var $customBox = $target.closest(".hts-dippar-group").find(".hts-dippar-custom");
                if($target.val().indexOf("_custom") !== -1) {
                    $customBox.slideDown().find("input[type=text]").focus();
                } else {
                    $customBox.slideUp();
                }
        });
        $dataPanel.find(".hts-dippar-custom").find("input[type=text]").focus(
            function() { $(this).select(); }
        );

        $dataPanel.data("loaded", true);

        var datasetId;

        var $cellLineSelect = $dataPanel.find("select[name=cellLineId]"),
            $drugSelect = $dataPanel.find("select[name=drugId]"),
            $assaySelect = $dataPanel.find("select[name=assayId]");

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
                $assaySelect,
                data.assays);
            if (data.assays.length > 1) {
                setSelectPicker($assaySelect, true);
            }
            var $selectClTags = $dataPanel.find("select[name=cellLineTags]");
            $selectClTags.selectpicker("hide");
            pushOptionsToSelect(
                $selectClTags,
                data.cellLineTags
            );
            var $selectDrTags = $dataPanel.find("select[name=drugTags]");
            $selectDrTags.selectpicker("hide");
            pushOptionsToSelect(
                $selectDrTags,
                data.drugTags
            );

            if(!plotOptionsCache.hasOwnProperty(datasetId)) {
                plotOptionsCache[datasetId] = data;
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
        var $this = $(this);
        var $container = $this.closest(".panel-container");
        $container[$this.data("effect")](400,
            function () {
                Plotly.purge($container.find(".plotly-graph-div")[0]);
                $container.remove();
                if($(".panel-container").length === 1) {
                    $("#quickstart").fadeIn();
                }
            });
    });

    $(".panel-copy-btn").on("click", function() {
        var $panel = $(this).closest(".panel-container");
        var $newPanel = $(".panel-container").last().clone(true, true);
        var $newPlotly = $newPanel.find(".plotly-graph-div");

        $newPanel.find("span[class=dataset-name]").text(
            $panel.find("span[class=dataset-name]").text()
        );

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
        // Set name/tag toggle switches
        $panel.find(".names-link.active,.tags-link.active").each(
          function(i, obj) {
              var $this = $(obj);
              $newPanel
                  .find($this.hasClass("names-link") ?
                                       ".names-link" : ".tags-link")
                  .filter("[data-entity=\""+$this.data("entity")+"\"]")
                  .click();
        });

        if($panel.find(".hts-change-data-btn").parent().hasClass("open")) {
            $newPanel.find(".hts-change-data-btn").click();
        }

        $("html, body").animate({
            scrollTop: $newPanel.offset().top
        }, 400);
    });

    // Add new panel
    $newPlotBtn = $(".new-plot-btn");
    $newPlotBtn.click(function (eNewPlot) {
        if($newPlotBtn.data("datasetId") === "") {
            $("#change-dataset-modal").data("addPlot", true).modal("show");
            return;
        }
        var $plotPanel = $(".panel-container").last().clone(true, true);
        $plotPanel.find("input[name=datasetId]").val(
            $(eNewPlot.currentTarget).data("datasetId")
        );
        $plotPanel.find("span[class=dataset-name]").text($("#dataset-name").text());
        var $changeDataBtn = $plotPanel.find(".hts-change-data-btn");

        $("#quickstart").hide();
        $plotPanel.prependTo(".sortable-panels").fadeIn(400, function () {
            $changeDataBtn.click();
        });
    });
};
module.exports = {
    activate: plots
};
