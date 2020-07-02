from django.contrib import admin
from .models import Team

class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    fields = ('name', 'description', 'about', 'gchat_space')
    readonly_fields = ('name', 'gchat_space')

admin.site.register(Team, TeamAdmin)