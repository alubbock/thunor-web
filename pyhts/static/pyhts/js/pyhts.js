window.pyHTS = {
    csrfToken: null,

    last_edited: null,
    num_css_unique_colours: 25,

    plateMap: null,
    cell_lines_used: [],
    drugs_used: [],
    doses_used: [],

    util: {},
    ajax: {},
    ui: {},
    classes: {}
};

var pyHTS = window.pyHTS;

pyHTS.util.getAttributeFromObjects = function(listOfObjects, attrName) {
    var attrList = [];
    $.each(listOfObjects, function(index, object) {
        attrList.push(object[attrName]);
    });
    return attrList;
};

pyHTS.util.substringMatcher = function(strs) {
    return function findMatches(q, cb) {
        // an array that will be populated with substring matches
        var matches = [];

        // regex used to determine if a string contains the substring `q`
        var substrRegex = new RegExp(q, "i");

        // iterate through the pool of strings and for any string that
        // contains the substring `q`, add it to the `matches` array
        $.each(strs, function (i, str) {
            if (substrRegex.test(str)) {
                matches.push(str);
            }
        });

        cb(matches);
    };
};

pyHTS.util.arrayDiffPositions = function(x, y) {
    // find positions of elements in x not in y
    var pos = [];
    $.each(x, function(i, el) {
       var this_pos = pyHTS.util.indexOf(el, y);
       if(this_pos < 0) {
           pos.push(i);
       }
    });
    return pos;
};

pyHTS.util.deepEqual = function (x, y) {
    if ((typeof x == "object" && x != null) &&
            (typeof y == "object" && y != null)) {
        if (Object.keys(x).length != Object.keys(y).length) {
            return false;
        }

        for (var prop in x) {
            if (y.hasOwnProperty(prop)) {
                if (!pyHTS.util.deepEqual(x[prop], y[prop]))
                    return false;
            } else
                return false;
        }

        return true;
    }
    else return x === y;
};

// extends indexOf to search for an array within an array
pyHTS.util.indexOf = function(needle, haystack) {
    if($.isArray(needle)) {
        for(var j=0; j<haystack.length; j++) {
            if(pyHTS.util.deepEqual(needle, haystack[j])) {
                return j;
            }
        }
        return -1; //not found
    } else {
        return $.inArray(needle, haystack);
    }
};

pyHTS.util.allNull = function(arr) {
    return arr.every(function(v) { return v === null; });
};

var onlyUnique = function(value, index, self) {
    return self.indexOf(value) === index;
};

pyHTS.util.unique = function(array) {
    return array.filter(onlyUnique);
};

pyHTS.util.doseUnits = [[1e-12, "p"],
                         [1e-9, "n"],
                         [1e-6, "μ"],
                         [1e-3, "m"],
                         [1, ""]];

pyHTS.util.doseFormatter = function(dose) {
    if(dose === undefined) return "None";
    var doseMultiplier = 1;
    var doseSuffix = "";
    for(var i=0; i<pyHTS.util.doseUnits.length; i++) {
        if(dose >= pyHTS.util.doseUnits[i][0]) {
            doseMultiplier = pyHTS.util.doseUnits[i][0];
            doseSuffix = pyHTS.util.doseUnits[i][1];
        }
    }

    return (parseFloat((dose / doseMultiplier).toPrecision(12)) + " " +
           doseSuffix + "M");
};

/**
 * Converts a dose to modified number and multiplier
 * @param dose
 * @returns {*}
 */
pyHTS.util.doseSplitter = function(dose) {
    if(dose === undefined) return [null, null];
    var doseMultiplier = 1;
    var doseSuffix = "";
    for(var i=0; i<pyHTS.util.doseUnits.length; i++) {
        if(dose >= pyHTS.util.doseUnits[i][0]) {
            doseMultiplier = pyHTS.util.doseUnits[i][0];
            doseSuffix = pyHTS.util.doseUnits[i][1];
        }
    }

    return [parseFloat((dose / doseMultiplier).toPrecision(12)), doseMultiplier, doseSuffix + "M"];
};

