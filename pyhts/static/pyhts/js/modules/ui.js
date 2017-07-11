"use strict";
var ui = (function() {
    var modalBase = $(
        '<div class="modal fade" id="modal-ok-cancel" tabindex="-1"' +
        ' role="dialog" aria-hidden="true">' +
        '<div class="modal-dialog">' +
            '<div class="modal-content">' +
                '<div class="modal-header"></div>' +
                '<div class="modal-body"></div>' +
                '<div class="modal-footer">' +
                    '<button type="button" class="btn btn-cancel btn-default"' +
                        ' data-dismiss="modal">Cancel</button>' +
                    '<button class="btn btn-success btn-ok">OK</button>' +
                '</div>' +
            '</div>' +
        '</div>' +
    '</div>');

    var okCancelModal = function (title, text, success_callback,
                                  cancel_callback, closed_callback,
                                  ok_label, cancel_label) {
        var $mok = $("#modal-ok-cancel");
        if ($mok.length == 0) {
            $mok = modalBase;
            $("body").append($mok);
        }
        if (cancel_callback != null || cancel_label != null) {
            cancel_label = cancel_label == null ? "Cancel" : cancel_label;
            $mok.find(".btn-cancel").text(cancel_label).show();
        } else {
            $mok.find(".btn-cancel").hide();
        }
        $mok.find(".modal-header").text(title);
        $mok.find(".modal-body").html(text);
        $mok.data("success", false);
        ok_label = ok_label == null ? "OK" : ok_label;
        $mok.find(".btn-ok").text(ok_label).off("click").on("click", function () {
            $mok.data("success", true).modal("hide");
        });
        $mok.off("shown.bs.model").on("shown.bs.modal", function () {
            $mok.find(".btn-ok").focus();
        }).off("hidden.bs.modal").on("hidden.bs.modal", function (e) {
            if (closed_callback != null) {
                closed_callback(e);
            }
            if (success_callback != null && $mok.data("success")) {
                success_callback(e);
            } else if (cancel_callback != null && !$mok.data("success")) {
                cancel_callback(e);
            }
        }).modal();
    };

    var okModal = function (title, text, closed_callback) {
        okCancelModal(title, text, null, null, closed_callback);
    };

    var loadingAnim = '<div class="loading-overlay">' +
                      '<div class="sk-folding-cube">' +
                      '<div class="sk-cube1 sk-cube"></div>' +
                      '<div class="sk-cube2 sk-cube"></div>' +
                      '<div class="sk-cube4 sk-cube"></div>' +
                      '<div class="sk-cube3 sk-cube"></div>' +
                      '</div>' +
                      '<div class="bolt"><i class="fa fa-bolt"></i></div>' +
                      '</div>';

    $.fn.loadingOverlay = function( action ) {
        if (action == "show") {
            return this.each(function(i, ele) {
                var $ele = $(ele);
                var $loadingOverlay = $ele.find(".loading-overlay");
                if ($loadingOverlay.length) {
                    $loadingOverlay.fadeIn();
                } else {
                    var overlay = $(loadingAnim);
                    overlay.appendTo($ele).fadeIn();
                }
            });
        } else if (action == "hide") {
            return this.each(function(i, ele) {
                $(ele).find(".loading-overlay").hide();
            });
        } else {
            okModal("Unknown loadingOverlay action: " + action);
        }
    };

    var loadingModal = (function () {
        var $dialog = $(
            '<div id="loading-modal" class="modal fade"' +
            ' data-backdrop="static" data-keyboard="false"' +
            ' tabindex="-1" role="dialog" aria-hidden="true">' +
            '<div class="modal-dialog modal-m">' +
            '<div class="modal-content">' +
            loadingAnim +
            '</div></div></div>');

        return {
            show: function (hideCallback) {
                $dialog.off("hidden.bs.modal");
                if (hideCallback !== undefined) {
                    $dialog.on("hidden.bs.modal", hideCallback);
                }
                $dialog.modal();
            },
            hide: function () {
                $dialog.modal("hide");
            }
        };
    })();

    return {
        okCancelModal: okCancelModal,
        okModal: okModal,
        loadingModal: loadingModal
    }
})();
module.exports = ui;
