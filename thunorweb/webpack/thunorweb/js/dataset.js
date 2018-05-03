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
    $('#dataset-name-edit').click(function() {
        var datasetName = $('.dataset-name').first().text();
        $('#dataset-name').hide();
        $('#dataset-rename').show().find("input[name=datasetName]").val(datasetName).select();
    });

    $('#dataset-rename-cancel').click(function() {
       $('#dataset-rename').hide();
       $('#dataset-name').show();
    });

    $('#dataset-rename-form').submit(function(e) {
       e.preventDefault();
       ui.loadingModal.show();

       $.ajax({type: 'POST',
        url: ajax.url("rename_dataset"),
        headers: { 'X-CSRFToken': ajax.getCsrfToken() },
        data: $(this).serialize(),
        success: function(data) {
            $('#dataset-rename').hide();
            $('.dataset-name').text(data.datasetName);
            $('#dataset-name').show();
        },
        error: ajax.ajaxErrorCallback,
        complete: function() {
            ui.loadingModal.hide();
        },
        dataType: 'json'});
    });


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
            text: "Are you sure you want to delete this dataset?",
            onOKHide: delete_dataset,
            okLabel: "Delete",
            okButtonClass: "btn-danger"
        });
    });
};

module.exports = {
    activate: dataset
};
