from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.contrib import messages
from django.db.models import Prefetch
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views.generic import ListView, DetailView
from .forms import GameForm, GameParticipationForm
from .forms import LoginForm, SignUpForm
from .models import Group, GroupMembership, Game, GamePost, GameParticipation
from .services import create_group_with_admin


class GroupListView(ListView):
    template_name = "group_list.html"
    context_object_name = "groups"
    queryset = Group.objects.all()

class GroupDetailView(DetailView):
    model = Group
    template_name = "group_detail.html"
    context_object_name = "group"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        posts_qs = (GamePost.objects
                    .select_related("game", "posted_by", "group")
                    .order_by("-posted_at"))
        return (Group.objects
                .prefetch_related(Prefetch("posts", queryset=posts_qs))
                )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        posts = self.object.posts.all()

        context["recent_posts"] = posts[:10]
        context["recent_games"] = [p.game for p in context["recent_posts"]]
        context["total_posts"] = posts.count()
        return context


@login_required
def group_create_view(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        if not name:
            messages.error(request, "Informe um nome para o grupo.")
        else:
            group = create_group_with_admin(name=name, created_by=request.user, description=description)
            messages.success(request, "Grupo criado!")
            return HttpResponseRedirect(reverse("core:group_list"))
    return render(request, "group_create.html")


@login_required
def game_create_view(request):
    """
    Cria uma partida e, opcionalmente, já a “posta” em 1+ grupos.
    """
    if request.method == "POST":
        form = GameForm(request.POST)
        if form.is_valid():
            game = form.save(commit=False)
            game.created_by = request.user
            game.save()

            # Post em grupos selecionados (ids em request.POST.getlist("groups"))
            group_ids = request.POST.getlist("groups")
            for gid in group_ids:
                group = Group.objects.filter(pk=gid).first()
                if group:
                    GamePost.objects.get_or_create(game=game, group=group, defaults={"posted_by": request.user})

            messages.success(request, "Partida criada!")
            return HttpResponseRedirect(reverse("core:game_detail", args=[game.pk]))
    else:
        form = GameForm()
    groups = Group.objects.all()
    return render(request, "game_create.html", {"form": form, "groups": groups})


def game_detail_view(request, pk: int):
    game = get_object_or_404(Game, pk=pk)
    participations = game.participations.select_related("player").all()
    return render(request, "game_detail.html", {"game": game, "participations": participations})


@login_required
def participation_add_view(request, pk: int):
    """
    Adiciona um jogador e seu saldo final a uma partida.
    """
    game = get_object_or_404(Game, pk=pk)
    if request.method == "POST":
        form = GameParticipationForm(request.POST)
        if form.is_valid():
            participation = form.save(commit=False)
            participation.game = game
            participation.save()
            messages.success(request, "Participação adicionada!")
            return HttpResponseRedirect(reverse("core:game_detail", args=[game.pk]))
    else:
        form = GameParticipationForm()
    return render(request, "participation_add.html", {"game": game, "form": form})


class RememberMeLoginView(LoginView):
    template_name = "account/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True  # já logado vai pro destino

    def form_valid(self, form):
        # controla expiração da sessão pelo checkbox remember_me
        remember = form.cleaned_data.get("remember_me")
        self.request.session.set_expiry(60*60*24*14 if remember else 0)
        return super().form_valid(form)
    
def signup_view(request):
    if request.user.is_authenticated:
        return redirect("core:group_list")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            # loga automaticamente após cadastro
            login(request, user)
            return redirect("core:group_list")
    else:
        form = SignUpForm()
    return render(request, "account/signup.html", {"form": form})

def logout_view(request):
    logout(request)
    return redirect("core:login")