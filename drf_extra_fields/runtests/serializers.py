from rest_framework import serializers

from drf_extra_fields import relations
from drf_extra_fields import parameterized
from drf_extra_fields import unhandled

from . import models


class ExampleChildSerializer(serializers.Serializer):
    """
    A simple serializer for testing composite fields as a child.
    """

    name = serializers.CharField()

    def create(self, validated_data):
        """
        Delegate to the children.
        """
        return validated_data

    def update(self, instance, validated_data):
        """
        Delegate to the children.
        """
        return validated_data


class ExamplePersonSerializer(relations.UUIDModelSerializer):
    """
    A simple model serializer for testing.
    """

    class Meta(relations.UUIDModelSerializer.Meta):
        model = models.Person
        exclude = None
        fields = ('id', 'name', 'articles')
        extra_kwargs = dict(related_to=dict(lookup_field='uuid'))


class OverriddenPersonSerializer(ExamplePersonSerializer):
    """
    An example of a serializer for a view that overrides another.
    """


class ExampleTypeFieldSerializer(
        parameterized.ParameterizedGenericSerializer):
    """
    A simple serializer for testing a type field parameter.
    """

    type = parameterized.SerializerParameterField(
        specific_serializers={
            "foo-type": ExampleChildSerializer(),
            "wo-models": serializers.Serializer()})


class ExampleSerializerWOModel(serializers.Serializer):
    """
    A simple serialier without a model.
    """


class ExampleUnhandledSerializer(unhandled.UnhandledSerializer):
    """
    A simple serialier that includes non-field items.
    """

    class Meta:
        child = unhandled.UnhandledChildField(
            source='unhandled', required=False)

    type = serializers.CharField(default='unhandled')

    def create(self, validated_data):
        """
        Just return the validated data.
        """
        return validated_data


class ExampleUnhandledTypeFieldSerializer(
        parameterized.ParameterizedGenericSerializer):
    """
    A simple serializer for testing a type field parameter.
    """

    primary = False

    type = parameterized.SerializerParameterField(
        specific_serializers={"foo-type": ExampleChildSerializer()},
        unhandled_serializer=ExampleUnhandledSerializer())
