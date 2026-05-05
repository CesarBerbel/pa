from django.urls import path

from .views import UserLoginView, UserLogoutView, CustomerSignupView, DashboardView

app_name = "accounts"

urlpatterns = [
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
    path("cadastro/", CustomerSignupView.as_view(), name="customer_signup"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
]
