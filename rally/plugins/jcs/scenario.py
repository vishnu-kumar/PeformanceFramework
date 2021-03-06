# Copyright 2015: Mirantis Inc.
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

from rally import jcsclients
from rally.task import scenario

# NOTE(boris-42): Shortcut to remove import of both rally.task.scenario and
#                 rally.plugins.openstack.scenario
configure = scenario.configure


class JCSScenario(scenario.Scenario):
    """Base class for all JCS scenarios."""

    # TODO(stpierre): this is still used by some cleanup routines;
    # remove it when they're using the new random name generator
    RESOURCE_NAME_PREFIX = "rally_"

    def __init__(self, context=None, admin_clients=None, clients=None):
        super(JCSScenario, self).__init__(context)
	"""
        if context:
            if "admin" in context:
                self._admin_clients = osclients.Clients(
                    context["admin"]["endpoint"])
            if "user" in context:
                self._clients = osclients.Clients(context["user"]["endpoint"])
        if admin_clients:
            if hasattr(self, "_admin_clients"):
                raise ValueError(
                    "Only one of context[\"admin\"] or admin_clients"
                    " must be supplied")
            self._admin_clients = admin_clients
        if clients:
            if hasattr(self, "_clients"):
                raise ValueError(
                    "Only one of context[\"user\"] or clients"
                    " must be supplied")
            self._clients = clients
	"""
	self._clients = jcsclients.Clients()

    def clients(self, client_type, version=None, **kwargs):
        """Returns a python jcs client of the requested type.

        The client will be that for one of the temporary non-administrator
        users created before the benchmark launch.

        :param client_type: Client type ("ec2"/"s3" etc.)
        :param version: client version ("1"/"2" etc.)

        :returns: Standard jcs service client instance
        """
	kwargs = self.context["jcs_user"]
        client = getattr(self._clients, client_type)

        return client(version, **kwargs) if version is not None else client(**kwargs)

    def admin_clients(self, client_type, version=None):
	pass
