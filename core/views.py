from tokenize import group
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import IntegrityError, models, transaction
from django.db.models import Case, When, Value, IntegerField
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView
from .forms import GameForm, GameParticipationForm, LoginForm, SignUpForm, GroupForm
from .models import Group, GroupMembership, Game, GamePost, GameParticipation, GroupRequest
from .services import create_group_with_admin
from django.http import HttpResponseForbidden

def group_admin_required(view_func):
    def _wrapped_view(request, slug, *args, **kwargs):
        group = get_object_or_404(Group, slug=slug)
        is_admin = GroupMembership.objects.filter(
            group=group, user=request.user, role=GroupMembership.Role.ADMIN
        ).exists()
        if not is_admin:
            return HttpResponseForbidden("Você não é admin deste grupo.")
        return view_func(request, slug, *args, **kwargs)
    return _wrapped_view


@login_required
def group_list_view(request):
    groups = (
        Group.objects
        .filter(
            id__in=GroupMembership.objects
                .filter(user=request.user)
                .values("group_id")
        )
        .select_related("created_by")
        .annotate(
            member_count=models.Count("memberships", distinct=True),
            post_count=models.Count("posts", distinct=True),
            last_post=models.Max("posts__posted_at"),
        )
        .order_by("name")
    )
    group_b = groups.filter(name="b").first()
    return render(request, "group_list.html", {"groups": groups})

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
                .prefetch_related(models.Prefetch("posts", queryset=posts_qs))
                )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        posts = self.object.posts.all()


        memberships = (
            GroupMembership.objects
            .filter(group=self.object)
            .select_related("user")
            .annotate(
                role_order=Case(
                    When(user=self.object.created_by, then=Value(0)),  # criador
                    When(role=GroupMembership.Role.ADMIN, then=Value(1)),
                    When(role=GroupMembership.Role.MEMBER, then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                )
            )
            .order_by("role_order", "user__username")
        )


        is_member = GroupMembership.objects.filter(user=self.request.user, group=self.object).exists()
        is_admin = GroupMembership.objects.filter(user=self.request.user, group=self.object, role=GroupMembership.Role.ADMIN).exists()

        context["already_requested"] = GroupRequest.objects.filter(group=self.object, requested_by=self.request.user).exists()
        context["is_admin"] = is_admin
        context["join_requests"] = GroupRequest.objects.filter(group=self.object).select_related("requested_by") if is_admin else []
        context["recent_posts"] = posts[:10]
        context["recent_games"] = [p.game for p in context["recent_posts"]]
        context["total_posts"] = posts.count()
        context["memberships"] = memberships  # <<< usar no template
        context["players"] = [gm.user for gm in memberships]  # se algo ainda usar
        context["is_member"] = is_member
        return context

@login_required
@group_admin_required
def group_promote_member_view(request, slug, user_id):
    if request.method != "POST":
        messages.error(request, "Operação inválida.")
        return redirect("core:group_detail", slug=slug)

    group = get_object_or_404(Group, slug=slug)
    target_user = get_object_or_404(User, pk=user_id)

    if target_user == group.created_by:
        messages.info(request, "O criador já possui privilégios máximos.")
        return redirect("core:group_detail", slug=slug)

    gm = GroupMembership.objects.filter(group=group, user=target_user).first()
    if not gm:
        messages.error(request, "Usuário não é membro deste grupo.")
        return redirect("core:group_detail", slug=slug)

    if gm.role == GroupMembership.Role.ADMIN:
        messages.info(request, f"{target_user.username} já é administrador.")
    else:
        gm.role = GroupMembership.Role.ADMIN
        gm.save(update_fields=["role"])
        messages.success(request, f"{target_user.username} agora é administrador.")

    return redirect("core:group_detail", slug=slug)


@login_required
@group_admin_required
def group_demote_admin_view(request, slug, user_id):
    if request.method != "POST":
        messages.error(request, "Operação inválida.")
        return redirect("core:group_detail", slug=slug)

    group = get_object_or_404(Group, slug=slug)
    target_user = get_object_or_404(User, pk=user_id)

    if target_user == group.created_by:
        messages.error(request, "Você não pode remover privilégios do criador do grupo.")
        return redirect("core:group_detail", slug=slug)

    gm = GroupMembership.objects.filter(group=group, user=target_user).first()
    if not gm:
        messages.error(request, "Usuário não é membro deste grupo.")
        return redirect("core:group_detail", slug=slug)

    if gm.role != GroupMembership.Role.ADMIN:
        messages.info(request, f"{target_user.username} já não é administrador.")
    else:
        gm.role = GroupMembership.Role.MEMBER
        gm.save(update_fields=["role"])
        messages.success(request, f"Privilégios de administrador removidos de {target_user.username}.")

    return redirect("core:group_detail", slug=slug)


@login_required
@group_admin_required
def group_remove_member_view(request, slug, user_id):
    if request.method != "POST":
        messages.error(request, "Operação inválida.")
        return redirect("core:group_detail", slug=slug)

    group = get_object_or_404(Group, slug=slug)
    target_user = get_object_or_404(User, pk=user_id)

    if target_user == group.created_by:
        messages.error(request, "Você não pode remover o criador do grupo.")
        return redirect("core:group_detail", slug=slug)
    if target_user == request.user:
        messages.info(request, "Para sair do grupo, use o botão 'Sair do grupo'.")
        return redirect("core:group_detail", slug=slug)

    deleted, _ = GroupMembership.objects.filter(group=group, user=target_user).delete()
    if deleted:
        messages.success(request, f"{target_user.username} foi removido do grupo.")
    else:
        messages.info(request, "Este usuário não era membro do grupo.")

    return redirect("core:group_detail", slug=slug)



@login_required
def group_create_view(request):
    if request.method == "POST":
        form = GroupForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    create_group_with_admin(
                        name=form.cleaned_data["name"],
                        description=form.cleaned_data.get("description", ""),
                        created_by=request.user,
                    )
            except IntegrityError:
                form.add_error("name", "Já existe um grupo com este nome.")
            else:
                messages.success(request, "Grupo criado!")
                return redirect(reverse("core:group_list"))
    else:
        form = GroupForm()

    return render(request, "group_create.html", {"form": form})

@login_required
def group_join_request_view(request, slug):
    if request.method != "GET":
        messages.error(request, "Operação inválida.")
        return redirect("core:group_detail", slug=slug)

    try:
        group = (
            Group.objects
            .select_related("created_by")
            .annotate(member_count=models.Count("memberships__user", distinct=True))
            .get(slug=slug)
        )
    except Group.DoesNotExist:
        messages.error(request, "Grupo não encontrado.")
        return redirect("core:group_list")


    membership = GroupMembership.objects.filter(group=group, user=request.user).exists()
    if membership:
        messages.info(request, f"Você já é membro de “{group.name}”.")
        return redirect("core:group_detail", slug=slug)

    invite = GroupRequest.objects.filter(group=group, requested_by=request.user).first()

    return render(
        request,
        "group_request.html",
        context={
            "already_member": membership,
            "already_requested": bool(invite),
            "group": group,
        },
    )

@login_required
def group_create_join_request_view(request, slug):
    if request.method != "POST":
        messages.error(request, "Operação inválida.")
        return redirect("core:group_detail", slug=slug)

    group = get_object_or_404(Group, slug=slug)

    membership = GroupMembership.objects.filter(group=group, user=request.user).exists()
    if membership:
        messages.info(request, f"Você já é membro de “{group.name}”.")
        return redirect("core:group_detail", slug=slug)

    invite = GroupRequest.objects.filter(group=group, requested_by=request.user).first()
    if invite:
        messages.info(request, f"Você já solicitou para entrar em “{group.name}”. Aguarde aprovação.")
        return redirect("core:group_detail", slug=slug)
    
    GroupRequest.objects.create(group=group, requested_by=request.user)
    return render(request, "group_request.html", context={"already_member": membership, "already_requested": invite, "group": group})

@login_required
@group_admin_required
def group_accept_request_view(request, slug, request_id):
    if request.method != "POST":
        messages.error(request, "Operação inválida.")
        return redirect("core:group_detail", slug=slug)

    group = get_object_or_404(Group, slug=slug)
    join_request = get_object_or_404(GroupRequest, id=request_id, group=group)

    GroupMembership.objects.get_or_create(user=join_request.requested_by, group=group, defaults={"role": GroupMembership.Role.MEMBER})
    GroupRequest.objects.filter(id=request_id).delete()
    messages.success(request, f"Pedido de {join_request.requested_by.username} aceito. Ele agora é membro de “{group.name}”.")
    return redirect("core:group_detail", slug=slug)

@login_required
@group_admin_required
def group_reject_request_view(request, slug, request_id):
    if request.method != "POST":
        messages.error(request, "Operação inválida.")
        return redirect("core:group_detail", slug=slug)

    group = get_object_or_404(Group, slug=slug)
    join_request = get_object_or_404(GroupRequest, id=request_id, group=group)

    GroupRequest.objects.filter(id=request_id).delete()
    messages.info(request, f"Pedido de {join_request.requested_by.username} rejeitado.")
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

    from_group = request.GET.get("from_group")

    session_key = f"last_group_for_game_{pk}"
    if from_group:
        request.session[session_key] = from_group
    else:
        from_group = request.session.get(session_key)

    back_group = None
    if from_group:
        is_valid = GamePost.objects.filter(
            game=game,
            group__slug=from_group,
        ).exists()

        if is_valid:
            back_group = Group.objects.only("name", "slug").filter(slug=from_group).first()
        else:
            request.session.pop(session_key, None)

    participations = game.participations.select_related("player").all()
    total_pot = sum((p.final_balance + (p.rebuy or 0) for p in participations))
    return render(
        request,
        "game_detail.html",
        {
            "game": game,
            "participations": participations,
            "back_group": back_group,
            "total_pot": total_pot,
        },
    )


@login_required
def participation_add_view(request, pk: int):
    game = get_object_or_404(Game, pk=pk)
    if request.method == "POST":
        form = GameParticipationForm(request.POST, game=game)
        if form.is_valid():
            try:
                form.save()
                return redirect("core:game_detail", pk=game.pk)
            except IntegrityError:
                form.add_error("player", "Este jogador já foi adicionado a esta partida.")
    else:
        form = GameParticipationForm(game=game)

    return render(request, "participation_add.html", {"form": form, "game": game})


class RememberMeLoginView(LoginView):
    template_name = "account/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True  # já logado vai pro destino

    def form_valid(self, form):
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
            login(request, user)
            return redirect("core:group_list")
    else:
        form = SignUpForm()
    return render(request, "account/signup.html", {"form": form})

def logout_view(request):
    logout(request)
    return redirect("core:login")