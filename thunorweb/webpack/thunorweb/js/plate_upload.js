import { ui } from './modules/ui'
import { ajax } from './modules/ajax'

const activate = function () {
    var ajaxSettings = {
        headers: {"X-CSRFToken": ajax.getCsrfToken()}
    };

    var pyHTSLockNext2 = function () {
        $("#hts-next-2").find("button").prop("disabled", true);
    };

    var pyHTSUnlockNext2 = function () {
        $("#hts-next-2").find("button").prop("disabled", false);
    };

    var createFileUploadScreen = function (dataset_id) {
        $("#js-upload-files").fileinput({
            theme: "fa",
            uploadUrl: ajax.url("upload_platefile"),
            uploadAsync: false,
            deleteUrl: ajax.url("delete_platefile"),
            allowedFileExtensions: ["xls", "xlsx", "txt", "csv", "tsv", "h5"],
            maxFileSize: 153600,
            maxFileCount: 20,
            minFileCount: 1,
            fileActionSettings: {
                showUpload: false,
                showZoom: false,
                showDrag: false
            },
            showBrowse: false,
            browseOnZoneClick: true,
            allowedPreviewTypes: false,
            initialPreview: pyHTS.state.initialPreview,
            initialPreviewConfig: pyHTS.state.initialPreviewConfig,
            overwriteInitial: false,
            uploadExtraData: {
                dataset_id: dataset_id
            },
            ajaxSettings: ajaxSettings,
            ajaxDeleteSettings: ajaxSettings
        }).on("filelock", pyHTSLockNext2)
            .on("filereset", pyHTSLockNext2)
            .on("filebatchuploadcomplete", pyHTSUnlockNext2)
            .on("fileuploaded", pyHTSUnlockNext2)
            .on("filebatchselected", function() {
                $(this).fileinput("upload");
            });
    };

    var createDataset = function (name) {
        if (name === "") {
            ui.okModal({
                title: "Error creating dataset",
                text: "Please enter a name for this dataset",
                onHidden: function () {
                    $("input[name=dataset-name]").focus();
                }
            });
            return false;
        }
        var $htsDatasetUpload1 = $("#hts-dataset-upload-1");
        $htsDatasetUpload1.loadingOverlay("show");
        $.ajax({
            type: "POST",
            url: ajax.url("create_dataset"),
            headers: {"X-CSRFToken": ajax.getCsrfToken() },
            data: {"name": name},
            success: function (data) {
                var newUrl = ajax.url("page_upload_platefile", data.id);
                if (window.history.replaceState) {
                    window.history.replaceState(null, null, newUrl);
                }
                $("#hts-next-2").prop("href",
                    ajax.url("page_annotate_dataset", data.id));
                $("#hts-back-to-dataset").prop("href",
                    ajax.url("page_view_dataset", data.id));
                createFileUploadScreen(data.id);
                $htsDatasetUpload1.slideUp();
                $("#hts-dataset-upload-2").slideDown();
            },
            error: ajax.ajaxErrorCallback,
            complete: function() {
                $htsDatasetUpload1.loadingOverlay("hide");
            },
            dataType: "json"
        });
    };

    $("#hts-next-1").click(function () {
        createDataset($("input[name=dataset-name]").val());
    });

    $("input[name=dataset-name]").keyup(function (e) {
        var btn_selected = $("#hts-next-1");
        btn_selected.prop("disabled", $(this).val() === "");
        if (e.which === 13) {
            btn_selected.click();
        }
    }).focus();

    if(pyHTS.state.datasetId !== null) {
        createFileUploadScreen(pyHTS.state.datasetId);
    }

    if(pyHTS.state.initialPreview.length > 0) {
        pyHTSUnlockNext2();
    }
};

export const plate_upload = {
    activate: activate
};
