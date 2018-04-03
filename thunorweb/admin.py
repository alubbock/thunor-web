from .forms import GroupAdminForm
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from .models import HTSDataset
from django.utils import timezone

admin.site.site_header = 'Thunor Administration'
admin.site.site_title = 'Thunor Admin'


class GroupAdmin(admin.ModelAdmin):
    form = GroupAdminForm
    filter_horizontal = ['permissions']

    def get_fieldsets(self, request, obj=None):
        if request.user.is_superuser:
            fieldsets = super(GroupAdmin, self).get_fieldsets(request, obj)
        else:
            # Non-superusers can't see group permissions
            fieldsets = ((None, {'fields': ('name', 'users')}), )

        return fieldsets

    def get_queryset(self, request):
        return Group.objects.exclude(name='Public')

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and 'permissions' in \
                form.cleaned_data:
            raise PermissionDenied()
        super(GroupAdmin, self).save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return obj is None or obj.name != 'Public'


admin.site.unregister(Group)
admin.site.register(Group, GroupAdmin)

# Methods to mark/unmark datasets as deleted


def mark_deleted(modeladmin, request, queryset):
    for obj in queryset:
        modeladmin.log_deletion(request, obj, '{} marked deleted'.format(obj))
    queryset.update(deleted_date=timezone.now())


mark_deleted.short_description = 'Mark as deleted'


def unmark_deleted(modeladmin, request, queryset):
    for obj in queryset:
        modeladmin.log_addition(request, obj, 'Unmark deleted')
    queryset.update(deleted_date=None)


unmark_deleted.short_description = 'Unmark as deleted'


# Admin classes for HTS Datasets and deleted datasets


class BaseHTSDatasetAdmin(admin.ModelAdmin):
    readonly_fields = ['creation_date']
    actions = [mark_deleted]
    list_display = ['name', 'owner', 'creation_date']

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super(BaseHTSDatasetAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions


class HTSDatasetAdmin(BaseHTSDatasetAdmin):
    def get_queryset(self, request):
        return HTSDataset.objects.exclude(deleted_date__isnull=False)


admin.site.register(HTSDataset, HTSDatasetAdmin)


class DeletedHTSDatasetAdmin(BaseHTSDatasetAdmin):
    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return HTSDataset.objects.exclude(deleted_date__isnull=True)


class DeletedHTSDataset(HTSDataset):
    class Meta:
        proxy = True
        verbose_name = 'Deleted HTS Dataset'


admin.site.register(DeletedHTSDataset, DeletedHTSDatasetAdmin)
