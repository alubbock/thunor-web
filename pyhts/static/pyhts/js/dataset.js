"use strict";

var ui = require("./modules/ui"),
    ajax = require("./modules/ajax");

var delete_dataset = function() {
    $.ajax({type: 'POST',
            url: ajax.url("delete_dataset"),
            headers: { 'X-CSRFToken': ajax.getCsrfToken() },
            data: {'dataset_id': $('#dataset-id').val()},
            success: function() {
                window.location = ajax.url("page_datasets");
            },
            error: ajax.ajaxErrorCallback,
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
                throw new Error("Error downloading file");
            }
        });
        return false;
    });

    $("#btn-delete-dataset").click(function() {
        ui.okCancelModal('Confirm Delete', 'Deleting this dataset is' +
            ' <strong>permanent</strong> and <strong>Irreversible</strong>.' +
            ' Are you sure?', delete_dataset, null, null, 'Delete', 'Cancel');
    });
};

module.exports = {
    activate: dataset
};