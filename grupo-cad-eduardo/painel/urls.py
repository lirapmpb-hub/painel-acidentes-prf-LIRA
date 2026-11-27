from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="inicio"),
    path("<slug:aba>/", views.index, name="aba"),
]