pyHTS.util.doseParser = function(dose) {
    var doseParts = dose.split(" ");
    var multiplier = 1;
    if(doseParts[1] === undefined)
        return doseParts[0];
    if(doseParts[1].length == 2) {
        for(var i=0; i<pyHTS.util.doseUnits.length; i++) {
            if(doseParts[1][0] == pyHTS.util.doseUnits[i][1]) {
                multiplier = pyHTS.util.doseUnits[i][0];
                break;
            }
        }
    }
    var val = parseFloat(doseParts[0]) * multiplier;
    // console.log(dose + " parsed as " + val);
    return val;
};

pyHTS.util.doseSorter = {
   "doses-pre": function(dose) {
       //TODO: Sort when multiple doses are present
       dose = dose.split("<br>");
       return pyHTS.util.doseParser(dose[0]);
   }
};

pyHTS.util.filterObjectsAttr = function(name, dataSource,
                                        searchAttribute, returnAttribute) {
    for(var i=0; i<dataSource.length; i++) {
        if(dataSource[i][searchAttribute] == name) {
            return dataSource[i][returnAttribute];
        }
    }
    return -1;
};

pyHTS.util.hasDuplicates = function(array, ignoreNull) {
    if(ignoreNull === undefined) {
        ignoreNull = true;
    }
    var valuesSoFar = Object.create(null);
    for (var i = 0; i < array.length; i++) {
        var value = array[i];
        if(value == null && ignoreNull) continue;
        if (value in valuesSoFar) {
            return true;
        }
        valuesSoFar[value] = true;
    }
    return false;
};

pyHTS.util.padNum = function(num, size) {
    var s = num + "";
    while (s.length < size) s = "0" + s;
    return s;
};

