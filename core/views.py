from tokenize import group
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.contrib import messages
from django.db.models import Prefetch
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView
from .forms import GameForm, GameParticipationForm
from .forms import LoginForm, SignUpForm
from .models import Group, GroupMembership, Game, GamePost, GameParticipation
from .services import create_group_with_admin

# @method_decorator(login_required, name='dispatch')
class GroupListView(ListView):
    template_name = "group_list.html"
    context_object_name = "groups"

    def get_queryset(self):
        return [gm.group for gm in GroupMembership.objects.filter(user=self.request.user)]

# @method_decorator(login_required, name='dispatch')
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
        players = [gm.user for gm in GroupMembership.objects.filter(group=self.object).select_related("user")]
        is_member = GroupMembership.objects.filter(user=self.request.user, group=self.object).exists()

        context["recent_posts"] = posts[:10]
        context["recent_games"] = [p.game for p in context["recent_posts"]]
        context["total_posts"] = posts.count()
        context["players"] = players
        context["is_member"] = is_member
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
def group_join_view(request, slug):
    if request.method != "POST":
        messages.error(request, "Operação inválida.")
        return redirect("core:group_detail", slug=slug)

    group = get_object_or_404(Group, slug=slug)

    # Evita duplicado; torna a operação idempotente
    membership, created = GroupMembership.objects.get_or_create(
        user=request.user,
        group=group,
        defaults={"role": GroupMembership.Role.MEMBER},
    )

    if created:
        messages.success(request, f"Você entrou no grupo “{group.name}”.")
    else:
        messages.info(request, f"Você já é membro de “{group.name}”.")
    return redirect("core:group_detail", slug=slug)


@login_required
def group_leave_view(request, slug):
    if request.method != "POST":
        messages.error(request, "Operação inválida.")
        return redirect("core:group_detail", slug=slug)

    group = get_object_or_404(Group, slug=slug)
    deleted, _ = GroupMembership.objects.filter(user=request.user, group=group).delete()
    if deleted:
        messages.success(request, f"Você saiu de “{group.name}”.")
    else:
        messages.info(request, f"Você não era membro de “{group.name}”.")
    return redirect("core:group_list")


@login_required
def group_delete_view(request, slug):
    group = get_object_or_404(Group, slug=slug)
    membership = GroupMembership.objects.filter(user=request.user, group=group, role=GroupMembership.Role.ADMIN).first()
    if not membership:
        raise Http404("Você não tem permissão para deletar este grupo.")
    if request.method == "POST":
        group.delete()
        messages.success(request, "Grupo deletado.")
        return HttpResponseRedirect(reverse("core:group_list"))
    return render(request, "group_list.html", {"group": group})


@login_required
def game_create_view(request):
    """
    Cria uma partida e, opcionalmente, já a “posta” em 1+ grupos.
    """
    if request.method == "POST":
        form = GameForm(request.POST, user=request.user)
        group_ids = request.POST.getlist("groups")
        
        if not group_ids:
            messages.error(request, "Selecione pelo menos um grupo.")
        elif form.is_valid():
            game = form.save(commit=False)
            game.created_by = request.user
            game.save()

            # Post em grupos selecionados (ids em request.POST.getlist("groups"))
            for gid in group_ids:
                group = Group.objects.filter(pk=gid).first()
                if group:
                    GamePost.objects.get_or_create(game=game, group=group, defaults={"posted_by": request.user})

            messages.success(request, "Partida criada!")
            return HttpResponseRedirect(reverse("core:game_detail", args=[game.pk]))
    else:
        form = GameForm(user=request.user)
    groups = [gm.group for gm in GroupMembership.objects.filter(user=request.user)]
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