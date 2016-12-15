var dataset = function() {
    var ui = require("./modules/ui");

    $("a.attachment-download").click(function(e) {
        e.preventDefault();
        ui.loadingModal.show("Preparing download. This may take several" +
            " minutes for large datasets...");
        $this = $(e.currentTarget);
        $.fileDownload($this.attr("href"), {
            successCallback: function() {
                ui.loadingModal.hide();
            },
            failCallback: function(html, url) {
                // TODO: Log error with Raven
                ui.loadingModal.hide();
                ui.okModal("Error", "There was an error downloading your" +
                    " file");
            }
        });
        return false;
    });
};

module.exports = {
    activate: dataset
};
