from django import forms
from django.contrib.auth import get_user_model
from .models import Game, GameParticipation, Group, GroupMembership
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
User = get_user_model()


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


class GameParticipationForm(forms.ModelForm):
    class Meta:
        model = GameParticipation
        fields = ["player", "final_balance"]

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