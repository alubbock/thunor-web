from .forms import GroupAdminForm
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied


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

    def delete_model(self, request, obj):
        # Don't allow deletion of Public group
        if obj is not None and obj.name == 'Public':
            raise PermissionDenied()
        super(GroupAdmin, self).delete_model(request, obj)


admin.site.unregister(Group)
admin.site.register(Group, GroupAdmin)
