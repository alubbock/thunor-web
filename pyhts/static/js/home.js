var ajax = require("./modules/ajax");

var home = function() {
    var $tabContent = $(".tab-content");
    $tabContent.loadingOverlay("show");
    var dataset_table = $("#dataset-table").DataTable({
        "ajax": {
            "url": ajax.url("get_datasets"),
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
                    "display": function (data, type, full, meta) {
                        return '<a href="'+ ajax.url("page_view_dataset",
                                full.id) +  '">' + full.name + '</a>';
                    }
                }
            },
            {"targets": 1, "data": "creation_date"}
        ],
        "order": [[1, "desc"]],
        "initComplete": function () {
            $tabContent.loadingOverlay("hide");
        }
    });

    var $datasetTabs = $("#dataset-tabs");

    $datasetTabs.find("li").click(function (e) {
        e.preventDefault();
        $tabContent.loadingOverlay("show");
        var $this = $(e.currentTarget);
        dataset_table.ajax.url($this.data("url")).load();
        $datasetTabs.find("li").removeClass("active");
        $this.addClass("active");
    });
};

module.exports = {
    activate: home
};
