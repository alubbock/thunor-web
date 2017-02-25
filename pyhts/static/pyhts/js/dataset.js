"use strict";

var ui = require("./modules/ui");

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
};

module.exports = {
    activate: dataset
};
