import re

try:
    import inflection
except ImportError:  # pragma: no cover
    inflectors = []
else:
    inflectors = [inflection.pluralize, inflection.parameterize]

from django.conf import settings
from django import urls
from django.db import models
from django.utils import functional

from rest_framework import fields
from rest_framework import serializers
from rest_framework.utils import serializer_helpers

from . import composite

url_parameter_re = re.compile(r'\^([^/?]+)/\$')


def get_resource_items(
        instance, pattern=None,
        url_re=url_parameter_re, inflectors=inflectors):
    """
    Lookup the resource type, model and serializer, from various sources.
    """
    parameter = serializer = uninflected = model = None

    if isinstance(instance, models.Model):
        model = type(instance)

    elif hasattr(instance, 'get_serializer'):
        serializer = instance.get_serializer()
        model = getattr(getattr(serializer, 'Meta', None), 'model', None)
        if hasattr(instance, 'get_queryset'):
            try:
                queryset = instance.get_queryset()
            except AssertionError:
                pass
            else:
                model = queryset.model

        # If the serializer sets the parameter explicitly, do not inflect
        parameter = getattr(
            getattr(serializer, 'Meta', None), 'parameter', None)

    if parameter is None and uninflected is None:
        if pattern is not None:
            url_match = url_re.match(pattern.regex.pattern)
            if url_match is not None:
                uninflected = url_match.group(1)
        if pattern is None and model is not None:
            uninflected = model._meta.verbose_name

    if parameter is None and uninflected is not None:
        # No explicit parameter, inflect the derived parameter
        parameter = uninflected
        for inflector in inflectors:
            parameter = inflector(parameter)

    return parameter, model, serializer


def lookup_serializer_parameters(
        field, pattern, url_re=url_parameter_re, inflectors=inflectors):
    """
    Lookup up the parameters and their specific serializers from views.
    """
    specific_serializers = {}
    specific_serializers_by_type = {}

    # Lookup any available viewset that can provide a serializer
    class_ = getattr(getattr(pattern, 'callback', None), 'cls', None)
    if hasattr(class_, 'get_serializer'):
        viewset = class_(request=None, format_kwarg=None)
        parameter, model, serializer = get_resource_items(
            viewset, pattern, url_re, inflectors)
        if serializer is not None:
            if parameter is not None:
                specific_serializers.setdefault(parameter, serializer)
            if model is not None:
                specific_serializers_by_type.setdefault(model, serializer)

    if hasattr(pattern, 'url_patterns'):
        for recursed_pattern in pattern.url_patterns:
            recursed = lookup_serializer_parameters(
                field, recursed_pattern, inflectors=inflectors)
            recursed['specific_serializers'].update(
                specific_serializers)
            specific_serializers = recursed[
                'specific_serializers']
            recursed['specific_serializers_by_type'].update(
                specific_serializers_by_type)
            specific_serializers_by_type = recursed[
                'specific_serializers_by_type']
    return dict(
        specific_serializers=specific_serializers,
        specific_serializers_by_type=specific_serializers_by_type)


class SerializerParameterValidator(object):
    """
    Omit the parameter field by default.
    """

    def set_context(self, serializer_field):
        """
        Capture the field.
        """
        self.field = serializer_field

    def __call__(self, value):
        """
        Lookup specific serializer for parameter and omit the field.
        """
        self.field.lookup_serializer(value)
        if self.field.skip:
            raise fields.SkipField(
                "Don't include generic type field in internal value")
        return value


