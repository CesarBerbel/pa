from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    # Custom user manager using email as the login field

    def create_user(self, email, password=None, **extra_fields):
        # Create a regular user with email and password
        if not email:
            raise ValueError("The email field is required.")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        # Create a superuser with admin permissions
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    # Custom user model for authentication by email

    username = None
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, verbose_name="Nome completo")
    phone = models.CharField(max_length=30, blank=True, verbose_name="Telefone")

    # Dois níveis distintos, porque a informação clínica não pode ficar
    # acessível a quem só trata da receção: quem marca consultas não tem de
    # ver a anamnese da cliente.
    is_internal_staff = models.BooleanField(
        default=False,
        verbose_name="Acesso à área interna",
        help_text=(
            "Permite gerir marcações, clientes, serviços e agenda. "
            "Não dá acesso a informação clínica."
        ),
    )

    can_access_clinical_data = models.BooleanField(
        default=False,
        verbose_name="Acesso a dados clínicos",
        help_text=(
            "Permite ver e editar fichas de anamnese e notas de evolução. "
            "Reservado a quem presta os cuidados."
        ),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    def __str__(self):
        return self.email

    @property
    def has_internal_access(self):
        return self.is_superuser or self.is_internal_staff

    @property
    def has_clinical_access(self):
        return self.is_superuser or self.can_access_clinical_data


class WebAuthnCredential(models.Model):
    """Chave pública de um dispositivo registado para entrar com biometria.

    O que aqui fica guardado é apenas a chave **pública**. A digital nunca sai
    do telemóvel: o que viaja é uma assinatura de um desafio aleatório, que
    esta chave permite verificar. Não há nada aqui que sirva para entrar noutro
    sítio, nem que revele a biometria de ninguém.

    Uma credencial vale para um dispositivo. Registar o telemóvel não dá acesso
    pelo portátil.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="webauthn_credentials",
        verbose_name="Utilizador",
    )

    credential_id = models.CharField(
        max_length=500,
        unique=True,
        verbose_name="Identificador da credencial",
        help_text="Devolvido pelo dispositivo, em base64url.",
    )

    public_key = models.TextField(
        verbose_name="Chave pública",
    )

    # Contador incrementado pelo autenticador a cada utilização. Se voltar
    # atrás, é sinal de credencial clonada.
    sign_count = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Contador de assinaturas",
    )

    name = models.CharField(
        max_length=80,
        verbose_name="Dispositivo",
        help_text="Como reconhecer este aparelho na lista.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    last_used_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Última utilização",
    )

    class Meta:
        ordering = ["-last_used_at", "-created_at"]
        verbose_name = "Dispositivo com biometria"
        verbose_name_plural = "Dispositivos com biometria"

    def __str__(self):
        return f"{self.name} ({self.user.email})"
