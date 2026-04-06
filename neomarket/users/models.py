from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator

class User(AbstractUser):
    class Roles(models.TextChoices):
        ADMIN = "admin", "Admin"
        CLIENT = "client", "Client"
        MODERATOR = "moderator", "Moderator"
        SELLER = "seller", "Seller"
    # username, first_name, last_name
    email = models.EmailField(_('email address'), unique=True)
    role = models.CharField(
        max_length=20,
        choices=Roles.choices,
        default=Roles.CLIENT,
    )

    phone_number = models.CharField(
        _('phone number'),
        max_length=20,
        blank=True,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
            )
        ]
    )
    profile_picture = models.ImageField(_('profile picture'), upload_to='media/pfp/', blank=True, null=True)
    
    # todo: добавить TextChoices для стран, регионов, городов, т.п.
    country = models.CharField(_('country'), max_length=256)
    region = models.CharField(_('region'), max_length=256)
    city = models.CharField(_('city'), max_length=256)
    district = models.CharField(_('district'), max_length=256)
    street = models.CharField(_('street'), max_length=256)
    building = models.CharField(_('building'), max_length=256)
    apartment = models.CharField(_('apartment'), max_length=256)

    created_at = models.DateTimeField(_('creation date'), auto_now_add=True)
    updated_at = models.DateTimeField(_('last update date'), auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email