"use strict";

var ui = require('./modules/ui'),
    util = require('./modules/util'),
    ajax = require('./modules/ajax');

var Well = function(well) {
    if(well === undefined) {
        this.cellLine = null;
        this.drugs = [];
        this.doses = [];
        this.dipRate = null;
    } else {
        this.cellLine = well.cellLine;
        this.drugs = well.drugs;
        this.doses = well.doses;
        this.dipRate = well.dipRate;
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
    },
    toStringFormat: function() {
        var well = $.extend(true, {}, this);
        if(well.cellLine !== null) {
            well.cellLine = util.filterObjectsAttr(well.cellLine, pyHTS.state.cell_lines, "id", "name");
        }
        if(well.drugs !== null) {
            var numDrugs = well.drugs.length;
            for(var drIdx = 0; drIdx < numDrugs; drIdx++) {
                well.drugs[drIdx] = well.drugs[drIdx] == null ? null :
                    util.filterObjectsAttr(well.drugs[drIdx], pyHTS.state.drugs, "id", "name");
            }
        }
        return well;
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
    wellsWithNumDrugsDosesUsed: function(numDrugsDoses) {
        var wells = [];
        for(var i=0, len=this.wells.length; i<len; i++) {
            if((this.wells[i].drugs != null && this.wells[i].drugs.length >= numDrugsDoses)
                || (this.wells[i].doses != null && this.wells[i].doses.length >= numDrugsDoses)) {
                wells.push(i);
            }
        }
        return wells;
    },
    wellNumToName: function(wellNum, padded) {
        return this.rowNumToName(Math.floor(wellNum / this.numCols)) +
               this.colNumToName(wellNum % this.numCols, padded);
    },
    rowNumToName: function(rowNum) {
        if(rowNum < 26) {
            return String.fromCharCode(65 + rowNum);
        } else {
            return String.fromCharCode(64 + Math.floor(rowNum / 26)) +
                String.fromCharCode(65 + rowNum % 26);
        }
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
                {"id": w, "name": this.wellNumToName(w, true)},
               util.filterObjectsAttr(this.wells[w].cellLine,
                                            pyHTS.state.cell_lines,
                                            "id", "name").toString().replace(/^-1$/, ""),
               $.map(this.wells[w].drugs, function(drug) {
                   return util.filterObjectsAttr(drug, pyHTS.state.drugs, "id", "name").toString().replace(/^-1$/, "None");
               }).join("<br>"),
               $.map(this.wells[w].doses, util.doseFormatter).join("<br>"),
               this.wells[w].dipRate === null ? null : this.wells[w].dipRate.toFixed(10)
            ]);
        }
        return wells;
    },
    toCSV: function(sep) {
        var i;
        var numDrugColumns = this.maxDrugsDosesUsed();
        var header = ['well', 'cell.line'];
        for(i=0; i < numDrugColumns; i++) {
            var drugName = 'drug'+(i+1);
            header.push(drugName);
            header.push(drugName+'.conc');
            header.push(drugName+'.units')
        }
        var wells = [header.join(sep)];
        for (var w=0, len=this.wells.length; w < len; w++) {
            var elements = [this.wellNumToName(w, true)];
            var well = this.wells[w];
            if (well.cellLine === null) {
                elements.push('');
            } else {
                elements.push(util.filterObjectsAttr(well.cellLine, pyHTS.state.cell_lines, 'id', 'name'));
            }
            for (i = 0; i < numDrugColumns; i++) {
                if (well.drugs !== null && well.drugs.length > i && well.drugs[i] != null) {
                    elements.push(util.filterObjectsAttr(well.drugs[i], pyHTS.state.drugs, 'id', 'name'));
                } else {
                    elements.push('');
                }
                if (well.doses !== null && well.doses.length > i) {
                    elements.push(well.doses[i]);
                } else {
                    elements.push('');
                }
                // Units are always molar
                elements.push('M');
            }
            wells.push(elements.join(sep))
        }
        return wells.join('\n');
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
        if (!this.unsaved_changes) {
            return true;
        }
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
        return true;
    }
};

var check_loading = function() {
    if(pyHTS.state.plates.length > 0 && pyHTS.state.plates[0] !== "MASTER") {
        ui.loadingModal.show();
    }
};

