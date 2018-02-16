var ajax = require("./modules/ajax"),
    datasetTable = require("./modules/dataset_table");

var home = function() {
    var callbackFn = function (data, type, full, meta) {
        return "<a href=\"" + ajax.url("page_view_dataset",
                full.id) +  "\">" + full.name + "</a>";
    };
    datasetTable.initDatasetTable(callbackFn);
};

module.exports = {
    activate: home
};
