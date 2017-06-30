var ui = require("./modules/ui"),
    ajax = require("./modules/ajax");

var activateSelect = function($select) {
  $select.selectpicker({actionsBox: true});
  $select.on("changed.bs.select", function() {
    $(this).closest("form").find("button[type=submit]").show();
  });
};

var activate = function() {
    $("#btn-add-tag").click(function () {
        var $select = $(".tag-container").last().clone(true).prependTo(".tag-list")
            .show().find("select");
        activateSelect($select);
    });
    $("form.set-tag-name").submit(function (e) {
        e.preventDefault();
        var $form = $(this);
        var tagName = $form.find("input[name=tagName]").val();
        if (tagName === "") {
            ui.okModal("Tag name empty", "Please enter a tag name");
            return;
        }
        if ($.inArray(tagName, pyHTS.state.tagNames) !== -1) {
            ui.okModal("Tag already exists", "A tag with that name already " +
                    "exists");
            return;
        }
        var $tagContainer = $form.closest(".tag-container");
        var $taggingForm = $tagContainer.find("form.set-tag-targets");
        $tagContainer.find(".tag-name").text(tagName);
        $taggingForm.find("input[name=tagName]").val(tagName);
        $form.hide();
        $taggingForm.show();
        $tagContainer.find("form.delete-tag").show();
    });
    $("form.set-tag-targets").submit(function (e) {
        var $form = $(this);
        $.ajax({
            type: "POST",
            headers: {"X-CSRFToken": ajax.getCsrfToken()},
            url: ajax.url("assign_tag"),
            data: $form.serialize(),
            success: function () {
                $form.find("button[type=submit]").hide();
                ui.okModal("Tag updated", "Tag changes saved");
            }
        });
        e.preventDefault();
    });
    $(".btn-cancel").click(function () {
        $(this).closest(".tag-container").remove();
    });
    $("form.delete-tag").submit(function (e) {
        var $form = $(this);
        $.ajax({
            type: "POST",
            headers: {"X-CSRFToken": ajax.getCsrfToken()},
            url: ajax.url("assign_tag"),
            data: $form.serialize(),
            success: function () {
                $form.closest(".tag-container").remove();
                ui.okModal("Tag deleted", "Tag deleted");
            }

        });
        e.preventDefault();
    });

    activateSelect($(".tag-container").not(":last").find("select"));
};

module.exports = {
  activate: activate
};
