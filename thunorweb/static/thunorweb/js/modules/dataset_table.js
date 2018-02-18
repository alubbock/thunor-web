var ajax = require("./ajax");

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
                "data": "name",
                "render": {
                    "display": tableRowCallbackFn
                }
            },
            {"targets": 1, "data": "creation_date"}
        ],
        "order": [[1, "desc"]],
        "initComplete": function () {
            $tabContent.loadingOverlay("hide");
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
        dataset_table.ajax.url($this.data("url")).load(loadingCompleteCallbackFn);
        $datasetTabs.find("li").removeClass("active");
        $this.addClass("active");
    });
};

module.exports = {
    initDatasetTable: initDatasetTable
};
