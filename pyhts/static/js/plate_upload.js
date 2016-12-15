var plate_upload = function () {
    var ui = require("./modules/ui"),
        ajax = require("./modules/ajax");

    var pyHTSLockNext2 = function () {
        $('#hts-next-2').hide();
    };

    var pyHTSUnlockNext2 = function () {
        $('#hts-next-2').show();
    };

    var createFileUploadScreen = function (dataset_id) {
        $("#js-upload-files").fileinput({
            uploadUrl: '/ajax/platefile/upload',
            uploadAsync: false,
            deleteUrl: '/ajax/platefile/delete',
            allowedFileExtensions: ['xls', 'xlsx',
                'txt', 'csv', 'tsv'],
            maxFileSize: 102400,
            maxFileCount: 20,
            minFileCount: 1,
            initialPreview: pyHTS.state.initialPreview,
            initialPreviewConfig: pyHTS.state.initialPreviewConfig,
            overwriteInitial: false,
            uploadExtraData: {
                dataset_id: dataset_id
            },
            ajaxSettings: pyHTS.state.ajaxSettings,
            ajaxDeleteSettings: pyHTS.state.ajaxSettings
        }).on('filelock', pyHTSLockNext2)
            .on('filereset', pyHTSLockNext2)
            .on('filebatchuploadcomplete', pyHTSUnlockNext2)
            .on('fileuploaded', pyHTSUnlockNext2);
    };

    var createDataset = function (name) {
        if (name == '') {
            ui.okModal('Error creating dataset',
                'Please enter a name for this dataset',
                function () {
                    $('input[name=dataset-name]').focus();
                });
            return false;
        }
        $.ajax({
            type: 'POST',
            url: '/ajax/dataset/create',
            headers: {'X-CSRFToken': pyHTS.state.csrfToken},
            data: {'name': name},
            success: function (data) {
                if (data.id) {
                    if (window.history.replaceState) {
                        window.history.replaceState(null, null,
                            '/dataset/' + data.id + '/upload');
                    }
                    $('#hts-next-2').prop('href',
                        '/dataset/' + data.id + '/annotate');
                    createFileUploadScreen(data.id);
                    $('#hts-dataset-upload-1').slideUp();
                    $('#hts-dataset-upload-2').slideDown();
                } else {
                    ui.okModal('Error', 'Unknown Error');
                    throw new Error('Unexpected response from server', data);
                }
            },
            error: ajax.ajaxErrorCallback,
            dataType: 'json'
        });
    };

    $('#hts-next-1').click(function () {
        createDataset($('input[name=dataset-name]').val());
    });

    $('input[name=dataset-name]').keyup(function (e) {
        var btn_selected = $('#hts-next-1');
        if ($(this).val() == '') {
            btn_selected.hide();
        } else {
            btn_selected.show();
        }
        if (e.which == 13) {
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

module.exports = {
    activate: plate_upload
};
