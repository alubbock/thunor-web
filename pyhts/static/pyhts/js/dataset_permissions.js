"use strict";

var ui = require("./modules/ui"),
    ajax = require("./modules/ajax");

var set_dataset_group_permission = function(dataset_id, group_id, perm_id,
                                            state, $caller) {
    $.ajax({type: 'POST',
            url: ajax.url("set_dataset_group_permission"),
            headers: { 'X-CSRFToken': ajax.getCsrfToken() },
            data: {
                'dataset_id': dataset_id,
                'group_id': group_id,
                'perm_id': perm_id,
                'state': state
            },
            error: function(jqXHR, textStatus, errorThrown) {
                if ($caller != null) {
                    $caller.bootstrapSwitch('state', !state, true);
                }
                ajax.ajaxErrorCallback(jqXHR, textStatus, errorThrown);
            },
            complete: function() {
                ui.loadingModal.hide();
            },
            dataType: 'json'});
};

var dataset_permissions = function() {
    $("input[type=checkbox]").bootstrapSwitch({
        'onSwitchChange': function(event, state) {
            var $target = $(event.currentTarget);
            ui.loadingModal.show();
            set_dataset_group_permission(
                $('#dataset-id').val(),
                $target.data('group-id'),
                $target.data('perm-id'),
                state,
                $target
            );
        }
    });
};

module.exports = {
    activate: dataset_permissions
};
