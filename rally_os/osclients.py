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

OSCLIENTS_OPTS = [
    cfg.FloatOpt("openstack_client_http_timeout", default=180.0,
                 help="HTTP timeout for any of OpenStack service in seconds"),
    cfg.BoolOpt("https_insecure", default=False,
                help="Use SSL for all OpenStack API interfaces",
                deprecated_for_removal=True),
    cfg.StrOpt("https_cacert", default=None,
               help="Path to CA server certificate for SSL",
               deprecated_for_removal=True)
]
CONF.register_opts(OSCLIENTS_OPTS)

_NAMESPACE = "openstack"


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


class OSClient(plugin.Plugin):
    def __init__(self, endpoint, cache_obj):
        self.endpoint = endpoint
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

    def keystone(self, *args, **kwargs):
        """Make a call to keystone client."""
        keystone = OSClient.get("keystone", namespace=_NAMESPACE)(
            self.endpoint, self.cache)
        return keystone(*args, **kwargs)

    def _get_session(self, auth=None, endpoint=None):
        endpoint = endpoint or self._get_endpoint()

        from keystoneclient.auth import token_endpoint
        from keystoneclient import session as ks_session

        kc = self.keystone()
        if auth is None:
            auth = token_endpoint.Token(endpoint, kc.auth_token)

        return ks_session.Session(auth=auth, verify=self.endpoint.insecure)

    def _get_endpoint(self):
        kc = self.keystone()
        api_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        return api_url

    def _get_auth_info(self, user_key="username",
                       password_key="password",
                       auth_url_key="auth_url",
                       project_name_key="project_id"
                       ):
        kw = {
            user_key: self.endpoint.username,
            password_key: self.endpoint.password,
            auth_url_key: self.endpoint.auth_url
        }
        if project_name_key:
            kw.update({project_name_key: self.endpoint.tenant_name})
        return kw

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


@configure("keystone")
class Keystone(OSClient):
    def keystone(self, *args, **kwargs):
        raise exceptions.RallyException(_("Method 'keystone' is restricted "
                                          "for keystoneclient. :)"))

    @staticmethod
    def _create_keystone_client(args):
        from keystoneclient import discover as keystone_discover
        discover = keystone_discover.Discover(**args)
        for version_data in discover.version_data():
            version = version_data["version"]
            if version[0] <= 2:
                from keystoneclient.v2_0 import client as keystone_v2
                return keystone_v2.Client(**args)
            elif version[0] == 3:
                from keystoneclient.v3 import client as keystone_v3
                return keystone_v3.Client(**args)
        raise exceptions.RallyException("Failed to discover keystone version "
                                        "for url %(auth_url)s.", **args)

    def create_client(self):
        """Return keystone client."""
        new_kw = {
            "timeout": CONF.openstack_client_http_timeout,
            "insecure": self.endpoint.insecure, "cacert": self.endpoint.cacert
        }
        kw = self.endpoint.to_dict()
        kw.update(new_kw)
        client = self._create_keystone_client(kw)
        if client.auth_ref is None:
            client.authenticate()
        return client


@configure("nova", default_version="2", default_service_type="compute")
class Nova(OSClient):
    def create_client(self, version=None):
        """Return nova client."""
        from novaclient import client as nova
        kc = self.keystone()
        compute_api_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
	#TBD VISHNU KUMAR acess key or ?
        client = nova.Client(self.choose_version(version),
                             auth_token=kc.auth_token,
                             http_log_debug=logging.is_debug(),
                             timeout=CONF.openstack_client_http_timeout,
                             insecure=self.endpoint.insecure,
                             cacert=self.endpoint.cacert,
                             **self._get_auth_info(password_key="api_key"))
        enforce_boot_from_volume(client)
        client.set_management_url(compute_api_url)
        return client


