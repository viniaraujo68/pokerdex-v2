from django.contrib import admin
from . import models


@admin.register(models.Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_by", "created_at")
    search_fields = ("name", "slug", "description", "created_by__username")
    list_filter = ("created_at",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(models.GroupMembership)
class GroupMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "group", "role", "joined_at")
    list_filter = ("role", "joined_at")
    search_fields = ("user__username", "group__name")


@admin.register(models.GroupInvite)
class GroupInviteAdmin(admin.ModelAdmin):
    list_display = ("group", "invited_user", "email", "token", "created_at", "accepted_at", "revoked_at")
    list_filter = ("created_at", "accepted_at", "revoked_at")
    search_fields = ("group__name", "invited_user__username", "email", "token")


class GameParticipationInline(admin.TabularInline):
    model = models.GameParticipation
    extra = 1


@admin.register(models.Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("__str__", "date", "location", "buy_in", "created_by", "created_at")
    list_filter = ("date", "created_at")
    search_fields = ("title", "location", "created_by__username")
    inlines = [GameParticipationInline]


@admin.register(models.GamePost)
class GamePostAdmin(admin.ModelAdmin):
    list_display = ("game", "group", "posted_by", "posted_at")
    list_filter = ("posted_at", "group")
    search_fields = ("game__title", "group__name", "posted_by__username")


@admin.register(models.GameParticipation)
class GameParticipationAdmin(admin.ModelAdmin):
    list_display = ("game", "player", "final_balance", "created_at")
    list_filter = ("created_at",)
    search_fields = ("game__title", "player__username")
