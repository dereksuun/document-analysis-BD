from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .api import (
    BillingOverviewView,
    CsrfView,
    DocumentViewSet,
    ExtractionSettingsView,
    FilterPresetViewSet,
    HealthView,
    KeywordCreateView,
    KeywordDetailView,
    LogoutView,
    MeView,
    ActivateAccountView,
    AdminResetPasswordView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfileView,
    SectorViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="api-documents")
router.register("presets", FilterPresetViewSet, basename="api-presets")
router.register("sectors", SectorViewSet, basename="api-sectors")
router.register("users", UserViewSet, basename="api-users")

admin_router = DefaultRouter()
admin_router.register("sectors", SectorViewSet, basename="api-admin-sectors")
admin_router.register("users", UserViewSet, basename="api-admin-users")

urlpatterns = [
    path("health/", HealthView.as_view(), name="api-health"),
    path("csrf/", CsrfView.as_view(), name="api-csrf"),
    path("auth/token/", TokenObtainPairView.as_view(), name="api-token"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="api-token-refresh"),
    path("auth/me/", MeView.as_view(), name="api-auth-me"),
    path("auth/password-reset/", PasswordResetRequestView.as_view(), name="api-password-reset"),
    path("auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="api-password-reset-confirm"),
    path("auth/activate/", ActivateAccountView.as_view(), name="api-auth-activate"),
    path("users/<int:user_id>/reset-password/", AdminResetPasswordView.as_view(), name="api-users-reset-password"),
    path("me/", MeView.as_view(), name="api-me"),
    path("profile/", ProfileView.as_view(), name="api-profile"),
    path("logout/", LogoutView.as_view(), name="api-logout"),
    path("extraction-settings/", ExtractionSettingsView.as_view(), name="api-extraction-settings"),
    path("keywords/", KeywordCreateView.as_view(), name="api-keywords"),
    path("keywords/<int:keyword_id>/", KeywordDetailView.as_view(), name="api-keyword-detail"),
    path("billing/overview/", BillingOverviewView.as_view(), name="api-billing-overview"),
    path("admin/", include(admin_router.urls)),
    path("", include(router.urls)),
]
