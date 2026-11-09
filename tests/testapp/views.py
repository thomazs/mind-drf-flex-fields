from rest_framework.viewsets import ModelViewSet

from mind_flex_fields import FlexFieldsModelViewSet
from tests.testapp.models import Pet, Profile, TaggedItem
from tests.testapp.serializers import (
    PetSerializer,
    ProfileSerializer,
    TaggedItemSerializer,
)


class PetViewSet(FlexFieldsModelViewSet):
    """
    API endpoint for testing purposes.
    """

    serializer_class = PetSerializer
    queryset = Pet.objects.all()
    permit_list_expands = ["owner"]


class TaggedItemViewSet(ModelViewSet):
    serializer_class = TaggedItemSerializer
    queryset = TaggedItem.objects.all()


class ProfileViewSet(FlexFieldsModelViewSet):
    """Select-relates its forward one-to-one, the way a real project would."""

    serializer_class = ProfileSerializer
    queryset = Profile.objects.all().select_related("owner")