@configure("neutron", default_version="2.0", default_service_type="network")
class Neutron(OSClient):
    def create_client(self, version=None):
        """Return neutron client."""
        from neutronclient.neutron import client as neutron
        kc = self.keystone()
        network_api_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        client = neutron.Client(self.choose_version(version),
                                token=kc.auth_token,
                                endpoint_url=network_api_url,
                                timeout=CONF.openstack_client_http_timeout,
                                insecure=self.endpoint.insecure,
                                ca_cert=self.endpoint.cacert,
                                **self._get_auth_info(
                                    project_name_key="tenant_name")
                                )
        return client


@configure("glance", default_version="1", default_service_type="image")
class Glance(OSClient):
    def create_client(self, version=None):
        """Return glance client."""
        import glanceclient as glance
        kc = self.keystone()
        image_api_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        client = glance.Client(self.choose_version(version),
                               endpoint=image_api_url,
                               token=kc.auth_token,
                               timeout=CONF.openstack_client_http_timeout,
                               insecure=self.endpoint.insecure,
                               cacert=self.endpoint.cacert)
        return client


@configure("heat", default_version="1", default_service_type="orchestration")
class Heat(OSClient):
    def create_client(self, version=None):
        """Return heat client."""
        from heatclient import client as heat
        kc = self.keystone()
        orchestration_api_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        client = heat.Client(self.choose_version(version),
                             endpoint=orchestration_api_url,
                             token=kc.auth_token,
                             timeout=CONF.openstack_client_http_timeout,
                             insecure=self.endpoint.insecure,
                             cacert=self.endpoint.cacert,
                             **self._get_auth_info(project_name_key=None))
        return client


@configure("cinder", default_version="1", default_service_type="volume")
class Cinder(OSClient):
    def create_client(self, version=None):
        """Return cinder client."""
        from cinderclient import client as cinder
        client = cinder.Client(self.choose_version(version),
                               http_log_debug=logging.is_debug(),
                               timeout=CONF.openstack_client_http_timeout,
                               insecure=self.endpoint.insecure,
                               cacert=self.endpoint.cacert,
                               **self._get_auth_info(password_key="api_key"))
        kc = self.keystone()
        volume_api_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        client.client.management_url = volume_api_url
        client.client.auth_token = kc.auth_token
        return client


@configure("manila", default_version="1", default_service_type="share")
class Manila(OSClient):
    def create_client(self, version=None):
        """Return manila client."""
        from manilaclient import client as manila
        manila_client = manila.Client(
            self.choose_version(version),
            region_name=self.endpoint.region_name,
            http_log_debug=logging.is_debug(),
            timeout=CONF.openstack_client_http_timeout,
            insecure=self.endpoint.insecure,
            cacert=self.endpoint.cacert,
            **self._get_auth_info(password_key="api_key",
                                  project_name_key="project_name"))
        kc = self.keystone()
        manila_client.client.management_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        manila_client.client.auth_token = kc.auth_token
        return manila_client


@configure("ceilometer", default_version="2", default_service_type="metering")
class Ceilometer(OSClient):
    def create_client(self, version=None):
        """Return ceilometer client."""
        from ceilometerclient import client as ceilometer
        kc = self.keystone()
        metering_api_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        auth_token = kc.auth_token
        if not hasattr(auth_token, "__call__"):
            # python-ceilometerclient requires auth_token to be a callable
            auth_token = lambda: kc.auth_token

        client = ceilometer.get_client(
            self.choose_version(version),
            os_endpoint=metering_api_url,
            token=auth_token,
            timeout=CONF.openstack_client_http_timeout,
            insecure=self.endpoint.insecure,
            cacert=self.endpoint.cacert,
            **self._get_auth_info(project_name_key="tenant_name"))
        return client


@configure("ironic", default_version="1", default_service_type="baremetal")
class Ironic(OSClient):

    def create_client(self, version=None):
        """Return Ironic client."""
        from ironicclient import client as ironic
        kc = self.keystone()
        baremetal_api_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        client = ironic.get_client(self.choose_version(version),
                                   os_auth_token=kc.auth_token,
                                   ironic_url=baremetal_api_url,
                                   timeout=CONF.openstack_client_http_timeout,
                                   insecure=self.endpoint.insecure,
                                   cacert=self.endpoint.cacert)
        return client


