$.extend(pyHTS.views, {
    "plate_upload": function () {

        var pyHTSLockNext2 = function () {
            $('#hts-next-2').hide();
        };
        pyHTS.pub.pyHTSUnlockNext2 = function () {
            $('#hts-next-2').show();
        };

        pyHTS.pub.createFileUploadScreen = function (dataset_id) {
            $("#js-upload-files").fileinput({
                uploadUrl: '/ajax/platefile/upload',
                uploadAsync: false,
                deleteUrl: '/ajax/platefile/delete',
                allowedFileExtensions: ['xls', 'xlsx',
                    'txt', 'csv', 'tsv'],
                maxFileSize: 2048,
                maxFileCount: 20,
                minFileCount: 1,
                initialPreview: initialPreview,
                initialPreviewConfig: initialPreviewConfig,
                overwriteInitial: false,
                uploadExtraData: {
                    dataset_id: dataset_id
                },
                ajaxSettings: pyHTS.ajaxSettings,
                ajaxDeleteSettings: pyHTS.ajaxSettings
            }).on('filelock', pyHTSLockNext2)
                .on('filereset', pyHTSLockNext2)
                .on('filebatchuploadcomplete', pyHTSUnlockNext2)
                .on('fileuploaded', pyHTSUnlockNext2);
        };

        var createDataset = function (name) {
            if (name == '') {
                pyHTS.ui.okModal('Error creating dataset',
                    'Please enter a name for this dataset',
                    function () {
                        $('input[name=dataset-name]').focus();
                    });
                return false;
            }
            $.ajax({
                type: 'POST',
                url: '/ajax/dataset/create',
                headers: {'X-CSRFToken': pyHTS.csrfToken},
                data: {'name': name},
                success: function (data) {
                    if (data.id) {
                        if (window.history.replaceState) {
                            window.history.replaceState(null, null,
                                '/dataset/' + data.id + '/upload');
                        }
                        $('#hts-next-2').prop('href',
                            '/dataset/' + data.id + '/annotate');
                        pyHTS.pub.createFileUploadScreen(data.id);
                        $('#hts-dataset-upload-1').slideUp();
                        $('#hts-dataset-upload-2').slideDown();
                    } else {
                        pyHTS.ui.okModal('Error', 'Unknown Error');
                        throw new Error('Unexpected response from ' +
                            'server', data);
                    }
                },
                error: pyHTS.ajax.ajaxErrorCallback,
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

    }
});
