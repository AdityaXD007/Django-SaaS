from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.tenants.services import create_tenant_with_owner

from .serializers import RegisterSerializer, UserProfileSerializer

User = get_user_model()


class RegisterView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    @extend_schema(
        summary="Register user and workspace",
        description=(
            "Creates a new user, their initial tenant/workspace, "
            "and an OWNER membership atomically. Returns user, tenant, and JWT tokens."
        ),
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(description="User and tenant created successfully"),
            400: OpenApiResponse(description="Validation error"),
        },
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        email = validated_data["email"]
        password = validated_data["password"]
        full_name = validated_data.get("full_name", "")
        tenant_name = validated_data["tenant_name"]

        with transaction.atomic():
            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
            )
            tenant = create_tenant_with_owner(user=user, name=tenant_name)

        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)

        return Response(
            {
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                },
                "tenant": {
                    "id": str(tenant.id),
                    "name": tenant.name,
                    "slug": tenant.slug,
                },
                "access": access,
                "refresh": str(refresh),
                "tokens": {
                    "access": access,
                    "refresh": str(refresh),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Get current user profile and workspaces",
        description="Returns the authenticated user's details and active workspace memberships.",
        responses={200: UserProfileSerializer},
    )
    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
