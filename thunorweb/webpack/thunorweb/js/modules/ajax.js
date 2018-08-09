"use strict";

var ui = require("./ui");

var ajax = (function () {
    var csrfToken = null;

    var getCookie = function (name) {
     var cookieValue = null;
     if (document.cookie && document.cookie != "") {
         var cookies = document.cookie.split(";");
         for(var i = 0, cookieLen = cookies.length; i < cookieLen; i++) {
             var cookie = jQuery.trim(cookies[i]);
             if (cookie.substring(0, name.length + 1) == (name + "=")) {
                 cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
             break;
         }
     }
     }
     return cookieValue;
    };

    var getCsrfToken = function() {
        if (csrfToken == null) {
            csrfToken = getCookie("csrftoken");
        }
      return csrfToken;
    };

    var ajax400Handler = function (jqXHR) {
        ui.okModal({
            title: "Invalid request",
            text: "The request was not processed for the following reason:<br><br>" + jqXHR.responseText
        });
        return true;
    };

    var ajax401Handler = function (jqXHR) {
        ui.okModal({
            title: "Authentication required",
            text: "The request to the server was not authenticated. Please" +
            " check that you are logged in, e.g. by refreshing the page."
        });
        return true;
    };

    var ajax404Handler = function (jqXHR) {
        ui.okModal({
            title: "Requested resource not found",
            text: "The requested resource was not found, or you do not do" +
            " have access to it. Please check you are logged in as the" +
            " correct user."
        });
        return true;
    };

    var ajax409Handler = function (jqXHR) {
        // Is this a known error?
        if (jqXHR.responseJSON.error != null) {
            var errStr;
            if (jqXHR.responseJSON.error === "non_empty_plates") {
                errStr = "The template could not be applied because some of the" +
                    " selected plates are not empty. The non-empty plates" +
                    " are:<br>" + jqXHR.responseJSON.plateNames.join(", ");
                if (pyHTS.state.currentView === "overview") {
                    errStr += "<br><br><strong>Switch to a different view tab" +
                        " (other than overview - see tabs above the plate" +
                        " layout) if you want to apply only one of cell lines, " +
                        "drugs or doses</strong>";
                }
            } else {
                errStr = jqXHR.responseJSON.error;
            }
            ui.okModal({
                title: "Conflict error",
                text: errStr
            });
            return true;
        }
        return false;
    };

    var ajax502Handler = function (jqXHR) {
        ui.okModal({
            title: "Server unavailable",
            text: "The server is currently unavailable. Please try your" +
            " request again in a few minutes (code 502)."
        });
        return true;
    };

    var ajaxErrorCallback = function (jqXHR, textStatus, thrownError) {
        if (textStatus === "error" ||
            textStatus === "parsererror") {
            var message = "Communication with the server timed " +
            "out. Please check your internet connection and try again.",
            subject = "Error communicating with server";
            if (jqXHR != null) {
                if (jqXHR.status === 0) {
                    ui.okModal({title: subject, text: message});
                    return;
                }
                if (jqXHR.status == 400 && ajax400Handler(jqXHR)) return;
                if (jqXHR.status == 401 && ajax401Handler(jqXHR)) return;
                if (jqXHR.status == 404 && ajax404Handler(jqXHR)) return;
                if (jqXHR.status == 409 && ajax409Handler(jqXHR)) return;
                if (jqXHR.status == 502 && ajax502Handler(jqXHR)) return;
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
            message = "An unknown error occurred with the " +
                "server and has been logged. Please bear" +
                " with us while we look into it.<br><br>"
                + "Reference number: " + Raven.lastEventId();
            ui.okModal({title: subject, text: message});
        }
    };

    var urls = {
        "get_datasets": "/ajax/dataset/all",
        "rename_dataset": "/ajax/dataset/rename",
        "delete_dataset": "/ajax/dataset/delete",
        "page_view_dataset": "/dataset/{ARG}",
        "create_cellline": "/ajax/cellline/create",
        "create_drug": "/ajax/drug/create",
        "load_plate": "/ajax/plate/load/{ARG}",
        "save_plate": "/ajax/plate/save",
        "page_datasets": "/",
        "page_upload_platefile": "/dataset/{ARG}/upload",
        "upload_platefile": "/ajax/platefile/upload",
        "delete_platefile": "/ajax/platefile/delete",
        "create_dataset": "/ajax/dataset/create",
        "set_dataset_group_permission": "/ajax/dataset/set-permission",
        "page_annotate_dataset": "/dataset/{ARG}/annotate",
        "dataset_groupings": "/ajax/dataset/{ARG}/groupings",
        "view_plots": "/plots",
        "get_plot": "/ajax/plot.json",
        "get_plot_csv": "/ajax/plot.csv",
        "get_plot_html": "/ajax/plot.html",
        "assign_tag": "/ajax/tags/assign",
        "create_tag": "/ajax/tags/create",
        "delete_tag": "/ajax/tags/delete",
        "get_tag_targets": "/ajax/tags/{ARG}/targets/",
        "set_tag_group_permission": "/ajax/tags/set-permission"
    };

    var url = function(view, arg) {
        var retUrl = urls[view];
        if(arg !== undefined) {
          return retUrl.replace("{ARG}", arg);
        } else {
            return retUrl;
        }
    };

    return {
        ajaxErrorCallback: ajaxErrorCallback,
        getCsrfToken: getCsrfToken,
        url: url
    }
})();
module.exports = ajax;