var plate_designer = function () {
    var setWellSizes = function() {
        var numWells = pyHTS.state.plateMap.wells.length;
        var $plate = $('#hts-well-plate-inner');
        if (numWells === 96) {
            $plate.removeClass("plate1536 plate384").addClass("plate96");
        } else if (numWells === 384) {
            $plate.removeClass("plate1536 plate96").addClass("plate384");
        } else if (numWells === 1536) {
            $plate.removeClass("plate384 plate96").addClass("plate1536");
        } else {
            // Set well size using javascript
            $plate.toggleClass('plate1536', numWells > 384);
            var wellWidthPercent = (100 / (pyHTS.state.plateMap.numCols + 1)) + '%';
            $('.welllist').not('#selectable-well-rows').not('.well-legend')
                .find('li').css('width', wellWidthPercent)
                .css('padding-bottom', wellWidthPercent);
            $('#selectable-well-rows').css('width', wellWidthPercent);
        }
    };
    if(pyHTS.state.plateMap.wells.length !== 384) {
        // triggers a repaint, so do this first
        setWellSizes();
    }
    var NUM_CSS_UNIQUE_COLOURS = 25;
    var $cellLineTypeahead = $('#cellline-typeahead'),
        $drugTypeaheads = $('.hts-drug-typeahead').not('.tt-hint'),
        $doseInputs = $('.hts-dose-input'),
        $doseUnits = $('.hts-dose-select'),
        $dipBox = $('#hts-dip-box');

    $('#hts-apply-template-multiple').find('select').selectpicker({
        actionsBox: true,
        iconBase: "fa",
        tickIcon: "fa-check",
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

        if(tgtPlateIds.length === 0) {
            ui.okModal({
                title: "No plates selected",
                text: "Please select target plates from the drop down list"
            });
            return;
        }
        if(pyHTS.state.plateMap.wellDataIsEmpty()) {
            ui.okModal({
                title: "Empty template",
                text: "The template could not be applied because it is empty"
            });
            return;
        }

        ui.loadingModal.show();

        pyHTS.state.plateMap.applyTemplateTo = tgtPlateIds;
        pyHTS.state.plateMap.applyTemplateMode = $.inArray(pyHTS.state.currentView,
            ['overview', 'table']) !== -1 ? 'all' : pyHTS.state.currentView;
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
        if(pyHTS.state.plateMapperLocalOnly === true) {
            var ids = util.getAttributeFromObjects(pyHTS.state.cell_lines, "id");
            var newId = Math.max.apply(null, ids) + 1;
            pyHTS.state.cell_lines.push({'id': newId, 'name': name});
            $('#cellline-typeahead').data('ttTypeahead').menu
                        .datasets[0].source =
                        util.substringMatcher(
                            util.getAttributeFromObjects(
                                pyHTS.state.cell_lines, 'name'
                            ));
            successCallback();
        } else {
            $.ajax({
                type: 'POST',
                url: ajax.url("create_cellline"),
                headers: {'X-CSRFToken': ajax.getCsrfToken()},
                data: {'name': name},
                success: function (data) {
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
                dataType: 'json'
            });
        }
    };

    var createDrug = function(name, successCallback) {
        if(pyHTS.state.plateMapperLocalOnly === true) {
            var ids = util.getAttributeFromObjects(pyHTS.state.drugs, "id");
            var newId = Math.max.apply(null, ids) + 1;
            pyHTS.state.drugs.push({'id': newId, 'name': name});
            $('.hts-drug-typeahead.tt-input').data('ttTypeahead')
                        .menu.datasets[0].source =
                        util.substringMatcher(
                            util.getAttributeFromObjects(
                                pyHTS.state.drugs, 'name'
                            ));
            successCallback();
        } else {
            $.ajax({
                type: 'POST',
                url: ajax.url("create_drug"),
                headers: {'X-CSRFToken': ajax.getCsrfToken()},
                data: {'name': name},
                success: function (data) {
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
                dataType: 'json'
            });
        }
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
        var tgtNumWells = pyHTS.state.plateMap.wells.length;
        var $selectableWells = $('#selectable-wells');
        var $wells = $selectableWells.find('.hts-well');
        $wells.removeClass('ui-selected');
        var needsResize = $wells.length !== tgtNumWells;
        if($wells.length > tgtNumWells) {
            // remove wells
            $wells.filter(':gt('+(tgtNumWells-1)+')').remove();

            $('#selectable-well-cols').find('li').filter(':gt(' +
                    (pyHTS.state.plateMap.numCols-1)+')').remove();

            $('#selectable-well-rows').find('li').filter(':gt' +
                    '('+(pyHTS.state.plateMap.numRows-1)+')')
                    .remove();
        } else if ($wells.length < tgtNumWells) {
            // add wells
            var lastWell = $wells.last();

            for(var w=$wells.length; w<tgtNumWells; w++) {
                lastWell.clone(true).appendTo($selectableWells);
            }

            var selectableCols = $('#selectable-well-cols');
            var cols = selectableCols.find('li');
            var lastCol = cols.last();
            for(var c=cols.length; c<pyHTS.state.plateMap.numCols; c++) {
                lastCol.clone().data('col', c+1).text(c+1)
                       .appendTo(selectableCols);
            }

            var selectableRows = $('#selectable-well-rows');
            var rows = selectableRows.find('li');
            var lastRow = rows.last();
            for(var r=rows.length; r<pyHTS.state.plateMap.numRows; r++) {
                lastRow.clone().data('row', r + 1)
                    .text(pyHTS.state.plateMap.rowNumToName(r))
                    .appendTo(selectableRows);
            }
        }
        if (needsResize) {
            setWellSizes();
            $wells = $selectableWells.find('.hts-well');
        }

        setNumberDrugInputs(pyHTS.state.plateMap.maxDrugsDosesUsed());

        if($('#hts-well-table').hasClass('active')) {
            refreshDataTable();
        } else if($('#hts-well-dip').hasClass('active')) {
            showDipColours();
        }

        // refresh the legend and well CSS classes
        var wellIds = [];
        for(var i=0; i<tgtNumWells; i++) {
            wellIds.push(i);
        }
        refreshLegend($wells, wellIds, 'cell-line');
        refreshLegend($wells, wellIds, 'drug');
        refreshLegend($wells, wellIds, 'dose');
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
            ui.okModal({
                title: "Error",
                text: "Please select some wells first",
                onHidden: function () {
                    $(caller).focus();
                }
            });
            return;
        }

        var allDosesValid = true;
        var doses = [];
        $doseInputs.each(function() {
            var valTxt = $(this).val();
            var val = parseFloat(valTxt);
            if (valTxt != '' && (isNaN(val) || val < 0)) {
                if(allDosesValid) {
                    ui.okModal({
                        title: "Error",
                        text: "Dose must be numeric and non-negative",
                        onHidden: function () {
                            $(caller).focus();
                        }
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
        var cl = $cellLineTypeahead.typeahead('val');
        var cl_id = util.filterObjectsAttr(cl, pyHTS.state.cell_lines,
                'name', 'id');
        if(cl !== '' && cl_id === -1) {
            ui.okCancelModal({
                title: 'Create cell line',
                text: 'Cell line "' + cl + '" ' +
                'was not found. Create it?<br /><br />' +
                'If you meant to autocomplete a suggestion use ' +
                '<kbd>Tab</kbd> instead.',
                onOKHidden: function () {
                    createCellLine(cl, createEntityCallback);
                },
                onCancelHidden: function () {
                    $('#cellline-typeahead').focus();
                }
            });
            return;
        }

        // Check all drugs exist
        var drugIds = [];
        for(var i=0, len=$drugTypeaheads.length; i<len; i++) {
            var drug = $($drugTypeaheads[i]).typeahead('val');
            var dr_id = util.filterObjectsAttr(drug, pyHTS.state.drugs,
                    'name', 'id');
            drugIds.push(dr_id);
            if(drug !== '' && dr_id === -1) {
                ui.okCancelModal({
                    title: 'Create drug',
                    text: 'Drug "' + drug + '" was not found. Create it?<br>' +
                          '<br>If you meant to autocomplate a suggestion' +
                          ' use <kbd>Tab</kbd> instead.',
                    onOKHidden: function () {
                        createDrug(drug, createEntityCallback);
                    },
                    onCancelHidden: function () {
                        $($drugTypeaheads[i]).focus();
                    }
                });
                return;
            }
        }
        var drugIdsLen = drugIds.length;

        // Validations succeeded, apply attributes to wells
        var wellIds = [];
        $.each($selectedWells, function(i, well) {
            var wellId = $(well).index();
            wellIds.push(wellId);
            if(cl_id != -1) {
                pyHTS.state.plateMap.wells[wellId].setCellLine(cl_id);
            }
            for(var j=0; j<drugIdsLen; j++) {
                if(drugIds[j] != -1) {
                    console.log('setting '+drugIds[j]);
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
            $('#hts-finish-platemap').prop("disabled", false);
        }

        // Clear inputs and lose focus
        $cellLineTypeahead.typeahead('val', '');
        $drugTypeaheads.typeahead('val', '');
        $doseInputs.val('');

        // Deselect wells or apply auto-stepper
        if (pyHTS.state.stepperMode === 'off') {
            $selectedWells.removeClass('ui-selected');
            $(caller).blur();
        } else {
            var multiple = pyHTS.state.stepperMode.search('^down|^right') !== -1 ? 1 : -1;
            var baseNum = 1;
            var inRowDirection = pyHTS.state.stepperMode.search('^down|^up') !== -1;
            if (pyHTS.state.stepperMode.endsWith('-sel')) {
                baseNum = inRowDirection ? pyHTS.state.plateMap.selectionHeight(wellIds) :
                    pyHTS.state.plateMap.selectionWidth(wellIds);
            }
            try {
                var newWellIds = pyHTS.state.plateMap.moveSelectionBy(wellIds, multiple * baseNum, inRowDirection);
                selectWells(newWellIds);
                var autoDilutionStep = parseFloat($('input[name=auto-dilution]').val());
                if(!isNaN(autoDilutionStep) && autoDilutionStep > 0) {
                    for (var i = 0; i < doses.length; i++) {
                        if (doses[i] === null || $doseInputs.eq(i).val() !== '') {
                            continue;
                        }
                        var newDose = doses[i] / autoDilutionStep;
                        setDoseInput(i, newDose);
                    }
                }
            } catch(e) {
                $(caller).blur();
                autoStepperOutOfBounds();
            }
        }
    };

    var setDoseInput = function(i, doseVal) {
        var doseSplit = util.doseSplitter(doseVal);
        $doseInputs.eq(i).val(doseSplit[0]);
        $('.hts-active-dose-unit').eq(i).data('dose', doseSplit[1]).text(doseSplit[2]);
    };

    var clearAllInputs = function() {
        $('#cellline-typeahead,.hts-drug-typeahead').not('.tt-hint')
            .typeahead('val', '');
        $('.hts-dose-input').val('');
    };

    $('input[name=auto-dilution]').focusout(function(e) {
       var floatVal = $(this).val(), validated = true;
       if(isNaN(floatVal)) {
            ui.okModal({title: 'Validation error', text: 'Auto dilution should be a numerical step (multiple)'});
            validated = false;
       } else if (floatVal < 0) {
           ui.okModal({title: 'Validation error', text: 'Auto dilution step should be a positive number'});
           validated = false;
       }
       if(validated === false) {
           $(this).val('').focus();
           e.preventDefault();
       }
       return validated;
    }).keyup(function (e) {
        // Drop focus on pressing enter
        if (e.which === 13) {
            $(this).blur();
        }
    });

    var autoStepperOutOfBounds = function() {
        ui.okModal({
            title: 'Auto-step error',
            text: 'The auto-stepper reached the edge of the plate. Please' +
            ' adjust your well selection manually to continue.'
        });
    };

    var activateDrugInputs = function() {
        createTypeahead('.hts-drug-typeahead:last',
                util.getAttributeFromObjects(pyHTS.state.drugs, 'name'));

        $('.hts-dose-input').last().keyup(function (e) {
            if (e.which === 13) {
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
        $('.hts-drug-num,#hts-remove-drug').show();
        activateDrugInputs();
        $drugTypeaheads = $('.hts-drug-typeahead').not('.tt-hint');
        $doseInputs = $('.hts-dose-input');
        $doseUnits = $('.hts-dose-select');
    };

    var removeDrugInput = function() {
        var $drugEntries = $('.hts-drug-entry');
        var numEntries = $drugEntries.length;
        if(numEntries > 1) {
            $drugEntries.filter(':last').remove();
        }
        if(numEntries == 2) {
            $('.hts-drug-num,#hts-remove-drug').hide();
        }
        $drugTypeaheads = $('.hts-drug-typeahead').not('.tt-hint');
        $doseInputs = $('.hts-dose-input');
        $doseUnits = $('.hts-dose-select');
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

    $('#hts-remove-drug').click(function() {
        var numDrugsInUse = pyHTS.state.plateMap.maxDrugsDosesUsed();
        if(numDrugsInUse >= $('.hts-drug-entry').length) {
            return ui.okModal({title: 'Cannot remove while drug has entries', text:
                'Some wells have data for drug/dose ' + numDrugsInUse + ': ' +
                pyHTS.state.plateMap.readableWells(pyHTS.state.plateMap.wellsWithNumDrugsDosesUsed(numDrugsInUse))
                });
        } else {
            removeDrugInput();
        }
    });

    var refreshDataTable = function() {
        $('#hts-well-table-view').find('table').DataTable({
            data: pyHTS.state.plateMap.asDataTable(),
            columns: [
                {title: 'Well', render: {_: "name", sort: "id"}, type: "num"},
                {title: 'Cell Line'},
                {title: 'Drugs'},
                {title: 'Doses'},
                {title: 'DIP Rate'}
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

    var shadeColor2 = function(color, percent) {
        var f=parseInt(color.slice(1),16),t=percent<0?0:255,p=percent<0?percent*-1:percent,R=f>>16,G=f>>8&0x00FF,B=f&0x0000FF;
        return "#"+(0x1000000+(Math.round((t-R)*p)+R)*0x10000+(Math.round((t-G)*p)+G)*0x100+(Math.round((t-B)*p)+B)).toString(16).slice(1);
    };

    var posColour = '#f48000';
    var negColour = '#3f83a3';
    $('#hts-well-dip').click(function(e) {
        setWellView(e, 'dip');
    });

    var viewStrings = {celllines: 'cell lines', drugs: 'drugs', doses:
        'doses', overview: '', table: '', dip: ''};

    var showDipColours = function() {
        var $wells = $('#selectable-wells').find('.hts-well');
        var dipRates = [];
        var dipMin = Number.POSITIVE_INFINITY;
        var dipMax = Number.NEGATIVE_INFINITY;
        var wellLen = pyHTS.state.plateMap.wells.length;
        for (var i = 0; i < wellLen; i++) {
            var dipVal = pyHTS.state.plateMap.wells[i].dipRate;
            if (dipVal < dipMin) dipMin = dipVal;
            if (dipVal > dipMax) dipMax = dipVal;
            dipRates.push(dipVal);
        }
        for (var j = 0; j < wellLen; j++) {
            var dipRate = dipRates[j];
            var bgColour = '';
            if (dipRate === null) {
            } else if (dipRate > 0) {
                bgColour = shadeColor2(posColour, 1.0 - (dipRate / dipMax));
            } else {
                bgColour = shadeColor2(negColour, 1.0 - (dipRate / dipMin));
            }
            $($wells[j]).css('background-color', bgColour);
        }
    };

    var hideDipColours = function() {
        $('#selectable-wells').find('.hts-well').css('background-color', '');
    };

    var setWellView = function(e, view) {
        e.preventDefault();
        if(view === 'table') {
            $('#hts-well-table-view').show();
            $('#hts-well-plate').hide();
            $('#plate-map-edit-controls').hide();
        } else {
            $('#hts-well-table-view').hide();
            $('#hts-well-plate').show();
        }
        pyHTS.state.currentView = view;
        $('.view-str').text(viewStrings[view]);

        clearAllInputs();

        if(view === 'dip') {
            showDipColours();
            if(pyHTS.state.editableFlag) {
                disablePlateSelection();
            }
            $('#plate-map-edit-controls').hide();
            $('#cellline-typeahead,.hts-drug-typeahead').prop('disabled', true)
                .css('background-color', '');
            $('.hts-dose-input').prop('disabled', true);
            $('#hts-dip-display').show();
        } else {
            hideDipColours();
            $('#hts-dip-display').hide();
            if(pyHTS.state.editableFlag) {
                enablePlateSelection();
                if (view !== 'table') {
                    $('#plate-map-edit-controls').show();
                }
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
        }

        $('#hts-well-nav').find('li').removeClass('active');
        $('#hts-well-'+view).addClass('active');
        $('#selectable-wells,#hts-legend-container')
                .removeClass('hts-overview hts-celllines hts-drugs hts-doses' +
                        ' hts-table hts-dip')
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
            wellIds.push($(well).index());
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
            numDrugs = $drugTypeaheads.length,
            numDoses = $doseInputs.length;

        for(i=0; i<numDrugs; i++) {
            drugs.push([]);
        }

        for(i=0; i<numDoses; i++) {
            doses.push([]);
        }

        $('#selectable-wells').find('.ui-selected').each(function(i, ele){
            var well = pyHTS.state.plateMap.wells[$(ele).index()];
            // Only get the first two for speed, just checking if 0/1/multiple
            if(cellLines.length < 2 && $.inArray(well.cellLine, cellLines) === -1) {
                cellLines.push(well.cellLine);
            }
            for(i=0; i<numDrugs; i++) {
                if(drugs[i].length < 2 && well.drugs && $.inArray(well.drugs[i], drugs[i]) === -1) {
                    drugs[i].push(well.drugs[i]);
                }
            }
            for(i=0; i<numDoses; i++) {
                if(doses[i].length < 2 && well.doses && $.inArray(well.doses[i], doses[i]) === -1) {
                    doses[i].push(well.doses[i]);
                }
            }
        });

        $cellLineTypeahead.typeahead('val', '');
        if(cellLines.length === 1 && cellLines[0] != null) {
            $cellLineTypeahead.typeahead('val', util
                    .filterObjectsAttr(cellLines[0], pyHTS.state.cell_lines,
                            'id', 'name'));
        } else if(cellLines.length > 1) {
            $cellLineTypeahead.attr('placeholder', '[Multiple]');
        }

        $drugTypeaheads.typeahead('val', '');
        for(i=0; i<numDrugs; i++) {
            if(drugs[i].length === 1 && drugs[i][0] != null) {
                $drugTypeaheads.eq(i).typeahead('val',
                        util.filterObjectsAttr(drugs[i][0], pyHTS.state.drugs,
                            'id', 'name'));
            } else if(drugs[i].length > 1) {
                $drugTypeaheads.eq(i).attr('placeholder', '[Multiple]');
            }
        }

        $doseInputs.val('');
        for(i=0; i<numDoses; i++) {
            if(doses[i].length === 1 && doses[i][0] != null) {
                setDoseInput(i, doses[i][0]);
            } else if(doses[i].length > 1) {
                $doseInputs.eq(i).attr('placeholder', '[Multiple]');
            }
        }
    };

    var disablePlateSelection = function() {
      $('#well-all,.hts-well').removeClass('ui-selected');
      updateInputsWithWellData();
      pyHTS.state.last_edited = 'all';
      $('#selectable-well-rows,#selectable-well-cols,#selectable-wells').selectable('disable');
    };

    var enablePlateSelection = function() {
      $('#selectable-well-rows,#selectable-well-cols,#selectable-wells').selectable('enable');
    };

    if(pyHTS.state.editableFlag) {
        $('#plate-map-edit-controls').show();
        $("#well-all").click(function () {
            if($('#hts-well-dip').hasClass('active')) return;
            if ($('.hts-well.ui-selected').length) {
                $('#well-all,.hts-well').removeClass('ui-selected');
                clearAllInputs();
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
                $('#selectable-wells').find('li').filter(function (idx) {
                    return idx >
                        ((pyHTS.state.plateMap.numCols * (rowNo - 1)) - 1)
                        && idx < (pyHTS.state.plateMap.numCols * rowNo);
                }).addClass('ui-selected');
            },
            unselecting: function (event, ui) {
                var rowNo = $(ui.unselecting).data('row');
                $('#selectable-wells').find('li').filter(function (idx) {
                    return idx >
                        ((pyHTS.state.plateMap.numCols * (rowNo - 1)) - 1)
                        && idx < (pyHTS.state.plateMap.numCols * rowNo);
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
                $('#selectable-wells').find('li').filter(function (idx) {
                    return idx % pyHTS.state.plateMap.numCols === (colNo - 1);
                }).addClass('ui-selected');
            },
            unselecting: function (event, ui) {
                var colNo = $(ui.unselecting).data('col');
                $('#selectable-wells').find('li').filter(function (idx) {
                    return idx % pyHTS.state.plateMap.numCols === (colNo - 1);
                }).removeClass('ui-selected');
            },
            stop: updateInputsWithWellData
        });

        // Monkey patch this function, otherwise it makes large plates on
        // the plate mapper unusably slow
        $.Widget.prototype._classes = function(options) {
            var full = [];
            var that = this;

            options = $.extend( {
                element: this.element,
                classes: this.options.classes || {}
            }, options );

            function uniqueSort ( results ) {
                var elem,
                    duplicates = [],
                    j = 0,
                    i = 0;

                results.sort();

                while ( (elem = results[i++]) ) {
                    if ( elem === results[ i ] ) {
                        j = duplicates.push( i );
                    }
                }
                while ( j-- ) {
                    results.splice( duplicates[ j ], 1 );
                }

                return results;
            }

            function processClassString( classes, checkOption ) {
                var current, i;
                for ( i = 0; i < classes.length; i++ ) {
                    current = that.classesElementLookup[ classes[ i ] ] || $();
                    if ( options.add ) {
                        current = $( uniqueSort( current.get().concat( options.element.get() ) ) );
                    } else {
                        current = $( current.not( options.element ).get() );
                    }
                    that.classesElementLookup[ classes[ i ] ] = current;
                    full.push( classes[ i ] );
                    if ( checkOption && options.classes[ classes[ i ] ] ) {
                        full.push( options.classes[ classes[ i ] ] );
                    }
                }
            }

            if ( options.keys ) {
                processClassString( options.keys.match( /\S+/g ) || [], true );
            }
            if ( options.extra ) {
                processClassString( options.extra.match( /\S+/g ) || [] );
            }

            return full.join( " " );
        };

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
            ui.okModal({
                title: 'Error',
                text: 'Please select some wells first'
            });
            return;
        }

        $.each(selectedWells, function(i, well) {
            var w = pyHTS.state.plateMap.wells[$(well).index()];
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
            ui.okModal({
                title: 'Error',
                text: 'Cannot apply template to itself'
            });
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
            ui.okModal({
                title: 'Plate map not empty',
                text: 'Cannot apply template data because this plate map is' +
                      ' not empty.'
            });
            return;
        }
        var templateId = pyHTS.state.plateMap.numCols + 'x' + pyHTS.state.plateMap.numRows;
        if(!pyHTS.state.plateMapTemplates[templateId].unsaved_changes) {
            ui.okModal({
                title: 'Template is empty',
                text: 'The template is empty, nothing to apply'
            });
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
        $('#auto-dilution-div').toggle(pyHTS.state.stepperMode !== 'off');
        $('#hts-autostepper-mode').text($(this).text());
    });

    // Mouseovers
    $('#selectable-wells').find('.hts-well').mouseenter(function(e) {
        var well = $(this).index(),
            wellData = pyHTS.state.plateMap.wells[well],
            i,
            len;
        if(wellData == null) return;
        $cellLineTypeahead.attr('placeholder',
                wellData.cellLine == null ? '' :
                util.filterObjectsAttr(wellData.cellLine,
                                            pyHTS.state.cell_lines,
                                            'id', 'name'));
        $drugTypeaheads.attr('placeholder', '');
        if(wellData.drugs != null) {
            for(i=0, len=wellData.drugs.length; i<len; i++) {
                if(wellData.drugs[i] == null) continue;
                $drugTypeaheads.eq(i).attr('placeholder',
                util.filterObjectsAttr(wellData.drugs[i], pyHTS.state.drugs,
                        'id', 'name'));
            }
        }
        $doseInputs.attr('placeholder', '');
        if(wellData.doses != null) {
            for(i=0, len=wellData.doses.length; i<len; i++) {
                if(wellData.doses[i] == null) continue;
                $doseInputs.eq(i).attr('placeholder',
                        util.doseFormatter(wellData.doses[i]));
            }
        }
        $dipBox.attr('placeholder', wellData.dipRate);
    }).mouseleave(function() {
        $cellLineTypeahead.attr('placeholder', 'Cell line');
        $drugTypeaheads.attr('placeholder', 'Drug name');
        $doseInputs.attr('placeholder', 'Dose');
        $dipBox.attr('placeholder', 'DIP rate');
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
        clearAllInputs();
        if(pyHTS.state.completeFlag) {
            pyHTS.state.plateMap.unsaved_changes = false;
            window.location = pyHTS.state.redirectURL;
            return;
        }
        if(data.success) {
            if(data.templateAppliedTo) {
                ui.okModal({
                    title: 'Template applied',
                    text: 'Template was successfully applied'
                });
                $('#hts-apply-template-multiple').find('select')
                        .selectpicker('deselectAll');
            }
            if(data.savedPlateId) {
                if ($.inArray(data.savedPlateId, pyHTS.state.savedPlates) == -1) {
                    pyHTS.state.savedPlates.push(data.savedPlateId);
                    $('#hts-plate-list')
                            .find('li[data-id=' + data.savedPlateId + ']')
                            .find('a')
                            .prepend('<span class="pull-right fa fa-check"' +
                                     ' aria-hidden="true"></span>');
                }
            }
            if(data.plateMap) {
                if(pyHTS.state.savedPlates.length == pyHTS.state.plates.length
                      || (pyHTS.state.savedPlates.length == (pyHTS.state.plates.length - 1)
                      && $.inArray(data.plateMap.plateId, pyHTS.state.savedPlates)
                        == -1)) {
                    $('#hts-finish-platemap').prop("disabled", false);
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
            url: ajax.url("load_plate", plateId),
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
            url: ajax.url("save_plate"),
            data: JSON.stringify(pyHTS.state.plateMap),
            type: 'POST',
            headers: { 'X-CSRFToken': ajax.getCsrfToken() },
            success: plateLoadedCallback,
            error: ajax.ajaxErrorCallback,
            complete: function() {
                ui.loadingModal.hide();
            }
        });
        delete pyHTS.state.plateMap.loadNext;
    };

    var validatePlate = function(retryCallback) {
        var plateValid = pyHTS.state.plateMap.validate();
        if (plateValid !== true) {
            ui.okCancelModal({
                title: 'Error validating plate map',
                text: '<ul><li>' + plateValid.join("</li><li>") + '</li></ul>',
                onOKHide: retryCallback,
                okLabel: 'Ignore Errors',
                cancelLabel: 'Go back',
                cancelByDefault: true
            });
            return false;
        }
        return true;
    };

    var setPlate = function(plateId, templateId, noValidation) {
        var $currentPlate = $('#hts-current-plate'),
            $plateList = $("#hts-plate-list"),
            currentId = $currentPlate.data('id');

        if(currentId != null && currentId != 'MASTER') {
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
            if(pyHTS.state.plateMap != null && pyHTS.state.plateMap.wellDataIsEmpty()) {
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
        if (currentId != null && currentId != 'MASTER' && pyHTS.state.plateMap.unsaved_changes) {
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
        $currentPlate.data('id', plateId.toString()).text(plateName);
        $plateList.find('li').removeClass('active');
        $plateEl.addClass('active');
        // update the UI
        if (plateId == 'MASTER') {
            pyHTS.state.plateMap = pyHTS.state.plateMapTemplates[templateId];
            refreshViewAll();
            $('#hts-prev-dataset,#hts-next-dataset').prop("disabled", true);
            $('#hts-apply-template').hide();
            $('#hts-apply-template-multiple,#apply-template-multiple-btn').show();
        } else {
            $('#hts-apply-template').show();
            $('#hts-apply-template-multiple,#apply-template-multiple-btn').hide();
            $('#hts-prev-dataset').prop("disabled", prevPlatePos() == null);
            $('#hts-next-dataset').prop("disabled", nextPlatePos() == null)
        }

        if (pyHTS.state.savedPlates.length == (pyHTS.state.plates.length - 1)
                   && $.inArray(plateId.toString(), pyHTS.state.savedPlates) != -1) {
            $('#hts-finish-platemap').prop("disabled", true);
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

    var downloadPlate = function(ignoreErrors, format) {
        if(!ignoreErrors) {
            if(!validatePlate(function() { downloadPlate(true, format); } )) {
                return false;
            }
        }
        var blob;
        if (format === 'tsv') {
            blob = new Blob([pyHTS.state.plateMap.toCSV('\t')], {type: "text/tab-separated-values"});
        } else if (format === 'json') {
            var wells = [];
            var numWells = pyHTS.state.plateMap.wells.length;
            for (var w = 0; w < numWells; w++) {
                wells.push(pyHTS.state.plateMap.wells[w].toStringFormat());
            }
            blob = new Blob([JSON.stringify({wells: wells})], {type: "application/json"});
        } else {
            ui.okModal({title: 'Unknown format', text: 'Unknown download' +
                ' format'});
            return;
        }
        FileSaver.saveAs(blob, "platemap." + format);
        if(pyHTS.state.plates[0] === "MASTER") {
            pyHTS.state.plateMap.unsaved_changes = false;
        }
    };

    $('#hts-download-json').click(function() {
        downloadPlate(!pyHTS.state.plateMap.unsaved_changes, 'json');
    });
    $('#hts-download-tsv').click(function() {
        downloadPlate(!pyHTS.state.plateMap.unsaved_changes, 'tsv');
    });

    if(pyHTS.state.plates.length > 0) {
        if(pyHTS.state.plates[0] === "MASTER") {
            setPlate("MASTER", pyHTS.state.plateMap.numCols + 'x' + pyHTS.state.plateMap.numRows);
        } else {
            setPlate(pyHTS.state.plates[0]);
        }
    }
};
module.exports = {
    activate: plate_designer,
    checkLoading: check_loading,
    PlateMap: PlateMap
};
