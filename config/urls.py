from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from . import health

urlpatterns = [path("admin/", admin.site.urls), path("together/", include("journey.urls")), path("", include("core.urls"))]
urlpatterns += [path("health/live/", health.live, name="health-live"), path("health/ready/", health.ready, name="health-ready")]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
