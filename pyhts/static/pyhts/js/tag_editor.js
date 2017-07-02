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
        var $container = $(".tag-container").last().clone(true).prependTo(".tag-list")
            .fadeIn(400);
        activateSelect($container.find("select"));
        $container.find("input").focus();
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
        pyHTS.state.tagNames.push(tagName);
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
        $.ajax({
            type: "POST",
            headers: {"X-CSRFToken": ajax.getCsrfToken()},
            url: ajax.url("assign_tag"),
            data: $form.serialize(),
            success: function () {
                $container.remove();
                var index = $.inArray(tagName, pyHTS.state.tagNames);
                if (index !== -1) {
                    pyHTS.state.tagNames.splice(index, 1);
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