pyHTS.classes.Well = function(well) {
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
pyHTS.classes.Well.prototype = {
    constructor: pyHTS.classes.Well,
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

pyHTS.classes.PlateMap = function(plateId, numRows, numCols, wells) {
    this.unsaved_changes = false;
    this.plateId = plateId;
    this.numRows = numRows;
    this.numCols = numCols;
    this.wells = [];
    for (var w = 0; w < (numRows * numCols); w++) {
        this.wells.push(wells === undefined ?
            new pyHTS.classes.Well() : new pyHTS.classes.Well(wells[w]));
        this.wells[w].setUnsavedChanges = this.setUnsavedChanges.bind(this);
    }
};
pyHTS.classes.PlateMap.prototype = {
    constructor: pyHTS.classes.PlateMap,
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
        for(var w=0; w<wellIds.length; w++) {
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

        for(var i=0; i<this.wells.length; i++) {
            var ent = this.wells[i][entry_list];
            if (ent == null) {
               continue;
            }
            if(typeof ent == "object" &&
                (!ent.length || pyHTS.util.allNull(ent))) {
                    continue;
            }

            if(pyHTS.util.indexOf(ent, usedEntries) == -1) {
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
        for(var i=0; i<this.wells.length; i++) {
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
            return pyHTS.util.padNum(colNum + 1, this.numCols.toString().length);
        } else {
            return (colNum + 1).toString();
        }
    },
    wellNumsToRowNums: function(wellNums) {
        var rowNums = [];
        for(var w=0; w<wellNums.length; w++) {
            rowNums.push(Math.floor(wellNums[w] / this.numCols));
        }
        return rowNums;
    },
    wellNumsToColNums: function(wellNums) {
        var colNums = [];
        for(var w=0; w<wellNums.length; w++) {
            colNums.push(wellNums[w] % this.numCols);
        }
        return colNums;
    },
    asDataTable: function() {
        var wells = [];
        for(var w=0; w<this.wells.length; w++) {
            wells.push([
               this.wellNumToName(w, true),
               pyHTS.util.filterObjectsAttr(this.wells[w].cellLine,
                                            pyHTS.cell_lines,
                                            "id", "name").toString().replace(/^-1$/, ""),
               $.map(this.wells[w].drugs, function(drug) {
                   return pyHTS.util.filterObjectsAttr(drug, pyHTS.drugs, "id", "name").toString().replace(/^-1$/, "None");
               }).join("<br>"),
               $.map(this.wells[w].doses, pyHTS.util.doseFormatter).join("<br>")
            ]);
        }
        return wells;
    },
    wellDataIsEmpty: function() {
        return this.allCellLinesEmpty() && this.allDrugsEmpty() && this.allDosesEmpty();
    },
    allCellLinesEmpty: function() {
        for(var w=0; w<this.wells.length; w++) {
            if(this.wells[w].cellLine != null) {
                return false;
            }
        }
        return true;
    },
    allDrugsEmpty: function() {
        for(var w=0; w<this.wells.length; w++) {
            var well = this.wells[w];
            if(well.drugs != null && well.drugs.length > 0) {
                return false;
            }
        }
        return true;
    },
    allDosesEmpty: function() {
        for(var w=0; w<this.wells.length; w++) {
            var well = this.wells[w];
            if(well.doses != null && well.doses.length > 0) {
                return false;
            }
        }
        return true;
    },
    readableWells: function(wellIds) {
        if(wellIds == null || wellIds.length == 0) {
            return "No wells";
        } else if(wellIds.length == 1) {
            return this.wellNumToName(wellIds[0]);
        }
        wellIds.sort(function(a,b){return a - b;});
        wellIds = pyHTS.util.unique(wellIds);

        var wellStrs = [],
            rowNums = this.wellNumsToRowNums(wellIds),
            colNums = this.wellNumsToColNums(wellIds),
            contigStart = wellIds[0];
        for(var w=0; w<wellIds.length; w++) {
            if(colNums[w] != (colNums[w+1] - 1) ||
               rowNums[w] != rowNums[w+1] ||
               w == (wellIds.length - 1)) {
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

        for(var w=0; w<this.wells.length; w++) {
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
                if(pyHTS.util.hasDuplicates(well.drugs)) {
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

pyHTS.ui.okCancelModal = function(title, text, success_callback,
                                  cancel_callback, closed_callback,
                                  ok_label, cancel_label) {
    var $mok = $("#modal-ok-cancel");
    if(cancel_callback != null) {
        cancel_label = cancel_label == null ? "Cancel" : cancel_label;
        $mok.find(".btn-cancel").text(cancel_label).show();
    } else {
        $mok.find(".btn-cancel").hide();
    }
    $mok.find(".modal-header").text(title);
    $mok.find(".modal-body").html(text);
    $mok.data("success", false);
    ok_label = ok_label == null ? "OK" : ok_label;
    $mok.find(".btn-ok").text(ok_label).off("click").on("click", function () {
        $mok.data("success", true).modal("hide");
    });
    $mok.off("shown.bs.model").on("shown.bs.modal", function() {
        $mok.find(".btn-ok").focus();
    }).off("hidden.bs.modal").on("hidden.bs.modal", function(e) {
        if(closed_callback != null) {
            closed_callback(e);
        }
        if(success_callback != null && $mok.data("success")) {
            success_callback(e);
        } else if(cancel_callback != null && !$mok.data("success")) {
            cancel_callback(e);
        }
    }).modal();
};

pyHTS.ui.okModal = function(title, text, closed_callback) {
    pyHTS.ui.okCancelModal(title, text, null, null, closed_callback);
};

pyHTS.ui.glyphiconHtml = function(iconName) {
    return '<span class="pull-right glyphicon glyphicon-'+iconName+
                      '" aria-hidden="true"></span>';
};

/**
 * Module for displaying "Waiting for..." dialog using Bootstrap
 *
 * @author Eugene Maslovich <ehpc@em42.ru>
 */

pyHTS.ui.loadingModal = (function () {
    // Creating modal dialog's DOM
    var $dialog = $(
        '<div class="modal fade" data-backdrop="static" data-keyboard="false" tabindex="-1" role="dialog" aria-hidden="true" style="padding-top:15%; overflow-y:visible;">' +
        '<div class="modal-dialog modal-m">' +
        '<div class="modal-content">' +
        '<div class="modal-header"><h3 style="margin:0;"></h3></div>' +
        '<div class="modal-body">' +
        '<div class="progress progress-striped active" style="margin-bottom:0;"><div class="progress-bar" style="width: 100%"></div></div>' +
        '</div>' +
        '</div></div></div>');

    return {
        /**
         * Opens our dialog
         * @param message Custom message
         * @param options Custom options:
         *                  options.dialogSize - bootstrap postfix for dialog size, e.g. "sm", "m";
         *                  options.progressType - bootstrap postfix for progress bar type, e.g. "success", "warning".
         */
        show: function (message, options) {
            // Assigning defaults
            if (typeof options === 'undefined') {
                options = {};
            }
            if (typeof message === 'undefined') {
                message = 'Loading';
            }
            var settings = $.extend({
                dialogSize: 'm',
                progressType: '',
                onHide: null // This callback runs after the dialog was hidden
            }, options);

            // Configuring dialog
            $dialog.find('.modal-dialog').attr('class', 'modal-dialog').addClass('modal-' + settings.dialogSize);
            $dialog.find('.progress-bar').attr('class', 'progress-bar');
            if (settings.progressType) {
                $dialog.find('.progress-bar').addClass('progress-bar-' + settings.progressType);
            }
            $dialog.find('h3').text(message);
            // Adding callbacks
            if (typeof settings.onHide === 'function') {
                $dialog.off('hidden.bs.modal').on('hidden.bs.modal', function (e) {
                    settings.onHide.call($dialog);
                });
            }
            // Opening dialog
            $dialog.modal();
        },
        /**
         * Closes dialog
         */
        hide: function () {
            $dialog.modal('hide');
        }
    };

})();

pyHTS.ajax.ajax401Handler = function(jqXHR) {
    pyHTS.ui.okModal("Authentication required", "The request to the server" +
        " was not authenticated. Please check that you are logged in, e.g." +
        " by refreshing the page.");
    return true;
};

pyHTS.ajax.ajax404Handler = function(jqXHR) {
    pyHTS.ui.okModal("Requested resource not found", "The requested resource" +
        " was not found, or you do not do have access to it. Please check" +
        " you are logged in as the correct user.");
    return true;
};

pyHTS.ajax.ajax409Handler = function(jqXHR) {
    // Is this a known error?
    if(jqXHR.responseJSON.error != null
        && jqXHR.responseJSON.error == "non_empty_plates") {
        var errStr = "The template could not be applied because some of the" +
                " selected plates are not empty. The non-empty plates" +
                " are:<br>" + jqXHR.responseJSON.plateNames.join(", ");
        if(pyHTS.ui.currentView == "overview") {
            errStr += "<br><br><strong>Switch to a different view tab if" +
                " you want to apply only one of cell lines, drugs or" +
                " doses</strong>";
        }
        pyHTS.ui.okModal("Error applying template", errStr);
        return true;
    }
    return false;
};

pyHTS.ajax.ajaxErrorCallback = function(jqXHR,textStatus,thrownError) {
    var message = 'Communication with the server timed ' +
        'out (perhaps the connection was lost?';
    if(textStatus == "error" ||
        textStatus == "parsererror") {
        if(jqXHR != null) {
            if(jqXHR.status == 401 && pyHTS.ajax.ajax401Handler(jqXHR)) return;
            if(jqXHR.status == 404 && pyHTS.ajax.ajax404Handler(jqXHR)) return;
            if(jqXHR.status == 409 && pyHTS.ajax.ajax409Handler(jqXHR)) return;
        }
        if(Raven != null) {
            Raven.captureMessage(thrownError || jqXHR.statusText, {
                extra: {
                    type: this.type,
                    url: this.url,
                    data: this.data,
                    status: jqXHR.status,
                    error: thrownError || jqXHR.statusText,
                    response: (jqXHR.responseText == undefined) ? null :
                        jqXHR.responseText.substring(0, 100)
                }
            });
        }
        message = 'An unknown error occurred with the ' +
            'server and has been logged. Please bear' +
            ' with us while we look into it.<br><br>'
            + 'Reference number: '+ Raven.lastEventId();
    } else if (textStatus == 'abort') {
        message = 'Communication with the server was ' +
            'aborted.';
    }
    pyHTS.ui.okModal('Error communicating with server',
        message);
};
