import { ui } from './modules/ui'
import { ajax } from './modules/ajax'
import { util } from './modules/util'

const activateSelect = function($select, $modal) {
  $select.selectpicker({actionsBox: true, iconBase: "fa", tickIcon: "fa-check"});
  $select.on("show.bs.select", function() {
      // disable automatic modal closing when pressing ESC/clicking on background
      var modalData = $modal.data("bs.modal");
      $modal.off("keydown.dismiss.bs.modal");
      modalData.options.backdrop = "static";
      // disable modal buttons during edit
      $modal.find(".btn-danger,.btn-ok").prop("disabled", true);
  }).on("hide.bs.select", function() {
    $(this).closest("form").submit();
  });
};

const set_tag_group_permission = function(tag_id, group_id, state, $caller) {
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

const clearTagNameChange = function() {
    $(".rename-tag-btn").show();
    $(".rename-tag-div").addClass("hidden");
    $(".tag-header").show();
    $("form.delete-tag").show();
};

const activate = function() {
    var entityType = $('#entity-type').val();
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
        rowId: function(row) {return row.tag.id;},
        select: {style: 'multi+shift'},
        dom: 'lBfrtip',
        buttons: [
            'selectAll',
            'selectNone',
            {
                text: 'Download',
                extend: 'selected',
                action: function ( e, dt, node, config ) {
                    var sep = '\t';
                    var rowDat = dt.rows({selected: true}).data();
                    var entLabel = (entityType === 'drugs') ? 'drug' : 'cell_line';
                    var txt = 'tag_name' + sep + 'tag_category' + sep + entLabel + '\n';
                    for (var i=0, imax=rowDat.length; i < imax; i++) {
                        var row = rowDat[i];
                        for(var j=0, jmax=row.targets.length; j<jmax; j++) {
                            txt += row.tag.name + sep + row.cat + sep + row.targets[j] + '\n';
                        }
                    }
                    FileSaver.saveAs(new Blob([txt], {type: "text/tab-separated-values"}),
                        'tags.txt'
                    );
                }
            },
            {
                text: 'Permissions',
                extend: 'selected',
                action: function( e, dt, node, config ) {
                    var tagIds = dt.rows({selected: true}).ids();
                    var numTags = tagIds.length;
                    if (numTags === 0) {
                        return;
                    }
                    var ajaxUrl = ajax.url('get_tag_groups', entityType) + '?';
                    for (var t=0;t<numTags;t++) {
                        ajaxUrl += 'tagId=' + tagIds[t] + '&';
                    }
                var $modal = ui.okModal({
                        title: 'Set tag permissions',
                        text: 'Loading...',
                        okLabel: 'Close'
                    });

                    $.ajax({
                        type: "GET",
                        url: ajaxUrl,
                        success: function (data) {
                            var $container = $(".tag-container").last().clone(true).show();
                            // prepopulate groups
                            var $groupPerms = $container.find(".group-permissions");
                            for (var g=0; g<data.groups.length; g++) {
                                var $groupInputDiv = $('.group-perm').last().clone().show();
                                var group = data.groups[g];
                                var numTagsGroup = group.tagIds.length;
                                $groupInputDiv.find("input")
                                    .data('tag-id', tagIds)
                                    .data('group-id', group.groupId)
                                    .prop('checked', numTagsGroup === numTags)
                                    .data('indeterminate', numTagsGroup > 0 && numTagsGroup < numTags);
                                $groupInputDiv.find('.group-name').text(group.groupName);
                                $groupPerms.append($groupInputDiv);
                            }
                            if(data.groups.length) {
                                $groupPerms.show();
                            }
                            $container.addClass("panel-default");
                            $container.find(".panel-body").show();
                            $container.find(".entity-change").hide();
                            $container.find("form.set-tag-name").hide();
                            $container.find("input[type=checkbox]").bootstrapSwitch({
                                'onSwitchChange': function(event, state) {
                                    var $target = $(event.currentTarget);
                                    set_tag_group_permission(
                                        $.makeArray($target.data('tag-id')),
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
                }
            },
            {
                text: 'Copy',
                extend: 'selected',
                action: function(e, dt) {
                    var tagIds = dt.rows({selected: true}).ids();
                    var $container = $(".tag-copy-container").last().clone().show();
                    var $form = $container.find("form");
                    var $tagId = $form.find("input[name=tagId]").val(tagIds[0]);
                    for(var t=1;t<tagIds.length;t++) {
                        $tagId.clone().val(tagIds[t]).insertAfter($tagId);
                    }
                    $form.find('input[name=copyMode]').change(function(e) {
                        var showTagName = $(e.target).val() !== 'separate' || tagIds.length === 1;
                        $form.find(".hts-tag-name").toggle(showTagName);
                        $form.find("input[name=tagName]").prop("disabled", !showTagName);
                    });
                    if(tagIds.length === 1) {
                        $form.find(".hts-tag-name").show();
                        $form.find("input[name=tagName]").prop("disabled", false);
                    }
                    ui.okCancelModal({
                        title: 'Copy tags',
                        text: $container,
                        okLabel: 'Copy tags',
                        onOKHide: function() {
                            $container.loadingOverlay("show");
                            $.ajax({
                                type: "POST",
                                headers: {"X-CSRFToken": ajax.getCsrfToken()},
                                url: ajax.url("copy_tags"),
                                data: $form.serialize(),
                                success: function () {
                                    $tagTable.ajax.reload();
                                },
                                error: ajax.ajaxErrorCallback,
                                complete: function() {
                                    $container.loadingOverlay("hide");
                                }
                            });
                        }
                    });
                }
            },
            {
                text: 'Delete',
                extend: 'selected',
                action: function(e, dt) {
                    var tagIds = dt.rows({selected: true}).ids();
                    var tagStr = tagIds.length === 1 ? 'tag' : 'tags';
                    var tagType = $('input[name=tagType]').val();
                    ui.okCancelModal({
                        title: 'Delete tags',
                        text: 'Delete '+tagIds.length+' '+tagStr + '? This action is irreversible.',
                        okLabel: 'Delete tags',
                        okButtonClass: "btn-danger",
                        onOKHide: function() {
                            ui.loadingModal.show();
                            $.ajax({
                                type: "POST",
                                headers: {"X-CSRFToken": ajax.getCsrfToken()},
                                url: ajax.url("delete_tag"),
                                data: {
                                    tagId: $.makeArray(tagIds),
                                    tagType: tagType
                                },
                                success: function () {
                                    $tagTable.ajax.reload();
                                    ui.okModal({title: 'Tags deleted', text: 'Tags deleted successfully'});
                                },
                                error: ajax.ajaxErrorCallback,
                                complete: function() {
                                    ui.loadingModal.hide();
                                }
                            });
                        }
                    });
                }
            }
        ],
        "columnDefs": [
            {"targets": 0, className: "select-checkbox", width: "20px", orderable: false, defaultContent: '', data: null},
            {"targets": 1, "data": "tag", "width": "1px", "className": "text-center", "render": {
                "display": function(data) {return util.userIcon(data.ownerEmail);},
                "sort": function(data) {return data.ownerEmail;}}
            },
            {"targets": 2, "data": "tag", "width": "25%", "render":
                function(data) {
                    if (!data.editable) return data.name;
                    return '<a href="#" data-id="' + data.id + '">' + data.name + '</a>';
                }
            },
            {"targets": 3, "data": "cat", "width": "25%"},
            {"targets": 4, "data": "targets", "render":
                function(data) {
                    var str = '';
                    for (var t=0,len=data.length; t<len; t++) {
                        str += '<label class="label label-primary">' + data[t] + '</label> ';
                    }
                    return str;
                }
            }
        ],
        "order": [[3, "asc"], [2, "asc"]],
        "drawCallback": function () {
            $('.tt').tooltip();
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
                clearTagNameChange();
                $tagTable.ajax.reload();
            }
        });

        $.ajax({
            type: "GET",
            url: ajax.url("get_tag_targets", entityType) + tagId,
            success: function (data) {
                var $container = $(".tag-container").last().clone(true).show();
                // set up select box with current entries preselected
                for (var i=0, len=data.targets.length; i<len; i++) {
                    $container.find('option').filter('[value='+data.targets[i]+']').prop('selected', true);
                }
                activateSelect($container.find("select"), $modal);
                // prepopulate form data
                $container.find(".tag-name").text(data.tagName);
                $container.find("input[name=tagsName]").val(data.tagName);
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
                $container.addClass("panel-default");
                $container.find(".panel-heading,.panel-body").show();
                $container.find("form.set-tag-name").hide();
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
            focusButton: false,
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
    $("form.rename-tag-form").submit(function(e) {
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
            url: ajax.url("rename_tag"),
            data: $form.serialize(),
            success: function (data) {
                clearTagNameChange();
                $tagTable.ajax.reload();
                $container.find(".tag-name").text(data.tagName);
                $container.find(".tag-category").text(data.tagCategory === null ? '' : data.tagCategory);
            },
            error: ajax.ajaxErrorCallback,
            complete: function() {
                $container.loadingOverlay("hide");
            }
        });
    });
    $(".rename-tag-btn").click(function(e) {
        e.preventDefault();
        $(".rename-tag-btn").hide();
        $(".rename-tag-div").removeClass("hidden");
        $(".tag-header").hide();
        $("form.delete-tag").hide();
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
            error: ajax.ajaxErrorCallback,
            complete: function() {
                $container.loadingOverlay("hide");
                // re-enable ESC/click on background to close modal
                var $modal = $container.closest(".modal");
                var modalData = $modal.data("bs.modal");
                modalData.escape();
                modalData.options.backdrop = true;
                // re-enable modal close button, delete button
                $modal.find(".btn-danger,.btn-ok").prop("disabled", false);
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

export const tag_editor = {
    activate: activate
}
