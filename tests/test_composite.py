from django.utils import datastructures

from rest_framework import exceptions
from rest_framework import serializers
from rest_framework import test

from drf_extra_fields import composite


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


class ExampleListSerializer(serializers.Serializer):
    """
    A simple serializer for testing the list composite field.
    """

    children = composite.SerializerListField(
        child=ExampleChildSerializer(allow_null=True), allow_empty=False)

    def create(self, validated_data):
        """
        Delegate to the children.
        """
        return {"children": [
            child_data.clone.create(child_data)
            for child_data in validated_data["children"]]}


class ExampleDictSerializer(serializers.Serializer):
    """
    A simple serializer for testing the dict composite field.
    """

    children = composite.SerializerDictField(
        child=ExampleChildSerializer(allow_null=True))

    def create(self, validated_data):
        """
        Delegate to the children.
        """
        return {"children": {
            key: child_data.clone.create(child_data)
            for key, child_data in validated_data["children"].items()}}


class TestCompositeSerializerFields(test.APISimpleTestCase):
    """
    Test that composite field serializers can be used as normal.
    """

    child_data = {"name": "Foo Name"}
    list_data = {"children": [child_data]}
    dict_data = {"children": {"foo": child_data}}
    list_serializer_data = [child_data]

    def test_list_field(self):
        """
        Test that a list field child serializer can be fully used.
        """
        list_data = self.list_data.copy()
        list_data["children"] = datastructures.MultiValueDict({
            '[0]': [self.child_data]})
        parent = ExampleListSerializer(data=list_data)
        parent.is_valid(raise_exception=True)
        save_result = parent.save()
        self.assertEqual(
            save_result, self.list_data, 'Wrong serializer save results')
        self.assertEqual(
            parent.data, self.list_data, 'Wrong serializer reproduction')

    def test_list_field_instance(self):
        """
        Test that a list field child serializer can be used with an instance.
        """
        parent = ExampleListSerializer(instance=self.list_data)
        self.assertEqual(
            parent.data, self.list_data, 'Wrong serializer reproduction')

    def test_list_field_type(self):
        """
        Test that a list field validates type.
        """
        type = ExampleListSerializer(data=self.dict_data)
        with self.assertRaises(exceptions.ValidationError) as cm:
            type.is_valid(raise_exception=True)
        self.assertIn(
            'expected a list of items',
            cm.exception.detail["children"][0].lower(),
            'Wrong list type validation error')

    def test_list_field_empty(self):
        """
        Test that a list field validates empty values.
        """
        empty_data = self.list_data.copy()
        empty_data["children"] = []
        empty = ExampleListSerializer(data=empty_data)
        with self.assertRaises(exceptions.ValidationError) as cm:
            empty.is_valid(raise_exception=True)
        self.assertIn(
            'may not be empty',
            cm.exception.detail["children"][0].lower(),
            'Wrong list type validation error')

    def test_list_field_none(self):
        """
        Test that a list field handles none values.
        """
        none_data = self.list_data.copy()
        none_data["children"] = [None]
        none = ExampleListSerializer(data=none_data)
        none.is_valid(raise_exception=True)
        self.assertEqual(
            none.data, none_data, 'Wrong serializer reproduction')

    def test_dict_field(self):
        """
        Test that a dict field child serializer can be fully used.
        """
        dict_data = self.dict_data.copy()
        dict_data["children"] = datastructures.MultiValueDict({
            '.' + key: [value]
            for key, value in self.dict_data["children"].items()})
        parent = ExampleDictSerializer(data=dict_data)
        parent.is_valid(raise_exception=True)
        save_result = parent.save()
        self.assertEqual(
            save_result, self.dict_data, 'Wrong serializer save results')
        self.assertEqual(
            parent.data, self.dict_data, 'Wrong serializer representation')

    def test_dict_field_instance(self):
        """
        Test that a dict field child serializer can be used with an instance.
        """
        parent = ExampleDictSerializer(instance=self.dict_data)
        self.assertEqual(
            parent.data, self.dict_data, 'Wrong serializer reproduction')

    def test_dict_field_type(self):
        """
        Test that a dict field validates type.
        """
        type = ExampleDictSerializer(data=self.list_data)
        with self.assertRaises(exceptions.ValidationError) as cm:
            type.is_valid(raise_exception=True)
        self.assertIn(
            'expected a dictionary of items',
            cm.exception.detail["children"][0].lower(),
            'Wrong dict type validation error')

    def test_dict_field_none(self):
        """
        Test that a dict field handles none values.
        """
        none_data = self.dict_data.copy()
        none_data["children"] = dict(
            self.dict_data["children"], foo=None)
        none = ExampleDictSerializer(data=none_data)
        none.is_valid(raise_exception=True)
        self.assertEqual(
            none.data, none_data, 'Wrong serializer reproduction')

    def test_list_serializer(self):
        """
        Test that a list serializer work.
        """
        parent = serializers.ListSerializer(
            data=self.list_serializer_data, child=ExampleChildSerializer())
        parent.is_valid(raise_exception=True)
        save_result = parent.save()
        self.assertEqual(
            save_result, self.list_serializer_data,
            'Wrong serializer save results')

    def test_clone_serializer(self):
        """
        Test that cloning a serializer preserves what is needed.
        """
        parent = serializers.ListSerializer(
            data=self.list_serializer_data, child=ExampleChildSerializer())
        parent.clone_meta = {"foo": "bar"}
        clone = composite.clone_serializer(parent)
        self.assertIs(
            clone.original, parent,
            'Serializer clone wrong original')
        self.assertIsInstance(
            clone.child, type(parent.child),
            'Serializer clone wrong child type')
        self.assertIs(
            clone.clone_meta, parent.clone_meta,
            'Serializer clone wrong clone metadata')

    def test_cone_return_dict(self):
        """
        Test that the return dict wrapper has the right references.
        """
        parent = ExampleListSerializer(data=self.list_data)
        parent.is_valid(raise_exception=True)
        wrapped = parent.validated_data["children"][0]
        self.assertIsInstance(
            wrapped, composite.CloneReturnDict,
            'Child data missing clone wrapper')
        wrapped_copy = wrapped.copy()
        self.assertIsInstance(
            wrapped_copy, composite.CloneReturnDict,
            'Child data clone wrapper copy wrong type')
        self.assertIs(
            wrapped_copy.data, wrapped.data,
            'Child data clone wrapper copy wrong data')
        self.assertIs(
            wrapped_copy.clone, wrapped.clone,
            'Child clone clone wrapper copy wrong clone')
        self.assertIs(
            wrapped_copy.serializer, wrapped.serializer,
            'Child serializer clone wrapper copy wrong serializer')
