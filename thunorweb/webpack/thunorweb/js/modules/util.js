export const util = (function() {
    var onlyUnique = function (value, index, self) {
        return self.indexOf(value) === index;
    };

    var doseUnits = [[1e-12, "p"], [1e-9, "n"], [1e-6, "μ"], [1e-3, "m"],
                     [1, ""]];

    return {
        getAttributeFromObjects: function (listOfObjects, attrName) {
            var attrList = [];
            $.each(listOfObjects, function (index, object) {
                attrList.push(object[attrName]);
            });
            return attrList;
        },
        substringMatcher: function (strs) {
            return function findMatches(q, cb) {
                // an array that will be populated with substring matches
                var matches = [];

                // regex used to determine if a string contains the substring `q`
                var substrRegex = new RegExp(
                    q.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, "\\$&"), "i");

                // iterate through the pool of strings and for any string that
                // contains the substring `q`, add it to the `matches` array
                $.each(strs, function (i, str) {
                    if (substrRegex.test(str)) {
                        matches.push(str);
                    }
                });

                cb(matches);
            };
        },
        arrayDiffPositions: function (x, y) {
            // find positions of elements in x not in y
            var pos = [];
            $.each(x, function (i, el) {
                var this_pos = util.indexOf(el, y);
                if (this_pos < 0) {
                    pos.push(i);
                }
            });
            return pos;
        },
        deepEqual: function (x, y) {
            if ((typeof x == "object" && x != null) &&
                (typeof y == "object" && y != null)) {
                if (Object.keys(x).length != Object.keys(y).length) {
                    return false;
                }

                for (var prop in x) {
                    if (y.hasOwnProperty(prop)) {
                        if (!util.deepEqual(x[prop], y[prop]))
                            return false;
                    } else
                        return false;
                }

                return true;
            }
            else return x === y;
        },
        indexOf: function (needle, haystack) {
            if ($.isArray(needle)) {
                for (var j = 0, len = haystack.length; j < len; j++) {
                    if (util.deepEqual(needle, haystack[j])) {
                        return j;
                    }
                }
                return -1; //not found
            } else {
                return $.inArray(needle, haystack);
            }
        },
        allNull: function (arr) {
            return arr.every(function (v) {
                return v === null;
            });
        },
        unique: function (array) {
            return array.filter(onlyUnique);
        },
        doseFormatter: function (dose) {
            if (dose === undefined) return "None";
            var doseMultiplier = 1;
            var doseSuffix = "";
            for (var i = 0, len = doseUnits.length; i < len; i++) {
                if (dose >= doseUnits[i][0]) {
                    doseMultiplier = doseUnits[i][0];
                    doseSuffix = doseUnits[i][1];
                }
            }
            return (parseFloat((dose / doseMultiplier).toPrecision(12)) + " " +
            doseSuffix + "M");
        },
        /**
         * Converts a dose to modified number and multiplier
         * @param dose
         * @returns {*}
         */
        doseSplitter: function (dose) {
            if (dose === undefined) return [null, null];
            var doseMultiplier = 1;
            var doseSuffix = "";
            for (var i = 0, len = doseUnits.length; i < len; i++) {
                if (dose >= doseUnits[i][0]) {
                    doseMultiplier = doseUnits[i][0];
                    doseSuffix = doseUnits[i][1];
                }
            }
            return [parseFloat((dose / doseMultiplier).toPrecision(12)), doseMultiplier, doseSuffix + "M"];
        },
        doseParser: function (dose) {
            var doseParts = dose.split(" ");
            var multiplier = 1;
            if (doseParts[1] === undefined)
                return doseParts[0];
            if (doseParts[1].length == 2) {
                for (var i = 0, len = doseUnits.length; i < len; i++) {
                    if (doseParts[1][0] == doseUnits[i][1]) {
                        multiplier = doseUnits[i][0];
                        break;
                    }
                }
            }
            return parseFloat(doseParts[0]) * multiplier;
        },
        doseSorter: {
            "doses-pre": function (dose) {
                //TODO: Sort when multiple doses are present
                dose = dose.split("<br>");
                return util.doseParser(dose[0]);
            }
        },
        filterObjectsAttr: function (name, dataSource,
                                     searchAttribute, returnAttribute, caseInsensitive) {
            if(caseInsensitive === true) {
                name = name.toUpperCase();
            }
            for (var i = 0, len = dataSource.length; i < len; i++) {
                if ((caseInsensitive ? dataSource[i][searchAttribute].toUpperCase() : dataSource[i][searchAttribute]) === name) {
                    return dataSource[i][returnAttribute];
                }
            }
            return -1;
        },
        hasDuplicates: function (array, ignoreNull) {
            if (ignoreNull === undefined) {
                ignoreNull = true;
            }
            var valuesSoFar = Object.create(null);
            for (var i = 0, len = array.length; i < len; i++) {
                var value = array[i];
                if (value == null && ignoreNull) continue;
                if (value in valuesSoFar) {
                    return true;
                }
                valuesSoFar[value] = true;
            }
            return false;
        },
        padNum: function (num, size) {
            var s = num + "";
            while (s.length < size) s = "0" + s;
            return s;
        },
        escapeHTML: function(unsafe) {
            return unsafe
                 .replace(/&/g, "&amp;")
                 .replace(/</g, "&lt;")
                 .replace(/>/g, "&gt;")
                 .replace(/"/g, "&quot;")
                 .replace(/'/g, "&#039;");
         },
        stringToColour: function(str) {
          var hash = 0;
          var i;
          for (i = 0; i < str.length; i++) {
            hash = str.charCodeAt(i) + ((hash << 5) - hash);
          }
          var colour = '#';
          for (i = 0; i < 3; i++) {
            var value = (hash >> (i * 8)) & 0xFF;
            colour += ('00' + value.toString(16)).substr(-2);
          }
          return colour;
        },
        userIcon: function(email) {
            return '<i class="fa fa-user tt" data-placement="top" data-toggle="tooltip" style="color:' + util.stringToColour(email) +
                   '" title="' + email + '"></i>';
        }
    }
})();
