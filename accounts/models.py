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
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True)

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
