"use strict";
/*!
 * Thunor
 * Copyright (c) 2016-2018 Alex Lubbock
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
