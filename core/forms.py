from django import forms
from django.contrib.auth import get_user_model
from .models import Game, GameParticipation
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
User = get_user_model()


class GameForm(forms.ModelForm):
    class Meta:
        model = Game
        fields = ["title", "date", "location", "buy_in"]


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
    email = forms.EmailField(
        required=True,
        help_text="Obrigatório. Informe um email válido."
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")