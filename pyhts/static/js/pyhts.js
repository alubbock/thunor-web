/*!
 * Thunor
 * Copyright 2016 Alex Lubbock
 */
var pyHTS = (function() {
    var views = {
        home: require("./home"),
        dataset: require("./dataset"),
        plots: require("./plots"),
        plate_upload: require("./plate_upload"),
        plate_designer: require("./plate_designer")
    };
    var pub = {
        PlateMap: views.plate_designer.PlateMap,
        ui: require("./modules/ui")
    };

    return({
        state: {},
        views: views,
        pub: pub
    });
})();
module.exports = pyHTS;
