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

import time

from oslo_config import cfg

from rally.plugins.jcs import scenario
from rally.task import atomic
from rally.task import utils


EC2_BENCHMARK_OPTS = [
    cfg.FloatOpt(
        "jcs_vpc_server_boot_prepoll_delay",
        default=1.0,
        help="Time to sleep after boot before polling for status"
    ),
    cfg.FloatOpt(
        "jcs_vpc_server_boot_timeout",
        default=300.0,
        help="Server boot timeout"
    ),
    cfg.FloatOpt(
        "jcs_vpc_server_boot_poll_interval",
        default=1.0,
        help="Server boot poll interval"
    )
]

CONF = cfg.CONF
benchmark_group = cfg.OptGroup(name="benchmark",
                               title="benchmark options")
CONF.register_opts(EC2_BENCHMARK_OPTS, group=benchmark_group)


class JCSVPCScenario(scenario.JCSScenario):
    """Base class for EC2 scenarios with basic atomic actions."""

    """
    ec2 = boto3.client("ec2")
    ec2.waiter_names
[u'bundle_task_complete', u'console_output_available', u'conversion_task_cancelled', u'conversion_task_completed', u'conversion_task_deleted', u'customer_gateway_available', u'export_task_cancelled', u'export_task_completed', u'image_available', u'instance_exists', u'instance_running', u'instance_status_ok', u'instance_stopped', u'instance_terminated', u'password_data_available', u'snapshot_completed', u'spot_instance_request_fulfilled', u'subnet_available', u'system_status_ok', u'volume_available', u'volume_deleted', u'volume_in_use', u'vpc_available', u'vpn_connection_available', u'vpn_connection_deleted']
    """

    """
    	s3 waiters:
	[u'bucket_exists', u'bucket_not_exists', u'object_exists', u'object_not_exists']
    """
    """
	ubuntu-trusty-14.04-amd64-server-20150325 (ami-96f1c1c4)
    """
    @atomic.action_timer("jcs_vpc.list_vpcs")
    def _list_vpcs(self):
        """Returns user volumes list."""
	return self.clients("jcs_vpc").describe_vpcs()
    
    @atomic.action_timer("jcs_vpc.create_vpc")
    def _create_vpc(self, cidr):
	response = self.clients("jcs_vpc").create_vpc(CidrBlock=cidr)
	vpcId = response["VpcId"]
	vpc_available_waiter = self.clients("jcs_vpc").get_waiter('vpc_available')
	vpc_available_waiter.wait(VpcIds=[vpcId])

	return (vpcId, response)

    @atomic.action_timer("jcs_vpc.delete_vpc")
    def _delete_vpc(self, vpcId):
        response = self.clients("jcs_vpc").delete_vpc(VpcId=vpcId)
	#TBD need to implement waiters as boto3 dont provide any waiters for vpc_deleted
        #vpcId = response["VpcId"]
        #vpc_available_waiter = self.clients("jcs_vpc").get_waiter('vpc_available')
        #vpc_available_waiter.wait(VpcIds=[vpcId])

        #return (vpcId, response)

    @atomic.action_timer("jcs_vpc.create_subnet")
    def _create_subnet(self, vpcId, cidrBlock):
        response = self.clients("jcs_vpc").create_subnet(VpcId=vpcId, CidrBlock=cidr)
        subnetId = response["SubnetId"]
        vpc_available_waiter = self.clients("jcs_vpc").get_waiter('subnet_available')
        vpc_available_waiter.wait(VpcIds=[vpcId])

        return (vpcId, response)

    @atomic.action_timer("jcs_vpc.create_security_group")
    def _create_security_group(self, vpcId, groupName, groupDescription):
	response = self.clients("jcs_vpc").create_security_group(vpcId, groupName, groupDescription)
	sec_grp_id = response["GroupId"]
	return (sec_grp_id, response)

    @atomic.action_timer("jcs_vpc.create_open_security_group")
    def _create_open_security_group(self, vpcId, groupName="open_sec_grp", groupDescription="All permissions igress and egress"):
	(sec_grp_id, response) = self._create_security_group(vpcId, groupName, groupDescription)
	kwargs = {
            'GroupId': sec_grp_id,
            'IpPermissions': [
		{
                'IpProtocol': 'tcp',
                'FromPort': 1,
                'ToPort': 65535,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
               	},
		{
		'IpProtocol': 'icmp',
                'FromPort': -1,
                'ToPort': -1,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                },
		{
                'IpProtocol': 'udp',
                'FromPort': 1,
                'ToPort': 65535,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                }  
	]	
        }
	self.clients("jcs_vpc").authorize_security_group_ingress(**kwargs)
	#TBD vishnu Default egress rule is open so we dont require below step
	self.clients("jcs_vpc").authorize_security_group_egress(**kwargs)

	return sec_grp_id

    @atomic.action_timer("jcs_vpc.create_floating_ip")
    def _create_floating_ip(self, domain="vpc"):
	kwargs = {
            'Domain': domain,
        }
	response = self.clients("jcs_vpc").allocate_address(**kwargs)
	publicIp = response["PublicIp"]
	allocationId = response["AllocationId"]
	
	return (allocationId, response)

    @atomic.action_timer("jcs_vpc.release_floating_ip")
    def _release_floating_ip(self, allocationId):
	response = self.clients("jcs_vpc").release_address(AllocationId=allocationId)

    @atomic.action_timer("jcs_vpc.associate_address")
    def _associate_address(self, instanceId, allocationId):
	kwargs = {
	"InstanceId":instanceId,
	"AllocationId":allocationId
	}
	response = self.clients("jcs_vpc").associate_address(**kwargs)
	associationId = response["AssociationId"]
	
	return (associationId, response)

    @atomic.action_timer("jcs_vpc.disassociate_address")
    def _disassociate_address(self, associationId):
	kwargs = {
	"AssociationId":associationId
	}
	self.client("jcs_vpc").disassociate_address(**kwargs)
	
    def _update_resource(self, resource):
        resource.update()
        return resource
