from django import forms
from django.contrib.auth import get_user_model
from .models import Game, GameParticipation, Group, GroupMembership
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from django.db.models.functions import Lower
User = get_user_model()

from django import forms
from .models import Group

class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name", "description"]
        labels = {"name": "Nome", "description": "Descrição"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
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


from django import forms
from django.db.models import Q
from .models import GameParticipation

class GameParticipationForm(forms.ModelForm):
    class Meta:
        model = GameParticipation
        fields = ["player", "final_balance"]

    def __init__(self, *args, game=None, **kwargs):
        super().__init__(*args, **kwargs)
        # 1) Defina o jogo cedo para o full_clean() considerar unique_together
        self.game = game or getattr(self.instance, "game", None)
        if self.game:
            self.instance.game = self.game  # 👈 chave do problema

    def clean_player(self):
        player = self.cleaned_data.get("player")
        game = getattr(self.instance, "game", None)  # já setado no __init__

        if not player or not game:
            return player

        qs = GameParticipation.objects.filter(game=game, player=player)
        if self.instance.pk:               # edição: ignore a própria linha
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise forms.ValidationError("Este jogador já foi adicionado a esta partida.")
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

class SignUpForm(UserCreationForm):
    username = forms.CharField(
        label="Usuário",
        max_length=150,
        help_text="Obrigatório. Até 150 caracteres. Letras, dígitos e @/./+/-/_ apenas.",
        widget=forms.TextInput(attrs={"placeholder": "Seu usuário"})
    )
    
    email = forms.EmailField(
        required=True,
        help_text="Obrigatório. Informe um email válido."
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")