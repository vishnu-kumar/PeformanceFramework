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
        "jcs_ec2_server_boot_prepoll_delay",
        default=1.0,
        help="Time to sleep after boot before polling for status"
    ),
    cfg.FloatOpt(
        "jcs_ec2_server_boot_timeout",
        default=300.0,
        help="Server boot timeout"
    ),
    cfg.FloatOpt(
        "jcs_ec2_server_boot_poll_interval",
        default=1.0,
        help="Server boot poll interval"
    )
]

CONF = cfg.CONF
benchmark_group = cfg.OptGroup(name="benchmark",
                               title="benchmark options")
CONF.register_opts(EC2_BENCHMARK_OPTS, group=benchmark_group)


class JCSSBSScenario(scenario.JCSScenario):
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
    @atomic.action_timer("jcs_ec2.list_volumes")
    def _list_volumes(self):
        """Returns user volumes list."""
	return self.clients("jcs_ec2").describe_volumes()
    
    @atomic.action_timer("jcs_ec2.create_volume")
    def _create_volume(self, **kwargs):
	"""Create Volumes and wait for volume to be avalable.
	kwargs = {Name, SnapshotId, Description, Size} 
	Size is mandatory when SnapshotId is not supplied.
	:returns volumeId: string, volumeId of volume created.
	"""
	#AvailabilityZone is required.You can attach a volume to an instance in same zone.
	"""
	http://boto3.readthedocs.org/en/latest/reference/services/ec2.html#waiters
	waiter = client.get_waiter('volume_available')
	response = client.create_volume(
    	DryRun=True|False,
    	Size=123,
    	SnapshotId='string',
    	AvailabilityZone='string',
    	VolumeType='standard'|'io1'|'gp2',
    	Iops=123,
    	Encrypted=True|False,
    	KmsKeyId='string'
	)
	waiter.wait(
    	DryRun=True|False,
    	VolumeIds=[
        	'string',
    		],
    	Filters=[
        {
            'Name': 'string',
            'Values': [
                'string',
            ]
        },
    	]	,
    	NextToken='string',
    	MaxResults=123
	)
	
	"""
	response = self.clients("jcs_ec2").create_volume(**kwargs)
	volumeId = response["VolumeId"]
	vol_available_waiter = self.clients("jcs_ec2").get_waiter('volume_available')
	vol_available_waiter.wait(VolumeIds=[volumeId])

	return (volumeId, response)

    @atomic.action_timer("jcs_ec2.delete_volume")
    def _delete_volume(self, volumeId):
	"""
	response = client.delete_volume(
    	DryRun=True|False,
    	VolumeId='string'
	)
	#The volume must be in the available state (not attached to an instance).
	"""
	#Need to check wether volume is in available state or not.
	response = self.clients("jcs_ec2").delete_volume(VolumeId = volumeId)
	
	vol_deleted_waiter = self.clients("jcs_ec2").get_waiter('volume_deleted')
        vol_deleted_waiter.wait(VolumeIds=[volumeId])

    @atomic.action_timer("jcs_ec2.attach_volume")
    def _attach_volume(self, VolumeId, InstanceId, Device):
	"""
	response = client.attach_volume(
    	DryRun=True|False,
    	VolumeId='string',
    	InstanceId='string',
    	Device='string'
	)
	"""
	response = self.clients("jcs_ec2").attach_volume(VolumeId=VolumeId, InstanceId=InstanceId, Device=device)
	vol_in_use_waiter = self.clients("jcs_ec2").get_waiter('volume_in_use')
	
	vol_in_use_waiter.wait(VolumeIds=[volumeId])

    @atomic.action_timer("jcs_ec2.detach_volume")
    def _detach_volume(self, volumeId, instanceId, force=False, **kwargs):
	"""
	response = client.detach_volume(
    	DryRun=True|False,
    	VolumeId='string',
    	InstanceId='string',
    	Device='string',
    	Force=True|False
	)
	"""
	response = self.clients("jcs_ec2").detach_volume(VolumeId=volumeId, InstanceId=instanceId, Force=force, **kwargs)
	volumeId= response["VolumeId"]
	
    	vol_available_waiter = self.clients("jcs_ec2").get_waiter('volume_available')
        vol_available_waiter.wait(VolumeIds=[volumeId])

    def _update_resource(self, resource):
        resource.update()
        return resource
