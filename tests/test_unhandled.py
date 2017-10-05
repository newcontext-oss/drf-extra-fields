from rest_framework.settings import api_settings
from rest_framework import test
from rest_framework import exceptions
from rest_framework import serializers

from drf_extra_fields import unhandled


class ExampleUnhandledSerializer(unhandled.UnhandledSerializer):
    """
    An example serializer that puts non-field items into `unhandled`.
    """

    foo = serializers.CharField(source='qux', required=False)

    class Meta:
        unhandled_kwargs = {'source': 'unhandled'}

    def create(self, validated_data):
        """
        Delegate to the children.
        """
        return validated_data


class TestUnhandledSerializerFields(test.APITestCase):
    """
    Test unhandled serializers handling of non-field items.
    """

    def test_unhandled_serializer(self):
        """
        An unhandled serializer captures non-handled fields.
        """
        data = {'qux': 'qux'}
        unhandled_serializer = ExampleUnhandledSerializer(data=data)
        unhandled_serializer.is_valid(raise_exception=True)
        self.assertEqual(
            unhandled_serializer.validated_data, {'unhandled': data},
            'Wrong unhandled serializer validated data')
        self.assertEqual(
            unhandled_serializer.save(), {'unhandled': data},
            'Wrong unhandled serializer saved value')
        self.assertEqual(
            unhandled_serializer.data, data,
            'Wrong unhandled serializer representation data')

    def test_unhandled_conflicts_internal(self):
        """
        Raises validation errors on conflicts when deserializing.
        """
        unhandled_serializer = ExampleUnhandledSerializer(
            data={'foo': 'foo', 'qux': 'qux'})
        with self.assertRaises(exceptions.ValidationError) as cm:
            unhandled_serializer.is_valid(raise_exception=True)
        self.assertIn(
            'conflict',
            cm.exception.detail[api_settings.NON_FIELD_ERRORS_KEY][0].lower(),
            'Wrong unhandled items conflicts validation error')

    def test_unhandled_conflicts_representation(self):
        """
        Raises validation errors on conflicts when serializing.
        """
        unhandled_serializer = ExampleUnhandledSerializer(
            instance={'qux': 'foo', 'unhandled': {'foo': 'qux'}})
        with self.assertRaises(exceptions.ValidationError) as cm:
            unhandled_serializer.data
        self.assertIn(
            'conflict',
            cm.exception.detail[api_settings.NON_FIELD_ERRORS_KEY][0].lower(),
            'Wrong unhandled items conflicts validation error')

    def test_unhandled_missing(self):
        """
        Handles missing unhandled instance value.
        """
        unhandled_serializer = ExampleUnhandledSerializer(
            instance={'qux': 'foo'})
        self.assertEqual(
            unhandled_serializer.data, {'foo': 'foo'},
            'Wrong missing unhanlded serialized value')
