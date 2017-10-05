import copy

from rest_framework import fields
from rest_framework import serializers

from drf_extra_fields import utils


class UnhandledChildField(fields.DictField):
    """
    A dict field to handle items not in the parent schema.
    """

    def get_value(self, dictionary):
        """
        Include only the items not consumed by the parent schema.
        """
        return {
            key: value for key, value in dictionary.items()
            if key not in self.parent.fields}


class UnhandledSerializer(serializers.Serializer):
    """
    Include non-field items after processing fields.

    Set `Meta.unhandled_kwargs` or pass in `unhandled_kwargs` to specify the
    arguments to be passed to the `rest_framework.fields.DictField` child
    field to process unhandled items.  For example, include `source` to
    specify an internal attribute unhandled items should be collected to, or
    `child` to specify a field to be used to validate individual values in the
    unhandled data.
    """

    default_error_messages = {
        'conflicts': (
            'Unhandled values conflict with field values: {conflicts!r}'),
    }

    def __init__(
            self, instance=None, data=fields.empty,
            unhandled_kwargs=None, **kwargs):
        """
        Ensure that a `source` is specified.
        """
        super(UnhandledSerializer, self).__init__(
            instance=instance, data=data, **kwargs)

        if unhandled_kwargs is None:
            # Take defaults from the class
            unhandled_kwargs = getattr(
                getattr(self, 'Meta', None), 'unhandled_kwargs', {})
        # Avoid mutating the class Meta
        unhandled_kwargs = copy.deepcopy(unhandled_kwargs)
        unhandled_kwargs.setdefault('source', '*')
        unhandled_kwargs.setdefault('required', False)
        unhandled_kwargs.setdefault('child', fields._UnvalidatedField())

        self.child = UnhandledChildField(**unhandled_kwargs)
        self.child.bind(field_name='', parent=self)

    def to_internal_value(self, data):
        """
        Collect non-field items into the `source`.
        """
        value = super(UnhandledSerializer, self).to_internal_value(data)

        unhandled_data = self.child.get_value(data)
        unhandled_value = self.child.to_internal_value(unhandled_data)
        conflicts = set(unhandled_value).intersection(value)
        if conflicts:
            # TODO Find use cases for tolerating conflicts and support not
            # failing
            with utils.nest_api_exception(code='conflicts'):
                self.fail('conflicts', conflicts=conflicts)
        fields.set_value(value, self.child.source_attrs, unhandled_value)

        return value

    def to_representation(self, instance):
        """
        Include non-field items in the representation.
        """
        data = super(UnhandledSerializer, self).to_representation(instance)

        try:
            unhandled_attr = self.child.get_attribute(instance)
        except fields.SkipField:
            pass
        else:
            unhandled_data = self.child.to_representation(unhandled_attr)
            conflicts = set(unhandled_data).intersection(data)
            if conflicts:
                # TODO Find use cases for tolerating conflicts and support not
                # failing
                with utils.nest_api_exception(code='conflicts'):
                    self.fail('conflicts', conflicts=conflicts)
            data.update(unhandled_data)

        return data
