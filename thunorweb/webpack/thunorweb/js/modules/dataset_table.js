var ajax = require("./ajax"),
    util = require("./util");

var formatISODate = function(data) {
    return data.replace('T', ' ').slice(0, -5) + ' UTC';
};

var initDatasetTable = function(tableRowCallbackFn, loadingCompleteCallbackFn) {
    var $tabContent = $(".tab-content");
    $tabContent.loadingOverlay("show");

    var $datasetTabs = $("#dataset-tabs");
    var defaultTableUrl = $datasetTabs.find("li.active").first().data('url');

    var dataset_table = $("#dataset-table").DataTable({
        "ajax": {
            "url": defaultTableUrl,
            "timeout": 15000,
            "error": ajax.ajaxErrorCallback,
            "complete": function() {
                $tabContent.loadingOverlay("hide");
            }
        },
        "columnDefs": [
            {
                "targets": 0,
                "data": "ownerEmail",
                "className": "text-center",
                "width": "0",
                "render": {"display": util.userIcon}
            },
            {
                "targets": 1,
                "data": "name",
                "render": {
                    "display": tableRowCallbackFn
                }
            },
            {"targets": 2, "data": "creationDate", "render": {"display": formatISODate}}
        ],
        "order": [[2, "desc"]],
        "drawCallback": function () {
            $('.tt').tooltip();
            if (loadingCompleteCallbackFn !== undefined) {
                loadingCompleteCallbackFn();
            }
        }
    });

    var lastTabClick = 0;

    $datasetTabs.find("li").click(function (e) {
        e.preventDefault();
        var dateNow = Date.now();
        if (dateNow - lastTabClick < 500) {
            return;
        }
        lastTabClick = dateNow;
        $tabContent.loadingOverlay("show");
        var $this = $(e.currentTarget);
        dataset_table.ajax.url($this.data("url")).load(function() {$tabContent.loadingOverlay("hide")});
        $datasetTabs.find("li").removeClass("active");
        $this.addClass("active");
    });
};

module.exports = {
    initDatasetTable: initDatasetTable
};