class SerializerParameterField(composite.ParentField):
    """
    Map serialized parameter to the specific serializer and back.
    """

    default_error_messages = {
        'unknown': (
            'No specific serializer available for parameter {parameter!r}'),
        'serializer': (
            'No parameter found for the specific serializer, {value!r}'),
        'mismatch': (
            'The parameter, {parameter!r}, '
            'does not match the looked up parameter, {by_type!r}'),
        'instance': (
            'Could not lookup parameter from {instance!r}'),
    }

    child = fields._UnvalidatedField(
        label='Parameter',
        help_text='the parameter that identifies the specific serializer')

    def __init__(
            self,
            urlconf=settings.ROOT_URLCONF, inflectors=inflectors,
            specific_serializers={}, specific_serializers_by_type={},
            skip=True, **kwargs):
        """Map parameters to serializers/fields per `specific_serializers`.

        `specific_serializers` maps parameter keys (e.g. string "types") to
        serializer instance values while `specific_serializers_by_type` maps
        instance types/classes (e.g. Django models) to specific serializer
        instances.

        If `urlconf` is given or is left as it's default,
        `settings.ROOT_URLCONF`, it will be used to map singular string types
        derived from the model's `verbose_name` of any viewset's
        `get_queryset()` found in the default URL patterns to those viewset's
        serializers via `get_serializer()`.

        If both are given, items in `specific_serializers*` override items
        derived from `urlconf`.
        """
        super(SerializerParameterField, self).__init__(**kwargs)

        assert (
            urlconf or
            specific_serializers or specific_serializers_by_type
        ), (
            'Must give at lease one of `urlconf`, `specific_serializers` or'
            '`specific_serializers_by_type`')
        self.urlconf = urlconf
        self.inflectors = inflectors
        self._specific_serializers = specific_serializers
        self._specific_serializers_by_type = specific_serializers_by_type

        self.skip = skip
        self.validators.append(SerializerParameterValidator())

        self.parameter_serializers = []

    def bind_parameter_field(self, serializer):
        """
        Bind the serializer to the parameter field.
        """
        if not hasattr(serializer, 'clone_meta'):
            serializer.clone_meta = {}
        serializer.clone_meta['parameter_field'] = self
        if isinstance(serializer, ParameterizedGenericSerializer):
            self.parameter_serializers.append(serializer)

    def bind(self, field_name, parent):
        """
        Tell the generic serializer to get the specific serializers from us.
        """
        super(SerializerParameterField, self).bind(field_name, parent)
        self.bind_parameter_field(parent)

    def merge_serializer_parameters(self):
        """
        Lookup and merge the parameters and specific serializers.
        """
        serializers = lookup_serializer_parameters(
            self, urls.get_resolver(self.urlconf), inflectors=self.inflectors)
        serializers['specific_serializers'].update(
            self._specific_serializers)
        serializers['specific_serializers_by_type'].update(
            self._specific_serializers_by_type)
        serializers['parameters'] = {
            type(serializer): parameter for parameter, serializer in
            serializers['specific_serializers'].items()}
        return serializers

    @functional.cached_property
    def specific_serializers(self):
        """
        Populate specific serializer lookup on first reference.
        """
        serializers = self.merge_serializer_parameters()
        vars(self).update(**serializers)
        return serializers['specific_serializers']

    @functional.cached_property
    def specific_serializers_by_type(self):
        """
        Populate specific serializer lookup on first reference.
        """
        serializers = self.merge_serializer_parameters()
        vars(self).update(**serializers)
        return serializers['specific_serializers_by_type']

    @functional.cached_property
    def parameters(self):
        """
        Populate specific serializer lookup on first reference.
        """
        serializers = self.merge_serializer_parameters()
        vars(self).update(**serializers)
        return serializers['parameters']

    def lookup_serializer(self, parameter):
        """
        The specific serializer corresponding to the parameter.
        """
        if parameter not in self.specific_serializers:
            self.fail('unknown', parameter=parameter)

        # if the generic serializer ends up using a serializer other than
        # `self.child`, such as when the primary serializer looks up the
        # serializer from the view, verify that the type matches.
        child = self.parameter_serializers[0].get_view_serializer()
        if child is not None:
            by_type = self.parameters.get(type(child))
            if by_type is None:
                self.fail('serializer', value=child)
            if parameter != by_type:
                self.fail('mismatch', parameter=parameter, by_type=by_type)
        else:
            child = self.specific_serializers[parameter]

        for parameter_serializer in self.parameter_serializers:
            parameter_serializer.child = child
        return child

    def lookup_parameter(self, instance):
        """
        The parameter corresponding to the specific serializer.
        """
        if isinstance(instance, serializer_helpers.ReturnDict):
            # Serializing self.validated_data
            child = instance.serializer
            if type(child) not in self.parameters:
                self.fail('serializer', value=child)
        else:
            # Infer the specific serializer from the instance type
            model = type(instance)
            if model not in self.specific_serializers_by_type:
                self.fail('instance', instance=instance)
            child = self.specific_serializers_by_type[model]
        parameter = self.parameters[type(child)]

        # if the generic serializer ends up using a serializer other than
        # `self.child`, such as when the primary serializer looks up the
        # serializer from the view, verify that the type matches.
        view_child = self.parameter_serializers[0].get_view_serializer()
        if view_child is not None:
            child = view_child

        for parameter_serializer in self.parameter_serializers:
            parameter_serializer.child = child
        return parameter

    def get_attribute(self, instance):
        """
        Lookup the parameter if the instance doesn't have the it directly.
        """
        try:
            # Try the attribute from the instance as the parameter
            parameter = fields.get_attribute(
                instance, self.source_attrs, exc_on_model_default=(
                    self.default is not fields.empty or
                    not self.required))
        except (KeyError, AttributeError) as exc:
            try:
                # Fallback to the parameter from the instance type
                return self.lookup_parameter(instance)
            except serializers.ValidationError:
                # Otherwise fallback to normal feild handling
                if self.default is not fields.empty:
                    parameter = self.get_default()
                    # Set the current parameter and bind the specific
                    # serializer based on the default parameter
                    self.lookup_serializer(parameter)
                    return parameter
                if not self.required:
                    child = serializers.Serializer(instance=instance)
                    for parameter_serializer in self.parameter_serializers:
                        parameter_serializer.child = child
                    raise fields.SkipField()
                msg = (
                    'Got {exc_type} when attempting to get a value for field '
                    '`{field}` on serializer `{serializer}`.\nThe serializer '
                    'field might be named incorrectly and not match '
                    'any attribute or key on the `{instance}` instance.\n'
                    'Original exception text was: {exc}.'.format(
                        exc_type=type(exc).__name__,
                        field=self.field_name,
                        serializer=self.parent.__class__.__name__,
                        instance=instance.__class__.__name__,
                        exc=exc
                    )
                )
                raise type(exc)(msg)
        else:
            # Set the current parameter and bind the specific serializer based
            # on the actual instance attribute
            self.lookup_serializer(parameter)
            return parameter

    def to_internal_value(self, data):
        """
        Delegate processing the simple parameter value to the child field.
        """
        return self.child.to_internal_value(data)

    def to_representation(self, value):
        """
        Delegate processing the simple parameter value to the child field.
        """
        return self.child.to_representation(value)


