from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL


class Group(models.Model):
    """
    Um grupo onde partidas podem ser postadas.
    Todo usuário pode criar novos grupos. O criador vira admin automaticamente.
    """
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=False)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="groups_created")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            candidate = base
            i = 1
            while Group.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                i += 1
                candidate = f"{base}-{i}"
            self.slug = candidate
        super().save(*args, **kwargs)


class GroupMembership(models.Model):
    """
    Associação entre usuário e grupo. 'role' define admin ou membro.
    """
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MEMBER = "MEMBER", "Member"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="group_memberships")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("user", "group")
        indexes = [
            models.Index(fields=["group", "user"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.user} @ {self.group} ({self.role})"


class GroupInvite(models.Model):
    """
    Convite para participar de um grupo.
    Pode ser enviado por email ou por user id (simples). Aceitação vira membership.
    """
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="invites")
    invited_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="invites_sent")
    email = models.EmailField(blank=True)  # alternativa: convites por e-mail
    invited_user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="invites_received"
    )
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["group"]),
            models.Index(fields=["token"]),
        ]

    def __str__(self):
        target = self.invited_user or self.email or "invitee"
        return f"Invite({target}) -> {self.group}"


class Game(models.Model):
    """
    Uma partida de poker. Pode ser postada em 1+ grupos.
    """
    title = models.CharField(max_length=140, blank=True)
    date = models.DateField(default=timezone.localdate)
    location = models.CharField(max_length=180, blank=True)
    buy_in = models.DecimalField(
        "Cacife (buy-in)", max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="games_created")
    created_at = models.DateTimeField(default=timezone.now)

    # Grupos onde esta partida foi postada
    groups = models.ManyToManyField(Group, through="GamePost", related_name="games")

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        label = self.title or f"Partida em {self.date}"
        return f"{label} - buy-in {self.buy_in}"


class GamePost(models.Model):
    """
    Relação explícita da partida com um grupo (postagem da partida no grupo).
    Mantemos quem postou e quando.
    """
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="posts")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="posts")
    posted_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="game_posts")
    posted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("game", "group")
        indexes = [
            models.Index(fields=["group", "game"]),
        ]

    def __str__(self):
        return f"{self.game} @ {self.group}"


class GameParticipation(models.Model):
    """
    Participação de um jogador em uma partida, com o saldo final.
    'final_balance' é o resultado líquido do jogador (pode ser negativo).
    """
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="participations")
    player = models.ForeignKey(User, on_delete=models.PROTECT, related_name="game_participations")
    final_balance = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("game", "player")
        indexes = [
            models.Index(fields=["game"]),
            models.Index(fields=["player"]),
        ]

    def __str__(self):
        return f"{self.player} in {self.game} -> {self.final_balance}"
