"use strict";
/*!
 * Thunor
 * Copyright 2016 Alex Lubbock
 */
var pyHTS = {
    views: {
        home: require("./home"),
        dataset: require("./dataset"),
        plots: require("./plots"),
        plate_upload: require("./plate_upload"),
        plate_designer: require("./plate_designer")
    },
    state: {}
};
module.exports = pyHTS;