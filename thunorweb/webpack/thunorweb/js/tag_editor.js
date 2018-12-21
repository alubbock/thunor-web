var ui = require("./modules/ui"),
    ajax = require("./modules/ajax"),
    util = require("./modules/util");

var activateSelect = function($select) {
  $select.selectpicker({actionsBox: true, iconBase: "fa", tickIcon: "fa-check"});
  $select.on("changed.bs.select", function() {
    $(this).closest("form").find("button[type=submit]").show();
  });
};

var set_tag_group_permission = function(tag_id, group_id, state, $caller) {
    $.ajax({type: 'POST',
            url: ajax.url("set_tag_group_permission"),
            headers: { 'X-CSRFToken': ajax.getCsrfToken() },
            data: {
                'tag_id': tag_id,
                'tag_type': $('#entity-type').val(),
                'group_id': group_id,
                'state': state
            },
            error: function(jqXHR, textStatus, errorThrown) {
                if ($caller != null) {
                    $caller.bootstrapSwitch('state', !state, true);
                }
                ajax.ajaxErrorCallback(jqXHR, textStatus, errorThrown);
            },
            dataType: 'json'});
};

var activate = function() {
    var $tabContent = $(".tab-content");
    $tabContent.loadingOverlay("show");

    var $tagTabs = $("#tag-tabs");
    var defaultTableUrl = $tagTabs.find("li.active").first().data('url');

    var $tagTable = $("#tag-table").DataTable({
        "ajax": {
            "url": defaultTableUrl,
            "timeout": 15000,
            "error": ajax.ajaxErrorCallback,
            "complete": function() {
                $tabContent.loadingOverlay("hide");
            }
        },
        "columnDefs": [
            {"targets": 0, "data": "tag", "width": "0", "render":
                function(data) {
                    return '<i class="fa fa-user" style="color:' + util.stringToColour(data.ownerEmail) +
                        '" title="' + data.ownerEmail + '"></i>';
                }
            },
            {"targets": 1, "data": "tag", "width": "25%", "render":
                function(data) {
                    if (!data.editable) return data.name;
                    return '<a href="#" data-id="' + data.id + '">' + data.name + '</a>';
                }
            },
            {"targets": 2, "data": "cat", "width": "25%"},
            {"targets": 3, "data": "targets", "render":
                function(data) {
                    var str = '';
                    for (var t=0,len=data.length; t<len; t++) {
                        str += '<label class="label label-primary">' + data[t] + '</label> ';
                    }
                    return str;
                }
            }
        ],
        "order": [[2, "asc"], [1, "asc  "]],
        "drawCallback": function () {
            $("#tag-table").find("a").unbind('click').click(function(e){
               e.preventDefault();
               editTag($(this).data('id'));
            });
        }
    });

    var lastTabClick = 0;

    $tagTabs.find("li").click(function (e) {
        e.preventDefault();
        var dateNow = Date.now();
        if (dateNow - lastTabClick < 500) {
            return;
        }
        lastTabClick = dateNow;
        $tabContent.loadingOverlay("show");
        var $this = $(e.currentTarget);
        $tagTable.ajax.url($this.data("url")).load(function() {$tabContent.loadingOverlay("hide")});
        $tagTabs.find("li").removeClass("active");
        $this.addClass("active");
    });

    var editTag = function(tagId) {
        var $modal = ui.okModal({
            title: 'Edit tag',
            text: 'Loading...',
            okLabel: 'Close',
            onHide: function() {
                $tagTable.ajax.reload();
            }
        });

         $.ajax({
            type: "GET",
            url: ajax.url("get_tag_targets", $('#entity-type').val()) + tagId,
            success: function (data) {
                var $container = $(".tag-container").last().clone(true).show();
                // set up select box with current entries preselected
                for (var i=0, len=data.targets.length; i<len; i++) {
                    $container.find('option').filter('[value='+data.targets[i]+']').prop('selected', true);
                }
                activateSelect($container.find("select"));
                // prepopulate form data
                $container.find(".tag-name").text(data.tagName);
                if (data.tagCategory !== null) {
                    $container.find(".tag-category").text(data.tagCategory);
                    $container.find("input[name=tagCategory]").val(data.tagCategory);
                }
                $container.find("input[name=tagId]").val(data.tagId);
                // prepopulate groups
                var $groupPerms = $container.find(".group-permissions");
                for (var g=0; g<data.groups.length; g++) {
                    var $groupInputDiv = $('.group-perm').last().clone().show();
                    $groupInputDiv.find("input")
                        .data('tag-id', data.tagId)
                        .data('group-id', data.groups[g].groupId)
                        .prop('checked', data.groups[g].canView);
                    $groupInputDiv.find('.group-name').text(data.groups[g].groupName);
                    $groupPerms.append($groupInputDiv);
                }
                if(data.groups.length) {
                    $groupPerms.show();
                }
                $container.find(".tag-header").show();
                $container.find("form.set-tag-name").hide();
                $container.find("form.set-tag-targets").show();
                $container.find("form.delete-tag").show();
                $container.find("input[type=checkbox]").bootstrapSwitch({
                    'onSwitchChange': function(event, state) {
                        var $target = $(event.currentTarget);
                        set_tag_group_permission(
                            $target.data('tag-id'),
                            $target.data('group-id'),
                            state,
                            $target
                        );
                    }
                });
                $modal.find(".modal-body").html($container);
            },
            error: function(jqXHR, textStatus, errorThrown) {
                $modal.modal('hide');
                ajax.ajaxErrorCallback(jqXHR, textStatus, errorThrown);
            }
        });
    };

    $("#btn-add-tag").click(function () {
        var $container = $(".tag-container").last().clone(true).show();
        ui.okModal({
            title: 'Add tag',
            text: $container,
            okLabel: 'Close',
            onHide: function() {
                $tagTable.ajax.reload();
            },
            onShow: function() {
                $container.find("input[name=tagsName]").focus();
            }
        });
    });

    $("form.set-tag-name").submit(function (e) {
        e.preventDefault();
        var $form = $(this);
        var tagName = $form.find("input[name=tagsName]").val();
        if (tagName === "") {
            ui.okModal({
                title: "Tag name empty",
                text: "Please enter a tag name"
            });
            return;
        }
        var $container = $form.closest(".tag-container");
        $container.loadingOverlay("show");
        $.ajax({
            type: "POST",
            headers: {"X-CSRFToken": ajax.getCsrfToken()},
            url: ajax.url("create_tag"),
            data: $form.serialize(),
            success: function (data) {
                editTag(data.tagId);
                $container.closest('.modal').modal('hide');
            },
            error: ajax.ajaxErrorCallback,
            complete: function() {
                $container.loadingOverlay("hide");
            }
        });
    });
    $("form.set-tag-targets").submit(function (e) {
        e.preventDefault();
        var $form = $(this);
        var $container = $form.closest(".tag-container");
        $container.loadingOverlay("show");
        $.ajax({
            type: "POST",
            headers: {"X-CSRFToken": ajax.getCsrfToken()},
            url: ajax.url("assign_tag"),
            data: $form.serialize(),
            success: function () {
                $container.closest('.modal').modal('hide');
            },
            error: ajax.ajaxErrorCallback,
            complete: function() {
                $container.loadingOverlay("hide");
            }
        });
    });
    $("form.delete-tag").submit(function (e) {
        e.preventDefault();
        var $form = $(this);
        var $container = $form.closest(".tag-container");
        $container.loadingOverlay("show");
        $.ajax({
            type: "POST",
            headers: {"X-CSRFToken": ajax.getCsrfToken()},
            url: ajax.url("delete_tag"),
            data: $form.serialize(),
            success: function () {
                $container.replaceWith('<div>Tag deleted</div>');
            },
            error: ajax.ajaxErrorCallback,
            complete: function() {
                $container.loadingOverlay("hide");
            }
        });
    });
    var ajaxSettings = {
        headers: {"X-CSRFToken": ajax.getCsrfToken()}
    };
    $('#btn-upload-tags').click(function() {
        var $uploaddiv = $('.upload-tags').first().clone().show();
        var $createEntities = $uploaddiv.find("input[type=checkbox]").bootstrapSwitch();
        $uploaddiv.find('input[type=file]').fileinput({
            theme: "fa",
            uploadUrl: $uploaddiv.find("form").attr('action'),
            uploadAsync: false,
            uploadExtraData: function() {
                return {'createEntities': $createEntities.bootstrapSwitch('state')};
            },
            allowedFileExtensions: ["txt", "csv"],
            maxFileSize: 5120,
            maxFileCount: 5,
            minFileCount: 1,
            fileActionSettings: {
                showUpload: false,
                showZoom: false,
                showDrag: false
            },
            allowedPreviewTypes: false,
            ajaxSettings: ajaxSettings
        }).on("filebatchuploadsuccess", function (event, data) {
            if (data.response !== undefined && data.response.entitiesCreated !== undefined && data.response.entitiesCreated.length > 0) {
                // Easier to just refresh the page, for now...
                window.location.reload(true);

                // for(var i=0;i<data.response.entitiesCreated.length;i++) {
                //     // create cell line/drug in list of entities
                //     var ent = data.response.entitiesCreated[i];
                //     pyHTS.state.entNames[ent['id']] = ent['name'];
                //     // add it to the select
                //     var $lastOpt = $('option[name=EntityId]').last();
                //     $lastOpt.clone().val(ent['id']).text(ent['name']).insertAfter($lastOpt);
                // }
            } else {
                $tagTable.ajax.reload();
                $(this).closest('.modal').modal('hide');
            }
        }).on("filebatchselected", function () {
            $(this).fileinput("upload");
        });

        ui.okCancelModal({
            text: $uploaddiv,
            title: 'Upload tags',
            okLabel: null
        });
    });
};

module.exports = {
  activate: activate
};
