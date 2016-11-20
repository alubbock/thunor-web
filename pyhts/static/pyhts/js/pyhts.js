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
        this.drugs[position] = drug;
        this.setUnsavedChanges();
    },
    setDose: function(dose, position) {
        if(this.doses == null) this.doses = [];
        this.doses[position] = dose;
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
    getUsedEntries: function(entry_list) {
        var usedEntries = [];

        for(var i=0; i<this.wells.length; i++) {
            var ent = this.wells[i][entry_list];
            if (ent == null || (typeof ent == "object" && !ent.length)) {
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
    wellNumToName: function(wellNum) {
        return String.fromCharCode(65 + Math.floor(wellNum / this.numCols)) +
               pyHTS.util.padNum(((wellNum % this.numCols) + 1), 2);
    },
    asDataTable: function() {
        var wells = [];
        for(var w=0; w<this.wells.length; w++) {
            wells.push([
               this.wellNumToName(w),
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
        for(var w=0; w<(this.numRows * this.numCols); w++) {
            var well = this.wells[w];
            if(well.cellLine != null ||
               (well.drugs != null && well.drugs.length > 0) ||
               (well.doses != null && well.doses.length > 0)) {
                return false;
            }
        }
        return true;
    },
    validate: function() {
        var wellsWithDrugButNotDose = [], wellsWithDoseButNotDrug = [],
            wellsWithDuplicateDrug = [], wellsWithDrugButNoCellLine = [],
            errors=[];

        for(var w=0; w<this.wells.length; w++) {
            var well = this.wells[w];
            if(well.drugs == null && well.doses == null) {
                continue;
            }
            if(well.drugs.length > 0) {
                if(well.cellLine == null) {
                    wellsWithDrugButNoCellLine.push(this.wellNumToName(w));
                }
                if(pyHTS.util.hasDuplicates(well.drugs)) {
                    wellsWithDuplicateDrug.push(this.wellNumToName(w));
                }
            }

            if(well.drugs.length > well.doses.length) {
                wellsWithDrugButNotDose.push(this.wellNumToName(w));
            } else if (well.drugs.length < well.doses.length) {
                wellsWithDoseButNotDrug.push(this.wellNumToName(w));
            } else {
                for(var pos = 0; pos < well.drugs.length; pos++) {
                    if(well.drugs[pos] == null && well.doses[pos] == null) {
                        continue;
                    }
                    if(well.drugs[pos] != null && well.doses[pos] == null) {
                        wellsWithDrugButNotDose.push(this.wellNumToName(w));
                    }
                    if(well.drugs[pos] == null && well.doses[pos] != null) {
                        wellsWithDoseButNotDrug.push(this.wellNumToName(w));
                    }
                }
            }
        }

        if(wellsWithDoseButNotDrug.length > 0) {
            errors.push("The following wells have one or more doses without" +
                " a drug: " + wellsWithDoseButNotDrug.join(", "));
        }
        if(wellsWithDrugButNotDose.length > 0) {
            errors.push("The following wells have one or more drugs without" +
                " a dose: " + wellsWithDrugButNotDose.join(", "));
        }
        if(wellsWithDuplicateDrug.length > 0) {
            errors.push("The following wells have the same drug more than" +
                " once: " + wellsWithDuplicateDrug.join(", "));
        }
        if(wellsWithDrugButNoCellLine.length > 0) {
            errors.push("The following wells have a drug defined but no" +
                " cell line: " + wellsWithDrugButNoCellLine.join(", "));
        }
        if(errors.length > 0) {
            return errors;
        }
        return false;
    }
};

pyHTS.ui.okCancelModal = function(title, text, success_callback,
                             cancel_callback, closed_callback) {
    var mok = "#modal-ok-cancel";
    if(cancel_callback != null) {
        $(mok).find(".btn-cancel").show();
    } else {
        $(mok).find(".btn-cancel").hide();
    }
    $(mok).find(".modal-header").text(title);
    $(mok).find(".modal-body").html(text);
    $(mok).data("success", false);
    $(mok).find(".btn-ok").off("click").on("click", function (e) {
        $(mok).data("success", true).modal("hide");
    });
    $(mok).off("shown.bs.model").on("shown.bs.modal", function() {
        $(mok).find(".btn-ok").focus();
    }).off("hidden.bs.modal").on("hidden.bs.modal", function(e) {
        if(closed_callback != null) {
            closed_callback(e);
        }
        if(success_callback != null && $(mok).data("success")) {
            success_callback(e);
        } else if(cancel_callback != null) {
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

pyHTS.ajax.ajaxErrorCallback = function(jqXHR,textStatus,thrownError) {
    var message = 'Communication with the server timed ' +
        'out (perhaps the connection was lost?';
    if(textStatus == "error" ||
        textStatus == "parsererror") {
        if(Raven != null) {
            Raven.captureMessage(thrownError || jqXHR.statusText, {
                extra: {
                    type: this.type,
                    url: this.url,
                    data: this.data,
                    status: jqXHR.status,
                    error: thrownError || jqXHR.statusText,
                    response: jqXHR.responseText.substring(0, 100)
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
