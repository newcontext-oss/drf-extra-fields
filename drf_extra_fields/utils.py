import contextlib

from rest_framework.settings import api_settings
from rest_framework import exceptions


@contextlib.contextmanager
def nest_api_exception(key=api_settings.NON_FIELD_ERRORS_KEY, code=None):
    """
    Re-raise any APIException nested under the given key.
    """
    try:
        yield
    except exceptions.APIException as exc:
        raise type(exc)({key: exc.detail}, code=code or exc.detail.code)
