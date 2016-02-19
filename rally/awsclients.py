# Copyright 2013: Mirantis Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import abc
import os

from oslo_config import cfg

from rally.common.i18n import _
from rally.common import log as logging
from rally.common import objects
from rally.common.plugin import plugin
from rally.common import utils
from rally import consts
from rally import exceptions
from rally.boot_from_vol_client import enforce_boot_from_volume


CONF = cfg.CONF

AWSCLIENTS_OPTS = [
    cfg.FloatOpt("aws_client_http_timeout", default=180.0,
                 help="HTTP timeout for any of AWS service in seconds"),
    cfg.BoolOpt("aws_https_insecure", default=False,
                help="Use SSL for all AWS API interfaces",
                deprecated_for_removal=True),
    cfg.StrOpt("aws_https_cacert", default=None,
               help="Path to CA server certificate for SSL",
               deprecated_for_removal=True)
]
CONF.register_opts(AWSCLIENTS_OPTS)

_NAMESPACE = "aws"


def configure(name, default_version=None, default_service_type=None):
    """OpenStack client class wrapper.

    Each client class has to be wrapped by configure() wrapper. It
    sets essential configuration of client classes.

    :param name: Name of the client
    :param default_version: Default version for client
    :param default_service_type: Default service type of endpoint
    """
    def wrapper(cls):
        cls = plugin.configure(name=name, namespace=_NAMESPACE)(cls)
        cls._meta_set("default_version", default_version)
        cls._meta_set("default_service_type", default_service_type)
        return cls

    return wrapper


class AWSClient(plugin.Plugin):
    def __init__(self, cache_obj):
        self.cache = cache_obj

    def choose_version(self, version=None):
        """Return version string.

        Choose version between transmitted(preferable value if present) and
        default.
        """
        # NOTE(andreykurilin): The result of choose is converted to string,
        # since most of clients contain map for versioned modules, where a key
        # is a string value of version. Example of map and its usage:
        #
        #     from oslo_utils import importutils
        #     ...
        #     version_map = {"1": "someclient.v1.client.Client",
        #                    "2": "someclient.v2.client.Client"}
        #
        #     def Client(version, *args, **kwargs):
        #         cls = importutils.import_class(version_map[version])
        #         return cls(*args, **kwargs)
        #
        # That is why type of version so important and we should ensure that
        # version is a string object.
        # For those clients which doesn't accept string value(for example
        # zaqarclient), this method should be overridden.
        return str(version or self._meta_get("default_version"))

    def get_service_type(self):
        return self._meta_get("default_service_type")

    def _get_session(self, auth=None):
	from boto3.session import Session
	session = None
	if(auth == None):
		session = Session(aws_access_key_id='',aws_secret_access_key='',\
			region_name='')	
	else:
		session = Session(aws_access_key_id=auth.aws_access_key_id, aws_secret_access_key=auth.aws_secret_access_key, \
					region_name = auth.region_name)
			
        return session
    def _get_client(self, service_name, auth=None):
	return self._get_session(auth).client(service_name)

    def _get_resource(self, service_name, auth=None):
	return self._get_session(auth).resource(service_name)

    @abc.abstractmethod
    def create_client(self, *args, **kwargs):
        """Create new instance of client."""

    def __call__(self, *args, **kwargs):
        """Return initialized client instance."""
        key = "{0}{1}{2}".format(self.get_name(),
                                 str(args) if args else "",
                                 str(kwargs) if kwargs else "")
        if key not in self.cache:
            self.cache[key] = self.create_client(*args, **kwargs)
        return self.cache[key]

@configure("aws_ec2")
class AWS_EC2(AWSClient):
	def create_client(self):
		ec2_client = self._get_client("ec2")
		return ec2_client



class Clients(object):
    """This class simplify and unify work with OpenStack python clients."""

    def __init__(self):
        """
	self.endpoint = endpoint
        # NOTE(kun) Apply insecure/cacert settings from rally.conf if those are
        # not set in deployment config. Remove it when invalid.
        if self.endpoint.insecure is None:
            self.endpoint.insecure = CONF.https_insecure
        if self.endpoint.cacert is None:
            self.endpoint.cacert = CONF.https_cacert
        """
	self.cache = {}

    def __getattr__(self, client_name):
        """Lazy load of clients."""
        return AWSClient.get(client_name, namespace=_NAMESPACE)(
            self.cache)

    @classmethod
    def create_from_env(cls):
        return cls(
            objects.Endpoint(
                os.environ["OS_AUTH_URL"],
                os.environ["OS_USERNAME"],
                os.environ["OS_PASSWORD"],
                os.environ.get("OS_TENANT_NAME"),
                region_name=os.environ.get("OS_REGION_NAME")
            ))

    def clear(self):
        """Remove all cached client handles."""
        self.cache = {}
		
