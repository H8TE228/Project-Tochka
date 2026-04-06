from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('login/', views.CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path("register/seller/", views.RegisterView.as_view(), name="register_seller"),
    path("register/client/", views.RegisterView.as_view(), name="register_client"),
    path("register/moderator/", views.RegisterView.as_view(), name="register_moderator"),
    path("register/admin/", views.RegisterView.as_view(), name="register_admin"),

    
    path('logout/', views.LogoutView.as_view(), name='logout'),
    
    path('profile/', views.UserProfileView.as_view(), name='user_profile'),
    path('profile/change-password/', views.ChangePasswordView.as_view(), name='change_password'),
    
    path('users/', views.UserListView.as_view(), name='user_list'),
]