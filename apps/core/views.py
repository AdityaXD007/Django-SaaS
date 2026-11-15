from django.db import connection
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    @extend_schema(
        summary="Health check",
        description="Checks database connectivity and returns service status.",
        responses={
            200: OpenApiResponse(description="Service is healthy"),
        },
    )
    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok"})
