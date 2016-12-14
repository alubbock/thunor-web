$.extend(pyHTS.views, {
    "plate_designer": function () {
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
            pyHTS.ui.okModal('No plates selected', 'Please select target ' +
                    'plates from the drop down list');
            return;
        }
        if(pyHTS.plateMap.wellDataIsEmpty()) {
            pyHTS.ui.okModal('Empty template', 'The template could not be ' +
                    'applied because it is empty');
            return;
        }

        pyHTS.ui.loadingModal.show('Applying template...');

        pyHTS.plateMap.applyTemplateTo = tgtPlateIds;
        pyHTS.plateMap.applyTemplateMode = $.inArray(pyHTS.ui.currentView,
            ['overview', 'table']) != -1 ? 'all' : pyHTS.ui.currentView;
        pyHTS.ajax.savePlate(null);
        delete pyHTS.plateMap.applyTemplateMode;
        delete pyHTS.plateMap.applyTemplateTo;
    });

    pyHTS.ui.currentView = 'overview';

    window.onbeforeunload = function() {
      if(pyHTS.plateMap!=null && pyHTS.plateMap.unsaved_changes) {
          return 'The plate map has unsaved changes. Are you sure you want ' +
                  'to leave the page?';
      }
    };

    pyHTS.ajax.createCellLine = function(name, successCallback) {
        $.ajax({type: 'POST',
                url: '/ajax/cellline/create',
                headers: { 'X-CSRFToken': pyHTS.csrfToken },
                data: {'name' : name},
                success: function(data) {
                    pyHTS.cell_lines = data.cellLines;
                    $('#cellline-typeahead').data('ttTypeahead').menu
                            .datasets[0].source =
                            pyHTS.util.substringMatcher(
                                    pyHTS.util.getAttributeFromObjects(
                                            pyHTS.cell_lines, 'name'
                                    ));
                    successCallback();
                },
                error: pyHTS.ajax.ajaxErrorCallback,
                dataType: 'json'});
    };

    pyHTS.ajax.createDrug = function(name, successCallback) {
        $.ajax({type: 'POST',
                url: '/ajax/drug/create',
                headers: { 'X-CSRFToken': pyHTS.csrfToken },
                data: {'name' : name},
                success: function(data) {
                    pyHTS.drugs = data.drugs;
                    $('.hts-drug-typeahead.tt-input').data('ttTypeahead')
                            .menu.datasets[0].source =
                                pyHTS.util.substringMatcher(
                                        pyHTS.util.getAttributeFromObjects(
                                                pyHTS.drugs, 'name'
                                        ));
                    successCallback();
                },
                error: pyHTS.ajax.ajaxErrorCallback,
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
        pyHTS.pub.setPlate(plateId, templateId);
    });

    pyHTS.ui.refreshViewAll = function() {
        var wellIds = [],
            tgtNumWells = pyHTS.plateMap.wells.length;
        for(var i=0; i<tgtNumWells; i++) {
            wellIds.push(i);
        }
        var selectedWells = $('#selectable-wells').find('.hts-well');
        selectedWells.removeClass('ui-selected');
        if(selectedWells.length > tgtNumWells) {
            // remove wells
            selectedWells.filter(':gt('+(tgtNumWells-1)+')').remove();

            $('#selectable-well-cols').find('li').filter(':gt(' +
                    (pyHTS.plateMap.numCols-1)+')').remove();

            $('#selectable-well-rows').find('li').filter(':gt' +
                    '('+(pyHTS.plateMap.numRows-1)+')')
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
            for(var c=cols.length; c<pyHTS.plateMap.numCols; c++) {
                lastCol.clone().data('col', c).text(c+1)
                       .appendTo(selectableCols);
            }

            var selectableRows = $('#selectable-well-rows');
            var rows = selectableRows.find('li');
            var lastRow = rows.filter(':last');
            for(var r=rows.length; r<pyHTS.plateMap.numRows; r++) {
                lastRow.clone().data('row', r)
                        .text(String.fromCharCode(65 + r))
                        .appendTo(selectableRows);
            }
        }

        pyHTS.ui.setNumberDrugInputs(pyHTS.plateMap.maxDrugsDosesUsed());

        if($('#hts-well-table').hasClass('active')) {
            refreshDataTable();
        }

        // resize the wells
        var wellWidthPercent = (100 / (pyHTS.plateMap.numCols + 1)) + '%';
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
            oldLegendEntries = pyHTS[oldLegendEntriesDescriptor],
            i;

        if(data_type == 'cell-line') {
            newLegendEntries = pyHTS.plateMap.getUsedCellLines();
        } else if (data_type == 'drug') {
            newLegendEntries = pyHTS.plateMap.getUsedDrugs();
        } else if (data_type == 'dose') {
            newLegendEntries = pyHTS.plateMap.getUsedDoses();
        }
        //compare old with new (this could be done more efficiently - this
        //scans the arrays twice)
        var removed = pyHTS.util.arrayDiffPositions(oldLegendEntries,
                newLegendEntries),
            added = pyHTS.util.arrayDiffPositions(newLegendEntries,
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
            var n = arrayInsertPos % pyHTS.num_css_unique_colours;
            var $lgnd = $baseLegendItem.clone().data('insertPos', arrayInsertPos);
            var legendText;
            if(data_type == 'cell-line') {
                legendText = pyHTS.util.filterObjectsAttr(newArrayEntry,
                        pyHTS.cell_lines, 'id', 'name');
            } else if(data_type == 'drug') {
                legendText = $.map(newArrayEntry, function(elem) {
                    return pyHTS.util.filterObjectsAttr(elem, pyHTS.drugs,
                            'id', 'name').toString().replace(/^-1$/, 'None');
                }).join(' & ');
            } else if(data_type == 'dose') {
                legendText = $.map(newArrayEntry, pyHTS.util.doseFormatter)
                        .join(' & ');
            }

            $lgnd.children('li').addClass('hts-'+data_type+'-'+n);
            $lgnd.find('.legend-label').text(legendText);
            $legendBlock.append($lgnd);
        }

        if(addedLen > 0 || removedLen > 0) {
            pyHTS[oldLegendEntriesDescriptor] = oldLegendEntries;
        }

        // Update the wells
        selectedWells.each(function(i, ele) {
            var well = pyHTS.plateMap.wells[wellIds[i]],
                $ele = $(ele),
                this_value,
                n;
            for(n = 0; n < pyHTS.num_css_unique_colours; n++) {
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
                var loc = pyHTS.util.indexOf(this_value,
                        pyHTS[oldLegendEntriesDescriptor]);
                if(loc >= 0) {
                    n = loc % pyHTS.num_css_unique_colours;
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
                    source: pyHTS.util.substringMatcher(dataSource)
                }).keyup(function (e) {
            if (e.which == 13) {
                submitToWells(this);
            }
        });
    };
    createTypeahead('#cellline-typeahead',
            pyHTS.util.getAttributeFromObjects(pyHTS.cell_lines, 'name'));

    var submitToWells = function(caller) {
        // called when enter is pressed

        //non-callback validation
        var $selectedWells = $('#selectable-wells').find('.ui-selected');
        if ($selectedWells.length === 0) {
            pyHTS.ui.okModal('Error', 'Please select some wells first',
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
                    pyHTS.ui.okModal('Error', 'Dose must be numeric and ' +
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
        var cl_id = pyHTS.util.filterObjectsAttr(cl, pyHTS.cell_lines,
                'name', 'id');
        if(cl != '' && cl_id == -1) {
            pyHTS.ui.okCancelModal('Create cell line',
                    'Cell line "' + cl + '" ' +
                'was not found. Create it?<br /><br />If you meant to ' +
                'autocomplete a suggestion use <kbd>Tab</kbd> instead.',
                function() { pyHTS.ajax.createCellLine(cl, createEntityCallback); },
                function() { $('#cellline-typeahead').focus(); });
            return;
        }

        // Check all drugs exist
        var $drugTypeaheads = $('.hts-drug-typeahead').not('.tt-hint');
        var drugIds = [];
        for(var i=0, len=$drugTypeaheads.length; i<len; i++) {
            var drug = $($drugTypeaheads[i]).typeahead('val');
            var dr_id = pyHTS.util.filterObjectsAttr(drug, pyHTS.drugs,
                    'name', 'id');
            drugIds.push(dr_id);
            if(drug != '' && dr_id == -1) {
                pyHTS.ui.okCancelModal('Create drug',
                'Drug "' + drug + '" was not found. Create it?<br /><br />'
                + 'If you meant to autocomplate a suggestion use ' +
                '<kbd>Tab</kbd> instead.',
                function() { pyHTS.ajax.createDrug(drug, createEntityCallback); },
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
                pyHTS.plateMap.wells[wellId].setCellLine(cl_id);
            }
            for(var j=0; j<drugIdsLen; j++) {
                if(drugIds[j] != -1) {
                    pyHTS.plateMap.wells[wellId].setDrug(drugIds[j], j);
                }
                if(doses[j] != null) {
                    pyHTS.plateMap.wells[wellId].setDose(doses[j], j);
                }
            }
        });

        // Refresh legend
        refreshLegend($selectedWells, wellIds, 'cell-line');
        refreshLegend($selectedWells, wellIds, 'drug');
        refreshLegend($selectedWells, wellIds, 'dose');

        // Show finish button if appropriate
        if(pyHTS.savedPlates.length == (pyHTS.plates.length - 1)
           && ($.inArray(pyHTS.plateMap.plateId, pyHTS.savedPlates) == -1)) {
            $('#hts-finish-platemap').show();
        }

        // Clear inputs and lose focus
        $cellLineTypeahead.typeahead('val', '');
        $drugTypeaheads.typeahead('val', '');
        $doseInputs.val('');

        // Deselect wells or apply auto-stepper
        var newWellIds;
        switch (pyHTS.stepperMode) {
            case 'off':
                $selectedWells.removeClass('ui-selected');
                break;
            case 'down-sel':
                try {
                    newWellIds = pyHTS.plateMap.moveSelectionDownBy(wellIds,
                            pyHTS.plateMap.selectionHeight(wellIds));
                } catch(e) {
                    autoStepperOutOfBounds();
                }
                break;
            case 'down-1':
                try {
                    newWellIds = pyHTS.plateMap.moveSelectionDownBy(wellIds, 1);
                } catch(e) {
                    autoStepperOutOfBounds();
                }
                break;
            case 'right-sel':
                try {
                    newWellIds = pyHTS.plateMap.moveSelectionRightBy(wellIds,
                            pyHTS.plateMap.selectionWidth(wellIds));
                } catch(e) {
                    autoStepperOutOfBounds();
                }
                break;
            case 'right-1':
                try {
                    newWellIds = pyHTS.plateMap.moveSelectionRightBy(wellIds, 1);
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
        pyHTS.ui.okModal('Auto-step error', 'The auto-stepper reached the' +
                ' edge of the plate. Please adjust your well ' +
                'selection manually to continue.');
    };

    var activateDrugInputs = function() {
        createTypeahead('.hts-drug-typeahead:last',
                pyHTS.util.getAttributeFromObjects(pyHTS.drugs, 'name'));

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

    pyHTS.ui.addDrugInput = function() {
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

    pyHTS.ui.removeDrugInput = function() {
        var $drugEntries = $('.hts-drug-entry');
        var numEntries = $drugEntries.length;
        if(numEntries > 1) {
            $drugEntries.filter(':last').remove();
        }
        if(numEntries == 2) {
            $('.hts-drug-num').hide();
        }
    };

    pyHTS.ui.setNumberDrugInputs = function(numInputs) {
        var requiredInputs = numInputs - $('.hts-drug-entry').length;
        for(var i=0, len=Math.abs(requiredInputs); i<len; i++) {
            if (requiredInputs < 0) {
                pyHTS.ui.removeDrugInput();
            } else if (requiredInputs > 0) {
                pyHTS.ui.addDrugInput();
            }
        }
    };

    $('#hts-add-drug').click(function (e) {
        pyHTS.ui.addDrugInput();
    });

    var refreshDataTable = function() {
        $('#hts-well-table-view').find('table').DataTable({
            data: pyHTS.plateMap.asDataTable(),
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
        pyHTS.ui.currentView = view;
        $('.view-str').text(viewStrings[view]);

        clearAllInputs();

        if(view == 'overview' || view == 'celllines') {
            $('#cellline-typeahead').prop('disabled', false).css
                ('background-color', 'transparent');
        } else {
            $('#cellline-typeahead').prop('disabled', true).css
                ('background-color', '');
        }

        if(view == 'overview' || view == 'drugs') {
            $('.hts-drug-typeahead').prop('disabled', false).css
                ('background-color', 'transparent');
        } else {
            $('.hts-drug-typeahead').prop('disabled', true).css
                ('background-color', '');
        }

        if(view == 'overview' || view == 'doses') {
            $('.hts-dose-input').prop('disabled', false);
        } else {
            $('.hts-dose-input').prop('disabled', true);
        }

        $('#hts-well-nav').find('li').removeClass('active');
        $('#hts-well-'+view).addClass('active');
        $('#selectable-wells,#hts-legend-container')
                .removeClass('hts-overview hts-celllines hts-drugs hts-doses' +
                        ' hts-table')
                .addClass('hts-'+view);
    };

    $.extend( $.fn.dataTableExt.oSort, pyHTS.util.doseSorter );

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
            newWellIds = pyHTS.plateMap.moveSelectionBy(wellIds, amount,
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
            var well = pyHTS.plateMap.wells[$(ele).data('well')];
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
            $cellLineTypeahead.typeahead('val', pyHTS.util
                    .filterObjectsAttr(cellLines[0], pyHTS.cell_lines,
                            'id', 'name'));
        } else if(cellLines.length > 1) {
            $cellLineTypeahead.attr('placeholder', '[Multiple]');
        }

        $drugTypeahead.typeahead('val', '');
        for(i=0; i<numDrugs; i++) {
            if(drugs[i].length == 1 && drugs[i][0] != null) {
                $drugTypeahead.eq(i).typeahead('val',
                        pyHTS.util.filterObjectsAttr(drugs[i][0], pyHTS.drugs,
                            'id', 'name'));
            } else if(drugs[i].length > 1) {
                $drugTypeahead.eq(i).attr('placeholder', '[Multiple]');
            }
        }

        $doseInput.val('');
        for(i=0; i<numDoses; i++) {
            if(doses[i].length == 1 && doses[i][0] != null) {
                var doseSplit = pyHTS.util.doseSplitter(doses[i][0]);
                $doseInput.eq(i).val(doseSplit[0]);
                $doseUnits.eq(i).data('dose', doseSplit[1]).text(doseSplit[2]);
            } else if(doses[i].length > 1) {
                $doseInput.eq(i).attr('placeholder', '[Multiple]');
            }
        }
    };

    $("#well-all").click(function () {
        if ($('.hts-well.ui-selected').length) {
            $('#well-all,.hts-well').removeClass('ui-selected');
        } else {
            $('#well-all,.hts-well').addClass('ui-selected');
            updateInputsWithWellData();
        }
        pyHTS.last_edited = 'all';
    });

    $('#selectable-well-rows').selectable({
        start: function (event, ui) {
            if (pyHTS.last_edited != 'row')
                $('.hts-well').removeClass('ui-selected');
            pyHTS.last_edited = 'row';
        },
        selecting: function (event, ui) {
            var rowNo = $(ui.selecting).data('row');
            $('#selectable-wells').find('li').filter(function() {
                return $(this).data('well') >
                        ((pyHTS.plateMap.numCols * (rowNo - 1)) - 1)
                && $(this).data('well') < (pyHTS.plateMap.numCols * rowNo);
            }).addClass('ui-selected');
        },
        unselecting: function (event, ui) {
            var rowNo = $(ui.unselecting).data('row');
            $('#selectable-wells').find('li').filter(function() {
                return $(this).data('well') >
                        ((pyHTS.plateMap.numCols * (rowNo - 1)) - 1)
                && $(this).data('well') < (pyHTS.plateMap.numCols * rowNo);
            }).removeClass('ui-selected');
        },
        stop: updateInputsWithWellData
    });

    $('#selectable-well-cols').selectable({
        start: function (event, ui) {
            if (pyHTS.last_edited != 'col')
                $('.hts-well').removeClass('ui-selected');
            pyHTS.last_edited = 'col';
        },
        selecting: function (event, ui) {
            var colNo = $(ui.selecting).data('col');
            $('#selectable-wells').find('li').filter(function() {
                return $(this).data('well') % pyHTS.plateMap.numCols ==
                        (colNo - 1);
            }).addClass('ui-selected');
        },
        unselecting: function (event, ui) {
            var colNo = $(ui.unselecting).data('col');
            $('#selectable-wells').find('li').filter(function() {
                return $(this).data('well') % pyHTS.plateMap.numCols ==
                        (colNo - 1);
            }).removeClass('ui-selected');
        },
        stop: updateInputsWithWellData
    });

    $("#selectable-wells").selectable({
        start: function () {
            pyHTS.last_edited = 'cell';
        },
        stop: updateInputsWithWellData
    });

    $('#hts-apply-annotation').click(function() {
        submitToWells(this);
    });

    $('#hts-clear-annotation').click(function() {
        var selectedWells = $('#selectable-wells').find('.ui-selected');

        if (selectedWells.length === 0) {
            pyHTS.ui.okModal('Error', 'Please select some wells first');
            return;
        }

        $.each(selectedWells, function(i, well) {
            var w = pyHTS.plateMap.wells[$(well).data('well')];
            if(pyHTS.ui.currentView == 'celllines') {
                w.setCellLine(null);
            } else if(pyHTS.ui.currentView == 'drugs') {
                w.setDrug(null, null);
            } else if(pyHTS.ui.currentView == 'doses') {
                w.setDose(null, null);
            } else {
                w.clear();
            }
        });

        clearAllInputs();
        pyHTS.ui.refreshViewAll();
    });

    var applyTemplateToCurrent = function() {
        if($('#hts-current-plate').data('id') == 'MASTER') {
            pyHTS.ui.okModal('Error', 'Cannot apply template to itself');
            return;
        }
        if(pyHTS.ui.currentView == 'celllines' && !pyHTS.plateMap
                .allCellLinesEmpty() ||
                pyHTS.ui.currentView == 'drugs' && !pyHTS.plateMap
                    .allDrugsEmpty() ||
                pyHTS.ui.currentView == 'doses' && !pyHTS.plateMap
                    .allDosesEmpty() ||
                !$.inArray(pyHTS.ui.currentView, ['celllines', 'drugs',
                        'doses']) && !pyHTS.plateMap.wellDataIsEmpty()) {
            pyHTS.ui.okModal('Plate map not empty', 'Cannot apply template ' +
                    'data because this plate map is not empty.');
            return;
        }
        var templateId = pyHTS.plateMap.numCols + 'x' + pyHTS.plateMap.numRows;
        if(!pyHTS.plateMapTemplates[templateId].unsaved_changes) {
            pyHTS.ui.okModal('Template is empty', 'The template is empty, ' +
                    'nothing to apply');
            return;
        }
        populateWellDataFromTemplate(pyHTS.plateMap.wells, templateId);
        pyHTS.plateMap.unsaved_changes = true;
        pyHTS.ui.refreshViewAll();
    };

    $('#hts-apply-template').click(function() {
        applyTemplateToCurrent();
    });

    // Auto-stepper
    pyHTS.stepperMode = 'off';
    $('#hts-autostepper-div').find('li').click(function(e) {
        e.preventDefault();
        pyHTS.stepperMode = $(this).data('mode');
        $('#hts-autostepper-mode').text($(this).text());
    });

    // Mouseovers
    $('#selectable-wells').find('.hts-well').mouseenter(function(e) {
        var well = $(this).data('well'),
            wellData = pyHTS.plateMap.wells[well],
            i,
            len;
        if(wellData == null) return;
        $('#cellline-typeahead').attr('placeholder',
                wellData.cellLine == null ? '' :
                pyHTS.util.filterObjectsAttr(wellData.cellLine,
                                            pyHTS.cell_lines,
                                            'id', 'name'));
        var $drugTypeaheads = $('.hts-drug-typeahead').not('.tt-hint');
        $drugTypeaheads.attr('placeholder', '');
        if(wellData.drugs != null) {
            for(i=0, len=wellData.drugs.length; i<len; i++) {
                if(wellData.drugs[i] == null) continue;
                $drugTypeaheads.eq(i).attr('placeholder',
                pyHTS.util.filterObjectsAttr(wellData.drugs[i], pyHTS.drugs,
                        'id', 'name'));
            }
        }
        var $doseInputs = $('.hts-dose-input');
        $doseInputs.attr('placeholder', '');
        if(wellData.doses != null) {
            for(i=0, len=wellData.doses.length; i<len; i++) {
                if(wellData.doses[i] == null) continue;
                $doseInputs.eq(i).attr('placeholder',
                        pyHTS.util.doseFormatter(wellData.doses[i]));
            }
        }
    }).mouseleave(function() {
        $('#cellline-typeahead').attr('placeholder', 'Cell line');
        $('.hts-drug-typeahead').not('.tt-hint').attr('placeholder', 'Drug name');
        $('.hts-dose-input').attr('placeholder', 'Dose');
    });

    var populateWellDataFromTemplate = function(wellData, templateId) {
        var templateWells = pyHTS.plateMapTemplates[templateId].wells;
        for(var w=0, len=wellData.length; w<len; w++) {
            if($.inArray(pyHTS.ui.currentView, ['drugs', 'doses']) == -1) {
                wellData[w].cellLine = templateWells[w].cellLine;
            }
            if($.inArray(pyHTS.ui.currentView, ['celllines', 'doses']) ==
                -1) {
                wellData[w].drugs = templateWells[w].drugs != null ?
                    templateWells[w].drugs.slice() : null;
            }
            if($.inArray(pyHTS.ui.currentView, ['celllines', 'drugs']) ==
                -1) {
                wellData[w].doses = templateWells[w].doses != null ?
                    templateWells[w].doses.slice() : null;
            }
        }
    };

    // Loading and saving plates
    var plateLoadedCallback = function (data) {
        if(pyHTS.completeFlag) {
            pyHTS.plateMap.unsaved_changes = false;
            window.location = pyHTS.redirectURL;
            return;
        }
        if(data.success) {
            if(data.templateAppliedTo) {
                pyHTS.ui.okModal('Template applied', 'Template was ' +
                        'successfully applied');
                $('#hts-apply-template-multiple').find('select')
                        .selectpicker('deselectAll');
            }
            if(data.savedPlateId) {
                if ($.inArray(data.savedPlateId, pyHTS.savedPlates) == -1) {
                    pyHTS.savedPlates.push(data.savedPlateId);
                    var plateInDropdown = $('#hts-plate-list')
                            .find('li[data-id=' + data.savedPlateId + ']')
                            .find('a');
                    plateInDropdown.html(pyHTS.ui.glyphiconHtml('ok') +
                            plateInDropdown.html());
                }
            }
            if(data.plateMap) {
                if(pyHTS.savedPlates.length == pyHTS.plates.length
                      || (pyHTS.savedPlates.length == (pyHTS.plates.length - 1)
                      && $.inArray(data.plateMap.plateId, pyHTS.savedPlates)
                        == -1)) {
                    $('#hts-finish-platemap').show();
                }
                pyHTS.plateMap = new pyHTS.classes.PlateMap(
                        data.plateMap.plateId,
                        data.plateMap.numRows,
                        data.plateMap.numCols,
                        data.plateMap.wells
                );
                pyHTS.ui.refreshViewAll();
            }
        }
    };

    pyHTS.ajax.loadPlate = function(plateId) {
        $.ajax({
            url: '/ajax/plate/load/'+plateId,
            type: 'GET',
            success: plateLoadedCallback,
            error: pyHTS.ajax.ajaxErrorCallback,
            complete: function() {
                pyHTS.ui.loadingModal.hide();
            }
        });
    };

    pyHTS.ajax.savePlate = function(nextPlateToLoad) {
        pyHTS.plateMap.loadNext = nextPlateToLoad;
        $.ajax({
            url: '/ajax/plate/save',
            data: JSON.stringify(pyHTS.plateMap),
            type: 'POST',
            headers: { 'X-CSRFToken': pyHTS.csrfToken },
            success: plateLoadedCallback,
            error: pyHTS.ajax.ajaxErrorCallback,
            complete: function() {
                pyHTS.ui.loadingModal.hide();
            }
        });
        delete pyHTS.plateMap.loadNext;
    };

    var validatePlate = function(retryCallback) {
        var plateErrors = pyHTS.plateMap.validate();
        if (plateErrors) {
            pyHTS.ui.okCancelModal('Error validating plate map',
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

    pyHTS.pub.setPlate = function(plateId, templateId, noValidation) {
        var $currentPlate = $('#hts-current-plate'),
            $plateList = $("#hts-plate-list"),
            currentId = $currentPlate.data('id');

        if(currentId != 'MASTER') {
            if(noValidation !== true) {
                var validated = validatePlate(function () {
                    pyHTS.pub.setPlate(plateId, templateId, true)
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
            if(pyHTS.plateMap.wellDataIsEmpty()) {
                pyHTS.plateMap.unsaved_changes = false;
            }
            if(plateId != 'MASTER') {
                $('#hts-select-plate').removeClass('btn-success');
            }
        }

        if(plateId != 'MASTER') {
            pyHTS.ui.loadingModal.show();
        }

        // save current data if necessary
        if (currentId != 'MASTER' && pyHTS.plateMap.unsaved_changes) {
            pyHTS.ajax.savePlate(plateId == 'MASTER' ? null : plateId);
        } else if (plateId != 'MASTER') {
            pyHTS.ajax.loadPlate(plateId);
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
            pyHTS.plateMap = pyHTS.plateMapTemplates[templateId];
            pyHTS.ui.refreshViewAll();
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

        if (pyHTS.savedPlates.length == (pyHTS.plates.length - 1)
                   && $.inArray(plateId, pyHTS.savedPlates) != -1) {
            $('#hts-finish-platemap').hide();
        }
    };

    var currentPlatePos = function() {
        return $.inArray($('#hts-current-plate').data('id'), pyHTS.plates);
    };

    var prevPlatePos = function() {
        var pos = currentPlatePos();
        return pos > 0 ? pyHTS.plates[pos - 1] : null;
    };

    var nextPlatePos = function() {
        var pos = currentPlatePos();
        return pos < (pyHTS.plates.length - 1) ? pyHTS.plates[pos + 1] : null;
    };

    $('#hts-next-dataset').click(function(e) {
        pyHTS.pub.setPlate(nextPlatePos());
    });

    $('#hts-prev-dataset').click(function(e) {
        pyHTS.pub.setPlate(prevPlatePos());
    });

    $('#hts-finish-platemap').click(function(e) {
        pyHTS.completeFlag = true;
        if ($('#hts-current-plate').data('id') != 'MASTER' &&
                pyHTS.plateMap.unsaved_changes) {
            if(!validatePlate()) {
                pyHTS.completeFlag = false;
                return;
            }
            pyHTS.ui.loadingModal.show();
            pyHTS.ajax.savePlate(null);
        } else {
            plateLoadedCallback();
        }
    });

    }
});
