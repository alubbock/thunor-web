"use strict";
var ui = (function() {
    var modalBase = $(
        '<div class="modal fade" tabindex="-1" role="dialog"' +
        ' aria-hidden="true" data-success="false">' +
        '<div class="modal-dialog">' +
            '<div class="modal-content">' +
                '<div class="modal-header"></div>' +
                '<div class="modal-body"></div>' +
                '<div class="modal-footer">' +
                    '<button type="button" class="btn btn-cancel"' +
                        ' data-dismiss="modal"></button>' +
                    '<button class="btn btn-ok"></button>' +
                '</div>' +
            '</div>' +
        '</div>' +
    '</div>');

    var modalDefaults = {
        title: "Information",
        okLabel: "OK",
        cancelLabel: "Cancel",
        focusButton: true,
        onCancelHide: undefined,
        onCancelHidden: undefined,
        onOKHide: undefined,
        onOKHidden: undefined,
        onHide: undefined,
        onHidden: undefined,
        onShow: undefined,
        okButtonClass: "btn-success",
        cancelButtonClass: "btn-default",
        cancelByDefault: false
    };

    var okCancelModal = function (modalSettings) {
        var $mok = modalBase.clone();
        var settings = $.extend({}, modalDefaults, modalSettings);
        var $cancelBtn = $mok.find(".btn-cancel")
                         .addClass(settings.cancelButtonClass);
        var $okBtn = $mok.find(".btn-ok").addClass(settings.okButtonClass);
        if (settings.cancelLabel !== null) {
            $cancelBtn.text(settings.cancelLabel).show();
        } else {
            $cancelBtn.hide();
        }
        $mok.find(".modal-header").text(settings.title);
        $mok.find(".modal-body").html(settings.text);
        if (settings.okLabel === null) {
            $okBtn.hide();
        } else {
            $okBtn.text(
                settings.okLabel).on("click", function () {
                $mok.data("success", true).modal("hide");
            });
        }
        $mok.on("shown.bs.modal", function (e) {
            if(settings.onShow !== undefined) {
                settings.onShow(e);
            }
            if(settings.focusButton !== false) {
                $mok.find(settings.cancelByDefault ? ".btn-cancel" : ".btn-ok").focus();
            }
        }).on("hide.bs.modal", function (e) {
            if($mok.data("success")) {
                if(settings.onOKHide !== undefined) {
                    return settings.onOKHide(e);
                }
            } else {
                if(settings.onCancelHide !== undefined) {
                    settings.onCancelHide(e);
                }
            }
            if(settings.onHide !== undefined) {
                settings.onHide(e);
            }
        }).on("hidden.bs.modal", function(e) {
            if($mok.data("success")) {
                if(settings.onOKHidden !== undefined) {
                    settings.onOKHidden(e);
                }
            } else {
                if(settings.onCancelHidden !== undefined) {
                    settings.onCancelHidden(e);
                }
            }
            if(settings.onHidden !== undefined) {
                settings.onHidden(e);
            }
            $(e.currentTarget).remove();
        }).appendTo("body").modal();
        return $mok;
    };

    var okModal = function (modalSettings) {
        return okCancelModal($.extend(modalSettings, {cancelLabel: null}));
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
            okModal({
                title: "Error",
                text: "Unknown loadingOverlay action: " + action
            });
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
