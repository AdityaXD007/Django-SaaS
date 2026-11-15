import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_check_endpoint():
    client = APIClient()
    url = reverse("health")
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {"status": "ok"}


@pytest.mark.django_db
def test_docs_and_schema_endpoints_load():
    client = APIClient()

    # Schema JSON/YAML endpoint
    schema_url = reverse("schema")
    schema_response = client.get(schema_url)
    assert schema_response.status_code == status.HTTP_200_OK

    # Swagger UI docs endpoint
    docs_url = reverse("docs")
    docs_response = client.get(docs_url)
    assert docs_response.status_code == status.HTTP_200_OK
    assert b"swagger-ui" in docs_response.content.lower()
