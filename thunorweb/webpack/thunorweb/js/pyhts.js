"use strict";
/*!
 * Thunor
 * Copyright 2016-2017 Alex Lubbock
 */
var pyHTS = {
    views: {
        home: require("./home"),
        dataset: require("./dataset"),
        dataset_permissions: require("./dataset_permissions"),
        plots: require("./plots"),
        plate_upload: require("./plate_upload"),
        plate_designer: require("./plate_designer"),
        tag_editor: require("./tag_editor")
    },
    state: {}
};
module.exports = pyHTS;
