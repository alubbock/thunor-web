"use strict";

var ui = require("./modules/ui"),
    ajax = require("./modules/ajax");

var delete_dataset = function() {
    ui.loadingModal.show();
    $.ajax({type: 'POST',
            url: ajax.url("delete_dataset"),
            headers: { 'X-CSRFToken': ajax.getCsrfToken() },
            data: {'dataset_id': $('#dataset-id').val()},
            success: function() {
                window.location = ajax.url("page_datasets");
            },
            error: ajax.ajaxErrorCallback,
            complete: function() {
                ui.loadingModal.hide();
            },
            dataType: 'json'});
};

var dataset = function() {

    $("a.attachment-download").click(function(e) {
        e.preventDefault();
        ui.loadingModal.show();
        var $this = $(e.currentTarget);
        $.fileDownload($this.attr("href"), {
            successCallback: function () {
                ui.loadingModal.hide();
            },
            failCallback: function () {
                ui.loadingModal.hide();
                Raven.captureMessage("Error downloading file");
                Raven.showReportDialog();
            }
        });
        return false;
    });

    $("#btn-delete-dataset").click(function() {
        ui.okCancelModal({
            title: "Confirm Delete",
            text: "Deleting this dataset is" +
            " <strong>permanent</strong> and" +
            " <strong>Irreversible</strong>." +
            " Are you sure?",
            onOKHide: delete_dataset,
            okLabel: "Delete",
            okButtonClass: "btn-danger"
        });
    });
};

module.exports = {
    activate: dataset
};
