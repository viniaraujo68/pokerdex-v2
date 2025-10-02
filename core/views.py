from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import IntegrityError, models, transaction
from django.db.models import Case, When, Value, IntegerField
from django.forms import model_to_dict
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.urls import reverse_lazy
from django.views.generic import DetailView
from .forms import GameForm, GameParticipationForm, LoginForm, SignUpForm, GroupForm
from .models import Group, GroupMembership, Game, GamePost, GameParticipation, GroupRequest
from .services import create_group_with_admin
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_http_methods

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
    my_groups = (
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

    other_groups = Group.objects.exclude(id__in=GroupMembership.objects
                .filter(user=request.user)
                .values("group_id")).order_by("name")
    return render(request, "group_list.html", {"my_groups": my_groups, "other_groups": other_groups})

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
    print("GROUP: ", group)
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

    if GroupMembership.objects.filter(group=group, user=request.user).exists():
        messages.info(request, f"Você já é membro de “{group.name}”.")
        return redirect("core:group_detail", slug=slug)

    invite = GroupRequest.objects.filter(group=group, requested_by=request.user).first()
    if invite:
        messages.info(request, f"Você já solicitou para entrar em “{group.name}”. Aguarde aprovação.")
        return redirect("core:group_detail", slug=slug)

    GroupRequest.objects.create(group=group, requested_by=request.user)
    return redirect("core:group_join_request", slug=slug)

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
    is_creator = group.created_by_id == request.user.id

    if is_creator:
        # Find the oldest admin (excluding the creator)
        oldest_admin = (
            GroupMembership.objects
            .filter(group=group, role=GroupMembership.Role.ADMIN)
            .exclude(user=request.user)
            .order_by("joined_at")
            .select_related("user")
            .first()
        )
        if oldest_admin:
            group.created_by = oldest_admin.user
            group.save(update_fields=["created_by"])

            messages.info(request, f"O título de criador foi transferido para {oldest_admin.user.username}.")
        else:
            # No admins, pick the oldest member (excluding the creator)
            oldest_member = (
            GroupMembership.objects
            .filter(group=group)
            .exclude(user=request.user)
            .order_by("joined_at")
            .select_related("user")
            .first()
            )
            if oldest_member:
                group.created_by = oldest_member.user
                group.save(update_fields=["created_by"])
                # Promove o novo criador a ADMIN
                oldest_member.role = GroupMembership.Role.ADMIN
                oldest_member.save(update_fields=["role"])
                messages.info(request, f"O título de criador de {group} foi transferido para {oldest_member.user.username}.")
            else:
                # No one left to transfer, just delete the group
                group.delete()
                messages.success(request, f"Você era o último membro. O grupo “{group.name}” foi deletado.")
                return redirect("core:group_list")

    deleted, _ = GroupMembership.objects.filter(user=request.user, group=group).delete()

    if deleted:
        messages.success(request, f"Você saiu de “{group.name}”.")
    else:
        messages.info(request, f"Você não era membro de “{group.name}”.")
    return redirect("core:group_list")

@login_required
@group_admin_required
@require_http_methods(["GET", "POST"])
def group_edit_view(request, slug):
    group = get_object_or_404(Group, slug=slug)

    # só admins (decorator já garante) — criador idem
    form = GroupForm(request.POST or None, request.FILES or None, instance=group)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Grupo atualizado!")
        return redirect("core:group_detail", slug=group.slug)

    return render(request, "edit_form_generic.html", {
        "form": form,
        "title": f"Editar grupo: {group.name}",
        "submit_label": "Salvar alterações",
        "back_url": reverse("core:group_detail", kwargs={"slug": group.slug}),
    })
@login_required
@group_admin_required
def group_delete_view(request, slug):
    group = get_object_or_404(Group, slug=slug)
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

    session_key = f"last_group_for_game_{pk}"

    # 1) Captura robusta do slug: GET -> sessão -> None
    candidate_slug = (request.GET.get("from_group") or request.session.get(session_key) or "").strip() or None
    print("candidate_slug:", candidate_slug)

    from_group = None
    if candidate_slug:
        # Tenta carregar o Group primeiro
        grp = Group.objects.only("id", "name", "slug").filter(slug=candidate_slug).first()
        print("group_obj_found?", bool(grp))

        is_valid = False
        if grp:
            # Validação 1: jogo pertence ao grupo via M2M?
            in_m2m = game.groups.filter(pk=grp.pk).exists()
            print("in_m2m:", in_m2m)
            if in_m2m:
                is_valid = True
            else:
                # Validação 2: existe GamePost com esse jogo e esse grupo?
                posted = GamePost.objects.filter(game_id=pk, group_id=grp.pk).exists()
                print("posted_via_gamepost:", posted)
                if posted:
                    is_valid = True

        if is_valid:
            from_group = grp
            request.session[session_key] = grp.slug
        else:
            # inválido → limpar sessão
            request.session.pop(session_key, None)

    # Permissões de edição
    is_creator = request.user.is_authenticated and (game.created_by_id == request.user.id)
    is_group_creator = request.user.is_authenticated and Group.objects.filter(
        id__in=game.groups.values_list("id", flat=True),
        created_by=request.user,
    ).exists()
    can_edit_game = is_creator or is_group_creator

    participations = game.participations.select_related("player").all()

    buy_in = game.buy_in or 0
    total_pot = sum((buy_in + (p.rebuy or 0)) for p in participations)

    print("from_group:", from_group)
    return render(
        request,
        "game_detail.html",
        {
            "game": game,
            "participations": participations,
            "from_group": from_group,
            "total_pot": total_pot,
            "can_edit_game": can_edit_game,
        },
    )

@login_required
@require_http_methods(["GET", "POST"])
def game_edit_view(request, pk: int):
    game = get_object_or_404(Game, pk=pk)
    is_group_creator = Group.objects.filter(
        id__in=game.groups.values_list("id", flat=True),
        created_by=request.user
    ).exists()
    
    if game.created_by_id != request.user.id and not is_group_creator:
        return HttpResponseForbidden("Você não pode editar esta partida.")

    # inicial selecionando grupos já “postados”
    posted_group_ids = list(
        GamePost.objects.filter(game=game).values_list("group_id", flat=True)
    )

    # form precisa de user para limitar os grupos que aparecem
    form = GameForm(
        request.POST or None,
        user=request.user,
        instance=game,
    )
    # deixe os grupos marcados na tela GET
    if request.method == "GET":
        form.fields["groups"].initial = posted_group_ids

    if request.method == "POST" and form.is_valid():
        game = form.save()  # já mantém created_by igual
        # sincronizar os GamePosts com o que veio do form
        new_group_ids = list(map(int, request.POST.getlist("groups")))

        # cria posts novos
        to_add = set(new_group_ids) - set(posted_group_ids)
        for gid in to_add:
            group = Group.objects.filter(pk=gid).first()
            if group:
                GamePost.objects.get_or_create(
                    game=game,
                    group=group,
                    defaults={"posted_by": request.user},
                )

        # remove posts que saíram
        to_remove = set(posted_group_ids) - set(new_group_ids)
        if to_remove:
            GamePost.objects.filter(game=game, group_id__in=to_remove).delete()

        messages.success(request, "Partida atualizada!")
        return redirect("core:game_detail", pk=game.pk)

    return render(request, "edit_form_generic.html", {
        "form": form,
        "title": f"Editar partida: {game.title}",
        "submit_label": "Salvar alterações",
        "back_url": reverse("core:game_detail", kwargs={"pk": game.pk}),
    })

@login_required
@require_http_methods(["POST"])
def game_delete_view(request, pk: int):
    game = get_object_or_404(Game, pk=pk)
    is_group_creator = Group.objects.filter(
        id__in=game.groups.values_list("id", flat=True),
        created_by=request.user
    ).exists()
    if game.created_by_id != request.user.id and not is_group_creator:
        return HttpResponseForbidden("Você não pode excluir esta partida.")
    game.delete()
    messages.success(request, "Partida excluída.")
    return redirect("core:group_list")

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

@login_required
@require_http_methods(["GET", "POST"])
def participation_edit_view(request, pk: int, part_id: int):
    game = get_object_or_404(Game, pk=pk)
    participation = get_object_or_404(GameParticipation, pk=part_id, game=game)

    # regra: quem pode editar? criador do jogo; opcionalmente o próprio jogador.
    is_game_owner = (game.created_by_id == request.user.id)
    is_self = (participation.player_id == request.user.id)
    is_group_creator = Group.objects.filter(
        id__in=game.groups.values_list("id", flat=True),
        created_by=request.user
    ).exists()

    if not (is_game_owner or is_self or is_group_creator):
        return HttpResponseForbidden("Sem permissão para editar esta participação.")

    form = GameParticipationForm(
        request.POST or None,
        game=game,
        instance=participation,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Participação atualizada.")
        return redirect("core:game_detail", pk=game.pk)

    return render(request, "edit_form_generic.html", {
        "form": form,
        "title": f"Editar participação de {participation.player.username}",
        "submit_label": "Salvar alterações",
        "back_url": reverse("core:game_detail", kwargs={"pk": game.pk}),
    })


@login_required
@require_http_methods(["POST"])
def participation_delete_view(request, pk: int, part_id: int):
    game = get_object_or_404(Game, pk=pk)
    participation = get_object_or_404(GameParticipation, pk=part_id, game=game)

    is_game_owner = (game.created_by_id == request.user.id)
    is_self = (participation.player_id == request.user.id)
    if not (is_game_owner or is_self):
        return HttpResponseForbidden("Sem permissão para excluir esta participação.")

    participation.delete()
    messages.success(request, "Participação removida.")
    return redirect("core:game_detail", pk=game.pk)
class RememberMeLoginView(LoginView):
    template_name = "account/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True  # já logado vai pro destino

    def form_valid(self, form):
        remember = form.cleaned_data.get("remember_me")
        self.request.session.set_expiry(60*60*24*14 if remember else 0)
        return super().form_valid(form)
    

class PasswordResetView(auth_views.PasswordResetView):
    template_name = "account/password_reset.html"
    email_template_name = "account/password_reset_email.txt"
    subject_template_name = "account/password_reset_subject.txt"
    success_url = reverse_lazy("core:password_reset_done")
    from_email = "teampokerdex@gmail.com"  # defina seu remetente

class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "account/password_reset_done.html"

class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "account/password_reset_confirm.html"
    success_url = reverse_lazy("core:password_reset_complete")

class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "account/password_reset_complete.html"
    
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