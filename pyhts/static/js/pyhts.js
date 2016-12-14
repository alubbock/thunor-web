/*!
 * Thunor
 * Copyright 2016 Alex Lubbock
 */
var pyHTS = (function() {
    var state = require("./modules/state");
    var views = {
        plots: require("./plots"),
        plate_upload: require("./plate_upload"),
        plate_designer: require("./plate_designer")
    };
    var pub = {
        PlateMap: views.plate_designer.PlateMap
    };

    return({
        state: state,
        views: views,
        pub: pub
    });
})();
module.exports = pyHTS;
