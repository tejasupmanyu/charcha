from django.contrib import admin
from .models import Team, TeamMember

class TeamMemberAdmin(admin.TabularInline):
    model = TeamMember

class TeamAdmin(admin.ModelAdmin):
    fields = ('name', 'is_public')
    list_display = ('name', 'members')
    readonly_fields = ('members', )

    inlines = (TeamMemberAdmin, )

    def members(self, team):
        if team.is_public:
            return 'public'
        else:
            usernames = [member.user.username for member in team.members.all()]
            return ", ".join(usernames)

admin.site.register(Team, TeamAdmin)
