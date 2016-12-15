var util = require("./modules/util");

var Well = function(well) {
    if(well === undefined) {
        this.cellLine = null;
        this.drugs = [];
        this.doses = [];
    } else {
        this.cellLine = well.cellLine;
        this.drugs = well.drugs;
        this.doses = well.doses;
    }
};
Well.prototype = {
    constructor: Well,
    setDrug: function(drug, position) {
        if(this.drugs == null) this.drugs = [];
        if(drug == null && position == null) {
            this.drugs = [];
        } else {
            this.drugs[position] = drug;
        }
        this.setUnsavedChanges();
    },
    setDose: function(dose, position) {
        if(this.doses == null) this.doses = [];
        if(dose == null && position == null) {
            this.doses = [];
        } else {
            this.doses[position] = dose;
        }
        this.setUnsavedChanges();
    },
    setCellLine: function(cellLine) {
        this.cellLine = cellLine;
        this.setUnsavedChanges();
    },
    clear: function() {
        this.cellLine = null;
        this.drugs = null;
        this.doses = null;
        this.setUnsavedChanges();
    }
};

var PlateMap = function(plateId, numRows, numCols, wells) {
    this.unsaved_changes = false;
    this.plateId = plateId;
    this.numRows = numRows;
    this.numCols = numCols;
    this.wells = [];
    for (var w=0, len=(numRows*numCols); w<len; w++) {
        this.wells.push(wells === undefined ?
            new Well() : new Well(wells[w]));
        this.wells[w].setUnsavedChanges = this.setUnsavedChanges.bind(this);
    }
};
PlateMap.prototype = {
    constructor: PlateMap,
    selectionHeight: function(wellIds) {
        var rowNums = this.wellNumsToRowNums(wellIds);
        return Math.max.apply(null, rowNums) - Math.min.apply(null, rowNums) + 1;
    },
    selectionWidth: function(wellIds) {
        var colNums = this.wellNumsToColNums(wellIds);
        return Math.max.apply(null, colNums) - Math.min.apply(null, colNums) + 1;
    },
    moveSelectionBy: function(wellIds, moveStep, inRowDirection) {
        var newWellIds = [],
            maxWell = this.wells.length,
            colNums = this.wellNumsToColNums(wellIds);
        for(var w=0, len=wellIds.length; w<len; w++) {
            if(!inRowDirection) {
                // check we don't overflow column
                if((colNums[w] + moveStep < 0) ||
                    colNums[w] > (this.numCols - moveStep - 1)) {
                    throw new Error("Out of bounds");
                }
            }
            var newId = inRowDirection ?
                        wellIds[w] + (this.numCols * moveStep) :
                        wellIds[w] + moveStep;
            if(newId < 0 || newId > (maxWell - 1)) {
                throw new Error("Out of bounds");
            }
            newWellIds.push(newId);
        }
        return newWellIds;
    },
    moveSelectionDownBy: function(wellIds, moveStep) {
        return this.moveSelectionBy(wellIds, moveStep, true);
    },
    moveSelectionRightBy: function(wellIds, moveStep) {
        return this.moveSelectionBy(wellIds, moveStep, false);
    },
    getUsedEntries: function(entry_list) {
        var usedEntries = [];

        for(var i=0, len=this.wells.length; i<len; i++) {
            var ent = this.wells[i][entry_list];
            if (ent == null) {
               continue;
            }
            if(typeof ent == "object" &&
                (!ent.length || util.allNull(ent))) {
                    continue;
            }

            if(util.indexOf(ent, usedEntries) === -1) {
                usedEntries.push(ent);
            }
        }
        return usedEntries;
    },
    setUnsavedChanges: function() {
        this.unsaved_changes = true;
    },
    getUsedCellLines: function() {
        return this.getUsedEntries("cellLine");
    },
    getUsedDrugs: function() {
        return this.getUsedEntries("drugs");
    },
    getUsedDoses: function() {
        return this.getUsedEntries("doses");
    },
    maxDrugsDosesUsed: function() {
        var maxUsed = 0;
        for(var i=0, len=this.wells.length; i<len; i++) {
            var numDrugsUsed = 0, numDosesUsed = 0;
            if(this.wells[i].drugs != null) numDrugsUsed =  this.wells[i].drugs.length;
            if(this.wells[i].doses != null) numDosesUsed =  this.wells[i].doses.length;
            maxUsed = Math.max(maxUsed, numDrugsUsed, numDosesUsed);
        }
        return maxUsed;
    },
    wellNumToName: function(wellNum, padded) {
        return this.rowNumToName(Math.floor(wellNum / this.numCols)) +
               this.colNumToName(wellNum % this.numCols, padded);
    },
    rowNumToName: function(rowNum) {
        return String.fromCharCode(65 + rowNum);
    },
    colNumToName: function(colNum, padded) {
        if(padded === true) {
            return util.padNum(colNum + 1, this.numCols.toString().length);
        } else {
            return (colNum + 1).toString();
        }
    },
    wellNumsToRowNums: function(wellNums) {
        var rowNums = [];
        for(var w=0, len=wellNums.length; w<len; w++) {
            rowNums.push(Math.floor(wellNums[w] / this.numCols));
        }
        return rowNums;
    },
    wellNumsToColNums: function(wellNums) {
        var colNums = [];
        for(var w=0, len=wellNums.length; w<len; w++) {
            colNums.push(wellNums[w] % this.numCols);
        }
        return colNums;
    },
    asDataTable: function() {
        var wells = [];
        for(var w=0, len=this.wells.length; w<len; w++) {
            wells.push([
               this.wellNumToName(w, true),
               util.filterObjectsAttr(this.wells[w].cellLine,
                                            pyHTS.state.cell_lines,
                                            "id", "name").toString().replace(/^-1$/, ""),
               $.map(this.wells[w].drugs, function(drug) {
                   return util.filterObjectsAttr(drug, pyHTS.state.drugs, "id", "name").toString().replace(/^-1$/, "None");
               }).join("<br>"),
               $.map(this.wells[w].doses, util.doseFormatter).join("<br>")
            ]);
        }
        return wells;
    },
    wellDataIsEmpty: function() {
        return this.allCellLinesEmpty() && this.allDrugsEmpty() && this.allDosesEmpty();
    },
    allCellLinesEmpty: function() {
        for(var w=0, len=this.wells.length; w<len; w++) {
            if(this.wells[w].cellLine != null) {
                return false;
            }
        }
        return true;
    },
    allDrugsEmpty: function() {
        for(var w=0, len=this.wells.length; w<len; w++) {
            var well = this.wells[w];
            if(well.drugs != null && well.drugs.length > 0) {
                return false;
            }
        }
        return true;
    },
    allDosesEmpty: function() {
        for(var w=0, len=this.wells.length; w<len; w++) {
            var well = this.wells[w];
            if(well.doses != null && well.doses.length > 0) {
                return false;
            }
        }
        return true;
    },
    readableWells: function(wellIds) {
        var wellIdsLen = wellIds.length;
        if(wellIds == null || wellIdsLen === 0) {
            return "No wells";
        } else if(wellIdsLen === 1) {
            return this.wellNumToName(wellIds[0]);
        }
        wellIds.sort(function(a,b){return a - b;});
        wellIds = util.unique(wellIds);

        var wellStrs = [],
            rowNums = this.wellNumsToRowNums(wellIds),
            colNums = this.wellNumsToColNums(wellIds),
            contigStart = wellIds[0];
        for(var w=0; w<wellIdsLen; w++) {
            if(colNums[w] != (colNums[w+1] - 1) ||
               rowNums[w] != rowNums[w+1] ||
               w === (wellIdsLen - 1)) {
                var wellStr = this.wellNumToName(contigStart);
                if ((w - wellIds.indexOf(contigStart)) > 0) {
                    wellStr += "\u2014" + this.colNumToName(colNums[w]);
                }
                wellStrs.push(wellStr);
                contigStart = wellIds[w + 1];
            }
        }
        return wellStrs.join(", ");
    },
    validate: function() {
        var wellsWithDrugButNotDose = [], wellsWithDoseButNotDrug = [],
            wellsWithDuplicateDrug = [], wellsWithDrugButNoCellLine = [],
            errors=[];

        for(var w=0, len=this.wells.length; w<len; w++) {
            var well = this.wells[w];

            var numDrugs = well.drugs == null ? 0 : well.drugs.length;
            var numDoses = well.doses == null ? 0 : well.doses.length;

            if(well.drugs == null && well.doses == null) {
                continue;
            }
            if(numDrugs > 0) {
                if(well.cellLine == null) {
                    wellsWithDrugButNoCellLine.push(w);
                }
                if(util.hasDuplicates(well.drugs)) {
                    wellsWithDuplicateDrug.push(w);
                }
            }

            if(numDrugs > numDoses) {
                wellsWithDrugButNotDose.push(w);
            } else if (numDrugs < numDoses) {
                wellsWithDoseButNotDrug.push(w);
            } else if (numDrugs > 0) {
                for(var pos = 0; pos < numDrugs; pos++) {
                    if(well.drugs[pos] == null && well.doses[pos] == null) {
                        continue;
                    }
                    if(well.drugs[pos] != null && well.doses[pos] == null) {
                        wellsWithDrugButNotDose.push(w);
                    }
                    if(well.drugs[pos] == null && well.doses[pos] != null) {
                        wellsWithDoseButNotDrug.push(w);
                    }
                }
            }
        }

        if(wellsWithDoseButNotDrug.length > 0) {
            errors.push("The following wells have one or more doses without" +
                " a drug: " + this.readableWells(wellsWithDoseButNotDrug));
        }
        if(wellsWithDrugButNotDose.length > 0) {
            errors.push("The following wells have one or more drugs without" +
                " a dose: " + this.readableWells(wellsWithDrugButNotDose));
        }
        if(wellsWithDuplicateDrug.length > 0) {
            errors.push("The following wells have the same drug more than" +
                " once: " + this.readableWells(wellsWithDuplicateDrug));
        }
        if(wellsWithDrugButNoCellLine.length > 0) {
            errors.push("The following wells have a drug defined but no" +
                " cell line: " + this.readableWells(wellsWithDrugButNoCellLine));
        }
        if(errors.length > 0) {
            return errors;
        }
        return false;
    }
};