@configure("sahara", default_version="1.1")
class Sahara(OSClient):
    def create_client(self, version=None):
        """Return Sahara client."""
        from saharaclient import client as sahara
        client = sahara.Client(self.choose_version(version),
                               **self._get_auth_info(
                                   password_key="api_key",
                                   project_name_key="project_name"))

        return client


@configure("zaqar", default_version="1.1", default_service_type="messaging")
class Zaqar(OSClient):
    def choose_version(self, version=None):
        # zaqarclient accepts only int or float obj as version
        return float(super(Zaqar, self).choose_version(version))

    def create_client(self, version=None):
        """Return Zaqar client."""
        from zaqarclient.queues import client as zaqar
        kc = self.keystone()
        messaging_api_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        conf = {"auth_opts": {"backend": "keystone", "options": {
            "os_username": self.endpoint.username,
            "os_password": self.endpoint.password,
            "os_project_name": self.endpoint.tenant_name,
            "os_project_id": kc.auth_tenant_id,
            "os_auth_url": self.endpoint.auth_url,
            "insecure": self.endpoint.insecure,
        }}}
        client = zaqar.Client(url=messaging_api_url,
                              version=self.choose_version(version),
                              conf=conf)
        return client


@configure("murano", default_version="1",
           default_service_type="application_catalog")
class Murano(OSClient):
    def create_client(self, version=None):
        """Return Murano client."""
        from muranoclient import client as murano
        kc = self.keystone()
        murano_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name
        )

        client = murano.Client(self.choose_version(version),
                               endpoint=murano_url,
                               token=kc.auth_token)

        return client


@configure("designate", default_version="1", default_service_type="dns")
class Designate(OSClient):
    def create_client(self, version=None):
        """Return designate client."""
        from designateclient import client

        version = self.choose_version(version)

        api_url = self._get_endpoint()
        api_url += "/v%s" % version

        session = self._get_session(endpoint=api_url)
        return client.Client(version, session=session)


@configure("trove", default_version="1.0")
class Trove(OSClient):
    def create_client(self, version=None):
        """Returns trove client."""
        from troveclient import client as trove
        client = trove.Client(self.choose_version(version),
                              region_name=self.endpoint.region_name,
                              timeout=CONF.openstack_client_http_timeout,
                              insecure=self.endpoint.insecure,
                              cacert=self.endpoint.cacert,
                              **self._get_auth_info(password_key="api_key")
                              )
        return client


@configure("mistral", default_service_type="workflowv2")
class Mistral(OSClient):
    def create_client(self):
        """Return Mistral client."""
        from mistralclient.api import client
        kc = self.keystone()

        mistral_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)

        client = client.client(mistral_url=mistral_url,
                               service_type=self.get_service_type(),
                               auth_token=kc.auth_token)
        return client


@configure("swift", default_service_type="object-store")
class Swift(OSClient):
    def create_client(self):
        """Return swift client."""
        from swiftclient import client as swift
        kc = self.keystone()
        object_api_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        client = swift.Connection(retries=1,
                                  preauthurl=object_api_url,
                                  preauthtoken=kc.auth_token,
                                  insecure=self.endpoint.insecure,
                                  cacert=self.endpoint.cacert,
                                  **self._get_auth_info(
                                      user_key="user",
                                      password_key="key",
                                      auth_url_key="authurl",
                                      project_name_key="tenant_name")
                                  )
        return client


