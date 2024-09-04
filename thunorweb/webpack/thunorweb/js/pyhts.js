"use strict";
/*!
 * Thunor
 * Copyright (c) 2016-2018 Alex Lubbock
 */
import { home } from './home'
import { dataset } from './dataset'
import { dataset_permissions } from './dataset_permissions'
import { plots } from './plots'
import { plate_upload } from './plate_upload'
import { plate_mapper } from './plate_mapper'
import { tag_editor } from './tag_editor'

export const views = {
    home: home,
    dataset: dataset,
    dataset_permissions: dataset_permissions,
    plots: plots,
    plate_upload: plate_upload,
    plate_mapper: plate_mapper,
    tag_editor: tag_editor
}
export var state = {}
