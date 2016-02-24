# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from rally.common import log as logging
from rally import consts
from rally.plugins.jcs import scenario
from rally.plugins.jcs.scenarios.ec2 import utils
from rally.task import types
from rally.task import validation


LOG = logging.getLogger(__name__)


class JCSEC2Servers(utils.JCSEC2Scenario):
    """Benchmark scenarios for servers using EC2."""

    #@validation.required_services(consts.Service.EC2)
    #@validation.required_openstack(users=True)
    @scenario.configure(context={"cleanup": ["jcs_ec2"]})
    def list_servers(self):
        """List all servers.

        This simple scenario tests the EC2 API list function by listing
        all the servers.
        """
        self._list_servers()

    @scenario.configure(context={"cleanup": ["jcs_ec2"]})
    def run_instances(self, ImageId, InstanceTypeId, **kwargs):
        self._run_instances(ImageId, InstanceTypeId, **kwargs)

   
    @scenario.configure(context={"cleanup": ["jcs_ec2"]})
    def create_list_delete_keypair(self):
	keyName =  self.generate_random_name()
	(keyMaterial, response) = self._create_key_pair(keyName)
	self._list_key_pair()
	self._delete_key_pair(keyName)
		
    @scenario.configure(context={"cleanup": ["jcs_ec2"]})
    def run_instances_1(self, imageId, instanceTypeId, instanceCount, subnetId):
	self._run_instances(imageId, instanceTypeId, instanceCount, subnetId)

    @scenario.configure(context={"cleanup": ["jcs_ec2"]})
    def run_and_stop_instances(self, imageId = "ami-96f1c1c4", instanceType="m3.medium", instanceCount=128):
        self._run_and_stop_instances(imageId, instanceType, instanceCount)

    @scenario.configure(context={"cleanup": ["jcs_ec2"]})
    def create_volume(self, az="ap-southeast-1a", size=1):
	self._create_volume(az, size)

    @scenario.configure(context={"cleanup": ["jcs_ec2"]})
    def run_instance_and_attach_volume(self, imageId = "ami-96f1c1c4", instanceType="t2.micro", instanceCount=1, size=1):
	self._run_instance_and_attach_volume(imageId, instanceType, instanceCount, size)

    @types.set(image=types.EC2ImageResourceType,
               flavor=types.EC2FlavorResourceType)
    @validation.image_valid_on_flavor("flavor", "image")
    #@validation.required_services(consts.Service.EC2)
    #@validation.required_openstack(users=True)
    @scenario.configure(context={"cleanup": ["jcs_ec2"]})
    def boot_server(self, image, flavor, **kwargs):
        """Boot a server.

        Assumes that cleanup is done elsewhere.

        :param image: image to be used to boot an instance
        :param flavor: flavor to be used to boot an instance
        :param kwargs: optional additional arguments for server creation
        """
        self._boot_servers(image, flavor, **kwargs)
