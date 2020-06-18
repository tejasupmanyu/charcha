"""charcha URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from __future__ import unicode_literals, absolute_import
from . import views

from django.conf.urls import url, include
from django.contrib import admin
from django.conf.urls.static import static
from django.conf import settings
import charcha.teams.views as team_views

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^healthcheck/$', views.health_check),
    url('', include('social_django.urls', namespace='social')),
    url(r'^', include('charcha.discussions.urls')),
    url(r'^', include('django.contrib.auth.urls')),
    url(r'^chatbot', team_views.google_chatbot, name="Webhook for google chatbot"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

