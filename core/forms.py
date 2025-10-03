from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db.models import Count, Q
from django.db.models.functions import Lower
from .models import Game, GameParticipation, Group, GroupMembership
User = get_user_model()

class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name", "description"]
        labels = {"name": "Nome", "description": "Descrição"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
            "description": forms.Textarea(attrs={"class": "text-light form-control", "rows": 4}),
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Informe um nome para o grupo.")
        return name

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("name")
        if name and Group.objects.annotate(n=Lower("name")).filter(n=name.lower()).exists():
            self.add_error("name", "Já existe um grupo com este nome.")

class GameForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="",
    )

    class Meta:
        model = Game
        fields = ["title", "date", "location", "buy_in"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "buy_in": forms.NumberInput(
                attrs={
                    "class": "form-control money-input",
                    "inputmode": "decimal", 
                    "step": "1.00", 
                    "placeholder": "2500,00"
                },
            )
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].queryset = Group.objects.filter(
            id__in=GroupMembership.objects.filter(user=user).values_list("group_id", flat=True)
        )

        if self.fields["groups"].queryset.exists():
            self.fields["groups"].label = "Postar em grupos"

    def clean_groups(self):
        groups = self.cleaned_data.get("groups")
        if not groups:
            raise forms.ValidationError("A partida deve ser postada em pelo menos um grupo.")
        return groups



User = get_user_model()

class GameParticipationForm(forms.ModelForm):
    class Meta:
        model = GameParticipation
        fields = ["player", "final_balance", "rebuy"]
        widgets = {
            "final_balance": forms.NumberInput(attrs={
                "step": "1",          # incrementa de 0,50 em 0,50
                "inputmode": "decimal", # teclado numérico no mobile
                "class": "form-control"
            }),
        }

    def __init__(self, *args, game=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = game or getattr(self.instance, "game", None)
        if not self.game:
            return

        self.instance.game = self.game

        group_ids = list(self.game.groups.values_list("id", flat=True))

        if group_ids:
            eligible_players = User.objects.all()
            for gid in group_ids:
                eligible_players = eligible_players.filter(group_memberships__group_id=gid)
            eligible_players = eligible_players.distinct()
        else:
            eligible_players = User.objects.none()
        
        already_in_game = list(
            GameParticipation.objects
            .filter(game=self.game)
            .values_list("player_id", flat=True)
        )

        
        if self.instance.pk and getattr(self.instance, "player_id", None):
            try:
                already_in_game.remove(self.instance.player_id)
            except ValueError:
                pass  

        eligible_players = eligible_players.exclude(pk__in=already_in_game)

        self.fields["player"].queryset = eligible_players.order_by("username")

    def clean_player(self):
        player = self.cleaned_data.get("player")
        game = getattr(self.instance, "game", None)
        if not player or not game:
            return player
 
        qs = GameParticipation.objects.filter(game=game, player=player)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Este jogador já foi adicionado a esta partida.")

        group_ids = list(game.groups.values_list("id", flat=True))
        if group_ids:
            count_in_groups = (
                GroupMembership.objects
                .filter(user=player, group_id__in=group_ids)
                .aggregate(gcount=Count("group_id", distinct=True))
                ["gcount"] or 0
            )
            if count_in_groups < len(group_ids):
                raise forms.ValidationError(
                    "Este jogador não pertence a todos os grupos nos quais a partida foi postada."
                )
        return player



class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Usuário",
        widget=forms.TextInput(attrs={"autofocus": True, "placeholder": "Seu usuário"})
    )
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={"placeholder": "Sua senha"})
    )
    remember_me = forms.BooleanField(
        label="Manter conectado", required=False
    )
    error_messages = {
        "invalid_login": "Usuário ou senha inválidos.",
    }

class SignUpForm(UserCreationForm):
    username = forms.CharField(
        label="Usuário",
        max_length=25,
        help_text="Obrigatório. Até 25 caracteres. Letras, dígitos e @/./+/-/_ apenas.",
        validators=[UnicodeUsernameValidator(message="Informe um nome de usuário válido. Use apenas letras, números e @/./+/-/_")],
        widget=forms.TextInput(attrs={"placeholder": "Seu usuário"})
    )
    
    email = forms.EmailField(
        required=True,
        help_text="Obrigatório. Informe um email válido."
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")