class SerializerParameterDictField(composite.SerializerDictField):
    """
    Map dictionary keys to the specific serializers and back.
    """
    # TODO specific serializer validation errors in parameter dict field

    key_child = SerializerParameterField(
        label='Dict Item Key Parameter',
        help_text='the key for an individual item in the dictionary '
        'to be used as the parameter', skip=False)

    def bind(self, field_name, parent):
        """
        Tell the generic serializer to get the specific serializers from us.
        """
        super(SerializerParameterDictField, self).bind(field_name, parent)
        self.key_child.bind_parameter_field(self.child.child)


class ParameterizedGenericSerializer(composite.CompositeSerializer):
    """
    Process generic schema, then delegate the rest to the specific serializer.
    """

    # Class-based defaults for instantiation kwargs
    exclude_parameterized = False

    def __init__(
            self, instance=None, data=fields.empty,
            parameter_field_name=None, exclude_parameterized=None, **kwargs):
        """Process generic schema, then delegate the rest to the specific.

        `SerializerParameterField` expects to be a field in the same
        JavaScript object as the parameterized fields:
        `{"type": "users", "id": 1, "username": "foo_username", ...}`
        while `SerializerParameterDictField` expects to get the parameter from
        a JavaScript object key/property-name:
        `{"users": {"id": 1, "username": "foo_username", ...}, ...}`.
        If `parameter_field_name` is given, it must be the name of a
        SerializerParameterField in the same parent serializer as this
        serializer.  This can be useful when the parameter is taken from a
        field next to the serializer, such as the JSON API format:
        `{"type": "users", "attributes": {"username": "foo_username", ...}}`.

        By default, the looked up parameterized serializer is used to process
        the data during `to_internal_value()` and `to_representation()`.
        Alternatively, only the paramaterized serializer fields which are
        consumed by the generic serializer's fields can be used if
        `exclude_parameterized=True`.  This can be useful where you need the
        parameterized serializer to lookup the parameter but don't actually
        want to include it's schema, such as when just looking up a `type`:
        `{"type": "users", "id": 1}`

        """
        super(ParameterizedGenericSerializer, self).__init__(
            instance=instance, data=data, **kwargs)
        self.parameter_field_name = parameter_field_name
        if exclude_parameterized is not None:
            # Allow class to provide a default
            self.exclude_parameterized = exclude_parameterized

    def bind(self, field_name, parent):
        """
        If a sibling parameter field is specified, bind as needed.
        """
        super(ParameterizedGenericSerializer, self).bind(field_name, parent)
        if self.parameter_field_name is not None:
            parameter_field = parent.fields[
                self.parameter_field_name]
            parameter_field.bind_parameter_field(self)

    def get_serializer(self, **kwargs):
        """
        Optionally exclude the specific child serialiers fields.
        """
        clone = super(ParameterizedGenericSerializer, self).get_serializer(
            **kwargs)
        if clone is None:
            return

        if self.exclude_parameterized:
            for field_name, field in list(clone.fields.items()):
                if field_name not in self.field_source_attrs:
                    del clone.fields[field_name]

        return clone

    def to_representation(self, instance):
        """
        Ensure the current parameter and serializer are set first.
        """
        # Ensure all fields are bound so the parameter field is available
        self.fields
        # Set the current parameter and specific serializer
        parameter_field = self.clone_meta['parameter_field']
        try:
            parameter_field.get_attribute(instance)
        except serializers.SkipField:
            pass
        except (AttributeError, KeyError):
            try:
                parameter_field.fail('instance', instance=instance)
            except serializers.ValidationError as exc:
                # Re-raise under the field name
                raise serializers.ValidationError({
                    parameter_field.field_name: exc.detail
                }, code=exc.detail[0].code)

        return super(ParameterizedGenericSerializer, self).to_representation(
            instance)
