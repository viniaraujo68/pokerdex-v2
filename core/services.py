from django.db import transaction
from django.utils.crypto import get_random_string
from django.contrib.auth import get_user_model
from .models import Group, GroupMembership, Game, GamePost, GameParticipation
User = get_user_model()


@transaction.atomic
def create_group_with_admin(*, name: str, created_by: User, description: str = "") -> Group:
    group = Group.objects.create(name=name, description=description, created_by=created_by)
    GroupMembership.objects.create(user=created_by, group=group, role=GroupMembership.Role.ADMIN)
    return group


def make_invite_token() -> str:
    return get_random_string(48)