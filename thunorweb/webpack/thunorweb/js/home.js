import { ajax } from './modules/ajax'
import { initDatasetTable } from './modules/dataset_table'

export const home = {
    activate: function() {
        var callbackFn = function (data, type, full, meta) {
            return "<a href=\"" + ajax.url("page_view_dataset",
                    full.id) +  "\">" + full.name + "</a>";
        };
        initDatasetTable(callbackFn);
    }
}
