window.pyHTS = {
    last_edited: null,
    num_css_unique_colours: 25,
    unsaved_changes: false,

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

pyHTS.util.padNum = function(num, size) {
    var s = num + "";
    while (s.length < size) s = "0" + s;
    return s;
};

pyHTS.classes.Well = function(well) {
    if(well === undefined) {
        this.cellLine = null;
        this.drugs = null;
        this.doses = null;
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
        pyHTS.unsaved_changes = true;
    },
    setDose: function(dose, position) {
        if(this.doses == null) this.doses = [];
        this.doses[position] = dose;
        pyHTS.unsaved_changes = true;
    },
    setCellLine: function(cellLine) {
        this.cellLine = cellLine;
        pyHTS.unsaved_changes = true;
    }
};

pyHTS.classes.PlateMap = function(plateId, numRows, numCols, wells) {
    this.plateId = plateId;
    this.numRows = numRows;
    this.numCols = numCols;
    this.wells = [];
    for (var w = 0; w < (numRows * numCols); w++) {
        this.wells.push(wells === undefined ?
            new pyHTS.classes.Well() : new pyHTS.classes.Well(wells[w]));
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
    getUsedCellLines: function() {
        return this.getUsedEntries("cellLine");
    },
    getUsedDrugs: function() {
        return this.getUsedEntries("drugs");
    },
    getUsedDoses: function() {
        return this.getUsedEntries("doses");
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
    }
};

pyHTS.ui.okCancelModal = function(title, text, success_callback,
                             cancel_callback, closed_callback) {
    var mok = "#modal-ok-cancel";
    if(cancel_callback !== undefined) {
        $(mok).find(".btn-cancel").show();
    } else {
        $(mok).find(".btn-cancel").hide();
    }
    $(mok).find(".modal-header").text(title);
    $(mok).find(".modal-body").html(text);
    $(mok).data("success", false);
    $("#modal-ok-cancel .btn-ok").off("click").on("click", function (e) {
        $(mok).data("success", true);
        $("#modal-ok-cancel").modal("hide");
    });
    $(mok).off("shown.bs.model").on("shown.bs.modal", function() {
        $("#modal-ok-cancel .btn-ok").focus();
    }).off("hide.bs.modal").on("hide.bs.modal", function(e) {
        if(success_callback !== undefined && $(mok).data("success")) {
            success_callback(e);
        } else if(cancel_callback !== undefined &&
                  cancel_callback !== null) {
            cancel_callback(e);
        }
    }).off("hidden.bs.modal").on("hidden.bs.modal", closed_callback).modal();
};

pyHTS.ui.okModal = function(title, text, closed_callback) {
    pyHTS.ui.okCancelModal(title, text, undefined, undefined,
            closed_callback);
};
