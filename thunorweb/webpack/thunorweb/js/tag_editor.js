var ui = require("./modules/ui"),
    ajax = require("./modules/ajax");

var activateSelect = function($select) {
  $select.selectpicker({actionsBox: true, iconBase: "fa", tickIcon: "fa-check"});
  $select.on("changed.bs.select", function() {
    $(this).closest("form").find("button[type=submit]").show();
  });
};

var activate = function() {
    $("#btn-add-tag").click(function () {
        var $container = $(".tag-container").last().clone(true).prependTo(".tag-list")
            .fadeIn(400);
        activateSelect($container.find("select"));
        $container.find("input[name=tagName]").focus();
    });
    $("form.set-tag-name").submit(function (e) {
        e.preventDefault();
        var $form = $(this);
        var tagName = $form.find("input[name=tagName]").val();
        if (tagName === "") {
            ui.okModal({
                title: "Tag name empty",
                text: "Please enter a tag name"
            });
            return;
        }
        var tagCategory = $form.find("input[name=tagCategory]").val();
        if (tagCategory.trim() === '') tagCategory = null;
        var catExists = pyHTS.state.tags.hasOwnProperty(tagCategory);
        if (catExists && pyHTS.state.tags[tagCategory].hasOwnProperty(tagName)) {
            ui.okModal({
                title: "Tag already exists",
                text: "A tag with that name already exists in the specified" +
                " category"
            });
            return;
        }
        if(!catExists) {
            pyHTS.state.tags[tagCategory] = {};
        }
        pyHTS.state.tags[tagCategory][tagName] = [];
        var $tagContainer = $form.closest(".tag-container");
        var $taggingForm = $tagContainer.find("form.set-tag-targets");
        $tagContainer.find(".tag-name").text(tagName);
        if (tagCategory !== null) {
            $tagContainer.find(".tag-category").text(tagCategory);
            $tagContainer.find("input[name=tagCategory]").val(tagCategory);
        }
        $tagContainer.find("input[name=tagName]").val(tagName);

        $tagContainer.find(".tag-header").show();
        $form.hide();
        $tagContainer.find(".btn-edit").trigger('click');
        $taggingForm.slideDown();
        $tagContainer.find("form.delete-tag").show();
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
            success: function (data) {
                $form.find("button[type=submit]").hide();
                $container.find(".label-success").fadeIn(400).delay(2000).fadeOut(400);
                pyHTS.state.tags[data.tagCategory][data.tagName] = data.entityIds;
                var $entNameTemplate = $('#ent-name-tplt');
                var entities = $('<div></div>');
                for (var i=0, len=data.entityIds.length; i<len; i++) {
                    entities.append($entNameTemplate.clone().removeAttr("id").show().text(pyHTS.state.tagNames[data.entityIds[i]]));
                    entities.append(' ');
                }
                console.log(entities);
                $container.find('.btn-edit').show();
                $container.find(".entity-change").hide();
                $container.find(".entity-options").empty().append(entities).show();
            },
            error: ajax.ajaxErrorCallback,
            complete: function() {
                $container.loadingOverlay("hide");
            }
        });
    });
    $(".btn-cancel").click(function () {
        $(this).closest(".tag-container").remove();
    });
    $(".btn-edit").click(function() {
        var $btnEdit = $(this);
        var $tagContainer = $btnEdit.closest(".tag-container");
        var $newSelect = $('.entity-select').last().clone().show();
        var $form = $btnEdit.closest('form');
        var tagCategory = $form.find('input[name=tagCategory]').val();
        if(tagCategory === '') tagCategory = null;
        var tagName = $form.find('input[name=tagName]').val();
        var entities = pyHTS.state.tags[tagCategory][tagName];
        for (var i=0, len=entities.length; i<len; i++) {
            $newSelect.find('option').filter('[value='+entities[i]+']').prop('selected', true);
        }
        $tagContainer.find(".entity-options").hide();
        $tagContainer.find(".entity-change").html($newSelect).show();
        activateSelect($newSelect.find("select"));
        $btnEdit.hide();
        $tagContainer.find(".btn-cancel-edit-tag").click(function() {
            $tagContainer.find(".entity-change").empty();
            $tagContainer.find(".entity-options").show();
            $btnEdit.show();
        })
    });
    $("form.delete-tag").submit(function (e) {
        var $form = $(this);
        var $container = $form.closest(".tag-container");
        $container.loadingOverlay("show");
        var tagName = $form.find("input[name=tagName]").val();
        var tagCategory = $form.find("input[name=tagCategory]").val();
        if(tagCategory === '') tagCategory = null;
        $.ajax({
            type: "POST",
            headers: {"X-CSRFToken": ajax.getCsrfToken()},
            url: ajax.url("assign_tag"),
            data: $form.serialize(),
            success: function () {
                $container.remove();
                delete pyHTS.state.tags[tagCategory][tagName];
            },
            error: ajax.ajaxErrorCallback,
            complete: function() {
                $container.loadingOverlay("hide");
            }
        });
        e.preventDefault();
    });
};

module.exports = {
  activate: activate
};
