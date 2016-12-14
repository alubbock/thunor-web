 var ajax = (function () {
     var ui = require("./ui");

    var ajax401Handler = function (jqXHR) {
        ui.okModal("Authentication required", "The request to the server" +
            " was not authenticated. Please check that you are logged in, e.g." +
            " by refreshing the page.");
        return true;
    };

    var ajax404Handler = function (jqXHR) {
        ui.okModal("Requested resource not found", "The requested" +
            " resource" +
            " was not found, or you do not do have access to it. Please check" +
            " you are logged in as the correct user.");
        return true;
    };

    var ajax409Handler = function (jqXHR) {
        // Is this a known error?
        if (jqXHR.responseJSON.error != null
            && jqXHR.responseJSON.error == "non_empty_plates") {
            var errStr = "The template could not be applied because some of the" +
                " selected plates are not empty. The non-empty plates" +
                " are:<br>" + jqXHR.responseJSON.plateNames.join(", ");
            if (state.currentView == "overview") {
                errStr += "<br><br><strong>Switch to a different view tab if" +
                    " you want to apply only one of cell lines, drugs or" +
                    " doses</strong>";
            }
            ui.okModal("Error applying template", errStr);
            return true;
        }
        return false;
    };

    var ajaxErrorCallback = function (jqXHR, textStatus, thrownError) {
        var message = 'Communication with the server timed ' +
            'out (perhaps the connection was lost?';
        if (textStatus == "error" ||
            textStatus == "parsererror") {
            if (jqXHR != null) {
                if (jqXHR.status == 401 && ajax401Handler(jqXHR)) return;
                if (jqXHR.status == 404 && ajax404Handler(jqXHR)) return;
                if (jqXHR.status == 409 && ajax409Handler(jqXHR)) return;
            }
            if (Raven != null) {
                Raven.captureMessage(thrownError || jqXHR.statusText, {
                    extra: {
                        type: this.type,
                        url: this.url,
                        data: this.data,
                        status: jqXHR.status,
                        error: thrownError || jqXHR.statusText,
                        response: (jqXHR.responseText == undefined) ? null :
                            jqXHR.responseText.substring(0, 100)
                    }
                });
            }
            message = 'An unknown error occurred with the ' +
                'server and has been logged. Please bear' +
                ' with us while we look into it.<br><br>'
                + 'Reference number: ' + Raven.lastEventId();
        } else if (textStatus == 'abort') {
            message = 'Communication with the server was aborted.';
        }
        ui.okModal('Error communicating with server', message);
    };

    return {
        ajaxErrorCallback: ajaxErrorCallback
    }
})();
module.exports = ajax;
