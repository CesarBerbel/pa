from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect


class InternalAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Base dos dois níveis de acesso da área interna.

    A verificação vive em `has_access()` para poder ser chamada no início de um
    dispatch() personalizado, antes de a view carregar o objeto. Sem isso, uma
    view que inspecione o objeto para decidir o redirecionamento revela o
    estado desse objeto a quem nem sequer tem permissão.
    """

    def has_access(self):
        raise NotImplementedError

    def test_func(self):
        return self.request.user.is_authenticated and self.has_access()

    def handle_no_permission(self):
        return redirect("home")

    def get_permission_denied_response(self):
        if self.test_func():
            return None

        return self.handle_no_permission()


class InternalAreaRequiredMixin(InternalAccessMixin):
    # Gestão corrente: marcações, clientes, serviços, agenda e bloqueios.
    # Inclui quem trabalha na receção.

    def has_access(self):
        return self.request.user.has_internal_access


class ClinicalAccessRequiredMixin(InternalAccessMixin):
    # Anamnese e notas de evolução. A legislação exige que o acesso à
    # informação clínica seja limitado a quem dela precisa para as suas
    # funções, por isso é um nível separado do acesso à área interna.

    def has_access(self):
        return self.request.user.has_clinical_access