var plate_designer = function () {
    var ui = require('./modules/ui'),
        util = require('./modules/util'),
        ajax = require('./modules/ajax');

    var NUM_CSS_UNIQUE_COLOURS = 25;

    $('#hts-apply-template-multiple').find('select').selectpicker({
        actionsBox: true,
        countSelectedText: function(n, N) {
            return n + ' of ' + N + ' plates selected';
        },
        selectedTextFormat: 'count > 1'
    }).on('changed.bs.select', function() {
        var $btn = $('#apply-template-multiple-btn');
        if($(this).selectpicker('val').length > 0) {
            $btn.removeClass('btn-default').addClass('btn-success');
        } else {
            $btn.removeClass('btn-success').addClass('btn-default');
        }
    });

    $('#apply-template-multiple-btn').click(function() {
        var $templateMultiple = $('#hts-apply-template-multiple');

        var tgtPlateIds = [];
        $templateMultiple.find('option:selected').each(function(i, ele){
            tgtPlateIds.push($(ele).data('id'));
        });

        if(tgtPlateIds.length == 0) {
            ui.okModal('No plates selected', 'Please select target ' +
                    'plates from the drop down list');
            return;
        }
        if(pyHTS.state.plateMap.wellDataIsEmpty()) {
            ui.okModal('Empty template', 'The template could not be ' +
                    'applied because it is empty');
            return;
        }

        ui.loadingModal.show('Applying template...');

        pyHTS.state.plateMap.applyTemplateTo = tgtPlateIds;
        pyHTS.state.plateMap.applyTemplateMode = $.inArray(pyHTS.state.currentView,
            ['overview', 'table']) != -1 ? 'all' : pyHTS.state.currentView;
        savePlate(null);
        delete pyHTS.state.plateMap.applyTemplateMode;
        delete pyHTS.state.plateMap.applyTemplateTo;
    });

    pyHTS.state.currentView = 'overview';

    window.onbeforeunload = function() {
      if(pyHTS.state.plateMap!=null && pyHTS.state.plateMap.unsaved_changes) {
          return 'The plate map has unsaved changes. Are you sure you want ' +
                  'to leave the page?';
      }
    };

    var createCellLine = function(name, successCallback) {
        $.ajax({type: 'POST',
                url: '/ajax/cellline/create',
                headers: { 'X-CSRFToken': pyHTS.state.csrfToken },
                data: {'name' : name},
                success: function(data) {
                    pyHTS.state.cell_lines = data.cellLines;
                    $('#cellline-typeahead').data('ttTypeahead').menu
                            .datasets[0].source =
                            util.substringMatcher(
                                    util.getAttributeFromObjects(
                                            pyHTS.state.cell_lines, 'name'
                                    ));
                    successCallback();
                },
                error: ajax.ajaxErrorCallback,
                dataType: 'json'});
    };

    var createDrug = function(name, successCallback) {
        $.ajax({type: 'POST',
                url: '/ajax/drug/create',
                headers: { 'X-CSRFToken': pyHTS.state.csrfToken },
                data: {'name' : name},
                success: function(data) {
                    pyHTS.state.drugs = data.drugs;
                    $('.hts-drug-typeahead.tt-input').data('ttTypeahead')
                            .menu.datasets[0].source =
                                util.substringMatcher(
                                        util.getAttributeFromObjects(
                                                pyHTS.state.drugs, 'name'
                                        ));
                    successCallback();
                },
                error: ajax.ajaxErrorCallback,
                dataType: 'json'});
    };

    // Plate selector
    $("#hts-plate-list").find("li").click(function(e) {
        e.preventDefault();

        // Load the plate map
        var plateId = $(this).data('id');
        var templateId = undefined;
        if(plateId == 'MASTER') {
            templateId = $(this).data('template');
        }
        setPlate(plateId, templateId);
    });

    var refreshViewAll = function() {
        var wellIds = [],
            tgtNumWells = pyHTS.state.plateMap.wells.length;
        for(var i=0; i<tgtNumWells; i++) {
            wellIds.push(i);
        }
        var selectedWells = $('#selectable-wells').find('.hts-well');
        selectedWells.removeClass('ui-selected');
        if(selectedWells.length > tgtNumWells) {
            // remove wells
            selectedWells.filter(':gt('+(tgtNumWells-1)+')').remove();

            $('#selectable-well-cols').find('li').filter(':gt(' +
                    (pyHTS.state.plateMap.numCols-1)+')').remove();

            $('#selectable-well-rows').find('li').filter(':gt' +
                    '('+(pyHTS.state.plateMap.numRows-1)+')')
                    .remove();

            selectedWells = $('#selectable-wells').find('.hts-well');
        } else if (selectedWells.length < tgtNumWells) {
            // add wells
            var lastWell = selectedWells.filter(':last');
            var selectableWells = $('#selectable-wells');
            for(var w=selectedWells.length; w<tgtNumWells; w++) {
                lastWell.clone().data('well', w).appendTo(selectableWells);
            }

            var selectableCols = $('#selectable-well-cols');
            var cols = selectableCols.find('li');
            var lastCol = cols.filter(':last');
            for(var c=cols.length; c<pyHTS.state.plateMap.numCols; c++) {
                lastCol.clone().data('col', c).text(c+1)
                       .appendTo(selectableCols);
            }

            var selectableRows = $('#selectable-well-rows');
            var rows = selectableRows.find('li');
            var lastRow = rows.filter(':last');
            for(var r=rows.length; r<pyHTS.state.plateMap.numRows; r++) {
                lastRow.clone().data('row', r)
                        .text(String.fromCharCode(65 + r))
                        .appendTo(selectableRows);
            }
        }

        setNumberDrugInputs(pyHTS.state.plateMap.maxDrugsDosesUsed());

        if($('#hts-well-table').hasClass('active')) {
            refreshDataTable();
        }

        // resize the wells
        var wellWidthPercent = (100 / (pyHTS.state.plateMap.numCols + 1)) + '%';
        $('.welllist').not('#selectable-well-rows').not('.well-legend')
                .find('li').css('width', wellWidthPercent)
                     .css('padding-bottom', wellWidthPercent);
        $('#selectable-well-rows').css('width', wellWidthPercent);

        // refresh the legend and well CSS classes
        refreshLegend(selectedWells, wellIds, 'cell-line');
        refreshLegend(selectedWells, wellIds, 'drug');
        refreshLegend(selectedWells, wellIds, 'dose');
    };

    var refreshLegend = function(selectedWells, wellIds, data_type) {
        var newLegendEntries,
            oldLegendEntriesDescriptor = data_type.replace(/-/g, '_') +
                's_used',
            oldLegendEntries = pyHTS.state[oldLegendEntriesDescriptor],
            i;

        if(data_type == 'cell-line') {
            newLegendEntries = pyHTS.state.plateMap.getUsedCellLines();
        } else if (data_type == 'drug') {
            newLegendEntries = pyHTS.state.plateMap.getUsedDrugs();
        } else if (data_type == 'dose') {
            newLegendEntries = pyHTS.state.plateMap.getUsedDoses();
        }
        //compare old with new (this could be done more efficiently - this
        //scans the arrays twice)
        var removed = util.arrayDiffPositions(oldLegendEntries,
                newLegendEntries),
            added = util.arrayDiffPositions(newLegendEntries,
                oldLegendEntries),
            removedLen = removed.length,
            addedLen = added.length;

        var $legendBlock = $('#legend-'+data_type+'s');
        $legendBlock.find('.well-legend').filter(function(i, ele) {
            return $.inArray($(ele).data('insertPos'), removed) !== -1;
        }).remove();
        for(i=0; i<removedLen; i++) {
            oldLegendEntries[removed[i]] = null;
        }

        if(addedLen > 0) {
            var $baseLegendItem = $('.well-legend').first();
        }
        for(i=0; i<addedLen; i++) {
            var arrayInsertPos = oldLegendEntries.length,
                unusedArrayPos = $.inArray(null, oldLegendEntries);
            if(unusedArrayPos >= 0) {
                //reuse a deleted legend colour
                arrayInsertPos = unusedArrayPos;
            }

            var newArrayEntry = newLegendEntries[added[i]];
            if($.isArray(newArrayEntry)) {
                newArrayEntry = newArrayEntry.slice();
            }
            oldLegendEntries[arrayInsertPos] = newArrayEntry;

            // Update the legend
            var n = arrayInsertPos % NUM_CSS_UNIQUE_COLOURS;
            var $lgnd = $baseLegendItem.clone().data('insertPos', arrayInsertPos);
            var legendText;
            if(data_type == 'cell-line') {
                legendText = util.filterObjectsAttr(newArrayEntry,
                        pyHTS.state.cell_lines, 'id', 'name');
            } else if(data_type == 'drug') {
                legendText = $.map(newArrayEntry, function(elem) {
                    return util.filterObjectsAttr(elem, pyHTS.state.drugs,
                            'id', 'name').toString().replace(/^-1$/, 'None');
                }).join(' & ');
            } else if(data_type == 'dose') {
                legendText = $.map(newArrayEntry, util.doseFormatter)
                        .join(' & ');
            }

            $lgnd.children('li').addClass('hts-'+data_type+'-'+n);
            $lgnd.find('.legend-label').text(legendText);
            $legendBlock.append($lgnd);
        }

        if(addedLen > 0 || removedLen > 0) {
            pyHTS.state[oldLegendEntriesDescriptor] = oldLegendEntries;
        }

        // Update the wells
        selectedWells.each(function(i, ele) {
            var well = pyHTS.state.plateMap.wells[wellIds[i]],
                $ele = $(ele),
                this_value,
                n;
            for(n = 0; n < NUM_CSS_UNIQUE_COLOURS; n++) {
                $ele.removeClass('hts-' + data_type + '-' + n);
            }
            if (data_type == "cell-line") {
                this_value = well.cellLine;
            } else if (data_type == "drug") {
                this_value = well.drugs;
            } else if (data_type == "dose") {
                this_value = well.doses;
            }
            if(this_value == null || this_value.length == 0) {
                $ele.removeClass('hts-' + data_type);
            } else {
                var loc = util.indexOf(this_value,
                        pyHTS.state[oldLegendEntriesDescriptor]);
                if(loc >= 0) {
                    n = loc % NUM_CSS_UNIQUE_COLOURS;
                    $ele.addClass('hts-' + data_type + '-' + n)
                            .addClass('hts-' + data_type);
                }
            }
        });
    };

    var createTypeahead = function($input, dataSource) {
        $($input).typeahead({
                    hint: true,
                    highlight: true,
                    minLength: 1
                },
                {
                    source: util.substringMatcher(dataSource)
                }).keyup(function (e) {
            if (e.which == 13) {
                submitToWells(this);
            }
        });
    };
    createTypeahead('#cellline-typeahead',
            util.getAttributeFromObjects(pyHTS.state.cell_lines, 'name'));

    var submitToWells = function(caller) {
        // called when enter is pressed

        //non-callback validation
        var $selectedWells = $('#selectable-wells').find('.ui-selected');
        if ($selectedWells.length === 0) {
            ui.okModal('Error', 'Please select some wells first',
                function () {
                    $(caller).focus();
                });
            return;
        }

        var allDosesValid = true;
        var doses = [];
        var $doseInputs = $('.hts-dose-input');
        $doseInputs.each(function() {
            var valTxt = $(this).val();
            var val = parseFloat(valTxt);
            if (valTxt != '' && (isNaN(val) || val < 0)) {
                if(allDosesValid) {
                    ui.okModal('Error', 'Dose must be numeric and ' +
                            'non-negative', function () {
                        $(obj).focus();
                    });
                }
                allDosesValid = false;
            } else {
                if(valTxt == '') {
                    doses.push(null);
                } else {
                    var dose_multiplier = $(this).parent('.input-group')
                            .find('.hts-active-dose-unit').data('dose');
                    doses.push(val * parseFloat(dose_multiplier));
                }
            }
        });

        if(!allDosesValid) {
            return;
        }

        // Check that the cell line exists
        var createEntityCallback = function() {
            $(caller).focus();
            submitToWells(caller);
        };
        var $cellLineTypeahead = $('#cellline-typeahead');
        var cl = $cellLineTypeahead.typeahead('val');
        var cl_id = util.filterObjectsAttr(cl, pyHTS.state.cell_lines,
                'name', 'id');
        if(cl != '' && cl_id == -1) {
            ui.okCancelModal('Create cell line',
                    'Cell line "' + cl + '" ' +
                'was not found. Create it?<br /><br />If you meant to ' +
                'autocomplete a suggestion use <kbd>Tab</kbd> instead.',
                function() { createCellLine(cl, createEntityCallback); },
                function() { $('#cellline-typeahead').focus(); });
            return;
        }

        // Check all drugs exist
        var $drugTypeaheads = $('.hts-drug-typeahead').not('.tt-hint');
        var drugIds = [];
        for(var i=0, len=$drugTypeaheads.length; i<len; i++) {
            var drug = $($drugTypeaheads[i]).typeahead('val');
            var dr_id = util.filterObjectsAttr(drug, pyHTS.state.drugs,
                    'name', 'id');
            drugIds.push(dr_id);
            if(drug != '' && dr_id == -1) {
                ui.okCancelModal('Create drug',
                'Drug "' + drug + '" was not found. Create it?<br /><br />'
                + 'If you meant to autocomplate a suggestion use ' +
                '<kbd>Tab</kbd> instead.',
                function() { createDrug(drug, createEntityCallback); },
                function() { $($drugTypeaheads[i]).focus(); });
                return;
            }
        }
        var drugIdsLen = drugIds.length;

        // Validations succeeded, apply attributes to wells
        var wellIds = [];
        $.each($selectedWells, function(i, well) {
            var wellId = $(well).data('well');
            wellIds.push(wellId);
            if(cl_id != -1) {
                pyHTS.state.plateMap.wells[wellId].setCellLine(cl_id);
            }
            for(var j=0; j<drugIdsLen; j++) {
                if(drugIds[j] != -1) {
                    pyHTS.state.plateMap.wells[wellId].setDrug(drugIds[j], j);
                }
                if(doses[j] != null) {
                    pyHTS.state.plateMap.wells[wellId].setDose(doses[j], j);
                }
            }
        });

        // Refresh legend
        refreshLegend($selectedWells, wellIds, 'cell-line');
        refreshLegend($selectedWells, wellIds, 'drug');
        refreshLegend($selectedWells, wellIds, 'dose');

        // Show finish button if appropriate
        if(pyHTS.state.savedPlates.length == (pyHTS.state.plates.length - 1)
           && ($.inArray(pyHTS.state.plateMap.plateId, pyHTS.state.savedPlates) == -1)) {
            $('#hts-finish-platemap').show();
        }

        // Clear inputs and lose focus
        $cellLineTypeahead.typeahead('val', '');
        $drugTypeaheads.typeahead('val', '');
        $doseInputs.val('');

        // Deselect wells or apply auto-stepper
        var newWellIds;
        switch (pyHTS.state.stepperMode) {
            case 'off':
                $selectedWells.removeClass('ui-selected');
                break;
            case 'down-sel':
                try {
                    newWellIds = pyHTS.state.plateMap.moveSelectionDownBy(wellIds,
                            pyHTS.state.plateMap.selectionHeight(wellIds));
                } catch(e) {
                    autoStepperOutOfBounds();
                }
                break;
            case 'down-1':
                try {
                    newWellIds = pyHTS.state.plateMap.moveSelectionDownBy(wellIds, 1);
                } catch(e) {
                    autoStepperOutOfBounds();
                }
                break;
            case 'right-sel':
                try {
                    newWellIds = pyHTS.state.plateMap.moveSelectionRightBy(wellIds,
                            pyHTS.state.plateMap.selectionWidth(wellIds));
                } catch(e) {
                    autoStepperOutOfBounds();
                }
                break;
            case 'right-1':
                try {
                    newWellIds = pyHTS.state.plateMap.moveSelectionRightBy(wellIds, 1);
                } catch(e) {
                    autoStepperOutOfBounds();
                }
                break;
        }

        if(newWellIds == null) {
            $(caller).blur();
        } else {
            selectWells(newWellIds);
        }
    };

    var clearAllInputs = function() {
        $('#cellline-typeahead,.hts-drug-typeahead').not('.tt-hint')
            .typeahead('val', '');
        $('.hts-dose-input').val('');
    };

    var autoStepperOutOfBounds = function() {
        ui.okModal('Auto-step error', 'The auto-stepper reached the' +
                ' edge of the plate. Please adjust your well ' +
                'selection manually to continue.');
    };

    var activateDrugInputs = function() {
        createTypeahead('.hts-drug-typeahead:last',
                util.getAttributeFromObjects(pyHTS.state.drugs, 'name'));

        $('.hts-dose-input').last().keyup(function (e) {
            if (e.which == 13) {
                submitToWells(this);
            }
        });

        $('.hts-dose-select').find('li').click(function (e) {
            e.preventDefault();
            $(this).closest('.input-group-btn').find('.hts-active-dose-unit')
                    .data('dose', $(this).data('dose')).text($(this).text());
        });
    };
    activateDrugInputs();

    var addDrugInput = function() {
        var orig_el = $('.hts-drug-entry').last(),
            new_el = orig_el.clone(true, false);
        new_el.data().drugNum++;
        new_el.find('.hts-drug-num').last().text(function (i, val) {
            return +val + 1;
        });
        new_el.insertAfter(orig_el);
        $('.hts-drug-num').show();
        activateDrugInputs();
    };

    var removeDrugInput = function() {
        var $drugEntries = $('.hts-drug-entry');
        var numEntries = $drugEntries.length;
        if(numEntries > 1) {
            $drugEntries.filter(':last').remove();
        }
        if(numEntries == 2) {
            $('.hts-drug-num').hide();
        }
    };

    var setNumberDrugInputs = function(numInputs) {
        var requiredInputs = numInputs - $('.hts-drug-entry').length;
        for(var i=0, len=Math.abs(requiredInputs); i<len; i++) {
            if (requiredInputs < 0) {
                removeDrugInput();
            } else if (requiredInputs > 0) {
                addDrugInput();
            }
        }
    };

    $('#hts-add-drug').click(function (e) {
        addDrugInput();
    });

    var refreshDataTable = function() {
        $('#hts-well-table-view').find('table').DataTable({
            data: pyHTS.state.plateMap.asDataTable(),
            columns: [
                {title: 'Well'},
                {title: 'Cell Line'},
                {title: 'Drugs'},
                {title: 'Doses'}
            ],
            destroy: true,
            paging: false,
            columnDefs: [
                {type: 'doses',
                 targets: 3}
            ]
        });
    };

    // Change plate view
    $('#hts-well-overview').click(function(e) { setWellView(e,'overview'); });
    $('#hts-well-celllines').click(function(e) { setWellView(e,'celllines');});
    $('#hts-well-drugs').click(function(e) { setWellView(e,'drugs'); });
    $('#hts-well-doses').click(function(e) { setWellView(e,'doses'); });
    $('#hts-well-table').click(function(e) {
        // deselect any selected wells
        $('.hts-well.ui-selected').removeClass('ui-selected');

        var $loadingIndicator = $('#hts-well-table-view')
                .find('.loading-indicator').show();

        setWellView(e, 'table');
        refreshDataTable();

        $loadingIndicator.hide();
    });

    var viewStrings = {celllines: 'cell lines', drugs: 'drugs', doses:
        'doses', overview: '', table: ''};

    var setWellView = function(e, view) {
        e.preventDefault();
        if(view == 'table') {
            $('#hts-well-table-view').show();
            $('#hts-well-plate').hide();
        } else {
            $('#hts-well-table-view').hide();
            $('#hts-well-plate').show();
        }
        pyHTS.state.currentView = view;
        $('.view-str').text(viewStrings[view]);

        clearAllInputs();

        if(pyHTS.state.editable) {
            if (view == 'overview' || view == 'celllines') {
                $('#cellline-typeahead').prop('disabled', false).css
                ('background-color', 'transparent');
            } else {
                $('#cellline-typeahead').prop('disabled', true).css
                ('background-color', '');
            }

            if (view == 'overview' || view == 'drugs') {
                $('.hts-drug-typeahead').prop('disabled', false).css
                ('background-color', 'transparent');
            } else {
                $('.hts-drug-typeahead').prop('disabled', true).css
                ('background-color', '');
            }

            if (view == 'overview' || view == 'doses') {
                $('.hts-dose-input').prop('disabled', false);
            } else {
                $('.hts-dose-input').prop('disabled', true);
            }
        }

        $('#hts-well-nav').find('li').removeClass('active');
        $('#hts-well-'+view).addClass('active');
        $('#selectable-wells,#hts-legend-container')
                .removeClass('hts-overview hts-celllines hts-drugs hts-doses' +
                        ' hts-table')
                .addClass('hts-'+view);
    };

    $.extend( $.fn.dataTableExt.oSort, util.doseSorter );

    // Well selection
    var selectWells = function(wellIds) {
        var $wells = $('#selectable-wells').find('.hts-well');
        // deselect any existing wells
        $wells.removeClass('ui-selected');

        // select new selection and update annotation panel
        for(var w=0, len=wellIds.length; w<len; w++){
            $wells.eq(wellIds[w]).addClass('ui-selected');
        }

        updateInputsWithWellData();
    };

    var moveSelectionBy = function(amount, isRowDirection) {
        var $selectedWells = $('#selectable-wells').find('.ui-selected');
        var wellIds = [], newWellIds;
        $.each($selectedWells, function(i, well) {
            wellIds.push($(well).data('well'));
        });
        try {
            newWellIds = pyHTS.state.plateMap.moveSelectionBy(wellIds, amount,
                    isRowDirection);
        } catch (e) {
            //ignore
        }
        if(newWellIds != null) {
            selectWells(newWellIds);
        }
    };

    $('#hts-move-selection').find('button').click(function() {
        moveSelectionBy($(this).data('move-by'), $(this).data('move-row-dir'));
    });

    var updateInputsWithWellData = function() {
        var i,
            cellLines = [], drugs = [], doses = [],
            $cellLineTypeahead = $('#cellline-typeahead'),
            $drugTypeahead = $('.hts-drug-typeahead').not('.tt-hint'),
            numDrugs = $drugTypeahead.length,
            $doseInput = $('.hts-dose-input'),
            $doseUnits = $('.hts-active-dose-unit'),
            numDoses = $doseInput.length;

        for(i=0; i<numDrugs; i++) {
            drugs.push([]);
        }

        for(i=0; i<numDoses; i++) {
            doses.push([]);
        }

        $('#selectable-wells').find('.ui-selected').each(function(i, ele){
            var well = pyHTS.state.plateMap.wells[$(ele).data('well')];
            if($.inArray(well.cellLine, cellLines) == -1) {
                cellLines.push(well.cellLine);
            }
            for(i=0; i<numDrugs; i++) {
                if(well.drugs && $.inArray(well.drugs[i], drugs[i]) == -1) {
                    drugs[i].push(well.drugs[i]);
                }
            }
            for(i=0; i<numDoses; i++) {
                if(well.doses && $.inArray(well.doses[i], doses[i]) == -1) {
                    doses[i].push(well.doses[i]);
                }
            }
        });

        $cellLineTypeahead.typeahead('val', '');
        if(cellLines.length == 1 && cellLines[0] != null) {
            $cellLineTypeahead.typeahead('val', util
                    .filterObjectsAttr(cellLines[0], pyHTS.state.cell_lines,
                            'id', 'name'));
        } else if(cellLines.length > 1) {
            $cellLineTypeahead.attr('placeholder', '[Multiple]');
        }

        $drugTypeahead.typeahead('val', '');
        for(i=0; i<numDrugs; i++) {
            if(drugs[i].length == 1 && drugs[i][0] != null) {
                $drugTypeahead.eq(i).typeahead('val',
                        util.filterObjectsAttr(drugs[i][0], pyHTS.state.drugs,
                            'id', 'name'));
            } else if(drugs[i].length > 1) {
                $drugTypeahead.eq(i).attr('placeholder', '[Multiple]');
            }
        }

        $doseInput.val('');
        for(i=0; i<numDoses; i++) {
            if(doses[i].length == 1 && doses[i][0] != null) {
                var doseSplit = util.doseSplitter(doses[i][0]);
                $doseInput.eq(i).val(doseSplit[0]);
                $doseUnits.eq(i).data('dose', doseSplit[1]).text(doseSplit[2]);
            } else if(doses[i].length > 1) {
                $doseInput.eq(i).attr('placeholder', '[Multiple]');
            }
        }
    };

    if(pyHTS.state.editableFlag) {
        $("#well-all").click(function () {
            if ($('.hts-well.ui-selected').length) {
                $('#well-all,.hts-well').removeClass('ui-selected');
            } else {
                $('#well-all,.hts-well').addClass('ui-selected');
                updateInputsWithWellData();
            }
            pyHTS.state.last_edited = 'all';
        });

        $('#selectable-well-rows').selectable({
            start: function (event, ui) {
                if (pyHTS.state.last_edited != 'row')
                    $('.hts-well').removeClass('ui-selected');
                pyHTS.state.last_edited = 'row';
            },
            selecting: function (event, ui) {
                var rowNo = $(ui.selecting).data('row');
                $('#selectable-wells').find('li').filter(function () {
                    return $(this).data('well') >
                        ((pyHTS.state.plateMap.numCols * (rowNo - 1)) - 1)
                        && $(this).data('well') < (pyHTS.state.plateMap.numCols * rowNo);
                }).addClass('ui-selected');
            },
            unselecting: function (event, ui) {
                var rowNo = $(ui.unselecting).data('row');
                $('#selectable-wells').find('li').filter(function () {
                    return $(this).data('well') >
                        ((pyHTS.state.plateMap.numCols * (rowNo - 1)) - 1)
                        && $(this).data('well') < (pyHTS.state.plateMap.numCols * rowNo);
                }).removeClass('ui-selected');
            },
            stop: updateInputsWithWellData
        });

        $('#selectable-well-cols').selectable({
            start: function (event, ui) {
                if (pyHTS.state.last_edited != 'col')
                    $('.hts-well').removeClass('ui-selected');
                pyHTS.state.last_edited = 'col';
            },
            selecting: function (event, ui) {
                var colNo = $(ui.selecting).data('col');
                $('#selectable-wells').find('li').filter(function () {
                    return $(this).data('well') % pyHTS.state.plateMap.numCols ==
                        (colNo - 1);
                }).addClass('ui-selected');
            },
            unselecting: function (event, ui) {
                var colNo = $(ui.unselecting).data('col');
                $('#selectable-wells').find('li').filter(function () {
                    return $(this).data('well') % pyHTS.state.plateMap.numCols ==
                        (colNo - 1);
                }).removeClass('ui-selected');
            },
            stop: updateInputsWithWellData
        });

        $("#selectable-wells").selectable({
            start: function () {
                pyHTS.state.last_edited = 'cell';
            },
            stop: updateInputsWithWellData
        });
    }

    $('#hts-apply-annotation').click(function() {
        submitToWells(this);
    });

    $('#hts-clear-annotation').click(function() {
        var selectedWells = $('#selectable-wells').find('.ui-selected');

        if (selectedWells.length === 0) {
            ui.okModal('Error', 'Please select some wells first');
            return;
        }

        $.each(selectedWells, function(i, well) {
            var w = pyHTS.state.plateMap.wells[$(well).data('well')];
            if(pyHTS.state.currentView == 'celllines') {
                w.setCellLine(null);
            } else if(pyHTS.state.currentView == 'drugs') {
                w.setDrug(null, null);
            } else if(pyHTS.state.currentView == 'doses') {
                w.setDose(null, null);
            } else {
                w.clear();
            }
        });

        clearAllInputs();
        refreshViewAll();
    });

    var applyTemplateToCurrent = function() {
        if($('#hts-current-plate').data('id') == 'MASTER') {
            ui.okModal('Error', 'Cannot apply template to itself');
            return;
        }
        if(pyHTS.state.currentView == 'celllines' && !pyHTS.state.plateMap
                .allCellLinesEmpty() ||
                pyHTS.state.currentView == 'drugs' && !pyHTS.state.plateMap
                    .allDrugsEmpty() ||
                pyHTS.state.currentView == 'doses' && !pyHTS.state.plateMap
                    .allDosesEmpty() ||
                !$.inArray(pyHTS.state.currentView, ['celllines', 'drugs',
                        'doses']) && !pyHTS.state.plateMap.wellDataIsEmpty()) {
            ui.okModal('Plate map not empty', 'Cannot apply template ' +
                    'data because this plate map is not empty.');
            return;
        }
        var templateId = pyHTS.state.plateMap.numCols + 'x' + pyHTS.state.plateMap.numRows;
        if(!pyHTS.state.plateMapTemplates[templateId].unsaved_changes) {
            ui.okModal('Template is empty', 'The template is empty, ' +
                    'nothing to apply');
            return;
        }
        populateWellDataFromTemplate(pyHTS.state.plateMap.wells, templateId);
        pyHTS.state.plateMap.unsaved_changes = true;
        refreshViewAll();
    };

    $('#hts-apply-template').click(function() {
        applyTemplateToCurrent();
    });

    // Auto-stepper
    pyHTS.state.stepperMode = 'off';
    $('#hts-autostepper-div').find('li').click(function(e) {
        e.preventDefault();
        pyHTS.state.stepperMode = $(this).data('mode');
        $('#hts-autostepper-mode').text($(this).text());
    });

    // Mouseovers
    $('#selectable-wells').find('.hts-well').mouseenter(function(e) {
        var well = $(this).data('well'),
            wellData = pyHTS.state.plateMap.wells[well],
            i,
            len;
        if(wellData == null) return;
        $('#cellline-typeahead').attr('placeholder',
                wellData.cellLine == null ? '' :
                util.filterObjectsAttr(wellData.cellLine,
                                            pyHTS.state.cell_lines,
                                            'id', 'name'));
        var $drugTypeaheads = $('.hts-drug-typeahead').not('.tt-hint');
        $drugTypeaheads.attr('placeholder', '');
        if(wellData.drugs != null) {
            for(i=0, len=wellData.drugs.length; i<len; i++) {
                if(wellData.drugs[i] == null) continue;
                $drugTypeaheads.eq(i).attr('placeholder',
                util.filterObjectsAttr(wellData.drugs[i], pyHTS.state.drugs,
                        'id', 'name'));
            }
        }
        var $doseInputs = $('.hts-dose-input');
        $doseInputs.attr('placeholder', '');
        if(wellData.doses != null) {
            for(i=0, len=wellData.doses.length; i<len; i++) {
                if(wellData.doses[i] == null) continue;
                $doseInputs.eq(i).attr('placeholder',
                        util.doseFormatter(wellData.doses[i]));
            }
        }
    }).mouseleave(function() {
        $('#cellline-typeahead').attr('placeholder', 'Cell line');
        $('.hts-drug-typeahead').not('.tt-hint').attr('placeholder', 'Drug name');
        $('.hts-dose-input').attr('placeholder', 'Dose');
    });

    var populateWellDataFromTemplate = function(wellData, templateId) {
        var templateWells = pyHTS.state.plateMapTemplates[templateId].wells;
        for(var w=0, len=wellData.length; w<len; w++) {
            if($.inArray(pyHTS.state.currentView, ['drugs', 'doses']) == -1) {
                wellData[w].cellLine = templateWells[w].cellLine;
            }
            if($.inArray(pyHTS.state.currentView, ['celllines', 'doses']) ==
                -1) {
                wellData[w].drugs = templateWells[w].drugs != null ?
                    templateWells[w].drugs.slice() : null;
            }
            if($.inArray(pyHTS.state.currentView, ['celllines', 'drugs']) ==
                -1) {
                wellData[w].doses = templateWells[w].doses != null ?
                    templateWells[w].doses.slice() : null;
            }
        }
    };

    // Loading and saving plates
    var plateLoadedCallback = function (data) {
        if(pyHTS.state.completeFlag) {
            pyHTS.state.plateMap.unsaved_changes = false;
            window.location = pyHTS.state.redirectURL;
            return;
        }
        if(data.success) {
            if(data.templateAppliedTo) {
                ui.okModal('Template applied', 'Template was ' +
                        'successfully applied');
                $('#hts-apply-template-multiple').find('select')
                        .selectpicker('deselectAll');
            }
            if(data.savedPlateId) {
                if ($.inArray(data.savedPlateId, pyHTS.state.savedPlates) == -1) {
                    pyHTS.state.savedPlates.push(data.savedPlateId);
                    var plateInDropdown = $('#hts-plate-list')
                            .find('li[data-id=' + data.savedPlateId + ']')
                            .find('a');
                    plateInDropdown.html(ui.glyphiconHtml('ok') +
                            plateInDropdown.html());
                }
            }
            if(data.plateMap) {
                if(pyHTS.state.savedPlates.length == pyHTS.state.plates.length
                      || (pyHTS.state.savedPlates.length == (pyHTS.state.plates.length - 1)
                      && $.inArray(data.plateMap.plateId, pyHTS.state.savedPlates)
                        == -1)) {
                    $('#hts-finish-platemap').show();
                }
                pyHTS.state.plateMap = new PlateMap(
                        data.plateMap.plateId,
                        data.plateMap.numRows,
                        data.plateMap.numCols,
                        data.plateMap.wells
                );
                refreshViewAll();
            }
        }
    };

    var loadPlate = function(plateId) {
        $.ajax({
            url: '/ajax/plate/load/'+plateId,
            type: 'GET',
            success: plateLoadedCallback,
            error: ajax.ajaxErrorCallback,
            complete: function() {
                ui.loadingModal.hide();
            }
        });
    };

    var savePlate = function(nextPlateToLoad) {
        pyHTS.state.plateMap.loadNext = nextPlateToLoad;
        $.ajax({
            url: '/ajax/plate/save',
            data: JSON.stringify(pyHTS.state.plateMap),
            type: 'POST',
            headers: { 'X-CSRFToken': pyHTS.state.csrfToken },
            success: plateLoadedCallback,
            error: ajax.ajaxErrorCallback,
            complete: function() {
                ui.loadingModal.hide();
            }
        });
        delete pyHTS.state.plateMap.loadNext;
    };

    var validatePlate = function(retryCallback) {
        var plateErrors = pyHTS.state.plateMap.validate();
        if (plateErrors) {
            ui.okCancelModal('Error validating plate map',
                '<ul><li>' + plateErrors.join("</li><li>") + '</li></ul>',
                null,
                retryCallback,
                null,
                'Go back',
                'Ignore errors'
            );
            return false;
        }
        return true;
    };

    var setPlate = function(plateId, templateId, noValidation) {
        var $currentPlate = $('#hts-current-plate'),
            $plateList = $("#hts-plate-list"),
            currentId = $currentPlate.data('id');

        if(currentId != 'MASTER') {
            if(noValidation !== true) {
                var validated = validatePlate(function () {
                    setPlate(plateId, templateId, true)
                });
                if (!validated) {
                    return false;
                }
            }
            if (plateId == 'MASTER') {
                $('#hts-select-plate').addClass('btn-success');
            }
        } else {
            // currently on a master template
            if(pyHTS.state.plateMap.wellDataIsEmpty()) {
                pyHTS.state.plateMap.unsaved_changes = false;
            }
            if(plateId != 'MASTER') {
                $('#hts-select-plate').removeClass('btn-success');
            }
        }

        if(plateId != 'MASTER') {
            ui.loadingModal.show();
        }

        // save current data if necessary
        if (currentId != 'MASTER' && pyHTS.state.plateMap.unsaved_changes) {
            savePlate(plateId == 'MASTER' ? null : plateId);
        } else if (plateId != 'MASTER') {
            loadPlate(plateId);
        }

        // update the dropdown
        var $plateEl = $plateList.find('li[data-id='+plateId+']');
        if(plateId == 'MASTER') {
            $plateEl = $plateEl.filter('[data-template='+templateId+']');
        }
        var plateName = $plateEl.find('a').text();
        $currentPlate.data('id', plateId).text(plateName);
        $plateList.find('li').removeClass('active');
        $plateEl.addClass('active');
        // update the UI
        if (plateId == 'MASTER') {
            pyHTS.state.plateMap = pyHTS.state.plateMapTemplates[templateId];
            refreshViewAll();
            $('#hts-prev-dataset,#hts-next-dataset').hide();
            $('#hts-apply-template').hide();
            $('#hts-apply-template-multiple').show();
        } else {
            $('#hts-apply-template').show();
            $('#hts-apply-template-multiple').hide();
            if (prevPlatePos() != null) {
                $('#hts-prev-dataset').show();
            } else {
                $('#hts-prev-dataset').hide();
            }
            if (nextPlatePos() != null) {
                $('#hts-next-dataset').show();
            } else {
                $('#hts-next-dataset').hide();
            }
        }

        if (pyHTS.state.savedPlates.length == (pyHTS.state.plates.length - 1)
                   && $.inArray(plateId, pyHTS.state.savedPlates) != -1) {
            $('#hts-finish-platemap').hide();
        }
    };

    var currentPlatePos = function() {
        return $.inArray($('#hts-current-plate').data('id'), pyHTS.state.plates);
    };

    var prevPlatePos = function() {
        var pos = currentPlatePos();
        return pos > 0 ? pyHTS.state.plates[pos - 1] : null;
    };

    var nextPlatePos = function() {
        var pos = currentPlatePos();
        return pos < (pyHTS.state.plates.length - 1) ? pyHTS.state.plates[pos + 1] : null;
    };

    $('#hts-next-dataset').click(function(e) {
        setPlate(nextPlatePos());
    });

    $('#hts-prev-dataset').click(function(e) {
        setPlate(prevPlatePos());
    });

    $('#hts-finish-platemap').click(function(e) {
        pyHTS.state.completeFlag = true;
        if ($('#hts-current-plate').data('id') != 'MASTER' &&
                pyHTS.state.plateMap.unsaved_changes) {
            if(!validatePlate()) {
                pyHTS.state.completeFlag = false;
                return;
            }
            ui.loadingModal.show();
            savePlate(null);
        } else {
            plateLoadedCallback();
        }
    });

    if(pyHTS.state.plates.length > 0) {
        setPlate(pyHTS.state.plates[0]);
    }
};
module.exports = {
    activate: plate_designer,
    PlateMap: PlateMap
};
