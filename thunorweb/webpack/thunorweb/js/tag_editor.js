var ui = require("./modules/ui"),
    ajax = require("./modules/ajax");

var activateSelect = function($select) {
  $select.selectpicker({actionsBox: true, iconBase: "fa", tickIcon: "fa-check"});
  $select.on("changed.bs.select", function() {
    $(this).closest("form").find("button[type=submit]").show();
  });
};

var activate = function() {
    $("#btn-add-tag,#btn-add-public-tag").click(function () {
        var $container = $(".tag-container").last().clone(true).prependTo(".tag-list")
            .fadeIn(400);
        if(this.id === "btn-add-public-tag") {
            $container.removeClass("panel-default").addClass("panel-primary")
                .find(".tag-name").after(" <span class=\"badge badge-primary\">Public</span>");
            $container.find("input[name=tagPublic]").val("1");
        }
        activateSelect($container.find("select"));
        $container.find("input").focus();
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
        var tagIsPublic = $form.find("input[name=tagPublic]").val() === "1";
        var existingTagArray = tagIsPublic ? pyHTS.state.publicTagNames : pyHTS.state.privateTagNames;
        if ($.inArray(tagName, existingTagArray) !== -1) {
            ui.okModal({
                title: "Tag already exists",
                text: "A tag with that name already exists"
            });
            return;
        }
        existingTagArray.push(tagName);
        var $tagContainer = $form.closest(".tag-container");
        var $taggingForm = $tagContainer.find("form.set-tag-targets");
        $tagContainer.find(".tag-name").text(tagName);
        $tagContainer.find("input[name=tagName]").val(tagName);
        $tagContainer.find(".tag-header").show();
        $form.hide();
        $taggingForm.slideDown();
        $tagContainer.find("form.delete-tag").show();
    });
    $("form.set-tag-targets").submit(function (e) {
        var $form = $(this);
        var $container = $form.closest(".tag-container");
        $container.loadingOverlay("show");
        $.ajax({
            type: "POST",
            headers: {"X-CSRFToken": ajax.getCsrfToken()},
            url: ajax.url("assign_tag"),
            data: $form.serialize(),
            success: function () {
                $form.find("button[type=submit]").hide();
                $container.find(".label-success").fadeIn(400).delay(2000).fadeOut(400);
            },
            error: ajax.ajaxErrorCallback,
            complete: function() {
                $container.loadingOverlay("hide");
            }
        });
        e.preventDefault();
    });
    $(".btn-cancel").click(function () {
        $(this).closest(".tag-container").remove();
    });
    $("form.delete-tag").submit(function (e) {
        var $form = $(this);
        var $container = $form.closest(".tag-container");
        $container.loadingOverlay("show");
        var tagName = $form.find("input[name=tagName]").val();
        var targetTagNamesArray = $form.find("input[name=tagPublic]").val() === "1" ? pyHTS.state.publicTagNames : pyHTS.state.privateTagNames;
        $.ajax({
            type: "POST",
            headers: {"X-CSRFToken": ajax.getCsrfToken()},
            url: ajax.url("assign_tag"),
            data: $form.serialize(),
            success: function () {
                $container.remove();
                var index = $.inArray(tagName, targetTagNamesArray);
                if (index !== -1) {
                    targetTagNamesArray.splice(index, 1);
                }
            },
            error: ajax.ajaxErrorCallback,
            complete: function() {
                $container.loadingOverlay("hide");
            }
        });
        e.preventDefault();
    });

    activateSelect($(".tag-container").not(":last").find("select"));
};

module.exports = {
  activate: activate
};