@configure("ec2")
class EC2(OSClient):
    def create_client(self):
        """Return ec2 client."""
        import boto
        kc = self.keystone()
        if kc.version != "v2.0":
            raise exceptions.RallyException(
                _("Rally EC2 benchmark currently supports only"
                  "Keystone version 2"))
        ec2_credential = kc.ec2.create(user_id=kc.auth_user_id,
                                       tenant_id=kc.auth_tenant_id)
        ec2_api_url = kc.service_catalog.url_for(
            service_type=consts.ServiceType.EC2,
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        client = boto.connect_ec2_endpoint(
            url=ec2_api_url,
            aws_access_key_id=ec2_credential.access,
            aws_secret_access_key=ec2_credential.secret,
            is_secure=self.endpoint.insecure)
        return client


@configure("monasca", default_version="2_0",
           default_service_type="monitoring")
class Monasca(OSClient):
    def create_client(self, version=None):
        """Return monasca client."""
        from monascaclient import client as monasca
        kc = self.keystone()
        monitoring_api_url = kc.service_catalog.url_for(
            service_type=self.get_service_type(),
            endpoint_type=self.endpoint.endpoint_type,
            region_name=self.endpoint.region_name)
        auth_token = kc.auth_token
        client = monasca.Client(
            self.choose_version(version),
            monitoring_api_url,
            token=auth_token,
            timeout=CONF.openstack_client_http_timeout,
            insecure=self.endpoint.insecure,
            cacert=self.endpoint.cacert,
            **self._get_auth_info(project_name_key="tenant_name"))
        return client


class Clients(object):
    """This class simplify and unify work with OpenStack python clients."""

    def __init__(self, endpoint):
        self.endpoint = endpoint
        # NOTE(kun) Apply insecure/cacert settings from rally.conf if those are
        # not set in deployment config. Remove it when invalid.
        if self.endpoint.insecure is None:
            self.endpoint.insecure = CONF.https_insecure
        if self.endpoint.cacert is None:
            self.endpoint.cacert = CONF.https_cacert
        self.cache = {}

    def __getattr__(self, client_name):
        """Lazy load of clients."""
        return OSClient.get(client_name, namespace=_NAMESPACE)(
            self.endpoint, self.cache)

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

    def verified_keystone(self):
        """Ensure keystone endpoints are valid and then authenticate

        :returns: Keystone Client
        """
        from keystoneclient import exceptions as keystone_exceptions
        try:
            # Ensure that user is admin
            client = self.keystone()
            if "admin" not in [role.lower() for role in
                               client.auth_ref.role_names]:
                raise exceptions.InvalidAdminException(
                    username=self.endpoint.username)
        except keystone_exceptions.Unauthorized:
            raise exceptions.InvalidEndpointsException()
        except keystone_exceptions.AuthorizationFailure:
            raise exceptions.HostUnreachableException(
                url=self.endpoint.auth_url)
        return client

    def services(self):
        """Return available services names and types.

        :returns: dict, {"service_type": "service_name", ...}
        """
        if "services_data" not in self.cache:
            services_data = {}
            ks = self.keystone()
            available_services = ks.service_catalog.get_endpoints()
            for stype in available_services.keys():
                if stype in consts.ServiceType:
                    services_data[stype] = consts.ServiceType[stype]
            self.cache["services_data"] = services_data

        return self.cache["services_data"]

    @classmethod
    @utils.log_deprecated("Use rally.osclients.configure decorator instead.",
                          "0.1.2")
    def register(cls, client_name):
        """DEPRECATED!Decorator that adds new OpenStack client dynamically.

        Use rally.osclients.configure decorator instead!

        :param client_name: str name how client will be named in Rally clients

        Decorated class will be added to Clients in runtime, so its sole
        argument is a Clients instance.

        Decorated function will be added to Clients in runtime, so its sole
        argument is a Clients instance.

        Example:
          >>> from rally import osclients
          >>> @osclients.Clients.register("supernova")
          ... def another_nova_client(self):
          ...   from novaclient import client as nova
          ...   return nova.Client("2", auth_token=self.keystone().auth_token,
          ...                      **self._get_auth_info(password_key="key"))
          ...
          >>> clients = osclients.Clients.create_from_env()
          >>> clients.supernova().services.list()[:2]
          [<Service: nova-conductor>, <Service: nova-cert>]
        """
        def wrap(client_func):
            try:
                OSClient.get(client_name, _NAMESPACE)
            except exceptions.PluginNotFound:
                # everything is ok
                pass
            else:
                raise ValueError(
                    _("Can not register client: name already exists: %s")
                    % client_name)

            @configure(client_name)
            class NewClient(OSClient):
                create_client = client_func

            return NewClient

        return wrap
